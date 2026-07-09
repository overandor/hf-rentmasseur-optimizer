import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Search, ArrowRight, Home, FileText, Code, Settings, Database, Rocket } from 'lucide-react'

const commands = [
  { label: 'Dashboard', section: 'Navigate', panel: 'dashboard', icon: Home },
  { label: 'Files', section: 'Navigate', panel: 'files', icon: FileText },
  { label: 'Query', section: 'Navigate', panel: 'query', icon: Search },
  { label: 'Pipeline', section: 'Navigate', panel: 'pipeline', icon: Rocket },
  { label: 'API Reference', section: 'Navigate', panel: 'api', icon: Code },
  { label: 'Settings', section: 'Navigate', panel: 'settings', icon: Settings },
  { label: 'SQL Query', section: 'Actions', panel: 'query', icon: Database },
  { label: 'Search Files', section: 'Actions', panel: 'files', icon: Search },
  { label: 'Run Clipboard Pipeline', section: 'Actions', panel: 'pipeline', icon: Rocket },
]

export default function CommandPalette({ onClose, onSelect }) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef(null)

  const filtered = commands.filter(item =>
    item.label.toLowerCase().includes(query.toLowerCase())
  )

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex(prev => Math.min(prev + 1, filtered.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex(prev => Math.max(prev - 1, 0))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        if (filtered[selectedIndex]) {
          onSelect(filtered[selectedIndex].panel)
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [filtered, selectedIndex, onSelect])

  const sections = [...new Set(filtered.map(i => i.section))]

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: -10 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: -10 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        onClick={e => e.stopPropagation()}
        className="glass-strong rounded-2xl w-full max-w-lg overflow-hidden glow-orange"
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-white/5">
          <Search className="w-4 h-4 text-secondary" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => { setQuery(e.target.value); setSelectedIndex(0) }}
            placeholder="Type a command or search..."
            className="flex-1 bg-transparent text-sm text-text placeholder-secondary/50 focus:outline-none"
          />
          <kbd className="text-[10px] text-secondary/50 font-mono px-1.5 py-0.5 rounded bg-white/5">ESC</kbd>
        </div>

        {/* Results */}
        <div className="max-h-[300px] overflow-y-auto thin-scrollbar p-2">
          {sections.map(section => (
            <div key={section}>
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-secondary/50 font-semibold">
                {section}
              </div>
              {filtered.filter(i => i.section === section).map(item => {
                const idx = filtered.indexOf(item)
                return (
                  <button
                    key={item.label}
                    onClick={() => onSelect(item.panel)}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-all ${selectedIndex === idx ? 'glass-orange text-primary' : 'text-secondary hover:bg-white/5'
                      }`}
                  >
                    <item.icon className="w-4 h-4 flex-shrink-0 text-primary" />
                    <span className="flex-1 text-left">{item.label}</span>
                    {selectedIndex === idx && <ArrowRight className="w-3.5 h-3.5" />}
                  </button>
                )
              })}
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="px-3 py-8 text-center text-sm text-secondary/50">No results found</div>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}
