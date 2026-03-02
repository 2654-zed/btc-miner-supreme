"""
tests/test_ioc_architecture.py
──────────────────────────────
Comprehensive test suite for the Inversion of Control architecture:

  • MathSandbox  (AST sanitiser + NumExpr / NumPy execution)
  • MathSanitizer (whitelist traversal)
  • DynamicCPUStrategy
  • MasterOrchestrator (hot-swap, lifecycle, diagnostics)
  • Pydantic schemas (validation layer)

Run:  pytest tests/test_ioc_architecture.py -v
"""

from __future__ import annotations

import math
import re

import numpy as np
import pytest

# ── Core / Domain ───────────────────────────────────────────────────────
from core.exceptions import (
    HardwareRoutingError,
    OrchestrationError,
    SecurityViolationError,
)
from core.orchestrator import MasterOrchestrator
from domain.interfaces import HeuristicStrategy
from domain.models import ExecutionResult, NonceBatch, StrategySwapEvent

# ── Infrastructure ──────────────────────────────────────────────────────
from infrastructure.math_sandbox import MathSandbox, MathSanitizer
from infrastructure.strategies.cpu_dynamic import DynamicCPUStrategy


# ═════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════

class DummyStrategy(HeuristicStrategy):
    """Trivial strategy for orchestrator tests."""

    def execute(self, nonces: np.ndarray) -> np.ndarray:
        return nonces.astype(np.float64) * 2

    def get_hardware_target(self) -> str:
        return "DUMMY_TEST"


class FakeGPUStrategy(HeuristicStrategy):
    def execute(self, nonces: np.ndarray) -> np.ndarray:
        return nonces.astype(np.float64) ** 2

    def get_hardware_target(self) -> str:
        return "GPU_CUDA"


class FakeFPGAStrategy(HeuristicStrategy):
    def execute(self, nonces: np.ndarray) -> np.ndarray:
        return nonces.astype(np.float64) + 1

    def get_hardware_target(self) -> str:
        return "FPGA_BRIDGE"


# ═════════════════════════════════════════════════════════════════════════
# MathSanitizer — AST Whitelist Tests
# ═════════════════════════════════════════════════════════════════════════

class TestMathSanitizer:
    """Verify that the AST whitelist blocks all dangerous constructs."""

    def test_safe_arithmetic(self):
        sandbox = MathSandbox()
        assert sandbox.sanitize("nonce + 1") is True
        assert sandbox.sanitize("nonce * 2 - 3") is True
        assert sandbox.sanitize("nonce ** 1.618") is True
        assert sandbox.sanitize("(nonce % 0xFFFFFFFF)") is True

    def test_safe_constants(self):
        sandbox = MathSandbox()
        assert sandbox.sanitize("nonce + pi") is True
        assert sandbox.sanitize("nonce * e") is True
        assert sandbox.sanitize("nonce * phi") is True
        assert sandbox.sanitize("nonce * gamma") is True

    def test_bitwise_ops(self):
        sandbox = MathSandbox()
        assert sandbox.sanitize("nonce ^ 0xFF") is True
        assert sandbox.sanitize("nonce & 0xFFFF") is True
        assert sandbox.sanitize("nonce | 0x1") is True

    def test_unary_ops(self):
        sandbox = MathSandbox()
        assert sandbox.sanitize("-nonce") is True
        assert sandbox.sanitize("+nonce") is True
        assert sandbox.sanitize("~nonce") is True

    def test_reject_function_calls(self):
        sandbox = MathSandbox()
        with pytest.raises(SecurityViolationError, match="Unauthorised"):
            sandbox.sanitize("print(nonce)")

    def test_reject_import(self):
        sandbox = MathSandbox()
        with pytest.raises(SecurityViolationError, match="Unauthorised"):
            sandbox.sanitize("__import__('os')")

    def test_reject_attribute_access(self):
        sandbox = MathSandbox()
        with pytest.raises(SecurityViolationError, match="Unauthorised"):
            sandbox.sanitize("nonce.__class__")

    def test_reject_dunder_traversal(self):
        sandbox = MathSandbox()
        with pytest.raises(SecurityViolationError, match="Unauthorised"):
            sandbox.sanitize("().__class__.__bases__")

    def test_reject_unauthorised_variable(self):
        sandbox = MathSandbox()
        with pytest.raises(SecurityViolationError, match="Unauthorised variable"):
            sandbox.sanitize("os + 1")

    def test_reject_string_constant(self):
        sandbox = MathSandbox()
        with pytest.raises(SecurityViolationError, match="numeric constants"):
            sandbox.sanitize("'hello'")

    def test_reject_list_comprehension(self):
        sandbox = MathSandbox()
        with pytest.raises(SecurityViolationError, match="Unauthorised"):
            sandbox.sanitize("[x for x in range(10)]")

    def test_reject_lambda(self):
        sandbox = MathSandbox()
        with pytest.raises(SecurityViolationError, match="Unauthorised"):
            sandbox.sanitize("lambda x: x + 1")

    def test_reject_multiline_exec(self):
        sandbox = MathSandbox()
        with pytest.raises(SecurityViolationError):
            sandbox.sanitize("import os\nos.system('id')")

    def test_empty_formula(self):
        sandbox = MathSandbox()
        with pytest.raises(ValueError, match="Empty"):
            sandbox.sanitize("")

    def test_syntax_error(self):
        sandbox = MathSandbox()
        with pytest.raises(ValueError, match="Invalid mathematical syntax"):
            sandbox.sanitize("nonce +* 1")


# ═════════════════════════════════════════════════════════════════════════
# MathSandbox — Execution Tests
# ═════════════════════════════════════════════════════════════════════════

class TestMathSandbox:
    """Verify that sanitised formulas produce correct numerical results."""

    def setup_method(self):
        self.sandbox = MathSandbox()
        self.nonces = np.arange(1, 101, dtype=np.uint32)

    def test_simple_addition(self):
        result = self.sandbox.execute("nonce + 1", self.nonces)
        expected = self.nonces.astype(np.float64) + 1
        np.testing.assert_array_almost_equal(result, expected)

    def test_power_formula(self):
        result = self.sandbox.execute("nonce ** 2", self.nonces)
        expected = self.nonces.astype(np.float64) ** 2
        np.testing.assert_array_almost_equal(result, expected)

    def test_modulo(self):
        result = self.sandbox.execute("nonce % 7", self.nonces)
        expected = self.nonces.astype(np.float64) % 7
        np.testing.assert_array_almost_equal(result, expected)

    def test_complex_expression(self):
        result = self.sandbox.execute("(nonce ** 1.618) + (1/962)", self.nonces)
        expected = self.nonces.astype(np.float64) ** 1.618 + 1 / 962
        np.testing.assert_array_almost_equal(result, expected, decimal=4)

    def test_constant_pi(self):
        result = self.sandbox.execute("nonce * pi", self.nonces)
        expected = self.nonces.astype(np.float64) * np.pi
        np.testing.assert_array_almost_equal(result, expected)

    def test_constant_phi(self):
        result = self.sandbox.execute("nonce * phi", self.nonces)
        phi = (1 + np.sqrt(5)) / 2
        expected = self.nonces.astype(np.float64) * phi
        np.testing.assert_array_almost_equal(result, expected)

    def test_constant_gamma(self):
        result = self.sandbox.execute("nonce * gamma", self.nonces)
        gamma = 0.5772156649015329
        expected = self.nonces.astype(np.float64) * gamma
        np.testing.assert_array_almost_equal(result, expected)

    def test_division_by_zero_yields_nan(self):
        nonces_with_zero = np.arange(0, 10, dtype=np.uint32)
        result = self.sandbox.execute("1 / nonce", nonces_with_zero)
        # nonce=0 should produce inf or nan, not crash
        assert np.isinf(result[0]) or np.isnan(result[0])

    def test_large_batch(self):
        large = np.arange(1_000_000, dtype=np.uint32)
        result = self.sandbox.execute("nonce + 1", large)
        assert result.shape == (1_000_000,)
        assert result[0] == 1.0
        assert result[-1] == 1_000_000.0

    def test_security_blocks_before_execution(self):
        """Malicious formula never reaches NumExpr."""
        with pytest.raises(SecurityViolationError):
            self.sandbox.execute("__import__('os').system('id')", self.nonces)


# ═════════════════════════════════════════════════════════════════════════
# DynamicCPUStrategy
# ═════════════════════════════════════════════════════════════════════════

class TestDynamicCPUStrategy:

    def test_basic_execution(self):
        strat = DynamicCPUStrategy(formula="nonce * 2")
        nonces = np.arange(100, dtype=np.uint32)
        result = strat.execute(nonces)
        np.testing.assert_array_almost_equal(result, nonces.astype(np.float64) * 2)

    def test_hardware_target(self):
        strat = DynamicCPUStrategy(formula="nonce + 1")
        assert strat.get_hardware_target() == "CPU_SANDBOX"

    def test_diagnostics(self):
        strat = DynamicCPUStrategy(formula="nonce + 1")
        nonces = np.arange(50, dtype=np.uint32)
        strat.execute(nonces)
        diag = strat.get_diagnostics()
        assert diag["target"] == "CPU_SANDBOX"
        assert diag["formula"] == "nonce + 1"
        assert diag["total_processed"] == 50

    def test_formula_update(self):
        strat = DynamicCPUStrategy(formula="nonce + 1")
        strat.update_formula("nonce * 3")
        assert strat.formula == "nonce * 3"

    def test_invalid_formula_rejected(self):
        with pytest.raises(SecurityViolationError):
            DynamicCPUStrategy(formula="print(nonce)")

    def test_update_invalid_formula_rejected(self):
        strat = DynamicCPUStrategy(formula="nonce + 1")
        with pytest.raises(SecurityViolationError):
            strat.update_formula("__import__('os')")
        # Original formula preserved
        assert strat.formula == "nonce + 1"


# ═════════════════════════════════════════════════════════════════════════
# MasterOrchestrator
# ═════════════════════════════════════════════════════════════════════════

class TestMasterOrchestrator:

    def test_init_and_process(self):
        orch = MasterOrchestrator(DummyStrategy())
        nonces = np.arange(10, dtype=np.uint32)
        result = orch.process_workload(nonces)
        assert isinstance(result, ExecutionResult)
        np.testing.assert_array_almost_equal(
            result.results, nonces.astype(np.float64) * 2
        )

    def test_current_target(self):
        orch = MasterOrchestrator(DummyStrategy())
        assert orch.current_target == "DUMMY_TEST"

    def test_strategy_hot_swap(self):
        orch = MasterOrchestrator(DummyStrategy())
        cpu = DynamicCPUStrategy("nonce + 100")
        event = orch.set_strategy(cpu, reason="test swap")
        assert orch.current_target == "CPU_SANDBOX"
        assert event.previous_target == "DUMMY_TEST"
        assert event.new_target == "CPU_SANDBOX"

    def test_swap_from_fpga_disables_bridge(self):
        orch = MasterOrchestrator(FakeFPGAStrategy())
        event = orch.set_strategy(DummyStrategy(), reason="test FPGA drain")
        assert event.previous_target == "FPGA_BRIDGE"
        assert event.new_target == "DUMMY_TEST"

    def test_swap_from_gpu_disables_bridge(self):
        orch = MasterOrchestrator(FakeGPUStrategy())
        event = orch.set_strategy(DummyStrategy(), reason="test GPU drain")
        assert event.previous_target == "GPU_CUDA"

    def test_swap_history(self):
        orch = MasterOrchestrator(DummyStrategy())
        orch.set_strategy(DynamicCPUStrategy("nonce + 1"))
        orch.set_strategy(DummyStrategy())
        assert len(orch.swap_history) == 2

    def test_halt_and_reject(self):
        orch = MasterOrchestrator(DummyStrategy())
        orch.halt()
        with pytest.raises(OrchestrationError, match="halted"):
            orch.process_workload(np.arange(5, dtype=np.uint32))

    def test_halt_and_resume(self):
        orch = MasterOrchestrator(DummyStrategy())
        orch.halt()
        orch.resume()
        result = orch.process_workload(np.arange(5, dtype=np.uint32))
        assert result.results is not None

    def test_diagnostics(self):
        orch = MasterOrchestrator(DummyStrategy())
        orch.process_workload(np.arange(10, dtype=np.uint32))
        diag = orch.get_diagnostics()
        assert diag["is_running"] is True
        assert diag["total_batches"] == 1
        assert diag["total_nonces"] == 10

    def test_process_batch(self):
        orch = MasterOrchestrator(DummyStrategy())
        batch = NonceBatch(nonces=np.arange(20, dtype=np.uint32), batch_id=42)
        result = orch.process_batch(batch)
        assert result.batch_id == 42

    def test_anomaly_counting(self):
        """Division by zero in CPU strategy should produce anomalies."""
        strat = DynamicCPUStrategy("1 / nonce")
        orch = MasterOrchestrator(strat)
        nonces = np.arange(0, 5, dtype=np.uint32)  # includes 0
        result = orch.process_workload(nonces)
        assert result.anomalies >= 1  # nonce=0 → inf


# ═════════════════════════════════════════════════════════════════════════
# Pydantic Schemas
# ═════════════════════════════════════════════════════════════════════════

class TestPydanticSchemas:

    def test_valid_injection_request(self):
        from api.schemas import HeuristicInjectionRequest
        req = HeuristicInjectionRequest(
            formula="nonce + 1",
            batch_size=1000,
            target_hardware="CPU",
        )
        assert req.formula == "nonce + 1"
        assert req.batch_size == 1000

    def test_formula_too_long(self):
        from api.schemas import HeuristicInjectionRequest
        with pytest.raises(Exception):  # Pydantic ValidationError
            HeuristicInjectionRequest(
                formula="x" * 300,
                batch_size=1000,
                target_hardware="CPU",
            )

    def test_formula_invalid_chars(self):
        from api.schemas import HeuristicInjectionRequest
        with pytest.raises(Exception):
            HeuristicInjectionRequest(
                formula="nonce; import os",
                batch_size=1000,
                target_hardware="CPU",
            )

    def test_batch_size_bounds(self):
        from api.schemas import HeuristicInjectionRequest
        with pytest.raises(Exception):
            HeuristicInjectionRequest(
                formula="nonce + 1",
                batch_size=100_000_000,  # exceeds 50M limit
                target_hardware="CPU",
            )

    def test_hardware_target_validation(self):
        from api.schemas import HeuristicInjectionRequest
        with pytest.raises(Exception):
            HeuristicInjectionRequest(
                formula="nonce + 1",
                batch_size=1000,
                target_hardware="ASIC",  # not in enum
            )

    def test_validation_request(self):
        from api.schemas import FormulaValidationRequest
        req = FormulaValidationRequest(formula="nonce ** 2")
        assert req.formula == "nonce ** 2"


# ═════════════════════════════════════════════════════════════════════════
# Integration:  Full Pipeline (AST → NumExpr → Orchestrator)
# ═════════════════════════════════════════════════════════════════════════

class TestFullPipeline:
    """End-to-end: formula string enters as text, exits as results array."""

    def test_griffin_962_attractor(self):
        formula = "(nonce ** 1.618) + (1/962) % 0xFFFFFFFF"
        strat = DynamicCPUStrategy(formula=formula)
        orch = MasterOrchestrator(strat)
        nonces = np.arange(1, 10001, dtype=np.uint32)
        result = orch.process_workload(nonces)
        assert result.results.shape == (10000,)
        assert result.hardware_target == "CPU_SANDBOX"
        assert result.anomalies == 0

    def test_hot_swap_mid_pipeline(self):
        orch = MasterOrchestrator(DummyStrategy())
        n = np.arange(100, dtype=np.uint32)

        # Process with dummy
        r1 = orch.process_workload(n)
        assert r1.hardware_target == "DUMMY_TEST"

        # Hot-swap to CPU sandbox
        orch.set_strategy(DynamicCPUStrategy("nonce ** 2"))
        r2 = orch.process_workload(n)
        assert r2.hardware_target == "CPU_SANDBOX"
        assert r2.results[10] == 100.0  # 10^2

    def test_swap_fpga_to_cpu_and_back(self):
        orch = MasterOrchestrator(FakeFPGAStrategy())
        n = np.arange(10, dtype=np.uint32)

        r1 = orch.process_workload(n)
        assert r1.hardware_target == "FPGA_BRIDGE"

        # Hot-swap to CPU
        orch.set_strategy(DynamicCPUStrategy("nonce + 42"))
        r2 = orch.process_workload(n)
        assert r2.hardware_target == "CPU_SANDBOX"
        assert r2.results[0] == 42.0

        # Swap back
        orch.set_strategy(FakeFPGAStrategy())
        r3 = orch.process_workload(n)
        assert r3.hardware_target == "FPGA_BRIDGE"
