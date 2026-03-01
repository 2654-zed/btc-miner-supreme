"""
qer_gan_memory_replay.py
────────────────────────
Uses Generative Adversarial Network (GAN) models to store, reinforce,
and replay successful entropy pathways from previously solved blocks.

Architecture
------------
- **Generator** : Maps a latent vector z ∈ ℝ^d  →  candidate nonce
  distribution (batch of uint32 values).
- **Discriminator** : Classifies nonce batches as "historically
  successful" vs. "random" — steering the generator toward patterns
  that correlated with past valid block solutions.
- **Replay Buffer** : Circular buffer of (block_height, winning_nonce,
  block_header_prefix) tuples the GAN trains on.

The GAN is trained online every *train_interval_blocks* blocks.
Between training epochs, the generator is used in inference mode to
produce nonce candidates that capture latent structure of previously
successful solutions.
"""

from __future__ import annotations

import logging
import os
import struct
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy torch import (optional at module level) ────────────────────────
_torch = None
_nn = None


def _ensure_torch():
    global _torch, _nn
    if _torch is None:
        try:
            import torch
            import torch.nn as nn
            _torch = torch
            _nn = nn
        except ImportError:
            raise RuntimeError(
                "PyTorch is required for GAN replay. "
                "Install with: pip install torch"
            )


# ── Config ───────────────────────────────────────────────────────────────

@dataclass
class GANConfig:
    latent_dim: int = 128
    gen_hidden: int = 256
    disc_hidden: int = 256
    output_nonces: int = 1024         # nonces per generator forward pass
    replay_buffer_size: int = 1_000_000
    train_interval_blocks: int = 10
    batch_size: int = 512
    learning_rate: float = 2e-4
    train_epochs: int = 50
    model_path: str = "./models/qer_gan.pt"
    device: str = "cuda"               # cuda | cpu


# ── Replay buffer ───────────────────────────────────────────────────────

@dataclass
class ReplayRecord:
    block_height: int
    winning_nonce: int
    header_prefix: bytes              # first 76 bytes of block header


class ReplayBuffer:
    """Fixed-size ring buffer of historical winning nonce records."""

    def __init__(self, maxlen: int = 1_000_000) -> None:
        self._buf: Deque[ReplayRecord] = deque(maxlen=maxlen)

    def push(self, record: ReplayRecord) -> None:
        self._buf.append(record)

    def sample(self, n: int) -> List[ReplayRecord]:
        if len(self._buf) == 0:
            return []
        idx = np.random.randint(0, len(self._buf), size=min(n, len(self._buf)))
        return [self._buf[i] for i in idx]

    def as_nonce_array(self) -> np.ndarray:
        return np.array([r.winning_nonce for r in self._buf], dtype=np.uint32)

    def __len__(self) -> int:
        return len(self._buf)


# ── Generator / Discriminator ───────────────────────────────────────────

def _build_generator(latent_dim: int, hidden: int, output_size: int):
    _ensure_torch()
    return _nn.Sequential(
        _nn.Linear(latent_dim, hidden),
        _nn.LeakyReLU(0.2),
        _nn.BatchNorm1d(hidden),
        _nn.Linear(hidden, hidden * 2),
        _nn.LeakyReLU(0.2),
        _nn.BatchNorm1d(hidden * 2),
        _nn.Linear(hidden * 2, hidden * 4),
        _nn.LeakyReLU(0.2),
        _nn.BatchNorm1d(hidden * 4),
        _nn.Linear(hidden * 4, output_size),
        _nn.Sigmoid(),            # outputs ∈ (0,1), scaled to nonce range
    )


def _build_discriminator(input_size: int, hidden: int):
    _ensure_torch()
    return _nn.Sequential(
        _nn.Linear(input_size, hidden * 4),
        _nn.LeakyReLU(0.2),
        _nn.Dropout(0.3),
        _nn.Linear(hidden * 4, hidden * 2),
        _nn.LeakyReLU(0.2),
        _nn.Dropout(0.3),
        _nn.Linear(hidden * 2, hidden),
        _nn.LeakyReLU(0.2),
        _nn.Linear(hidden, 1),
        _nn.Sigmoid(),
    )


# ── QER-GAN Memory Replay System ────────────────────────────────────────

class QERGANMemoryReplay:
    """
    Trains and queries a GAN that learns the latent distribution of
    historically successful nonces.
    """

    def __init__(self, cfg: Optional[GANConfig] = None) -> None:
        self.cfg = cfg or GANConfig()
        self.buffer = ReplayBuffer(maxlen=self.cfg.replay_buffer_size)
        self._blocks_since_train: int = 0

        _ensure_torch()
        self.device = _torch.device(
            self.cfg.device if _torch.cuda.is_available() else "cpu"
        )

        # Networks
        self.gen = _build_generator(
            self.cfg.latent_dim, self.cfg.gen_hidden, self.cfg.output_nonces
        ).to(self.device)

        self.disc = _build_discriminator(
            self.cfg.output_nonces, self.cfg.disc_hidden
        ).to(self.device)

        # Optimisers
        self.opt_g = _torch.optim.Adam(
            self.gen.parameters(), lr=self.cfg.learning_rate, betas=(0.5, 0.999)
        )
        self.opt_d = _torch.optim.Adam(
            self.disc.parameters(), lr=self.cfg.learning_rate, betas=(0.5, 0.999)
        )

        self.criterion = _nn.BCELoss()
        self._load_checkpoint()
        logger.info(
            "QER-GAN initialised  | device=%s  buffer_cap=%d",
            self.device, self.cfg.replay_buffer_size,
        )

    # ── Checkpoint persistence ───────────────────────────────────────────
    def _load_checkpoint(self) -> None:
        p = Path(self.cfg.model_path)
        if p.exists():
            ckpt = _torch.load(p, map_location=self.device, weights_only=False)
            self.gen.load_state_dict(ckpt["gen"])
            self.disc.load_state_dict(ckpt["disc"])
            logger.info("Loaded GAN checkpoint from %s", p)

    def save_checkpoint(self) -> None:
        p = Path(self.cfg.model_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        _torch.save(
            {"gen": self.gen.state_dict(), "disc": self.disc.state_dict()}, p
        )
        logger.info("Saved GAN checkpoint to %s", p)

    # ── Record a winning nonce ───────────────────────────────────────────
    def record_win(self, block_height: int, nonce: int, header: bytes) -> None:
        """Push a winning nonce into the replay buffer; trigger training if due."""
        self.buffer.push(ReplayRecord(block_height, nonce, header[:76]))
        self._blocks_since_train += 1
        if self._blocks_since_train >= self.cfg.train_interval_blocks:
            self.train()
            self._blocks_since_train = 0

    # ── Training loop ────────────────────────────────────────────────────
    def train(self) -> dict:
        """Run a short training session on the replay buffer contents."""
        if len(self.buffer) < self.cfg.batch_size:
            logger.warning("Buffer too small for training (%d < %d)", len(self.buffer), self.cfg.batch_size)
            return {"d_loss": float("nan"), "g_loss": float("nan")}

        nonce_arr = self.buffer.as_nonce_array().astype(np.float32) / float(2**32)

        total_d, total_g = 0.0, 0.0
        self.gen.train()
        self.disc.train()

        for epoch in range(self.cfg.train_epochs):
            # ── Sample real batch ────────────────────────────────────────
            idx = np.random.randint(0, len(nonce_arr), size=self.cfg.batch_size)
            # Expand each nonce into a "nonce pattern" vector of length output_nonces
            # by adding small perturbations (captures neighbourhood structure)
            centers = nonce_arr[idx]
            offsets = np.random.normal(0, 0.001, (self.cfg.batch_size, self.cfg.output_nonces)).astype(np.float32)
            real_batch = np.clip(centers[:, None] + offsets, 0, 1)
            real_tensor = _torch.tensor(real_batch, device=self.device)

            ones = _torch.ones(self.cfg.batch_size, 1, device=self.device)
            zeros = _torch.zeros(self.cfg.batch_size, 1, device=self.device)

            # ── Discriminator step ───────────────────────────────────────
            self.opt_d.zero_grad()
            d_real = self.disc(real_tensor)
            loss_d_real = self.criterion(d_real, ones)

            z = _torch.randn(self.cfg.batch_size, self.cfg.latent_dim, device=self.device)
            fake = self.gen(z).detach()
            d_fake = self.disc(fake)
            loss_d_fake = self.criterion(d_fake, zeros)

            loss_d = (loss_d_real + loss_d_fake) / 2
            loss_d.backward()
            self.opt_d.step()

            # ── Generator step ───────────────────────────────────────────
            self.opt_g.zero_grad()
            z = _torch.randn(self.cfg.batch_size, self.cfg.latent_dim, device=self.device)
            fake = self.gen(z)
            d_fake = self.disc(fake)
            loss_g = self.criterion(d_fake, ones)
            loss_g.backward()
            self.opt_g.step()

            total_d += loss_d.item()
            total_g += loss_g.item()

        avg_d = total_d / self.cfg.train_epochs
        avg_g = total_g / self.cfg.train_epochs
        logger.info("GAN trained  | D_loss=%.4f  G_loss=%.4f  buffer=%d", avg_d, avg_g, len(self.buffer))
        self.save_checkpoint()
        return {"d_loss": avg_d, "g_loss": avg_g}

    # ── Inference: generate nonce candidates ─────────────────────────────
    def generate(self, count: int) -> np.ndarray:
        """
        Produce *count* nonce candidates from the trained generator.

        Returns uint32 numpy array.
        """
        _ensure_torch()
        self.gen.eval()
        all_nonces: List[np.ndarray] = []
        remaining = count

        with _torch.no_grad():
            while remaining > 0:
                batch = min(remaining, self.cfg.batch_size)
                z = _torch.randn(batch, self.cfg.latent_dim, device=self.device)
                out = self.gen(z).cpu().numpy()              # (batch, output_nonces) in (0,1)
                nonces = (out * (2**32 - 1)).astype(np.uint32).ravel()
                all_nonces.append(nonces)
                remaining -= len(nonces)

        result = np.concatenate(all_nonces)[:count]
        logger.debug("GAN generated %d candidates", len(result))
        return result
