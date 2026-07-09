import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Monitor, X, Activity, Database, Clock, Hash } from 'lucide-react'

const API_BASE = ''

export default function SessionsPanel() {
  const [files, setFiles] = useState([])
  const [states, setStates] = useState({})
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)

  const fetchAll = useCallback(async () => {
    try {
      const fRes = await fetch(`${API_BASE}/files`)
      const f = await fRes.json()
      const fileList = f.files || []
      setFiles(fileList)

      const statePromises = fileList.map(async (file) => {
        try {
          const sRes = await fetch(`${API_BASE}/superpose/state/${file.file_id}`)
          return [file.file_id, await sRes.json()]
        } catch {
          return [file.file_id, { error: true }]
        }
      })
      const entries = await Promise.all(statePromises)
      setStates(Object.fromEntries(entries))
    } catch {
      setFiles([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const id = setInterval(fetchAll, 10000)
    return () => clearInterval(id)
  }, [fetchAll])

  const sessions = files.map(f => ({
    file_id: f.file_id,
    filename: f.filename,
    ...states[f.file_id],
  })).filter(s => !s.error)

  const liveCount = sessions.filter(s => s.session_status === 'live').length
  const totalQueries = sessions.reduce((sum, s) => sum + (s.total_queries || 0), 0)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <motion.div
          animate={{ opacity: [0.3, 0.8, 0.3] }}
          transition={{ duration: 1.5, repeat: Infinity }}
          className="text-sm text-secondary font-mono"
        >
          Fetching superposition state...
        </motion.div>
      </div>
    )
  }

  return (
    <div className="p-6 h-full overflow-y-auto thin-scrollbar space-y-4">
      {/* Real summary */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex gap-4">
        <div className="glass rounded-2xl p-4 flex items-center gap-3 flex-1">
          <div className="w-10 h-10 rounded-xl glass-orange flex items-center justify-center">
            <Monitor className="w-5 h-5 text-primary" />
          </div>
          <div>
            <div className="text-2xl font-bold tabular-nums">{sessions.length}</div>
            <div className="text-[10px] text-secondary">File Sessions</div>
          </div>
        </div>
        <div className="glass rounded-2xl p-4 flex items-center gap-3 flex-1">
          <div className="w-10 h-10 rounded-xl bg-success/10 flex items-center justify-center">
            <span className="w-2.5 h-2.5 rounded-full bg-success animate-pulse" />
          </div>
          <div>
            <div className="text-2xl font-bold tabular-nums text-success">{liveCount}</div>
            <div className="text-[10px] text-secondary">Live Now</div>
          </div>
        </div>
        <div className="glass rounded-2xl p-4 flex items-center gap-3 flex-1">
          <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
            <Activity className="w-5 h-5 text-accent" />
          </div>
          <div>
            <div className="text-2xl font-bold tabular-nums">{totalQueries}</div>
            <div className="text-[10px] text-secondary">Total Queries</div>
          </div>
        </div>
      </motion.div>

      {/* Real session list */}
      {sessions.length === 0 ? (
        <div className="glass rounded-2xl p-8 text-center text-sm text-secondary">
          No file sessions. Files appear here once indexed.
        </div>
      ) : (
        <div className="space-y-2">
          {sessions.map((s, i) => {
            const isLive = s.session_status === 'live'
            return (
              <motion.div
                key={s.file_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                whileHover={{ x: 4 }}
                onClick={() => setSelected(s)}
                className="glass rounded-xl p-4 flex items-center gap-4 cursor-pointer hover:glass-orange transition-all"
              >
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${isLive ? 'bg-success animate-pulse' : 'bg-secondary'}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{s.filename}</span>
                    <span className="text-[10px] text-secondary font-mono">{s.file_id}</span>
                  </div>
                  <div className="text-[10px] text-secondary">
                    {s.total_queries || 0} queries · {s.query_breakdown ? Object.entries(s.query_breakdown).map(([k, v]) => `${k}:${v}`).join(' · ') : 'no breakdown'}
                  </div>
                </div>
                <div className="flex items-center gap-4 text-[10px] text-secondary flex-shrink-0">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {s.last_access ? new Date(s.last_access * 1000).toLocaleTimeString() : 'never'}
                  </span>
                  <span className={`font-mono ${isLive ? 'text-success' : 'text-secondary'}`}>
                    {isLive ? 'LIVE' : 'IDLE'}
                  </span>
                </div>
              </motion.div>
            )
          })}
        </div>
      )}

      {/* Detail modal — real data */}
      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
            onClick={() => setSelected(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={e => e.stopPropagation()}
              className="glass-strong rounded-2xl p-6 w-full max-w-md"
            >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-primary" />
                  <span className="text-sm font-semibold">Superposition State</span>
                </div>
                <button onClick={() => setSelected(null)} className="text-secondary hover:text-text">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="space-y-3">
                {[
                  ['File', selected.filename],
                  ['File ID', selected.file_id],
                  ['Session', selected.session_status || '—'],
                  ['Uploaded', selected.uploaded_at ? new Date(selected.uploaded_at * 1000).toLocaleString() : '—'],
                  ['Last Access', selected.last_access ? new Date(selected.last_access * 1000).toLocaleString() : 'Never'],
                  ['Total Queries', selected.total_queries || 0],
                  ['Index Size', selected.index_size_bytes ? `${(selected.index_size_bytes / 1024).toFixed(1)} KB` : '—'],
                  ['Original Size', selected.original_size || '—'],
                  ['Compression', selected.compression_ratio || '—'],
                ].map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between py-2 border-b border-white/5">
                    <span className="text-xs text-secondary">{k}</span>
                    <span className="text-xs font-mono text-text">{String(v)}</span>
                  </div>
                ))}
              </div>
              {selected.query_breakdown && (
                <div className="mt-4">
                  <div className="text-[10px] uppercase tracking-wider text-secondary mb-2">Query Breakdown</div>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(selected.query_breakdown).map(([type, count]) => (
                      <span key={type} className="px-2 py-1 rounded-lg glass text-[10px] font-mono">
                        <span className="text-primary">{type}</span>
                        <span className="text-secondary ml-1">×{count}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
