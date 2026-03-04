"""
tests/test_lab_schemas.py
─────────────────────────
Pydantic v2 model validation tests for Strategy Lab schemas.

Covers:
  • BenchmarkRunRequest — field constraints (batch_size, timeout,
    strategy_id length, formula regex)
  • StrategySchema — category regex enforcement
  • MetricsBlock / ComparisonBlock — round-trip construction
  • RunSummary / RunDeleteResponse — lightweight models

Run:  pytest tests/test_lab_schemas.py -v
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.lab_schemas import (
    AvailableStrategiesResponse,
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    ComparisonBlock,
    MetricsBlock,
    RunDeleteResponse,
    RunListResponse,
    RunSummary,
    StrategyParameterSchema,
    StrategySchema,
)


# ═════════════════════════════════════════════════════════════════════════
# BenchmarkRunRequest
# ═════════════════════════════════════════════════════════════════════════

class TestBenchmarkRunRequest:
    """Validate field constraints on the benchmark run request model."""

    def test_minimal_valid_request(self):
        req = BenchmarkRunRequest(strategy_id="formula_quadratic")
        assert req.strategy_id == "formula_quadratic"
        assert req.batch_size == 1_000_000
        assert req.timeout_seconds == 30
        assert req.formula is None
        assert req.parameters is None

    def test_all_fields_specified(self):
        req = BenchmarkRunRequest(
            strategy_id="custom_formula",
            formula="nonce + 1",
            batch_size=5_000,
            parameters={"k": "3"},
            timeout_seconds=60,
        )
        assert req.formula == "nonce + 1"
        assert req.batch_size == 5_000
        assert req.timeout_seconds == 60
        assert req.parameters == {"k": "3"}

    def test_batch_size_lower_bound(self):
        req = BenchmarkRunRequest(strategy_id="x", batch_size=1_000)
        assert req.batch_size == 1_000

    def test_batch_size_upper_bound(self):
        req = BenchmarkRunRequest(strategy_id="x", batch_size=50_000_000)
        assert req.batch_size == 50_000_000

    def test_batch_size_below_min_rejected(self):
        with pytest.raises(ValidationError, match="batch_size"):
            BenchmarkRunRequest(strategy_id="x", batch_size=999)

    def test_batch_size_above_max_rejected(self):
        with pytest.raises(ValidationError, match="batch_size"):
            BenchmarkRunRequest(strategy_id="x", batch_size=50_000_001)

    def test_timeout_lower_bound(self):
        req = BenchmarkRunRequest(strategy_id="x", timeout_seconds=5)
        assert req.timeout_seconds == 5

    def test_timeout_upper_bound(self):
        req = BenchmarkRunRequest(strategy_id="x", timeout_seconds=120)
        assert req.timeout_seconds == 120

    def test_timeout_below_min_rejected(self):
        with pytest.raises(ValidationError, match="timeout_seconds"):
            BenchmarkRunRequest(strategy_id="x", timeout_seconds=4)

    def test_timeout_above_max_rejected(self):
        with pytest.raises(ValidationError, match="timeout_seconds"):
            BenchmarkRunRequest(strategy_id="x", timeout_seconds=121)

    def test_strategy_id_empty_rejected(self):
        with pytest.raises(ValidationError, match="strategy_id"):
            BenchmarkRunRequest(strategy_id="")

    def test_strategy_id_too_long_rejected(self):
        with pytest.raises(ValidationError, match="strategy_id"):
            BenchmarkRunRequest(strategy_id="x" * 101)

    def test_formula_valid_arithmetic(self):
        req = BenchmarkRunRequest(
            strategy_id="custom_formula",
            formula="(nonce ** 2 + 41) % 0xFFFFFFFF",
        )
        assert req.formula is not None

    def test_formula_with_bitwise_ops(self):
        req = BenchmarkRunRequest(
            strategy_id="custom_formula",
            formula="nonce ^ nonce & 0xFF",
        )
        assert req.formula is not None

    def test_formula_rejects_semicolons(self):
        with pytest.raises(ValidationError, match="formula"):
            BenchmarkRunRequest(
                strategy_id="custom_formula",
                formula="nonce; import os",
            )

    def test_formula_rejects_underscores(self):
        with pytest.raises(ValidationError, match="formula"):
            BenchmarkRunRequest(
                strategy_id="custom_formula",
                formula="__import__('os')",
            )

    def test_formula_rejects_brackets(self):
        with pytest.raises(ValidationError, match="formula"):
            BenchmarkRunRequest(
                strategy_id="custom_formula",
                formula="[x for x in range(10)]",
            )

    def test_formula_empty_rejected(self):
        with pytest.raises(ValidationError, match="formula"):
            BenchmarkRunRequest(
                strategy_id="custom_formula",
                formula="",
            )

    def test_formula_too_long_rejected(self):
        with pytest.raises(ValidationError, match="formula"):
            BenchmarkRunRequest(
                strategy_id="custom_formula",
                formula="a" * 251,
            )


# ═════════════════════════════════════════════════════════════════════════
# StrategySchema
# ═════════════════════════════════════════════════════════════════════════

class TestStrategySchema:
    """Validate category regex and construction."""

    def test_entropy_source_category(self):
        s = StrategySchema(
            id="test",
            name="Test",
            description="A test strategy",
            category="entropy_source",
        )
        assert s.category == "entropy_source"

    def test_math_formula_category(self):
        s = StrategySchema(
            id="test",
            name="Test",
            description="A test strategy",
            category="math_formula",
        )
        assert s.category == "math_formula"

    def test_invalid_category_rejected(self):
        with pytest.raises(ValidationError, match="category"):
            StrategySchema(
                id="test",
                name="Test",
                description="A test strategy",
                category="unknown_type",
            )

    def test_with_parameters(self):
        param = StrategyParameterSchema(
            name="depth",
            type="int",
            default_value="8",
            min_value="1",
            max_value="64",
            description="Harmonic depth",
        )
        s = StrategySchema(
            id="test",
            name="Test",
            description="d",
            category="entropy_source",
            parameters=[param],
        )
        assert len(s.parameters) == 1
        assert s.parameters[0].name == "depth"


# ═════════════════════════════════════════════════════════════════════════
# StrategyParameterSchema
# ═════════════════════════════════════════════════════════════════════════

class TestStrategyParameterSchema:

    def test_valid_float_type(self):
        p = StrategyParameterSchema(name="w", type="float", default_value="0.35")
        assert p.type == "float"

    def test_valid_int_type(self):
        p = StrategyParameterSchema(name="d", type="int", default_value="8")
        assert p.type == "int"

    def test_valid_str_type(self):
        p = StrategyParameterSchema(name="m", type="str", default_value="auto")
        assert p.type == "str"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError, match="type"):
            StrategyParameterSchema(name="x", type="list", default_value="[]")


# ═════════════════════════════════════════════════════════════════════════
# MetricsBlock / ComparisonBlock round-trip
# ═════════════════════════════════════════════════════════════════════════

class TestMetricsAndComparison:

    def test_metrics_block_construction(self):
        m = MetricsBlock(
            execution_time_ms=12.5,
            throughput_nonces_per_sec=80_000_000.0,
            mean=0.5,
            std=0.29,
            min_val=0.0,
            max_val=1.0,
            anomaly_count=0,
            uniqueness_ratio=0.99,
            ks_statistic=0.01,
            ks_p_value=0.85,
        )
        assert m.anomaly_count == 0
        assert m.ks_p_value == 0.85

    def test_comparison_block_construction(self):
        c = ComparisonBlock(
            speedup_factor=1.5,
            mean_divergence=0.02,
            std_ratio=1.1,
            anomaly_delta=0,
            distribution_different=False,
        )
        assert c.distribution_different is False

    def test_metrics_block_negative_values(self):
        """Negative execution_time doesn't make physical sense but
        Pydantic doesn't constrain it — the engine enforces semantics."""
        m = MetricsBlock(
            execution_time_ms=-1.0,
            throughput_nonces_per_sec=0.0,
            mean=-100.0,
            std=0.0,
            min_val=-100.0,
            max_val=-100.0,
            anomaly_count=0,
            uniqueness_ratio=0.0,
            ks_statistic=0.0,
            ks_p_value=1.0,
        )
        assert m.execution_time_ms == -1.0


# ═════════════════════════════════════════════════════════════════════════
# Response models
# ═════════════════════════════════════════════════════════════════════════

class TestResponseModels:

    def test_run_summary(self):
        s = RunSummary(
            run_id="abc-123",
            strategy_id="formula_quadratic",
            strategy_name="Quadratic Residue",
            batch_size=1_000,
            timestamp="2025-01-01T00:00:00Z",
            timed_out=False,
            strategy_execution_time_ms=10.0,
            baseline_execution_time_ms=5.0,
            speedup_factor=0.5,
            distribution_different=True,
        )
        assert s.run_id == "abc-123"
        assert s.formula is None

    def test_run_delete_response(self):
        r = RunDeleteResponse(deleted=True, run_id="xyz")
        assert r.deleted is True

    def test_available_strategies_response(self):
        resp = AvailableStrategiesResponse(strategies=[])
        assert resp.strategies == []

    def test_run_list_response(self):
        resp = RunListResponse(runs=[], total=0, capacity=50)
        assert resp.capacity == 50
