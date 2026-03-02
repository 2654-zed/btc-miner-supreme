"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type {
  EntropySnapshot,
  HardwareState,
  ProfitMetrics,
  WalletInfo,
  MiningStats,
  TerminalLine,
} from "@/types";

// ─── API Configuration ───
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const STATUS_URL = `${API_BASE}/api/v1/status`;
const POLL_INTERVAL_MS = 2000;

/**
 * Backend telemetry payload — mirrors ``FullStatusResponse`` from the
 * Python FastAPI backend.  Parsed from ``GET /api/v1/status``.
 */
interface StatusPayload {
  entropy: EntropySnapshot[];
  hardware: HardwareState;
  profit: ProfitMetrics;
  wallet: WalletInfo;
  mining: MiningStats;
  terminal: TerminalLine[];
}

// ─── Main data hook (network-sourced) ───
export function useTelemetry() {
  const [entropy, setEntropy] = useState<EntropySnapshot[]>([]);
  const [hardware, setHardware] = useState<HardwareState | null>(null);
  const [profit, setProfit] = useState<ProfitMetrics | null>(null);
  const [wallet, setWallet] = useState<WalletInfo | null>(null);
  const [mining, setMining] = useState<MiningStats | null>(null);
  const [terminal, setTerminal] = useState<TerminalLine[]>([]);
  const [connectionLost, setConnectionLost] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const res = await fetch(STATUS_URL, {
        signal: controller.signal,
        headers: { Accept: "application/json" },
      });

      if (!res.ok) {
        throw new Error(`Backend returned ${res.status}`);
      }

      const data: StatusPayload = await res.json();

      // Merge entropy history (append new snapshots, cap at 60)
      setEntropy((prev) => {
        if (data.entropy.length === 0) return prev;
        const merged = [...prev, ...data.entropy];
        return merged.length > 60 ? merged.slice(-60) : merged;
      });

      setHardware(data.hardware);
      setProfit(data.profit);
      setWallet(data.wallet);
      setMining(data.mining);

      // Append terminal lines (avoid duplicates by id, cap at 200)
      setTerminal((prev) => {
        const existingIds = new Set(prev.map((l) => l.id));
        const newLines = data.terminal.filter((l) => !existingIds.has(l.id));
        if (newLines.length === 0) return prev;
        const merged = [...prev, ...newLines];
        return merged.length > 200 ? merged.slice(-200) : merged;
      });

      setConnectionLost(false);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("[useTelemetry] Connection to Orchestrator lost");
      setConnectionLost(true);
    }
  }, []);

  // Poll loop
  useEffect(() => {
    // Initial fetch
    fetchStatus();
    const iv = setInterval(fetchStatus, POLL_INTERVAL_MS);
    return () => {
      clearInterval(iv);
      abortRef.current?.abort();
    };
  }, [fetchStatus]);

  return { entropy, hardware, profit, wallet, mining, terminal, connectionLost };
}
