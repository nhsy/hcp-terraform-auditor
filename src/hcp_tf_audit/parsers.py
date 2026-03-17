"""Parsing functions for HCP Terraform API responses."""

from datetime import datetime

from .models import ManagedResource, RunRecord


def parse_resource(res_data: dict) -> ManagedResource:
    attrs = res_data.get("attributes", {})
    return ManagedResource(
        address=attrs.get("address", "unknown"),
        provider_type=attrs.get("provider-type", "unknown"),
        provider=attrs.get("provider", "unknown"),
        module=attrs.get("module", "root"),
        updated_at=attrs.get("updated-at", ""),
    )


def parse_run(run_data: dict) -> RunRecord:
    attrs = run_data["attributes"]
    ts = attrs.get("status-timestamps", {}) or {}

    plan_dur = None
    if ts.get("planning-at") and ts.get("planned-at"):
        try:
            t1 = datetime.fromisoformat(ts["planning-at"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(ts["planned-at"].replace("Z", "+00:00"))
            plan_dur = (t2 - t1).total_seconds() / 60.0
        except (ValueError, TypeError):
            pass

    apply_dur = None
    if ts.get("applying-at") and ts.get("applied-at"):
        try:
            t1 = datetime.fromisoformat(ts["applying-at"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(ts["applied-at"].replace("Z", "+00:00"))
            apply_dur = (t2 - t1).total_seconds() / 60.0
        except (ValueError, TypeError):
            pass

    return RunRecord(
        id=run_data["id"],
        status=attrs.get("status", "unknown"),
        source=attrs.get("source", "unknown"),
        operation=attrs.get("terraform-operation", "plan_and_apply"),
        created_at=attrs.get("created-at", ""),
        plan_duration=plan_dur,
        apply_duration=apply_dur,
        has_changes=attrs.get("has-changes", False),
        is_destroy=attrs.get("is-destroy", False),
        trigger_reason=attrs.get("trigger-reason", ""),
    )
