import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText, Shield, Copy, Check, ChevronLeft, Layers, Search,
  Database, Hash, Activity, Code,
} from 'lucide-react'

const API_BASE = ''

export default function FileDetail({ fileId, onClear }) {
  const [files, setFiles] = useState([])
  const [selectedId, setSelectedId] = useState(fileId)
  const [meta, setMeta] = useState(null)
  const [summary, setSummary] = useState(null)
  const [capabilities, setCapabilities] = useState(null)
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [activeTab, setActiveTab] = useState('meta')

  // Fetch file list
  useEffect(() => {
    const fetchFiles = async () => {
      try {
        const res = await fetch(`${API_BASE}/files`)
        const data = await res.json()
        setFiles(data.files || [])
        if (!selectedId && data.files?.length > 0) {
          setSelectedId(data.files[0].file_id)
        }
      } catch {
        setFiles([])
      }
    }
    fetchFiles()
  }, [])

  // Update selectedId when fileId prop changes
  useEffect(() => {
    if (fileId) setSelectedId(fileId)
  }, [fileId])

  // Fetch detail data for selected file
  const fetchDetail = useCallback(async (id) => {
    if (!id) return
    setLoading(true)
    setMeta(null)
    setSummary(null)
    setCapabilities(null)
    setState(null)

    try {
      const [mRes, sRes, cRes, stRes] = await Promise.all([
        fetch(`${API_BASE}/meta/${id}`).then(r => r.json()).catch(() => null),
        fetch(`${API_BASE}/summary/${id}`).then(r => r.json()).catch(() => null),
        fetch(`${API_BASE}/capabilities/${id}`).then(r => r.json()).catch(() => null),
        fetch(`${API_BASE}/superpose/state/${id}`).then(r => r.json()).catch(() => null),
      ])
      setMeta(mRes)
      setSummary(sRes)
      setCapabilities(cRes)
      setState(stRes)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDetail(selectedId)
  }, [selectedId, fetchDetail])

  const copyUrl = () => {
    navigator.clipboard?.writeText(`${API_BASE}/meta/${selectedId}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const selectedFile = files.find(f => f.file_id === selectedId)
  const isLive = state?.session_status === 'live'

  return (
    <div className="p-6 h-full overflow-y-auto thin-scrollbar">
      {/* File selector */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {onClear && (
          <button
            onClick={onClear}
            className="flex items-center gap-1 text-xs text-secondary hover:text-text px-2 py-1.5 rounded-lg glass transition-all"
          >
            <ChevronLeft className="w-3 h-3" />
            Back
          </button>
        )}
        {files.map(f => (
          <button
            key={f.file_id}
            onClick={() => setSelectedId(f.file_id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all ${selectedId === f.file_id
                ? 'glass-orange text-primary'
                : 'glass text-secondary hover:text-text'
              }`}
          >
            {f.filename}
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <motion.div
            animate={{ opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 1.5, repeat: Infinity }}
            className="text-sm text-secondary font-mono"
          >
            Fetching file data...
          </motion.div>
        </div>
      )}

      {!loading && meta && (
        <>
          {/* File header */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass rounded-2xl p-5 mb-4"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl glass-orange flex items-center justify-center">
                  <FileText className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <div className="text-sm font-semibold">{meta.meta?.filename || selectedFile?.filename}</div>
                  <div className="text-[10px] text-secondary font-mono">{selectedId}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-mono ${isLive ? 'text-success' : 'text-critical'}`}>
                  {isLive ? '● LIVE' : '● OFFLINE'}
                </span>
                <button
                  onClick={copyUrl}
                  className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] glass hover:glass-orange transition-all"
                >
                  {copied ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                  {copied ? 'Copied' : 'Copy URL'}
                </button>
              </div>
            </div>

            {/* Real measured metadata grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                ['Size', meta.meta?.size_human || '—'],
                ['Lines', meta.meta?.total_lines || '—'],
                ['Format', meta.meta?.format || '—'],
                ['Chunks', meta.meta?.total_chunks || '—'],
                ['Words', meta.meta?.total_words || '—'],
                ['Chars', meta.meta?.total_chars || '—'],
                ['Entropy', meta.meta?.entropy || '—'],
                ['Merkle Root', meta.meta?.merkle_root?.slice(0, 12) + '...' || '—'],
              ].map(([label, value]) => (
                <div key={label}>
                  <div className="text-[10px] uppercase tracking-wider text-secondary mb-1">{label}</div>
                  <div className="text-sm font-mono tabular-nums">{value}</div>
                </div>
              ))}
            </div>

            {state && (
              <div className="mt-4 pt-4 border-t border-white/5 grid grid-cols-3 gap-4">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-secondary mb-1">Index Size</div>
                  <div className="text-sm font-mono">{state.compression_ratio || '—'}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-secondary mb-1">Queries</div>
                  <div className="text-sm font-mono tabular-nums">{state.total_queries || 0}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-secondary mb-1">Last Access</div>
                  <div className="text-sm font-mono">{state.last_access ? new Date(state.last_access * 1000).toLocaleTimeString() : 'Never'}</div>
                </div>
              </div>
            )}
          </motion.div>

          {/* Tabs */}
          <div className="flex items-center gap-1 mb-4">
            {[
              { id: 'meta', label: 'Meta', icon: FileText },
              { id: 'summary', label: 'Summary', icon: Activity },
              { id: 'capabilities', label: 'Capabilities', icon: Shield },
              { id: 'chunks', label: 'Chunks', icon: Layers },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs transition-all ${activeTab === tab.id
                    ? 'glass-orange text-primary font-medium'
                    : 'glass text-secondary hover:text-text'
                  }`}
              >
                <tab.icon className="w-3.5 h-3.5" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
            >
              {/* Meta tab */}
              {activeTab === 'meta' && meta && (
                <div className="glass rounded-2xl p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <Hash className="w-4 h-4 text-primary" />
                    <span className="text-sm font-semibold">Metadata</span>
                  </div>
                  <pre className="text-[11px] font-mono text-secondary leading-relaxed overflow-x-auto thin-scrollbar">
                    {JSON.stringify(meta, null, 2)}
                  </pre>
                </div>
              )}

              {/* Summary tab */}
              {activeTab === 'summary' && summary && (
                <div className="space-y-4">
                  {/* Semantic chunks */}
                  {summary.semantic_chunks && (
                    <div className="glass rounded-2xl p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <Layers className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold">Semantic Chunks ({summary.semantic_chunks.length})</span>
                      </div>
                      <div className="space-y-1.5 max-h-64 overflow-y-auto thin-scrollbar">
                        {summary.semantic_chunks.map(chunk => (
                          <div key={chunk.idx} className="flex items-center gap-3 py-1.5 px-2 rounded-lg hover:bg-white/5 text-[10px] font-mono">
                            <span className="text-primary w-6">#{chunk.idx}</span>
                            <span className="text-secondary w-20">{chunk.type}</span>
                            <span className="text-secondary/70">L{chunk.lines}</span>
                            <span className="text-secondary/50">{chunk.size}B</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Functions */}
                  {summary.functions && summary.functions.length > 0 && (
                    <div className="glass rounded-2xl p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <Code className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold">Functions ({summary.functions.length})</span>
                      </div>
                      <div className="space-y-1">
                        {summary.functions.map((fn, i) => (
                          <div key={i} className="flex items-center gap-3 py-1.5 px-2 rounded-lg hover:bg-white/5 text-[10px] font-mono">
                            <span className="text-secondary/50">L{fn.line}</span>
                            <span className="text-primary">{fn.symbol}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Top words */}
                  {summary.top_words && (
                    <div className="glass rounded-2xl p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <Search className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold">Top Words</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {summary.top_words.map((w, i) => (
                          <span key={i} className="px-2 py-1 rounded-lg glass text-[10px] font-mono">
                            {w.word} <span className="text-secondary/50">×{w.count}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Section headers */}
                  {summary.section_headers && summary.section_headers.length > 0 && (
                    <div className="glass rounded-2xl p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <Database className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold">Sections ({summary.section_headers.length})</span>
                      </div>
                      <div className="space-y-1">
                        {summary.section_headers.map((s, i) => (
                          <div key={i} className="text-[10px] font-mono text-secondary py-1 px-2 rounded hover:bg-white/5">
                            {s.header} <span className="text-secondary/40">×{s.count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Capabilities tab */}
              {activeTab === 'capabilities' && capabilities && (
                <div className="glass rounded-2xl p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <Shield className="w-4 h-4 text-primary" />
                    <span className="text-sm font-semibold">{capabilities.total} Capabilities</span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {capabilities.capabilities?.map(cap => (
                      <div
                        key={cap.id}
                        className={`flex items-center gap-2 py-2 px-3 rounded-xl text-xs ${cap.enabled ? 'glass text-text' : 'bg-white/3 text-secondary/40'
                          }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${cap.enabled ? 'bg-success' : 'bg-secondary/30'}`} />
                        <span className="font-mono">{cap.name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Chunks tab */}
              {activeTab === 'chunks' && summary?.semantic_chunks && (
                <ChunkViewer fileId={selectedId} chunks={summary.semantic_chunks} />
              )}
            </motion.div>
          </AnimatePresence>
        </>
      )}

      {!loading && !meta && (
        <div className="flex items-center justify-center py-12 text-secondary text-sm">
          {files.length === 0 ? 'No files indexed.' : 'Select a file to inspect.'}
        </div>
      )}
    </div>
  )
}

function ChunkViewer({ fileId, chunks }) {
  const [selectedChunk, setSelectedChunk] = useState(null)
  const [chunkData, setChunkData] = useState(null)
  const [loadingChunk, setLoadingChunk] = useState(false)

  const fetchChunk = async (idx) => {
    setSelectedChunk(idx)
    setLoadingChunk(true)
    setChunkData(null)
    try {
      const res = await fetch(`${API_BASE}/chunk/${fileId}/${idx}`)
      const data = await res.json()
      setChunkData(data)
    } catch {
      setChunkData({ error: 'Failed to fetch chunk' })
    } finally {
      setLoadingChunk(false)
    }
  }

  return (
    <div className="grid grid-cols-12 gap-4">
      {/* Chunk list */}
      <div className="col-span-12 md:col-span-4">
        <div className="glass rounded-2xl p-4">
          <div className="text-xs font-semibold mb-3">Chunks ({chunks.length})</div>
          <div className="space-y-1 max-h-96 overflow-y-auto thin-scrollbar">
            {chunks.map(chunk => (
              <button
                key={chunk.idx}
                onClick={() => fetchChunk(chunk.idx)}
                className={`w-full flex items-center gap-2 py-2 px-2 rounded-lg text-[10px] font-mono transition-all ${selectedChunk === chunk.idx
                    ? 'glass-orange text-primary'
                    : 'hover:bg-white/5 text-secondary'
                  }`}
              >
                <span className="text-primary w-6">#{chunk.idx}</span>
                <span className="w-16 text-left">{chunk.type}</span>
                <span className="text-secondary/50">L{chunk.lines}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chunk content */}
      <div className="col-span-12 md:col-span-8">
        <div className="glass rounded-2xl p-5 min-h-64">
          {loadingChunk && (
            <div className="flex items-center justify-center py-8">
              <motion.div
                animate={{ opacity: [0.3, 0.8, 0.3] }}
                transition={{ duration: 1.5, repeat: Infinity }}
                className="text-xs text-secondary font-mono"
              >
                Fetching chunk...
              </motion.div>
            </div>
          )}
          {!loadingChunk && !selectedChunk && (
            <div className="flex items-center justify-center py-8 text-secondary text-xs">
              Select a chunk to view its content.
            </div>
          )}
          {!loadingChunk && chunkData && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-semibold">Chunk #{selectedChunk}</span>
                {chunkData.error && <span className="text-[10px] text-critical">{chunkData.error}</span>}
              </div>
              <pre className="text-[10px] font-mono text-secondary leading-relaxed overflow-x-auto thin-scrollbar max-h-96">
                {chunkData.content || chunkData.chunk_content || chunkData.text || JSON.stringify(chunkData, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
