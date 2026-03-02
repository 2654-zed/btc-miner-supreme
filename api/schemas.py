"""
api/schemas.py
──────────────
Pydantic v2 models defining the strict API contract between the
React/Next.js frontend and the Python orchestration backend.

Validation Layers
─────────────────
1. **Pydantic field constraints** — min/max length, regex pattern,
   numeric bounds — intercept malformed payloads at the HTTP edge.
2. **AST sanitiser** (``MathSandbox``) — deep structural validation
   of the formula string's abstract syntax tree.
3. **NumExpr evaluation** — final execution behind the GIL-bypass
   thread-pool.

This module implements Layer 1 only; Layers 2-3 are enforced inside
``api/router.py → infrastructure/math_sandbox.py``.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class HeuristicInjectionRequest(BaseModel):
    """
    Immutable contract for the ``POST /api/v1/inject-heuristic`` endpoint.

    The regex ``pattern`` blocks obvious injection vectors (shell
    metacharacters, quotes, semicolons, backticks) at the Pydantic
    layer, long before the AST sanitiser runs.
    """
    formula: str = Field(
        ...,
        min_length=1,
        max_length=250,
        pattern=r"^[a-zA-Z0-9\s\+\-\*\/\(\)\.\%\^\~\&\|]+$",
        description=(
            "Pure arithmetic expression referencing 'nonce' and optional "
            "constants (pi, e, phi, gamma).  Example: "
            "(nonce ** 1.618) + (1/962) % 0xFFFFFFFF"
        ),
        examples=["(nonce ** 1.618) + (1/962) % 0xFFFFFFFF"],
    )
    batch_size: int = Field(
        default=1_000_000,
        gt=0,
        le=50_000_000,
        description="Number of uint32 nonces to evaluate in one vectorised chunk.",
    )
    target_hardware: str = Field(
        default="CPU",
        pattern=r"^(CPU|FPGA|GPU)$",
        description="Requested execution hardware.  Only 'CPU' supports dynamic formulas.",
    )


class HeuristicInjectionResponse(BaseModel):
    """Structured response returned to the React frontend."""
    success: bool
    message: str
    processed_count: int = 0
    anomalies_detected: int = 0
    elapsed_ms: float = 0.0
    hardware_target: str = ""


class OrchestratorStatusResponse(BaseModel):
    """Snapshot of the Orchestrator's runtime state."""
    is_running: bool
    current_target: str
    total_batches: int
    total_nonces: int
    swap_history_length: int


class FormulaValidationRequest(BaseModel):
    """Lightweight payload for the ``POST /api/v1/validate-formula`` endpoint."""
    formula: str = Field(
        ...,
        min_length=1,
        max_length=250,
        pattern=r"^[a-zA-Z0-9\s\+\-\*\/\(\)\.\%\^\~\&\|]+$",
    )


class FormulaValidationResponse(BaseModel):
    """Result of AST-only validation (no execution)."""
    valid: bool
    error: Optional[str] = None
