# hcp-terraform-auditor

A CLI tool that audits HCP Terraform organizations for resource usage under management (RUM) cost drivers and operational anti-patterns. It fetches workspace data via the Terraform Cloud API and produces a detailed text or JSON report with findings and prioritized recommendations.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [Task](https://taskfile.dev/)

## Installation

```bash
task install
```

## Configuration

Set the following environment variables, or pass them as CLI flags:

| Variable            | Flag      | Description                      |
|---------------------|-----------|----------------------------------|
| `TFE_TOKEN`         | `--token` | HCP Terraform API token          |
| `TFE_ORGANIZATION`  | `--org`   | HCP Terraform organization name  |

Copy `.env.example` to `.env` and populate the values — the `.env` file is loaded automatically by Taskfile.

### Token Permissions

The tool is read-only. Use a **team token** scoped to a team with the following minimum permissions on the target organization:

| Permission | Required access | Reason |
|---|---|---|
| Workspaces | Read | List workspaces and their attributes |
| Projects | Read | Resolve `--project` filter names to IDs |
| Runs | Read | Fetch run history per workspace |
| State versions | Read | Fetch state version metadata per workspace |
| Managed resources | Read | Fetch RUM counts and resource details |

A **user token** or **organization token** will also work but grants broader access than necessary. For least privilege, create a dedicated team with read-only access to the organization and generate a team token for that team.

> The tool never writes, applies, or modifies any Terraform state or configuration.

## Usage

```bash
# Run with default options (30-day window, top 15 workspaces)
task run

# Pass additional arguments using -- (Task v3)
task run -- --days 60 --top 20

# Or using the CLI_ARGS variable (alternative syntax)
task run CLI_ARGS="--days 60 --top 20"

# Output as JSON
task run -- --json

# Faster scan: skip per-resource details, use counts only
task run -- --skip-resources

# Tune rate limiting for large organizations
task run -- --rate-delay 0.5 --max-retries 10

# Audit workspaces in a named project (pass the project name, not the ID)
task run -- --project "platform"

# Audit workspaces whose name contains "prod"
task run -- --workspace prod

# Combine: only "prod" workspaces inside a specific project
task run -- --project platform --workspace prod

# Multiple values within a flag are OR'd
task run -- --workspace prod --workspace staging
```

> Note: `--project` accepts the human-readable project **name** (e.g. `platform`), not the internal project ID (e.g. `prj-abc123`). The tool resolves the name to an ID automatically via the projects API.

Or invoke the CLI directly:

```bash
hcp-audit --org my-org --token <token> --days 30 --top 15 --json
```

### CLI Options

| Option             | Default               | Description                                            |
|--------------------|-----------------------|--------------------------------------------------------|
| `--days`           | `30`                  | Audit period in days for run analysis                  |
| `--top`            | `15`                  | Number of top workspaces to display                    |
| `--json`           | `false`               | Output as JSON instead of formatted text               |
| `--org`            | `$TFE_ORGANIZATION`   | Organization name                                      |
| `--token`          | `$TFE_TOKEN`          | API token                                              |
| `--skip-resources` | `false`               | Use resource count only; skip full resource fetch      |
| `--max-retries`    | `5`                   | Max HTTP retry attempts before giving up               |
| `--rate-delay`     | `0.1`                 | Seconds between each request (proactive throttle)      |
| `--project`        | _(all)_               | Filter by project **name** substring (not project ID; repeatable) |
| `--workspace`      | _(all)_               | Filter by workspace **name** substring (repeatable)    |

### Rate Limiting

The client applies a proactive per-request delay (default 0.1s, ~10 req/s) and retries on 429 and 5xx responses using exponential backoff with jitter. Default delays per retry attempt are approximately 2s, 4s, 8s, 16s before giving up. A `Retry-After` header from the server always overrides the computed backoff.

For large organizations that trigger rate limiting, increase `--rate-delay` (e.g. `--rate-delay 0.5`) to reduce throughput, or increase `--max-retries` to allow more recovery attempts.

## Report Contents

The text report includes:

- **RUM Summary** — total managed resources and inflator count
- **RUM by Provider / Type / Project** — distribution with percentages
- **Run Summary** — total runs, statuses, wasted run counts
- **Anti-Patterns Detected** — table of detected patterns with affected workspace counts
- **Top Workspaces by RUM / Run Count** — detailed per-workspace metrics
- **Findings** — per-workspace findings with severity indicators
- **Recommendations** — prioritized (HIGH / MEDIUM / LOW) actionable recommendations

## Development

```bash
task test          # Run test suite
task test:cov      # Run tests with coverage report
task lint          # Lint and format check
task lint:fix      # Auto-fix lint issues
task check         # Run lint + test together
```
