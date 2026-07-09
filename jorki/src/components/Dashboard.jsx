import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, Shield, Activity, Copy, Check, Search, ArrowRight, UploadCloud, Loader2, X, Dna, BookOpen } from 'lucide-react'

const API_BASE = ''

export default function Dashboard({ setActivePanel, onSelectFile }) {
  const [health, setHealth] = useState(null)
  const [files, setFiles] = useState([])
  const [states, setStates] = useState({})
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(null)
  const [uploadResult, setUploadResult] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  const fetchAll = useCallback(async () => {
    try {
      const [hRes, fRes] = await Promise.all([
        fetch(`${API_BASE}/health`),
        fetch(`${API_BASE}/files`),
      ])
      const h = await hRes.json()
      const f = await fRes.json()
      setHealth(h)
      const fileList = f.files || []
      setFiles(fileList)

      // Fetch superposition state for each file
      const statePromises = fileList.map(async (file) => {
        try {
          const sRes = await fetch(`${API_BASE}/superpose/state/${file.file_id}`)
          return [file.file_id, await sRes.json()]
        } catch {
          return [file.file_id, { error: true }]
        }
      })
      const stateEntries = await Promise.all(statePromises)
      setStates(Object.fromEntries(stateEntries))
    } catch {
      setHealth({ status: 'error' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const id = setInterval(fetchAll, 15000)
    return () => clearInterval(id)
  }, [fetchAll])

  const copyUrl = (fileId) => {
    navigator.clipboard?.writeText(`${API_BASE}/meta/${fileId}`)
    setCopied(fileId)
    setTimeout(() => setCopied(null), 2000)
  }

  const handleUpload = useCallback(async (file) => {
    setUploading(true)
    setUploadProgress({ name: file.name, size: (file.size / 1024).toFixed(1) })
    setUploadResult(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch(`${API_BASE}/index`, { method: 'POST', body: fd })
      const data = await res.json()
      if (data.error) {
        setUploadResult({ error: data.error })
      } else {
        setUploadResult({ success: true, file_id: data.file_id, filename: data.filename, chunks: data.total_chunks, lines: data.total_lines })
        fetchAll()
      }
    } catch (e) {
      setUploadResult({ error: e.message })
    } finally {
      setUploading(false)
    }
  }, [fetchAll])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(file)
  }, [handleUpload])

  const handleFileSelect = useCallback((e) => {
    const file = e.target.files[0]
    if (file) handleUpload(file)
  }, [handleUpload])

  const isLive = health?.status === 'ok'

  // Compute real aggregate stats
  const totalQueries = Object.values(states).reduce((sum, s) => sum + (s?.total_queries || 0), 0)
  const totalIndexBytes = Object.values(states).reduce((sum, s) => sum + (s?.index_size_bytes || 0), 0)
  const liveCount = Object.values(states).filter(s => s?.session_status === 'live').length
  const indexKB = (totalIndexBytes / 1024).toFixed(1)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <motion.div
          animate={{ opacity: [0.3, 0.8, 0.3] }}
          transition={{ duration: 1.5, repeat: Infinity }}
          className="text-sm text-secondary font-mono"
        >
          Connecting to Space...
        </motion.div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4 h-full overflow-y-auto thin-scrollbar">
      {/* Real status banner */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isLive ? 'bg-success animate-pulse' : 'bg-critical'}`} />
            <span className="text-sm font-semibold">Space Status</span>
          </div>
          <span className={`text-xs font-mono ${isLive ? 'text-success' : 'text-critical'}`}>
            {isLive ? '● VERIFIED' : '● ERROR'}
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-secondary mb-1">Files</div>
            <div className="text-xl font-bold tabular-nums">{files.length} indexed</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-secondary mb-1">Live Sessions</div>
            <div className="text-xl font-bold tabular-nums text-success">{liveCount}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-secondary mb-1">Queries Served</div>
            <div className="text-xl font-bold tabular-nums">{totalQueries}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-secondary mb-1">Index Size</div>
            <div className="text-xl font-bold tabular-nums">{indexKB} KB</div>
          </div>
        </div>
      </motion.div>

      {/* Upload zone */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="glass rounded-2xl p-5"
      >
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => !uploading && fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-6 text-center transition-all cursor-pointer ${dragOver ? 'border-primary bg-primary/5' : 'border-white/10 hover:border-white/20 hover:bg-white/3'
            }`}
        >
          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileSelect} />
          {uploading ? (
            <div className="flex flex-col items-center gap-3">
              <Loader2 className="w-6 h-6 text-primary animate-spin" />
              <div className="text-sm text-secondary">
                Indexing <span className="text-text font-mono">{uploadProgress?.name}</span> ({uploadProgress?.size} KB)
              </div>
              <div className="text-[10px] text-secondary/60 font-mono">Computing Merkle root · chunking · symbol extraction...</div>
            </div>
          ) : uploadResult ? (
            <div className="flex flex-col items-center gap-2">
              {uploadResult.error ? (
                <>
                  <X className="w-6 h-6 text-critical" />
                  <div className="text-sm text-critical">{uploadResult.error}</div>
                </>
              ) : (
                <>
                  <Check className="w-6 h-6 text-success" />
                  <div className="text-sm text-success">
                    Indexed: <span className="font-mono">{uploadResult.filename}</span>
                  </div>
                  <div className="text-[10px] text-secondary font-mono">
                    {uploadResult.file_id} · {uploadResult.chunks} chunks · {uploadResult.lines} lines
                  </div>
                </>
              )}
              <button
                onClick={(e) => { e.stopPropagation(); setUploadResult(null) }}
                className="text-[10px] text-secondary/60 hover:text-text mt-1"
              >
                Upload another
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <UploadCloud className={`w-6 h-6 ${dragOver ? 'text-primary' : 'text-secondary'}`} />
              <div className="text-sm text-secondary">
                Drop a file to index, or <span className="text-primary underline">browse</span>
              </div>
              <div className="text-[10px] text-secondary/50 font-mono">SHA-256 · Merkle root · Semantic chunks · Symbol table</div>
            </div>
          )}
        </div>
      </motion.div>

      {/* Real file list */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="glass rounded-2xl p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold">Indexed Files</span>
          </div>
          <button
            onClick={() => setActivePanel('query')}
            className="flex items-center gap-1 text-xs text-secondary hover:text-primary transition-colors"
          >
            <Search className="w-3 h-3" />
            Query
          </button>
        </div>

        {files.length === 0 ? (
          <div className="text-center py-8 text-secondary text-sm">
            No files indexed. Drop a file above to get started.
          </div>
        ) : (
          <div className="space-y-2">
            {files.map((file, i) => {
              const state = states[file.file_id]
              const isFileLive = state?.session_status === 'live'
              const queries = state?.total_queries || 0
              const idxSize = state?.index_size_bytes ? `${(state.index_size_bytes / 1024).toFixed(1)} KB` : '—'
              const origSize = state?.original_size || file.size

              return (
                <motion.div
                  key={file.file_id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.1 + i * 0.05 }}
                  className="flex items-center gap-4 py-3 px-3 rounded-xl hover:bg-white/5 transition-all group cursor-pointer"
                  onClick={() => onSelectFile(file.file_id)}
                >
                  <span className={`w-2 h-2 rounded-full flex-shrink-0 ${isFileLive ? 'bg-success animate-pulse' : 'bg-secondary'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{file.filename}</span>
                      <span className="text-[10px] text-secondary font-mono">{file.file_id}</span>
                    </div>
                    <div className="text-[10px] text-secondary mt-0.5">
                      {origSize} → {idxSize} index · {queries} queries
                    </div>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); copyUrl(file.file_id) }}
                    className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] glass hover:glass-orange transition-all opacity-0 group-hover:opacity-100"
                  >
                    {copied === file.file_id ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                    {copied === file.file_id ? 'Copied' : 'Copy URL'}
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); onSelectFile(file.file_id); setActivePanel('intel') }}
                    className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] glass hover:glass-orange transition-all opacity-0 group-hover:opacity-100"
                  >
                    <Dna className="w-3 h-3" />
                    Intel
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); onSelectFile(file.file_id); setActivePanel('dossier') }}
                    className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] glass hover:glass-orange transition-all opacity-0 group-hover:opacity-100"
                  >
                    <FileText className="w-3 h-3" />
                    Dossier
                  </button>
                  <ArrowRight className="w-3 h-3 text-secondary/40 group-hover:text-primary transition-colors" />
                </motion.div>
              )
            })}
          </div>
        )}
      </motion.div>

      {/* Real endpoints reference */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass rounded-2xl p-5"
      >
        <div className="flex items-center gap-2 mb-3">
          <Activity className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Live Endpoints</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-[10px] font-mono">
          {[
            ['GET', '/health'],
            ['GET', '/files'],
            ['GET', '/meta/{id}'],
            ['GET', '/summary/{id}'],
            ['GET', '/dna/{id}'],
            ['GET', '/kpi/{id}'],
            ['GET', '/kpi/{id}/gif'],
            ['GET', '/ml/{id}'],
            ['GET', '/profile/{id}'],
            ['GET', '/valuation/{id}'],
            ['GET', '/resume/{id}'],
            ['GET', '/video/{id}'],
            ['GET', '/formulas'],
            ['POST', '/reindex/{id}'],
            ['POST', '/password/{id}'],
            ['GET', '/password/{id}/status'],
            ['POST', '/password/{id}/verify'],
          ].map(([method, path]) => (
            <div key={path} className="flex items-center gap-2 py-1.5 px-2 rounded-lg bg-white/3">
              <span className={method === 'GET' ? 'text-success' : 'text-primary'}>{method}</span>
              <span className="text-secondary truncate">{path}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  )
}
