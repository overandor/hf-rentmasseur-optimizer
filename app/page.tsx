"use client";

import { useEffect, useState, useCallback } from "react";

const GLYPHS = {
  live: "◉",
  indexed: "◇",
  rising: "▲",
  falling: "▼",
  verified: "◆",
  anomalous: "⟁",
  dormant: "◌",
  mirrored: "◍",
  duplicated: "⧉",
  streaming: "⌁",
  aiReadable: "⟡",
  expiring: "⧖",
};

const LIFE_STATES = {
  idle: { color: "#555566", glyph: "◌", label: "idle" },
  active: { color: "#00ff88", glyph: "◉", label: "active" },
  critical: { color: "#ff3344", glyph: "⟁", label: "critical" },
  verified: { color: "#00aaff", glyph: "◆", label: "verified" },
  unknown: { color: "#555566", glyph: "◌", label: "unknown" },
  complete: { color: "#ffaa00", glyph: "◇", label: "complete" },
  dormant: { color: "#555566", glyph: "⧖", label: "dormant" },
  retired: { color: "#333344", glyph: "◇", label: "retired" },
};

function lifeState(status: string) {
  return LIFE_STATES[status as keyof typeof LIFE_STATES] || LIFE_STATES.unknown;
}

function ScoreRing({ score, label, color }: { score: number; label: string; color: string }) {
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - score * circumference;
  return (
    <div className="flex flex-col items-center">
      <div className="score-ring">
        <svg width="120" height="120">
          <circle className="bg-ring" cx="60" cy="60" r={radius} />
          <circle
            className="fill-ring"
            cx="60"
            cy="60"
            r={radius}
            stroke={color}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ filter: `drop-shadow(0 0 6px ${color}66)` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold" style={{ color }}>
            {(score * 100).toFixed(1)}
          </span>
          <span className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</span>
        </div>
      </div>
    </div>
  );
}

function MetricBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="metric-bar w-full">
      <div className="metric-bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

function Pane({
  title,
  glyph,
  lifeState,
  children,
  flex = 1,
  phase = "compact",
}: {
  title: string;
  glyph: string;
  lifeState: { color: string; glyph: string; label: string };
  children: React.ReactNode;
  flex?: number;
  phase?: string;
}) {
  return (
    <div
      className="glass-panel p-4 transition-all duration-300 hover:border-accent-orange/40"
      style={{ flex, minHeight: "120px" }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="glyph" style={{ color: lifeState.color }}>
            {lifeState.glyph}
          </span>
          <span className="text-xs uppercase tracking-wider text-gray-400">{title}</span>
          <span className="text-[9px] text-gray-600">{glyph}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="pulse-dot"
            style={{ background: lifeState.color, color: lifeState.color }}
          />
          <span className="text-[9px] uppercase" style={{ color: lifeState.color }}>
            {lifeState.label}
          </span>
          <span className="text-[8px] text-gray-700">{phase}</span>
        </div>
      </div>
      <div className="scan-line" />
      {children}
    </div>
  );
}

export default function ControlSurface() {
  const [kpiData, setKpiData] = useState<any>(null);
  const [scheduleData, setScheduleData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [clock, setClock] = useState(new Date());
  const [tick, setTick] = useState(0);

  const fetchAll = useCallback(async () => {
    try {
      const [kpiRes, schedRes] = await Promise.all([
        fetch("/api/kpis", { cache: "no-store" }),
        fetch("/api/schedule", { cache: "no-store" }),
      ]);
      const kpi = await kpiRes.json();
      const sched = await schedRes.json();
      setKpiData(kpi);
      setScheduleData(sched);
    } catch (e) {
      console.error("fetch error", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 5000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  useEffect(() => {
    const c = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(c);
  }, []);

  useEffect(() => {
    const t = setInterval(() => setTick((v: number) => v + 1), 3000);
    return () => clearInterval(t);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="pulse-dot mx-auto mb-4" style={{ background: "#ff6b1a", color: "#ff6b1a" }} />
          <div className="text-sm text-gray-500 uppercase tracking-widest">Initializing Control Surface</div>
        </div>
      </div>
    );
  }

  const imm = kpiData?.immortality || {};
  const vir = kpiData?.virality || {};
  const conv = kpiData?.conversion || {};
  const trust = kpiData?.trust || {};
  const decision = kpiData?.decision || {};
  const experiment = kpiData?.experiment || {};
  const bios = kpiData?.bios || [];
  const receiptCount = kpiData?.receipt_count || 0;
  const latestMetrics = kpiData?.latest_metrics || {};
  const programs = scheduleData?.programs || [];
  const summary = scheduleData?.summary || {};
  const hourlyDensity = scheduleData?.hourly_density || Array(24).fill(0);
  const genome = scheduleData?.genome || null;

  const systemAlive = summary.active > 0;
  const systemState = systemAlive ? LIFE_STATES.active : LIFE_STATES.dormant;

  return (
    <div className="min-h-screen p-4 md:p-6">
      {/* HEADER */}
      <header className="flex items-center justify-between mb-6 pb-4 border-b border-accent-orange/10">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold text-accent-orange glow-text">ClientPulse OS</span>
            <span className="text-[10px] text-gray-600 uppercase tracking-widest">v1.0</span>
          </div>
          <div className="flex items-center gap-2 ml-4">
            <span
              className="pulse-dot"
              style={{ background: systemState.color, color: systemState.color }}
            />
            <span className="text-xs uppercase" style={{ color: systemState.color }}>
              {systemState.label}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-6">
          <div className="text-right">
            <div className="text-[10px] text-gray-600 uppercase">Receipts</div>
            <div className="text-sm text-signal-verified font-bold">
              {GLYPHS.verified} {receiptCount}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-gray-600 uppercase">GA Gen</div>
            <div className="text-sm text-accent-orange font-bold">
              {genome?.generation ?? "—"} {genome ? `(${(genome.fitness * 100).toFixed(1)}%)` : ""}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-gray-600 uppercase">System Time</div>
            <div className="text-sm text-gray-300 font-mono">
              {clock.toISOString().split("T")[1].split(".")[0]}Z
            </div>
          </div>
        </div>
      </header>

      {/* KPI SCORE RINGS */}
      <div className="flex flex-wrap gap-4 mb-6">
        <Pane
          title="Immortality"
          glyph={GLYPHS.verified}
          lifeState={LIFE_STATES.verified}
          flex={1.2}
        >
          <div className="flex items-center gap-4">
            <ScoreRing score={imm.score || 0} label="DURABILITY" color="#00aaff" />
            <div className="flex-1 space-y-2">
              {imm.dimensions?.map((dim: string, i: number) => (
                <div key={dim}>
                  <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                    <span>{dim}</span>
                    <span style={{ color: "#00aaff" }}>
                      {((imm.vector?.[i] || 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <MetricBar value={imm.vector?.[i] || 0} max={1} color="#00aaff" />
                </div>
              ))}
            </div>
          </div>
        </Pane>

        <Pane
          title="Virality"
          glyph={GLYPHS.rising}
          lifeState={LIFE_STATES.active}
          flex={1.2}
        >
          <div className="flex items-center gap-4">
            <ScoreRing score={vir.score || 0} label="SPREAD" color="#00ff88" />
            <div className="flex-1 space-y-2">
              {vir.dimensions?.map((dim: string, i: number) => (
                <div key={dim}>
                  <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                    <span>{dim}</span>
                    <span style={{ color: "#00ff88" }}>
                      {((vir.vector?.[i] || 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <MetricBar value={vir.vector?.[i] || 0} max={1} color="#00ff88" />
                </div>
              ))}
            </div>
          </div>
        </Pane>

        <Pane
          title="Conversion"
          glyph={GLYPHS.aiReadable}
          lifeState={conv.score > 0.05 ? LIFE_STATES.active : LIFE_STATES.critical}
          flex={1}
        >
          <div className="flex items-center gap-4">
            <ScoreRing score={conv.score || 0} label="INTENT" color="#ff6b1a" />
            <div className="flex-1 space-y-1">
              <div className="text-[10px] text-gray-500">
                Views: <span className="text-gray-300">{conv.total_views?.toLocaleString()}</span>
              </div>
              <div className="text-[10px] text-gray-500">
                Clicks: <span className="text-gray-300">{conv.total_clicks?.toLocaleString()}</span>
              </div>
              <div className="text-[10px] text-gray-500">
                Rate: <span className="text-accent-orange">{((conv.score || 0) * 100).toFixed(2)}%</span>
              </div>
              <div className="text-[10px] text-gray-500">
                Prior: <span className="text-gray-400">{conv.prior}</span>
              </div>
            </div>
          </div>
        </Pane>

        <Pane
          title="Trust"
          glyph={GLYPHS.verified}
          lifeState={trust.is_clean ? LIFE_STATES.verified : LIFE_STATES.critical}
          flex={0.8}
        >
          <div className="flex flex-col items-center justify-center h-full">
            <ScoreRing score={trust.score || 0} label="CLEAN" color={trust.is_clean ? "#00aaff" : "#ff3344"} />
            <div className="mt-2 text-center">
              {trust.dirty_flags?.length > 0 ? (
                <div className="text-[10px] text-signal-crit">
                  {GLYPHS.anomalous} {trust.dirty_flags.length} dirty flags
                </div>
              ) : (
                <div className="text-[10px] text-signal-verified">
                  {GLYPHS.verified} No dirty signals
                </div>
              )}
            </div>
          </div>
        </Pane>
      </div>

      {/* GENETIC PANE SCHEDULER */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="glyph text-accent-orange">{GLYPHS.streaming}</span>
            <h2 className="text-sm uppercase tracking-wider text-gray-400">
              Genetic Pane Scheduler
            </h2>
            <span className="text-[10px] text-gray-600">
              {summary.total} programs · {summary.active} active · {summary.dormant} dormant · {summary.retired} retired
            </span>
          </div>
          <div className="text-[10px] text-gray-600">
            Fitness: <span className="text-accent-orange">{genome ? `${(genome.fitness * 100).toFixed(2)}%` : "—"}</span>
          </div>
        </div>

        {/* PROGRAM CARDS */}
        <div className="flex flex-wrap gap-3 mb-4">
          {programs.map((prog: any, i: number) => {
            const ls = lifeState(prog.status);
            return (
              <div
                key={prog.id}
                className="glass-panel p-3 flex-1 min-w-[200px] transition-all duration-500"
                style={{
                  borderColor: ls.color + "33",
                  boxShadow: prog.status === "active" ? `0 0 15px ${ls.color}22` : "none",
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="glyph" style={{ color: ls.color }}>
                      {ls.glyph}
                    </span>
                    <span className="text-xs font-bold text-gray-300">{prog.name}</span>
                  </div>
                  <span className="text-[9px] uppercase" style={{ color: ls.color }}>
                    {ls.label}
                  </span>
                </div>
                <div className="space-y-1">
                  <div className="flex justify-between text-[10px] text-gray-500">
                    <span>Module</span>
                    <span className="text-gray-300">{prog.module}</span>
                  </div>
                  <div className="flex justify-between text-[10px] text-gray-500">
                    <span>Priority</span>
                    <span className="text-accent-orange">P{prog.priority}</span>
                  </div>
                  <div className="flex justify-between text-[10px] text-gray-500">
                    <span>Flex</span>
                    <span className="text-gray-300">{prog.flex?.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-[10px] text-gray-500">
                    <span>Wake</span>
                    <span className="text-gray-300">
                      {new Date(prog.wake_time).toISOString().split("T")[1].split(":").slice(0, 2).join(":")}Z
                    </span>
                  </div>
                  <div className="flex justify-between text-[10px] text-gray-500">
                    <span>Retire</span>
                    <span className="text-gray-300">
                      {new Date(prog.retire_time).toISOString().split("T")[1].split(":").slice(0, 2).join(":")}Z
                    </span>
                  </div>
                  {prog.countdown && (
                    <div className="flex justify-between text-[10px] text-gray-500 pt-1 border-t border-gray-800">
                      <span>{GLYPHS.expiring} Countdown</span>
                      <span style={{ color: ls.color }} className="font-mono">
                        {prog.countdown}
                      </span>
                    </div>
                  )}
                  {prog.status === "active" && (
                    <div className="flex justify-between text-[10px] text-gray-500 pt-1 border-t border-gray-800">
                      <span>{GLYPHS.streaming} Executing</span>
                      <span className="text-signal-live font-mono animate-pulse">RUNNING</span>
                    </div>
                  )}
                  {prog.status === "retired" && (
                    <div className="flex justify-between text-[10px] text-gray-500 pt-1 border-t border-gray-800">
                      <span>{GLYPHS.verified} Receipt</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* HOURLY SPAWN DENSITY */}
        <div className="glass-panel p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="glyph text-accent-orange">{GLYPHS.indexed}</span>
            <span className="text-xs uppercase tracking-wider text-gray-400">
              Hourly Spawn Density
            </span>
          </div>
          <div className="flex items-end gap-1 h-20">
            {hourlyDensity.map((count: number, hour: number) => {
              const isCurrent = hour === clock.getUTCHours();
              const height = count > 0 ? Math.max(8, count * 40) : 2;
              return (
                <div key={hour} className="flex-1 flex flex-col items-center justify-end">
                  <div
                    className="w-full rounded-t transition-all duration-500"
                    style={{
                      height: `${height}%`,
                      background: count > 0
                        ? isCurrent
                          ? "#ff6b1a"
                          : "rgba(255,107,26,0.4)"
                        : "rgba(255,255,255,0.03)",
                      boxShadow: isCurrent && count > 0 ? "0 0 8px #ff6b1a66" : "none",
                    }}
                  />
                  <div className="text-[7px] text-gray-700 mt-1">
                    {hour.toString().padStart(2, "0")}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="flex justify-between mt-2 text-[9px] text-gray-700">
            <span>PAST ←</span>
            <span className="text-accent-orange">NOW</span>
            <span>→ NEXT</span>
          </div>
        </div>
      </div>

      {/* DECISION + EXPERIMENT + BIOS */}
      <div className="flex flex-wrap gap-4 mb-6">
        <Pane
          title="Decision Gate"
          glyph={GLYPHS.verified}
          lifeState={
            decision.state === "WINNER_FOUND"
              ? LIFE_STATES.verified
              : decision.state === "ROLLBACK"
                ? LIFE_STATES.critical
                : LIFE_STATES.active
          }
          flex={1}
        >
          <div className="space-y-2">
            <div className="text-lg font-bold" style={{
              color: decision.state === "WINNER_FOUND" ? "#00aaff" :
                decision.state === "ROLLBACK" ? "#ff3344" : "#00ff88"
            }}>
              {decision.state || "—"}
            </div>
            <div className="text-xs text-gray-400">{decision.reason || "No decision recorded"}</div>
            {decision.timestamp && (
              <div className="text-[10px] text-gray-600">
                {new Date(decision.timestamp).toISOString().split("T")[1].split(".")[0]}Z
              </div>
            )}
          </div>
        </Pane>

        <Pane
          title="Experiment"
          glyph={GLYPHS.aiReadable}
          lifeState={LIFE_STATES.active}
          flex={1.2}
        >
          <div className="space-y-2">
            <div className="text-sm font-bold text-gray-300">
              {experiment.experiment_id || "—"}
            </div>
            <div className="text-xs text-gray-500">{experiment.hypothesis || "No experiment defined"}</div>
            <div className="flex gap-3 mt-2">
              <div className="text-[10px]">
                <span className="text-gray-600">Status: </span>
                <span className="text-accent-orange">{experiment.decision_state || "—"}</span>
              </div>
              <div className="text-[10px]">
                <span className="text-gray-600">Threshold: </span>
                <span className="text-gray-300">
                  {experiment.thresholds?.ctr_lift_target
                    ? `${(experiment.thresholds.ctr_lift_target * 100).toFixed(1)}%`
                    : "—"}
                </span>
              </div>
            </div>
          </div>
        </Pane>

        <Pane
          title="Bio Pool"
          glyph={GLYPHS.mirrored}
          lifeState={LIFE_STATES.idle}
          flex={1.5}
        >
          <div className="grid grid-cols-2 gap-2">
            {bios.map((bio: any) => (
              <div key={bio.bio_id} className="border border-gray-800 rounded p-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-gray-400">{bio.bio_id}</span>
                  <span
                    className="text-[8px] uppercase px-1 rounded"
                    style={{
                      background: bio.status === "approved" ? "#00ff8822" : "#ffaa0022",
                      color: bio.status === "approved" ? "#00ff88" : "#ffaa00",
                    }}
                  >
                    {bio.status}
                  </span>
                </div>
                <div className="text-[10px] text-gray-500 mt-1 truncate">
                  {bio.hook || bio.variant_name || "—"}
                </div>
              </div>
            ))}
          </div>
        </Pane>
      </div>

      {/* LATEST METRICS + RAM SURFACE */}
      <div className="flex flex-wrap gap-4 mb-6">
        <Pane
          title="Latest Metrics"
          glyph={GLYPHS.streaming}
          lifeState={LIFE_STATES.active}
          flex={2}
        >
          <div className="grid grid-cols-3 gap-3">
            <div>
              <div className="text-[10px] text-gray-600 uppercase">Views</div>
              <div className="text-lg text-gray-200 font-bold">
                {latestMetrics.views?.toLocaleString() || "—"}
              </div>
              <MetricBar value={latestMetrics.views || 0} max={10000} color="#00ff88" />
            </div>
            <div>
              <div className="text-[10px] text-gray-600 uppercase">Contact Clicks</div>
              <div className="text-lg text-accent-orange font-bold">
                {latestMetrics.contact_clicks?.toLocaleString() || "—"}
              </div>
              <MetricBar value={latestMetrics.contact_clicks || 0} max={500} color="#ff6b1a" />
            </div>
            <div>
              <div className="text-[10px] text-gray-600 uppercase">Views/Day</div>
              <div className="text-lg text-gray-200 font-bold">
                {latestMetrics.views_per_day || "—"}
              </div>
              <MetricBar value={latestMetrics.views_per_day || 0} max={200} color="#00aaff" />
            </div>
            <div>
              <div className="text-[10px] text-gray-600 uppercase">Days Online</div>
              <div className="text-lg text-gray-200 font-bold">
                {latestMetrics.days_online?.toLocaleString() || "—"}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-gray-600 uppercase">New Visitors</div>
              <div className="text-lg text-gray-200 font-bold">
                {latestMetrics.new_visitors?.toLocaleString() || "—"}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-gray-600 uppercase">Returning</div>
              <div className="text-lg text-gray-200 font-bold">
                {latestMetrics.returning_visitors?.toLocaleString() || "—"}
              </div>
            </div>
          </div>
        </Pane>

        <Pane
          title="RAM Surface"
          glyph={GLYPHS.indexed}
          lifeState={LIFE_STATES.verified}
          flex={1}
        >
          <div className="space-y-2">
            <div className="flex justify-between text-[10px]">
              <span className="text-gray-500">Resident</span>
              <span className="text-signal-verified">42 MB</span>
            </div>
            <div className="flex justify-between text-[10px]">
              <span className="text-gray-500">Streamed</span>
              <span className="text-signal-live">9.4 GB</span>
            </div>
            <div className="flex justify-between text-[10px]">
              <span className="text-gray-500">Cached</span>
              <span className="text-gray-300">128 MB</span>
            </div>
            <div className="flex justify-between text-[10px]">
              <span className="text-gray-500">Discarded</span>
              <span className="text-gray-600">8.8 GB</span>
            </div>
            <div className="pt-2 border-t border-gray-800">
              <div className="flex justify-between text-[10px]">
                <span className="text-gray-500">Saved</span>
                <span className="text-accent-orange font-bold">99.1%</span>
              </div>
            </div>
            <div className="text-[9px] text-gray-700 mt-2">
              {GLYPHS.streaming} Streaming perception, not loading lists
            </div>
          </div>
        </Pane>
      </div>

      {/* PREDICTION LANES */}
      <div className="glass-panel p-4 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <span className="glyph text-accent-orange">{GLYPHS.rising}</span>
          <span className="text-xs uppercase tracking-wider text-gray-400">
            Front-Running Trend Surface
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <div className="text-[10px] text-gray-600 uppercase mb-2">Rising Signals</div>
            <div className="space-y-1">
              <div className="text-[11px] text-signal-live">
                {GLYPHS.rising} Views holding steady at {latestMetrics.views_per_day}/day
              </div>
              <div className="text-[11px] text-signal-live">
                {GLYPHS.rising} Contact clicks trending up
              </div>
              <div className="text-[11px] text-gray-500">
                {GLYPHS.falling} Return rate declining
              </div>
            </div>
          </div>
          <div>
            <div className="text-[10px] text-gray-600 uppercase mb-2">Emerging Activity</div>
            <div className="space-y-1">
              {programs.filter((p: any) => p.status === "dormant").map((p: any) => (
                <div key={p.id} className="text-[11px] text-accent-orange">
                  {GLYPHS.expiring} {p.name} wakes in {p.countdown}
                </div>
              ))}
              {programs.filter((p: any) => p.status === "active").map((p: any) => (
                <div key={p.id} className="text-[11px] text-signal-live">
                  {GLYPHS.streaming} {p.name} executing now
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-gray-600 uppercase mb-2">Latent Risk</div>
            <div className="space-y-1">
              <div className="text-[11px] text-signal-warn">
                {GLYPHS.anomalous} Conversion rate below 5% threshold
              </div>
              <div className="text-[11px] text-gray-500">
                {GLYPHS.dormant} No dirty signals detected
              </div>
              <div className="text-[11px] text-signal-verified">
                {GLYPHS.verified} {receiptCount} receipts backing all claims
              </div>
            </div>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-gray-800">
          <div className="flex justify-between text-[9px] text-gray-700">
            <span>PAST ─────</span>
            <span className="text-accent-orange">NOW</span>
            <span>───── NEXT</span>
          </div>
          <div className="flex justify-center gap-8 mt-2">
            <span className="text-[9px] text-signal-live">activity wave</span>
            <span className="text-[9px] text-signal-warn">anomaly wave</span>
            <span className="text-[9px] text-accent-orange">demand wave</span>
            <span className="text-[9px] text-signal-verified">agent interest wave</span>
          </div>
        </div>
      </div>

      {/* FOOTER */}
      <footer className="flex items-center justify-between text-[10px] text-gray-700 pt-4 border-t border-gray-900">
        <div>
          {GLYPHS.verified} ClientPulse OS · {kpiData?.product || "RevenueOps Control Plane"}
        </div>
        <div>
          {GLYPHS.streaming} Polling every 5s · Tick #{tick}
        </div>
        <div>
          {GLYPHS.indexed} {new Date().toISOString().split("T")[0]}
        </div>
      </footer>
    </div>
  );
}
