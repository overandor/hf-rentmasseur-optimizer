import { useState, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Home, FileText, Search, Code, Settings, Shield, ArrowLeft, Rocket,
  Dna, BookOpen,
} from 'lucide-react'
import Dashboard from './Dashboard.jsx'
import FileDetail from './FileDetail.jsx'
import FileIntelligence from './FileIntelligence.jsx'
import FileDossier from './FileDossier.jsx'
import FormulasPanel from './FormulasPanel.jsx'
import QueryPanel from './QueryPanel.jsx'
import APIPanel from './APIPanel.jsx'
import SettingsPanel from './SettingsPanel.jsx'
import PipelinePanel from './PipelinePanel.jsx'

const API_BASE = ''

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: Home },
  { id: 'files', label: 'Files', icon: FileText },
  { id: 'intel', label: 'Intelligence', icon: Dna },
  { id: 'dossier', label: 'Dossier', icon: FileText },
  { id: 'formulas', label: 'Formulas', icon: BookOpen },
  { id: 'query', label: 'Query', icon: Search },
  { id: 'pipeline', label: 'Pipeline', icon: Rocket },
  { id: 'api', label: 'API', icon: Code },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export default function CommandCenter({ activePanel, setActivePanel, onExit }) {
  const [health, setHealth] = useState(null)
  const [fileCount, setFileCount] = useState(0)
  const [selectedFileId, setSelectedFileId] = useState(null)

  useEffect(() => {
    const poll = async () => {
      try {
        const hRes = await fetch(`${API_BASE}/health`)
        const h = await hRes.json()
        setHealth(h)
        setFileCount(h.files_registered ?? 0)
      } catch {
        setHealth({ status: 'error' })
      }
    }
    poll()
    const id = setInterval(poll, 10000)
    return () => clearInterval(id)
  }, [])

  const isLive = health?.status === 'ok'

  const renderPanel = () => {
    switch (activePanel) {
      case 'dashboard':
        return <Dashboard setActivePanel={setActivePanel} onSelectFile={(id) => { setSelectedFileId(id); setActivePanel('files') }} />
      case 'files':
        return <FileDetail fileId={selectedFileId} onClear={() => setSelectedFileId(null)} />
      case 'intel':
        return <FileIntelligence fileId={selectedFileId} onBack={() => { setSelectedFileId(null); setActivePanel('dashboard') }} />
      case 'dossier':
        return selectedFileId
          ? <FileDossier fileId={selectedFileId} onClose={() => { setSelectedFileId(null); setActivePanel('dashboard') }} />
          : <FileSelector onFileSelect={(id) => { setSelectedFileId(id); setActivePanel('dossier') }} />
      case 'formulas':
        return <FormulasPanel />
      case 'query':
        return <QueryPanel />
      case 'pipeline':
        return <PipelinePanel />
      case 'api':
        return <APIPanel />
      case 'settings':
        return <SettingsPanel />
      default:
        return <Dashboard setActivePanel={setActivePanel} onSelectFile={(id) => { setSelectedFileId(id); setActivePanel('files') }} />
    }
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg">
      {/* Sidebar */}
      <div className="w-56 flex-shrink-0 glass-strong border-r border-white/5 flex flex-col">
        {/* Logo */}
        <div className="flex items-center gap-2 px-5 h-14 border-b border-white/5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center glow-orange">
            <span className="text-bg font-black text-sm">J</span>
          </div>
          <span className="font-bold tracking-tight">Jorki</span>
          <span className={`ml-auto text-[10px] font-mono flex items-center gap-1 ${isLive ? 'text-success' : 'text-critical'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-success animate-pulse' : 'bg-critical'}`} />
            {isLive ? 'LIVE' : 'OFF'}
          </span>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto thin-scrollbar py-3 px-2">
          {navItems.map(item => (
            <button
              key={item.id}
              onClick={() => setActivePanel(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all mb-0.5 ${activePanel === item.id
                ? 'glass-orange text-primary font-medium'
                : 'text-secondary hover:text-text hover:bg-white/5'
                }`}
            >
              <item.icon className="w-4 h-4 flex-shrink-0" />
              <span className="flex-1 text-left">{item.label}</span>
              {item.id === 'files' && fileCount > 0 && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-secondary">
                  {fileCount}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Bottom — real status only */}
        <div className="border-t border-white/5 p-3 space-y-2">
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl glass text-xs">
            <Shield className={`w-3.5 h-3.5 ${isLive ? 'text-success' : 'text-critical'}`} />
            <span className="text-secondary">{isLive ? 'Verified' : 'Unverified'}</span>
            <span className={`ml-auto font-mono ${isLive ? 'text-success' : 'text-critical'}`}>
              {health?.version ? `v${health.version}` : '—'}
            </span>
          </div>
          <button
            onClick={onExit}
            className="w-full flex items-center gap-2 text-xs text-secondary/60 hover:text-text px-3 py-2 transition-colors"
          >
            <ArrowLeft className="w-3 h-3" />
            Back to Landing
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar — real data only */}
        <div className="h-14 border-b border-white/5 glass-strong flex items-center px-6 gap-4 flex-shrink-0">
          <h2 className="text-sm font-semibold capitalize">
            {navItems.find(n => n.id === activePanel)?.label || 'Dashboard'}
          </h2>
          <div className="flex-1" />
          <div className="flex items-center gap-3 text-xs">
            <div className="flex items-center gap-1.5 text-secondary">
              <FileText className="w-3.5 h-3.5 text-primary" />
              <span className="font-mono tabular-nums">{fileCount} files</span>
            </div>
            <div className="w-px h-4 bg-white/10" />
            <div className="flex items-center gap-1.5 text-secondary">
              <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-success' : 'bg-critical'}`} />
              <span className="font-mono">{isLive ? 'Space Live' : 'Space Down'}</span>
            </div>
          </div>
        </div>

        {/* Panel content */}
        <div className="flex-1 overflow-y-auto thin-scrollbar">
          <AnimatePresence mode="wait">
            <motion.div
              key={activePanel}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              {renderPanel()}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}

function FileSelector({ onFileSelect }) {
  const [files, setFiles] = useState([])
  useEffect(() => {
    fetch(`${API_BASE}/files`).then(r => r.json()).then(d => setFiles(d.files || [])).catch(() => { })
  }, [])
  return (
    <div className="p-6">
      <div className="glass rounded-2xl p-5">
        <div className="text-sm font-semibold mb-4">Select a file to view dossier</div>
        {files.length === 0 ? (
          <div className="text-xs text-secondary/40 py-4 text-center">No files indexed. Upload from Dashboard.</div>
        ) : (
          <div className="space-y-1">
            {files.map(f => (
              <button
                key={f.file_id}
                onClick={() => onFileSelect(f.file_id)}
                className="w-full flex items-center gap-3 py-2.5 px-3 rounded-xl glass hover:glass-orange text-secondary hover:text-primary transition-all"
              >
                <FileText className="w-4 h-4 flex-shrink-0" />
                <span className="text-xs font-mono flex-1 text-left">{f.filename}</span>
                <span className="text-[10px] font-mono text-secondary/40">{f.size}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
