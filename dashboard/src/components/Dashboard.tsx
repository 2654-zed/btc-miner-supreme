"use client";

import { useSimulation } from "@/hooks/useSimulation";
import Header from "@/components/Header";
import CollapseDynamics from "@/components/CollapseDynamics";
import HardwareMatrix from "@/components/HardwareMatrix";
import ProfitabilityWallet from "@/components/ProfitabilityWallet";
import LiveTerminal from "@/components/LiveTerminal";
import HeuristicInjector from "@/components/HeuristicInjector";

export default function Dashboard() {
  const { entropy, hardware, profit, wallet, mining, terminal, connectionLost } = useSimulation();

  if (!hardware) {
    return (
      <div className="min-h-screen bg-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="text-neon-green font-mono text-2xl font-bold text-glow-green animate-pulse-glow">
            Ω
          </div>
          <div className="font-mono text-xs text-text-dim mt-2 tracking-widest">
            CONNECTING TO ORCHESTRATOR...
          </div>
        </div>
      </div>
    );
  }

  // Default mining/profit for Header when data hasn&#39;t arrived yet
  const headerMining = mining ?? {
    totalRounds: 0,
    blocksFound: 0,
    uptime: 0,
    currentPhase: "Awaiting Telemetry",
    stratumConnected: false,
    lastBlockTime: "N/A",
  };
  const headerProfit = profit ?? {
    btcPrice: 0,
    dailyRevenueBTC: 0,
    dailyRevenueUSD: 0,
    powerCostUSD: 0,
    netProfitUSD: 0,
    hashRate: 0,
    networkDifficulty: 0,
    networkShare: 0,
  };

  return (
    <div className="min-h-screen bg-bg-primary grid-bg">
      {/* Connection Lost Banner */}
      {connectionLost && (
        <div className="bg-red-900/80 border-b border-red-500 px-4 py-2 text-center">
          <span className="font-mono text-xs text-red-300 tracking-widest">
            ⚠ CONNECTION TO ORCHESTRATOR LOST — retrying every 2s...
          </span>
        </div>
      )}

      {/* Header */}
      <Header mining={headerMining} profit={headerProfit} />

      {/* Main Grid Layout */}
      <div className="grid grid-cols-12 gap-3 p-3 h-[calc(100vh-60px)]">
        {/* Left Column - Hardware Matrix (scrollable) */}
        <div className="col-span-3 overflow-y-auto pr-1 space-y-3">
          <HardwareMatrix hardware={hardware} />
        </div>

        {/* Center Column - Collapse Dynamics + Terminal */}
        <div className="col-span-6 flex flex-col gap-3 overflow-hidden">
          <div className="flex-shrink-0 overflow-y-auto">
            <CollapseDynamics data={entropy} />
          </div>
          <div className="flex-1 min-h-0">
            <LiveTerminal lines={terminal} />
          </div>
        </div>

        {/* Right Column - Profitability, Wallet & Heuristic Injector */}
        <div className="col-span-3 overflow-y-auto pl-1 space-y-3">
          <ProfitabilityWallet profit={profit} wallet={wallet} />
          <HeuristicInjector />
        </div>
      </div>
    </div>
  );
}
