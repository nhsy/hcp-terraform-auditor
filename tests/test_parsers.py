"""Tests for hcp_tf_audit.parsers."""

import pytest

from hcp_tf_audit.models import ManagedResource
from hcp_tf_audit.parsers import parse_resource, parse_run


class TestParseResource:
    @pytest.mark.parametrize(
        "attrs, expected",
        [
            (
                {
                    "address": "aws_instance.web",
                    "provider-type": "aws_instance",
                    "provider": "registry.terraform.io/hashicorp/aws",
                    "module": "module.compute",
                    "updated-at": "2024-01-15",
                },
                ManagedResource(
                    address="aws_instance.web",
                    provider_type="aws_instance",
                    provider="registry.terraform.io/hashicorp/aws",
                    module="module.compute",
                    updated_at="2024-01-15",
                ),
            ),
            (
                {},
                ManagedResource(
                    address="unknown",
                    provider_type="unknown",
                    provider="unknown",
                    module="root",
                    updated_at="",
                ),
            ),
            (
                {"address": "null_resource.wait", "provider-type": "null_resource"},
                ManagedResource(
                    address="null_resource.wait",
                    provider_type="null_resource",
                    provider="unknown",
                    module="root",
                    updated_at="",
                ),
            ),
        ],
    )
    def test_parse_resource_parametrized(self, attrs, expected):
        result = parse_resource({"attributes": attrs})
        assert result == expected

    def test_parse_resource_empty_data(self):
        result = parse_resource({})
        assert result.address == "unknown"
        assert result.provider_type == "unknown"
        assert result.module == "root"
        assert result.updated_at == ""


class TestParseRun:
    def _run_data(self, attrs: dict) -> dict:
        return {"id": "run-abc123", "attributes": attrs}

    def test_parse_run_standard(self):
        data = self._run_data(
            {
                "status": "applied",
                "source": "tfe-vcs",
                "terraform-operation": "plan_and_apply",
                "created-at": "2024-01-15T10:00:00Z",
                "has-changes": True,
                "is-destroy": False,
                "trigger-reason": "vcs",
                "status-timestamps": {},
            }
        )
        result = parse_run(data)
        assert result.id == "run-abc123"
        assert result.status == "applied"
        assert result.source == "tfe-vcs"
        assert result.operation == "plan_and_apply"
        assert result.created_at == "2024-01-15T10:00:00Z"
        assert result.has_changes is True
        assert result.is_destroy is False
        assert result.plan_duration is None
        assert result.apply_duration is None

    def test_parse_run_defaults(self):
        data = self._run_data({})
        result = parse_run(data)
        assert result.status == "unknown"
        assert result.source == "unknown"
        assert result.operation == "plan_and_apply"
        assert result.has_changes is False
        assert result.is_destroy is False
        assert result.trigger_reason == ""

    def test_parse_run_plan_duration_calculated(self):
        data = self._run_data(
            {
                "status": "planned",
                "source": "tfe-ui",
                "terraform-operation": "plan_only",
                "created-at": "2024-01-15T10:00:00Z",
                "status-timestamps": {
                    "planning-at": "2024-01-15T10:00:00Z",
                    "planned-at": "2024-01-15T10:35:00Z",
                },
            }
        )
        result = parse_run(data)
        assert result.plan_duration == pytest.approx(35.0)

    def test_parse_run_apply_duration_calculated(self):
        data = self._run_data(
            {
                "status": "applied",
                "source": "tfe-ui",
                "terraform-operation": "plan_and_apply",
                "created-at": "2024-01-15T10:00:00Z",
                "status-timestamps": {
                    "applying-at": "2024-01-15T10:05:00Z",
                    "applied-at": "2024-01-15T10:10:00Z",
                },
            }
        )
        result = parse_run(data)
        assert result.apply_duration == pytest.approx(5.0)

    def test_parse_run_missing_timestamps_no_duration(self):
        data = self._run_data(
            {
                "status": "applied",
                "source": "tfe-ui",
                "terraform-operation": "plan_and_apply",
                "created-at": "2024-01-15T10:00:00Z",
                "status-timestamps": {
                    "planning-at": "2024-01-15T10:00:00Z",
                    # "planned-at" missing
                },
            }
        )
        result = parse_run(data)
        assert result.plan_duration is None

    def test_parse_run_null_status_timestamps(self):
        data = self._run_data(
            {
                "status": "applied",
                "source": "tfe-ui",
                "terraform-operation": "plan_and_apply",
                "created-at": "2024-01-15T10:00:00Z",
                "status-timestamps": None,
            }
        )
        result = parse_run(data)
        assert result.plan_duration is None
        assert result.apply_duration is None

    def test_parse_run_invalid_timestamp_no_duration(self):
        data = self._run_data(
            {
                "status": "applied",
                "source": "tfe-ui",
                "terraform-operation": "plan_and_apply",
                "created-at": "2024-01-15T10:00:00Z",
                "status-timestamps": {
                    "planning-at": "not-a-date",
                    "planned-at": "also-not-a-date",
                },
            }
        )
        result = parse_run(data)
        assert result.plan_duration is None
