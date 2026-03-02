"""
api/router.py
─────────────
FastAPI router implementing the Dynamic Heuristic Injector endpoints.

Endpoints
─────────
  POST  /api/v1/inject-heuristic   — inject a formula + execute
  POST  /api/v1/validate-formula   — AST-only dry-run validation
  GET   /api/v1/orchestrator/status — runtime diagnostics

Security Model
──────────────
  1. Pydantic regex + length constraints (schemas.py)
  2. AST whitelist traversal (MathSandbox)
  3. NumExpr GIL-bypass evaluation

Error Codes
───────────
  400  — Invalid syntax, impossible hardware routing
  403  — AST SecurityViolationError (malicious construct detected)
  500  — Unhandled internal error
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import yaml  # type: ignore[import-untyped]
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    FormulaValidationRequest,
    FormulaValidationResponse,
    FullStatusResponse,
    HeuristicInjectionRequest,
    HeuristicInjectionResponse,
    OrchestratorStatusResponse,
)
from core.config_provider import ConfigProvider, ConfigurationError
from core.exceptions import HardwareRoutingError, SecurityViolationError
from core.orchestrator import MasterOrchestrator
from core.telemetry_provider import TelemetryProvider
from infrastructure.strategies.cpu_dynamic import DynamicCPUStrategy

logger = logging.getLogger(__name__)

# ── Application-scoped singleton ────────────────────────────────────────
_orchestrator: MasterOrchestrator | None = None


def _get_orchestrator() -> MasterOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        # Bootstrap with a CPU strategy using a harmless default formula
        default = DynamicCPUStrategy(formula="nonce % 0xFFFFFFFF")
        _orchestrator = MasterOrchestrator(initial_strategy=default)
    return _orchestrator


# ── Lifespan ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Dynamic Heuristic Injector API starting …")
    _get_orchestrator()  # Eager init
    yield
    logger.info("API shutting down — halting orchestrator.")
    if _orchestrator:
        _orchestrator.halt()


# ── App factory ─────────────────────────────────────────────────────────
app = FastAPI(
    title="ΩINTELLIGENCE™ Dynamic Heuristic Injector",
    version="1.0.0",
    description=(
        "Hardware-agnostic orchestration API supporting runtime formula "
        "injection via secure AST sanitisation + NumExpr execution."
    ),
    lifespan=lifespan,
)

_cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)


# ─── Routes ─────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/inject-heuristic",
    response_model=HeuristicInjectionResponse,
    summary="Inject and execute a dynamic mathematical heuristic",
)
async def inject_dynamic_heuristic(request: HeuristicInjectionRequest):
    """
    Validates the formula via AST sanitisation, hot-swaps the
    Orchestrator to a ``DynamicCPUStrategy``, generates a nonce
    batch, and executes.
    """
    try:
        # Hard architectural constraint: only CPU supports dynamic strings
        if request.target_hardware in ("FPGA", "GPU"):
            raise HardwareRoutingError(
                f"Dynamic string injection is fundamentally incompatible "
                f"with {request.target_hardware} AOT architecture.  "
                f"Route to 'CPU' instead."
            )

        # 1. Build a new CPU strategy (validates AST in constructor)
        strategy = DynamicCPUStrategy(formula=request.formula)

        # 2. Hot-swap via IoC
        orch = _get_orchestrator()
        orch.set_strategy(
            strategy,
            reason=f"user-injected formula: {request.formula[:60]}",
        )

        # 3. Generate nonces and process
        nonces = np.arange(request.batch_size, dtype=np.uint32)
        result = orch.process_workload(nonces)

        return HeuristicInjectionResponse(
            success=True,
            message=(
                "Dynamic heuristic successfully injected and verified "
                "via the CPU Sandbox."
            ),
            processed_count=request.batch_size,
            anomalies_detected=result.anomalies,
            elapsed_ms=round(result.elapsed_ms, 2),
            hardware_target=result.hardware_target,
        )

    except HardwareRoutingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Security Policy Violation: {exc}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Unhandled injection error")
        raise HTTPException(
            status_code=500,
            detail="Internal orchestration failure.",
        )


@app.post(
    "/api/v1/validate-formula",
    response_model=FormulaValidationResponse,
    summary="Dry-run AST validation without execution",
)
async def validate_formula(request: FormulaValidationRequest):
    """Parses and validates a formula via the AST sanitiser only."""
    from infrastructure.math_sandbox import MathSandbox

    sandbox = MathSandbox()
    try:
        sandbox.sanitize(request.formula)
        return FormulaValidationResponse(valid=True)
    except (SecurityViolationError, ValueError) as exc:
        return FormulaValidationResponse(valid=False, error=str(exc))


@app.get(
    "/api/v1/orchestrator/status",
    response_model=OrchestratorStatusResponse,
    summary="Orchestrator runtime diagnostics",
)
async def orchestrator_status():
    """Returns current state of the MasterOrchestrator."""
    diag = _get_orchestrator().get_diagnostics()
    return OrchestratorStatusResponse(
        is_running=diag["is_running"],
        current_target=diag["current_target"],
        total_batches=diag["total_batches"],
        total_nonces=diag["total_nonces"],
        swap_history_length=diag["swap_history_length"],
    )


# ─── Full Telemetry Status (ConfigProvider-sourced) ────────────────────

# Monotonic counter for terminal line IDs
_terminal_line_id = 0

# Singleton ConfigProvider — injected, not hardcoded
_config_provider: ConfigProvider | None = None
# Singleton TelemetryProvider — real hardware metrics
_telemetry_provider: TelemetryProvider | None = None


def _get_config() -> ConfigProvider:
    """Lazy-initialise the ConfigProvider singleton.

    Raises ``ConfigurationError`` if env vars are not set.
    There is NO silent fallback — fail-fast is enforced.
    """
    global _config_provider
    if _config_provider is None:
        _config_provider = ConfigProvider()
    return _config_provider


def _get_telemetry() -> TelemetryProvider:
    """Lazy-initialise the TelemetryProvider singleton."""
    global _telemetry_provider
    if _telemetry_provider is None:
        _telemetry_provider = TelemetryProvider()
    return _telemetry_provider


def _build_hardware_state() -> dict:
    """Probe REAL hardware via TelemetryProvider.

    Returns only devices that actually exist on the host.
    Metrics are measured, never fabricated.
    """
    tp = _get_telemetry()
    snap = tp.collect()

    cpus = [
        {
            "model": c.model,
            "cores": c.cores,
            "threads": c.threads,
            "load": c.load,       # None if psutil unavailable
            "temp": c.temp,       # None if sensor unavailable
            "frequency": c.frequency,
        }
        for c in snap.cpus
    ]

    gpus = [
        {
            "id": g.id,
            "name": g.name,
            "temp": g.temp,
            "utilization": g.utilization,
            "memUsed": g.mem_used,
            "memTotal": g.mem_total,  # QUERIED from pynvml, never hardcoded
            "power": g.power,
            "hashRate": g.hash_rate,
            "status": g.status,
        }
        for g in snap.gpus
    ]

    fpgas = [
        {
            "id": f.id,
            "name": f.name,
            "voltage": f.voltage,
            "xrtStatus": f.xrt_status,
            "dmaRate": f.dma_rate,
            "hashRate": f.hash_rate,
            "temp": f.temp,
            "status": f.status,
        }
        for f in snap.fpgas
    ]

    return {"cpus": cpus, "gpus": gpus, "fpgas": fpgas}


def _build_terminal_lines() -> list[dict]:
    """Generate terminal boot lines from REAL config state."""
    global _terminal_line_id
    now = time.strftime("%H:%M:%S", time.localtime())

    lines = []
    boot_msgs: list[tuple[str, str]] = []

    try:
        cfg_prov = _get_config()
        topo = cfg_prov.hardware_topology
        stratum = cfg_prov.stratum_config
        payout = cfg_prov.payout_config
        boot_msgs = [
            ("System", f"ΩINTELLIGENCE™ v{cfg_prov.raw.get('system', {}).get('version', '?')} booting"),
            ("Config", f"config.yaml loaded — {cfg_prov._path}"),
            ("Hardware", f"CPU: {topo.cpu_model} × {topo.cpu_nodes} (config claim — verify with probe)"),
            ("Hardware", f"GPU: {topo.gpu_model} × {topo.gpu_count} (config claim)"),
            ("Hardware", f"FPGA: {topo.fpga_model} × {topo.fpga_count} (config claim)"),
            ("Stratum", f"Pool: {stratum.pool_url}"),
            ("Wallet", f"Payout threshold: ≥ {payout.min_payout_btc} BTC"),
        ]
    except ConfigurationError as exc:
        boot_msgs = [
            ("System", "ΩINTELLIGENCE™ booting — CONFIG ERROR"),
            ("Error", f"ConfigProvider failed: {exc}"),
            ("Error", "Set required env vars (see .env.example) and restart."),
        ]

    # Add real hardware probe summary
    tp = _get_telemetry()
    snap = tp.collect()
    boot_msgs.append(("Probe", f"Detected: {len(snap.cpus)} CPU(s), {len(snap.gpus)} GPU(s), {len(snap.fpgas)} FPGA(s)"))

    for tag, msg in boot_msgs:
        _terminal_line_id += 1
        lines.append({
            "id": _terminal_line_id,
            "timestamp": now,
            "tag": tag,
            "message": msg,
            "level": "error" if tag == "Error" else "info",
        })
    return lines


@app.get(
    "/api/v1/status",
    response_model=FullStatusResponse,
    summary="Full dashboard telemetry — hardware-probed, never fabricated",
)
async def full_status():
    """
    Returns the complete telemetry payload consumed by the React dashboard.

    Contract
    ────────
    • Hardware metrics are PROBED from psutil / pynvml / XRT.
    • Financial metrics are ``None`` until a price feed is wired.
    • Mining stats come from the orchestrator — not fabricated.
    • If a data source is unavailable, the field is ``None``, NEVER zero.
    """
    tp = _get_telemetry()
    miner = tp._miner_telemetry

    # Orchestrator diagnostics
    try:
        orch_diag = _get_orchestrator().get_diagnostics()
        is_running = orch_diag["is_running"]
        total_batches = orch_diag["total_batches"]
    except Exception:
        is_running = False
        total_batches = 0

    # Wallet address from config (fail-fast if not configured)
    try:
        wallet_address = _get_config().wallet_address
    except ConfigurationError:
        wallet_address = None

    return FullStatusResponse(
        entropy=[],  # Populated when entropy pipeline is wired
        hardware=_build_hardware_state(),
        profit={
            # None = "not yet wired" — dashboard renders N/A, not fake $0
            "btcPrice": None,
            "dailyRevenueBTC": None,
            "dailyRevenueUSD": None,
            "powerCostUSD": None,
            "netProfitUSD": None,
            "hashRate": miner.aggregate_hash_rate if miner.aggregate_hash_rate > 0 else None,
            "networkDifficulty": None,
            "networkShare": None,
        },
        wallet={
            "address": wallet_address,
            "balance": None,           # Requires blockchain query
            "pendingRewards": None,    # Requires pool API
            "totalMined": None,        # Requires ledger
            "lastPayout": None,
        },
        mining={
            "totalRounds": total_batches + miner.total_rounds,
            "blocksFound": miner.blocks_found,
            "uptime": tp.uptime_seconds,
            "currentPhase": miner.current_phase if miner.current_phase != "Offline" else (
                "Active" if is_running else "Idle"
            ),
            "stratumConnected": miner.stratum_connected,
            "lastBlockTime": miner.last_block_time,
        },
        terminal=_build_terminal_lines(),
    )
