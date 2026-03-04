"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
  Cell,
} from "recharts";
import type { MetricsBlock } from "@/types/lab";

// ─── Props ─────────────────────────────────────────────────────────────

interface BenchmarkChartProps {
  strategyMetrics: MetricsBlock;
  baselineMetrics: MetricsBlock;
  strategyName: string;
}

// ─── Helpers ───────────────────────────────────────────────────────────

function fmt(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toFixed(2);
}

// ─── Theme / colors ────────────────────────────────────────────────────

const STRATEGY_COLOR = "#00ff66";
const BASELINE_COLOR = "#00d4ff";
const TOOLTIP_STYLE = {
  background: "#0d0d1a",
  border: "1px solid #1a1a3e",
  borderRadius: 6,
  fontFamily: "var(--font-mono)",
  fontSize: 10,
};

// ─── Component ─────────────────────────────────────────────────────────

export default function BenchmarkChart({
  strategyMetrics,
  baselineMetrics,
  strategyName,
}: BenchmarkChartProps) {
  // ── Throughput comparison ────────────────────────────────────────
  const throughputData = [
    {
      name: strategyName,
      value: strategyMetrics.throughput_nonces_per_sec,
      fill: STRATEGY_COLOR,
    },
    {
      name: "CSPRNG Baseline",
      value: baselineMetrics.throughput_nonces_per_sec,
      fill: BASELINE_COLOR,
    },
  ];

  // ── Distribution comparison (normalized) ─────────────────────────
  const distributionData = [
    {
      metric: "Mean",
      strategy: strategyMetrics.mean,
      baseline: baselineMetrics.mean,
    },
    {
      metric: "Std Dev",
      strategy: strategyMetrics.std,
      baseline: baselineMetrics.std,
    },
    {
      metric: "Min",
      strategy: strategyMetrics.min_val,
      baseline: baselineMetrics.min_val,
    },
    {
      metric: "Max",
      strategy: strategyMetrics.max_val,
      baseline: baselineMetrics.max_val,
    },
  ];

  // ── KS score comparison ──────────────────────────────────────────
  const ksData = [
    {
      metric: "KS Statistic",
      strategy: strategyMetrics.ks_statistic,
      baseline: baselineMetrics.ks_statistic,
    },
    {
      metric: "KS p-value",
      strategy: strategyMetrics.ks_p_value,
      baseline: baselineMetrics.ks_p_value,
    },
    {
      metric: "Uniqueness",
      strategy: strategyMetrics.uniqueness_ratio,
      baseline: baselineMetrics.uniqueness_ratio,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {/* ── Throughput bar chart ──────────────────────────────────── */}
      <div className="panel">
        <div className="panel-header">⟐ Throughput Comparison</div>
        <div className="p-3 h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={throughputData} layout="vertical" barCategoryGap="30%">
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1a3e" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fontSize: 8, fill: "#6b7280" }}
                tickFormatter={fmt}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 8, fill: "#6b7280" }}
                width={90}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(value) => [
                  `${fmt(Number(value))} nonces/s`,
                  "Throughput",
                ]}
              />
              <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                {throughputData.map((entry, idx) => (
                  <Cell key={idx} fill={entry.fill} opacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Distribution comparison ───────────────────────────────── */}
      <div className="panel">
        <div className="panel-header">⟐ Distribution Comparison</div>
        <div className="p-3 h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={distributionData} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1a3e" />
              <XAxis
                dataKey="metric"
                tick={{ fontSize: 8, fill: "#6b7280" }}
              />
              <YAxis
                tick={{ fontSize: 8, fill: "#6b7280" }}
                tickFormatter={fmt}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(value) => fmt(Number(value))}
              />
              <Legend
                wrapperStyle={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 9,
                }}
              />
              <Bar
                dataKey="strategy"
                name={strategyName}
                fill={STRATEGY_COLOR}
                opacity={0.85}
                radius={[3, 3, 0, 0]}
              />
              <Bar
                dataKey="baseline"
                name="CSPRNG"
                fill={BASELINE_COLOR}
                opacity={0.85}
                radius={[3, 3, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── KS / Quality comparison ──────────────────────────────── */}
      <div className="col-span-2 panel">
        <div className="panel-header">⟐ Statistical Quality — KS Test &amp; Uniqueness</div>
        <div className="p-3 h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={ksData} barCategoryGap="25%">
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1a3e" />
              <XAxis
                dataKey="metric"
                tick={{ fontSize: 9, fill: "#6b7280" }}
              />
              <YAxis
                domain={[0, 1]}
                tick={{ fontSize: 8, fill: "#6b7280" }}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(value) => Number(value).toFixed(6)}
              />
              <Legend
                wrapperStyle={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 9,
                }}
              />
              <Bar
                dataKey="strategy"
                name={strategyName}
                fill={STRATEGY_COLOR}
                opacity={0.85}
                radius={[3, 3, 0, 0]}
              />
              <Bar
                dataKey="baseline"
                name="CSPRNG"
                fill={BASELINE_COLOR}
                opacity={0.85}
                radius={[3, 3, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
