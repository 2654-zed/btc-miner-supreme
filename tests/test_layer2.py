"""
test_layer2.py
──────────────
Unit tests for the Layer-2 execution & hardware dispatch modules.
"""

import hashlib
import os
import struct
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from layer2_execution.sha256d_invertor import SHA256dInvertor, BlockTemplate, InversionResult
from layer2_execution.gpu_parallel_splitter import GPUParallelSplitter, GPUSplitterConfig
from layer2_execution.fpga_sha_bridge import FPGASHABridge, FPGAConfig


# ═══════════════════════════════════════════════════════════════════════════
# SHA256d Invertor
# ═══════════════════════════════════════════════════════════════════════════

class TestSHA256dInvertor:
    def _make_template(self, difficulty_bits=0x2100ffff):
        """Create a trivially low-difficulty template for testing."""
        return BlockTemplate(
            version=0x20000000,
            prev_block_hash=bytes(32),
            merkle_root=bytes(32),
            timestamp=int(time.time()),
            bits=difficulty_bits,
        )

    def test_sha256d_known_value(self):
        data = b"hello"
        expected = hashlib.sha256(hashlib.sha256(data).digest()).digest()
        assert SHA256dInvertor.sha256d(data) == expected

    def test_header_prefix_length(self):
        tmpl = self._make_template()
        assert len(tmpl.header_prefix()) == 76

    def test_full_header_length(self):
        tmpl = self._make_template()
        assert len(tmpl.full_header(0)) == 80

    def test_target_from_bits(self):
        tmpl = self._make_template(0x1d00ffff)
        target = tmpl.target()
        assert target > 0
        assert target < (1 << 256)

    def test_invert_collapse_finds_easy(self):
        """With trivially low difficulty, almost any nonce works."""
        tmpl = self._make_template(0x2100ffff)
        inv = SHA256dInvertor(mode="collapse")
        candidates = np.arange(0, 100, dtype=np.uint32)
        result = inv.invert(tmpl, candidates)
        assert result.found
        assert result.nonce is not None

    def test_invert_bruteforce_finds_easy(self):
        tmpl = self._make_template(0x2100ffff)
        inv = SHA256dInvertor(mode="bruteforce")
        result = inv.invert(tmpl, bf_start=0, bf_end=100)
        assert result.found

    def test_invert_hybrid(self):
        tmpl = self._make_template(0x2100ffff)
        inv = SHA256dInvertor(mode="hybrid")
        candidates = np.arange(0, 50, dtype=np.uint32)
        result = inv.invert(tmpl, candidates, bf_start=0, bf_end=100)
        assert result.found

    def test_hashrate_reported(self):
        tmpl = self._make_template(0x1f00ffff)
        inv = SHA256dInvertor(mode="collapse")
        candidates = np.arange(0, 100, dtype=np.uint32)
        result = inv.invert(tmpl, candidates)
        assert result.hashrate > 0
        assert result.elapsed_sec >= 0


# ═══════════════════════════════════════════════════════════════════════════
# GPU Parallel Splitter (CPU fallback)
# ═══════════════════════════════════════════════════════════════════════════

class TestGPUSplitter:
    def test_cpu_fallback_finds_easy(self):
        tmpl = BlockTemplate(
            version=0x20000000,
            prev_block_hash=bytes(32),
            merkle_root=bytes(32),
            timestamp=int(time.time()),
            bits=0x2100ffff,
        )
        splitter = GPUParallelSplitter()
        candidates = np.arange(0, 200, dtype=np.uint32)
        winner = splitter.dispatch(
            tmpl.header_prefix(),
            candidates,
            tmpl.target_bytes(),
        )
        assert winner is not None

    def test_streaming_dispatch(self):
        tmpl = BlockTemplate(
            version=0x20000000,
            prev_block_hash=bytes(32),
            merkle_root=bytes(32),
            timestamp=int(time.time()),
            bits=0x2100ffff,
        )
        splitter = GPUParallelSplitter()
        candidates = np.arange(0, 500, dtype=np.uint32)
        winner = splitter.dispatch_streaming(
            tmpl.header_prefix(), candidates, tmpl.target_bytes(), chunk_size=100,
        )
        assert winner is not None


# ═══════════════════════════════════════════════════════════════════════════
# FPGA SHA Bridge (CPU emulation)
# ═══════════════════════════════════════════════════════════════════════════

class TestFPGABridge:
    def test_emulation_finds_easy(self):
        tmpl = BlockTemplate(
            version=0x20000000,
            prev_block_hash=bytes(32),
            merkle_root=bytes(32),
            timestamp=int(time.time()),
            bits=0x2100ffff,
        )
        bridge = FPGASHABridge()
        candidates = np.arange(0, 200, dtype=np.uint32)
        result = bridge.dispatch(
            tmpl.header_prefix(), candidates, tmpl.target_bytes(),
        )
        assert result.found
        assert result.nonce is not None

    def test_pack_unpack_roundtrip(self):
        prefix = os.urandom(76)
        buf = FPGASHABridge.pack_dispatch(prefix, 1000, 5000)
        assert len(buf) == 84  # 76 + 4 + 4
        assert buf[:76] == prefix
