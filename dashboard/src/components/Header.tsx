"use client";

import { motion } from "framer-motion";
import type { MiningStats, ProfitMetrics } from "@/types";

interface HeaderProps {
  mining: MiningStats;
  profit: ProfitMetrics;
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
}

function formatHashRate(eh: number): string {
  return `${eh.toFixed(2)} EH/s`;
}

function formatNumber(n: number): string {
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  return n.toLocaleString();
}

export default function Header({ mining, profit }: HeaderProps) {
  return (
    <header className="border-b border-border-dim bg-bg-panel/80 backdrop-blur-sm sticky top-0 z-50">
      <div className="flex items-center justify-between px-6 py-3">
        {/* Logo & Title */}
        <div className="flex items-center gap-4">
          <motion.div
            className="relative"
            animate={{ rotate: 360 }}
            transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
          >
            <div className="w-10 h-10 rounded-full border-2 border-neon-green flex items-center justify-center text-neon-green font-bold text-lg text-glow-green">
              Ω
            </div>
          </motion.div>

          <div>
            <h1 className="font-mono text-sm font-bold tracking-[0.2em] text-neon-green text-glow-green">
              ΩINTELLIGENCE™ SUPREMACY CORE
            </h1>
            <p className="font-mono text-[10px] text-text-dim tracking-widest">
              COLLAPSE-THEORETIC MINING ENGINE v4.2.0
            </p>
          </div>

          {/* Status indicator */}
          <div className="flex items-center gap-2 ml-6">
            <motion.div
              className="w-2.5 h-2.5 rounded-full bg-neon-green"
              animate={{ opacity: [1, 0.4, 1] }}
              transition={{ duration: 1.5, repeat: Infinity }}
            />
            <span className="font-mono text-[11px] text-neon-green">
              {mining.stratumConnected ? "MINING ACTIVE" : "DISCONNECTED"}
            </span>
          </div>
        </div>

        {/* Global Metrics Bar */}
        <div className="flex items-center gap-6">
          <MetricChip
            label="HASHRATE"
            value={formatHashRate(profit.hashRate)}
            color="text-neon-green"
          />
          <MetricChip
            label="NET SHARE"
            value={`${(profit.networkShare * 100).toFixed(5)}%`}
            color="text-neon-cyan"
          />
          <MetricChip
            label="DIFFICULTY"
            value={formatNumber(profit.networkDifficulty)}
            color="text-neon-orange"
          />
          <MetricChip
            label="BLOCKS"
            value={mining.blocksFound.toString()}
            color="text-neon-green"
          />
          <MetricChip
            label="ROUNDS"
            value={formatNumber(mining.totalRounds)}
            color="text-text-dim"
          />
          <MetricChip
            label="UPTIME"
            value={formatUptime(mining.uptime)}
            color="text-text-dim"
          />

          {/* Phase indicator */}
          <div className="border-l border-border-dim pl-4">
            <div className="font-mono text-[9px] text-text-dim tracking-widest">PHASE</div>
            <motion.div
              key={mining.currentPhase}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="font-mono text-[11px] text-neon-cyan text-glow-cyan"
            >
              {mining.currentPhase}
            </motion.div>
          </div>
        </div>
      </div>
    </header>
  );
}

function MetricChip({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="text-center">
      <div className="font-mono text-[9px] text-text-dim tracking-widest">{label}</div>
      <div className={`font-mono text-sm font-bold ${color}`}>{value}</div>
    </div>
  );
}
