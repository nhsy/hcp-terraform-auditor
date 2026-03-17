"""Dataclasses for HCP Terraform audit data models."""

from dataclasses import dataclass, field


@dataclass
class ManagedResource:
    address: str
    provider_type: str
    provider: str
    module: str
    updated_at: str


@dataclass
class RunRecord:
    id: str
    status: str
    source: str
    operation: str
    created_at: str
    plan_duration: float | None = None
    apply_duration: float | None = None
    has_changes: bool = False
    is_destroy: bool = False
    trigger_reason: str = ""


@dataclass
class RUMBreakdown:
    total_managed: int = 0
    inflator_count: int = 0
    inflator_pct: float = 0.0
    by_provider: dict = field(default_factory=dict)
    by_type: dict = field(default_factory=dict)
    by_module: dict = field(default_factory=dict)
    top_types: list = field(default_factory=list)
    stale_resources: int = 0


@dataclass
class WorkspaceAudit:
    id: str
    name: str
    project: str
    vcs_connected: bool
    auto_apply: bool
    execution_mode: str
    terraform_version: str
    # RUM data
    rum: RUMBreakdown = field(default_factory=RUMBreakdown)
    resources: list = field(default_factory=list)
    # Run data
    runs: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    run_count: int = 0
    errored_count: int = 0
    canceled_count: int = 0
    applied_count: int = 0
    plan_only_count: int = 0
    discarded_count: int = 0
    no_changes_count: int = 0
    destroy_count: int = 0
    avg_daily_runs: float = 0.0
    rapid_fire_sequences: int = 0


@dataclass
class OrgAuditReport:
    organization: str
    audit_period_days: int
    generated_at: str
    # RUM summary
    total_rum: int = 0
    total_rum_inflators: int = 0
    org_inflator_pct: float = 0.0
    rum_by_project: dict = field(default_factory=dict)
    rum_by_provider: dict = field(default_factory=dict)
    rum_by_type_top20: list = field(default_factory=list)
    # Workspace summary
    total_workspaces: int = 0
    active_workspaces: int = 0
    stale_workspaces: int = 0
    # Run summary
    total_runs: int = 0
    total_errored: int = 0
    total_canceled: int = 0
    total_applied: int = 0
    total_plan_only: int = 0
    total_no_changes: int = 0
    estimated_wasted_runs: int = 0
    # Analysis
    workspace_audits: list = field(default_factory=list)
    anti_patterns: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
