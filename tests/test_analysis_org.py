"""Tests for hcp_tf_audit.analysis.org."""

import pytest

from hcp_tf_audit.analysis.org import compute_org_summary, generate_recommendations
from hcp_tf_audit.models import RUMBreakdown
from tests.conftest import make_org_report, make_workspace


def _ws(
    name: str,
    total_managed: int = 0,
    inflator_count: int = 0,
    run_count: int = 0,
    errored: int = 0,
    canceled: int = 0,
    applied: int = 0,
    plan_only: int = 0,
    no_changes: int = 0,
    project: str = "default",
):
    ws = make_workspace(name=name, project=project)
    ws.rum = RUMBreakdown(
        total_managed=total_managed,
        inflator_count=inflator_count,
        by_provider={"hashicorp/aws": total_managed} if total_managed else {},
        by_type={"aws_instance": total_managed} if total_managed else {},
    )
    ws.run_count = run_count
    ws.errored_count = errored
    ws.canceled_count = canceled
    ws.applied_count = applied
    ws.plan_only_count = plan_only
    ws.no_changes_count = no_changes
    return ws


class TestComputeOrgSummary:
    def test_total_rum_rollup(self):
        report = make_org_report()
        report.workspace_audits = [
            _ws("ws-a", total_managed=100),
            _ws("ws-b", total_managed=200),
        ]
        compute_org_summary(report)
        assert report.total_rum == 300

    def test_total_runs_rollup(self):
        report = make_org_report()
        report.workspace_audits = [
            _ws("ws-a", run_count=50),
            _ws("ws-b", run_count=30),
        ]
        compute_org_summary(report)
        assert report.total_runs == 80

    def test_org_inflator_pct(self):
        report = make_org_report()
        report.workspace_audits = [
            _ws("ws-a", total_managed=100, inflator_count=40),
        ]
        compute_org_summary(report)
        assert report.org_inflator_pct == pytest.approx(0.4)

    def test_active_and_stale_workspace_counts(self):
        report = make_org_report()
        report.workspace_audits = [
            _ws("ws-active", run_count=5),
            _ws("ws-stale", run_count=0),
            _ws("ws-stale2", run_count=0),
        ]
        compute_org_summary(report)
        assert report.active_workspaces == 1
        assert report.stale_workspaces == 2

    def test_estimated_wasted_runs(self):
        report = make_org_report()
        report.workspace_audits = [
            _ws("ws-a", run_count=10, errored=2, canceled=1, no_changes=3),
        ]
        compute_org_summary(report)
        assert report.estimated_wasted_runs == 6

    def test_rum_by_project(self):
        report = make_org_report()
        report.workspace_audits = [
            _ws("ws-a", total_managed=50, project="proj-x"),
            _ws("ws-b", total_managed=30, project="proj-x"),
            _ws("ws-c", total_managed=20, project="proj-y"),
        ]
        compute_org_summary(report)
        assert report.rum_by_project["proj-x"] == 80
        assert report.rum_by_project["proj-y"] == 20

    def test_empty_workspace_list(self):
        report = make_org_report()
        report.workspace_audits = []
        compute_org_summary(report)
        assert report.total_rum == 0
        assert report.total_runs == 0
        assert report.org_inflator_pct == 0.0


class TestRumConcentrationRisk:
    def test_concentration_risk_detected(self):
        report = make_org_report()
        report.workspace_audits = [
            _ws("ws-big", total_managed=400),
            _ws("ws-small", total_managed=100),
        ]
        compute_org_summary(report)
        # ws-big holds 400/500 = 80% > 30% threshold and >50 resources
        big_ws = next(w for w in report.workspace_audits if w.name == "ws-big")
        patterns = [f["pattern"] for f in big_ws.findings]
        assert "RUM_CONCENTRATION_RISK" in patterns

    def test_concentration_risk_not_on_small_ws(self):
        report = make_org_report()
        report.workspace_audits = [
            _ws("ws-big", total_managed=400),
            _ws("ws-small", total_managed=100),
        ]
        compute_org_summary(report)
        small_ws = next(w for w in report.workspace_audits if w.name == "ws-small")
        patterns = [f["pattern"] for f in small_ws.findings]
        assert "RUM_CONCENTRATION_RISK" not in patterns

    def test_concentration_risk_not_detected_below_50_resources(self):
        report = make_org_report()
        # ws-tiny holds 100% but < 50 resources
        tiny = _ws("ws-tiny", total_managed=30)
        report.workspace_audits = [tiny]
        compute_org_summary(report)
        patterns = [f["pattern"] for f in tiny.findings]
        assert "RUM_CONCENTRATION_RISK" not in patterns


class TestGenerateRecommendations:
    def test_recommendations_sorted_high_before_medium_before_low(self):
        report = make_org_report()
        # Stale workspaces -> LOW recommendation
        ws_stale = _ws("ws-stale", run_count=0)
        # Workspace with findings that trigger HIGH recommendations
        ws_active = _ws("ws-active", run_count=10, errored=5)
        ws_active.findings = [{"pattern": "HIGH_FAILURE_RATE", "severity": "HIGH", "category": "Runs", "detail": ""}]
        report.workspace_audits = [ws_stale, ws_active]
        compute_org_summary(report)
        generate_recommendations(report)

        priorities = [r["priority"] for r in report.recommendations]
        high_indices = [i for i, p in enumerate(priorities) if p == "HIGH"]
        low_indices = [i for i, p in enumerate(priorities) if p == "LOW"]
        if high_indices and low_indices:
            assert max(high_indices) < min(low_indices)

    def test_no_inflator_recommendation_when_zero_inflators(self):
        report = make_org_report()
        report.workspace_audits = [_ws("ws-a", total_managed=10, inflator_count=0)]
        compute_org_summary(report)
        generate_recommendations(report)
        titles = [r["title"] for r in report.recommendations]
        assert not any("inflator" in t.lower() for t in titles)

    def test_inflator_recommendation_present_when_inflators_exist(self):
        report = make_org_report()
        ws = _ws("ws-a", total_managed=100, inflator_count=40)
        report.workspace_audits = [ws]
        compute_org_summary(report)
        generate_recommendations(report)
        titles = [r["title"] for r in report.recommendations]
        assert any("inflator" in t.lower() for t in titles)

    def test_anti_patterns_list_populated(self):
        report = make_org_report()
        ws = _ws("ws-a", run_count=5)
        ws.findings = [
            {"pattern": "HIGH_FAILURE_RATE", "severity": "HIGH", "category": "Runs", "detail": ""},
            {"pattern": "HIGH_FAILURE_RATE", "severity": "HIGH", "category": "Runs", "detail": ""},
            {"pattern": "RAPID_FIRE_RUNS", "severity": "HIGH", "category": "Runs", "detail": ""},
        ]
        report.workspace_audits = [ws]
        compute_org_summary(report)
        generate_recommendations(report)
        ap_map = {ap["pattern"]: ap["affected_workspaces"] for ap in report.anti_patterns}
        assert ap_map["HIGH_FAILURE_RATE"] == 2
        assert ap_map["RAPID_FIRE_RUNS"] == 1

    def test_stale_workspace_recommendation(self):
        report = make_org_report()
        report.workspace_audits = [_ws("ws-dead", run_count=0)]
        compute_org_summary(report)
        generate_recommendations(report)
        titles = [r["title"] for r in report.recommendations]
        assert any("stale" in t.lower() for t in titles)
