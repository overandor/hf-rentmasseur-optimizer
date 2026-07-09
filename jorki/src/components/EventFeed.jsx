import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Radio } from 'lucide-react'
import { mockEvents, eventTemplates, fileNames, fileSizes } from '../data/mockData.js'
import { useInterval } from '../hooks/useUtils.js'

const colorMap = {
  primary: 'text-primary',
  success: 'text-success',
  accent: 'text-accent',
  secondary: 'text-secondary',
  critical: 'text-critical',
  warning: 'text-warning',
}

const bgMap = {
  primary: 'bg-primary/10',
  success: 'bg-success/10',
  accent: 'bg-accent/10',
  secondary: 'bg-secondary/10',
  critical: 'bg-critical/10',
  warning: 'bg-warning/10',
}

export default function EventFeed() {
  const [events, setEvents] = useState(mockEvents)
  const idRef = useRef(100)

  useInterval(() => {
    const template = eventTemplates[Math.floor(Math.random() * eventTemplates.length)]
    const file = fileNames[Math.floor(Math.random() * fileNames.length)]
    const size = fileSizes[Math.floor(Math.random() * fileSizes.length)]
    const now = new Date()
    const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`

    const newEvent = {
      id: idRef.current++,
      time,
      type: template.type,
      file,
      detail: template.detail(file, size),
      status: template.status,
      color: template.color,
    }

    setEvents(prev => [newEvent, ...prev].slice(0, 12))
  }, 2500)

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.35 }}
      className="glass rounded-2xl p-4 flex flex-col"
      style={{ maxHeight: '320px' }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Live Event Feed</span>
        </div>
        <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
      </div>

      <div className="flex-1 overflow-y-auto thin-scrollbar space-y-1">
        <AnimatePresence initial={false}>
          {events.map(event => (
            <motion.div
              key={event.id}
              initial={{ opacity: 0, x: -20, height: 0 }}
              animate={{ opacity: 1, x: 0, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3 }}
              className="flex items-start gap-3 py-2 border-b border-white/5 last:border-0"
            >
              <span className="text-[10px] font-mono text-secondary/60 mt-0.5 w-16 flex-shrink-0">
                {event.time}
              </span>
              <div className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-semibold ${bgMap[event.color]} ${colorMap[event.color]} flex-shrink-0`}>
                {event.type}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-text truncate">{event.file}</div>
                <div className="text-[10px] text-secondary">
                  {event.detail}
                  {event.status && <span className={`ml-1 ${colorMap[event.color]}`}>· {event.status}</span>}
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
