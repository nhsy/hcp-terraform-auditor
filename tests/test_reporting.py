"""Tests for hcp_tf_audit.reporting."""

import json
from dataclasses import asdict

from hcp_tf_audit.models import RUMBreakdown
from hcp_tf_audit.reporting import print_report
from tests.conftest import make_org_report, make_workspace


def _ws(name: str, total_managed: int = 0, run_count: int = 0, findings: list = None):
    ws = make_workspace(name=name)
    ws.rum = RUMBreakdown(total_managed=total_managed)
    ws.run_count = run_count
    ws.findings = findings or []
    return ws


class TestPrintReport:
    def test_api_requests_in_output(self, capsys):
        report = make_org_report()
        report.workspace_audits = []
        print_report(report, top_n=5, request_count=42)
        captured = capsys.readouterr()
        assert "API requests made: 42" in captured.out

    def test_organization_name_in_output(self, capsys):
        report = make_org_report(organization="my-org")
        report.workspace_audits = []
        print_report(report, top_n=5, request_count=0)
        captured = capsys.readouterr()
        assert "my-org" in captured.out

    def test_top_rum_section_rendered(self, capsys):
        report = make_org_report()
        report.workspace_audits = [
            _ws("ws-heavy", total_managed=500),
            _ws("ws-light", total_managed=10),
        ]
        print_report(report, top_n=5, request_count=0)
        captured = capsys.readouterr()
        assert "TOP 5 WORKSPACES BY RUM COUNT" in captured.out
        assert "ws-heavy" in captured.out

    def test_top_runs_section_rendered(self, capsys):
        report = make_org_report()
        report.workspace_audits = [
            _ws("ws-busy", run_count=100),
            _ws("ws-idle", run_count=0),
        ]
        print_report(report, top_n=5, request_count=0)
        captured = capsys.readouterr()
        assert "TOP 5 WORKSPACES BY RUN COUNT" in captured.out
        assert "ws-busy" in captured.out

    def test_anti_patterns_section_rendered(self, capsys):
        report = make_org_report()
        report.anti_patterns = [{"pattern": "HIGH_FAILURE_RATE", "affected_workspaces": 3}]
        report.workspace_audits = []
        print_report(report, top_n=5, request_count=0)
        captured = capsys.readouterr()
        assert "ANTI-PATTERNS DETECTED" in captured.out
        assert "HIGH_FAILURE_RATE" in captured.out

    def test_recommendations_section_rendered(self, capsys):
        report = make_org_report()
        report.recommendations = [
            {
                "priority": "HIGH",
                "category": "RUM Cost",
                "title": "Reduce RUM inflators",
                "detail": "Some detail text here.",
            }
        ]
        report.workspace_audits = []
        print_report(report, top_n=5, request_count=0)
        captured = capsys.readouterr()
        assert "RECOMMENDATIONS" in captured.out
        assert "Reduce RUM inflators" in captured.out

    def test_findings_section_rendered(self, capsys):
        report = make_org_report()
        ws = _ws(
            "flagged-ws",
            total_managed=50,
            findings=[
                {
                    "pattern": "RUM_HEAVY_WORKSPACE",
                    "severity": "HIGH",
                    "category": "RUM",
                    "detail": "Too many resources.",
                }
            ],
        )
        report.workspace_audits = [ws]
        print_report(report, top_n=5, request_count=0)
        captured = capsys.readouterr()
        assert "WORKSPACE FINDINGS" in captured.out
        assert "flagged-ws" in captured.out
        assert "RUM_HEAVY_WORKSPACE" in captured.out

    def test_empty_workspace_list_no_error(self, capsys):
        report = make_org_report()
        report.workspace_audits = []
        print_report(report, top_n=5, request_count=0)
        captured = capsys.readouterr()
        assert "HCP TERRAFORM" in captured.out

    def test_top_n_respected_for_rum_section(self, capsys):
        report = make_org_report()
        report.workspace_audits = [_ws(f"ws-{i:02d}", total_managed=100 - i) for i in range(20)]
        print_report(report, top_n=3, request_count=0)
        captured = capsys.readouterr()
        assert "TOP 3 WORKSPACES BY RUM COUNT" in captured.out


class TestReportSerialisation:
    def test_asdict_contains_expected_keys(self):
        report = make_org_report(organization="my-org", audit_period_days=30)
        output = asdict(report)
        assert "organization" in output
        assert "audit_period_days" in output
        assert "workspace_audits" in output
        assert "recommendations" in output
        assert "anti_patterns" in output
        assert "total_rum" in output
        assert "total_runs" in output

    def test_asdict_json_serialisable(self):
        report = make_org_report()
        output = asdict(report)
        json_str = json.dumps(output, default=str)
        parsed = json.loads(json_str)
        assert parsed["organization"] == "test-org"
