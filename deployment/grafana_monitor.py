"""
grafana_monitor.py
──────────────────
Exports real-time metrics to Prometheus for visualisation in Grafana.

Tracked metrics
───────────────
- btcminer_rounds_total           — counter of mining rounds executed
- btcminer_blocks_found_total     — counter of blocks solved
- btcminer_round_duration_seconds — histogram of round latencies
- btcminer_candidates_per_round   — gauge of candidates dispatched
- btcminer_hashrate               — gauge of effective hashes/sec
- btcminer_entropy_workers        — gauge of active entropy workers
- btcminer_gpu_utilization        — gauge (0-1) of GPU busyness
- btcminer_fpga_utilization       — gauge (0-1) of FPGA busyness
- btcminer_cone_size              — gauge of collapse-cone width
- btcminer_gan_buffer_size        — gauge of GAN replay buffer depth
- btcminer_nonce_success_rate     — gauge of recent hit/miss ratio
- btcminer_cpu_percent            — gauge of host CPU load
- btcminer_memory_percent         — gauge of host RAM usage

The Prometheus HTTP server runs in a background thread and is scraped
by Prometheus at the configured interval.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

# ── Lazy Prometheus import ──────────────────────────────────────────────
_prom = None


def _ensure_prom():
    global _prom
    if _prom is None:
        try:
            import prometheus_client as pc
            _prom = pc
        except ImportError:
            raise RuntimeError(
                "prometheus_client required. Install with: pip install prometheus-client"
            )


@dataclass
class MonitorConfig:
    prometheus_port: int = 9100
    metrics_prefix: str = "btcminer"
    export_interval_sec: int = 5
    grafana_dashboard_uid: str = "btc-collapse-dynamics"


class GrafanaMonitor:
    """
    Prometheus metrics exporter for the BTC Miner Supreme pipeline.
    """

    def __init__(self, cfg: Optional[MonitorConfig] = None) -> None:
        _ensure_prom()
        self.cfg = cfg or MonitorConfig()
        p = self.cfg.metrics_prefix

        # ── Counters ─────────────────────────────────────────────────────
        self.rounds_total = _prom.Counter(
            f"{p}_rounds_total",
            "Total mining rounds executed",
        )
        self.blocks_found = _prom.Counter(
            f"{p}_blocks_found_total",
            "Total blocks solved",
        )

        # ── Histograms ───────────────────────────────────────────────────
        self.round_duration = _prom.Histogram(
            f"{p}_round_duration_seconds",
            "Duration of each mining round",
            buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60),
        )

        # ── Gauges ───────────────────────────────────────────────────────
        self.candidates_gauge = _prom.Gauge(
            f"{p}_candidates_per_round",
            "Number of candidates in last round",
        )
        self.hashrate_gauge = _prom.Gauge(
            f"{p}_hashrate",
            "Effective hash rate (H/s)",
        )
        self.entropy_workers = _prom.Gauge(
            f"{p}_entropy_workers",
            "Active entropy generator workers",
        )
        self.gpu_util = _prom.Gauge(
            f"{p}_gpu_utilization",
            "GPU utilisation fraction",
        )
        self.fpga_util = _prom.Gauge(
            f"{p}_fpga_utilization",
            "FPGA utilisation fraction",
        )
        self.cone_size = _prom.Gauge(
            f"{p}_cone_size",
            "Collapse-cone width (candidates)",
        )
        self.gan_buffer = _prom.Gauge(
            f"{p}_gan_buffer_size",
            "GAN replay buffer depth",
        )
        self.success_rate = _prom.Gauge(
            f"{p}_nonce_success_rate",
            "Recent nonce hit/miss ratio",
        )
        self.cpu_pct = _prom.Gauge(
            f"{p}_cpu_percent",
            "Host CPU usage percentage",
        )
        self.mem_pct = _prom.Gauge(
            f"{p}_memory_percent",
            "Host memory usage percentage",
        )

        # ── Rolling window for success rate ──────────────────────────────
        self._recent_hits = 0
        self._recent_total = 0
        self._window = 1000

        # ── Start Prometheus HTTP server ─────────────────────────────────
        self._server_thread: Optional[threading.Thread] = None
        self._sysmon_thread: Optional[threading.Thread] = None
        self._running = False
        self._start_server()
        self._start_sysmon()

        logger.info(
            "GrafanaMonitor started on :%d  (prefix=%s)",
            self.cfg.prometheus_port, self.cfg.metrics_prefix,
        )

    # ── Prometheus HTTP server ───────────────────────────────────────────
    def _start_server(self) -> None:
        try:
            _prom.start_http_server(self.cfg.prometheus_port)
        except OSError as exc:
            logger.warning("Prometheus server start failed (port busy?): %s", exc)

    # ── System monitor thread ────────────────────────────────────────────
    def _start_sysmon(self) -> None:
        self._running = True
        self._sysmon_thread = threading.Thread(
            target=self._sysmon_loop, daemon=True, name="sysmon"
        )
        self._sysmon_thread.start()

    def _sysmon_loop(self) -> None:
        while self._running:
            try:
                self.cpu_pct.set(psutil.cpu_percent(interval=1.0))
                self.mem_pct.set(psutil.virtual_memory().percent)
            except Exception:
                pass
            time.sleep(self.cfg.export_interval_sec)

    # ── Recording API (called from the mining loop) ──────────────────────
    def record_round(
        self,
        elapsed_sec: float,
        candidates: int,
        found: bool,
        hashrate: float = 0.0,
    ) -> None:
        """Record the outcome of a single mining round."""
        self.rounds_total.inc()
        self.round_duration.observe(elapsed_sec)
        self.candidates_gauge.set(candidates)

        if hashrate > 0:
            self.hashrate_gauge.set(hashrate)

        if found:
            self.blocks_found.inc()
            self._recent_hits += 1

        self._recent_total += 1
        if self._recent_total > self._window:
            # Decay
            self._recent_hits = self._recent_hits // 2
            self._recent_total = self._recent_total // 2

        rate = self._recent_hits / max(self._recent_total, 1)
        self.success_rate.set(rate)

    def set_cone_size(self, size: int) -> None:
        self.cone_size.set(size)

    def set_gan_buffer(self, size: int) -> None:
        self.gan_buffer.set(size)

    def set_entropy_workers(self, count: int) -> None:
        self.entropy_workers.set(count)

    def set_gpu_utilization(self, frac: float) -> None:
        self.gpu_util.set(frac)

    def set_fpga_utilization(self, frac: float) -> None:
        self.fpga_util.set(frac)

    # ── Shutdown ─────────────────────────────────────────────────────────
    def stop(self) -> None:
        self._running = False
