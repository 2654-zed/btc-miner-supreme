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
    allow_headers=["*"],
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

# In-memory boot timestamp for uptime tracking
_BOOT_TIME = time.time()

# Monotonic counter for terminal line IDs
_terminal_line_id = 0

# Singleton ConfigProvider — injected, not hardcoded
_config_provider: ConfigProvider | None = None


def _get_config() -> ConfigProvider:
    """Lazy-initialise the ConfigProvider singleton."""
    global _config_provider
    if _config_provider is None:
        try:
            _config_provider = ConfigProvider()
        except ConfigurationError as exc:
            logger.warning("ConfigProvider init failed: %s — using raw YAML fallback", exc)
            _config_provider = ConfigProvider.__new__(ConfigProvider)
            # Minimal fallback: load raw YAML without env resolution
            config_path = Path(__file__).resolve().parent.parent / "config.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                _config_provider._raw = yaml.safe_load(f) or {}
            _config_provider._path = config_path
    return _config_provider


def _build_hardware_state(cfg: dict) -> dict:
    """Construct HardwareState from config.yaml hardware topology."""
    hw = cfg.get("hardware", {})
    cpu_cfg = hw.get("cpu", {})
    gpu_cfg = hw.get("gpu", {})
    fpga_cfg = hw.get("fpga", {})

    cpus = []
    for i in range(cpu_cfg.get("nodes", 2)):
        cpus.append({
            "model": cpu_cfg.get("model", "Unknown CPU"),
            "cores": cpu_cfg.get("threads_per_node", 128) // 2,
            "threads": cpu_cfg.get("threads_per_node", 128),
            "load": 0.0,
            "temp": 0.0,
            "frequency": 0.0,
        })

    gpus = []
    for i in range(gpu_cfg.get("count", 0)):
        gpus.append({
            "id": i,
            "name": f"{gpu_cfg.get('model', 'GPU')}:{i}",
            "temp": 0.0,
            "utilization": 0.0,
            "memUsed": 0.0,
            "memTotal": 80.0,
            "power": 0.0,
            "hashRate": 0.0,
            "status": "idle",
        })

    fpgas = []
    for i in range(fpga_cfg.get("count", 0)):
        fpgas.append({
            "id": i,
            "name": f"{fpga_cfg.get('model', 'FPGA')}:{i}",
            "voltage": 0.0,
            "xrtStatus": "disconnected",
            "dmaRate": 0.0,
            "hashRate": 0.0,
            "temp": 0.0,
            "status": "idle",
        })

    return {"cpus": cpus, "gpus": gpus, "fpgas": fpgas}


def _build_terminal_lines(cfg: dict) -> list[dict]:
    """Generate a few initial terminal boot lines."""
    global _terminal_line_id
    now = time.strftime("%H:%M:%S", time.localtime())
    config_path = _get_config()._path if _config_provider else "config.yaml"
    lines = []
    boot_msgs = [
        ("System", f"ΩINTELLIGENCE™ v{cfg.get('system', {}).get('version', '1.0.0')} booting"),
        ("Config", f"config.yaml loaded — {config_path}"),
        ("Hardware", f"CPU: {cfg.get('hardware', {}).get('cpu', {}).get('model', '?')} × {cfg.get('hardware', {}).get('cpu', {}).get('nodes', 0)}"),
        ("Hardware", f"GPU: {cfg.get('hardware', {}).get('gpu', {}).get('model', '?')} × {cfg.get('hardware', {}).get('gpu', {}).get('count', 0)}"),
        ("Hardware", f"FPGA: {cfg.get('hardware', {}).get('fpga', {}).get('model', '?')} × {cfg.get('hardware', {}).get('fpga', {}).get('count', 0)}"),
        ("Stratum", f"Connecting to {cfg.get('network', {}).get('stratum', {}).get('pool_url', 'N/A')}"),
        ("Wallet", f"Cold wallet configured — payout ≥ {cfg.get('network', {}).get('payout', {}).get('min_payout_btc', 0)} BTC"),
    ]
    for tag, msg in boot_msgs:
        _terminal_line_id += 1
        lines.append({
            "id": _terminal_line_id,
            "timestamp": now,
            "tag": tag,
            "message": msg,
            "level": "info",
        })
    return lines


@app.get(
    "/api/v1/status",
    response_model=FullStatusResponse,
    summary="Full dashboard telemetry — single source of truth from config.yaml",
)
async def full_status():
    """
    Returns the complete telemetry payload consumed by the React dashboard.

    * Wallet address is **always** parsed from ``config.yaml →
      network.payout.cold_wallet_address``.
    * Hardware topology is derived from config.
    * Live metrics default to zero until real telemetry services
      are wired in.
    """
    cfg = _get_config().raw
    wallet_address = cfg.get("network", {}).get("payout", {}).get("cold_wallet_address", "")

    uptime_seconds = int(time.time() - _BOOT_TIME)

    # Orchestrator diagnostics (may already be running)
    try:
        orch_diag = _get_orchestrator().get_diagnostics()
        is_running = orch_diag["is_running"]
        total_batches = orch_diag["total_batches"]
    except Exception:
        is_running = False
        total_batches = 0

    return FullStatusResponse(
        entropy=[],
        hardware=_build_hardware_state(cfg),
        profit={
            "btcPrice": 0.0,
            "dailyRevenueBTC": 0.0,
            "dailyRevenueUSD": 0.0,
            "powerCostUSD": 0.0,
            "netProfitUSD": 0.0,
            "hashRate": 0.0,
            "networkDifficulty": 0.0,
            "networkShare": 0.0,
        },
        wallet={
            "address": wallet_address,
            "balance": 0.0,
            "pendingRewards": 0.0,
            "totalMined": 0.0,
            "lastPayout": "N/A",
        },
        mining={
            "totalRounds": total_batches,
            "blocksFound": 0,
            "uptime": uptime_seconds,
            "currentPhase": "Awaiting Telemetry" if not is_running else "Active",
            "stratumConnected": False,
            "lastBlockTime": "N/A",
        },
        terminal=_build_terminal_lines(cfg),
    )
