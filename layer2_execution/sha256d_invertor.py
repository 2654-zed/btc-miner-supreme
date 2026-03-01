"""
sha256d_invertor.py
───────────────────
Core collapse-theoretic double-SHA-256 inverter component.

Despite the name, SHA-256 is a one-way function and cannot be algebraically
inverted.  This module implements the *practical* inversion strategy:

1.  Accept a narrowed nonce cone from the CollapseConeOptimizer.
2.  Construct complete 80-byte block headers for each candidate nonce.
3.  Compute SHA-256d = SHA-256(SHA-256(header)) in bulk.
4.  Compare results against the target difficulty.
5.  Return any nonce whose resulting hash meets the target.

The "collapse" aspect is that the input space has already been massively
pruned by the symbolic guidance layers, so we execute far fewer hash
evaluations than a naïve sweep.

This module provides a pure-Python / NumPy reference path.  For
production throughput, the GPU and FPGA dispatch modules call specialised
kernels that replicate the same logic at hardware speed.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BlockTemplate:
    """Minimal block template fields needed to build the 80-byte header."""
    version: int                   # 4 bytes, little-endian
    prev_block_hash: bytes         # 32 bytes
    merkle_root: bytes             # 32 bytes
    timestamp: int                 # 4 bytes, little-endian
    bits: int                      # 4 bytes (compact difficulty)
    # nonce is the 4-byte field we are searching (bytes 76-79)

    def header_prefix(self) -> bytes:
        """Return the first 76 bytes (everything except the nonce)."""
        return (
            struct.pack("<I", self.version)
            + self.prev_block_hash
            + self.merkle_root
            + struct.pack("<I", self.timestamp)
            + struct.pack("<I", self.bits)
        )

    def full_header(self, nonce: int) -> bytes:
        """Return the complete 80-byte block header."""
        return self.header_prefix() + struct.pack("<I", nonce)

    def target(self) -> int:
        """Derive the 256-bit target from compact 'bits' encoding."""
        exponent = (self.bits >> 24) & 0xFF
        coefficient = self.bits & 0x007FFFFF
        return coefficient * (1 << (8 * (exponent - 3)))

    def target_bytes(self) -> bytes:
        return self.target().to_bytes(32, "big")


@dataclass
class InversionResult:
    """Result of a SHA-256d inversion attempt."""
    found: bool
    nonce: Optional[int] = None
    block_hash: Optional[bytes] = None
    attempts: int = 0
    elapsed_sec: float = 0.0
    hashrate: float = 0.0              # hashes / sec


class SHA256dInvertor:
    """
    Attempts to find a nonce such that SHA256d(header ‖ nonce) < target.
    Operates on pre-narrowed candidate arrays from the collapse cone.
    """

    def __init__(self, mode: str = "collapse") -> None:
        """
        Parameters
        ----------
        mode : str
            "collapse"   – expects pre-optimised candidates
            "bruteforce" – linear sweep over a range
            "hybrid"     – collapse first, then brute-force remainder
        """
        self.mode = mode
        logger.info("SHA256dInvertor initialised  | mode=%s", mode)

    # ── Core hash routine ────────────────────────────────────────────────
    @staticmethod
    def sha256d(data: bytes) -> bytes:
        """Double SHA-256 hash."""
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()

    @staticmethod
    def hash_meets_target(block_hash: bytes, target: int) -> bool:
        """Check whether a hash (big-endian 32 bytes) is below target."""
        hash_int = int.from_bytes(block_hash, "big")
        return hash_int < target

    # ── Collapse-mode inversion ──────────────────────────────────────────
    def invert_collapse(
        self,
        template: BlockTemplate,
        candidates: np.ndarray,
    ) -> InversionResult:
        """
        Try every nonce in *candidates* (uint32 array) against the
        block template.
        """
        target = template.target()
        prefix = template.header_prefix()
        t0 = time.perf_counter()

        for i, nonce in enumerate(candidates):
            nonce_int = int(nonce)
            header = prefix + struct.pack("<I", nonce_int)
            h = self.sha256d(header)
            # Compare hash directly as big-endian 256-bit integer
            if self.hash_meets_target(h, target):
                elapsed = time.perf_counter() - t0
                # Return display-order hash (reversed for Bitcoin convention)
                return InversionResult(
                    found=True,
                    nonce=nonce_int,
                    block_hash=h[::-1],
                    attempts=i + 1,
                    elapsed_sec=elapsed,
                    hashrate=(i + 1) / max(elapsed, 1e-9),
                )

        elapsed = time.perf_counter() - t0
        return InversionResult(
            found=False,
            attempts=len(candidates),
            elapsed_sec=elapsed,
            hashrate=len(candidates) / max(elapsed, 1e-9),
        )

    # ── Brute-force mode ─────────────────────────────────────────────────
    def invert_bruteforce(
        self,
        template: BlockTemplate,
        start: int = 0,
        end: int = 2**32,
        chunk: int = 2**20,
    ) -> InversionResult:
        """Linear sweep from *start* to *end*."""
        target = template.target()
        prefix = template.header_prefix()
        t0 = time.perf_counter()
        total = 0

        for nonce in range(start, end):
            header = prefix + struct.pack("<I", nonce)
            h = self.sha256d(header)
            total += 1
            if self.hash_meets_target(h, target):
                elapsed = time.perf_counter() - t0
                return InversionResult(
                    found=True,
                    nonce=nonce,
                    block_hash=h[::-1],
                    attempts=total,
                    elapsed_sec=elapsed,
                    hashrate=total / max(elapsed, 1e-9),
                )

            if total % chunk == 0:
                elapsed = time.perf_counter() - t0
                logger.debug(
                    "Brute-force progress: %d / %d  (%.1f MH/s)",
                    total, end - start, total / max(elapsed, 1e-9) / 1e6,
                )

        elapsed = time.perf_counter() - t0
        return InversionResult(
            found=False,
            attempts=total,
            elapsed_sec=elapsed,
            hashrate=total / max(elapsed, 1e-9),
        )

    # ── Unified dispatcher ───────────────────────────────────────────────
    def invert(
        self,
        template: BlockTemplate,
        candidates: Optional[np.ndarray] = None,
        bf_start: int = 0,
        bf_end: int = 2**32,
    ) -> InversionResult:
        """
        Run inversion according to configured mode.
        """
        if self.mode == "collapse":
            if candidates is None:
                raise ValueError("collapse mode requires candidates array")
            return self.invert_collapse(template, candidates)

        elif self.mode == "bruteforce":
            return self.invert_bruteforce(template, bf_start, bf_end)

        elif self.mode == "hybrid":
            # Try collapse candidates first, then brute-force the rest
            if candidates is not None:
                result = self.invert_collapse(template, candidates)
                if result.found:
                    return result
                logger.info(
                    "Collapse pass exhausted (%d candidates), falling back to brute-force",
                    len(candidates),
                )
            return self.invert_bruteforce(template, bf_start, bf_end)

        raise ValueError(f"Unknown mode: {self.mode}")
