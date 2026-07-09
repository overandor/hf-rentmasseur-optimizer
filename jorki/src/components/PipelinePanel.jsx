import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Rocket, GitBranch, Box, Globe, AppWindow, Disc, ShieldCheck,
  Store, Loader2, Check, X, AlertTriangle, Clipboard, ChevronRight,
  FileSearch, ArrowLeft,
} from 'lucide-react'
import FileDossier from './FileDossier.jsx'

const API_BASE = ''

const STAGES = [
  { id: 'clipboard', label: 'Clipboard', glyph: '⌁', icon: Clipboard, desc: 'Read clipboard content' },
  { id: 'repo', label: 'GitHub Repo', glyph: '◇', icon: GitBranch, desc: 'Create repo + push' },
  { id: 'artifact', label: 'HF Space', glyph: '◍', icon: Box, desc: 'Deploy artifact to HuggingFace' },
  { id: 'deploy', label: 'Vercel', glyph: '⌁', icon: Globe, desc: 'Deploy web UI to Vercel' },
  { id: 'app', label: 'macOS App', glyph: '◉', icon: AppWindow, desc: 'Build SwiftUI app bundle' },
  { id: 'dmg', label: 'DMG', glyph: '◆', icon: Disc, desc: 'Package as DMG' },
  { id: 'notarize', label: 'Notarize', glyph: '◈', icon: ShieldCheck, desc: 'Apple notarization + staple' },
  { id: 'appstore', label: 'App Store', glyph: '✦', icon: Store, desc: 'App Store ready' },
]

const STATE_GLYPHS = {
  idle: { glyph: '◌', color: 'text-secondary', pulse: false },
  active: { glyph: '◉', color: 'text-primary', pulse: true },
  complete: { glyph: '✓', color: 'text-success', pulse: false },
  error: { glyph: '⟁', color: 'text-critical', pulse: false },
  skipped: { glyph: '◍', color: 'text-secondary/50', pulse: false },
}

export default function PipelinePanel() {
  const [pipelineState, setPipelineState] = useState(null)
  const [stageStatuses, setStageStatuses] = useState({})
  const [triggering, setTriggering] = useState(false)
  const [error, setError] = useState(null)
  const [receipts, setReceipts] = useState([])
  const [contentPreview, setContentPreview] = useState('')
  const [logs, setLogs] = useState([])
  const [showDossier, setShowDossier] = useState(false)
  const pollRef = useRef(null)

  const fetchState = useCallback(async (runId) => {
    try {
      const res = await fetch(`${API_BASE}/pipeline/status/${runId}`)
      const data = await res.json()
      setPipelineState(data)
      setContentPreview(data.content_preview || '')
      setReceipts(data.receipt_chain || [])

      const statuses = {}
      for (const stage of STAGES) {
        if (data.completed_stages?.includes(stage.id)) {
          statuses[stage.id] = 'complete'
        } else if (data.current_stage === stage.id) {
          statuses[stage.id] = 'active'
        } else if (data.error_stage === stage.id) {
          statuses[stage.id] = 'error'
        } else {
          statuses[stage.id] = 'idle'
        }
      }
      setStageStatuses(statuses)
      setLogs(data.logs || [])

      if (data.status === 'running') {
        pollRef.current = setTimeout(() => fetchState(runId), 2000)
      }
    } catch (e) {
      setError(e.message)
    }
  }, [])

  const trigger = useCallback(async () => {
    setTriggering(true)
    setError(null)
    setStageStatuses({})
    setReceipts([])
    setLogs([])
    try {
      const res = await fetch(`${API_BASE}/pipeline/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      const data = await res.json()
      if (data.error) {
        setError(data.error)
      } else {
        fetchState(data.run_id)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setTriggering(false)
    }
  }, [fetchState])

  const triggerWithContent = useCallback(async (content) => {
    setTriggering(true)
    setError(null)
    setStageStatuses({})
    setReceipts([])
    setLogs([])
    try {
      const res = await fetch(`${API_BASE}/pipeline/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      })
      const data = await res.json()
      if (data.error) {
        setError(data.error)
      } else {
        fetchState(data.run_id)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setTriggering(false)
    }
  }, [fetchState])

  const checkExisting = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/pipeline/latest`)
      if (res.ok) {
        const data = await res.json()
        if (data.run_id) {
          fetchState(data.run_id)
        }
      }
    } catch {
      // no existing pipeline
    }
  }, [fetchState])

  useEffect(() => {
    checkExisting()
    return () => { if (pollRef.current) clearTimeout(pollRef.current) }
  }, [checkExisting])

  const isRunning = pipelineState?.status === 'running'
  const isComplete = pipelineState?.status === 'complete'
  const hasError = pipelineState?.status === 'error'
  const completedCount = Object.values(stageStatuses).filter(s => s === 'complete').length
  const progress = Math.round((completedCount / STAGES.length) * 100)

  const fileId = pipelineState?.file_id

  if (showDossier && fileId) {
    return <FileDossier fileId={fileId} onClose={() => setShowDossier(false)} />
  }

  return (
    <div className="p-6 space-y-4 h-full overflow-y-auto thin-scrollbar">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Rocket className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold">Clipboard → App Store Pipeline</span>
          </div>
          <div className="flex items-center gap-2">
            {isRunning && (
              <span className="text-[10px] font-mono text-primary flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                RUNNING
              </span>
            )}
            {isComplete && (
              <span className="text-[10px] font-mono text-success flex items-center gap-1">
                <Check className="w-3 h-3" />
                COMPLETE
              </span>
            )}
            {hasError && (
              <span className="text-[10px] font-mono text-critical flex items-center gap-1">
                <X className="w-3 h-3" />
                ERROR
              </span>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-1.5 rounded-full bg-white/5 overflow-hidden mb-3">
          <motion.div
            className="h-full bar-fill"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5 }}
          />
        </div>
        <div className="flex items-center justify-between text-[10px] text-secondary font-mono">
          <span>{completedCount}/{STAGES.length} stages</span>
          <span>{progress}%</span>
        </div>
      </motion.div>

      {/* Trigger */}
      {!isRunning && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="glass rounded-2xl p-5"
        >
          <div className="flex items-center gap-3 mb-4">
            <Clipboard className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold">Trigger Pipeline</span>
          </div>
          <p className="text-xs text-secondary mb-4">
            Reads your clipboard, creates a GitHub repo, deploys to HuggingFace + Vercel,
            builds a macOS app, packages as DMG, notarizes, and prepares for App Store.
          </p>
          <div className="flex gap-2">
            <button
              onClick={trigger}
              disabled={triggering}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm bg-primary text-bg font-medium hover:bg-accent transition-all disabled:opacity-50"
            >
              {triggering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Rocket className="w-4 h-4" />}
              {triggering ? 'Starting…' : 'Run from Clipboard'}
            </button>
          </div>
          {error && (
            <div className="mt-3 flex items-center gap-2 text-xs text-critical">
              <AlertTriangle className="w-3.5 h-3.5" />
              {error}
            </div>
          )}
        </motion.div>
      )}

      {/* Pipeline stages */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="glass rounded-2xl p-5"
      >
        <div className="flex items-center gap-2 mb-4">
          <span className="text-sm font-semibold">Pipeline Stages</span>
          <span className="text-[10px] text-secondary/50 font-mono">glyph state machine</span>
        </div>

        <div className="space-y-1">
          {STAGES.map((stage, i) => {
            const status = stageStatuses[stage.id] || 'idle'
            const sg = STATE_GLYPHS[status]
            const StageIcon = stage.icon
            const isLast = i === STAGES.length - 1

            return (
              <div key={stage.id}>
                <motion.div
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.1 + i * 0.04 }}
                  className={`flex items-center gap-4 py-3 px-3 rounded-xl transition-all ${status === 'active' ? 'glass-orange' :
                    status === 'complete' ? 'bg-success/5' :
                      status === 'error' ? 'bg-critical/5' : ''
                    }`}
                >
                  {/* Glyph state */}
                  <span className={`text-lg font-mono w-6 text-center ${sg.color} ${sg.pulse ? 'animate-pulse' : ''}`}>
                    {sg.glyph}
                  </span>

                  {/* Icon */}
                  <StageIcon className={`w-4 h-4 flex-shrink-0 ${status === 'complete' ? 'text-success' :
                    status === 'active' ? 'text-primary' :
                      status === 'error' ? 'text-critical' : 'text-secondary/40'
                    }`} />

                  {/* Label + desc */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm ${status === 'idle' ? 'text-secondary/60' : 'text-text'}`}>
                        {stage.label}
                      </span>
                      <span className="text-[10px] text-secondary/40 font-mono">{stage.glyph}</span>
                    </div>
                    <div className="text-[10px] text-secondary/50 mt-0.5">{stage.desc}</div>
                  </div>

                  {/* Status badge */}
                  <div className="flex items-center gap-1.5">
                    {status === 'active' && <Loader2 className="w-3 h-3 text-primary animate-spin" />}
                    {status === 'complete' && <Check className="w-3 h-3 text-success" />}
                    {status === 'error' && <X className="w-3 h-3 text-critical" />}
                    {status === 'complete' && pipelineState?.[`${stage.id}_url`] && (
                      <a
                        href={pipelineState[`${stage.id}_url`]}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[10px] text-primary hover:text-accent font-mono ml-1"
                      >
                        open ↗
                      </a>
                    )}
                  </div>
                </motion.div>

                {/* Connector line */}
                {!isLast && (
                  <div className="ml-6 pl-5 h-4 flex items-center">
                    <div className={`w-px h-full ${stageStatuses[stage.id] === 'complete' ? 'bg-success/30' : 'bg-white/5'
                      }`} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </motion.div>

      {/* Content preview */}
      {contentPreview && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="glass rounded-2xl p-5"
        >
          <div className="flex items-center gap-2 mb-3">
            <span className="text-sm font-semibold">Clipboard Content</span>
            <span className="text-[10px] text-secondary/50 font-mono">
              {pipelineState?.content_type} · {pipelineState?.content_hash?.slice(0, 16)}…
            </span>
            {fileId && (
              <button
                onClick={() => setShowDossier(true)}
                className="flex items-center gap-1.5 ml-auto px-3 py-1.5 rounded-lg text-[11px] bg-primary/10 text-primary hover:bg-primary/20 transition-all font-medium"
              >
                <FileSearch className="w-3.5 h-3.5" />
                View Intel Dossier
              </button>
            )}
          </div>
          <pre className="text-[11px] font-mono text-secondary bg-bg/50 rounded-xl p-3 max-h-40 overflow-y-auto thin-scrollbar whitespace-pre-wrap">
            {contentPreview.slice(0, 500)}
            {contentPreview.length > 500 && '\n…'}
          </pre>
        </motion.div>
      )}

      {/* Logs */}
      {logs.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass rounded-2xl p-5"
        >
          <div className="flex items-center gap-2 mb-3">
            <span className="text-sm font-semibold">Pipeline Logs</span>
            <span className="text-[10px] text-secondary/50 font-mono">{logs.length} entries</span>
          </div>
          <div className="space-y-1 max-h-48 overflow-y-auto thin-scrollbar">
            {logs.map((log, i) => (
              <div key={i} className="text-[11px] font-mono flex items-start gap-2">
                <span className="text-secondary/40 flex-shrink-0">{log.ts}</span>
                <span className={`flex-shrink-0 ${log.level === 'error' ? 'text-critical' :
                  log.level === 'ok' ? 'text-success' : 'text-primary'
                  }`}>
                  {log.glyph || '◉'}
                </span>
                <span className="text-secondary/60 flex-shrink-0 w-28 truncate">{log.stage}</span>
                <span className="text-text/80">{log.msg}</span>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Receipts */}
      {receipts.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="glass rounded-2xl p-5"
        >
          <div className="flex items-center gap-2 mb-3">
            <ShieldCheck className="w-4 h-4 text-success" />
            <span className="text-sm font-semibold">Receipt Chain</span>
            <span className="text-[10px] text-secondary/50 font-mono">SHA-256 linked</span>
          </div>
          <div className="space-y-2">
            {receipts.map((r, i) => (
              <div key={i} className="flex items-center gap-3 py-2 px-3 rounded-lg bg-white/3">
                <span className="text-success text-xs">◆</span>
                <span className="text-xs font-mono text-secondary flex-shrink-0">{r.stage}</span>
                <span className="text-[10px] font-mono text-secondary/40 flex-1 truncate">
                  {r.hash?.slice(0, 24)}…
                </span>
                <ChevronRight className="w-3 h-3 text-secondary/30" />
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Artifacts */}
      {isComplete && pipelineState && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="glass rounded-2xl p-5"
        >
          <div className="flex items-center gap-2 mb-4">
            <Store className="w-4 h-4 text-success" />
            <span className="text-sm font-semibold">Artifacts</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {pipelineState.github_url && (
              <ArtifactCard label="GitHub" url={pipelineState.github_url} icon={GitBranch} />
            )}
            {pipelineState.hf_space_url && (
              <ArtifactCard label="HuggingFace Space" url={pipelineState.hf_space_url} icon={Box} />
            )}
            {pipelineState.vercel_url && (
              <ArtifactCard label="Vercel" url={pipelineState.vercel_url} icon={Globe} />
            )}
            {pipelineState.dmg_path && (
              <ArtifactCard label="DMG" url={null} path={pipelineState.dmg_path} icon={Disc} />
            )}
          </div>
        </motion.div>
      )}
    </div>
  )
}

function ArtifactCard({ label, url, path, icon: Icon }) {
  return (
    <div className="flex items-center gap-3 py-3 px-4 rounded-xl glass">
      <Icon className="w-4 h-4 text-primary flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-medium">{label}</div>
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer"
            className="text-[10px] text-primary hover:text-accent font-mono truncate block">
            {url}
          </a>
        )}
        {path && (
          <div className="text-[10px] text-secondary font-mono truncate">{path}</div>
        )}
      </div>
      {url && <span className="text-[10px] text-secondary/40">↗</span>}
    </div>
  )
}
