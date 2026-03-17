"""Run analysis functions."""

from datetime import datetime

from ..config import THRESHOLDS
from ..models import WorkspaceAudit


def detect_rapid_fire(runs: list) -> int:
    """Count sequences of rapid-fire runs (many runs within a short window)."""
    if len(runs) < 2:
        return 0
    sorted_runs = sorted(runs, key=lambda r: r.created_at)
    sequences = 0
    streak = 1
    for i in range(1, len(sorted_runs)):
        try:
            t1 = datetime.fromisoformat(sorted_runs[i - 1].created_at.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(sorted_runs[i].created_at.replace("Z", "+00:00"))
            delta_min = (t2 - t1).total_seconds() / 60.0
            if delta_min <= THRESHOLDS["rapid_fire_interval_min"]:
                streak += 1
            else:
                if streak >= THRESHOLDS["rapid_fire_count"]:
                    sequences += 1
                streak = 1
        except (ValueError, TypeError):
            streak = 1
    if streak >= THRESHOLDS["rapid_fire_count"]:
        sequences += 1
    return sequences


def analyze_runs(ws_audit: WorkspaceAudit, audit_days: int) -> None:
    """Analyze a workspace's runs and populate findings."""
    runs = ws_audit.runs
    n = len(runs)
    if n == 0:
        return

    ws_audit.run_count = n
    ws_audit.errored_count = sum(1 for r in runs if r.status == "errored")
    ws_audit.canceled_count = sum(1 for r in runs if r.status in ("canceled", "force_canceled"))
    ws_audit.applied_count = sum(1 for r in runs if r.status == "applied")
    ws_audit.plan_only_count = sum(1 for r in runs if r.operation == "plan_only")
    ws_audit.discarded_count = sum(1 for r in runs if r.status == "discarded")
    ws_audit.no_changes_count = sum(1 for r in runs if r.status == "planned_and_finished" and not r.has_changes)
    ws_audit.destroy_count = sum(1 for r in runs if r.is_destroy)
    ws_audit.avg_daily_runs = round(n / max(audit_days, 1), 2)
    ws_audit.rapid_fire_sequences = detect_rapid_fire(runs)

    # ── High failure rate ──
    if n >= 5 and ws_audit.errored_count / n > THRESHOLDS["high_failure_rate"]:
        ws_audit.findings.append(
            {
                "pattern": "HIGH_FAILURE_RATE",
                "severity": "HIGH",
                "category": "Runs",
                "detail": (
                    f"{ws_audit.errored_count}/{n} runs errored "
                    f"({ws_audit.errored_count / n:.0%}). Investigate provider auth, "
                    f"state corruption, or version mismatches."
                ),
            }
        )

    # ── High cancel rate ──
    if n >= 5 and ws_audit.canceled_count / n > THRESHOLDS["high_cancel_rate"]:
        ws_audit.findings.append(
            {
                "pattern": "HIGH_CANCEL_RATE",
                "severity": "MEDIUM",
                "category": "Runs",
                "detail": (
                    f"{ws_audit.canceled_count}/{n} runs canceled "
                    f"({ws_audit.canceled_count / n:.0%}). Users may be triggering "
                    f"runs prematurely."
                ),
            }
        )

    # ── Excessive daily runs ──
    if ws_audit.avg_daily_runs > THRESHOLDS["excessive_daily_runs"]:
        ws_audit.findings.append(
            {
                "pattern": "EXCESSIVE_DAILY_RUNS",
                "severity": "HIGH",
                "category": "Runs",
                "detail": (
                    f"Averaging {ws_audit.avg_daily_runs} runs/day. "
                    f"Batch changes, use VCS path filters, or consolidate triggers."
                ),
            }
        )

    # ── Speculative plan overuse ──
    if n >= 10 and ws_audit.plan_only_count / n > THRESHOLDS["speculative_plan_ratio"]:
        ws_audit.findings.append(
            {
                "pattern": "SPECULATIVE_PLAN_OVERUSE",
                "severity": "MEDIUM",
                "category": "Runs",
                "detail": (
                    f"{ws_audit.plan_only_count}/{n} runs are plan-only "
                    f"({ws_audit.plan_only_count / n:.0%}). Each PR commit triggers "
                    f"a speculative plan—use draft PRs or label-based triggers."
                ),
            }
        )

    # ── Rapid-fire runs ──
    if ws_audit.rapid_fire_sequences > 0:
        ws_audit.findings.append(
            {
                "pattern": "RAPID_FIRE_RUNS",
                "severity": "HIGH",
                "category": "Runs",
                "detail": (
                    f"{ws_audit.rapid_fire_sequences} sequence(s) of "
                    f"{THRESHOLDS['rapid_fire_count']}+ runs within "
                    f"{THRESHOLDS['rapid_fire_interval_min']} min. Likely CI/CD "
                    f"misconfiguration."
                ),
            }
        )

    # ── No-change churn ──
    if n >= 10 and ws_audit.no_changes_count / n > THRESHOLDS["no_change_churn_ratio"]:
        ws_audit.findings.append(
            {
                "pattern": "NO_CHANGE_CHURN",
                "severity": "MEDIUM",
                "category": "Runs",
                "detail": (
                    f"{ws_audit.no_changes_count}/{n} runs had no changes "
                    f"({ws_audit.no_changes_count / n:.0%}). Set file-triggers-enabled "
                    f"and configure trigger-prefixes."
                ),
            }
        )

    # ── Long plan durations (correlated with high RUM) ──
    plan_times = [r.plan_duration for r in runs if r.plan_duration is not None]
    if plan_times:
        long = sum(1 for t in plan_times if t > THRESHOLDS["long_plan_duration_min"])
        if long > 0:
            avg_plan = sum(plan_times) / len(plan_times)
            ws_audit.findings.append(
                {
                    "pattern": "LONG_PLAN_DURATION",
                    "severity": "MEDIUM",
                    "category": "Runs/RUM",
                    "detail": (
                        f"{long} plans exceeded {THRESHOLDS['long_plan_duration_min']} min "
                        f"(avg {avg_plan:.1f} min). High resource counts inflate plan times. "
                        f"Split workspace or reduce RUM."
                    ),
                }
            )

    # ── Destroy-heavy ──
    if n >= 5 and ws_audit.destroy_count / n > 0.3:
        ws_audit.findings.append(
            {
                "pattern": "DESTROY_HEAVY",
                "severity": "MEDIUM",
                "category": "Runs",
                "detail": (
                    f"{ws_audit.destroy_count}/{n} runs are destroys "
                    f"({ws_audit.destroy_count / n:.0%}). Consider ephemeral "
                    f"workspace patterns."
                ),
            }
        )

    # ── Shadow CI (no VCS, all API-driven) ──
    api_runs = sum(1 for r in runs if r.source == "tfe-api")
    if not ws_audit.vcs_connected and api_runs > n * 0.8 and n >= 10:
        ws_audit.findings.append(
            {
                "pattern": "SHADOW_CI_PIPELINE",
                "severity": "LOW",
                "category": "Runs",
                "detail": (
                    f"No VCS connection but {api_runs}/{n} runs are API-triggered. "
                    f"Connect to VCS for better deduplication."
                ),
            }
        )
