"use client";

import { motion, AnimatePresence } from "framer-motion";
import type { RunSummary } from "@/types/lab";

// ─── Props ─────────────────────────────────────────────────────────────

interface RunHistoryProps {
  runs: RunSummary[];
  total: number;
  capacity: number;
  loading: boolean;
  onSelect: (runId: string) => void;
  onDelete: (runId: string) => void;
  onRefresh: () => void;
}

// ─── Helpers ───────────────────────────────────────────────────────────

function fmtMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms.toFixed(1)}ms`;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ─── Component ─────────────────────────────────────────────────────────

export default function RunHistory({
  runs,
  total,
  capacity,
  loading,
  onSelect,
  onDelete,
  onRefresh,
}: RunHistoryProps) {
  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <span>⟐ Run History</span>
        <div className="flex items-center gap-3">
          <span className="text-[9px] text-text-dim">
            {total}/{capacity} STORED
          </span>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="font-mono text-[8px] text-neon-cyan hover:text-neon-cyan/80 transition-colors disabled:opacity-40"
          >
            {loading ? "⟳" : "↻ REFRESH"}
          </button>
        </div>
      </div>

      <div className="max-h-64 overflow-y-auto">
        {runs.length === 0 && !loading && (
          <div className="p-4 text-center">
            <span className="font-mono text-[10px] text-text-dim">
              No benchmark runs yet. Execute one above.
            </span>
          </div>
        )}

        <AnimatePresence>
          {runs.map((run) => (
            <motion.div
              key={run.run_id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 8 }}
              className="border-b border-border-dim last:border-b-0 px-3 py-2 hover:bg-bg-card/50 transition-colors cursor-pointer group"
              onClick={() => onSelect(run.run_id)}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-neon-green font-semibold truncate">
                      {run.strategy_name}
                    </span>
                    {run.timed_out && (
                      <span className="font-mono text-[7px] text-neon-orange border border-neon-orange/30 rounded px-1">
                        TIMEOUT
                      </span>
                    )}
                    {run.distribution_different && (
                      <span className="font-mono text-[7px] text-neon-red border border-neon-red/30 rounded px-1">
                        STRUCTURED
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-3 mt-0.5">
                    <span className="font-mono text-[8px] text-text-dim">
                      {run.batch_size.toLocaleString()} nonces
                    </span>
                    <span className="font-mono text-[8px] text-text-dim">
                      {fmtMs(run.strategy_execution_time_ms)}
                    </span>
                    <span
                      className={`font-mono text-[8px] font-bold ${
                        run.speedup_factor >= 1 ? "text-neon-green" : "text-neon-orange"
                      }`}
                    >
                      {run.speedup_factor.toFixed(2)}× speedup
                    </span>
                    <span className="font-mono text-[8px] text-text-dim">
                      {relativeTime(run.timestamp)}
                    </span>
                  </div>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(run.run_id);
                  }}
                  className="font-mono text-[9px] text-text-dim hover:text-neon-red transition-colors opacity-0 group-hover:opacity-100 ml-2 shrink-0"
                  title="Delete run"
                >
                  ✕
                </button>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
