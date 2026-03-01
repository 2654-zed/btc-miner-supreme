# BTC Miner Supreme — Collapse-Theoretic Mining Pipeline

A multi-layered Bitcoin mining system built on **symbolic collapse logic**, **GAN-trained entropy replay**, and **hardware-accelerated SHA-256d verification** across GPU and FPGA fabrics.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        LAYER 1: ENTROPY SHAPING                        │
│                                                                         │
│  Griffin962 Weaver ──► Zeta Router ──► GAN Replay ──► Observer Ladder  │
│            │                                                │           │
│            └──────────── Collapse Cone Optimizer ◄───────────┘           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  Optimised nonce candidates
┌──────────────────────────────▼──────────────────────────────────────────┐
│                     LAYER 2: EXECUTION & DISPATCH                       │
│                                                                         │
│  SHA256d Invertor ◄── GPU Parallel Splitter (10× H100)                  │
│                   ◄── FPGA SHA Bridge        (40× Alveo UL3524)         │
│                                                                         │
│                    ┌── BTC Miner Supreme (orchestrator) ──┐             │
└────────────────────┴──────────────────────────────────────┴─────────────┘
                               │  Valid block found
┌──────────────────────────────▼──────────────────────────────────────────┐
│                   LAYER 3: NETWORKING & PAYOUT                          │
│                                                                         │
│  BTC Mainnet Connector ──► Stratum Submitter                            │
│  Block Submission Fuzzer   Wallet Payout Automation                     │
└─────────────────────────────────────────────────────────────────────────┘
```

## Hardware Topology

| Role | Hardware | Qty |
|------|----------|-----|
| Orchestration (CPU) | Intel Xeon Platinum 8593Q | 2 nodes |
| Parallel Nonce Sweep (GPU) | NVIDIA H100 SXM | 10 |
| Ultra-Fast Hashing (FPGA) | Alveo UL3524 | 40 |

## Project Structure

```
btc/
├── config.yaml                          # Master configuration
├── requirements.txt                     # Python dependencies
├── Dockerfile                           # Multi-stage build
├── docker-compose.yml                   # Full stack orchestration
│
├── layer1_entropy/                      # Entropy Shaping & Symbolic Guidance
│   ├── griffin962_entropy_weaver.py      #   Griffin-class attractor (1/962)
│   ├── zeta_aligned_symbolic_router.py  #   Riemann zeta critical-line filter
│   ├── qer_gan_memory_replay.py         #   GAN replay buffer & training
│   ├── observer_ladder_replay.py        #   Recursive observer ranking
│   └── collapse_cone_optimizer.py       #   Fuses all sources → nonce cone
│
├── layer2_execution/                    # Execution & Hardware Dispatch
│   ├── sha256d_invertor.py              #   Core double-SHA-256 inverter
│   ├── gpu_parallel_splitter.py         #   Numba CUDA parallel dispatch
│   ├── fpga_sha_bridge.py              #   XRT FPGA bridge for Alveo
│   └── btc_miner_supreme.py            #   Master mining loop
│
├── layer3_network/                      # Networking, Safety, & Payout
│   ├── btc_mainnet_connector.py         #   Bitcoin JSON-RPC client
│   ├── stratum_submitter.py             #   Stratum V1 pool client
│   ├── block_submission_fuzzer.py       #   Timing obfuscation
│   └── wallet_payout_automation.py      #   Cold-wallet auto-sweep
│
├── deployment/                          # Deployment & Telemetry
│   ├── entropy_core_balancer.py         #   CPU auto-scaling
│   ├── grafana_monitor.py               #   Prometheus metrics exporter
│   ├── prometheus.yml                   #   Prometheus scrape config
│   └── grafana/                         #   Grafana dashboards & provisioning
│
└── tests/                               # Test suite
    ├── test_layer1.py
    ├── test_layer2.py
    ├── test_layer3.py
    └── test_deployment.py
```

## Quick Start

### Local Development

```bash
# Clone and install
cd btc
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Start mining (connects to local Bitcoin node)
python -m layer2_execution.btc_miner_supreme config.yaml
```

### Docker Deployment

```bash
# Build and launch full stack (miner + Prometheus + Grafana)
docker compose up --build -d

# View logs
docker compose logs -f miner

# Access Grafana dashboard
# → http://localhost:3000  (admin / supremestack)

# Access Prometheus
# → http://localhost:9090
```

## Configuration

All parameters are centralised in `config.yaml`:

- **`entropy.*`** — Layer-1 symbolic guidance tuning (Griffin constant, zeta range, GAN hyper-parameters, observer depth)
- **`execution.*`** — SHA-256d mode (`collapse` / `bruteforce` / `hybrid`), GPU & FPGA dispatch settings
- **`hardware.*`** — Device counts and CUDA/XRT paths
- **`network.*`** — Bitcoin RPC, Stratum pool, submission fuzzing, cold-wallet payout
- **`deployment.*`** — Core balancer auto-tuning, Prometheus/Grafana monitoring

### Critical Settings to Update

1. **`network.bitcoin_rpc.*`** — Point to your full Bitcoin Core node
2. **`network.stratum.pool_url`** — Your mining pool address
3. **`network.payout.cold_wallet_address`** — Your cold-storage BTC address
4. **`hardware.fpga.bitstream_path`** — Path to your compiled SHA-256d FPGA bitstream

## Monitoring

The Grafana dashboard (`Collapse Dynamics`) displays:

| Panel | Metric |
|-------|--------|
| Blocks Found | `btcminer_blocks_found_total` |
| Hash Rate | `btcminer_hashrate` |
| Round Duration | `btcminer_round_duration_seconds` |
| Nonce Success Rate | `btcminer_nonce_success_rate` |
| Entropy Workers | `btcminer_entropy_workers` |
| GPU Utilization | `btcminer_gpu_utilization` |
| FPGA Utilization | `btcminer_fpga_utilization` |
| CPU / Memory | `btcminer_cpu_percent` / `btcminer_memory_percent` |
| Cone Size | `btcminer_cone_size` |
| GAN Buffer | `btcminer_gan_buffer_size` |

## Module Reference

### Layer 1 — Entropy Shaping

| Module | Purpose |
|--------|---------|
| `griffin962_entropy_weaver` | Generates nonce candidates biased toward attractor basins derived from the harmonic series on 1/962 × φ |
| `zeta_aligned_symbolic_router` | Filters candidates by proximity to Riemann ζ non-trivial zeros on the critical line |
| `qer_gan_memory_replay` | GAN (Generator / Discriminator) trained on historically successful nonces; replays learned distribution |
| `observer_ladder_replay` | Multi-layer recursive Bayesian scorer that ranks candidates by convergence evidence |
| `collapse_cone_optimizer` | Fuses all Layer-1 sources via weighted-vote / intersection / union into the final nonce cone |

### Layer 2 — Execution

| Module | Purpose |
|--------|---------|
| `sha256d_invertor` | Pure-Python reference SHA-256d with collapse / bruteforce / hybrid modes |
| `gpu_parallel_splitter` | Numba CUDA kernel dispatch across multiple H100 GPUs |
| `fpga_sha_bridge` | XRT-based dispatch to Alveo UL3524 FPGAs with DMA buffer protocol |
| `btc_miner_supreme` | Top-level orchestrator wiring all layers into a continuous mining loop |

### Layer 3 — Networking

| Module | Purpose |
|--------|---------|
| `btc_mainnet_connector` | Bitcoin Core JSON-RPC client (getblocktemplate, submitblock) |
| `stratum_submitter` | Stratum V1 protocol client with subscribe/authorize/submit |
| `block_submission_fuzzer` | Randomised timing + telemetry variation for submission privacy |
| `wallet_payout_automation` | Auto-sweeps mined rewards to cold wallet with fee estimation |

## License

Proprietary — all rights reserved.
