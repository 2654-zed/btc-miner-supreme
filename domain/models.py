"""
domain/models.py
────────────────
Shared data structures used across the orchestration pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class NonceBatch:
    """An immutable parcel of nonce candidates produced by Layer 1."""
    nonces: "np.ndarray"
    batch_id: int = 0
    created_at: float = field(default_factory=time.time)
    source: str = "collapse_cone"


@dataclass
class ExecutionResult:
    """Container returned by a HeuristicStrategy after processing."""
    results: "np.ndarray"
    anomalies: int = 0                # NaN / Inf count
    hardware_target: str = ""
    elapsed_ms: float = 0.0
    batch_id: int = 0


@dataclass
class StrategySwapEvent:
    """Audit record emitted when the Orchestrator hot-swaps strategies."""
    previous_target: str
    new_target: str
    reason: str
    timestamp: float = field(default_factory=time.time)
