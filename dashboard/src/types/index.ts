// ─── ΩINTELLIGENCE™ Type Definitions ───

export interface EntropySnapshot {
  time: string;
  convergenceScore: number;
  griffinBasin: number;
  zetaAlignment: number;
  ganReplay: number;
  observerLadder: number;
  coneSize: number;
  deviation: number;
}

export interface GPUNode {
  id: number;
  name: string;
  temp: number | null;
  utilization: number | null;
  memUsed: number | null;
  memTotal: number | null;
  power: number | null;
  hashRate: number | null;
  status: "active" | "idle" | "unavailable";
}

export interface FPGANode {
  id: number;
  name: string;
  voltage: number | null;
  xrtStatus: "connected" | "disconnected" | "unavailable";
  dmaRate: number | null;
  hashRate: number | null;
  temp: number | null;
  status: "active" | "idle" | "unavailable";
}

export interface CPUInfo {
  model: string;
  cores: number;
  threads: number;
  load: number | null;
  temp: number | null;
  frequency: number | null;
}

export interface HardwareState {
  cpus: CPUInfo[];
  gpus: GPUNode[];
  fpgas: FPGANode[];
}

export interface WalletInfo {
  address: string | null;
  balance: number | null;
  pendingRewards: number | null;
  totalMined: number | null;
  lastPayout: string | null;
}

export interface ProfitMetrics {
  btcPrice: number | null;
  dailyRevenueBTC: number | null;
  dailyRevenueUSD: number | null;
  powerCostUSD: number | null;
  netProfitUSD: number | null;
  hashRate: number | null;
  networkDifficulty: number | null;
  networkShare: number | null;
}

export interface MiningStats {
  totalRounds: number;
  blocksFound: number;
  uptime: number;
  currentPhase: string;
  stratumConnected: boolean;
  lastBlockTime: string | null;
}

export interface TerminalLine {
  id: number;
  timestamp: string;
  tag: string;
  message: string;
  level: "info" | "success" | "warning" | "error";
}
