"""
fpga_sha_bridge.py
──────────────────
Converts nonce ranges to FPGA-compatible buffers and offloads hardware-
accelerated SHA-256d hash verification to Alveo UL3524 units via the
Xilinx Runtime (XRT) Python bindings.

Buffer Protocol
───────────────
Each dispatch packet sent to the FPGA contains:

  ┌──────────────────────────────────────────────────────────┐
  │  76-byte header prefix  │  start_nonce (4B)  │  count (4B) │
  └──────────────────────────────────────────────────────────┘

The FPGA iterates nonces [start, start+count) and writes back:

  ┌──────────────────────────────────────────────────────────┐
  │  found (1B)  │  winning_nonce (4B)  │  hash (32B)        │
  └──────────────────────────────────────────────────────────┘

If `found == 0x01`, the winning nonce and hash are valid.

When XRT is not available (e.g., development on a machine without FPGAs)
the bridge falls back to CPU emulation so the pipeline never breaks.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy XRT import ─────────────────────────────────────────────────────
_xrt = None
_HAS_XRT = False


def _try_import_xrt():
    global _xrt, _HAS_XRT
    if _xrt is not None or _HAS_XRT:
        return
    try:
        import pyxrt
        _xrt = pyxrt
        _HAS_XRT = True
        logger.info("XRT Python bindings available")
    except ImportError:
        logger.warning("pyxrt not installed; FPGA bridge will use CPU emulation")


@dataclass
class FPGAConfig:
    device_count: int = 40
    bitstream_path: str = "./bitstreams/sha256d_pipeline.xclbin"
    pipeline_depth: int = 16
    dma_buffer_size_mb: int = 64
    timeout_ms: int = 5000
    clock_mhz: int = 500
    xrt_device_prefix: str = "/dev/xclmgmt"


@dataclass
class FPGAResult:
    found: bool
    nonce: Optional[int] = None
    block_hash: Optional[bytes] = None
    device_id: int = -1
    latency_ms: float = 0.0


class FPGASHABridge:
    """
    Offloads SHA-256d verification to Alveo UL3524 FPGA accelerators.
    Falls back to CPU emulation when XRT is unavailable.
    """

    def __init__(self, cfg: Optional[FPGAConfig] = None) -> None:
        self.cfg = cfg or FPGAConfig()
        _try_import_xrt()

        self._devices: List = []
        self._kernels: List = []

        if _HAS_XRT:
            self._init_xrt_devices()
        else:
            logger.info("FPGA bridge running in CPU-emulation mode")

        logger.info(
            "FPGASHABridge  | XRT=%s  devices=%d  pipeline=%d  buf=%dMB",
            _HAS_XRT, len(self._devices), self.cfg.pipeline_depth,
            self.cfg.dma_buffer_size_mb,
        )

    # ── XRT device initialisation ────────────────────────────────────────
    def _init_xrt_devices(self) -> None:
        """Open XRT device handles and load the bitstream."""
        bitstream = Path(self.cfg.bitstream_path)
        if not bitstream.exists():
            logger.error("Bitstream not found: %s — FPGA dispatch disabled", bitstream)
            return

        for idx in range(self.cfg.device_count):
            try:
                dev = _xrt.device(idx)
                uuid = dev.load_xclbin(str(bitstream))
                krnl = _xrt.kernel(dev, uuid, "sha256d_pipeline")
                self._devices.append(dev)
                self._kernels.append(krnl)
                logger.debug("FPGA device %d ready", idx)
            except Exception as exc:
                logger.warning("Cannot open FPGA device %d: %s", idx, exc)
                break

    # ── Buffer packing ───────────────────────────────────────────────────
    @staticmethod
    def pack_dispatch(header_prefix: bytes, start_nonce: int, count: int) -> bytes:
        """Pack a dispatch buffer for the FPGA."""
        assert len(header_prefix) == 76
        return header_prefix + struct.pack("<II", start_nonce, count)

    @staticmethod
    def unpack_result(buf: bytes) -> FPGAResult:
        """Unpack the FPGA result buffer."""
        found = buf[0]
        nonce = struct.unpack("<I", buf[1:5])[0]
        block_hash = buf[5:37]
        return FPGAResult(
            found=bool(found),
            nonce=nonce if found else None,
            block_hash=block_hash if found else None,
        )

    # ── Dispatch to FPGA ─────────────────────────────────────────────────
    def dispatch(
        self,
        header_prefix: bytes,
        candidates: np.ndarray,
        target_bytes: bytes,
    ) -> FPGAResult:
        """
        Hash *candidates* on FPGA accelerators.  Falls back to CPU
        emulation when XRT is unavailable or no devices are initialised.
        """
        if not self._devices:
            return self._emulate(header_prefix, candidates, target_bytes)

        return self._xrt_dispatch(header_prefix, candidates, target_bytes)

    def _xrt_dispatch(
        self,
        header_prefix: bytes,
        candidates: np.ndarray,
        target_bytes: bytes,
    ) -> FPGAResult:
        """Dispatch work across real FPGA devices via XRT."""
        chunks = np.array_split(candidates, len(self._devices))

        for dev_id, (dev, krnl, chunk) in enumerate(
            zip(self._devices, self._kernels, chunks)
        ):
            if len(chunk) == 0:
                continue

            # Build contiguous nonce range from sorted chunk
            sorted_chunk = np.sort(chunk)
            start_nonce = int(sorted_chunk[0])
            count = int(sorted_chunk[-1]) - start_nonce + 1

            # Allocate DMA buffers
            buf_size = self.cfg.dma_buffer_size_mb * 1024 * 1024
            in_buf = _xrt.bo(dev, buf_size, _xrt.bo.normal, krnl.group_id(0))
            out_buf = _xrt.bo(dev, 37, _xrt.bo.normal, krnl.group_id(1))

            # Pack & transfer input
            payload = self.pack_dispatch(header_prefix, start_nonce, count)
            in_buf.write(payload)
            in_buf.sync(_xrt.xclBOSyncDirection.XCL_BO_SYNC_BO_TO_DEVICE)

            # Execute kernel
            t0 = time.perf_counter()
            run = krnl(in_buf, out_buf, len(target_bytes))
            run.wait(self.cfg.timeout_ms)
            latency = (time.perf_counter() - t0) * 1000

            # Read result
            out_buf.sync(_xrt.xclBOSyncDirection.XCL_BO_SYNC_BO_FROM_DEVICE)
            raw = out_buf.read(37)
            result = self.unpack_result(raw)
            result.device_id = dev_id
            result.latency_ms = latency

            if result.found:
                logger.info(
                    "FPGA device %d found nonce %d in %.1f ms",
                    dev_id, result.nonce, latency,
                )
                return result

        return FPGAResult(found=False)

    # ── CPU emulation fallback ───────────────────────────────────────────
    def _emulate(
        self,
        header_prefix: bytes,
        candidates: np.ndarray,
        target_bytes: bytes,
    ) -> FPGAResult:
        """Software emulation of the FPGA SHA-256d pipeline."""
        target_int = int.from_bytes(target_bytes, "big")
        t0 = time.perf_counter()

        for nonce in candidates:
            nonce_int = int(nonce)
            header = header_prefix + struct.pack("<I", nonce_int)
            h = hashlib.sha256(hashlib.sha256(header).digest()).digest()
            if int.from_bytes(h, "big") < target_int:
                latency = (time.perf_counter() - t0) * 1000
                return FPGAResult(
                    found=True,
                    nonce=nonce_int,
                    block_hash=h[::-1],
                    device_id=-1,
                    latency_ms=latency,
                )

        latency = (time.perf_counter() - t0) * 1000
        logger.debug(
            "FPGA emulation: %d nonces in %.1f ms — no hit", len(candidates), latency,
        )
        return FPGAResult(found=False, latency_ms=latency)

    # ── Diagnostics ──────────────────────────────────────────────────────
    def device_summary(self) -> List[dict]:
        return [
            {"id": i, "type": self.cfg.xrt_device_prefix}
            for i in range(len(self._devices))
        ]
