"use client";

import { useSimulation } from "@/hooks/useSimulation";
import Header from "@/components/Header";
import CollapseDynamics from "@/components/CollapseDynamics";
import HardwareMatrix from "@/components/HardwareMatrix";
import ProfitabilityWallet from "@/components/ProfitabilityWallet";
import LiveTerminal from "@/components/LiveTerminal";

export default function Dashboard() {
  const { entropy, hardware, profit, wallet, mining, terminal } = useSimulation();

  if (!hardware) {
    return (
      <div className="min-h-screen bg-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="text-neon-green font-mono text-2xl font-bold text-glow-green animate-pulse-glow">
            Ω
          </div>
          <div className="font-mono text-xs text-text-dim mt-2 tracking-widest">
            INITIALIZING SUPREMACY CORE...
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-primary grid-bg">
      {/* Header */}
      <Header mining={mining} profit={profit} />

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

        {/* Right Column - Profitability & Wallet */}
        <div className="col-span-3 overflow-y-auto pl-1">
          <ProfitabilityWallet profit={profit} wallet={wallet} />
        </div>
      </div>
    </div>
  );
}
