import { useState, useEffect, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import Landing from './components/Landing.jsx'
import CommandCenter from './components/CommandCenter.jsx'
import CommandPalette from './components/CommandPalette.jsx'

export default function App() {
  const [view, setView] = useState('landing')
  const [activePanel, setActivePanel] = useState('dashboard')
  const [paletteOpen, setPaletteOpen] = useState(false)

  const openCommandCenter = useCallback(() => {
    setView('command')
    setActivePanel('dashboard')
  }, [])

  const openLanding = useCallback(() => {
    setView('landing')
  }, [])

  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        if (view === 'command') {
          setPaletteOpen(prev => !prev)
        }
      }
      if (e.key === 'Escape') {
        setPaletteOpen(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [view])

  return (
    <>
      <AnimatePresence mode="wait">
        {view === 'landing' ? (
          <motion.div
            key="landing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.4 }}
          >
            <Landing onLaunch={openCommandCenter} />
          </motion.div>
        ) : (
          <motion.div
            key="command"
            initial={{ opacity: 0, scale: 1.02 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <CommandCenter
              activePanel={activePanel}
              setActivePanel={setActivePanel}
              onExit={openLanding}
            />
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {paletteOpen && (
          <CommandPalette
            onClose={() => setPaletteOpen(false)}
            onSelect={(panel) => {
              setActivePanel(panel)
              setPaletteOpen(false)
            }}
          />
        )}
      </AnimatePresence>
    </>
  )
}
