"""
btc_miner_supreme.py
────────────────────
Top-level master runner that wires all the entropy optimisation filters
and hardware dispatch layers together into a continuous mining loop.

Lifecycle
─────────
1. Fetch block template from Bitcoin RPC / Stratum.
2. Run the Layer-1 collapse-cone optimiser to produce a narrowed nonce
   candidate set.
3. Dispatch candidates through the GPU parallel splitter first (fast
   first-pass), then FPGA bridge (deep verification).
4. On success → submit block via Stratum / mainnet, record replay,
   trigger payout sweep.
5. On miss → reseed entropy, fetch fresh template, repeat.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

# Layer 1
from layer1_entropy.griffin962_entropy_weaver import GriffinEntropyWeaver, GriffinConfig
from layer1_entropy.zeta_aligned_symbolic_router import ZetaAlignedSymbolicRouter, ZetaRouterConfig
from layer1_entropy.qer_gan_memory_replay import QERGANMemoryReplay, GANConfig
from layer1_entropy.observer_ladder_replay import ObserverLadder, ObserverConfig
from layer1_entropy.collapse_cone_optimizer import CollapseConeOptimizer, CollapseConeConfig

# Layer 2
from layer2_execution.sha256d_invertor import SHA256dInvertor, BlockTemplate
from layer2_execution.gpu_parallel_splitter import GPUParallelSplitter, GPUSplitterConfig
from layer2_execution.fpga_sha_bridge import FPGASHABridge, FPGAConfig

logger = logging.getLogger(__name__)


@dataclass
class MinerConfig:
    """Aggregated configuration loaded from config.yaml."""
    griffin: GriffinConfig
    zeta: ZetaRouterConfig
    gan: GANConfig
    observer: ObserverConfig
    cone: CollapseConeConfig
    gpu: GPUSplitterConfig
    fpga: FPGAConfig
    sha256d_mode: str = "hybrid"
    poll_interval_sec: float = 0.5
    max_rounds_per_template: int = 50


def load_config(path: str = "config.yaml") -> MinerConfig:
    """Parse config.yaml into typed dataclass."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    ent = raw.get("entropy", {})
    exe = raw.get("execution", {})
    hw = raw.get("hardware", {})

    griffin_cfg = GriffinConfig(
        attractor_constant=ent.get("griffin", {}).get("attractor_constant", 1 / 962),
        basin_width=ent.get("griffin", {}).get("basin_width", 0.0005),
        harmonic_depth=ent.get("griffin", {}).get("harmonic_depth", 8),
        seed_mode=ent.get("griffin", {}).get("seed_mode", "truerandom"),
    )

    zeta_cfg = ZetaRouterConfig(
        imaginary_range=tuple(ent.get("zeta", {}).get("imaginary_range", [14.134, 10000.0])),
        zero_cache_size=ent.get("zeta", {}).get("zero_cache_size", 100000),
        filter_tolerance=ent.get("zeta", {}).get("filter_tolerance", 1e-6),
    )

    gan_cfg = GANConfig(
        latent_dim=ent.get("gan", {}).get("latent_dim", 128),
        replay_buffer_size=ent.get("gan", {}).get("replay_buffer_size", 1000000),
        train_interval_blocks=ent.get("gan", {}).get("train_interval_blocks", 10),
        batch_size=ent.get("gan", {}).get("batch_size", 512),
        learning_rate=ent.get("gan", {}).get("learning_rate", 0.0002),
        model_path=ent.get("gan", {}).get("model_path", "./models/qer_gan.pt"),
    )

    observer_cfg = ObserverConfig(
        recursion_depth=ent.get("observer", {}).get("recursion_depth", 5),
        convergence_threshold=ent.get("observer", {}).get("convergence_threshold", 0.85),
        ladder_width=ent.get("observer", {}).get("ladder_width", 32),
        history_window=ent.get("observer", {}).get("history_window", 500),
    )

    cone_cfg = CollapseConeConfig(
        cone_angle_deg=ent.get("collapse_cone", {}).get("cone_angle_deg", 15.0),
        merge_strategy=ent.get("collapse_cone", {}).get("merge_strategy", "weighted_vote"),
        max_candidates=ent.get("collapse_cone", {}).get("max_candidates", 2**26),
    )

    gpu_cfg = GPUSplitterConfig(
        threads_per_block=hw.get("gpu", {}).get("threads_per_block", 256),
        blocks_per_grid=hw.get("gpu", {}).get("blocks_per_grid", 1024),
        stream_count=exe.get("gpu_dispatch", {}).get("stream_count", 4),
        pinned_memory=exe.get("gpu_dispatch", {}).get("pinned_memory", True),
        batch_overlap=exe.get("gpu_dispatch", {}).get("batch_overlap", True),
    )

    fpga_cfg = FPGAConfig(
        device_count=hw.get("fpga", {}).get("count", 40),
        bitstream_path=hw.get("fpga", {}).get("bitstream_path", "./bitstreams/sha256d_pipeline.xclbin"),
        pipeline_depth=exe.get("fpga_dispatch", {}).get("pipeline_depth", 16),
        dma_buffer_size_mb=exe.get("fpga_dispatch", {}).get("dma_buffer_size_mb", 64),
        timeout_ms=exe.get("fpga_dispatch", {}).get("timeout_ms", 5000),
    )

    return MinerConfig(
        griffin=griffin_cfg,
        zeta=zeta_cfg,
        gan=gan_cfg,
        observer=observer_cfg,
        cone=cone_cfg,
        gpu=gpu_cfg,
        fpga=fpga_cfg,
        sha256d_mode=exe.get("sha256d", {}).get("mode", "hybrid"),
    )


class BTCMinerSupreme:
    """
    Master orchestrator — the main mining loop.
    """

    def __init__(self, cfg: MinerConfig) -> None:
        self.cfg = cfg
        self._running = False

        # ── Layer 1 ──────────────────────────────────────────────────────
        self.griffin = GriffinEntropyWeaver(cfg.griffin)
        self.zeta = ZetaAlignedSymbolicRouter(cfg.zeta)
        try:
            self.gan = QERGANMemoryReplay(cfg.gan)
        except Exception as exc:
            logger.warning("GAN init failed (%s) — running without GAN replay", exc)
            self.gan = None
        self.observer = ObserverLadder(cfg.observer)
        self.cone = CollapseConeOptimizer(
            cfg=cfg.cone,
            griffin=self.griffin,
            zeta=self.zeta,
            gan=self.gan,
            observer=self.observer,
        )

        # ── Layer 2 ──────────────────────────────────────────────────────
        self.invertor = SHA256dInvertor(mode=cfg.sha256d_mode)
        self.gpu = GPUParallelSplitter(cfg.gpu)
        self.fpga = FPGASHABridge(cfg.fpga)

        # ── Layer 3 (injected by the run script) ─────────────────────────
        self.connector = None      # BTCMainnetConnector
        self.stratum = None        # StratumSubmitter
        self.fuzzer = None         # BlockSubmissionFuzzer
        self.payout = None         # WalletPayoutAutomation
        self.monitor = None        # GrafanaMonitor

        # stats
        self.rounds = 0
        self.blocks_found = 0

    # ── Graceful shutdown ────────────────────────────────────────────────
    def _handle_signal(self, sig, frame):
        logger.info("Shutdown signal received (%s)", sig)
        self._running = False

    # ── Template acquisition ─────────────────────────────────────────────
    def _get_template(self) -> Optional[BlockTemplate]:
        """Fetch block template from the connector or Stratum."""
        if self.connector is not None:
            return self.connector.get_block_template()
        raise RuntimeError(
            "No connector configured. BTCMinerSupreme refuses to mine "
            "against dummy templates.  Provide a BTCMainnetConnector or "
            "StratumSubmitter before calling run()."
        )

    @staticmethod
    def _dummy_template() -> BlockTemplate:
        """Generate a dummy template for headless testing."""
        import os, struct as st
        return BlockTemplate(
            version=0x20000000,
            prev_block_hash=os.urandom(32),
            merkle_root=os.urandom(32),
            timestamp=int(time.time()),
            bits=0x1d00ffff,  # difficulty 1
        )

    # ── Main mining loop ─────────────────────────────────────────────────
    def run(self) -> None:
        """Start the mining loop (blocking)."""
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        self._running = True
        logger.info("═══ BTC Miner Supreme starting ═══")

        while self._running:
            template = self._get_template()
            if template is None:
                time.sleep(self.cfg.poll_interval_sec)
                continue

            for round_idx in range(self.cfg.max_rounds_per_template):
                if not self._running:
                    break

                self.rounds += 1
                t0 = time.perf_counter()

                # ── Step 1: Build collapse cone ──────────────────────────
                candidates = self.cone.optimise()
                logger.info(
                    "Round %d | Cone produced %d candidates", self.rounds, len(candidates),
                )

                # ── Step 2: GPU first-pass ───────────────────────────────
                winner = self.gpu.dispatch_streaming(
                    template.header_prefix(),
                    candidates,
                    template.target_bytes(),
                )

                # ── Step 3: FPGA deep verify (if GPU found nothing) ─────
                if winner is None and len(candidates) > 0:
                    fpga_result = self.fpga.dispatch(
                        template.header_prefix(),
                        candidates,
                        template.target_bytes(),
                    )
                    if fpga_result.found:
                        winner = fpga_result.nonce

                elapsed = time.perf_counter() - t0

                # ── Step 4: Handle result ────────────────────────────────
                if winner is not None:
                    self.blocks_found += 1
                    logger.info(
                        "╔═══════════════════════════════════════════════╗\n"
                        "║  BLOCK FOUND!  nonce=%d  round=%d  (%.2fs)    ║\n"
                        "╚═══════════════════════════════════════════════╝",
                        winner, self.rounds, elapsed,
                    )
                    self._on_block_found(template, winner)
                    break  # fetch new template

                # ── Step 5: Reseed entropy for next round ────────────────
                self.griffin.reseed(template.prev_block_hash)
                logger.debug(
                    "Round %d miss | %.2fs | reseeding", self.rounds, elapsed,
                )

                # Export telemetry
                if self.monitor:
                    self.monitor.record_round(
                        elapsed_sec=elapsed,
                        candidates=len(candidates),
                        found=False,
                    )

            time.sleep(self.cfg.poll_interval_sec)

        logger.info("═══ BTC Miner Supreme stopped  | rounds=%d  blocks=%d ═══",
                     self.rounds, self.blocks_found)

    # ── Post-solution pipeline ───────────────────────────────────────────
    def _on_block_found(self, template: BlockTemplate, nonce: int) -> None:
        """Submit block, record replay, trigger payout."""
        full_header = template.full_header(nonce)
        block_hash = self.invertor.sha256d(full_header)

        # Record for GAN replay
        if self.gan:
            self.gan.record_win(0, nonce, full_header)
        self.observer.record_block(nonce)

        # Submit
        if self.fuzzer:
            self.fuzzer.submit(full_header, block_hash)
        elif self.stratum:
            self.stratum.submit(nonce)
        elif self.connector:
            self.connector.submit_block(full_header.hex())

        # Payout
        if self.payout:
            self.payout.sweep_if_due()

        # Telemetry
        if self.monitor:
            self.monitor.record_round(elapsed_sec=0, candidates=0, found=True)


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    import structlog
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    cfg = load_config(config_path)
    miner = BTCMinerSupreme(cfg)

    # Wire up Layer 3 if modules are importable
    try:
        from layer3_network.btc_mainnet_connector import BTCMainnetConnector
        net = yaml.safe_load(open(config_path))["network"]
        miner.connector = BTCMainnetConnector(
            rpc_url=f"http://{net['bitcoin_rpc']['host']}:{net['bitcoin_rpc']['port']}",
            rpc_user=net["bitcoin_rpc"]["user"],
            rpc_password=net["bitcoin_rpc"]["password"],
        )
    except Exception as exc:
        logger.warning("Mainnet connector unavailable: %s", exc)

    try:
        from layer3_network.stratum_submitter import StratumSubmitter
        net = yaml.safe_load(open(config_path))["network"]
        miner.stratum = StratumSubmitter(
            pool_url=net["stratum"]["pool_url"],
            worker=net["stratum"]["worker_name"],
            password=net["stratum"]["worker_password"],
        )
    except Exception as exc:
        logger.warning("Stratum submitter unavailable: %s", exc)

    try:
        from layer3_network.block_submission_fuzzer import BlockSubmissionFuzzer
        net = yaml.safe_load(open(config_path))["network"]
        miner.fuzzer = BlockSubmissionFuzzer(
            submitter=miner.stratum,
            connector=miner.connector,
            min_delay_ms=net["submission"]["min_delay_ms"],
            max_delay_ms=net["submission"]["max_delay_ms"],
        )
    except Exception as exc:
        logger.warning("Submission fuzzer unavailable: %s", exc)

    try:
        from layer3_network.wallet_payout_automation import WalletPayoutAutomation
        net = yaml.safe_load(open(config_path))["network"]
        miner.payout = WalletPayoutAutomation(
            wallet_address=net["payout"]["cold_wallet_address"],
            min_payout=net["payout"]["min_payout_btc"],
            connector=miner.connector,
        )
    except Exception as exc:
        logger.warning("Payout automation unavailable: %s", exc)

    try:
        from deployment.grafana_monitor import GrafanaMonitor
        miner.monitor = GrafanaMonitor()
    except Exception as exc:
        logger.warning("Grafana monitor unavailable: %s", exc)

    miner.run()


if __name__ == "__main__":
    main()
