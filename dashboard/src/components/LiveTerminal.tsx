"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { TerminalLine } from "@/types";

interface LiveTerminalProps {
  lines: TerminalLine[];
}

const TAG_COLORS: Record<string, string> = {
  Stratum: "text-neon-cyan",
  Griffin: "text-neon-green",
  Zeta: "text-neon-purple",
  GAN: "text-neon-orange",
  Observer: "text-neon-cyan",
  Cone: "text-neon-green",
  GPU: "text-neon-green",
  FPGA: "text-neon-cyan",
  Block: "text-yellow-400",
  Wallet: "text-neon-orange",
};

const LEVEL_COLORS: Record<string, string> = {
  info: "text-text-primary",
  success: "text-neon-green",
  warning: "text-neon-orange",
  error: "text-neon-red",
};

export default function LiveTerminal({ lines }: LiveTerminalProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);

  const filteredLines = filter
    ? lines.filter((l) => l.tag === filter)
    : lines;

  // Auto-scroll
  useEffect(() => {
    if (!paused && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredLines.length, paused]);

  const togglePause = useCallback(() => setPaused((p) => !p), []);

  return (
    <div className="panel flex flex-col h-full">
      {/* Header */}
      <div className="panel-header flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span>⟐ Live Terminal Feed</span>
          <span className="text-[9px] text-text-dim">
            {filteredLines.length} lines
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Filter buttons */}
          <div className="flex gap-1">
            {["Stratum", "Griffin", "GPU", "Block"].map((tag) => (
              <button
                key={tag}
                onClick={() => setFilter(filter === tag ? null : tag)}
                className={`font-mono text-[8px] px-1.5 py-0.5 rounded border transition-colors ${
                  filter === tag
                    ? "border-neon-green text-neon-green bg-neon-green/10"
                    : "border-border-dim text-text-dim hover:border-neon-green/40"
                }`}
              >
                {tag}
              </button>
            ))}
          </div>

          {/* Pause button */}
          <button
            onClick={togglePause}
            className={`font-mono text-[9px] px-2 py-0.5 rounded border transition-colors ${
              paused
                ? "border-neon-orange text-neon-orange bg-neon-orange/10"
                : "border-border-dim text-text-dim hover:border-neon-green/40"
            }`}
          >
            {paused ? "▶ RESUME" : "⏸ PAUSE"}
          </button>
        </div>
      </div>

      {/* Terminal body */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 bg-bg-primary/50 font-mono text-[11px] leading-relaxed min-h-0"
      >
        <AnimatePresence initial={false}>
          {filteredLines.slice(-100).map((line) => (
            <motion.div
              key={line.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.15 }}
              className="flex gap-2 hover:bg-border-dim/20 px-1 rounded"
            >
              <span className="text-text-dim shrink-0 select-none">
                {line.timestamp}
              </span>
              <span
                className={`shrink-0 select-none w-16 text-right ${
                  TAG_COLORS[line.tag] || "text-text-dim"
                }`}
              >
                [{line.tag}]
              </span>
              <span className={LEVEL_COLORS[line.level] || "text-text-primary"}>
                {line.message}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Paused indicator */}
      {paused && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="border-t border-neon-orange/30 bg-neon-orange/5 px-3 py-1 text-center"
        >
          <span className="font-mono text-[10px] text-neon-orange animate-pulse">
            ⏸ FEED PAUSED — click RESUME to continue
          </span>
        </motion.div>
      )}
    </div>
  );
}
