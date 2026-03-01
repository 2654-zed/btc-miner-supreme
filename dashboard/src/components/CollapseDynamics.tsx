"use client";

import { motion } from "framer-motion";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { EntropySnapshot } from "@/types";

interface CollapseDynamicsProps {
  data: EntropySnapshot[];
}

export default function CollapseDynamics({ data }: CollapseDynamicsProps) {
  const latest = data[data.length - 1];

  return (
    <div className="grid grid-cols-2 gap-3">
      {/* Convergence Score - Large Area Chart */}
      <div className="col-span-2 panel">
        <div className="panel-header flex items-center justify-between">
          <span>⟐ Entropy Convergence — Real-Time</span>
          {latest && (
            <motion.span
              key={latest.convergenceScore.toFixed(3)}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-neon-green text-xs"
            >
              SCORE: {latest.convergenceScore.toFixed(4)}
            </motion.span>
          )}
        </div>
        <div className="p-3 h-52">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs>
                <linearGradient id="convGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00ff66" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#00ff66" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1a3e" />
              <XAxis dataKey="time" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
              <YAxis domain={[0.3, 1]} tick={{ fontSize: 9 }} />
              <Tooltip
                contentStyle={{
                  background: "#0d0d1a",
                  border: "1px solid #1a1a3e",
                  borderRadius: 6,
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                }}
              />
              <Area
                type="monotone"
                dataKey="convergenceScore"
                stroke="#00ff66"
                strokeWidth={2}
                fill="url(#convGrad)"
                dot={false}
                animationDuration={300}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Griffin-962 Basins */}
      <div className="panel">
        <div className="panel-header">⟐ Griffin-962 Basin Depth</div>
        <div className="p-3 h-40">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.slice(-30)}>
              <defs>
                <linearGradient id="griffGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00d4ff" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#00d4ff" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1a3e" />
              <XAxis dataKey="time" tick={{ fontSize: 8 }} interval="preserveStartEnd" />
              <YAxis domain={[0, 1]} tick={{ fontSize: 8 }} />
              <Tooltip
                contentStyle={{
                  background: "#0d0d1a",
                  border: "1px solid #1a1a3e",
                  borderRadius: 6,
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                }}
              />
              <Area
                type="monotone"
                dataKey="griffinBasin"
                stroke="#00d4ff"
                strokeWidth={1.5}
                fill="url(#griffGrad)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Zeta-Line Alignment */}
      <div className="panel">
        <div className="panel-header">⟐ Zeta-Line Alignment</div>
        <div className="p-3 h-40">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.slice(-30)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1a3e" />
              <XAxis dataKey="time" tick={{ fontSize: 8 }} interval="preserveStartEnd" />
              <YAxis domain={[0, 1]} tick={{ fontSize: 8 }} />
              <Tooltip
                contentStyle={{
                  background: "#0d0d1a",
                  border: "1px solid #1a1a3e",
                  borderRadius: 6,
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                }}
              />
              <Line
                type="monotone"
                dataKey="zetaAlignment"
                stroke="#a855f7"
                strokeWidth={1.5}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Source Comparison - Multi-Line */}
      <div className="panel">
        <div className="panel-header">⟐ Source Comparison</div>
        <div className="p-3 h-40">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.slice(-30)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1a3e" />
              <XAxis dataKey="time" tick={{ fontSize: 8 }} interval="preserveStartEnd" />
              <YAxis domain={[0, 1]} tick={{ fontSize: 8 }} />
              <Tooltip
                contentStyle={{
                  background: "#0d0d1a",
                  border: "1px solid #1a1a3e",
                  borderRadius: 6,
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                }}
              />
              <Line type="monotone" dataKey="ganReplay" stroke="#ff4500" strokeWidth={1} dot={false} />
              <Line type="monotone" dataKey="observerLadder" stroke="#00d4ff" strokeWidth={1} dot={false} />
              <Line type="monotone" dataKey="griffinBasin" stroke="#00ff66" strokeWidth={1} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Collapse Cone Size - Bar Chart */}
      <div className="panel">
        <div className="panel-header flex items-center justify-between">
          <span>⟐ Collapse Cone</span>
          {latest && (
            <span className="text-neon-orange text-[10px]">
              SIZE: {latest.coneSize} | DEV: {latest.deviation.toFixed(4)}
            </span>
          )}
        </div>
        <div className="p-3 h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.slice(-20)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1a3e" />
              <XAxis dataKey="time" tick={{ fontSize: 8 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 8 }} />
              <Tooltip
                contentStyle={{
                  background: "#0d0d1a",
                  border: "1px solid #1a1a3e",
                  borderRadius: 6,
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                }}
              />
              <Bar dataKey="coneSize" fill="#ff4500" radius={[2, 2, 0, 0]} opacity={0.8} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
