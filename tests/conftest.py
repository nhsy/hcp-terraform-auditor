"""Shared test fixtures."""

from hcp_tf_audit.models import ManagedResource, OrgAuditReport, RunRecord, WorkspaceAudit


def make_workspace(
    ws_id: str = "ws-001",
    name: str = "test-workspace",
    project: str = "default",
    vcs_connected: bool = False,
    auto_apply: bool = False,
    execution_mode: str = "remote",
    terraform_version: str = "1.5.0",
) -> WorkspaceAudit:
    return WorkspaceAudit(
        id=ws_id,
        name=name,
        project=project,
        vcs_connected=vcs_connected,
        auto_apply=auto_apply,
        execution_mode=execution_mode,
        terraform_version=terraform_version,
    )


def make_run(
    run_id: str = "run-001",
    status: str = "applied",
    source: str = "tfe-ui",
    operation: str = "plan_and_apply",
    created_at: str = "2024-01-01T00:00:00Z",
    plan_duration: float | None = None,
    apply_duration: float | None = None,
    has_changes: bool = True,
    is_destroy: bool = False,
    trigger_reason: str = "",
) -> RunRecord:
    return RunRecord(
        id=run_id,
        status=status,
        source=source,
        operation=operation,
        created_at=created_at,
        plan_duration=plan_duration,
        apply_duration=apply_duration,
        has_changes=has_changes,
        is_destroy=is_destroy,
        trigger_reason=trigger_reason,
    )


def make_resource(
    address: str = "aws_instance.web",
    provider_type: str = "aws_instance",
    provider: str = "registry.terraform.io/hashicorp/aws",
    module: str = "root",
    updated_at: str = "2024-01-01",
) -> ManagedResource:
    return ManagedResource(
        address=address,
        provider_type=provider_type,
        provider=provider,
        module=module,
        updated_at=updated_at,
    )


def make_org_report(
    organization: str = "test-org",
    audit_period_days: int = 30,
    generated_at: str = "2024-03-01T00:00:00+00:00",
) -> OrgAuditReport:
    return OrgAuditReport(
        organization=organization,
        audit_period_days=audit_period_days,
        generated_at=generated_at,
    )
