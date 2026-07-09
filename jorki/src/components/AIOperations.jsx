import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Zap, Database, Terminal } from 'lucide-react'
import { mockAIModels, aiQueries } from '../data/mockData.js'

export default function AIOperations() {
  const [query, setQuery] = useState('SELECT * FROM files WHERE size > 5GB')
  const [queryIndex, setQueryIndex] = useState(0)

  const queries = [
    'SELECT * FROM files WHERE size > 5GB',
    'SELECT name, downloads FROM files ORDER BY downloads DESC LIMIT 10',
    'SELECT type, COUNT(*) FROM files GROUP BY type',
    'SELECT * FROM transfers WHERE status = "live"',
    'SELECT SUM(size) FROM files WHERE status = "shared"',
  ]

  useEffect(() => {
    const id = setInterval(() => {
      setQueryIndex(prev => (prev + 1) % queries.length)
      setQuery(queries[(queryIndex + 1) % queries.length])
    }, 4000)
    return () => clearInterval(id)
  }, [queryIndex])

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.45 }}
      className="glass rounded-2xl p-5 h-full"
    >
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-4 h-4 text-primary" />
        <span className="text-sm font-semibold">AI Operations</span>
      </div>

      {/* Model status */}
      <div className="space-y-2 mb-4">
        {mockAIModels.map(m => (
          <div key={m.name} className="flex items-center justify-between glass rounded-xl px-3 py-2">
            <span className="text-xs font-medium">{m.name}</span>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
              <span className="text-[10px] text-success font-mono">{m.status}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Current query */}
      <div className="glass-orange rounded-xl p-3 mb-3">
        <div className="flex items-center gap-2 mb-2">
          <Terminal className="w-3 h-3 text-primary" />
          <span className="text-[10px] uppercase tracking-wider text-secondary">Current Query</span>
        </div>
        <motion.div
          key={query}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="font-mono text-[11px] text-primary leading-relaxed"
        >
          {query}
        </motion.div>
      </div>

      {/* AI actions */}
      <div className="flex flex-wrap gap-1.5">
        {aiQueries.slice(0, 6).map(q => (
          <button
            key={q}
            className="text-[10px] px-2 py-1 rounded-lg glass hover:glass-orange text-secondary hover:text-primary transition-all"
          >
            {q}
          </button>
        ))}
      </div>
    </motion.div>
  )
}
