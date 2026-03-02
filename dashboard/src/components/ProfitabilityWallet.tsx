"use client";

import { motion } from "framer-motion";
import type { ProfitMetrics, WalletInfo } from "@/types";

interface ProfitabilityWalletProps {
  profit: ProfitMetrics | null;
  wallet: WalletInfo | null;
}

// ─── Skeleton / Loading State ───
function TelemetrySkeleton() {
  return (
    <div className="panel">
      <div className="panel-header">⟐ Initializing Telemetry...</div>
      <div className="p-6 flex flex-col items-center gap-4">
        <div className="w-36 h-[72px] bg-bg-primary rounded animate-pulse" />
        <div className="grid grid-cols-2 gap-3 w-full">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-4 bg-bg-primary rounded animate-pulse" />
          ))}
        </div>
        <div className="w-full h-12 bg-bg-primary rounded animate-pulse mt-2" />
      </div>
    </div>
  );
}

// ─── Gauge Arc ───
function ProfitGauge({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = Math.min(value / max, 1);
  const angle = pct * 180;
  const isHigh = value > max * 0.6;

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-36 h-[72px] overflow-hidden">
        {/* Background arc */}
        <svg viewBox="0 0 140 72" className="absolute inset-0 w-full h-full">
          <path
            d="M 10 70 A 60 60 0 0 1 130 70"
            fill="none"
            stroke="#1a1a3e"
            strokeWidth="8"
            strokeLinecap="round"
          />
          <motion.path
            d="M 10 70 A 60 60 0 0 1 130 70"
            fill="none"
            stroke={isHigh ? "#00ff66" : "#ff4500"}
            strokeWidth="8"
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: pct }}
            transition={{ duration: 1, ease: "easeOut" }}
          />
        </svg>
        {/* Center value */}
        <div className="absolute inset-0 flex items-end justify-center pb-0">
          <motion.span
            key={value.toFixed(0)}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            className={`font-mono text-xl font-bold ${isHigh ? "text-neon-green text-glow-green" : "text-neon-orange"}`}
          >
            ${value.toFixed(0)}
          </motion.span>
        </div>
      </div>
      <span className="font-mono text-[9px] text-text-dim tracking-widest mt-1">{label}</span>
    </div>
  );
}

function obfuscateAddress(addr: string | null): string {
  if (!addr) return "NOT CONFIGURED";
  if (addr.length < 12) return addr;
  return addr.slice(0, 8) + "••••••" + addr.slice(-6);
}

function fmtNullable(v: number | null, fmt: (n: number) => string, fallback = "N/A"): string {
  return v != null ? fmt(v) : fallback;
}

export default function ProfitabilityWallet({ profit, wallet }: ProfitabilityWalletProps) {
  // Graceful loading state while awaiting first network fetch
  if (!profit || !wallet) {
    return <TelemetrySkeleton />;
  }

  const btcPrice = profit.btcPrice ?? 0;

  return (
    <div className="space-y-3">
      {/* Profit Gauge */}
      <div className="panel">
        <div className="panel-header">⟐ Profitability Engine</div>
        <div className="p-4 flex flex-col items-center">
          <ProfitGauge value={profit.netProfitUSD ?? 0} max={100} label="NET USD / DAY" />

          <div className="grid grid-cols-2 gap-x-6 gap-y-2 mt-4 w-full">
            <MetricRow label="BTC Price" value={fmtNullable(profit.btcPrice, v => `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`)} color="text-neon-green" />
            <MetricRow label="Revenue BTC" value={fmtNullable(profit.dailyRevenueBTC, v => v.toFixed(6))} color="text-neon-cyan" />
            <MetricRow label="Revenue USD" value={fmtNullable(profit.dailyRevenueUSD, v => `$${v.toFixed(2)}`)} color="text-neon-green" />
            <MetricRow label="Power Cost" value={fmtNullable(profit.powerCostUSD, v => `$${v.toFixed(2)}`)} color="text-neon-orange" />
            <MetricRow label="Hash Rate" value={fmtNullable(profit.hashRate, v => `${v.toFixed(2)} EH/s`)} color="text-neon-cyan" />
            <MetricRow label="Net Share" value={fmtNullable(profit.networkShare, v => `${(v * 100).toFixed(5)}%`)} color="text-text-dim" />
          </div>

          {/* BTC Price Ticker */}
          <div className="mt-4 w-full border-t border-border-dim pt-3">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[9px] text-text-dim tracking-widest">BTC/USD</span>
              <motion.span
                key={btcPrice.toFixed(0)}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="font-mono text-lg font-bold text-neon-green text-glow-green"
              >
                {profit.btcPrice != null ? `$${profit.btcPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "AWAITING FEED"}
              </motion.span>
            </div>
          </div>
        </div>
      </div>

      {/* Wallet */}
      <div className="panel">
        <div className="panel-header">⟐ Cold Wallet</div>
        <div className="p-4 space-y-3">
          {/* Address */}
          <div>
            <div className="font-mono text-[8px] text-text-dim tracking-widest mb-1">ADDRESS</div>
            <div className="font-mono text-xs text-neon-cyan bg-bg-primary rounded px-2 py-1.5 border border-border-dim">
              {obfuscateAddress(wallet.address)}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <WalletStat
              label="BALANCE"
              value={fmtNullable(wallet.balance, v => `${v.toFixed(5)} BTC`)}
              usd={wallet.balance != null ? `$${(wallet.balance * btcPrice).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : undefined}
              color="text-neon-green"
            />
            <WalletStat
              label="PENDING"
              value={fmtNullable(wallet.pendingRewards, v => `${v.toFixed(5)} BTC`)}
              usd={wallet.pendingRewards != null ? `$${(wallet.pendingRewards * btcPrice).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : undefined}
              color="text-neon-orange"
            />
            <WalletStat
              label="TOTAL MINED"
              value={fmtNullable(wallet.totalMined, v => `${v.toFixed(5)} BTC`)}
              usd={wallet.totalMined != null ? `$${(wallet.totalMined * btcPrice).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : undefined}
              color="text-neon-cyan"
            />
            <WalletStat
              label="LAST PAYOUT"
              value={wallet.lastPayout ?? "N/A"}
              color="text-text-dim"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex justify-between items-center">
      <span className="font-mono text-[9px] text-text-dim">{label}</span>
      <span className={`font-mono text-xs font-bold ${color}`}>{value}</span>
    </div>
  );
}

function WalletStat({
  label,
  value,
  usd,
  color,
}: {
  label: string;
  value: string;
  usd?: string;
  color: string;
}) {
  return (
    <div className="bg-bg-primary rounded p-2 border border-border-dim">
      <div className="font-mono text-[7px] text-text-dim tracking-widest">{label}</div>
      <div className={`font-mono text-xs font-bold ${color} mt-0.5`}>{value}</div>
      {usd && <div className="font-mono text-[9px] text-text-dim mt-0.5">{usd}</div>}
    </div>
  );
}
