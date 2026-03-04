"""
api/lab_schemas.py
──────────────────
Pydantic v2 models for the Strategy Lab — an experimentation tool
for benchmarking nonce-selection strategies against a cryptographically
secure random baseline.

These schemas define the strict contract between the React frontend
and the Python benchmark engine.  Every nullable numeric field uses
``Optional[float]`` (never bare ``0.0``).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ─── Strategy catalogue ─────────────────────────────────────────────────


class StrategyParameterSchema(BaseModel):
    """Descriptor for one tunable parameter of a strategy."""
    name: str
    type: str = Field(
        ...,
        pattern=r"^(float|int|str)$",
        description="Parameter data type.",
    )
    default_value: str = Field(
        ...,
        description="JSON-encoded default (always string for transport).",
    )
    min_value: Optional[str] = None
    max_value: Optional[str] = None
    description: str = ""


class StrategySchema(BaseModel):
    """One selectable strategy in the lab catalogue."""
    id: str
    name: str
    description: str
    category: str = Field(
        ...,
        pattern=r"^(entropy_source|math_formula)$",
    )
    parameters: list[StrategyParameterSchema] = []


class AvailableStrategiesResponse(BaseModel):
    """Response for ``GET /api/v1/lab/strategies``."""
    strategies: list[StrategySchema]


# ─── Benchmark run ───────────────────────────────────────────────────────


class BenchmarkRunRequest(BaseModel):
    """
    Request body for ``POST /api/v1/lab/run``.

    If ``strategy_id`` is ``"custom_formula"`` then ``formula`` is
    required.  Otherwise ``formula`` is ignored.
    """
    strategy_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Strategy identifier from /strategies, or 'custom_formula'.",
    )
    formula: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=250,
        pattern=r"^[a-zA-Z0-9\s\+\-\*\/\(\)\.\%\^\~\&\|]+$",
        description=(
            "Required when strategy_id == 'custom_formula'. "
            "Same constraints as HeuristicInjectionRequest.formula."
        ),
    )
    batch_size: int = Field(
        default=1_000_000,
        ge=1_000,
        le=50_000_000,
        description="Number of uint32 nonces per benchmark run.",
    )
    parameters: Optional[dict[str, str]] = Field(
        default=None,
        description="Strategy-specific parameter overrides (JSON-string values).",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Hard wall-clock limit in seconds.",
    )


# ─── Metrics ─────────────────────────────────────────────────────────────


class MetricsBlock(BaseModel):
    """Statistical metrics for one side of the benchmark (strategy or baseline)."""
    execution_time_ms: float
    throughput_nonces_per_sec: float
    mean: float
    std: float
    min_val: float
    max_val: float
    anomaly_count: int
    uniqueness_ratio: float
    ks_statistic: float
    ks_p_value: float


class ComparisonBlock(BaseModel):
    """Comparative metrics between strategy and baseline."""
    speedup_factor: float
    mean_divergence: float
    std_ratio: float
    anomaly_delta: int
    distribution_different: bool


class BenchmarkRunResponse(BaseModel):
    """
    Full result of one benchmark run.

    Returned by ``POST /api/v1/lab/run`` and ``GET /api/v1/lab/runs/{run_id}``.
    """
    run_id: str
    strategy_id: str
    strategy_name: str
    formula: Optional[str] = None
    batch_size: int
    timestamp: str
    timed_out: bool

    strategy_metrics: MetricsBlock
    baseline_metrics: MetricsBlock
    comparison: ComparisonBlock


# ─── Run list ────────────────────────────────────────────────────────────


class RunSummary(BaseModel):
    """Lightweight summary used in the run history list."""
    run_id: str
    strategy_id: str
    strategy_name: str
    formula: Optional[str] = None
    batch_size: int
    timestamp: str
    timed_out: bool
    strategy_execution_time_ms: float
    baseline_execution_time_ms: float
    speedup_factor: float
    distribution_different: bool


class RunListResponse(BaseModel):
    """Response for ``GET /api/v1/lab/runs``."""
    runs: list[RunSummary]
    total: int
    capacity: int


# ─── Delete ──────────────────────────────────────────────────────────────


class RunDeleteResponse(BaseModel):
    """Response for ``DELETE /api/v1/lab/runs/{run_id}``."""
    deleted: bool
    run_id: str
