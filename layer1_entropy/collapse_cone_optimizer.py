"""
collapse_cone_optimizer.py
──────────────────────────
Combines the outputs from the entropy weaver, zeta router, GAN replay,
and observer ladders to generate the final optimised "entropy cone" for
hardware execution.

The collapse cone is a narrowed, prioritised subset of the full 2^32
nonce space.  It is expressed as an ordered array of uint32 nonce
candidates ready for dispatch to the GPU splitter or FPGA bridge.

Merge Strategies
────────────────
- **weighted_vote** (default): Each source casts a weighted ballot for
  its candidates; final ranking is the sum of normalised votes.
- **intersection**: Only nonces endorsed by ALL sources survive.
- **union**: All unique candidates from every source, ranked by best
  individual score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from layer1_entropy.griffin962_entropy_weaver import GriffinEntropyWeaver, GriffinConfig
from layer1_entropy.zeta_aligned_symbolic_router import ZetaAlignedSymbolicRouter, ZetaRouterConfig
from layer1_entropy.qer_gan_memory_replay import QERGANMemoryReplay, GANConfig
from layer1_entropy.observer_ladder_replay import ObserverLadder, ObserverConfig

logger = logging.getLogger(__name__)


@dataclass
class CollapseConeConfig:
    cone_angle_deg: float = 15.0
    merge_strategy: str = "weighted_vote"     # weighted_vote | intersection | union
    max_candidates: int = 2**26               # ≈ 67 M nonces
    source_weights: Dict[str, float] = None   # override per-source vote weight

    def __post_init__(self):
        if self.source_weights is None:
            self.source_weights = {
                "griffin": 0.30,
                "zeta": 0.20,
                "gan": 0.30,
                "observer": 0.20,
            }


class CollapseConeOptimizer:
    """
    Fuses all Layer-1 entropy sources into an optimised nonce dispatch
    cone for Layer-2 hardware execution.
    """

    def __init__(
        self,
        cfg: Optional[CollapseConeConfig] = None,
        griffin: Optional[GriffinEntropyWeaver] = None,
        zeta: Optional[ZetaAlignedSymbolicRouter] = None,
        gan: Optional[QERGANMemoryReplay] = None,
        observer: Optional[ObserverLadder] = None,
    ) -> None:
        self.cfg = cfg or CollapseConeConfig()
        self.griffin = griffin or GriffinEntropyWeaver()
        self.zeta = zeta or ZetaAlignedSymbolicRouter()
        self.gan = gan
        self.observer = observer or ObserverLadder()

        # Cone aperture → fraction of nonce space to explore
        self._cone_fraction = self.cfg.cone_angle_deg / 360.0
        logger.info(
            "CollapseConeOptimizer  | strategy=%s  max_cand=%d  cone_frac=%.4f",
            self.cfg.merge_strategy, self.cfg.max_candidates, self._cone_fraction,
        )

    # ── Public API ───────────────────────────────────────────────────────
    def optimise(self, raw_count: Optional[int] = None) -> np.ndarray:
        """
        Generate and fuse nonce candidates from all sources.

        Parameters
        ----------
        raw_count : int, optional
            Number of candidates to request from each source before
            merging.  Defaults to 2× max_candidates.

        Returns
        -------
        np.ndarray of uint32  —  the optimised collapse cone, sorted
        by descending composite score and capped at max_candidates.
        """
        if raw_count is None:
            raw_count = min(self.cfg.max_candidates * 2, 2**27)

        sources: Dict[str, np.ndarray] = {}
        scores: Dict[str, np.ndarray] = {}

        # ── Source 1: Griffin weaver ─────────────────────────────────────
        g_cands = self.griffin.weave(raw_count)
        sources["griffin"] = g_cands
        scores["griffin"] = self.griffin._score(g_cands)

        # ── Source 2: Zeta router (filter Griffin output) ────────────────
        z_scores = self.zeta.score(g_cands)
        sources["zeta"] = g_cands  # same candidates, different scores
        scores["zeta"] = z_scores

        # ── Source 3: GAN replay ─────────────────────────────────────────
        if self.gan is not None:
            try:
                gan_cands = self.gan.generate(raw_count)
                sources["gan"] = gan_cands
                scores["gan"] = self.griffin._score(gan_cands)  # cross-score
            except Exception as exc:
                logger.warning("GAN generation skipped: %s", exc)

        # ── Source 4: Observer ladder re-score ───────────────────────────
        obs_scores = self.observer.score(g_cands)
        sources["observer"] = g_cands
        scores["observer"] = obs_scores

        # ── Merge ────────────────────────────────────────────────────────
        if self.cfg.merge_strategy == "weighted_vote":
            return self._merge_weighted_vote(sources, scores)
        elif self.cfg.merge_strategy == "intersection":
            return self._merge_intersection(sources, scores)
        elif self.cfg.merge_strategy == "union":
            return self._merge_union(sources, scores)
        else:
            raise ValueError(f"Unknown merge strategy: {self.cfg.merge_strategy}")

    # ── Merge implementations ────────────────────────────────────────────
    def _merge_weighted_vote(
        self,
        sources: Dict[str, np.ndarray],
        scores: Dict[str, np.ndarray],
    ) -> np.ndarray:
        """Weighted-vote fusion: accumulate normalised scores per nonce."""
        vote_map: Dict[int, float] = {}
        w = self.cfg.source_weights

        for name, cands in sources.items():
            weight = w.get(name, 0.25)
            sc = scores.get(name, np.ones(len(cands)))
            for nonce, s in zip(cands.tolist(), sc.tolist()):
                vote_map[nonce] = vote_map.get(nonce, 0.0) + weight * s

        # Sort descending by vote
        ranked = sorted(vote_map.items(), key=lambda x: -x[1])
        top = ranked[: self.cfg.max_candidates]
        result = np.array([n for n, _ in top], dtype=np.uint32)
        logger.info("WeightedVote merge → %d candidates (from %d unique)", len(result), len(vote_map))
        return result

    def _merge_intersection(
        self,
        sources: Dict[str, np.ndarray],
        scores: Dict[str, np.ndarray],
    ) -> np.ndarray:
        """Keep only nonces present in ALL sources."""
        sets = [set(c.tolist()) for c in sources.values()]
        common = sets[0]
        for s in sets[1:]:
            common &= s
        result = np.array(list(common), dtype=np.uint32)[: self.cfg.max_candidates]
        logger.info("Intersection merge → %d candidates", len(result))
        return result

    def _merge_union(
        self,
        sources: Dict[str, np.ndarray],
        scores: Dict[str, np.ndarray],
    ) -> np.ndarray:
        """Union of all sources, ranked by best individual score."""
        best: Dict[int, float] = {}
        for name, cands in sources.items():
            sc = scores.get(name, np.ones(len(cands)))
            for nonce, s in zip(cands.tolist(), sc.tolist()):
                if nonce not in best or s > best[nonce]:
                    best[nonce] = s

        ranked = sorted(best.items(), key=lambda x: -x[1])
        top = ranked[: self.cfg.max_candidates]
        result = np.array([n for n, _ in top], dtype=np.uint32)
        logger.info("Union merge → %d candidates (from %d unique)", len(result), len(best))
        return result

    # ── Telemetry helpers ────────────────────────────────────────────────
    def source_diagnostics(self) -> Dict[str, dict]:
        """Gather health metrics from each entropy source."""
        diag: Dict[str, dict] = {
            "griffin": {"basins": len(self.griffin.basins)},
            "zeta": {"zeros_loaded": len(self.zeta._zeros)},
            "observer": {"layers": self.observer.layer_summary()},
        }
        if self.gan is not None:
            diag["gan"] = {"buffer_size": len(self.gan.buffer)}
        return diag
