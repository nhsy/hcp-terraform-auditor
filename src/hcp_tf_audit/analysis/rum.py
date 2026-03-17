"""RUM (Resources Under Management) analysis."""

from collections import defaultdict
from datetime import datetime

from ..config import RUM_INFLATOR_TYPES, THRESHOLDS
from ..models import WorkspaceAudit


def analyze_rum(ws_audit: WorkspaceAudit, stale_cutoff: datetime) -> None:
    """Analyze managed resources for RUM billing impact and anti-patterns."""
    resources = ws_audit.resources
    rum = ws_audit.rum
    rum.total_managed = len(resources)

    if rum.total_managed == 0:
        return

    by_provider = defaultdict(int)
    by_type = defaultdict(int)
    by_module = defaultdict(int)
    inflators = 0
    stale = 0

    for res in resources:
        by_provider[res.provider] += 1
        by_type[res.provider_type] += 1
        by_module[res.module] += 1

        if res.provider_type in RUM_INFLATOR_TYPES:
            inflators += 1

        if res.updated_at:
            try:
                updated = datetime.fromisoformat(res.updated_at + "T00:00:00+00:00")
                if updated < stale_cutoff:
                    stale += 1
            except (ValueError, TypeError):
                pass

    rum.inflator_count = inflators
    rum.inflator_pct = round(inflators / rum.total_managed, 3) if rum.total_managed > 0 else 0
    rum.by_provider = dict(by_provider)
    rum.by_type = dict(by_type)
    rum.by_module = dict(by_module)
    rum.top_types = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:10]
    rum.stale_resources = stale

    # ── RUM Anti-pattern: Oversized workspace ──
    if rum.total_managed >= THRESHOLDS["rum_heavy_workspace"]:
        ws_audit.findings.append(
            {
                "pattern": "RUM_HEAVY_WORKSPACE",
                "severity": "HIGH",
                "category": "RUM",
                "detail": (
                    f"Workspace manages {rum.total_managed} resources "
                    f"(threshold: {THRESHOLDS['rum_heavy_workspace']}). "
                    f"Consider splitting into smaller, focused workspaces to reduce "
                    f"blast radius and plan times."
                ),
            }
        )

    # ── RUM Anti-pattern: High inflator ratio ──
    if rum.total_managed >= 20 and rum.inflator_pct > THRESHOLDS["rum_inflator_ratio"]:
        ws_audit.findings.append(
            {
                "pattern": "RUM_INFLATOR_HEAVY",
                "severity": "HIGH",
                "category": "RUM",
                "detail": (
                    f"{inflators}/{rum.total_managed} resources ({rum.inflator_pct:.0%}) are "
                    f"zero-cost control-plane objects (IAM policies, SG rules, DNS records, etc.) "
                    f"that inflate your RUM count. Consider managing these with a separate tool, "
                    f"consolidating SG rules into single resources, or using aws_security_group "
                    f"inline rules instead of aws_security_group_rule."
                ),
            }
        )

    # ── RUM Anti-pattern: Stale resources ──
    if rum.total_managed >= 10 and stale > 0:
        stale_pct = stale / rum.total_managed
        if stale_pct > 0.50:
            ws_audit.findings.append(
                {
                    "pattern": "RUM_STALE_RESOURCES",
                    "severity": "MEDIUM",
                    "category": "RUM",
                    "detail": (
                        f"{stale}/{rum.total_managed} resources ({stale_pct:.0%}) have not been "
                        f"modified in {THRESHOLDS['rum_stale_resource_days']}+ days. "
                        f"Review whether these are still needed. Removing unused resources "
                        f"reduces your RUM count."
                    ),
                }
            )

    # ── RUM Anti-pattern: Module sprawl ──
    if len(by_module) > 10 and rum.total_managed > 50:
        ws_audit.findings.append(
            {
                "pattern": "RUM_MODULE_SPRAWL",
                "severity": "LOW",
                "category": "RUM",
                "detail": (
                    f"Workspace uses {len(by_module)} distinct modules with "
                    f"{rum.total_managed} total resources. Deep module nesting can create "
                    f"many small helper resources. Audit modules for unnecessary resource "
                    f"generation."
                ),
            }
        )
