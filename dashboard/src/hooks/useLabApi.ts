"use client";

import { useState, useCallback, useRef } from "react";
import type {
  AvailableStrategiesResponse,
  BenchmarkRunRequest,
  BenchmarkRunResponse,
  RunListResponse,
  RunDeleteResponse,
  Strategy,
  RunSummary,
} from "@/types/lab";

// ─── API Configuration ────────────────────────────────────────────────
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const LAB_BASE = `${API_BASE}/api/v1/lab`;

// ─── Error container ──────────────────────────────────────────────────
export interface LabApiError {
  status: number;
  detail: string;
}

function isLabApiError(err: unknown): err is LabApiError {
  return (
    typeof err === "object" &&
    err !== null &&
    "status" in err &&
    "detail" in err
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────

export function useLabApi() {
  // ── Strategies ────────────────────────────────────────────────────
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategiesLoading, setStrategiesLoading] = useState(false);
  const [strategiesError, setStrategiesError] = useState<string | null>(null);

  // ── Active run ────────────────────────────────────────────────────
  const [lastResult, setLastResult] = useState<BenchmarkRunResponse | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  // ── Run history ───────────────────────────────────────────────────
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsCapacity, setRunsCapacity] = useState(50);
  const [runsLoading, setRunsLoading] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  // ── Fetch strategies ──────────────────────────────────────────────

  const fetchStrategies = useCallback(async () => {
    setStrategiesLoading(true);
    setStrategiesError(null);
    try {
      const res = await fetch(`${LAB_BASE}/strategies`, {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        throw { status: res.status, detail: body.detail ?? res.statusText };
      }
      const data: AvailableStrategiesResponse = await res.json();
      setStrategies(data.strategies);
    } catch (err) {
      if (isLabApiError(err)) {
        setStrategiesError(err.detail);
      } else {
        setStrategiesError("Unable to reach API server.");
      }
    } finally {
      setStrategiesLoading(false);
    }
  }, []);

  // ── Run benchmark ─────────────────────────────────────────────────

  const runBenchmark = useCallback(async (request: BenchmarkRunRequest) => {
    // Abort any in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setRunLoading(true);
    setRunError(null);
    setLastResult(null);

    try {
      const res = await fetch(`${LAB_BASE}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      const data = await res.json();

      if (!res.ok) {
        const detail = data.detail ?? res.statusText;
        if (res.status === 403) {
          setRunError(`Security Policy Violation: ${detail}`);
        } else if (res.status === 408) {
          setRunError(`Benchmark timed out: ${detail}`);
        } else {
          setRunError(detail);
        }
        return null;
      }

      const result: BenchmarkRunResponse = data;
      setLastResult(result);
      return result;
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return null;
      setRunError("Network error: unable to reach API server.");
      return null;
    } finally {
      setRunLoading(false);
    }
  }, []);

  // ── Fetch run history ─────────────────────────────────────────────

  const fetchRuns = useCallback(async () => {
    setRunsLoading(true);
    try {
      const res = await fetch(`${LAB_BASE}/runs`, {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) return;
      const data: RunListResponse = await res.json();
      setRuns(data.runs);
      setRunsTotal(data.total);
      setRunsCapacity(data.capacity);
    } catch {
      // Silently fail — history is non-critical
    } finally {
      setRunsLoading(false);
    }
  }, []);

  // ── Delete a run ──────────────────────────────────────────────────

  const deleteRun = useCallback(async (runId: string) => {
    try {
      const res = await fetch(`${LAB_BASE}/runs/${runId}`, {
        method: "DELETE",
      });
      if (!res.ok) return false;
      const data: RunDeleteResponse = await res.json();
      if (data.deleted) {
        // Optimistically remove from local state
        setRuns((prev) => prev.filter((r) => r.run_id !== runId));
        setRunsTotal((prev) => Math.max(0, prev - 1));
      }
      return data.deleted;
    } catch {
      return false;
    }
  }, []);

  // ── Get single run ────────────────────────────────────────────────

  const getRun = useCallback(async (runId: string): Promise<BenchmarkRunResponse | null> => {
    try {
      const res = await fetch(`${LAB_BASE}/runs/${runId}`, {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) return null;
      const data: BenchmarkRunResponse = await res.json();
      setLastResult(data);
      return data;
    } catch {
      return null;
    }
  }, []);

  return {
    // Strategies
    strategies,
    strategiesLoading,
    strategiesError,
    fetchStrategies,

    // Active run
    lastResult,
    runLoading,
    runError,
    runBenchmark,

    // History
    runs,
    runsTotal,
    runsCapacity,
    runsLoading,
    fetchRuns,
    deleteRun,
    getRun,
  };
}
