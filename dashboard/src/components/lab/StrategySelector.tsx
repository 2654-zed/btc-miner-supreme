"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Strategy } from "@/types/lab";

// ─── Constants ─────────────────────────────────────────────────────────

const BATCH_PRESETS = [
  { label: "1K", value: 1_000 },
  { label: "10K", value: 10_000 },
  { label: "100K", value: 100_000 },
  { label: "1M", value: 1_000_000 },
  { label: "5M", value: 5_000_000 },
  { label: "50M", value: 50_000_000 },
];

// ─── Props ─────────────────────────────────────────────────────────────

export interface StrategyConfig {
  strategyId: string;
  formula: string;
  batchSize: number;
  timeoutSeconds: number;
  parameters: Record<string, string>;
}

interface StrategySelectorProps {
  strategies: Strategy[];
  disabled?: boolean;
  onChange: (config: StrategyConfig) => void;
}

// ─── Component ─────────────────────────────────────────────────────────

export default function StrategySelector({
  strategies,
  disabled = false,
  onChange,
}: StrategySelectorProps) {
  const [selectedId, setSelectedId] = useState<string>("");
  const [formula, setFormula] = useState("");
  const [batchSize, setBatchSize] = useState(1_000_000);
  const [timeoutSeconds, setTimeoutSeconds] = useState(30);
  const [paramValues, setParamValues] = useState<Record<string, string>>({});

  const selected = useMemo(
    () => strategies.find((s) => s.id === selectedId) ?? null,
    [strategies, selectedId],
  );

  const entropySources = useMemo(
    () => strategies.filter((s) => s.category === "entropy_source"),
    [strategies],
  );
  const mathFormulas = useMemo(
    () => strategies.filter((s) => s.category === "math_formula"),
    [strategies],
  );

  // Emit changes upward whenever anything changes
  const emitChange = (overrides: Partial<StrategyConfig> = {}) => {
    onChange({
      strategyId: overrides.strategyId ?? selectedId,
      formula: overrides.formula ?? formula,
      batchSize: overrides.batchSize ?? batchSize,
      timeoutSeconds: overrides.timeoutSeconds ?? timeoutSeconds,
      parameters: overrides.parameters ?? paramValues,
    });
  };

  const handleSelectStrategy = (id: string) => {
    setSelectedId(id);
    const strat = strategies.find((s) => s.id === id);
    // Reset params to defaults
    const defaults: Record<string, string> = {};
    for (const p of strat?.parameters ?? []) {
      defaults[p.name] = p.default_value;
    }
    setParamValues(defaults);
    emitChange({ strategyId: id, parameters: defaults });
  };

  const handleParamChange = (name: string, value: string) => {
    const next = { ...paramValues, [name]: value };
    setParamValues(next);
    emitChange({ parameters: next });
  };

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <span>⟐ Strategy Selector</span>
        <span className="text-[9px] text-text-dim">
          {strategies.length} AVAILABLE
        </span>
      </div>

      <div className="p-4 space-y-4">
        {/* ── Category: Entropy Sources ──────────────────────────────── */}
        {entropySources.length > 0 && (
          <div>
            <div className="font-mono text-[8px] text-neon-cyan tracking-widest mb-2">
              ENTROPY SOURCES
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {entropySources.map((s) => (
                <button
                  key={s.id}
                  disabled={disabled}
                  onClick={() => handleSelectStrategy(s.id)}
                  className={`text-left font-mono text-[9px] px-2.5 py-2 rounded border transition-all ${
                    selectedId === s.id
                      ? "border-neon-cyan text-neon-cyan bg-neon-cyan/10"
                      : "border-border-dim text-text-dim hover:border-neon-cyan/40 hover:text-neon-cyan/80"
                  } disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  <div className="font-semibold">{s.name}</div>
                  {s.parameters.length > 0 && (
                    <div className="text-[7px] text-text-dim mt-0.5">
                      {s.parameters.length} param{s.parameters.length > 1 ? "s" : ""}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Category: Math Formulas ────────────────────────────────── */}
        {mathFormulas.length > 0 && (
          <div>
            <div className="font-mono text-[8px] text-neon-green tracking-widest mb-2">
              MATH FORMULAS
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {mathFormulas.map((s) => (
                <button
                  key={s.id}
                  disabled={disabled}
                  onClick={() => handleSelectStrategy(s.id)}
                  className={`text-left font-mono text-[9px] px-2.5 py-2 rounded border transition-all ${
                    selectedId === s.id
                      ? "border-neon-green text-neon-green bg-neon-green/10"
                      : "border-border-dim text-text-dim hover:border-neon-green/40 hover:text-neon-green/80"
                  } disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  {s.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Strategy description ───────────────────────────────────── */}
        <AnimatePresence mode="wait">
          {selected && (
            <motion.div
              key={selected.id}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              className="p-2.5 rounded border border-border-dim bg-bg-primary"
            >
              <p className="font-mono text-[10px] text-text-dim leading-relaxed">
                {selected.description}
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Custom formula input (for custom_formula strategy) ──────── */}
        <AnimatePresence>
          {selectedId === "custom_formula" && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
            >
              <label className="font-mono text-[8px] text-text-dim tracking-widest block mb-1.5">
                CUSTOM FORMULA — f(nonce)
              </label>
              <input
                type="text"
                value={formula}
                disabled={disabled}
                onChange={(e) => {
                  setFormula(e.target.value);
                  emitChange({ formula: e.target.value });
                }}
                className="w-full p-2.5 bg-bg-primary border border-border-dim rounded font-mono text-sm text-neon-green focus:border-neon-green/50 focus:outline-none transition-colors disabled:opacity-40"
                placeholder="e.g., (nonce ** 1.618) + (1/962) % 0xFFFFFFFF"
                spellCheck={false}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Strategy-specific parameters ───────────────────────────── */}
        <AnimatePresence>
          {selected && selected.parameters.length > 0 && (
            <motion.div
              key={`${selected.id}-params`}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="space-y-2"
            >
              <div className="font-mono text-[8px] text-neon-purple tracking-widest">
                PARAMETERS
              </div>
              {selected.parameters.map((p) => (
                <div key={p.name} className="flex items-center gap-3">
                  <label className="font-mono text-[9px] text-text-dim w-36 shrink-0">
                    {p.name}
                  </label>
                  <input
                    type={p.type === "str" ? "text" : "number"}
                    value={paramValues[p.name] ?? p.default_value}
                    disabled={disabled}
                    step={p.type === "float" ? "any" : "1"}
                    min={p.min_value ?? undefined}
                    max={p.max_value ?? undefined}
                    onChange={(e) => handleParamChange(p.name, e.target.value)}
                    className="flex-1 p-1.5 bg-bg-primary border border-border-dim rounded font-mono text-[10px] text-neon-purple focus:border-neon-purple/50 focus:outline-none transition-colors disabled:opacity-40"
                  />
                  <span className="font-mono text-[7px] text-text-dim w-10 shrink-0">
                    {p.type}
                  </span>
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Batch size ─────────────────────────────────────────────── */}
        <div>
          <label className="font-mono text-[8px] text-text-dim tracking-widest block mb-1.5">
            BATCH SIZE
          </label>
          <div className="flex gap-1">
            {BATCH_PRESETS.map((bp) => (
              <button
                key={bp.value}
                disabled={disabled}
                onClick={() => {
                  setBatchSize(bp.value);
                  emitChange({ batchSize: bp.value });
                }}
                className={`font-mono text-[8px] px-2 py-1 rounded border flex-1 transition-colors ${
                  batchSize === bp.value
                    ? "border-neon-cyan text-neon-cyan bg-neon-cyan/10"
                    : "border-border-dim text-text-dim hover:border-neon-cyan/40"
                } disabled:opacity-40 disabled:cursor-not-allowed`}
              >
                {bp.label}
              </button>
            ))}
          </div>
        </div>

        {/* ── Timeout ────────────────────────────────────────────────── */}
        <div className="flex items-center gap-3">
          <label className="font-mono text-[8px] text-text-dim tracking-widest shrink-0">
            TIMEOUT (s)
          </label>
          <input
            type="range"
            min={5}
            max={120}
            step={5}
            value={timeoutSeconds}
            disabled={disabled}
            onChange={(e) => {
              const v = Number(e.target.value);
              setTimeoutSeconds(v);
              emitChange({ timeoutSeconds: v });
            }}
            className="flex-1 accent-neon-cyan"
          />
          <span className="font-mono text-[10px] text-neon-cyan w-8 text-right">
            {timeoutSeconds}s
          </span>
        </div>
      </div>
    </div>
  );
}
