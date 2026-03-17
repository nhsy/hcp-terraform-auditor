"""Tests for hcp_tf_audit.models — verifies default_factory isolation."""

from hcp_tf_audit.models import OrgAuditReport, RUMBreakdown, WorkspaceAudit


class TestRUMBreakdownIsolation:
    def test_by_provider_independent(self):
        r1 = RUMBreakdown()
        r2 = RUMBreakdown()
        r1.by_provider["aws"] = 5
        assert "aws" not in r2.by_provider

    def test_by_type_independent(self):
        r1 = RUMBreakdown()
        r2 = RUMBreakdown()
        r1.by_type["aws_instance"] = 10
        assert "aws_instance" not in r2.by_type

    def test_by_module_independent(self):
        r1 = RUMBreakdown()
        r2 = RUMBreakdown()
        r1.by_module["networking"] = 3
        assert "networking" not in r2.by_module

    def test_top_types_independent(self):
        r1 = RUMBreakdown()
        r2 = RUMBreakdown()
        r1.top_types.append(("aws_instance", 5))
        assert len(r2.top_types) == 0


class TestWorkspaceAuditIsolation:
    def _make_ws(self, ws_id: str) -> WorkspaceAudit:
        return WorkspaceAudit(
            id=ws_id,
            name=f"ws-{ws_id}",
            project="default",
            vcs_connected=False,
            auto_apply=False,
            execution_mode="remote",
            terraform_version="1.5.0",
        )

    def test_findings_independent(self):
        ws1 = self._make_ws("1")
        ws2 = self._make_ws("2")
        ws1.findings.append({"pattern": "TEST"})
        assert len(ws2.findings) == 0

    def test_resources_independent(self):
        ws1 = self._make_ws("1")
        ws2 = self._make_ws("2")
        ws1.resources.append("fake-resource")
        assert len(ws2.resources) == 0

    def test_runs_independent(self):
        ws1 = self._make_ws("1")
        ws2 = self._make_ws("2")
        ws1.runs.append("fake-run")
        assert len(ws2.runs) == 0

    def test_rum_breakdown_independent(self):
        ws1 = self._make_ws("1")
        ws2 = self._make_ws("2")
        ws1.rum.total_managed = 99
        assert ws2.rum.total_managed == 0


class TestOrgAuditReportIsolation:
    def test_workspace_audits_independent(self):
        r1 = OrgAuditReport(organization="a", audit_period_days=30, generated_at="2024-01-01")
        r2 = OrgAuditReport(organization="b", audit_period_days=30, generated_at="2024-01-01")
        r1.workspace_audits.append("fake")
        assert len(r2.workspace_audits) == 0

    def test_recommendations_independent(self):
        r1 = OrgAuditReport(organization="a", audit_period_days=30, generated_at="2024-01-01")
        r2 = OrgAuditReport(organization="b", audit_period_days=30, generated_at="2024-01-01")
        r1.recommendations.append({"priority": "HIGH"})
        assert len(r2.recommendations) == 0
