"""
tests/test_lab_router.py
────────────────────────
API-level tests for the Strategy Lab router.

Uses ``httpx.AsyncClient`` via ``pytest-asyncio`` to exercise:
  • GET  /api/v1/lab/strategies
  • POST /api/v1/lab/run
  • GET  /api/v1/lab/runs
  • GET  /api/v1/lab/runs/{run_id}
  • DELETE /api/v1/lab/runs/{run_id}

Tests also cover error paths (unknown strategy, missing formula, 404).

Run:  pytest tests/test_lab_router.py -v
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import httpx

from api.router import app  # FastAPI application


# ═════════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def client():
    """Provide an httpx.AsyncClient bound to the FastAPI app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ═════════════════════════════════════════════════════════════════════════
# GET /strategies
# ═════════════════════════════════════════════════════════════════════════

class TestListStrategies:

    @pytest.mark.asyncio
    async def test_returns_200(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/lab/strategies")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_catalogue_has_11_entries(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/lab/strategies")
        strategies = resp.json()["strategies"]
        assert len(strategies) == 11

    @pytest.mark.asyncio
    async def test_each_strategy_has_required_fields(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/lab/strategies")
        for s in resp.json()["strategies"]:
            assert "id" in s
            assert "name" in s
            assert "description" in s
            assert "category" in s
            assert s["category"] in ("entropy_source", "math_formula")

    @pytest.mark.asyncio
    async def test_contains_custom_formula(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/lab/strategies")
        ids = [s["id"] for s in resp.json()["strategies"]]
        assert "custom_formula" in ids

    @pytest.mark.asyncio
    async def test_contains_padic_ladder(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/lab/strategies")
        ids = [s["id"] for s in resp.json()["strategies"]]
        assert "padic_ladder" in ids

    @pytest.mark.asyncio
    async def test_entropy_sources_have_parameters(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/lab/strategies")
        entropy_strats = [
            s for s in resp.json()["strategies"]
            if s["category"] == "entropy_source"
        ]
        # All entropy sources (except maybe padic) should have parameters
        for s in entropy_strats:
            assert isinstance(s["parameters"], list)


# ═════════════════════════════════════════════════════════════════════════
# POST /run
# ═════════════════════════════════════════════════════════════════════════

class TestRunBenchmark:

    @pytest.mark.asyncio
    async def test_run_formula_quadratic(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/lab/run",
            json={
                "strategy_id": "formula_quadratic",
                "batch_size": 1_000,
                "timeout_seconds": 30,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy_id"] == "formula_quadratic"
        assert data["batch_size"] == 1_000
        assert "strategy_metrics" in data
        assert "baseline_metrics" in data
        assert "comparison" in data

    @pytest.mark.asyncio
    async def test_run_returns_metrics_with_all_fields(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/lab/run",
            json={"strategy_id": "formula_euler", "batch_size": 1_000},
        )
        data = resp.json()
        for side in ("strategy_metrics", "baseline_metrics"):
            m = data[side]
            assert "execution_time_ms" in m
            assert "throughput_nonces_per_sec" in m
            assert "mean" in m
            assert "std" in m
            assert "min_val" in m
            assert "max_val" in m
            assert "anomaly_count" in m
            assert "uniqueness_ratio" in m
            assert "ks_statistic" in m
            assert "ks_p_value" in m

    @pytest.mark.asyncio
    async def test_run_returns_comparison(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/lab/run",
            json={"strategy_id": "formula_euler", "batch_size": 1_000},
        )
        comp = resp.json()["comparison"]
        assert "speedup_factor" in comp
        assert "mean_divergence" in comp
        assert "std_ratio" in comp
        assert "anomaly_delta" in comp
        assert "distribution_different" in comp

    @pytest.mark.asyncio
    async def test_run_unknown_strategy_returns_400(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/lab/run",
            json={"strategy_id": "nonexistent_strategy", "batch_size": 1_000},
        )
        assert resp.status_code == 400
        assert "Unknown strategy_id" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_custom_formula_missing_formula_returns_400(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/lab/run",
            json={"strategy_id": "custom_formula", "batch_size": 1_000},
        )
        assert resp.status_code == 400
        assert "formula" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_custom_formula_with_formula(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/lab/run",
            json={
                "strategy_id": "custom_formula",
                "formula": "nonce + 42",
                "batch_size": 1_000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["formula"] == "nonce + 42"

    @pytest.mark.asyncio
    async def test_batch_size_validation(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/lab/run",
            json={"strategy_id": "formula_quadratic", "batch_size": 500},
        )
        assert resp.status_code == 422  # Pydantic validation error


# ═════════════════════════════════════════════════════════════════════════
# GET /runs  &  GET /runs/{run_id}  &  DELETE /runs/{run_id}
# ═════════════════════════════════════════════════════════════════════════

class TestRunsEndpoints:

    @pytest.mark.asyncio
    async def test_list_runs(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/lab/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data
        assert "total" in data
        assert "capacity" in data

    @pytest.mark.asyncio
    async def test_get_run_after_creation(self, client: httpx.AsyncClient):
        # Create a run
        create_resp = await client.post(
            "/api/v1/lab/run",
            json={"strategy_id": "formula_quadratic", "batch_size": 1_000},
        )
        run_id = create_resp.json()["run_id"]

        # Retrieve it
        get_resp = await client.get(f"/api/v1/lab/runs/{run_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["run_id"] == run_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_run_returns_404(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/lab/runs/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_run(self, client: httpx.AsyncClient):
        create_resp = await client.post(
            "/api/v1/lab/run",
            json={"strategy_id": "formula_quadratic", "batch_size": 1_000},
        )
        run_id = create_resp.json()["run_id"]

        del_resp = await client.delete(f"/api/v1/lab/runs/{run_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True
        assert del_resp.json()["run_id"] == run_id

        # Verify it's gone
        get_resp = await client.get(f"/api/v1/lab/runs/{run_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client: httpx.AsyncClient):
        resp = await client.delete("/api/v1/lab/runs/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_run_appears_in_list(self, client: httpx.AsyncClient):
        create_resp = await client.post(
            "/api/v1/lab/run",
            json={"strategy_id": "formula_harmonic", "batch_size": 1_000},
        )
        run_id = create_resp.json()["run_id"]

        list_resp = await client.get("/api/v1/lab/runs")
        run_ids_in_list = [r["run_id"] for r in list_resp.json()["runs"]]
        assert run_id in run_ids_in_list
