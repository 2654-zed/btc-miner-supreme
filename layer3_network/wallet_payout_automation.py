"""
wallet_payout_automation.py
───────────────────────────
Automatically routes mined block rewards to a designated cold wallet
address upon successful block solution.

Features
────────
- Periodic balance sweep: checks wallet balance and sends to cold
  storage when threshold is met.
- UTXO consolidation: batches small UTXOs into a single output to
  reduce future transaction fees.
- Fee estimation: uses `estimatesmartfee` to choose an appropriate
  fee rate.
- Audit log: records every sweep transaction for accounting.
"""

from __future__ import annotations

import json
import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PayoutConfig:
    cold_wallet_address: str = "bc1qYOUR_COLD_WALLET_ADDRESS_HERE"
    min_payout_btc: float = 0.001
    auto_sweep: bool = True
    sweep_interval_minutes: int = 60
    fee_target_blocks: int = 6
    consolidate_utxos: bool = True
    max_utxos_per_tx: int = 50
    audit_log_path: str = "./data/payout_audit.jsonl"


@dataclass
class SweepRecord:
    timestamp: str
    txid: str
    amount_btc: float
    fee_btc: float
    destination: str
    utxo_count: int


class WalletPayoutAutomation:
    """
    Manages automatic transfer of mining rewards to cold storage.
    """

    def __init__(
        self,
        wallet_address: str = "bc1qYOUR_COLD_WALLET_ADDRESS_HERE",
        min_payout: float = 0.001,
        connector=None,             # BTCMainnetConnector
        sweep_interval_min: int = 60,
    ) -> None:
        self.address = wallet_address
        self.min_payout = min_payout
        self.connector = connector
        self.sweep_interval = sweep_interval_min * 60   # seconds
        self._last_sweep = 0.0
        self._audit: List[SweepRecord] = []
        self._lock = threading.Lock()
        self._audit_path = Path("./data/payout_audit.jsonl")

        logger.info(
            "WalletPayoutAutomation → %s  min=%.4f BTC  interval=%dm",
            wallet_address[:16] + "…", min_payout, sweep_interval_min,
        )

    # ── Sweep logic ──────────────────────────────────────────────────────
    def sweep_if_due(self) -> Optional[str]:
        """
        Check if a sweep is due (time + balance threshold) and execute
        if so.  Returns the txid on success, or None.
        """
        now = time.time()
        if now - self._last_sweep < self.sweep_interval:
            return None

        if self.connector is None:
            logger.debug("No connector — sweep skipped")
            return None

        try:
            balance = self.connector.get_balance()
        except Exception as exc:
            logger.warning("Cannot fetch balance: %s", exc)
            return None

        if balance < self.min_payout:
            logger.debug("Balance %.8f < min %.8f — sweep skipped", balance, self.min_payout)
            self._last_sweep = now
            return None

        return self._execute_sweep(balance)

    def force_sweep(self) -> Optional[str]:
        """Force an immediate sweep regardless of interval / threshold."""
        if self.connector is None:
            logger.error("No connector — cannot sweep")
            return None
        try:
            balance = self.connector.get_balance()
        except Exception as exc:
            logger.error("Cannot fetch balance: %s", exc)
            return None
        return self._execute_sweep(balance)

    def _execute_sweep(self, balance: float) -> Optional[str]:
        """Build and broadcast a sweep transaction."""
        with self._lock:
            try:
                # Estimate fee
                fee_rate = self._estimate_fee()

                # List unspent UTXOs
                utxos = self._list_utxos()
                if not utxos:
                    logger.info("No UTXOs to sweep")
                    return None

                # Build raw transaction
                txid = self._send_all(utxos, balance, fee_rate)
                if txid:
                    record = SweepRecord(
                        timestamp=datetime.utcnow().isoformat(),
                        txid=txid,
                        amount_btc=balance,
                        fee_btc=fee_rate * 250 / 1e8,  # rough estimate
                        destination=self.address,
                        utxo_count=len(utxos),
                    )
                    self._audit.append(record)
                    self._write_audit(record)
                    self._last_sweep = time.time()
                    logger.info(
                        "Sweep complete: %.8f BTC → %s  txid=%s",
                        balance, self.address[:16], txid[:16],
                    )
                return txid

            except Exception as exc:
                logger.error("Sweep failed: %s", exc)
                return None

    # ── RPC helpers ──────────────────────────────────────────────────────
    def _estimate_fee(self, target_blocks: int = 6) -> float:
        """Get fee rate in sat/vB from estimatesmartfee."""
        try:
            result = self.connector._rpc("estimatesmartfee", [target_blocks])
            btc_per_kb = result.get("feerate", 0.0001)
            sat_per_vb = btc_per_kb * 1e8 / 1000
            return max(sat_per_vb, 1.0)
        except Exception:
            return 10.0   # fallback: 10 sat/vB

    def _list_utxos(self) -> List[Dict]:
        """List unspent transaction outputs."""
        try:
            return self.connector._rpc("listunspent", [1, 9999999])
        except Exception as exc:
            logger.warning("listunspent failed: %s", exc)
            return []

    def _send_all(self, utxos: List[Dict], total: float, fee_rate: float) -> Optional[str]:
        """
        Create, sign, and broadcast a transaction sweeping all UTXOs
        to the cold wallet.
        """
        # Inputs
        inputs = [
            {"txid": u["txid"], "vout": u["vout"]}
            for u in utxos[:50]   # cap to avoid oversized tx
        ]
        input_total = sum(u["amount"] for u in utxos[:50])

        # Rough fee estimate (250 bytes base + 68 per input)
        tx_size = 250 + 68 * len(inputs)
        fee_btc = fee_rate * tx_size / 1e8
        send_amount = round(input_total - fee_btc, 8)

        if send_amount <= 0:
            logger.warning("Insufficient balance after fee")
            return None

        outputs = {self.address: send_amount}

        try:
            raw_tx = self.connector._rpc("createrawtransaction", [inputs, outputs])
            signed = self.connector._rpc("signrawtransactionwithwallet", [raw_tx])
            if not signed.get("complete"):
                logger.error("Transaction signing incomplete")
                return None
            txid = self.connector._rpc("sendrawtransaction", [signed["hex"]])
            return txid
        except Exception as exc:
            logger.error("Transaction broadcast failed: %s", exc)
            return None

    # ── Audit log ────────────────────────────────────────────────────────
    def _write_audit(self, record: SweepRecord) -> None:
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._audit_path, "a") as f:
                f.write(json.dumps({
                    "timestamp": record.timestamp,
                    "txid": record.txid,
                    "amount_btc": record.amount_btc,
                    "fee_btc": record.fee_btc,
                    "destination": record.destination,
                    "utxo_count": record.utxo_count,
                }) + "\n")
        except Exception as exc:
            logger.warning("Audit write failed: %s", exc)

    @property
    def audit_history(self) -> List[SweepRecord]:
        return list(self._audit)

    @property
    def total_swept_btc(self) -> float:
        return sum(r.amount_btc for r in self._audit)
