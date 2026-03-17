"""Org-level analysis and recommendations."""

from collections import Counter, defaultdict

from ..config import THRESHOLDS
from ..models import OrgAuditReport


def compute_org_summary(report: OrgAuditReport) -> None:
    """Roll up per-workspace data into org-level totals and detect org-wide anti-patterns."""
    org_by_provider: dict = defaultdict(int)
    org_by_type: dict = defaultdict(int)
    org_by_project: dict = defaultdict(int)

    for ws in report.workspace_audits:
        # RUM rollup
        report.total_rum += ws.rum.total_managed
        report.total_rum_inflators += ws.rum.inflator_count
        for prov, cnt in ws.rum.by_provider.items():
            org_by_provider[prov] += cnt
        for typ, cnt in ws.rum.by_type.items():
            org_by_type[typ] += cnt
        org_by_project[ws.project] += ws.rum.total_managed

        # Run rollup
        report.total_runs += ws.run_count
        report.total_errored += ws.errored_count
        report.total_canceled += ws.canceled_count
        report.total_applied += ws.applied_count
        report.total_plan_only += ws.plan_only_count
        report.total_no_changes += ws.no_changes_count

        if ws.run_count > 0:
            report.active_workspaces += 1
        else:
            report.stale_workspaces += 1

    report.org_inflator_pct = round(report.total_rum_inflators / max(report.total_rum, 1), 3)
    report.rum_by_provider = dict(org_by_provider)
    report.rum_by_project = dict(org_by_project)
    report.rum_by_type_top20 = sorted(org_by_type.items(), key=lambda x: x[1], reverse=True)[:20]
    report.estimated_wasted_runs = report.total_errored + report.total_canceled + report.total_no_changes

    # ── Org-level RUM anti-pattern: concentration risk ──
    if report.total_rum > 0:
        for ws in report.workspace_audits:
            ws_pct = ws.rum.total_managed / report.total_rum
            if ws_pct > THRESHOLDS["rum_concentration_pct"] and ws.rum.total_managed > 50:
                ws.findings.append(
                    {
                        "pattern": "RUM_CONCENTRATION_RISK",
                        "severity": "HIGH",
                        "category": "RUM",
                        "detail": (
                            f"Workspace holds {ws.rum.total_managed}/{report.total_rum} "
                            f"({ws_pct:.0%}) of all org RUM. A single large workspace "
                            f"creates blast radius and billing concentration risk."
                        ),
                    }
                )


def generate_recommendations(report: OrgAuditReport) -> None:
    """Generate prioritised recommendations from detected anti-patterns."""
    pattern_counts: Counter = Counter()
    for ws in report.workspace_audits:
        for f in ws.findings:
            pattern_counts[f["pattern"]] += 1

    recs = []

    # ── RUM Recommendations ──

    if report.total_rum_inflators > 0:
        recs.append(
            {
                "priority": "HIGH",
                "category": "RUM Efficiency",
                "title": f"Reduce RUM inflators ({report.total_rum_inflators} resources)",
                "detail": (
                    f"{report.total_rum_inflators} of {report.total_rum} managed resources "
                    f"({report.org_inflator_pct:.0%}) are zero-cost control-plane objects "
                    f"(IAM roles/policies, SG rules, DNS records, etc.) that inflate your RUM "
                    f"count. Strategies: (1) Use inline security group rules instead of separate "
                    f"aws_security_group_rule resources; (2) Consolidate IAM policies into fewer "
                    f"combined policies; (3) Move lightweight resources to a non-HCP-Terraform "
                    f"backend; (4) Use for_each on parent resources instead of spawning helper "
                    f"resources."
                ),
            }
        )

    if pattern_counts["RUM_HEAVY_WORKSPACE"] > 0:
        recs.append(
            {
                "priority": "HIGH",
                "category": "RUM Architecture",
                "title": "Split oversized workspaces",
                "detail": (
                    f"{pattern_counts['RUM_HEAVY_WORKSPACE']} workspace(s) exceed "
                    f"{THRESHOLDS['rum_heavy_workspace']} managed resources. Large workspaces "
                    f"cause slow plans, higher blast radius, and queue contention. Split by "
                    f"service boundary, environment, or lifecycle (e.g., networking vs compute "
                    f"vs IAM). Use terraform_remote_state or run triggers to coordinate."
                ),
            }
        )

    if pattern_counts["RUM_STALE_RESOURCES"] > 0:
        recs.append(
            {
                "priority": "MEDIUM",
                "category": "RUM Cleanup",
                "title": "Remove or audit stale resources",
                "detail": (
                    f"{pattern_counts['RUM_STALE_RESOURCES']} workspace(s) contain resources "
                    f"unchanged for {THRESHOLDS['rum_stale_resource_days']}+ days. Each stale "
                    f"resource still counts as a billable RUM. Run terraform state list and "
                    f"terraform state rm for resources that are no longer needed, or terraform "
                    f"import them into a self-managed backend."
                ),
            }
        )

    if pattern_counts["RUM_CONCENTRATION_RISK"] > 0:
        recs.append(
            {
                "priority": "HIGH",
                "category": "RUM Governance",
                "title": "Redistribute concentrated RUM",
                "detail": (
                    f"{pattern_counts['RUM_CONCENTRATION_RISK']} workspace(s) hold >"
                    f"{THRESHOLDS['rum_concentration_pct']:.0%} of total org RUM. "
                    f"This creates billing concentration risk where a single workspace "
                    f"dominates your costs. Decompose into project-aligned workspaces."
                ),
            }
        )

    # ── Run Recommendations ──

    if pattern_counts["HIGH_FAILURE_RATE"] > 0:
        recs.append(
            {
                "priority": "HIGH",
                "category": "Run Reliability",
                "title": "Investigate high-failure workspaces",
                "detail": (
                    f"{pattern_counts['HIGH_FAILURE_RATE']} workspace(s) have error rates "
                    f"above {THRESHOLDS['high_failure_rate']:.0%}. Common causes: expired "
                    f"credentials, state corruption, version incompatibilities."
                ),
            }
        )

    if pattern_counts["RAPID_FIRE_RUNS"] > 0:
        recs.append(
            {
                "priority": "HIGH",
                "category": "CI/CD Hygiene",
                "title": "Fix rapid-fire run triggers",
                "detail": (
                    f"{pattern_counts['RAPID_FIRE_RUNS']} workspace(s) show rapid-fire bursts. "
                    f"Add debounce logic in CI (cancel previous runs on new commits) or use "
                    f"squash merges."
                ),
            }
        )

    if pattern_counts["EXCESSIVE_DAILY_RUNS"] > 0:
        recs.append(
            {
                "priority": "HIGH",
                "category": "Run Volume",
                "title": "Reduce excessive daily run volume",
                "detail": (
                    f"{pattern_counts['EXCESSIVE_DAILY_RUNS']} workspace(s) exceed "
                    f"{THRESHOLDS['excessive_daily_runs']} runs/day. Use path-based filtering "
                    f"(file-triggers-enabled + trigger-prefixes)."
                ),
            }
        )

    if pattern_counts["NO_CHANGE_CHURN"] > 0:
        recs.append(
            {
                "priority": "MEDIUM",
                "category": "Run Efficiency",
                "title": "Reduce no-change run churn",
                "detail": (
                    f"{pattern_counts['NO_CHANGE_CHURN']} workspace(s) frequently plan with "
                    f"no changes. Configure trigger-prefixes or trigger-patterns."
                ),
            }
        )

    if pattern_counts["SPECULATIVE_PLAN_OVERUSE"] > 0:
        recs.append(
            {
                "priority": "MEDIUM",
                "category": "Run Cost",
                "title": "Optimize speculative plans",
                "detail": (
                    f"{pattern_counts['SPECULATIVE_PLAN_OVERUSE']} workspace(s) have >70% "
                    f"plan-only runs. Use draft PRs, path filtering, or label-based triggers."
                ),
            }
        )

    if report.stale_workspaces > 0:
        recs.append(
            {
                "priority": "LOW",
                "category": "Governance",
                "title": "Clean up stale workspaces",
                "detail": (
                    f"{report.stale_workspaces} workspace(s) had zero runs in the audit "
                    f"period. Check if they still manage resources (which still incur RUM "
                    f"costs even without runs)."
                ),
            }
        )

    waste_pct = (report.estimated_wasted_runs / max(report.total_runs, 1)) * 100
    if waste_pct > 15:
        recs.append(
            {
                "priority": "HIGH",
                "category": "Run Waste",
                "title": f"Reduce wasted runs ({waste_pct:.0f}% of total)",
                "detail": (
                    f"{report.estimated_wasted_runs}/{report.total_runs} runs "
                    f"({waste_pct:.1f}%) were errored, canceled, or no-change."
                ),
            }
        )

    report.recommendations = sorted(recs, key=lambda r: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[r["priority"]])
    report.anti_patterns = [{"pattern": k, "affected_workspaces": v} for k, v in pattern_counts.most_common()]
