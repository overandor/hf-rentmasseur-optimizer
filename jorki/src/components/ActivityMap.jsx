import { motion } from 'framer-motion'
import { Globe } from 'lucide-react'
import { mockNodes, mockConnections } from '../data/mockData.js'

export default function ActivityMap() {
  const nodeMap = Object.fromEntries(mockNodes.map(n => [n.name, n]))

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.3 }}
      className="glass rounded-2xl p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Global Activity</span>
        </div>
        <span className="text-[10px] text-secondary font-mono">{mockNodes.length} nodes</span>
      </div>

      <div className="relative aspect-[2/1] rounded-xl bg-bg/50 overflow-hidden grid-bg">
        {/* Connection lines */}
        <svg className="absolute inset-0 w-full h-full">
          {mockConnections.map((conn, i) => {
            const from = nodeMap[conn.from]
            const to = nodeMap[conn.to]
            if (!from || !to) return null
            return (
              <g key={i}>
                <line
                  x1={`${from.x}%`} y1={`${from.y}%`}
                  x2={`${to.x}%`} y2={`${to.y}%`}
                  stroke="rgba(255,138,0,0.15)"
                  strokeWidth="1"
                />
                <motion.circle
                  r="2"
                  fill="#FF8A00"
                  initial={{ offsetDistance: '0%' }}
                  animate={{ offsetDistance: ['0%', '100%'] }}
                  transition={{ duration: 2 + i * 0.3, repeat: Infinity, ease: 'linear' }}
                  style={{
                    offsetPath: `path('M ${from.x * 4} ${from.y * 2} L ${to.x * 4} ${to.y * 2}')`,
                    offsetRotate: '0deg',
                  }}
                />
              </g>
            )
          })}
        </svg>

        {/* Nodes */}
        {mockNodes.map((node, i) => (
          <div
            key={node.name}
            className="absolute group"
            style={{ left: `${node.x}%`, top: `${node.y}%`, transform: 'translate(-50%, -50%)' }}
          >
            <motion.div
              className="w-2 h-2 rounded-full bg-primary"
              animate={{ scale: [1, 1.5, 1], opacity: [0.6, 1, 0.6] }}
              transition={{ duration: 2, delay: i * 0.2, repeat: Infinity }}
            />
            <motion.div
              className="absolute inset-0 rounded-full border border-primary/40"
              animate={{ scale: [1, 3, 1], opacity: [0.5, 0, 0.5] }}
              transition={{ duration: 2, delay: i * 0.2, repeat: Infinity }}
            />
            <div className="absolute left-3 top-1/2 -translate-y-1/2 whitespace-nowrap text-[9px] text-secondary opacity-0 group-hover:opacity-100 transition-opacity">
              {node.name} · {node.latency}ms
            </div>
          </div>
        ))}
      </div>

      <div className="mt-2 flex items-center justify-between text-[10px] text-secondary">
        <span>Every pulse = active transfer</span>
        <span className="text-success">All nodes online</span>
      </div>
    </motion.div>
  )
}
