import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { BarChart3, TrendingUp, TrendingDown, Activity, Users, HardDrive, Zap, Clock } from 'lucide-react'
import { useAnimatedNumber, useLiveData, useInterval } from '../hooks/useUtils.js'

function Sparkline({ data, max, color = '#FF8A00', height = 40 }) {
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * 100
    const y = 100 - (v / max) * 90 - 5
    return `${x},${y}`
  }).join(' ')

  return (
    <svg className="w-full" style={{ height }} preserveAspectRatio="none" viewBox="0 0 100 100">
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function MetricCard({ icon: Icon, label, value, unit, trend, sparkData, sparkColor, delay }) {
  const animated = useAnimatedNumber(value, 600)
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      whileHover={{ y: -2 }}
      className="glass rounded-2xl p-4"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-primary" />
          <span className="text-[10px] uppercase tracking-wider text-secondary">{label}</span>
        </div>
        {trend !== undefined && (
          <span className={`flex items-center gap-0.5 text-[10px] ${trend > 0 ? 'text-success' : 'text-critical'}`}>
            {trend > 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {Math.abs(trend).toFixed(1)}%
          </span>
        )}
      </div>
      <div className="text-2xl font-bold tabular-nums mb-2">
        {typeof animated === 'number' && animated % 1 !== 0 ? animated.toFixed(1) : Math.round(animated)}
        {unit && <span className="text-xs text-secondary ml-1">{unit}</span>}
      </div>
      {sparkData && <Sparkline data={sparkData} max={Math.max(...sparkData) * 1.2} color={sparkColor} height={30} />}
    </motion.div>
  )
}

export default function Analytics() {
  const [storageHistory, setStorageHistory] = useState(Array.from({ length: 30 }, (_, i) => 0.8 + i * 0.015 + Math.random() * 0.05))
  const [transferHistory, setTransferHistory] = useState(Array.from({ length: 30 }, () => 150 + Math.random() * 120))
  const [userHistory, setUserHistory] = useState(Array.from({ length: 30 }, () => 5 + Math.random() * 8))
  const [apiHistory, setApiHistory] = useState(Array.from({ length: 30 }, () => 35 + Math.random() * 15))

  const liveData = useLiveData({
    storage: 1.2,
    transfers: 241,
    users: 11,
    apiCalls: 42,
  }, 3000, 0.02)

  useInterval(() => {
    setStorageHistory(prev => [...prev.slice(1), liveData.storage])
    setTransferHistory(prev => [...prev.slice(1), liveData.transfers])
    setUserHistory(prev => [...prev.slice(1), liveData.users])
    setApiHistory(prev => [...prev.slice(1), liveData.apiCalls])
  }, 3000)

  const storageTrend = ((storageHistory[storageHistory.length - 1] - storageHistory[0]) / storageHistory[0]) * 100
  const transferTrend = ((transferHistory[transferHistory.length - 1] - transferHistory[0]) / transferHistory[0]) * 100
  const userTrend = ((userHistory[userHistory.length - 1] - userHistory[0]) / userHistory[0]) * 100
  const apiTrend = ((apiHistory[apiHistory.length - 1] - apiHistory[0]) / apiHistory[0]) * 100

  return (
    <div className="p-6 h-full overflow-y-auto thin-scrollbar space-y-4">
      {/* Top metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard icon={HardDrive} label="Storage" value={liveData.storage} unit="TB" trend={storageTrend} sparkData={storageHistory} sparkColor="#FF8A00" delay={0} />
        <MetricCard icon={Activity} label="Transfers" value={liveData.transfers} unit="active" trend={transferTrend} sparkData={transferHistory} sparkColor="#FFB347" delay={0.05} />
        <MetricCard icon={Users} label="Live Users" value={liveData.users} unit="online" trend={userTrend} sparkData={userHistory} sparkColor="#32D74B" delay={0.1} />
        <MetricCard icon={Zap} label="API Calls" value={liveData.apiCalls} unit="K/day" trend={apiTrend} sparkData={apiHistory} sparkColor="#FFD60A" delay={0.15} />
      </div>

      {/* Throughput timeline */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass rounded-2xl p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold">Throughput Timeline</span>
          </div>
          <div className="flex items-center gap-3 text-[10px]">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-primary" /> Upload</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-accent" /> Download</span>
          </div>
        </div>
        <div className="flex items-end gap-1 h-32">
          {Array.from({ length: 48 }).map((_, i) => {
            const upload = 30 + Math.sin(i * 0.3) * 20 + Math.random() * 15
            const download = 25 + Math.cos(i * 0.25) * 18 + Math.random() * 12
            return (
              <div key={i} className="flex-1 flex flex-col gap-0.5 justify-end">
                <motion.div
                  className="w-full rounded-t-sm bg-primary/70"
                  initial={{ height: 0 }}
                  animate={{ height: `${upload}%` }}
                  transition={{ duration: 0.4, delay: i * 0.01 }}
                />
                <motion.div
                  className="w-full rounded-b-sm bg-accent/50"
                  initial={{ height: 0 }}
                  animate={{ height: `${download}%` }}
                  transition={{ duration: 0.4, delay: i * 0.01 + 0.05 }}
                />
              </div>
            )
          })}
        </div>
        <div className="flex justify-between mt-2 text-[9px] text-secondary/50 font-mono">
          <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span>
        </div>
      </motion.div>

      {/* Recent activity table */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="glass rounded-2xl p-5"
      >
        <div className="flex items-center gap-2 mb-4">
          <Clock className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Recent Activity</span>
        </div>
        <div className="space-y-2">
          {[
            { time: '2m ago', event: 'File indexed', detail: 'dataset.zip → 4.2 GB', status: 'success' },
            { time: '5m ago', event: 'Share link created', detail: 'report.pdf', status: 'accent' },
            { time: '12m ago', event: 'SQL query executed', detail: 'SELECT * FROM chunks', status: 'primary' },
            { time: '18m ago', event: 'Access revoked', detail: 'file_id: 9df7315ee91f', status: 'critical' },
            { time: '31m ago', event: 'Chunk retrieved', detail: 'idx=12, 45 lines', status: 'secondary' },
            { time: '45m ago', event: 'Search performed', detail: '"merkle root"', status: 'primary' },
          ].map((row, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3 + i * 0.05 }}
              className="flex items-center gap-3 py-2 border-b border-white/5 last:border-0"
            >
              <span className="text-[10px] text-secondary/50 font-mono w-16 flex-shrink-0">{row.time}</span>
              <span className={`text-xs flex-shrink-0 ${
                row.status === 'success' ? 'text-success' :
                row.status === 'accent' ? 'text-accent' :
                row.status === 'critical' ? 'text-critical' :
                row.status === 'primary' ? 'text-primary' : 'text-secondary'
              }`}>{row.event}</span>
              <span className="text-xs text-secondary truncate">{row.detail}</span>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </div>
  )
}
