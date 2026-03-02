"""
btc_mainnet_connector.py
────────────────────────
Fetches block templates from a full Bitcoin node via JSON-RPC and submits
valid solved blocks back to the network.

Supports Bitcoin Core's `getblocktemplate` (BIP 22/23) and `submitblock`
RPCs, with automatic retry and connection pooling.
"""

from __future__ import annotations

import json
import logging
import struct
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

from layer2_execution.sha256d_invertor import BlockTemplate

logger = logging.getLogger(__name__)


@dataclass
class RPCConfig:
    rpc_url: str = "http://127.0.0.1:8332"
    rpc_user: str = ""      # REQUIRED — set via config.yaml or BTC_RPC_USER env
    rpc_password: str = ""  # REQUIRED — set via config.yaml or BTC_RPC_PASSWORD env
    timeout: int = 30
    max_retries: int = 3
    retry_backoff: float = 1.0


class BTCMainnetConnector:
    """
    JSON-RPC client for a Bitcoin Core full node.
    """

    def __init__(
        self,
        rpc_url: str = "http://127.0.0.1:8332",
        rpc_user: str = "",
        rpc_password: str = "",
        timeout: int = 30,
    ) -> None:
        self.url = rpc_url
        self.auth = HTTPBasicAuth(rpc_user, rpc_password)
        self.timeout = timeout
        self._id_counter = 0

        self._session = requests.Session()
        adapter = HTTPAdapter(max_retries=3, pool_connections=4, pool_maxsize=4)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

        logger.info("BTCMainnetConnector → %s", rpc_url)

    # ── Low-level RPC ────────────────────────────────────────────────────
    def _rpc(self, method: str, params: list = None) -> Any:
        self._id_counter += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id_counter,
            "method": method,
            "params": params or [],
        }
        try:
            resp = self._session.post(
                self.url,
                json=payload,
                auth=self.auth,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("error"):
                raise RuntimeError(f"RPC error: {body['error']}")
            return body["result"]
        except requests.RequestException as exc:
            logger.error("RPC call %s failed: %s", method, exc)
            raise

    # ── High-level API ───────────────────────────────────────────────────
    def get_block_count(self) -> int:
        return self._rpc("getblockcount")

    def get_best_block_hash(self) -> str:
        return self._rpc("getbestblockhash")

    def get_block_template(self, capabilities: Optional[List[str]] = None) -> BlockTemplate:
        """
        Call `getblocktemplate` and return a BlockTemplate ready for
        nonce searching.
        """
        caps = capabilities or ["coinbasetxn", "workid"]
        tmpl = self._rpc("getblocktemplate", [{"rules": ["segwit"], "capabilities": caps}])

        version = tmpl["version"]
        prev_hash = bytes.fromhex(tmpl["previousblockhash"])
        # Bitcoin encodes prev hash in internal byte order
        prev_hash_internal = prev_hash[::-1]

        # Build merkle root from coinbase + transactions
        merkle_root = self._compute_merkle_root(tmpl)

        timestamp = tmpl.get("curtime", int(time.time()))
        bits_hex = tmpl["bits"]
        bits = int(bits_hex, 16)

        return BlockTemplate(
            version=version,
            prev_block_hash=prev_hash_internal,
            merkle_root=merkle_root,
            timestamp=timestamp,
            bits=bits,
        )

    def submit_block(self, block_hex: str) -> str:
        """Submit a serialised block to the network."""
        result = self._rpc("submitblock", [block_hex])
        if result is None:
            logger.info("Block accepted by node!")
        else:
            logger.warning("Block submission result: %s", result)
        return result

    def get_network_info(self) -> Dict:
        return self._rpc("getnetworkinfo")

    def get_mining_info(self) -> Dict:
        return self._rpc("getmininginfo")

    def get_balance(self) -> float:
        return self._rpc("getbalance")

    # ── Merkle helpers ───────────────────────────────────────────────────
    def _compute_merkle_root(self, tmpl: Dict) -> bytes:
        """Compute the merkle root from the template's transactions."""
        import hashlib

        coinbase_txn = tmpl.get("coinbasetxn", {}).get("data", "")

        tx_hashes: List[bytes] = []
        if coinbase_txn:
            raw = bytes.fromhex(coinbase_txn)
            h = hashlib.sha256(hashlib.sha256(raw).digest()).digest()
            tx_hashes.append(h)

        for tx in tmpl.get("transactions", []):
            tx_hash = bytes.fromhex(tx["hash"])
            # Template provides txid in RPC byte order → reverse for internal
            tx_hashes.append(tx_hash[::-1])

        if not tx_hashes:
            return b"\x00" * 32

        # Standard Bitcoin merkle-tree construction
        while len(tx_hashes) > 1:
            if len(tx_hashes) % 2 == 1:
                tx_hashes.append(tx_hashes[-1])  # duplicate last
            next_level: List[bytes] = []
            for i in range(0, len(tx_hashes), 2):
                combined = tx_hashes[i] + tx_hashes[i + 1]
                h = hashlib.sha256(hashlib.sha256(combined).digest()).digest()
                next_level.append(h)
            tx_hashes = next_level

        return tx_hashes[0]

    # ── Convenience ──────────────────────────────────────────────────────
    def is_connected(self) -> bool:
        try:
            self.get_block_count()
            return True
        except Exception:
            return False
