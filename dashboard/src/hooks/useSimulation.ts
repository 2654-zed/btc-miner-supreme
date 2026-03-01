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

// ─── Random helpers ───
const rand = (min: number, max: number) => Math.random() * (max - min) + min;
const randInt = (min: number, max: number) => Math.floor(rand(min, max));
const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

// ─── Generate entropy snapshot ───
function generateEntropy(prev?: EntropySnapshot): EntropySnapshot {
  const now = new Date();
  const base = prev?.convergenceScore ?? 0.72;
  return {
    time: now.toLocaleTimeString("en-US", { hour12: false }),
    convergenceScore: clamp(base + rand(-0.03, 0.035), 0.4, 0.98),
    griffinBasin: clamp(rand(0.55, 0.95), 0, 1),
    zetaAlignment: clamp(rand(0.6, 0.92), 0, 1),
    ganReplay: clamp(rand(0.45, 0.88), 0, 1),
    observerLadder: clamp(rand(0.5, 0.85), 0, 1),
    coneSize: randInt(800, 4200),
    deviation: clamp(rand(0.01, 0.15), 0, 1),
  };
}

// ─── Generate hardware state ───
function generateHardware(prev?: HardwareState): HardwareState {
  const gpuNames = ["H100-SXM5"];
  const gpus = Array.from({ length: 10 }, (_, i) => {
    const prevGpu = prev?.gpus[i];
    return {
      id: i,
      name: `${gpuNames[0]}:${i}`,
      temp: clamp((prevGpu?.temp ?? 65) + rand(-2, 2.5), 55, 88),
      utilization: clamp((prevGpu?.utilization ?? 95) + rand(-3, 3), 80, 100),
      memUsed: clamp((prevGpu?.memUsed ?? 72) + rand(-1, 1), 60, 80),
      memTotal: 80,
      power: clamp((prevGpu?.power ?? 650) + rand(-20, 20), 580, 700),
      hashRate: clamp((prevGpu?.hashRate ?? 245) + rand(-15, 15), 200, 290),
      status: Math.random() > 0.02 ? "active" as const : "idle" as const,
    };
  });

  const fpgas = Array.from({ length: 40 }, (_, i) => {
    const prevFpga = prev?.fpgas[i];
    return {
      id: i,
      name: `UL3524:${i}`,
      voltage: clamp((prevFpga?.voltage ?? 0.85) + rand(-0.01, 0.01), 0.78, 0.92),
      xrtStatus: Math.random() > 0.03 ? "connected" as const : "disconnected" as const,
      dmaRate: clamp((prevFpga?.dmaRate ?? 12.5) + rand(-0.5, 0.5), 10, 15),
      hashRate: clamp((prevFpga?.hashRate ?? 18) + rand(-2, 2), 12, 25),
      temp: clamp((prevFpga?.temp ?? 52) + rand(-1.5, 1.5), 42, 68),
      status: Math.random() > 0.03 ? "active" as const : "idle" as const,
    };
  });

  return {
    cpus: [
      {
        model: "Xeon 8593Q",
        cores: 64,
        threads: 128,
        load: clamp(rand(25, 55), 0, 100),
        temp: clamp(rand(58, 72), 40, 95),
        frequency: clamp(rand(2.2, 3.8), 1.8, 4.0),
      },
      {
        model: "Xeon 8593Q",
        cores: 64,
        threads: 128,
        load: clamp(rand(20, 50), 0, 100),
        temp: clamp(rand(55, 70), 40, 95),
        frequency: clamp(rand(2.2, 3.8), 1.8, 4.0),
      },
    ],
    gpus,
    fpgas,
  };
}

// ─── Terminal messages ───
const TAGS = ["Stratum", "Griffin", "Zeta", "GAN", "Observer", "Cone", "GPU", "FPGA", "Block", "Wallet"];
const MESSAGES: Record<string, string[]> = {
  Stratum: [
    "mining.notify received — new job #%JOBID%",
    "difficulty updated → 2^%DIFF%",
    "connection stable — latency %LAT%ms",
    "submitted share accepted ✓",
  ],
  Griffin: [
    "Phase 1/962 — basin depth %DEPTH% — φ-harmonic lock",
    "attractor basin converged at offset %OFF%",
    "entropy weave cycle complete — %N% candidates",
    "seed rotation — TrueRandom injection",
  ],
  Zeta: [
    "ζ(½+%T%i) zero alignment — projection active",
    "Gram-point extension to N=%N% zeros",
    "symbolic routing → %ROUTES% filtered paths",
    "non-trivial zero match — confidence %CONF%%",
  ],
  GAN: [
    "Generator loss: %GLOSS% | Discriminator: %DLOSS%",
    "replay buffer: %BUF% / 10000 historical nonces",
    "model checkpoint saved → epoch %EPOCH%",
    "inference batch — %N% synthetic candidates",
  ],
  Observer: [
    "Bayesian ladder depth %D% — convergence %CONV%%",
    "EMA weight update — α=%ALPHA%",
    "bin partition rotation — %BINS% active bins",
    "recursive scoring complete — top %N% selected",
  ],
  Cone: [
    "weighted_vote merge — %N% sources fused",
    "collapse cone → %SIZE% final candidates",
    "entropy quality score: %Q% / 1.000",
    "Phase Complete — dispatching to Layer 2",
  ],
  GPU: [
    "H100:%ID% — numba kernel launched — %BLOCKS% blocks",
    "SHA-256d batch — %RATE% MH/s sustained",
    "memory pool: %MEM%% utilized — no pressure",
    "thermal throttle check — within bounds",
  ],
  FPGA: [
    "UL3524:%ID% — XRT handshake OK — DMA %RATE% GB/s",
    "bitstream verified — hash pipeline active",
    "voltage regulator stable at %V%V",
    "bridge dispatch — %N% nonces queued",
  ],
  Block: [
    "★ BLOCK CANDIDATE FOUND — hash below target!",
    "block submitted via dual-path — awaiting confirmation",
    "merkle root recomputed — %TX% transactions",
    "getblocktemplate refreshed — height %HEIGHT%",
  ],
  Wallet: [
    "cold wallet sweep: %AMOUNT% BTC → %ADDR%",
    "fee estimation: %FEE% sat/vB (medium priority)",
    "audit log updated — %ENTRIES% entries",
    "balance check: %BAL% BTC confirmed",
  ],
};

function generateTerminalLine(id: number): TerminalLine {
  const tag = TAGS[randInt(0, TAGS.length)];
  const msgs = MESSAGES[tag];
  let msg = msgs[randInt(0, msgs.length)];

  // Replace placeholders
  msg = msg.replace("%JOBID%", randInt(100000, 999999).toString(16));
  msg = msg.replace("%DIFF%", randInt(72, 80).toString());
  msg = msg.replace("%LAT%", randInt(12, 85).toString());
  msg = msg.replace("%DEPTH%", rand(0.7, 0.99).toFixed(3));
  msg = msg.replace("%OFF%", randInt(0, 4294967295).toString(16).padStart(8, "0"));
  msg = msg.replace("%N%", randInt(500, 5000).toString());
  msg = msg.replace("%T%", rand(14, 50).toFixed(4));
  msg = msg.replace("%ROUTES%", randInt(50, 500).toString());
  msg = msg.replace("%CONF%", rand(85, 99).toFixed(1));
  msg = msg.replace("%GLOSS%", rand(0.001, 0.05).toFixed(4));
  msg = msg.replace("%DLOSS%", rand(0.3, 0.7).toFixed(4));
  msg = msg.replace("%BUF%", randInt(5000, 10000).toString());
  msg = msg.replace("%EPOCH%", randInt(100, 999).toString());
  msg = msg.replace("%D%", randInt(3, 8).toString());
  msg = msg.replace("%CONV%", rand(70, 98).toFixed(1));
  msg = msg.replace("%ALPHA%", rand(0.01, 0.1).toFixed(4));
  msg = msg.replace("%BINS%", randInt(16, 64).toString());
  msg = msg.replace("%SIZE%", randInt(800, 4200).toString());
  msg = msg.replace("%Q%", rand(0.7, 0.99).toFixed(3));
  msg = msg.replace("%ID%", randInt(0, 10).toString());
  msg = msg.replace("%BLOCKS%", randInt(256, 1024).toString());
  msg = msg.replace("%RATE%", rand(180, 290).toFixed(1));
  msg = msg.replace("%MEM%", rand(75, 95).toFixed(0));
  msg = msg.replace("%V%", rand(0.78, 0.92).toFixed(3));
  msg = msg.replace("%TX%", randInt(1500, 4500).toString());
  msg = msg.replace("%HEIGHT%", randInt(880000, 890000).toString());
  msg = msg.replace("%AMOUNT%", rand(0.01, 3.125).toFixed(6));
  msg = msg.replace("%ADDR%", "bc1q" + Array.from({ length: 38 }, () => "0123456789abcdef"[randInt(0, 16)]).join(""));
  msg = msg.replace("%FEE%", randInt(5, 45).toString());
  msg = msg.replace("%ENTRIES%", randInt(100, 9999).toString());
  msg = msg.replace("%BAL%", rand(0, 50).toFixed(6));

  let level: TerminalLine["level"] = "info";
  if (tag === "Block") level = "success";
  else if (msg.includes("error") || msg.includes("disconnect")) level = "error";
  else if (msg.includes("throttle") || msg.includes("pressure")) level = "warning";

  const now = new Date();
  return {
    id,
    timestamp: now.toLocaleTimeString("en-US", { hour12: false, fractionalSecondDigits: 3 } as Intl.DateTimeFormatOptions),
    tag,
    message: msg,
    level,
  };
}

// ─── Main simulation hook ───
export function useSimulation() {
  const lineCounter = useRef(0);
  const [entropy, setEntropy] = useState<EntropySnapshot[]>([]);
  const [hardware, setHardware] = useState<HardwareState | null>(null);
  const [profit, setProfit] = useState<ProfitMetrics>({
    btcPrice: 107500,
    dailyRevenueBTC: 0.00048,
    dailyRevenueUSD: 51.60,
    powerCostUSD: 18.40,
    netProfitUSD: 33.20,
    hashRate: 3.42,
    networkDifficulty: 119.12e12,
    networkShare: 0.0000028,
  });
  const [wallet] = useState<WalletInfo>({
    address: "bc1q8x7y9z0a1b2c3d4e5f6g7h8j9k0l1m2n3o4p5q6r",
    balance: 12.48291,
    pendingRewards: 0.00156,
    totalMined: 47.83621,
    lastPayout: "2025-01-14 03:22:18 UTC",
  });
  const [mining, setMining] = useState<MiningStats>({
    totalRounds: 0,
    blocksFound: 847,
    uptime: 2592000,
    currentPhase: "Layer 1 — Entropy Shaping",
    stratumConnected: true,
    lastBlockTime: "2025-01-14 02:57:41 UTC",
  });
  const [terminal, setTerminal] = useState<TerminalLine[]>([]);

  // Tick - entropy + mining stats (every 1.5s)
  useEffect(() => {
    const iv = setInterval(() => {
      setEntropy((prev) => {
        const snap = generateEntropy(prev[prev.length - 1]);
        const next = [...prev, snap];
        return next.length > 60 ? next.slice(-60) : next;
      });

      setMining((prev) => ({
        ...prev,
        totalRounds: prev.totalRounds + randInt(10, 50),
        currentPhase: [
          "Layer 1 — Entropy Shaping",
          "Layer 1 — GAN Replay",
          "Layer 1 — Cone Fusion",
          "Layer 2 — SHA-256d Dispatch",
          "Layer 2 — GPU Kernel",
          "Layer 2 — FPGA Bridge",
          "Layer 3 — Stratum Submit",
        ][randInt(0, 7)],
      }));

      setProfit((prev) => ({
        ...prev,
        btcPrice: clamp(prev.btcPrice + rand(-150, 160), 95000, 120000),
        hashRate: clamp(prev.hashRate + rand(-0.08, 0.08), 2.8, 4.2),
        dailyRevenueBTC: clamp(prev.dailyRevenueBTC + rand(-0.00005, 0.00006), 0.0002, 0.001),
        dailyRevenueUSD: clamp(prev.dailyRevenueUSD + rand(-2, 2.5), 20, 100),
        networkShare: clamp(prev.networkShare + rand(-0.0000002, 0.0000002), 0.000001, 0.00001),
      }));
    }, 1500);
    return () => clearInterval(iv);
  }, []);

  // Tick - hardware (every 2s)
  useEffect(() => {
    const iv = setInterval(() => {
      setHardware((prev) => generateHardware(prev ?? undefined));
    }, 2000);
    // Initial
    setHardware(generateHardware());
    return () => clearInterval(iv);
  }, []);

  // Tick - terminal lines (every 400ms)
  useEffect(() => {
    const iv = setInterval(() => {
      lineCounter.current += 1;
      const line = generateTerminalLine(lineCounter.current);
      setTerminal((prev) => {
        const next = [...prev, line];
        return next.length > 200 ? next.slice(-200) : next;
      });
    }, 400);
    return () => clearInterval(iv);
  }, []);

  return { entropy, hardware, profit, wallet, mining, terminal };
}
