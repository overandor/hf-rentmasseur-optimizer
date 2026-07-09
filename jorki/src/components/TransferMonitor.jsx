import { useState } from 'react'
import { motion } from 'framer-motion'
import { Activity, Zap, Wifi, Timer, TrendingUp, TrendingDown } from 'lucide-react'
import { useAnimatedNumber, useLiveData, useInterval } from '../hooks/useUtils.js'

function WaveChart({ values, max, color = 'primary', height = 80 }) {
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * 100
    const y = 100 - (v / max) * 100
    return `${x},${y}`
  }).join(' ')

  return (
    <div className="relative" style={{ height }}>
      <svg className="absolute inset-0 w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 100">
        <defs>
          <linearGradient id={`grad-${color}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#FF8A00" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#FF8A00" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon
          points={`0,100 ${points} 100,100`}
          fill={`url(#grad-${color})`}
        />
        <polyline
          points={points}
          fill="none"
          stroke="#FF8A00"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  )
}

export default function TransferMonitor() {
  const [uploadHistory, setUploadHistory] = useState(Array.from({ length: 40 }, () => 1.5 + Math.random() * 1.5))
  const [downloadHistory, setDownloadHistory] = useState(Array.from({ length: 40 }, () => 1.2 + Math.random() * 1.2))

  const liveData = useLiveData({
    uploadRate: 2.34,
    downloadRate: 1.92,
    connections: 128,
    latency: 19,
  }, 1500, 0.05)

  useInterval(() => {
    setUploadHistory(prev => [...prev.slice(1), liveData.uploadRate])
    setDownloadHistory(prev => [...prev.slice(1), liveData.downloadRate])
  }, 1500)

  const animatedUpload = useAnimatedNumber(liveData.uploadRate, 500)
  const animatedDownload = useAnimatedNumber(liveData.downloadRate, 500)
  const animatedConn = useAnimatedNumber(liveData.connections, 500)
  const animatedLat = useAnimatedNumber(liveData.latency, 500)

  const uploadTrend = uploadHistory[uploadHistory.length - 1] > uploadHistory[uploadHistory.length - 5]
  const downloadTrend = downloadHistory[downloadHistory.length - 1] > downloadHistory[downloadHistory.length - 5]

  return (
    <div className="p-6 h-full overflow-y-auto thin-scrollbar space-y-4">
      {/* Live banner */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl p-5 scanline"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
            <span className="text-sm font-semibold">Transfer Monitor</span>
            <span className="text-[10px] text-success font-mono ml-2">LIVE</span>
          </div>
          <span className="text-[10px] text-secondary">Updates every 1.5s</span>
        </div>

        {/* Upload wave */}
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <TrendingUp className={`w-3.5 h-3.5 ${uploadTrend ? 'text-success' : 'text-critical'}`} />
              <span className="text-xs text-secondary">Upload Rate</span>
            </div>
            <span className="text-lg font-bold tabular-nums">
              {animatedUpload.toFixed(2)}<span className="text-xs text-secondary ml-1">GB/s</span>
            </span>
          </div>
          <WaveChart values={uploadHistory} max={4} color="primary" height={60} />
        </div>

        {/* Download wave */}
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <TrendingDown className={`w-3.5 h-3.5 ${downloadTrend ? 'text-success' : 'text-critical'}`} />
              <span className="text-xs text-secondary">Download Rate</span>
            </div>
            <span className="text-lg font-bold tabular-nums">
              {animatedDownload.toFixed(2)}<span className="text-xs text-secondary ml-1">GB/s</span>
            </span>
          </div>
          <WaveChart values={downloadHistory} max={3} color="accent" height={60} />
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3 pt-3 border-t border-white/5">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-1.5">
              <Wifi className="w-3 h-3 text-primary" />
              <span className="text-[10px] uppercase tracking-wider text-secondary">Connections</span>
            </div>
            <span className="text-lg font-bold tabular-nums">{Math.round(animatedConn)}</span>
          </div>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-1.5">
              <Timer className="w-3 h-3 text-warning" />
              <span className="text-[10px] uppercase tracking-wider text-secondary">Latency</span>
            </div>
            <span className="text-lg font-bold tabular-nums">{animatedLat.toFixed(0)}<span className="text-xs text-secondary ml-1">ms</span></span>
          </div>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-1.5">
              <Zap className="w-3 h-3 text-accent" />
              <span className="text-[10px] uppercase tracking-wider text-secondary">Total</span>
            </div>
            <span className="text-lg font-bold tabular-nums">{(animatedUpload + animatedDownload).toFixed(2)}<span className="text-xs text-secondary ml-1">GB/s</span></span>
          </div>
        </div>
      </motion.div>

      {/* Active transfers list */}
      <TransferGrid />
    </div>
  )
}
