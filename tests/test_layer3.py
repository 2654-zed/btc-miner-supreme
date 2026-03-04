"""
test_layer3.py
──────────────
Unit tests for Layer-3 networking, submission fuzzer, and payout modules.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from layer3_network.stratum_submitter import StratumSubmitter, StratumJob
from layer3_network.block_submission_fuzzer import BlockSubmissionFuzzer
from layer3_network.wallet_payout_automation import WalletPayoutAutomation


# ═══════════════════════════════════════════════════════════════════════════
# Stratum Submitter (unit-level, no real connection)
# ═══════════════════════════════════════════════════════════════════════════

class TestStratumSubmitter:
    def test_parse_url_tcp(self):
        s = StratumSubmitter(pool_url="stratum+tcp://pool.local:3333")
        host, port, tls = s._parse_url("stratum+tcp://pool.example.com:3333")
        assert host == "pool.example.com"
        assert port == 3333
        assert tls is False

    def test_parse_url_ssl(self):
        s = StratumSubmitter(pool_url="stratum+tcp://pool.local:3333")
        host, port, tls = s._parse_url("stratum+ssl://secure.pool.io:4444")
        assert host == "secure.pool.io"
        assert port == 4444
        assert tls is True

    def test_no_job_submit_fails(self):
        s = StratumSubmitter(pool_url="stratum+tcp://pool.local:3333")
        # Without a current job and no socket, submit should return False
        result = s.submit(12345)
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════
# Block Submission Fuzzer
# ═══════════════════════════════════════════════════════════════════════════

class TestSubmissionFuzzer:
    def test_no_channels_returns_false(self):
        fuzzer = BlockSubmissionFuzzer(min_delay_ms=1, max_delay_ms=5)
        result = fuzzer.submit(b"\x00" * 80, b"\x00" * 32)
        assert result is False

    def test_submission_count_increments(self):
        fuzzer = BlockSubmissionFuzzer(min_delay_ms=1, max_delay_ms=2)
        fuzzer.submit(b"\x00" * 80, b"\x00" * 32)
        fuzzer.submit(b"\x00" * 80, b"\x00" * 32)
        assert fuzzer.total_submissions == 2


# ═══════════════════════════════════════════════════════════════════════════
# Wallet Payout Automation (offline)
# ═══════════════════════════════════════════════════════════════════════════

class TestWalletPayout:
    def test_no_connector_returns_none(self):
        payout = WalletPayoutAutomation(wallet_address="bc1qtest")
        result = payout.sweep_if_due()
        assert result is None

    def test_total_swept_starts_zero(self):
        payout = WalletPayoutAutomation()
        assert payout.total_swept_btc == 0.0

    def test_audit_starts_empty(self):
        payout = WalletPayoutAutomation()
        assert len(payout.audit_history) == 0
