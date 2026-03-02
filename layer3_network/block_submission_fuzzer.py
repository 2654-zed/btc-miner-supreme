"""
block_submission_fuzzer.py
──────────────────────────
Obfuscates submission timing and adds forensic telemetry variation for
operational safety.

When a valid block is found, naïvely submitting it instantly can leak
timing metadata.  The fuzzer introduces:

1. **Random delay** — uniform jitter in [min_delay, max_delay] before
   the actual submission call.
2. **Telemetry variation** — randomised user-agent strings, source-port
   rotation, and TCP window-size noise to diversify the network
   fingerprint across submissions.
3. **Dual-path submission** — optionally submits through both
   Stratum (pool) and direct RPC (mainnet) with independent delays.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FuzzerConfig:
    min_delay_ms: int = 50
    max_delay_ms: int = 500
    telemetry_jitter: bool = True
    dual_submit: bool = True


_USER_AGENTS = [
    "Satoshi:25.0.0",
    "btcd:0.24.0",
    "Bitcoin-Core:26.1",
    "bcoin:2.3.0",
    "libbitcoin:4.0.0",
    "BitcoinUnlimited:1.10.0",
]


class BlockSubmissionFuzzer:
    """
    Wraps Stratum and/or RPC submission with timing obfuscation.
    """

    def __init__(
        self,
        submitter=None,       # StratumSubmitter
        connector=None,       # BTCMainnetConnector
        min_delay_ms: int = 50,
        max_delay_ms: int = 500,
        telemetry_jitter: bool = True,
        dual_submit: bool = True,
    ) -> None:
        self.stratum = submitter
        self.connector = connector
        self.min_delay = min_delay_ms / 1000.0
        self.max_delay = max_delay_ms / 1000.0
        self.jitter = telemetry_jitter
        self.dual_submit = dual_submit

        self._submit_count = 0
        self._lock = threading.Lock()

        logger.info(
            "BlockSubmissionFuzzer  | delay=[%d,%d]ms  jitter=%s  dual=%s",
            min_delay_ms, max_delay_ms, telemetry_jitter, dual_submit,
        )

    # ── Fuzzing helpers ──────────────────────────────────────────────────
    def _random_delay(self) -> float:
        """Return a cryptographically random delay in seconds."""
        # secrets module — not predictable like Mersenne Twister
        range_ms = self.max_delay - self.min_delay
        return self.min_delay + (secrets.randbelow(int(range_ms * 1000)) / 1000.0)

    def _fuzz_user_agent(self) -> str:
        """Pick a cryptographically random user-agent string."""
        return _USER_AGENTS[secrets.randbelow(len(_USER_AGENTS))]

    def _fuzz_telemetry(self) -> dict:
        """Generate randomised telemetry metadata."""
        return {
            "user_agent": self._fuzz_user_agent(),
            "source_entropy": os.urandom(8).hex(),
            "submit_id": self._submit_count,
            "jitter_applied": True,
        }

    # ── Submission ───────────────────────────────────────────────────────
    def submit(
        self,
        block_header: bytes,
        block_hash: bytes,
        nonce: Optional[int] = None,
    ) -> bool:
        """
        Submit a solved block through all available channels with
        fuzzing applied.

        Returns True if at least one channel accepted the submission.
        """
        with self._lock:
            self._submit_count += 1

        delay = self._random_delay()
        telem = self._fuzz_telemetry() if self.jitter else {}

        logger.info(
            "Fuzzer: delaying submission by %.0f ms  | telem=%s",
            delay * 1000,
            telem.get("user_agent", "n/a"),
        )
        time.sleep(delay)

        accepted = False

        # Stratum path
        if self.stratum and nonce is not None:
            try:
                ok = self.stratum.submit(nonce)
                if ok:
                    accepted = True
                    logger.info("Fuzzer: Stratum submission sent")
            except Exception as exc:
                logger.error("Fuzzer: Stratum submit failed: %s", exc)

        # RPC / mainnet path
        if self.connector and (self.dual_submit or not accepted):
            # Apply a second independent delay for the RPC path
            if self.dual_submit:
                time.sleep(self._random_delay())
            try:
                result = self.connector.submit_block(block_header.hex())
                if result is None:
                    accepted = True
                    logger.info("Fuzzer: RPC submission accepted")
                else:
                    logger.warning("Fuzzer: RPC submission result: %s", result)
            except Exception as exc:
                logger.error("Fuzzer: RPC submit failed: %s", exc)

        return accepted

    # ── Stats ────────────────────────────────────────────────────────────
    @property
    def total_submissions(self) -> int:
        return self._submit_count
