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
  temp: number;
  utilization: number;
  memUsed: number;
  memTotal: number;
  power: number;
  hashRate: number;
  status: "active" | "idle" | "error";
}

export interface FPGANode {
  id: number;
  name: string;
  voltage: number;
  xrtStatus: "connected" | "disconnected" | "error";
  dmaRate: number;
  hashRate: number;
  temp: number;
  status: "active" | "idle" | "error";
}

export interface CPUInfo {
  model: string;
  cores: number;
  threads: number;
  load: number;
  temp: number;
  frequency: number;
}

export interface HardwareState {
  cpus: CPUInfo[];
  gpus: GPUNode[];
  fpgas: FPGANode[];
}

export interface WalletInfo {
  address: string;
  balance: number;
  pendingRewards: number;
  totalMined: number;
  lastPayout: string;
}

export interface ProfitMetrics {
  btcPrice: number;
  dailyRevenueBTC: number;
  dailyRevenueUSD: number;
  powerCostUSD: number;
  netProfitUSD: number;
  hashRate: number;
  networkDifficulty: number;
  networkShare: number;
}

export interface MiningStats {
  totalRounds: number;
  blocksFound: number;
  uptime: number;
  currentPhase: string;
  stratumConnected: boolean;
  lastBlockTime: string;
}

export interface TerminalLine {
  id: number;
  timestamp: string;
  tag: string;
  message: string;
  level: "info" | "success" | "warning" | "error";
}
