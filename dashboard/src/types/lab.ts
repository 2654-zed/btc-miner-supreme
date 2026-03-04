// ─── Strategy Lab Type Definitions ─────────────────────────────────────
// Mirrors Pydantic models from api/lab_schemas.py exactly.

// ── Strategy catalogue ─────────────────────────────────────────────────

export interface StrategyParameter {
  name: string;
  type: "float" | "int" | "str";
  default_value: string;
  min_value: string | null;
  max_value: string | null;
  description: string;
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  category: "entropy_source" | "math_formula";
  parameters: StrategyParameter[];
}

export interface AvailableStrategiesResponse {
  strategies: Strategy[];
}

// ── Benchmark run request ──────────────────────────────────────────────

export interface BenchmarkRunRequest {
  strategy_id: string;
  formula?: string | null;
  batch_size: number;
  parameters?: Record<string, string> | null;
  timeout_seconds: number;
}

// ── Metrics ────────────────────────────────────────────────────────────

export interface MetricsBlock {
  execution_time_ms: number;
  throughput_nonces_per_sec: number;
  mean: number;
  std: number;
  min_val: number;
  max_val: number;
  anomaly_count: number;
  uniqueness_ratio: number;
  ks_statistic: number;
  ks_p_value: number;
}

export interface ComparisonBlock {
  speedup_factor: number;
  mean_divergence: number;
  std_ratio: number;
  anomaly_delta: number;
  distribution_different: boolean;
}

// ── Benchmark run response ─────────────────────────────────────────────

export interface BenchmarkRunResponse {
  run_id: string;
  strategy_id: string;
  strategy_name: string;
  formula: string | null;
  batch_size: number;
  timestamp: string;
  timed_out: boolean;
  strategy_metrics: MetricsBlock;
  baseline_metrics: MetricsBlock;
  comparison: ComparisonBlock;
}

// ── Run list ───────────────────────────────────────────────────────────

export interface RunSummary {
  run_id: string;
  strategy_id: string;
  strategy_name: string;
  formula: string | null;
  batch_size: number;
  timestamp: string;
  timed_out: boolean;
  strategy_execution_time_ms: number;
  baseline_execution_time_ms: number;
  speedup_factor: number;
  distribution_different: boolean;
}

export interface RunListResponse {
  runs: RunSummary[];
  total: number;
  capacity: number;
}

// ── Delete ─────────────────────────────────────────────────────────────

export interface RunDeleteResponse {
  deleted: boolean;
  run_id: string;
}
