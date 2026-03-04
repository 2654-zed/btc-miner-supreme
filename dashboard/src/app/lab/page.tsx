"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { useLabApi } from "@/hooks/useLabApi";
import StrategySelector, {
  type StrategyConfig,
} from "@/components/lab/StrategySelector";
import ComparisonPanel from "@/components/lab/ComparisonPanel";
import RunHistory from "@/components/lab/RunHistory";
import type { BenchmarkRunRequest } from "@/types/lab";

// ─── Page ──────────────────────────────────────────────────────────────

export default function LabPage() {
  const {
    strategies,
    strategiesLoading,
    strategiesError,
    fetchStrategies,
    lastResult,
    runLoading,
    runError,
    runBenchmark,
    runs,
    runsTotal,
    runsCapacity,
    runsLoading,
    fetchRuns,
    deleteRun,
    getRun,
  } = useLabApi();

  // Local config from StrategySelector
  const configRef = useRef<StrategyConfig>({
    strategyId: "",
    formula: "",
    batchSize: 1_000_000,
    timeoutSeconds: 30,
    parameters: {},
  });
  const [configValid, setConfigValid] = useState(false);

  // Load strategies + history on mount
  useEffect(() => {
    fetchStrategies();
    fetchRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConfigChange = useCallback((config: StrategyConfig) => {
    configRef.current = config;
    setConfigValid(config.strategyId !== "");
  }, []);

  const handleRun = useCallback(async () => {
    const cfg = configRef.current;
    if (!cfg.strategyId) return;

    const request: BenchmarkRunRequest = {
      strategy_id: cfg.strategyId,
      batch_size: cfg.batchSize,
      timeout_seconds: cfg.timeoutSeconds,
      parameters:
        Object.keys(cfg.parameters).length > 0 ? cfg.parameters : null,
    };

    // Include formula for custom_formula
    if (cfg.strategyId === "custom_formula" && cfg.formula.trim()) {
      request.formula = cfg.formula;
    }

    const result = await runBenchmark(request);
    if (result) {
      // Refresh history after successful run
      fetchRuns();
    }
  }, [runBenchmark, fetchRuns]);

  const handleSelectRun = useCallback(
    (runId: string) => {
      getRun(runId);
    },
    [getRun],
  );

  return (
    <div className="min-h-screen bg-bg-primary grid-bg">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="border-b border-border-dim bg-bg-panel/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-4">
            <motion.div
              className="relative"
              animate={{ rotate: 360 }}
              transition={{
                duration: 20,
                repeat: Infinity,
                ease: "linear",
              }}
            >
              <div className="w-10 h-10 rounded-full border-2 border-neon-purple flex items-center justify-center text-neon-purple font-bold text-lg">
                Ω
              </div>
            </motion.div>

            <div>
              <h1 className="font-mono text-sm font-bold tracking-[0.2em] text-neon-purple">
                STRATEGY LAB
              </h1>
              <p className="font-mono text-[10px] text-text-dim tracking-widest">
                BENCHMARK &amp; COMPARE NONCE-SELECTION STRATEGIES
              </p>
            </div>

            {/* Status */}
            <div className="flex items-center gap-2 ml-6">
              <motion.div
                className={`w-2.5 h-2.5 rounded-full ${
                  runLoading ? "bg-neon-cyan" : "bg-neon-green"
                }`}
                animate={{ opacity: runLoading ? [1, 0.3, 1] : 1 }}
                transition={
                  runLoading
                    ? { duration: 0.8, repeat: Infinity }
                    : undefined
                }
              />
              <span className="font-mono text-[11px] text-neon-green">
                {runLoading ? "BENCHMARKING…" : "IDLE"}
              </span>
            </div>
          </div>

          {/* Nav link back to dashboard */}
          <Link
            href="/"
            className="font-mono text-[10px] text-text-dim hover:text-neon-green transition-colors border border-border-dim hover:border-neon-green/40 rounded px-3 py-1.5"
          >
            ← OPERATIONS DASHBOARD
          </Link>
        </div>
      </header>

      {/* ── Main layout ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-12 gap-3 p-3">
        {/* Left column: Strategy selector + Run button + History */}
        <div className="col-span-4 space-y-3">
          {/* Loading / error states for strategies */}
          {strategiesLoading && (
            <div className="panel p-4 text-center">
              <span className="font-mono text-[10px] text-neon-cyan animate-pulse">
                Loading strategies…
              </span>
            </div>
          )}

          {strategiesError && (
            <div className="panel p-4">
              <div className="font-mono text-[10px] text-neon-red mb-2">
                ⚠ {strategiesError}
              </div>
              <button
                onClick={fetchStrategies}
                className="font-mono text-[9px] text-neon-cyan hover:text-neon-cyan/80"
              >
                ↻ RETRY
              </button>
            </div>
          )}

          {!strategiesLoading && !strategiesError && strategies.length > 0 && (
            <StrategySelector
              strategies={strategies}
              disabled={runLoading}
              onChange={handleConfigChange}
            />
          )}

          {/* Run button */}
          <button
            onClick={handleRun}
            disabled={runLoading || !configValid}
            className={`w-full font-mono text-xs font-bold py-3 rounded border transition-all ${
              runLoading
                ? "border-neon-cyan/40 text-neon-cyan/60 bg-neon-cyan/5 cursor-wait"
                : "border-neon-green/60 text-neon-green bg-neon-green/10 hover:bg-neon-green/20 hover:border-neon-green"
            } disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            {runLoading ? (
              <span className="animate-pulse">⟳ EXECUTING BENCHMARK…</span>
            ) : (
              "⟐ RUN BENCHMARK"
            )}
          </button>

          {/* Error display */}
          <AnimatePresence>
            {runError && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="p-3 rounded border border-neon-red/30 bg-neon-red/5"
              >
                <p className="font-mono text-[10px] text-neon-red">{runError}</p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Run history */}
          <RunHistory
            runs={runs}
            total={runsTotal}
            capacity={runsCapacity}
            loading={runsLoading}
            onSelect={handleSelectRun}
            onDelete={deleteRun}
            onRefresh={fetchRuns}
          />
        </div>

        {/* Right column: Results */}
        <div className="col-span-8 space-y-3">
          <AnimatePresence mode="wait">
            {lastResult ? (
              <motion.div
                key={lastResult.run_id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                <ComparisonPanel result={lastResult} />
              </motion.div>
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-3"
              >
                {/* Empty state hero */}
                <div className="panel h-48 flex items-center justify-center">
                  <div className="text-center">
                    <motion.div
                      className="text-neon-purple font-mono text-4xl font-bold mb-3 text-glow-purple"
                      animate={{ opacity: [0.3, 0.6, 0.3] }}
                      transition={{ duration: 4, repeat: Infinity }}
                    >
                      Ω
                    </motion.div>
                    <p className="font-mono text-[11px] text-text-dim">
                      Select a strategy and click{" "}
                      <span className="text-neon-green">RUN BENCHMARK</span> to
                      begin.
                    </p>
                    <p className="font-mono text-[9px] text-text-dim mt-1">
                      Strategy output is compared against{" "}
                      <span className="text-neon-cyan">secrets.token_bytes</span>{" "}
                      (CSPRNG) baseline with KS statistical test.
                    </p>
                  </div>
                </div>

                {/* Theory reference panel — surfaces handover §1-4 context */}
                <TheoryPanel />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

// ─── Theory Panel ──────────────────────────────────────────────────────

function TheoryPanel() {
  return (
    <div className="panel">
      <div className="panel-header text-neon-purple">⟐ Theory Reference</div>
      <div className="p-4 space-y-3">
        <TheorySection title="MECHANISM">
          The benchmark engine compares nonce-selection strategies against a
          cryptographically secure random baseline (CSPRNG). Each strategy
          processes a batch of N uint32 nonces and produces scored output.
          Statistical divergence is measured via the Kolmogorov-Smirnov test.
        </TheorySection>

        <TheorySection title="p-ADIC LADDER FILTER">
          Multi-prime modular filter scoring nonces by distance-to-mid-residue
          across (p, k) stages: p ∈ &#123;2,3,5,7&#125; for masking, p ∈
          &#123;11,13,17&#125; for scoring, plus a trigonometric entropy overlay
          weighted at 0.35. Top-K survivors selected via argpartition.
        </TheorySection>

        <TheorySection title="FAIRNESS CONSTRAINTS">
          Both strategy and baseline process identical batch sizes (N). The
          baseline uses <span className="text-neon-cyan">secrets.token_bytes</span>{" "}
          — no Math.random() or numpy.random in the measurement path.
          Wall-clock timing via <span className="text-neon-cyan">time.perf_counter</span>.
        </TheorySection>

        <TheorySection title="COMPLEXITY">
          O(N) for masking stages. O(K log K) for ranking phase.
          KS test subsampled at 100K to avoid O(N log N) sorting overhead on
          large batches.
        </TheorySection>

        <div className="border-t border-border-dim pt-2">
          <p className="font-mono text-[7px] text-text-dim leading-relaxed">
            Safety: This system is explicitly sandboxed as a benchmarking tool.
            It does not generate valid Bitcoin mainnet block hashes and does not
            submit shares to external mining pools.
          </p>
        </div>
      </div>
    </div>
  );
}

function TheorySection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="font-mono text-[8px] text-neon-purple tracking-widest mb-1">
        {title}
      </div>
      <p className="font-mono text-[9px] text-text-dim leading-relaxed">
        {children}
      </p>
    </div>
  );
}
