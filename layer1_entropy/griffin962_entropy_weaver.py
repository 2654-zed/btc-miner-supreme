"""
griffin962_entropy_weaver.py
────────────────────────────
Injects symbolic entropy tuned to the Griffin-class attractor constant (1/962)
to collapse the nonce space toward high-likelihood target basins.

The weaver generates biased nonce candidates from a TrueRandom / os.urandom
seed, modulated by a harmonic series built on the 1/962 constant.  Candidates
cluster around "basins" whose spacing mirrors the harmonic overtones, so
downstream layers receive a pre-narrowed search cone rather than a flat
uniform distribution over 2^32.
"""

from __future__ import annotations

import hashlib
import os
import struct
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Griffin Constants ────────────────────────────────────────────────────
GRIFFIN_CONSTANT: float = 1.0 / 962.0           # ≈ 0.001039501
GOLDEN_RATIO: float = (1.0 + np.sqrt(5)) / 2.0  # φ
EULER_MASCHERONI: float = 0.5772156649015329


@dataclass
class GriffinConfig:
    """Tunable parameters for the entropy weaver."""
    attractor_constant: float = GRIFFIN_CONSTANT
    basin_width: float = 0.0005
    harmonic_depth: int = 8
    seed_mode: str = "truerandom"        # truerandom | urandom | deterministic
    deterministic_seed: Optional[int] = None
    nonce_space: int = 2**32


@dataclass
class EntropyBasin:
    """Represents a single attractor basin in the nonce space."""
    center: int
    radius: int
    weight: float


class GriffinEntropyWeaver:
    """
    Generates nonce candidates biased toward Griffin-attractor basins.

    The full 2^32 nonce space is partitioned into basins whose centers
    are determined by the harmonic series

        c_k = floor(N * frac(k / 962 * φ))    for k = 1 … harmonic_depth

    Each basin has a Gaussian-weighted profile; the weaver emits
    pre-scored (nonce, weight) pairs that downstream layers use for
    prioritized dispatch.
    """

    def __init__(self, cfg: Optional[GriffinConfig] = None) -> None:
        self.cfg = cfg or GriffinConfig()
        self._rng = self._init_rng()
        self.basins: List[EntropyBasin] = self._compute_basins()
        logger.info(
            "GriffinEntropyWeaver initialised  | basins=%d  seed_mode=%s",
            len(self.basins), self.cfg.seed_mode,
        )

    # ── RNG bootstrap ────────────────────────────────────────────────────
    def _init_rng(self) -> np.random.Generator:
        if self.cfg.seed_mode == "deterministic" and self.cfg.deterministic_seed is not None:
            return np.random.default_rng(self.cfg.deterministic_seed)

        # TrueRandom / urandom: harvest 32 bytes of OS entropy
        raw = os.urandom(32)
        seed_int = int.from_bytes(raw, "big") % (2**128)
        return np.random.default_rng(seed_int)

    # ── Basin calculation ────────────────────────────────────────────────
    def _compute_basins(self) -> List[EntropyBasin]:
        """Derive attractor basins from harmonic series on 1/962."""
        N = self.cfg.nonce_space
        basins: List[EntropyBasin] = []

        for k in range(1, self.cfg.harmonic_depth + 1):
            # Fractional part of k * attractor * φ gives pseudo-uniform
            # but symbolically meaningful spread over [0, 1).
            frac_val = (k * self.cfg.attractor_constant * GOLDEN_RATIO) % 1.0
            center = int(N * frac_val) % N

            # Basin radius shrinks with harmonic index → higher harmonics
            # are tighter, more precise "collapse" zones.
            radius = max(1, int(N * self.cfg.basin_width / k))

            # Weight includes Euler-Mascheroni damping
            weight = np.exp(-EULER_MASCHERONI * k / self.cfg.harmonic_depth)

            basins.append(EntropyBasin(center=center, radius=radius, weight=weight))
            logger.debug(
                "  basin k=%d  center=%010d  radius=%d  weight=%.6f",
                k, center, radius, weight,
            )

        # Normalise weights
        total = sum(b.weight for b in basins)
        for b in basins:
            b.weight /= total

        return basins

    # ── Candidate generation ─────────────────────────────────────────────
    def weave(self, count: int) -> np.ndarray:
        """
        Generate *count* nonce candidates biased toward attractor basins.

        Returns
        -------
        np.ndarray of shape (count,) with dtype uint32.
        """
        N = self.cfg.nonce_space
        weights = np.array([b.weight for b in self.basins])
        centers = np.array([b.center for b in self.basins], dtype=np.int64)
        radii = np.array([b.radius for b in self.basins], dtype=np.int64)

        # Choose basin indices proportional to weight
        basin_idx = self._rng.choice(len(self.basins), size=count, p=weights)

        # Gaussian offsets within each basin
        offsets = self._rng.standard_normal(count) * radii[basin_idx] / 3.0

        candidates = (centers[basin_idx] + offsets.astype(np.int64)) % N
        candidates = candidates.astype(np.uint32)

        logger.debug("Wove %d candidates across %d basins", count, len(self.basins))
        return candidates

    def weave_scored(self, count: int) -> List[tuple]:
        """Return (nonce, score) pairs where score ∈ (0,1] reflects basin affinity."""
        candidates = self.weave(count)
        scores = self._score(candidates)
        return list(zip(candidates.tolist(), scores.tolist()))

    # ── Scoring ──────────────────────────────────────────────────────────
    def _score(self, nonces: np.ndarray) -> np.ndarray:
        """Score each nonce by proximity to nearest basin center."""
        N = self.cfg.nonce_space
        best = np.zeros(len(nonces), dtype=np.float64)
        for b in self.basins:
            # Circular distance on [0, N)
            dist = np.minimum(
                np.abs(nonces.astype(np.int64) - b.center),
                N - np.abs(nonces.astype(np.int64) - b.center),
            )
            gaussian = b.weight * np.exp(-0.5 * (dist / max(b.radius, 1)) ** 2)
            best = np.maximum(best, gaussian)
        # Normalise to [0, 1]
        mx = best.max()
        if mx > 0:
            best /= mx
        return best

    # ── Reseeding (for multi-block sessions) ─────────────────────────────
    def reseed(self, block_hash: bytes) -> None:
        """Mix previous block hash into RNG state for fresh entropy."""
        digest = hashlib.sha256(block_hash).digest()
        new_seed = int.from_bytes(digest[:16], "big")
        self._rng = np.random.default_rng(new_seed)
        self.basins = self._compute_basins()
        logger.info("Reseeded weaver with block_hash=%s", block_hash[:8].hex())
