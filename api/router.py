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
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    FormulaValidationRequest,
    FormulaValidationResponse,
    HeuristicInjectionRequest,
    HeuristicInjectionResponse,
    OrchestratorStatusResponse,
)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
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
