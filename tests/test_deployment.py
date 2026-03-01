"""
test_deployment.py
──────────────────
Unit tests for deployment modules.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deployment.entropy_core_balancer import EntropyCoreBalancer, BalancerConfig


class TestCoreBalancer:
    def test_initial_workers_within_range(self):
        cfg = BalancerConfig(min_entropy_workers=1, max_entropy_workers=8)
        bal = EntropyCoreBalancer(cfg)
        assert cfg.min_entropy_workers <= bal.pool.num_workers <= cfg.max_entropy_workers

    def test_set_workers_clamps(self):
        cfg = BalancerConfig(min_entropy_workers=2, max_entropy_workers=6)
        bal = EntropyCoreBalancer(cfg)
        bal.set_workers(100)
        assert bal.pool.num_workers == 6
        bal.set_workers(0)
        assert bal.pool.num_workers == 2

    def test_recommended_batch_size(self):
        cfg = BalancerConfig(batch_size_per_worker=1000)
        bal = EntropyCoreBalancer(cfg)
        assert bal.recommended_batch_size() == bal.pool.num_workers * 1000

    def test_snapshot_keys(self):
        bal = EntropyCoreBalancer()
        snap = bal.snapshot()
        expected_keys = {"workers", "batch_per_worker", "total_batch",
                         "physical_cores", "logical_cores", "cpu_percent",
                         "memory_percent"}
        assert expected_keys.issubset(set(snap.keys()))
