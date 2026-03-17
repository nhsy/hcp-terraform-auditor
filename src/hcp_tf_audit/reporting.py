"""Report printing functions."""

from .config import RUM_INFLATOR_TYPES
from .models import OrgAuditReport


def print_report(report: OrgAuditReport, top_n: int, request_count: int) -> None:
    W = 80
    sep = "=" * W
    thin = "─" * 44

    print(f"\n{sep}")
    print("  HCP TERRAFORM — RUM & RUN USAGE AUDIT REPORT")
    print(f"  Organization: {report.organization}")
    generated = report.generated_at[:19]
    print(f"  Period: Last {report.audit_period_days} days  |  Generated: {generated}")
    print(sep)

    # ── RUM Summary ──
    print(f"\n{thin}")
    print("  RESOURCES UNDER MANAGEMENT (RUM) SUMMARY")
    print(thin)
    print(f"  Total Managed Resources (RUM):  {report.total_rum:,}")
    inflator_pct = f"{report.org_inflator_pct:.0%}"
    print(f"  Known Zero-Cost Inflators:      {report.total_rum_inflators:,} ({inflator_pct})")

    # ── RUM by Provider ──
    if report.rum_by_provider:
        print("\n  RUM by Provider:")
        for prov, cnt in sorted(report.rum_by_provider.items(), key=lambda x: -x[1])[:10]:
            pct = cnt / max(report.total_rum, 1) * 100
            bar = "█" * int(pct / 3)
            print(f"    {prov:<40} {cnt:>6}  ({pct:>5.1f}%) {bar}")

    # ── RUM by Resource Type (Top 20) ──
    if report.rum_by_type_top20:
        print("\n  Top 20 Resource Types by Count:")
        for typ, cnt in report.rum_by_type_top20:
            inflator_flag = " ◆" if typ in RUM_INFLATOR_TYPES else ""
            pct = cnt / max(report.total_rum, 1) * 100
            print(f"    {typ:<45} {cnt:>5}  ({pct:>4.1f}%){inflator_flag}")
        print("    (◆ = known zero-cost inflator type)")

    # ── RUM by Project ──
    if report.rum_by_project:
        print("\n  RUM by Project:")
        for proj, cnt in sorted(report.rum_by_project.items(), key=lambda x: -x[1])[:10]:
            print(f"    {proj:<40} {cnt:>6} RUM")

    # ── Run Summary ──
    print(f"\n{thin}")
    print("  RUN CONSUMPTION SUMMARY")
    print(thin)
    print(f"  Total Workspaces:      {report.total_workspaces}")
    print(f"  Active (with runs):    {report.active_workspaces}")
    print(f"  Stale (no runs):       {report.stale_workspaces}")
    print(f"  Total Runs:            {report.total_runs:,}")
    print(f"    Applied:             {report.total_applied:,}")
    print(f"    Errored:             {report.total_errored:,}")
    print(f"    Canceled:            {report.total_canceled:,}")
    print(f"    Plan-Only:           {report.total_plan_only:,}")
    print(f"    No Changes:          {report.total_no_changes:,}")
    waste_pct = (report.estimated_wasted_runs / max(report.total_runs, 1)) * 100
    print(f"  Estimated Wasted:      {report.estimated_wasted_runs:,} ({waste_pct:.1f}%)")

    # ── Anti-Patterns ──
    if report.anti_patterns:
        print(f"\n{thin}")
        print("  ANTI-PATTERNS DETECTED")
        print(thin)
        for ap in report.anti_patterns:
            print(f"  {ap['pattern']:<35} {ap['affected_workspaces']} workspace(s)")

    # ── Top Workspaces by RUM ──
    by_rum = sorted(report.workspace_audits, key=lambda w: w.rum.total_managed, reverse=True)[:top_n]
    by_rum = [w for w in by_rum if w.rum.total_managed > 0]
    if by_rum:
        print(f"\n{thin}")
        print(f"  TOP {top_n} WORKSPACES BY RUM COUNT")
        print(thin)
        print(f"  {'Workspace':<30} {'RUM':>6} {'Inflat':>6} {'Runs':>6} {'Findings':>8}")
        for ws in by_rum:
            print(
                f"  {ws.name:<30} {ws.rum.total_managed:>6} "
                f"{ws.rum.inflator_count:>6} "
                f"{ws.run_count:>6} {len(ws.findings):>8}"
            )

    # ── Top Workspaces by Run Count ──
    by_runs = sorted(report.workspace_audits, key=lambda w: w.run_count, reverse=True)[:top_n]
    by_runs = [w for w in by_runs if w.run_count > 0]
    if by_runs:
        print(f"\n{thin}")
        print(f"  TOP {top_n} WORKSPACES BY RUN COUNT")
        print(thin)
        print(f"  {'Workspace':<30} {'Runs':>6} {'Err':>5} {'Cxl':>5} {'NoChg':>6} {'RUM':>6}")
        for ws in by_runs:
            print(
                f"  {ws.name:<30} {ws.run_count:>6} {ws.errored_count:>5} "
                f"{ws.canceled_count:>5} {ws.no_changes_count:>6} "
                f"{ws.rum.total_managed:>6}"
            )

    # ── Detailed Findings ──
    flagged = sorted(
        [w for w in report.workspace_audits if w.findings],
        key=lambda w: len(w.findings),
        reverse=True,
    )[:top_n]
    if flagged:
        print(f"\n{thin}")
        print(f"  WORKSPACE FINDINGS (TOP {top_n})")
        print(thin)
        for ws in flagged:
            print(f"\n  [{ws.name}] (project: {ws.project})")
            print(f"    RUM: {ws.rum.total_managed} | Inflators: {ws.rum.inflator_count}")
            print(
                f"    Runs: {ws.run_count} | VCS: {'yes' if ws.vcs_connected else 'no'} | "
                f"Auto-apply: {'yes' if ws.auto_apply else 'no'} | "
                f"Mode: {ws.execution_mode}"
            )
            if ws.rum.top_types:
                types_str = ", ".join(f"{t}({c})" for t, c in ws.rum.top_types[:5])
                print(f"    Top types: {types_str}")
            for f in ws.findings:
                sev = {"HIGH": "!!!", "MEDIUM": " !!", "LOW": "  !"}[f["severity"]]
                cat = f.get("category", "")
                print(f"    [{sev}] [{cat}] {f['pattern']}: {f['detail']}")

    # ── Recommendations ──
    if report.recommendations:
        print(f"\n{thin}")
        print("  RECOMMENDATIONS")
        print(thin)
        for i, rec in enumerate(report.recommendations, 1):
            print(f"\n  {i}. [{rec['priority']}] {rec['title']}")
            print(f"     Category: {rec['category']}")
            words = rec["detail"].split()
            line = "     "
            for w in words:
                if len(line) + len(w) + 1 > W:
                    print(line)
                    line = "     " + w
                else:
                    line += (" " + w) if line.strip() else w
            if line.strip():
                print(line)

    print(f"\n{sep}")
    print(f"  API requests made: {request_count}")
    print(sep)
