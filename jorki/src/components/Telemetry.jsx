import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Wifi, Activity, Timer, ShieldCheck } from 'lucide-react'
import { useAnimatedNumber, useLiveData, useInterval, formatNumber } from '../hooks/useUtils.js'

function BarChart({ values, max, color = 'primary', height = 60 }) {
  return (
    <div className="flex items-end gap-1" style={{ height }}>
      {values.map((v, i) => (
        <motion.div
          key={i}
          className={`flex-1 rounded-sm bg-${color}`}
          initial={{ height: 0 }}
          animate={{ height: `${(v / max) * 100}%` }}
          transition={{ duration: 0.4, delay: i * 0.02 }}
          style={{ minHeight: '2px' }}
        />
      ))}
    </div>
  )
}

export default function Telemetry() {
  const [connHistory, setConnHistory] = useState(Array.from({ length: 20 }, () => 600 + Math.random() * 300))
  const [reqHistory, setReqHistory] = useState(Array.from({ length: 20 }, () => 7000 + Math.random() * 3000))

  const liveData = useLiveData({
    connections: 842,
    requestsPerSec: 9224,
    avgLatency: 14,
    integrity: 100,
  }, 2000, 0.03)

  useInterval(() => {
    setConnHistory(prev => [...prev.slice(1), liveData.connections])
    setReqHistory(prev => [...prev.slice(1), liveData.requestsPerSec])
  }, 2000)

  const animatedConn = useAnimatedNumber(liveData.connections, 600)
  const animatedReq = useAnimatedNumber(liveData.requestsPerSec, 600)
  const animatedLat = useAnimatedNumber(liveData.avgLatency, 600)

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.4 }}
      className="glass rounded-2xl p-5 h-full"
    >
      <div className="flex items-center gap-2 mb-4">
        <Activity className="w-4 h-4 text-primary" />
        <span className="text-sm font-semibold">Telemetry</span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Connections */}
        <div className="glass rounded-xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <Wifi className="w-3.5 h-3.5 text-primary" />
            <span className="text-[10px] uppercase tracking-wider text-secondary">Connections</span>
          </div>
          <div className="text-xl font-bold tabular-nums mb-2">{Math.round(animatedConn)}</div>
          <BarChart values={connHistory} max={1000} color="primary" height={40} />
        </div>

        {/* Requests/sec */}
        <div className="glass rounded-xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-3.5 h-3.5 text-accent" />
            <span className="text-[10px] uppercase tracking-wider text-secondary">Requests/sec</span>
          </div>
          <div className="text-xl font-bold tabular-nums mb-2">{formatNumber(animatedReq)}</div>
          <BarChart values={reqHistory} max={12000} color="accent" height={40} />
        </div>

        {/* Average Latency */}
        <div className="glass rounded-xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <Timer className="w-3.5 h-3.5 text-warning" />
            <span className="text-[10px] uppercase tracking-wider text-secondary">Avg Latency</span>
          </div>
          <div className="text-xl font-bold tabular-nums">
            {animatedLat.toFixed(0)}<span className="text-xs text-secondary ml-1">ms</span>
          </div>
          <div className="mt-2 h-1.5 rounded-full bg-white/5 overflow-hidden">
            <motion.div
              className="h-full bg-warning rounded-full"
              animate={{ width: `${(animatedLat / 50) * 100}%` }}
              transition={{ duration: 0.6 }}
            />
          </div>
        </div>

        {/* Integrity */}
        <div className="glass rounded-xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck className="w-3.5 h-3.5 text-success" />
            <span className="text-[10px] uppercase tracking-wider text-secondary">Integrity</span>
          </div>
          <div className="text-xl font-bold tabular-nums text-success">
            {liveData.integrity}<span className="text-xs text-secondary ml-1">%</span>
          </div>
          <div className="mt-2 flex items-center gap-1">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="flex-1 h-1.5 rounded-full bg-success/80" />
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  )
}
