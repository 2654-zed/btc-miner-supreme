# ╔══════════════════════════════════════════════════════════════════════╗
# ║  BTC Miner Supreme — Multi-Stage Dockerfile                        ║
# ║  Bundles Python, Numba, CUDA, OpenCL, and XRT FPGA bridge          ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ── Stage 1: Builder ─────────────────────────────────────────────────────
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        python3.11 \
        python3.11-dev \
        python3.11-venv \
        python3-pip \
        git \
        wget \
        curl \
        ocl-icd-opencl-dev \
        opencl-headers \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python  python  /usr/bin/python3.11 1

# XRT (Xilinx Runtime) — install if host provides the .deb
# In production, mount or COPY the XRT installer matching your FPGA shell
ARG XRT_DEB=""
RUN if [ -n "$XRT_DEB" ]; then \
        dpkg -i "$XRT_DEB" || apt-get -f install -y; \
    fi

WORKDIR /opt/btc-miner

# Python deps
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python3 -m pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        libgomp1 \
        ocl-icd-libopencl1 \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python  python  /usr/bin/python3.11 1

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy XRT libs if they were installed (safe no-op when absent)
COPY --from=builder /opt/xilinx /tmp/xilinx
RUN if [ -d /tmp/xilinx ]; then cp -a /tmp/xilinx /opt/xilinx; fi

WORKDIR /opt/btc-miner

# Copy application code
COPY config.yaml .
COPY layer1_entropy/ layer1_entropy/
COPY layer2_execution/ layer2_execution/
COPY layer3_network/ layer3_network/
COPY deployment/ deployment/
COPY tests/ tests/

# Data & model directories
RUN mkdir -p data/checkpoints models bitstreams

# Prometheus port
EXPOSE 9100

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:9100/metrics')" || exit 1

# Default entrypoint
ENTRYPOINT ["python3", "-m", "layer2_execution.btc_miner_supreme"]
CMD ["config.yaml"]
