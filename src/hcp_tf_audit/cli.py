"""Command-line interface entry point."""

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from .analysis.org import compute_org_summary, generate_recommendations
from .analysis.rum import analyze_rum
from .analysis.runs import analyze_runs
from .client import TFCClient
from .config import RATE_LIMIT_DELAY, RETRY_MAX_ATTEMPTS, THRESHOLDS
from .models import OrgAuditReport, WorkspaceAudit
from .parsers import parse_resource, parse_run
from .reporting import print_report


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="HCP Terraform RUM & Run Usage Auditor")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Audit period in days for run analysis (default: 30)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="Number of top workspaces to show (default: 15)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of text",
    )
    parser.add_argument(
        "--org",
        type=str,
        default=None,
        help="Organization name (or set TFE_ORGANIZATION env var)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="API token (or set TFE_TOKEN env var)",
    )
    parser.add_argument(
        "--skip-resources",
        action="store_true",
        help="Skip detailed resource fetching (faster, uses count only)",
    )
    parser.add_argument(
        "--project",
        action="append",
        metavar="PROJECT",
        default=None,
        help="Filter by project name (substring match, case-insensitive; repeatable)",
    )
    parser.add_argument(
        "--workspace",
        action="append",
        metavar="WORKSPACE",
        default=None,
        help="Filter by workspace name (substring match, case-insensitive; repeatable)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=RETRY_MAX_ATTEMPTS,
        help=f"Max HTTP retry attempts (default: {RETRY_MAX_ATTEMPTS})",
    )
    parser.add_argument(
        "--rate-delay",
        type=float,
        default=RATE_LIMIT_DELAY,
        help=f"Seconds between requests (default: {RATE_LIMIT_DELAY})",
    )
    args = parser.parse_args()

    token = args.token or os.environ.get("TFE_TOKEN")
    org = args.org or os.environ.get("TFE_ORGANIZATION")

    if not token:
        print("ERROR: Set TFE_TOKEN env var or pass --token")
        sys.exit(1)
    if not org:
        print("ERROR: Set TFE_ORGANIZATION env var or pass --org")
        sys.exit(1)

    client = TFCClient(token, org, max_retries=args.max_retries, rate_limit_delay=args.rate_delay)
    since = datetime.now(UTC) - timedelta(days=args.days)
    stale_cutoff = datetime.now(UTC) - timedelta(days=THRESHOLDS["rum_stale_resource_days"])

    report = OrgAuditReport(
        organization=org,
        audit_period_days=args.days,
        generated_at=datetime.now(UTC).isoformat(),
    )

    # ── 1. Fetch all workspaces ──
    print(f"Fetching workspaces for org '{org}'...")
    workspaces = client.list_workspaces()
    print(f"  Found {len(workspaces)} workspaces.")

    # ── Resolve --project names to project IDs ──
    project_ids: set[str] | None = None
    if args.project:
        projects = client.list_projects()
        project_ids = {
            p["id"] for p in projects if any(f.lower() in p["attributes"].get("name", "").lower() for f in args.project)
        }
        print(f"  --project matched {len(project_ids)} project ID(s): {sorted(project_ids)}")

    # ── Apply filters ──
    if project_ids is not None:
        workspaces = [
            ws
            for ws in workspaces
            if (ws.get("relationships", {}).get("project", {}).get("data") or {}).get("id", "") in project_ids
        ]
        print(f"  Filtered to {len(workspaces)} workspace(s) by project.")

    if args.workspace:
        workspaces = [
            ws
            for ws in workspaces
            if any(f.lower() in ws["attributes"].get("name", "").lower() for f in args.workspace)
        ]
        print(f"  Filtered to {len(workspaces)} workspace(s) by workspace name.")

    report.total_workspaces = len(workspaces)
    print()

    # ── 2. Audit each workspace ──
    for i, ws in enumerate(workspaces, 1):
        attrs = ws["attributes"]
        ws_name = attrs.get("name", ws["id"])
        project_name = "default"
        try:
            proj_rel = ws.get("relationships", {}).get("project", {}).get("data", {})
            if proj_rel:
                project_name = proj_rel.get("id", "default")
        except Exception:
            pass

        ws_audit = WorkspaceAudit(
            id=ws["id"],
            name=ws_name,
            project=project_name,
            vcs_connected=attrs.get("vcs-repo") is not None,
            auto_apply=attrs.get("auto-apply", False),
            execution_mode=attrs.get("execution-mode", "remote"),
            terraform_version=attrs.get("terraform-version", "unknown"),
        )

        print(f"  [{i}/{len(workspaces)}] {ws_name}...", end="", flush=True)

        # ── Fetch managed resources (RUM) ──
        if args.skip_resources:
            count = client.get_workspace_resource_count(ws["id"])
            ws_audit.rum.total_managed = count
            print(f" {count} RUM", end="")
        else:
            raw_resources = client.list_workspace_resources(ws["id"])
            ws_audit.resources = [parse_resource(r) for r in raw_resources]
            analyze_rum(ws_audit, stale_cutoff)
            print(
                f" {ws_audit.rum.total_managed} RUM ({ws_audit.rum.inflator_count} inflators)",
                end="",
            )

        # ── Fetch runs ──
        raw_runs = client.list_workspace_runs(ws["id"], since)
        ws_audit.runs = [parse_run(r) for r in raw_runs]
        analyze_runs(ws_audit, args.days)
        print(f", {len(ws_audit.runs)} runs, {len(ws_audit.findings)} findings")

        report.workspace_audits.append(ws_audit)

    # ── 3. Org-level analysis ──
    compute_org_summary(report)
    generate_recommendations(report)

    # ── 4. Output ──
    if args.json:
        output = asdict(report)
        for ws in output["workspace_audits"]:
            ws.pop("runs", None)
            ws.pop("resources", None)
        print(json.dumps(output, indent=2, default=str))
    else:
        print_report(report, args.top, client.request_count)


if __name__ == "__main__":
    main()
