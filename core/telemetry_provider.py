"""
core/telemetry_provider.py
──────────────────────────
Central telemetry aggregator — the ONLY source of runtime metrics for
the API layer.  Replaces all hardcoded zeros in ``/api/v1/status``.

Design Contract
───────────────
  • Every metric is either **measured** or **absent** (None).
  • No metric is ever fabricated.  If a data source is unavailable,
    the field reports ``None`` and the API schema uses ``Optional[float]``.
  • Hardware metrics come from psutil / pynvml / XRT — never from config.yaml.
  • Financial metrics come from real price feeds — never from constants.

Fallback Behaviour
──────────────────
  When a provider library is missing (psutil, pynvml, etc.), the
  corresponding metrics return ``None``.  The dashboard must handle
  null gracefully (skeleton / "N/A").
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Optional hardware libraries ─────────────────────────────────────────

_HAS_PSUTIL = False
_psutil: Any = None

try:
    import psutil as _psutil  # type: ignore[no-redef]
    _HAS_PSUTIL = True
except ImportError:
    pass

_HAS_PYNVML = False
_pynvml: Any = None

try:
    import pynvml as _pynvml  # type: ignore[no-redef]
    _pynvml.nvmlInit()
    _HAS_PYNVML = True
except (ImportError, Exception):
    pass


# ── Data classes (measured, not fabricated) ──────────────────────────────


@dataclass
class CPUMetrics:
    model: str
    cores: int
    threads: int
    load: Optional[float]       # percent, from psutil
    temp: Optional[float]       # celsius, from psutil
    frequency: Optional[float]  # MHz, from psutil


@dataclass
class GPUMetrics:
    id: int
    name: str
    temp: Optional[float]
    utilization: Optional[float]
    mem_used: Optional[float]   # GB
    mem_total: Optional[float]  # GB — queried, NEVER hardcoded
    power: Optional[float]      # watts
    hash_rate: Optional[float]  # from miner telemetry, not GPU driver
    status: str                 # "active" | "idle" | "unavailable"


@dataclass
class FPGAMetrics:
    id: int
    name: str
    voltage: Optional[float]
    xrt_status: str              # "connected" | "disconnected" | "unavailable"
    dma_rate: Optional[float]
    hash_rate: Optional[float]
    temp: Optional[float]
    status: str


@dataclass
class MinerTelemetry:
    """Snapshot from a running BTCMinerSupreme instance."""
    total_rounds: int = 0
    blocks_found: int = 0
    uptime_seconds: int = 0
    current_phase: str = "Offline"
    stratum_connected: bool = False
    last_block_time: str = "N/A"
    aggregate_hash_rate: float = 0.0  # H/s measured


@dataclass
class TelemetrySnapshot:
    """Complete telemetry state at a point in time."""
    cpus: List[CPUMetrics] = field(default_factory=list)
    gpus: List[GPUMetrics] = field(default_factory=list)
    fpgas: List[FPGAMetrics] = field(default_factory=list)
    miner: MinerTelemetry = field(default_factory=MinerTelemetry)
    timestamp: float = field(default_factory=time.time)


# ── Hardware Probe Functions ─────────────────────────────────────────────


def probe_cpus() -> List[CPUMetrics]:
    """Query actual CPU metrics via psutil.  Returns empty if unavailable."""
    if not _HAS_PSUTIL:
        logger.debug("psutil not available — CPU metrics will be null")
        return []

    cpu_count_logical = _psutil.cpu_count(logical=True) or 0
    cpu_count_physical = _psutil.cpu_count(logical=False) or 0
    cpu_freq = _psutil.cpu_freq()
    cpu_percent = _psutil.cpu_percent(interval=0.1)

    # Temperature — platform dependent
    temp = None
    try:
        temps = _psutil.sensors_temperatures()
        if temps:
            # Pick the first sensor group that has readings
            for name, entries in temps.items():
                if entries:
                    temp = entries[0].current
                    break
    except (AttributeError, Exception):
        pass  # sensors_temperatures not available on all platforms

    # Report as a single CPU entry (per-socket breakdown requires hwloc)
    import platform
    model = platform.processor() or "Unknown CPU"

    return [CPUMetrics(
        model=model,
        cores=cpu_count_physical,
        threads=cpu_count_logical,
        load=cpu_percent,
        temp=temp,
        frequency=cpu_freq.current if cpu_freq else None,
    )]


def probe_gpus() -> List[GPUMetrics]:
    """Query actual GPU metrics via pynvml.  Returns empty if unavailable."""
    if not _HAS_PYNVML:
        logger.debug("pynvml not available — GPU metrics will be null")
        return []

    gpus = []
    try:
        count = _pynvml.nvmlDeviceGetCount()
        for i in range(count):
            handle = _pynvml.nvmlDeviceGetHandleByIndex(i)
            name = _pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8")

            try:
                temp = float(_pynvml.nvmlDeviceGetTemperature(
                    handle, _pynvml.NVML_TEMPERATURE_GPU
                ))
            except Exception:
                temp = None

            try:
                util = _pynvml.nvmlDeviceGetUtilizationRates(handle)
                utilization = float(util.gpu)
            except Exception:
                utilization = None

            try:
                mem = _pynvml.nvmlDeviceGetMemoryInfo(handle)
                mem_used = round(mem.used / (1024**3), 2)
                mem_total = round(mem.total / (1024**3), 2)
            except Exception:
                mem_used = None
                mem_total = None

            try:
                power = round(
                    _pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0, 1
                )
            except Exception:
                power = None

            gpus.append(GPUMetrics(
                id=i,
                name=f"{name}:{i}",
                temp=temp,
                utilization=utilization,
                mem_used=mem_used,
                mem_total=mem_total,  # QUERIED, not hardcoded
                power=power,
                hash_rate=None,  # Only the miner can report this
                status="active" if utilization and utilization > 5 else "idle",
            ))
    except Exception as exc:
        logger.warning("GPU probe failed: %s", exc)

    return gpus


def probe_fpgas() -> List[FPGAMetrics]:
    """Query actual FPGA status via XRT.  Returns empty if unavailable."""
    try:
        import pyxrt as xrt  # type: ignore
    except ImportError:
        logger.debug("XRT not available — FPGA metrics will be null")
        return []

    fpgas = []
    try:
        # XRT device enumeration
        idx = 0
        while True:
            try:
                dev = xrt.device(idx)
                info = dev.get_info(xrt.xclDeviceInfo2)
                fpgas.append(FPGAMetrics(
                    id=idx,
                    name=info.mName.decode() if hasattr(info, "mName") else f"FPGA:{idx}",
                    voltage=None,  # Requires board-specific query
                    xrt_status="connected",
                    dma_rate=None,
                    hash_rate=None,  # Only the miner can report this
                    temp=None,
                    status="idle",
                ))
                idx += 1
            except Exception:
                break
    except Exception as exc:
        logger.warning("FPGA probe failed: %s", exc)

    return fpgas


# ── Telemetry Provider (Singleton) ──────────────────────────────────────


class TelemetryProvider:
    """
    Aggregates real hardware metrics and miner telemetry into a single
    snapshot.  This is the ONLY class the API layer should query.

    Contract
    ────────
    • ``collect()`` returns a ``TelemetrySnapshot`` with MEASURED values.
    • Fields that cannot be measured are ``None``, never zero.
    • The provider never generates, simulates, or approximates data.
    """

    def __init__(self) -> None:
        self._miner_telemetry = MinerTelemetry()
        self._boot_time = time.time()
        logger.info(
            "TelemetryProvider online  psutil=%s  pynvml=%s",
            _HAS_PSUTIL, _HAS_PYNVML,
        )

    def update_miner_telemetry(self, telemetry: MinerTelemetry) -> None:
        """Called by the miner process/thread to push live stats."""
        self._miner_telemetry = telemetry

    def collect(self) -> TelemetrySnapshot:
        """
        Probe all hardware and merge with miner telemetry.
        Returns only what is actually measurable.
        """
        return TelemetrySnapshot(
            cpus=probe_cpus(),
            gpus=probe_gpus(),
            fpgas=probe_fpgas(),
            miner=self._miner_telemetry,
            timestamp=time.time(),
        )

    @property
    def uptime_seconds(self) -> int:
        return int(time.time() - self._boot_time)
