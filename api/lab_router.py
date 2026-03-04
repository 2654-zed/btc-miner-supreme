"""
api/lab_router.py
─────────────────
FastAPI ``APIRouter`` implementing the Strategy Lab endpoints.

Mounted onto the main ``app`` in ``api/router.py`` via
``app.include_router(lab_router)``.

Endpoints
─────────
  GET   /api/v1/lab/strategies        — available strategy catalogue
  POST  /api/v1/lab/run               — execute benchmark run
  GET   /api/v1/lab/runs              — list past run summaries
  GET   /api/v1/lab/runs/{run_id}     — full result for one run
  DELETE /api/v1/lab/runs/{run_id}    — delete a stored run
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

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
from core.exceptions import HardwareRoutingError, SecurityViolationError
from domain.interfaces import HeuristicStrategy
from infrastructure.benchmark_engine import BenchmarkEngine, BenchmarkRunResult

logger = logging.getLogger(__name__)

lab_router = APIRouter(
    prefix="/api/v1/lab",
    tags=["Strategy Lab"],
)

# ─── Singleton benchmark engine ────────────────────────────────────────
_engine: BenchmarkEngine | None = None


def _get_engine() -> BenchmarkEngine:
    global _engine
    if _engine is None:
        _engine = BenchmarkEngine()
    return _engine


# ─── Strategy catalogue (static) ───────────────────────────────────────

STRATEGY_CATALOGUE: list[StrategySchema] = [
    StrategySchema(
        id="griffin_962",
        name="Griffin-962 Attractor",
        description=(
            "Scores nonces by proximity to attractor basins derived "
            "from the harmonic series on 1/962 × φ."
        ),
        category="entropy_source",
        parameters=[
            StrategyParameterSchema(
                name="attractor_constant",
                type="float",
                default_value="0.001039501",
                min_value="0.0000001",
                max_value="1.0",
                description="Griffin constant (default 1/962).",
            ),
            StrategyParameterSchema(
                name="basin_width",
                type="float",
                default_value="0.0005",
                min_value="0.00001",
                max_value="0.1",
                description="Width of each attractor basin.",
            ),
            StrategyParameterSchema(
                name="harmonic_depth",
                type="int",
                default_value="8",
                min_value="1",
                max_value="64",
                description="Number of harmonic overtones.",
            ),
        ],
    ),
    StrategySchema(
        id="zeta_critical",
        name="Zeta-Critical Alignment",
        description=(
            "Scores nonces by proximity to Riemann ζ function "
            "non-trivial zeros projected onto uint32 space."
        ),
        category="entropy_source",
        parameters=[
            StrategyParameterSchema(
                name="filter_tolerance",
                type="float",
                default_value="1e-6",
                min_value="1e-12",
                max_value="0.01",
                description="Proximity tolerance for zero alignment.",
            ),
        ],
    ),
    StrategySchema(
        id="observer_ladder",
        name="Observer Ladder Replay",
        description=(
            "Multi-layer recursive Bayesian scorer ranking nonces by "
            "accumulated convergence evidence across recursion layers."
        ),
        category="entropy_source",
        parameters=[
            StrategyParameterSchema(
                name="recursion_depth",
                type="int",
                default_value="5",
                min_value="1",
                max_value="20",
                description="Number of recursive scoring layers.",
            ),
            StrategyParameterSchema(
                name="convergence_threshold",
                type="float",
                default_value="0.85",
                min_value="0.0",
                max_value="1.0",
                description="Minimum score to pass the ladder.",
            ),
        ],
    ),
    StrategySchema(
        id="formula_griffin",
        name="Griffin-962 Formula",
        description="Evaluates (nonce ** 1.618) + (1/962) % 0xFFFFFFFF via CPU sandbox.",
        category="math_formula",
        parameters=[],
    ),
    StrategySchema(
        id="formula_zeta_phi",
        name="Zeta-Critical φ Bias",
        description="Evaluates (nonce ** phi) % 0xFFFFFFFF via CPU sandbox.",
        category="math_formula",
        parameters=[],
    ),
    StrategySchema(
        id="formula_euler",
        name="Euler–Mascheroni Damp",
        description="Evaluates nonce * gamma + (nonce ** 0.5) via CPU sandbox.",
        category="math_formula",
        parameters=[],
    ),
    StrategySchema(
        id="formula_harmonic",
        name="Harmonic Resonance",
        description="Evaluates (nonce * pi / 962) % 0xFFFFFFFF via CPU sandbox.",
        category="math_formula",
        parameters=[],
    ),
    StrategySchema(
        id="formula_quadratic",
        name="Quadratic Residue",
        description="Evaluates (nonce ** 2 + nonce + 41) % 0xFFFFFFFF via CPU sandbox.",
        category="math_formula",
        parameters=[],
    ),
    StrategySchema(
        id="formula_xor",
        name="XOR Cascade",
        description="Evaluates nonce ^ (nonce >> 16) ^ (nonce >> 8) via CPU sandbox.",
        category="math_formula",
        parameters=[],
    ),
    StrategySchema(
        id="padic_ladder",
        name="p-Adic Ladder Filter",
        description=(
            "Multi-prime p-adic modular ladder filter. Scores nonces by "
            "distance-to-mid-residue across configurable (prime, power) "
            "stages plus a trigonometric entropy overlay."
        ),
        category="entropy_source",
        parameters=[
            StrategyParameterSchema(
                name="entropy_weight",
                type="float",
                default_value="0.35",
                min_value="0.0",
                max_value="2.0",
                description="Weight of the trigonometric entropy overlay term.",
            ),
        ],
    ),
    StrategySchema(
        id="custom_formula",
        name="Custom Formula",
        description=(
            "User-supplied arithmetic expression evaluated via "
            "AST-sanitised MathSandbox. Provide formula in request body."
        ),
        category="math_formula",
        parameters=[],
    ),
]

_CATALOGUE_BY_ID = {s.id: s for s in STRATEGY_CATALOGUE}

# ─── Preset formula map ─────────────────────────────────────────────────

_PRESET_FORMULAS = {
    "formula_griffin": "(nonce ** 1.618) + (1/962) % 0xFFFFFFFF",
    "formula_zeta_phi": "(nonce ** phi) % 0xFFFFFFFF",
    "formula_euler": "nonce * gamma + (nonce ** 0.5)",
    "formula_harmonic": "(nonce * pi / 962) % 0xFFFFFFFF",
    "formula_quadratic": "(nonce ** 2 + nonce + 41) % 0xFFFFFFFF",
    "formula_xor": "nonce ^ (nonce >> 16) ^ (nonce >> 8)",
}


# ─── Strategy builder ──────────────────────────────────────────────────

def _build_strategy(
    strategy_id: str,
    formula: Optional[str],
    parameters: Optional[dict[str, str]],
) -> tuple[HeuristicStrategy, Optional[str]]:
    """Construct the appropriate HeuristicStrategy for a benchmark run.

    Returns
    -------
    (strategy, formula_used)
        The strategy instance and the formula string (if applicable).

    Raises
    ------
    ValueError
        If parameters are invalid.
    SecurityViolationError
        If a formula fails AST validation.
    """
    params = parameters or {}

    # ── Preset formula strategies ────────────────────────────────────
    if strategy_id in _PRESET_FORMULAS:
        from infrastructure.strategies.cpu_dynamic import DynamicCPUStrategy
        f = _PRESET_FORMULAS[strategy_id]
        return DynamicCPUStrategy(formula=f), f

    # ── Custom formula ───────────────────────────────────────────────
    if strategy_id == "custom_formula":
        from infrastructure.strategies.cpu_dynamic import DynamicCPUStrategy
        return DynamicCPUStrategy(formula=formula), formula  # type: ignore[arg-type]

    # ── Griffin-962 entropy source ───────────────────────────────────
    if strategy_id == "griffin_962":
        from infrastructure.strategies.entropy_adapter import GriffinScoringStrategy
        return GriffinScoringStrategy(
            attractor_constant=float(params.get("attractor_constant", "0.001039501")),
            basin_width=float(params.get("basin_width", "0.0005")),
            harmonic_depth=int(params.get("harmonic_depth", "8")),
        ), None

    # ── Zeta-Critical entropy source ─────────────────────────────────
    if strategy_id == "zeta_critical":
        from infrastructure.strategies.entropy_adapter import ZetaScoringStrategy
        return ZetaScoringStrategy(
            filter_tolerance=float(params.get("filter_tolerance", "1e-6")),
        ), None

    # ── Observer Ladder entropy source ───────────────────────────────
    if strategy_id == "observer_ladder":
        from infrastructure.strategies.entropy_adapter import ObserverScoringStrategy
        return ObserverScoringStrategy(
            recursion_depth=int(params.get("recursion_depth", "5")),
            convergence_threshold=float(params.get("convergence_threshold", "0.85")),
        ), None

    # ── p-Adic Ladder ────────────────────────────────────────────────
    if strategy_id == "padic_ladder":
        from infrastructure.strategies.padic_ladder_strategy import (
            PadicLadderConfig,
            PadicLadderStrategy,
        )
        cfg = PadicLadderConfig(
            entropy_weight=float(params.get("entropy_weight", "0.35")),
        )
        return PadicLadderStrategy(cfg), None

    raise ValueError(f"No builder for strategy_id '{strategy_id}'")


def _result_to_response(r: BenchmarkRunResult) -> BenchmarkRunResponse:
    """Convert an internal BenchmarkRunResult to a Pydantic response."""
    return BenchmarkRunResponse(
        run_id=r.run_id,
        strategy_id=r.strategy_id,
        strategy_name=r.strategy_name,
        formula=r.formula,
        batch_size=r.batch_size,
        timestamp=r.timestamp,
        timed_out=r.timed_out,
        strategy_metrics=MetricsBlock(
            execution_time_ms=r.strategy_metrics.execution_time_ms,
            throughput_nonces_per_sec=r.strategy_metrics.throughput_nonces_per_sec,
            mean=r.strategy_metrics.mean,
            std=r.strategy_metrics.std,
            min_val=r.strategy_metrics.min_val,
            max_val=r.strategy_metrics.max_val,
            anomaly_count=r.strategy_metrics.anomaly_count,
            uniqueness_ratio=r.strategy_metrics.uniqueness_ratio,
            ks_statistic=r.strategy_metrics.ks_statistic,
            ks_p_value=r.strategy_metrics.ks_p_value,
        ),
        baseline_metrics=MetricsBlock(
            execution_time_ms=r.baseline_metrics.execution_time_ms,
            throughput_nonces_per_sec=r.baseline_metrics.throughput_nonces_per_sec,
            mean=r.baseline_metrics.mean,
            std=r.baseline_metrics.std,
            min_val=r.baseline_metrics.min_val,
            max_val=r.baseline_metrics.max_val,
            anomaly_count=r.baseline_metrics.anomaly_count,
            uniqueness_ratio=r.baseline_metrics.uniqueness_ratio,
            ks_statistic=r.baseline_metrics.ks_statistic,
            ks_p_value=r.baseline_metrics.ks_p_value,
        ),
        comparison=ComparisonBlock(
            speedup_factor=r.comparison.speedup_factor,
            mean_divergence=r.comparison.mean_divergence,
            std_ratio=r.comparison.std_ratio,
            anomaly_delta=r.comparison.anomaly_delta,
            distribution_different=r.comparison.distribution_different,
        ),
    )


def _result_to_summary(r: BenchmarkRunResult) -> RunSummary:
    """Convert an internal BenchmarkRunResult to a lightweight summary."""
    return RunSummary(
        run_id=r.run_id,
        strategy_id=r.strategy_id,
        strategy_name=r.strategy_name,
        formula=r.formula,
        batch_size=r.batch_size,
        timestamp=r.timestamp,
        timed_out=r.timed_out,
        strategy_execution_time_ms=r.strategy_metrics.execution_time_ms,
        baseline_execution_time_ms=r.baseline_metrics.execution_time_ms,
        speedup_factor=r.comparison.speedup_factor,
        distribution_different=r.comparison.distribution_different,
    )


# ─── Endpoints ──────────────────────────────────────────────────────────


@lab_router.get(
    "/strategies",
    response_model=AvailableStrategiesResponse,
    summary="List available benchmark strategies",
)
async def list_strategies():
    """Return the full catalogue of selectable strategies with
    their tunable parameters."""
    return AvailableStrategiesResponse(strategies=STRATEGY_CATALOGUE)


@lab_router.post(
    "/run",
    response_model=BenchmarkRunResponse,
    summary="Execute a benchmark run — strategy vs. random baseline",
)
async def run_benchmark(request: BenchmarkRunRequest):
    """
    Build the requested strategy, execute a benchmark run against
    a cryptographically secure random baseline, and return
    empirically computed comparative metrics.
    """
    # Validate strategy_id
    if request.strategy_id not in _CATALOGUE_BY_ID:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy_id: '{request.strategy_id}'. "
                   f"Use GET /api/v1/lab/strategies for valid IDs.",
        )

    # custom_formula requires a formula string
    if request.strategy_id == "custom_formula" and not request.formula:
        raise HTTPException(
            status_code=400,
            detail="strategy_id 'custom_formula' requires a non-empty 'formula' field.",
        )

    strategy_info = _CATALOGUE_BY_ID[request.strategy_id]

    try:
        strategy, formula_used = _build_strategy(
            request.strategy_id, request.formula, request.parameters,
        )
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Security Policy Violation: {exc}",
        )
    except (ValueError, HardwareRoutingError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        engine = _get_engine()
        result = engine.run(
            strategy=strategy,
            strategy_id=request.strategy_id,
            strategy_name=strategy_info.name,
            batch_size=request.batch_size,
            formula=formula_used,
            timeout_seconds=request.timeout_seconds,
        )
    except Exception as exc:
        logger.exception("Benchmark run failed")
        raise HTTPException(
            status_code=500,
            detail=f"Benchmark execution error: {exc}",
        )

    return _result_to_response(result)


@lab_router.get(
    "/runs",
    response_model=RunListResponse,
    summary="List summaries of stored benchmark runs",
)
async def list_runs():
    """Return summaries of all stored benchmark runs, newest first."""
    engine = _get_engine()
    runs = engine.list_runs()
    return RunListResponse(
        runs=[_result_to_summary(r) for r in runs],
        total=engine.total,
        capacity=engine.capacity,
    )


@lab_router.get(
    "/runs/{run_id}",
    response_model=BenchmarkRunResponse,
    summary="Retrieve full results of a specific benchmark run",
)
async def get_run(run_id: str):
    """Retrieve full results for a specific stored benchmark run."""
    result = _get_engine().get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return _result_to_response(result)


@lab_router.delete(
    "/runs/{run_id}",
    response_model=RunDeleteResponse,
    summary="Delete a stored benchmark run",
)
async def delete_run(run_id: str):
    """Delete a specific stored benchmark run."""
    if not _get_engine().delete_run(run_id):
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return RunDeleteResponse(deleted=True, run_id=run_id)
