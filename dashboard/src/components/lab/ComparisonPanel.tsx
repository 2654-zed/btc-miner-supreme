"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import type { ComparisonBlock, BenchmarkRunResponse } from "@/types/lab";
import MetricsCard from "./MetricsCard";
import BenchmarkChart from "./BenchmarkChart";
import LiftIndicator from "./LiftIndicator";

// ─── Props ─────────────────────────────────────────────────────────────

interface ComparisonPanelProps {
  result: BenchmarkRunResponse;
}

// ─── Tab type ──────────────────────────────────────────────────────────

type ViewTab = "overview" | "charts" | "raw";

// ─── Component ─────────────────────────────────────────────────────────

export default function ComparisonPanel({ result }: ComparisonPanelProps) {
  const c = result.comparison;
  const [activeTab, setActiveTab] = useState<ViewTab>("overview");

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-3"
    >
      {/* ── Header banner ──────────────────────────────────────────── */}
      <div className="panel">
        <div className="panel-header flex items-center justify-between">
          <span>⟐ Benchmark Result</span>
          <span className="text-[9px] text-text-dim">{result.run_id.slice(0, 8)}</span>
        </div>

        <div className="p-3">
          {/* Strategy label */}
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="font-mono text-[11px] text-neon-green font-bold">
                {result.strategy_name}
              </div>
              {result.formula && (
                <div className="font-mono text-[9px] text-text-dim mt-0.5">
                  f(nonce) = {result.formula}
                </div>
              )}
            </div>
            <div className="text-right">
              <div className="font-mono text-[8px] text-text-dim tracking-widest">BATCH</div>
              <div className="font-mono text-[11px] text-neon-cyan font-bold">
                {result.batch_size.toLocaleString()}
              </div>
            </div>
          </div>

          {/* Timeout warning */}
          {result.timed_out && (
            <div className="border border-neon-orange/30 bg-neon-orange/5 rounded p-2 mb-3">
              <span className="font-mono text-[9px] text-neon-orange">
                ⚠ RUN TIMED OUT — partial metrics may be incomplete
              </span>
            </div>
          )}

          {/* Comparison chips */}
          <ComparisonRow comparison={c} />

          {/* Tab switcher */}
          <div className="flex gap-1 mt-3 border-t border-border-dim pt-3">
            {(["overview", "charts", "raw"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`font-mono text-[9px] px-3 py-1.5 rounded border transition-all ${
                  activeTab === tab
                    ? "border-neon-purple text-neon-purple bg-neon-purple/10"
                    : "border-border-dim text-text-dim hover:border-neon-purple/40"
                }`}
              >
                {tab === "overview" ? "⟐ OVERVIEW" : tab === "charts" ? "⟐ CHARTS" : "⟐ RAW DATA"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Tab: Overview ──────────────────────────────────────────── */}
      {activeTab === "overview" && (
        <motion.div
          key="overview"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="space-y-3"
        >
          {/* Lift indicator */}
          <LiftIndicator
            comparison={result.comparison}
            strategyName={result.strategy_name}
          />

          {/* Side-by-side metrics cards */}
          <div className="grid grid-cols-2 gap-3">
            <MetricsCard
              title="⟐ STRATEGY"
              metrics={result.strategy_metrics}
              accentColor="green"
            />
            <MetricsCard
              title="⟐ CSPRNG BASELINE"
              metrics={result.baseline_metrics}
              accentColor="cyan"
            />
          </div>
        </motion.div>
      )}

      {/* ── Tab: Charts ────────────────────────────────────────────── */}
      {activeTab === "charts" && (
        <motion.div
          key="charts"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <BenchmarkChart
            strategyMetrics={result.strategy_metrics}
            baselineMetrics={result.baseline_metrics}
            strategyName={result.strategy_name}
          />
        </motion.div>
      )}

      {/* ── Tab: Raw Data ──────────────────────────────────────────── */}
      {activeTab === "raw" && (
        <motion.div
          key="raw"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="panel"
        >
          <div className="panel-header">⟐ Raw JSON Response</div>
          <pre className="p-4 font-mono text-[10px] text-text-dim overflow-auto max-h-96 leading-relaxed">
            {JSON.stringify(result, null, 2)}
          </pre>
        </motion.div>
      )}
    </motion.div>
  );
}

// ─── Comparison Row ────────────────────────────────────────────────────

function ComparisonRow({ comparison }: { comparison: ComparisonBlock }) {
  const speedColor =
    comparison.speedup_factor >= 1.0 ? "text-neon-green" : "text-neon-orange";
  const distColor =
    comparison.distribution_different ? "text-neon-red" : "text-neon-green";

  return (
    <div className="grid grid-cols-5 gap-2">
      <ComparisonChip
        label="SPEEDUP"
        value={`${comparison.speedup_factor.toFixed(2)}×`}
        color={speedColor}
      />
      <ComparisonChip
        label="MEAN DIV"
        value={comparison.mean_divergence.toFixed(4)}
        color="text-text-primary"
      />
      <ComparisonChip
        label="STD RATIO"
        value={comparison.std_ratio.toFixed(4)}
        color="text-text-primary"
      />
      <ComparisonChip
        label="Δ ANOMALY"
        value={comparison.anomaly_delta.toString()}
        color={comparison.anomaly_delta > 0 ? "text-neon-orange" : "text-text-primary"}
      />
      <ComparisonChip
        label="DIST"
        value={comparison.distribution_different ? "DIFFERENT" : "SIMILAR"}
        color={distColor}
      />
    </div>
  );
}

function ComparisonChip({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="text-center bg-bg-primary rounded p-2 border border-border-dim">
      <div className="font-mono text-[7px] text-text-dim tracking-widest">{label}</div>
      <div className={`font-mono text-[11px] font-bold ${color}`}>{value}</div>
    </div>
  );
}
