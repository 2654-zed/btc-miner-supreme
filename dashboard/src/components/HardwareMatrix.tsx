"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import type { HardwareState, GPUNode, FPGANode, CPUInfo } from "@/types";

interface HardwareMatrixProps {
  hardware: HardwareState;
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "active" || status === "connected"
      ? "bg-neon-green"
      : status === "idle"
      ? "bg-yellow-500"
      : "bg-neon-red";
  return (
    <motion.div
      className={`w-1.5 h-1.5 rounded-full ${color}`}
      animate={status === "active" || status === "connected" ? { opacity: [1, 0.5, 1] } : {}}
      transition={{ duration: 2, repeat: Infinity }}
    />
  );
}

function TempBar({ temp, max = 95 }: { temp: number; max?: number }) {
  const pct = (temp / max) * 100;
  const color = temp > 80 ? "#ff4500" : temp > 70 ? "#ffaa00" : "#00ff66";
  return (
    <div className="w-full h-1.5 bg-bg-primary rounded-full overflow-hidden">
      <motion.div
        className="h-full rounded-full"
        style={{ background: color }}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.5 }}
      />
    </div>
  );
}

function UtilBar({ value, color = "#00ff66" }: { value: number; color?: string }) {
  return (
    <div className="w-full h-1 bg-bg-primary rounded-full overflow-hidden">
      <motion.div
        className="h-full rounded-full"
        style={{ background: color }}
        animate={{ width: `${value}%` }}
        transition={{ duration: 0.5 }}
      />
    </div>
  );
}

// ─── CPU Card ───
function CPUCard({ cpu, index }: { cpu: CPUInfo; index: number }) {
  return (
    <div className="panel p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <StatusDot status="active" />
          <span className="font-mono text-[10px] text-neon-cyan">CPU:{index}</span>
        </div>
        <span className="font-mono text-[9px] text-text-dim">{cpu.model}</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="font-mono text-[8px] text-text-dim">LOAD</div>
          <div className="font-mono text-xs text-neon-green">{cpu.load != null ? `${cpu.load.toFixed(0)}%` : 'N/A'}</div>
          <UtilBar value={cpu.load ?? 0} />
        </div>
        <div>
          <div className="font-mono text-[8px] text-text-dim">TEMP</div>
          <div className="font-mono text-xs text-neon-orange">{cpu.temp != null ? `${cpu.temp.toFixed(0)}°C` : 'N/A'}</div>
          <TempBar temp={cpu.temp ?? 0} />
        </div>
        <div>
          <div className="font-mono text-[8px] text-text-dim">FREQ</div>
          <div className="font-mono text-xs text-neon-cyan">{cpu.frequency != null ? `${cpu.frequency.toFixed(1)}GHz` : 'N/A'}</div>
        </div>
      </div>
      <div className="mt-1 font-mono text-[8px] text-text-dim text-center">
        {cpu.cores}C / {cpu.threads}T
      </div>
    </div>
  );
}

// ─── GPU Card ───
function GPUCard({ gpu }: { gpu: GPUNode }) {
  const [hovered, setHovered] = useState(false);

  return (
    <motion.div
      className="panel p-2 cursor-pointer"
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      whileHover={{ borderColor: "#00ff6660" }}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <StatusDot status={gpu.status} />
          <span className="font-mono text-[9px] text-neon-green">{gpu.name}</span>
        </div>
        <span className="font-mono text-[9px] text-text-dim">{gpu.hashRate != null ? `${gpu.hashRate.toFixed(0)} MH/s` : 'N/A'}</span>
      </div>

      <div className="grid grid-cols-4 gap-1 text-center">
        <div>
          <div className="font-mono text-[7px] text-text-dim">TEMP</div>
          <div className="font-mono text-[10px] text-neon-orange">{gpu.temp != null ? `${gpu.temp.toFixed(0)}°` : '-'}</div>
        </div>
        <div>
          <div className="font-mono text-[7px] text-text-dim">UTIL</div>
          <div className="font-mono text-[10px] text-neon-green">{gpu.utilization != null ? `${gpu.utilization.toFixed(0)}%` : '-'}</div>
        </div>
        <div>
          <div className="font-mono text-[7px] text-text-dim">MEM</div>
          <div className="font-mono text-[10px] text-neon-cyan">{gpu.memUsed != null ? `${gpu.memUsed.toFixed(0)}G` : '-'}</div>
        </div>
        <div>
          <div className="font-mono text-[7px] text-text-dim">PWR</div>
          <div className="font-mono text-[10px] text-neon-purple">{gpu.power != null ? `${gpu.power.toFixed(0)}W` : '-'}</div>
        </div>
      </div>

      <div className="mt-1">
        <UtilBar value={gpu.utilization ?? 0} />
      </div>

      {/* Hover detail */}
      {hovered && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="mt-2 pt-2 border-t border-border-dim"
        >
          <div className="font-mono text-[8px] text-text-dim space-y-0.5">
            <div>Numba CUDA: {gpu.status === 'active' ? 'active' : 'inactive'}</div>
            <div>VRAM: {gpu.memUsed != null ? gpu.memUsed.toFixed(1) : '?'} / {gpu.memTotal != null ? gpu.memTotal.toFixed(0) : '?'} GB</div>
            <div>Power draw: {gpu.power != null ? `${gpu.power.toFixed(0)} W` : 'N/A'}</div>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}

// ─── FPGA Mini Card ───
function FPGAMiniCard({ fpga }: { fpga: FPGANode }) {
  const [hovered, setHovered] = useState(false);
  const borderColor =
    fpga.xrtStatus === "connected" ? "#00ff6620" : "#ff450040";

  return (
    <motion.div
      className="panel p-1.5 cursor-pointer"
      style={{ borderColor }}
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      whileHover={{ borderColor: "#00d4ff60" }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <StatusDot status={fpga.xrtStatus} />
          <span className="font-mono text-[7px] text-text-dim">{fpga.name}</span>
        </div>
        <span className="font-mono text-[7px] text-neon-cyan">{fpga.hashRate != null ? fpga.hashRate.toFixed(0) : '-'}</span>
      </div>

      {hovered && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-1 font-mono text-[7px] text-text-dim space-y-0.5"
        >
          <div>XRT: {fpga.xrtStatus} | V: {fpga.voltage != null ? `${fpga.voltage.toFixed(3)}V` : 'N/A'}</div>
          <div>DMA: {fpga.dmaRate != null ? `${fpga.dmaRate.toFixed(1)} GB/s` : 'N/A'} | T: {fpga.temp != null ? `${fpga.temp.toFixed(0)}°C` : 'N/A'}</div>
        </motion.div>
      )}
    </motion.div>
  );
}

// ─── Main Component ───
export default function HardwareMatrix({ hardware }: HardwareMatrixProps) {
  const totalGpuHash = hardware.gpus.reduce((s, g) => s + (g.hashRate ?? 0), 0);
  const totalFpgaHash = hardware.fpgas.reduce((s, f) => s + (f.hashRate ?? 0), 0);
  const activeGpus = hardware.gpus.filter((g) => g.status === "active").length;
  const activeFpgas = hardware.fpgas.filter((f) => f.status === "active").length;
  const gpusWithTemp = hardware.gpus.filter((g) => g.temp != null);
  const avgGpuTemp = gpusWithTemp.length > 0
    ? gpusWithTemp.reduce((s, g) => s + (g.temp ?? 0), 0) / gpusWithTemp.length
    : null;

  return (
    <div className="space-y-3">
      {/* Summary bar */}
      <div className="panel p-3">
        <div className="panel-header !p-0 !pb-2 !border-b-0 flex items-center justify-between">
          <span>⟐ Hardware Orchestration Matrix</span>
        </div>
        <div className="grid grid-cols-5 gap-3 text-center mt-1">
          <SummaryItem label="GPU HASH" value={`${(totalGpuHash / 1000).toFixed(2)} GH/s`} color="text-neon-green" />
          <SummaryItem label="FPGA HASH" value={`${(totalFpgaHash).toFixed(0)} MH/s`} color="text-neon-cyan" />
          <SummaryItem label="GPU ACTIVE" value={`${activeGpus}/${hardware.gpus.length}`} color="text-neon-green" />
          <SummaryItem label="FPGA ACTIVE" value={`${activeFpgas}/${hardware.fpgas.length}`} color="text-neon-cyan" />
          <SummaryItem label="AVG GPU TEMP" value={avgGpuTemp != null ? `${avgGpuTemp.toFixed(1)}°C` : "N/A"} color="text-neon-orange" />
        </div>
      </div>

      {/* CPUs */}
      <div className="grid grid-cols-2 gap-2">
        {hardware.cpus.map((cpu, i) => (
          <CPUCard key={i} cpu={cpu} index={i} />
        ))}
      </div>

      {/* GPUs - 2x5 grid */}
      <div>
        <div className="font-mono text-[9px] text-text-dim tracking-widest mb-1.5 px-1">
          {hardware.gpus.length > 0 ? `${hardware.gpus[0].name.split(':')[0]} × ${hardware.gpus.length}` : 'NO GPUs DETECTED'}
        </div>
        <div className="grid grid-cols-2 gap-2">
          {hardware.gpus.map((gpu) => (
            <GPUCard key={gpu.id} gpu={gpu} />
          ))}
        </div>
      </div>

      {/* FPGAs - 8x5 grid */}
      <div>
        <div className="font-mono text-[9px] text-text-dim tracking-widest mb-1.5 px-1">
          {hardware.fpgas.length > 0 ? `${hardware.fpgas[0].name.split(':')[0]} × ${hardware.fpgas.length}` : 'NO FPGAs DETECTED'}
        </div>
        <div className="grid grid-cols-5 gap-1">
          {hardware.fpgas.map((fpga) => (
            <FPGAMiniCard key={fpga.id} fpga={fpga} />
          ))}
        </div>
      </div>
    </div>
  );
}

function SummaryItem({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <div className="font-mono text-[8px] text-text-dim tracking-wider">{label}</div>
      <div className={`font-mono text-sm font-bold ${color}`}>{value}</div>
    </div>
  );
}
