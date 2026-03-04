"use client";

import { motion } from "framer-motion";
import type { MetricsBlock } from "@/types/lab";

// ─── Props ─────────────────────────────────────────────────────────────

interface MetricsCardProps {
  title: string;
  metrics: MetricsBlock;
  accentColor: "green" | "cyan" | "orange" | "purple";
}

// ─── Helpers ───────────────────────────────────────────────────────────

function fmt(n: number, decimals = 2): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(decimals)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(decimals)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(decimals)}K`;
  return n.toFixed(decimals);
}

function fmtMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms.toFixed(2)}ms`;
}

function ksVerdict(pValue: number): { label: string; color: string } {
  if (pValue >= 0.05) return { label: "UNIFORM", color: "text-neon-green" };
  if (pValue >= 0.01) return { label: "MARGINAL", color: "text-neon-orange" };
  return { label: "STRUCTURED", color: "text-neon-red" };
}

// ─── Color Mapping ─────────────────────────────────────────────────────

const ACCENT_MAP = {
  green: {
    border: "border-neon-green/40",
    text: "text-neon-green",
    bg: "bg-neon-green/5",
    glow: "glow-green",
  },
  cyan: {
    border: "border-neon-cyan/40",
    text: "text-neon-cyan",
    bg: "bg-neon-cyan/5",
    glow: "glow-cyan",
  },
  orange: {
    border: "border-neon-orange/40",
    text: "text-neon-orange",
    bg: "bg-neon-orange/5",
    glow: "glow-orange",
  },
  purple: {
    border: "border-neon-purple/40",
    text: "text-neon-purple",
    bg: "bg-neon-purple/5",
    glow: "",
  },
};

// ─── Component ─────────────────────────────────────────────────────────

export default function MetricsCard({ title, metrics, accentColor }: MetricsCardProps) {
  const a = ACCENT_MAP[accentColor];
  const ks = ksVerdict(metrics.ks_p_value);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`panel ${a.glow}`}
    >
      <div className={`panel-header ${a.text}`}>{title}</div>

      <div className="p-3 space-y-3">
        {/* Timing row */}
        <div className="grid grid-cols-2 gap-2">
          <Stat label="EXEC TIME" value={fmtMs(metrics.execution_time_ms)} color={a.text} />
          <Stat
            label="THROUGHPUT"
            value={`${fmt(metrics.throughput_nonces_per_sec)}/s`}
            color={a.text}
          />
        </div>

        {/* Distribution row */}
        <div className="grid grid-cols-3 gap-2">
          <Stat label="MEAN" value={fmt(metrics.mean, 4)} color="text-text-primary" />
          <Stat label="STD" value={fmt(metrics.std, 4)} color="text-text-primary" />
          <Stat
            label="UNIQUE"
            value={`${(metrics.uniqueness_ratio * 100).toFixed(1)}%`}
            color="text-text-primary"
          />
        </div>

        {/* Range row */}
        <div className="grid grid-cols-2 gap-2">
          <Stat label="MIN" value={fmt(metrics.min_val, 4)} color="text-text-dim" />
          <Stat label="MAX" value={fmt(metrics.max_val, 4)} color="text-text-dim" />
        </div>

        {/* KS + anomalies */}
        <div className="border-t border-border-dim pt-2 grid grid-cols-3 gap-2">
          <Stat label="KS STAT" value={metrics.ks_statistic.toFixed(4)} color="text-text-primary" />
          <Stat label="KS p" value={metrics.ks_p_value.toFixed(4)} color={ks.color} />
          <Stat label="VERDICT" value={ks.label} color={ks.color} />
        </div>

        {/* Anomalies */}
        {metrics.anomaly_count > 0 && (
          <div className="border border-neon-orange/30 bg-neon-orange/5 rounded p-2">
            <span className="font-mono text-[9px] text-neon-orange">
              ⚠ {metrics.anomaly_count.toLocaleString()} anomalies (NaN/Inf)
            </span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ─── Sub-component ─────────────────────────────────────────────────────

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <div className="font-mono text-[7px] text-text-dim tracking-widest">{label}</div>
      <div className={`font-mono text-[11px] font-bold ${color}`}>{value}</div>
    </div>
  );
}
