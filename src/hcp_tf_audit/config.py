"""Constants for HCP Terraform audit configuration."""

BASE_URL = "https://app.terraform.io/api/v2"
PAGE_SIZE = 100
RATE_LIMIT_DELAY = 0.1  # seconds between every request (proactive throttle ~10 req/s)
RETRY_MAX_ATTEMPTS = 5  # 1 original + 4 retries
RETRY_BACKOFF_BASE = 2.0  # exponential base
RETRY_BACKOFF_FACTOR = 1.0  # multiplier: delay = factor * base^attempt
RETRY_BACKOFF_MAX = 60.0  # ceiling before jitter (seconds)
RETRY_JITTER_MAX = 2.0  # uniform random jitter range added to backoff

# Resource types that are known zero-cost control-plane objects (RUM inflators)
RUM_INFLATOR_TYPES: frozenset[str] = frozenset(
    {
        # AWS
        "aws_iam_policy",
        "aws_iam_role",
        "aws_iam_role_policy_attachment",
        "aws_iam_user",
        "aws_iam_group",
        "aws_iam_group_membership",
        "aws_iam_policy_attachment",
        "aws_iam_user_policy_attachment",
        "aws_iam_instance_profile",
        "aws_security_group_rule",
        "aws_route",
        "aws_route_table_association",
        "aws_subnet",
        "aws_s3_bucket_policy",
        "aws_s3_bucket_versioning",
        "aws_s3_bucket_server_side_encryption_configuration",
        "aws_s3_bucket_lifecycle_configuration",
        "aws_s3_bucket_public_access_block",
        "aws_s3_bucket_acl",
        "aws_s3_bucket_cors_configuration",
        "aws_cloudwatch_log_group",
        "aws_sns_topic_subscription",
        "aws_lambda_permission",
        "aws_route53_record",
        # Azure
        "azurerm_role_assignment",
        "azurerm_role_definition",
        "azurerm_management_lock",
        "azurerm_monitor_diagnostic_setting",
        "azurerm_subnet",
        "azurerm_subnet_network_security_group_association",
        "azurerm_dns_a_record",
        "azurerm_dns_cname_record",
        "azurerm_private_dns_a_record",
        "azurerm_network_security_rule",
        # GCP
        "google_project_iam_member",
        "google_project_iam_binding",
        "google_project_iam_policy",
        "google_service_account",
        "google_dns_record_set",
        "google_compute_firewall",
        # General / helpers
        "random_id",
        "random_string",
        "random_password",
        "random_pet",
        "random_integer",
        "random_uuid",
        "random_shuffle",
        "local_file",
        "local_sensitive_file",
        "time_sleep",
        "time_rotating",
        "time_static",
        "tls_private_key",
        "tls_self_signed_cert",
        "tls_cert_request",
    }
)

# ─── Anti-Pattern Thresholds ─────────────────────────────────────────────────

THRESHOLDS: dict[str, float | int] = {
    # RUM-specific
    "rum_heavy_workspace": 200,  # workspace with 200+ managed resources
    "rum_inflator_ratio": 0.50,  # >50% of resources are zero-cost inflators
    "rum_stale_resource_days": 90,  # resources unchanged for 90+ days
    "rum_growth_rate_pct_month": 25,  # >25% RUM growth month-over-month
    "rum_concentration_pct": 0.30,  # single workspace holds >30% of total RUM
    # Run-specific
    "high_failure_rate": 0.30,
    "high_cancel_rate": 0.25,
    "excessive_daily_runs": 20,
    "speculative_plan_ratio": 0.70,
    "rapid_fire_interval_min": 5,
    "rapid_fire_count": 5,
    "stale_workspace_days": 90,
    "long_plan_duration_min": 30,
    "no_apply_ratio": 0.50,
    "no_change_churn_ratio": 0.50,
}
