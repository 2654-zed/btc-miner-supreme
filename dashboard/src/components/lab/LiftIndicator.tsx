"use client";

import { motion } from "framer-motion";
import type { ComparisonBlock } from "@/types/lab";

// ─── Props ─────────────────────────────────────────────────────────────

interface LiftIndicatorProps {
  comparison: ComparisonBlock;
  strategyName: string;
}

// ─── Component ─────────────────────────────────────────────────────────

/**
 * Visual "lift" indicator inspired by §6 of the Research-Lab handover.
 *
 * Displays the speedup factor as an animated gauge, the distribution
 * verdict as a status badge, and the mean divergence as a delta bar.
 * All values are empirically computed by BenchmarkEngine — nothing
 * is fabricated.
 */
export default function LiftIndicator({
  comparison,
  strategyName,
}: LiftIndicatorProps) {
  const speedup = comparison.speedup_factor;
  const isFaster = speedup >= 1.0;

  // Clamp gauge to [0, 2] for display (>2× extremely rare)
  const gaugeRatio = Math.min(speedup / 2.0, 1.0);
  const gaugeAngle = gaugeRatio * 180;

  // Verdict colour
  const distVerdict = comparison.distribution_different;

  return (
    <div className="panel glow-purple">
      <div className="panel-header text-neon-purple">⟐ Empirical Lift Analysis</div>

      <div className="p-4">
        {/* ── Speedup gauge (SVG arc) ──────────────────────────────── */}
        <div className="flex flex-col items-center mb-4">
          <div className="relative w-44 h-[88px] overflow-hidden">
            {/* Background arc */}
            <svg viewBox="0 0 180 92" className="absolute inset-0 w-full h-full">
              <defs>
                <linearGradient id="liftGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#ff4500" />
                  <stop offset="50%" stopColor="#a855f7" />
                  <stop offset="100%" stopColor="#00ff66" />
                </linearGradient>
              </defs>
              {/* Track */}
              <path
                d="M 10 88 A 80 80 0 0 1 170 88"
                fill="none"
                stroke="#1a1a3e"
                strokeWidth="10"
                strokeLinecap="round"
              />
              {/* Fill */}
              <motion.path
                d="M 10 88 A 80 80 0 0 1 170 88"
                fill="none"
                stroke="url(#liftGrad)"
                strokeWidth="10"
                strokeLinecap="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: gaugeRatio }}
                transition={{ duration: 1.2, ease: "easeOut" }}
              />
              {/* Tick marks */}
              <text x="8" y="86" fill="#6b7280" fontSize="8" fontFamily="var(--font-mono)">0×</text>
              <text x="80" y="12" fill="#6b7280" fontSize="8" fontFamily="var(--font-mono)" textAnchor="middle">1×</text>
              <text x="158" y="86" fill="#6b7280" fontSize="8" fontFamily="var(--font-mono)">2×</text>
            </svg>

            {/* Center value */}
            <div className="absolute inset-0 flex items-end justify-center pb-0">
              <motion.span
                key={speedup.toFixed(2)}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                className={`font-mono text-2xl font-bold ${
                  isFaster ? "text-neon-green text-glow-green" : "text-neon-orange"
                }`}
              >
                {speedup.toFixed(2)}×
              </motion.span>
            </div>
          </div>
          <span className="font-mono text-[9px] text-text-dim tracking-widest mt-1">
            SPEEDUP FACTOR — {isFaster ? "FASTER" : "SLOWER"} THAN CSPRNG
          </span>
        </div>

        {/* ── Metrics grid ─────────────────────────────────────────── */}
        <div className="grid grid-cols-3 gap-2">
          {/* Mean divergence */}
          <div className="bg-bg-primary rounded p-2.5 border border-border-dim text-center">
            <div className="font-mono text-[7px] text-text-dim tracking-widest">MEAN DIVERGENCE</div>
            <div className="font-mono text-sm font-bold text-neon-purple mt-1">
              {(comparison.mean_divergence * 100).toFixed(2)}%
            </div>
            <MiniBar ratio={Math.min(comparison.mean_divergence, 1.0)} color="#a855f7" />
          </div>

          {/* Std ratio */}
          <div className="bg-bg-primary rounded p-2.5 border border-border-dim text-center">
            <div className="font-mono text-[7px] text-text-dim tracking-widest">STD RATIO</div>
            <div className="font-mono text-sm font-bold text-neon-cyan mt-1">
              {comparison.std_ratio.toFixed(4)}
            </div>
            <MiniBar ratio={Math.min(comparison.std_ratio, 1.0)} color="#00d4ff" />
          </div>

          {/* Distribution verdict */}
          <div className="bg-bg-primary rounded p-2.5 border border-border-dim text-center">
            <div className="font-mono text-[7px] text-text-dim tracking-widest">DISTRIBUTION</div>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className={`font-mono text-sm font-bold mt-1 ${
                distVerdict ? "text-neon-red" : "text-neon-green"
              }`}
            >
              {distVerdict ? "DIFFERENT" : "SIMILAR"}
            </motion.div>
            <div
              className={`mt-1.5 h-1 rounded-full ${
                distVerdict ? "bg-neon-red/40" : "bg-neon-green/40"
              }`}
            />
          </div>
        </div>

        {/* ── Theory note ──────────────────────────────────────────── */}
        <div className="border-t border-border-dim pt-3 mt-3">
          <p className="font-mono text-[8px] text-text-dim leading-relaxed">
            Lift = Strategy throughput ÷ Baseline throughput.
            KS test determines if output distribution diverges from uniform.
            Strategy: <span className="text-neon-green">{strategyName}</span> vs{" "}
            <span className="text-neon-cyan">secrets.token_bytes</span> (CSPRNG).
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Mini progress bar ─────────────────────────────────────────────────

function MiniBar({ ratio, color }: { ratio: number; color: string }) {
  return (
    <div className="mt-1.5 h-1 bg-border-dim rounded-full overflow-hidden">
      <motion.div
        className="h-full rounded-full"
        style={{ backgroundColor: color }}
        initial={{ width: 0 }}
        animate={{ width: `${Math.max(ratio * 100, 2)}%` }}
        transition={{ duration: 0.8, ease: "easeOut" }}
      />
    </div>
  );
}
