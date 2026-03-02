"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";

// ─── TypeScript contracts mirroring Pydantic schemas ───────────────────

interface InjectionRequest {
  formula: string;
  batch_size: number;
  target_hardware: "CPU" | "FPGA" | "GPU";
}

interface InjectionResponse {
  success: boolean;
  message: string;
  processed_count?: number;
  anomalies_detected?: number;
  elapsed_ms?: number;
  hardware_target?: string;
}

interface ValidationResponse {
  valid: boolean;
  error?: string | null;
}

// ─── Constants ─────────────────────────────────────────────────────────

const PRESET_FORMULAS = [
  { label: "Griffin-962 Attractor", formula: "(nonce ** 1.618) + (1/962) % 0xFFFFFFFF" },
  { label: "Zeta-Critical φ Bias", formula: "(nonce ** phi) % 0xFFFFFFFF" },
  { label: "Euler–Mascheroni Damp", formula: "nonce * gamma + (nonce ** 0.5)" },
  { label: "Harmonic Resonance", formula: "(nonce * pi / 962) % 0xFFFFFFFF" },
  { label: "Quadratic Residue", formula: "(nonce ** 2 + nonce + 41) % 0xFFFFFFFF" },
  { label: "XOR Cascade", formula: "nonce ^ (nonce >> 16) ^ (nonce >> 8)" },
];

const BATCH_PRESETS = [
  { label: "100K", value: 100_000 },
  { label: "1M", value: 1_000_000 },
  { label: "5M", value: 5_000_000 },
  { label: "10M", value: 10_000_000 },
  { label: "50M", value: 50_000_000 },
];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// ─── Component ─────────────────────────────────────────────────────────

export default function HeuristicInjector() {
  const [formula, setFormula] = useState("(nonce ** 1.618) + (1/962) % 0xFFFFFFFF");
  const [batchSize, setBatchSize] = useState(5_000_000);
  const [hardware, setHardware] = useState<"CPU" | "FPGA" | "GPU">("CPU");
  const [status, setStatus] = useState<string>("");
  const [statusType, setStatusType] = useState<"idle" | "loading" | "success" | "error" | "warning">("idle");
  const [isProcessing, setIsProcessing] = useState(false);
  const [anomalies, setAnomalies] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [validationState, setValidationState] = useState<"unchecked" | "valid" | "invalid">("unchecked");
  const [validationError, setValidationError] = useState<string>("");

  // ── Validate formula (AST dry-run) ───────────────────────────────────

  const validateFormula = useCallback(async () => {
    if (!formula.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/validate-formula`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ formula }),
      });
      const data: ValidationResponse = await res.json();
      if (data.valid) {
        setValidationState("valid");
        setValidationError("");
      } else {
        setValidationState("invalid");
        setValidationError(data.error || "Unknown validation error");
      }
    } catch {
      // API might not be running — skip validation
      setValidationState("unchecked");
    }
  }, [formula]);

  // ── Inject heuristic ─────────────────────────────────────────────────

  const handleInjection = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setIsProcessing(true);
    setStatus("Transmitting heuristic payload to orchestration engine…");
    setStatusType("loading");
    setAnomalies(null);
    setElapsedMs(null);

    const payload: InjectionRequest = {
      formula,
      batch_size: batchSize,
      target_hardware: hardware,
    };

    try {
      const response = await fetch(`${API_BASE}/api/v1/inject-heuristic`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok) {
        if (response.status === 403) {
          setStatus(`Security Violation Blocked: ${data.detail}`);
          setStatusType("error");
        } else if (response.status === 400) {
          setStatus(`Injection Rejected: ${data.detail}`);
          setStatusType("error");
        } else {
          setStatus(`Engine Error: ${data.detail || "Unknown failure"}`);
          setStatusType("error");
        }
        return;
      }

      const successData = data as InjectionResponse;
      setStatus(
        `${successData.message} — ${successData.processed_count?.toLocaleString()} nonces in ${successData.elapsed_ms?.toFixed(1)} ms`
      );
      setStatusType("success");
      setElapsedMs(successData.elapsed_ms ?? null);

      if (successData.anomalies_detected && successData.anomalies_detected > 0) {
        setAnomalies(successData.anomalies_detected);
      }
    } catch {
      setStatus("Network Error: Unable to reach orchestration engine. Ensure the API server is running on port 8000.");
      setStatusType("error");
    } finally {
      setIsProcessing(false);
    }
  }, [formula, batchSize, hardware]);

  // ── Render ───────────────────────────────────────────────────────────

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <span>⟐ Dynamic Heuristic Injector</span>
        <span className="text-[9px] text-text-dim">IoC STRATEGY PATTERN</span>
      </div>

      <div className="p-4 space-y-4">
        {/* Formula input */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="font-mono text-[9px] text-text-dim tracking-widest">
              MATHEMATICAL FORMULA — f(nonce)
            </label>
            {validationState === "valid" && (
              <span className="font-mono text-[9px] text-neon-green">✓ AST VALID</span>
            )}
            {validationState === "invalid" && (
              <span className="font-mono text-[9px] text-neon-red">✗ INVALID</span>
            )}
          </div>
          <input
            type="text"
            value={formula}
            onChange={(e) => {
              setFormula(e.target.value);
              setValidationState("unchecked");
            }}
            onBlur={validateFormula}
            className="w-full p-2.5 bg-bg-primary border border-border-dim rounded font-mono text-sm text-neon-green focus:border-neon-green/50 focus:outline-none transition-colors"
            placeholder="e.g., (nonce ** 1.618) + (1/962) % 0xFFFFFFFF"
            spellCheck={false}
          />
          {validationState === "invalid" && validationError && (
            <motion.p
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="font-mono text-[10px] text-neon-red mt-1"
            >
              {validationError}
            </motion.p>
          )}
        </div>

        {/* Preset formulas */}
        <div>
          <div className="font-mono text-[8px] text-text-dim tracking-widest mb-1.5">
            PRESETS
          </div>
          <div className="flex flex-wrap gap-1.5">
            {PRESET_FORMULAS.map((preset) => (
              <button
                key={preset.label}
                onClick={() => {
                  setFormula(preset.formula);
                  setValidationState("unchecked");
                }}
                className={`font-mono text-[8px] px-2 py-1 rounded border transition-colors ${
                  formula === preset.formula
                    ? "border-neon-green text-neon-green bg-neon-green/10"
                    : "border-border-dim text-text-dim hover:border-neon-green/40 hover:text-neon-green/80"
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        {/* Batch size + Hardware target */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="font-mono text-[8px] text-text-dim tracking-widest block mb-1.5">
              BATCH SIZE
            </label>
            <div className="flex gap-1">
              {BATCH_PRESETS.map((bp) => (
                <button
                  key={bp.value}
                  onClick={() => setBatchSize(bp.value)}
                  className={`font-mono text-[8px] px-2 py-1 rounded border flex-1 transition-colors ${
                    batchSize === bp.value
                      ? "border-neon-cyan text-neon-cyan bg-neon-cyan/10"
                      : "border-border-dim text-text-dim hover:border-neon-cyan/40"
                  }`}
                >
                  {bp.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="font-mono text-[8px] text-text-dim tracking-widest block mb-1.5">
              TARGET HARDWARE
            </label>
            <div className="flex gap-1">
              {(["CPU", "GPU", "FPGA"] as const).map((hw) => (
                <button
                  key={hw}
                  onClick={() => setHardware(hw)}
                  className={`font-mono text-[9px] px-3 py-1 rounded border flex-1 transition-colors ${
                    hardware === hw
                      ? hw === "CPU"
                        ? "border-neon-green text-neon-green bg-neon-green/10"
                        : "border-neon-orange text-neon-orange bg-neon-orange/10"
                      : "border-border-dim text-text-dim hover:border-border-glow"
                  }`}
                >
                  {hw}
                  {hw !== "CPU" && (
                    <span className="block text-[7px] text-text-dim">AOT ONLY</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Hardware warning */}
        <AnimatePresence>
          {hardware !== "CPU" && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="border border-neon-orange/30 bg-neon-orange/5 rounded p-2.5"
            >
              <p className="font-mono text-[10px] text-neon-orange">
                ⚠ Dynamic string injection is fundamentally incompatible with{" "}
                {hardware} AOT architecture. Formula will be blocked at the API layer.
                Switch to CPU Sandbox for dynamic execution.
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Submit button */}
        <button
          onClick={handleInjection}
          disabled={isProcessing || !formula.trim()}
          className={`w-full font-mono text-xs font-bold py-2.5 rounded border transition-all ${
            isProcessing
              ? "border-neon-cyan/40 text-neon-cyan/60 bg-neon-cyan/5 cursor-wait"
              : "border-neon-green/60 text-neon-green bg-neon-green/10 hover:bg-neon-green/20 hover:border-neon-green"
          } disabled:opacity-40 disabled:cursor-not-allowed`}
        >
          {isProcessing ? (
            <span className="animate-pulse">⟳ COMPILING & INJECTING…</span>
          ) : (
            "⟐ INJECT HEURISTIC"
          )}
        </button>

        {/* Status display */}
        <AnimatePresence>
          {status && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={`p-3 rounded border font-mono text-[11px] ${
                statusType === "success"
                  ? "bg-neon-green/5 border-neon-green/30 text-neon-green"
                  : statusType === "error"
                  ? "bg-neon-red/5 border-neon-red/30 text-neon-red"
                  : statusType === "loading"
                  ? "bg-neon-cyan/5 border-neon-cyan/30 text-neon-cyan animate-pulse"
                  : "bg-bg-card border-border-dim text-text-dim"
              }`}
            >
              <p>{status}</p>
              {elapsedMs !== null && statusType === "success" && (
                <p className="text-text-dim text-[9px] mt-1">
                  Throughput: ~{((batchSize / (elapsedMs / 1000)) / 1e6).toFixed(1)}M nonces/sec
                </p>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Anomaly warning */}
        <AnimatePresence>
          {anomalies !== null && anomalies > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="p-2.5 rounded border border-neon-orange/30 bg-neon-orange/5"
            >
              <p className="font-mono text-[10px] text-neon-orange">
                ⚠ {anomalies.toLocaleString()} mathematical anomalies (NaN/Inf)
                detected during execution. Check formula for division by zero
                or logical impossibilities.
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Architecture note */}
        <div className="border-t border-border-dim pt-3 mt-2">
          <p className="font-mono text-[8px] text-text-dim leading-relaxed">
            Security: Pydantic regex → AST whitelist traversal → NumExpr GIL-bypass execution.
            No eval() or exec() in the critical path. Dynamic formulas restricted to CPU sandbox;
            GPU/FPGA reserved for AOT-compiled SHA-256d workloads.
          </p>
        </div>
      </div>
    </div>
  );
}
