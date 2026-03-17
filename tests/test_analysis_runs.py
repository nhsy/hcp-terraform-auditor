"""Tests for hcp_tf_audit.analysis.runs."""

import pytest

from hcp_tf_audit.analysis.runs import analyze_runs, detect_rapid_fire
from tests.conftest import make_run, make_workspace


def _runs_at(*timestamps: str) -> list:
    return [make_run(run_id=f"run-{i}", created_at=ts) for i, ts in enumerate(timestamps)]


class TestDetectRapidFire:
    @pytest.mark.parametrize(
        "timestamps, expected_sequences",
        [
            # Empty list
            ([], 0),
            # Single run — no pair to compare
            (["2024-01-01T00:00:00Z"], 0),
            # 4 runs 1 min apart — streak=4, below threshold of 5
            (
                [
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:01:00Z",
                    "2024-01-01T00:02:00Z",
                    "2024-01-01T00:03:00Z",
                ],
                0,
            ),
            # Exactly 5 runs 1 min apart — streak=5, meets threshold
            (
                [
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:01:00Z",
                    "2024-01-01T00:02:00Z",
                    "2024-01-01T00:03:00Z",
                    "2024-01-01T00:04:00Z",
                ],
                1,
            ),
            # Two groups of 5 separated by >5 min gap
            (
                [
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:01:00Z",
                    "2024-01-01T00:02:00Z",
                    "2024-01-01T00:03:00Z",
                    "2024-01-01T00:04:00Z",
                    "2024-01-01T01:00:00Z",
                    "2024-01-01T01:01:00Z",
                    "2024-01-01T01:02:00Z",
                    "2024-01-01T01:03:00Z",
                    "2024-01-01T01:04:00Z",
                ],
                2,
            ),
            # Spread-out runs — all >5 min apart
            (
                [
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:10:00Z",
                    "2024-01-01T00:20:00Z",
                    "2024-01-01T00:30:00Z",
                    "2024-01-01T00:40:00Z",
                    "2024-01-01T00:50:00Z",
                ],
                0,
            ),
            # Runs exactly at threshold boundary (5 min apart) — still counts as rapid fire
            (
                [
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:05:00Z",
                    "2024-01-01T00:10:00Z",
                    "2024-01-01T00:15:00Z",
                    "2024-01-01T00:20:00Z",
                ],
                1,
            ),
        ],
    )
    def test_detect_rapid_fire(self, timestamps, expected_sequences):
        runs = _runs_at(*timestamps)
        assert detect_rapid_fire(runs) == expected_sequences


class TestAnalyzeRuns:
    def _ws_with_runs(self, runs: list) -> object:
        ws = make_workspace()
        ws.runs = runs
        return ws

    def test_empty_runs_no_findings(self):
        ws = self._ws_with_runs([])
        analyze_runs(ws, audit_days=30)
        assert ws.run_count == 0
        assert ws.findings == []

    def test_high_failure_rate_detected(self):
        runs = [make_run(run_id=f"e{i}", status="errored") for i in range(3)] + [
            make_run(run_id=f"a{i}", status="applied") for i in range(2)
        ]
        ws = self._ws_with_runs(runs)
        analyze_runs(ws, audit_days=30)
        patterns = [f["pattern"] for f in ws.findings]
        assert "HIGH_FAILURE_RATE" in patterns

    def test_high_cancel_rate_detected(self):
        runs = [make_run(run_id=f"c{i}", status="canceled") for i in range(3)] + [
            make_run(run_id=f"a{i}", status="applied") for i in range(7)
        ]
        ws = self._ws_with_runs(runs)
        analyze_runs(ws, audit_days=30)
        patterns = [f["pattern"] for f in ws.findings]
        assert "HIGH_CANCEL_RATE" in patterns

    def test_excessive_daily_runs_detected(self):
        runs = [make_run(run_id=f"r{i}", created_at="2024-01-01T00:00:00Z") for i in range(21)]
        ws = self._ws_with_runs(runs)
        analyze_runs(ws, audit_days=1)
        patterns = [f["pattern"] for f in ws.findings]
        assert "EXCESSIVE_DAILY_RUNS" in patterns

    def test_speculative_plan_overuse_detected(self):
        runs = [make_run(run_id=f"p{i}", operation="plan_only") for i in range(8)] + [
            make_run(run_id=f"a{i}", operation="plan_and_apply") for i in range(2)
        ]
        ws = self._ws_with_runs(runs)
        analyze_runs(ws, audit_days=30)
        patterns = [f["pattern"] for f in ws.findings]
        assert "SPECULATIVE_PLAN_OVERUSE" in patterns

    def test_rapid_fire_runs_detected(self):
        timestamps = [
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:01:00Z",
            "2024-01-01T00:02:00Z",
            "2024-01-01T00:03:00Z",
            "2024-01-01T00:04:00Z",
        ]
        runs = _runs_at(*timestamps)
        ws = self._ws_with_runs(runs)
        analyze_runs(ws, audit_days=30)
        patterns = [f["pattern"] for f in ws.findings]
        assert "RAPID_FIRE_RUNS" in patterns

    def test_no_change_churn_detected(self):
        runs = [
            make_run(
                run_id=f"nc{i}",
                status="planned_and_finished",
                has_changes=False,
            )
            for i in range(7)
        ] + [make_run(run_id=f"a{i}", status="applied") for i in range(3)]
        ws = self._ws_with_runs(runs)
        analyze_runs(ws, audit_days=30)
        patterns = [f["pattern"] for f in ws.findings]
        assert "NO_CHANGE_CHURN" in patterns

    def test_long_plan_duration_detected(self):
        runs = [make_run(run_id="slow", plan_duration=45.0)]
        ws = self._ws_with_runs(runs)
        analyze_runs(ws, audit_days=30)
        patterns = [f["pattern"] for f in ws.findings]
        assert "LONG_PLAN_DURATION" in patterns

    def test_no_finding_for_healthy_workspace(self):
        # Spread runs across different hours so no rapid-fire is triggered
        runs = [make_run(run_id=f"r{i}", created_at=f"2024-01-01T{i:02d}:00:00Z") for i in range(5)]
        ws = self._ws_with_runs(runs)
        analyze_runs(ws, audit_days=30)
        assert ws.findings == []

    def test_run_counts_populated(self):
        # Spread timestamps so no rapid-fire is triggered
        runs = [
            make_run(run_id="e1", status="errored", created_at="2024-01-01T00:00:00Z"),
            make_run(run_id="c1", status="canceled", created_at="2024-01-01T01:00:00Z"),
            make_run(run_id="a1", status="applied", created_at="2024-01-01T02:00:00Z"),
            make_run(run_id="d1", status="discarded", created_at="2024-01-01T03:00:00Z"),
            # plan_only runs have status "planned", not "applied"
            make_run(
                run_id="p1",
                status="planned",
                operation="plan_only",
                created_at="2024-01-01T04:00:00Z",
            ),
        ]
        ws = self._ws_with_runs(runs)
        analyze_runs(ws, audit_days=10)
        assert ws.run_count == 5
        assert ws.errored_count == 1
        assert ws.canceled_count == 1
        assert ws.applied_count == 1
        assert ws.discarded_count == 1
        assert ws.plan_only_count == 1
        assert ws.avg_daily_runs == pytest.approx(0.5)
