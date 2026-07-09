import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowRight, Shield, Copy, Check, ExternalLink } from 'lucide-react'

const API_BASE = 'https://josephrw-llm-file-proxy.hf.space'

export default function Landing({ onLaunch }) {
  const [health, setHealth] = useState(null)
  const [files, setFiles] = useState([])
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const fetchReal = async () => {
      try {
        const hRes = await fetch(`${API_BASE}/health`)
        const h = await hRes.json()
        setHealth(h)
        const fRes = await fetch(`${API_BASE}/files`)
        const f = await fRes.json()
        setFiles(f.files || [])
      } catch (e) {
        setHealth({ status: 'error', error: e.message })
      }
    }
    fetchReal()
    const id = setInterval(fetchReal, 10000)
    return () => clearInterval(id)
  }, [])

  const copyUrl = () => {
    navigator.clipboard?.writeText(API_BASE)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const isLive = health?.status === 'ok'
  const fileCount = health?.files_registered ?? files.length

  return (
    <div className="relative h-screen w-screen overflow-y-auto no-scrollbar bg-bg">
      {/* Subtle aurora */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <motion.div
          className="absolute -top-1/4 -left-1/4 w-[60%] h-[60%] rounded-full blur-[140px]"
          style={{ background: 'radial-gradient(circle, rgba(255,138,0,0.08) 0%, transparent 70%)' }}
          animate={{ x: [0, 60, 0], y: [0, 30, 0] }}
          transition={{ duration: 20, repeat: Infinity, ease: 'easeInOut' }}
        />
        <div className="absolute inset-0 grid-bg opacity-10" />
      </div>

      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-6 py-12">
        {/* Logo */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-3 mb-12"
        >
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center glow-orange">
            <span className="text-bg font-black text-xl">J</span>
          </div>
          <span className="text-xl font-bold tracking-tight">Jorki</span>
        </motion.div>

        {/* Status badge */}
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="flex items-center gap-2 mb-8"
        >
          <span className={`w-2 h-2 rounded-full ${isLive ? 'bg-success animate-pulse' : 'bg-critical'}`} />
          <span className="text-xs font-mono uppercase tracking-wider">
            {isLive ? 'Live' : 'Connecting...'}
          </span>
        </motion.div>

        {/* Hero */}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="text-5xl md:text-6xl font-black tracking-tight text-center mb-4"
        >
          JORKI
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="text-lg text-secondary text-center mb-2"
        >
          The file server built for AI workflows.
        </motion.p>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="text-sm text-secondary/60 text-center mb-8 max-w-md"
        >
          Upload once. Share instantly. Query intelligently. Revoke completely.
        </motion.p>

        {/* Real measured state */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="glass rounded-2xl p-6 mb-8 w-full max-w-md"
        >
          <div className="flex items-center gap-2 mb-4">
            <Shield className="w-4 h-4 text-success" />
            <span className="text-xs uppercase tracking-wider text-secondary font-semibold">Measured State</span>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-secondary text-xs">Status</span>
              <span className={`font-mono text-xs ${isLive ? 'text-success' : 'text-critical'}`}>
                {isLive ? '● Live' : '● Error'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-secondary text-xs">Files</span>
              <span className="font-mono text-xs text-text">{fileCount} indexed</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-secondary text-xs">Version</span>
              <span className="font-mono text-xs text-text">{health?.version || '—'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-secondary text-xs">Storage</span>
              <span className="font-mono text-xs text-text">
                {health?.persistent_storage ? 'Persistent' : 'Ephemeral'}
              </span>
            </div>
          </div>
          {files.length > 0 && (
            <div className="mt-4 pt-4 border-t border-white/5 space-y-1.5">
              {files.slice(0, 3).map(f => (
                <div key={f.file_id} className="flex items-center justify-between text-[10px]">
                  <span className="text-secondary font-mono truncate">{f.filename}</span>
                  <span className="text-secondary/60 font-mono flex-shrink-0 ml-2">{f.size}</span>
                </div>
              ))}
            </div>
          )}
        </motion.div>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
          className="flex items-center gap-3 mb-12"
        >
          <button
            onClick={onLaunch}
            className="group flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-primary to-accent text-bg font-semibold glow-orange-strong hover:scale-105 transition-transform"
          >
            Launch Space
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </button>
          <button
            onClick={copyUrl}
            className="flex items-center gap-2 px-6 py-3 rounded-xl glass text-text font-semibold hover:glass-orange transition-all"
          >
            {copied ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
            {copied ? 'Copied' : 'Copy Demo URL'}
          </button>
        </motion.div>

        {/* Principles */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="flex flex-col items-center gap-2 mb-8"
        >
          {[
            'Index. Query. Retrieve. Verify. Revoke.',
            'Built for Hugging Face. Measured in receipts.',
          ].map((line, i) => (
            <p key={i} className="text-xs text-secondary/50 text-center font-mono">{line}</p>
          ))}
        </motion.div>

        {/* Footer */}
        <div className="flex items-center gap-4 text-[10px] text-secondary/40">
          <a
            href={API_BASE}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-secondary transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            {API_BASE}
          </a>
        </div>
      </div>
    </div>
  )
}
