import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { FileVideo, FileArchive, FileText, FileImage, Database, CheckCircle2, Loader } from 'lucide-react'
import { mockTransfers } from '../data/mockData.js'
import { useInterval } from '../hooks/useUtils.js'

const iconMap = {
  video: FileVideo,
  archive: FileArchive,
  file: FileText,
  image: FileImage,
  database: Database,
}

export default function TransferGrid() {
  const [transfers, setTransfers] = useState(mockTransfers)

  useInterval(() => {
    setTransfers(prev =>
      prev.map(t => {
        if (t.status === 'live') {
          const newProgress = Math.min(100, t.progress + Math.random() * 3)
          const newSpeed = t.speed * (0.8 + Math.random() * 0.4)
          return {
            ...t,
            progress: newProgress,
            speed: newSpeed,
            eta: newProgress >= 100 ? 'Done' : `${(100 - newProgress) / newSpeed * 10}`.slice(0, 4) + 's',
            status: newProgress >= 100 ? 'complete' : 'live',
            hash: newProgress >= 100 ? 'Verified' : t.hash,
          }
        }
        return t
      })
    )
  }, 1500)

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.3 }}
      className="glass rounded-2xl p-5"
    >
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-semibold">Transfer Grid</span>
        <span className="text-[10px] text-secondary font-mono">
          {transfers.filter(t => t.status === 'live').length} live · {transfers.filter(t => t.status === 'complete').length} done
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {transfers.map((t, i) => {
          const Icon = FileVideo
          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
              whileHover={{ y: -2 }}
              className="glass rounded-xl p-4 border border-white/5"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 min-w-0">
                  <Icon className="w-4 h-4 text-secondary flex-shrink-0" />
                  <span className="text-xs font-medium truncate">{t.name}</span>
                </div>
                {t.status === 'live' ? (
                  <span className="text-[9px] font-mono text-success flex items-center gap-1 flex-shrink-0">
                    <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                    LIVE
                  </span>
                ) : (
                  <CheckCircle2 className="w-3.5 h-3.5 text-success flex-shrink-0" />
                )}
              </div>

              <div className="h-2 rounded-full bg-white/5 overflow-hidden mb-2">
                <motion.div
                  className="h-full bar-fill"
                  animate={{ width: `${t.progress}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>

              <div className="flex items-center justify-between text-[10px] mb-2">
                <span className="text-text font-mono tabular-nums">{Math.round(t.progress)}%</span>
                <span className="text-secondary">{t.size}</span>
              </div>

              <div className="grid grid-cols-3 gap-2 text-[9px] text-secondary">
                <div>
                  <span className="block text-secondary/50">Speed</span>
                  <span className="text-text font-mono">{t.speed > 0 ? t.speed.toFixed(1) + ' GB/s' : '—'}</span>
                </div>
                <div>
                  <span className="block text-secondary/50">ETA</span>
                  <span className="text-text font-mono">{t.eta}</span>
                </div>
                <div>
                  <span className="block text-secondary/50">Hash</span>
                  <span className={t.hash === 'Verified' ? 'text-success' : t.hash === 'Pending' ? 'text-warning' : 'text-secondary'}>
                    {t.hash}
                  </span>
                </div>
              </div>
            </motion.div>
          )
        })}
      </div>
    </motion.div>
  )
}
