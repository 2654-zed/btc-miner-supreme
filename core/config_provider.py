"""
core/config_provider.py
───────────────────────
Single Source of Truth — strict dependency injection from config.yaml.

This module enforces the Architectural Governance principle that NO
component may hardcode credentials, wallet addresses, or connection
strings.  Every configurable value MUST flow through this provider.

Environment Variable Override
─────────────────────────────
Config values containing ``${ENV_VAR}`` are resolved from the process
environment.  If the env var is unset, a ``ConfigurationError`` is
raised at startup (fail-fast, never silently degrade).

Usage
─────
    from core.config_provider import ConfigProvider

    cfg = ConfigProvider()           # reads config.yaml + env
    wallet = cfg.wallet_address      # resolved, validated
    rpc    = cfg.rpc_config          # RPCConfig dataclass
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# ─── Exceptions ─────────────────────────────────────────────────────────


class ConfigurationError(Exception):
    """Raised when config.yaml is missing, malformed, or contains
    unresolved environment variable references."""


# ─── Data models ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RPCConfig:
    url: str
    user: str
    password: str
    timeout: int = 30


@dataclass(frozen=True)
class StratumConfig:
    pool_url: str
    worker: str
    password: str
    backup_pools: tuple[str, ...] = ()


@dataclass(frozen=True)
class PayoutConfig:
    cold_wallet_address: str
    min_payout_btc: float = 0.001
    auto_sweep: bool = True
    sweep_interval_minutes: int = 60


@dataclass(frozen=True)
class HardwareTopology:
    cpu_model: str
    cpu_nodes: int
    cpu_threads_per_node: int
    gpu_model: str
    gpu_count: int
    fpga_model: str
    fpga_count: int


# ─── Environment Variable Resolver ─────────────────────────────────────

_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env(value: Any) -> Any:
    """Replace ``${VAR}`` placeholders with environment variable values.
    Raises ``ConfigurationError`` if the variable is unset."""
    if not isinstance(value, str):
        return value
    def _replacer(match: re.Match) -> str:
        var = match.group(1)
        val = os.environ.get(var)
        if val is None:
            raise ConfigurationError(
                f"Required environment variable ${{{var}}} is not set. "
                f"Add it to your .env file or export it in the shell."
            )
        return val
    return _ENV_PATTERN.sub(_replacer, value)


def _resolve_dict(d: dict) -> dict:
    """Recursively resolve all env var references in a nested dict."""
    resolved = {}
    for k, v in d.items():
        if isinstance(v, dict):
            resolved[k] = _resolve_dict(v)
        elif isinstance(v, list):
            resolved[k] = [_resolve_env(item) for item in v]
        else:
            resolved[k] = _resolve_env(v)
    return resolved


# ─── Config Provider ───────────────────────────────────────────────────


class ConfigProvider:
    """
    Immutable, validated configuration loaded from ``config.yaml``.

    Enforces the Governance Blueprint's Layer 4 requirement:
    *"All data bridges must use dependency-injected connections;
    hardcoded defaults are prohibited."*
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._path = config_path or Path(__file__).resolve().parent.parent / "config.yaml"
        if not self._path.exists():
            raise ConfigurationError(f"config.yaml not found at {self._path}")

        with open(self._path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ConfigurationError("config.yaml is empty or malformed")

        self._raw = _resolve_dict(raw)
        self._validate()

        logger.info(
            "ConfigProvider initialised from %s (wallet=%s…)",
            self._path, self.wallet_address[:12],
        )

    # ── Accessors ───────────────────────────────────────────────────

    @property
    def wallet_address(self) -> str:
        return self._payout["cold_wallet_address"]

    @property
    def rpc_config(self) -> RPCConfig:
        rpc = self._raw.get("network", {}).get("bitcoin_rpc", {})
        return RPCConfig(
            url=f"http://{rpc.get('host', '127.0.0.1')}:{rpc.get('port', 8332)}",
            user=rpc.get("user", ""),
            password=rpc.get("password", ""),
            timeout=rpc.get("timeout", 30),
        )

    @property
    def stratum_config(self) -> StratumConfig:
        s = self._raw.get("network", {}).get("stratum", {})
        return StratumConfig(
            pool_url=s.get("pool_url", ""),
            worker=s.get("worker_name", ""),
            password=s.get("worker_password", ""),
            backup_pools=tuple(s.get("backup_pools", [])),
        )

    @property
    def payout_config(self) -> PayoutConfig:
        return PayoutConfig(**self._payout)

    @property
    def hardware_topology(self) -> HardwareTopology:
        hw = self._raw.get("hardware", {})
        cpu = hw.get("cpu", {})
        gpu = hw.get("gpu", {})
        fpga = hw.get("fpga", {})
        return HardwareTopology(
            cpu_model=cpu.get("model", "Unknown"),
            cpu_nodes=cpu.get("nodes", 0),
            cpu_threads_per_node=cpu.get("threads_per_node", 0),
            gpu_model=gpu.get("model", "Unknown"),
            gpu_count=gpu.get("count", 0),
            fpga_model=fpga.get("model", "Unknown"),
            fpga_count=fpga.get("count", 0),
        )

    @property
    def raw(self) -> Dict[str, Any]:
        """Full resolved config dict (read-only copy)."""
        return dict(self._raw)

    # ── Validation ──────────────────────────────────────────────────

    @property
    def _payout(self) -> dict:
        return self._raw.get("network", {}).get("payout", {})

    def _validate(self) -> None:
        """Fail-fast validation of critical config fields.

        Raises ``ConfigurationError`` for missing/unresolved critical values.
        Warnings-only mode is an anti-pattern — this is hard-fail.
        """
        errors: list[str] = []

        wallet = self._payout.get("cold_wallet_address", "")
        if not wallet or wallet.startswith("${"):
            errors.append(
                f"Wallet address is unresolved ('{wallet}'). "
                "Set COLD_WALLET_ADDRESS in your .env file."
            )

        rpc = self._raw.get("network", {}).get("bitcoin_rpc", {})
        if not rpc.get("user") or not rpc.get("password"):
            errors.append(
                "Bitcoin RPC credentials are empty. "
                "Set BTC_RPC_USER and BTC_RPC_PASSWORD in your .env file."
            )

        stratum = self._raw.get("network", {}).get("stratum", {})
        pool_url = stratum.get("pool_url", "")
        if not pool_url or "example.com" in pool_url or pool_url.startswith("${"):
            errors.append(
                f"Stratum pool URL is invalid ('{pool_url}'). "
                "Set a real pool URL in config.yaml or via STRATUM_POOL_URL."
            )

        if errors:
            for e in errors:
                logger.error("CONFIG VALIDATION FAILED: %s", e)
            raise ConfigurationError(
                f"{len(errors)} critical config error(s): {'; '.join(errors)}"
            )
