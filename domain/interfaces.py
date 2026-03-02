"""
domain/interfaces.py
────────────────────
Abstract Base Class defining the strict contract for all cryptographic
execution engines.  Any new hardware or mathematical approach must
implement the ``HeuristicStrategy`` interface.

This satisfies the Dependency Inversion Principle (the 'D' in SOLID),
ensuring that high-level orchestration modules depend on abstractions
rather than concrete hardware drivers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any

import numpy as np


class HeuristicStrategy(ABC):
    """
    Abstract Base Class defining the strict contract for all
    cryptographic execution engines.  Concrete implementations wrap
    hardware-specific paths (FPGA, GPU, CPU sandbox).
    """

    @abstractmethod
    def execute(self, nonces: np.ndarray) -> np.ndarray:
        """
        Process an array of nonces and return the computed result array.

        Parameters
        ----------
        nonces : np.ndarray
            1-D uint32 array of nonce candidates.

        Returns
        -------
        np.ndarray
            Evaluated results (hashes, scores, or transformed values).
        """
        ...

    @abstractmethod
    def get_hardware_target(self) -> str:
        """Return a human-readable identifier for the execution backend."""
        ...

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Optional override — return runtime diagnostics (temps, utilisation,
        queue depth, etc.) for telemetry dashboards.
        """
        return {"target": self.get_hardware_target()}
