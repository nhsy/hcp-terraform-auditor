"""Tests for hcp_tf_audit.analysis.rum."""

from datetime import UTC, datetime, timedelta

import pytest

from hcp_tf_audit.analysis.rum import analyze_rum
from tests.conftest import make_resource, make_workspace

_NOW = datetime(2026, 3, 17, tzinfo=UTC)
_STALE_CUTOFF = _NOW - timedelta(days=90)
_OLD_DATE = (_NOW - timedelta(days=120)).strftime("%Y-%m-%d")
_RECENT_DATE = (_NOW - timedelta(days=10)).strftime("%Y-%m-%d")


def _ws_with_resources(resources: list):
    ws = make_workspace()
    ws.resources = resources
    return ws


class TestAnalyzeRumEmpty:
    def test_empty_resources_early_return(self):
        ws = _ws_with_resources([])
        analyze_rum(ws, _STALE_CUTOFF)
        assert ws.rum.total_managed == 0
        assert ws.findings == []


class TestAnalyzeRumBreakdown:
    def test_provider_breakdown(self):
        resources = [
            make_resource(provider="hashicorp/aws"),
            make_resource(provider="hashicorp/aws"),
            make_resource(provider="hashicorp/azurerm"),
        ]
        ws = _ws_with_resources(resources)
        analyze_rum(ws, _STALE_CUTOFF)
        assert ws.rum.by_provider["hashicorp/aws"] == 2
        assert ws.rum.by_provider["hashicorp/azurerm"] == 1

    def test_type_breakdown(self):
        resources = [
            make_resource(provider_type="aws_instance"),
            make_resource(provider_type="aws_instance"),
            make_resource(provider_type="aws_s3_bucket"),
        ]
        ws = _ws_with_resources(resources)
        analyze_rum(ws, _STALE_CUTOFF)
        assert ws.rum.by_type["aws_instance"] == 2
        assert ws.rum.by_type["aws_s3_bucket"] == 1


class TestRumHeavyWorkspace:
    def test_rum_heavy_workspace_detected(self):
        resources = [make_resource(provider_type="aws_instance", address=f"aws_instance.web[{i}]") for i in range(200)]
        ws = _ws_with_resources(resources)
        analyze_rum(ws, _STALE_CUTOFF)
        patterns = [f["pattern"] for f in ws.findings]
        assert "RUM_HEAVY_WORKSPACE" in patterns

    def test_rum_heavy_workspace_not_detected_below_threshold(self):
        resources = [make_resource() for _ in range(199)]
        ws = _ws_with_resources(resources)
        analyze_rum(ws, _STALE_CUTOFF)
        patterns = [f["pattern"] for f in ws.findings]
        assert "RUM_HEAVY_WORKSPACE" not in patterns

    def test_rum_heavy_workspace_severity_is_high(self):
        resources = [make_resource(address=f"aws_instance.web[{i}]") for i in range(200)]
        ws = _ws_with_resources(resources)
        analyze_rum(ws, _STALE_CUTOFF)
        finding = next(f for f in ws.findings if f["pattern"] == "RUM_HEAVY_WORKSPACE")
        assert finding["severity"] == "HIGH"


class TestRumInflatorHeavy:
    def test_inflator_heavy_detected(self):
        # 20+ resources, >50% are inflators
        inflators = [make_resource(provider_type="aws_iam_policy", address=f"aws_iam_policy.p[{i}]") for i in range(15)]
        non_inflators = [make_resource(provider_type="aws_instance", address=f"aws_instance.w[{i}]") for i in range(5)]
        ws = _ws_with_resources(inflators + non_inflators)
        analyze_rum(ws, _STALE_CUTOFF)
        patterns = [f["pattern"] for f in ws.findings]
        assert "RUM_INFLATOR_HEAVY" in patterns

    def test_inflator_heavy_not_detected_below_count_threshold(self):
        # Only 10 resources (< 20 minimum), even if all are inflators
        inflators = [make_resource(provider_type="aws_iam_policy", address=f"p[{i}]") for i in range(10)]
        ws = _ws_with_resources(inflators)
        analyze_rum(ws, _STALE_CUTOFF)
        patterns = [f["pattern"] for f in ws.findings]
        assert "RUM_INFLATOR_HEAVY" not in patterns

    def test_inflator_pct_populated(self):
        inflators = [make_resource(provider_type="aws_iam_policy", address=f"p[{i}]") for i in range(20)]
        ws = _ws_with_resources(inflators)
        analyze_rum(ws, _STALE_CUTOFF)
        assert ws.rum.inflator_count == 20
        assert ws.rum.inflator_pct == pytest.approx(1.0)


class TestRumStaleResources:
    def test_stale_resources_detected(self):
        # 12 resources: 7 old (>50%), 5 recent — meets threshold
        stale = [make_resource(address=f"old[{i}]", updated_at=_OLD_DATE) for i in range(7)]
        fresh = [make_resource(address=f"new[{i}]", updated_at=_RECENT_DATE) for i in range(3)]
        ws = _ws_with_resources(stale + fresh)
        analyze_rum(ws, _STALE_CUTOFF)
        patterns = [f["pattern"] for f in ws.findings]
        assert "RUM_STALE_RESOURCES" in patterns

    def test_stale_resources_not_detected_below_count_threshold(self):
        # Fewer than 10 resources total
        stale = [make_resource(address=f"old[{i}]", updated_at=_OLD_DATE) for i in range(6)]
        ws = _ws_with_resources(stale)
        analyze_rum(ws, _STALE_CUTOFF)
        patterns = [f["pattern"] for f in ws.findings]
        assert "RUM_STALE_RESOURCES" not in patterns

    def test_stale_resources_not_detected_below_pct_threshold(self):
        # 10 resources: only 2 old (20%), not >50%
        stale = [make_resource(address=f"old[{i}]", updated_at=_OLD_DATE) for i in range(2)]
        fresh = [make_resource(address=f"new[{i}]", updated_at=_RECENT_DATE) for i in range(8)]
        ws = _ws_with_resources(stale + fresh)
        analyze_rum(ws, _STALE_CUTOFF)
        patterns = [f["pattern"] for f in ws.findings]
        assert "RUM_STALE_RESOURCES" not in patterns

    def test_stale_resources_severity_is_medium(self):
        stale = [make_resource(address=f"old[{i}]", updated_at=_OLD_DATE) for i in range(7)]
        fresh = [make_resource(address=f"new[{i}]", updated_at=_RECENT_DATE) for i in range(3)]
        ws = _ws_with_resources(stale + fresh)
        analyze_rum(ws, _STALE_CUTOFF)
        finding = next(f for f in ws.findings if f["pattern"] == "RUM_STALE_RESOURCES")
        assert finding["severity"] == "MEDIUM"


class TestRumModuleSprawl:
    def test_module_sprawl_detected(self):
        # >10 distinct modules, >50 resources
        resources = [
            make_resource(
                address=f"aws_instance.web[{i}]",
                module=f"module.svc{i % 12}",
            )
            for i in range(60)
        ]
        ws = _ws_with_resources(resources)
        analyze_rum(ws, _STALE_CUTOFF)
        patterns = [f["pattern"] for f in ws.findings]
        assert "RUM_MODULE_SPRAWL" in patterns

    def test_module_sprawl_not_detected_few_modules(self):
        # Only 3 modules
        resources = [make_resource(address=f"aws_instance.web[{i}]", module=f"module.svc{i % 3}") for i in range(60)]
        ws = _ws_with_resources(resources)
        analyze_rum(ws, _STALE_CUTOFF)
        patterns = [f["pattern"] for f in ws.findings]
        assert "RUM_MODULE_SPRAWL" not in patterns

    def test_module_sprawl_severity_is_low(self):
        resources = [
            make_resource(
                address=f"aws_instance.web[{i}]",
                module=f"module.svc{i % 12}",
            )
            for i in range(60)
        ]
        ws = _ws_with_resources(resources)
        analyze_rum(ws, _STALE_CUTOFF)
        finding = next(f for f in ws.findings if f["pattern"] == "RUM_MODULE_SPRAWL")
        assert finding["severity"] == "LOW"
