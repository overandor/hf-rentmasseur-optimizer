import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, Database, Terminal, FileText, Loader2, ChevronRight } from 'lucide-react'

const API_BASE = ''

export default function QueryPanel() {
  const [files, setFiles] = useState([])
  const [selectedFile, setSelectedFile] = useState(null)
  const [mode, setMode] = useState('search')
  const [searchQuery, setSearchQuery] = useState('')
  const [sqlQuery, setSqlQuery] = useState('SELECT * FROM data LIMIT 10')
  const [chunkIdx, setChunkIdx] = useState(0)
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchFiles = async () => {
      try {
        const res = await fetch(`${API_BASE}/files`)
        const data = await res.json()
        setFiles(data.files || [])
        if (data.files?.length > 0) setSelectedFile(data.files[0].file_id)
      } catch {
        setFiles([])
      }
    }
    fetchFiles()
  }, [])

  const execute = useCallback(async () => {
    if (!selectedFile) return
    setLoading(true)
    setError(null)
    setResults(null)

    try {
      let res
      if (mode === 'search') {
        res = await fetch(`${API_BASE}/search/${selectedFile}?q=${encodeURIComponent(searchQuery)}`)
      } else if (mode === 'sql') {
        res = await fetch(`${API_BASE}/query/sql/${selectedFile}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sql: sqlQuery }),
        })
      } else if (mode === 'chunk') {
        res = await fetch(`${API_BASE}/chunk/${selectedFile}/${chunkIdx}`)
      }
      const data = await res.json()
      setResults(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [selectedFile, mode, searchQuery, sqlQuery, chunkIdx])

  const modes = [
    { id: 'search', label: 'Search', icon: Search },
    { id: 'sql', label: 'SQL', icon: Database },
    { id: 'chunk', label: 'Chunk', icon: FileText },
  ]

  return (
    <div className="p-6 h-full overflow-y-auto thin-scrollbar space-y-4">
      {/* File selector */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl p-4"
      >
        <div className="flex items-center gap-2 mb-3">
          <FileText className="w-4 h-4 text-primary" />
          <span className="text-xs font-semibold">Target File</span>
        </div>
        {files.length === 0 ? (
          <div className="text-xs text-secondary">No files indexed.</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {files.map(f => (
              <button
                key={f.file_id}
                onClick={() => setSelectedFile(f.file_id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all ${selectedFile === f.file_id
                    ? 'glass-orange text-primary'
                    : 'glass text-secondary hover:text-text'
                  }`}
              >
                {f.filename}
              </button>
            ))}
          </div>
        )}
      </motion.div>

      {/* Mode selector */}
      <div className="flex items-center gap-1">
        {modes.map(m => (
          <button
            key={m.id}
            onClick={() => { setMode(m.id); setResults(null); setError(null) }}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs transition-all ${mode === m.id
                ? 'glass-orange text-primary font-medium'
                : 'glass text-secondary hover:text-text'
              }`}
          >
            <m.icon className="w-3.5 h-3.5" />
            {m.label}
          </button>
        ))}
      </div>

      {/* Query input */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="glass rounded-2xl p-5"
      >
        {mode === 'search' && (
          <div className="flex items-center gap-2">
            <Search className="w-4 h-4 text-secondary flex-shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && execute()}
              placeholder="Search file content..."
              className="flex-1 bg-transparent text-sm text-text placeholder-secondary/50 focus:outline-none"
            />
            <button
              onClick={execute}
              disabled={!selectedFile || !searchQuery || loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs glass-orange text-primary disabled:opacity-30 transition-all"
            >
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <ChevronRight className="w-3 h-3" />}
              Run
            </button>
          </div>
        )}

        {mode === 'sql' && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-secondary flex-shrink-0" />
              <span className="text-xs text-secondary font-mono">SQL Query</span>
            </div>
            <textarea
              value={sqlQuery}
              onChange={e => setSqlQuery(e.target.value)}
              rows={4}
              className="w-full bg-white/3 rounded-xl p-3 text-xs font-mono text-text placeholder-secondary/50 focus:outline-none focus:glass-orange resize-none thin-scrollbar"
              placeholder="SELECT * FROM data LIMIT 10"
            />
            <button
              onClick={execute}
              disabled={!selectedFile || loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs glass-orange text-primary disabled:opacity-30 transition-all"
            >
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Database className="w-3 h-3" />}
              Execute SQL
            </button>
          </div>
        )}

        {mode === 'chunk' && (
          <div className="flex items-center gap-3">
            <FileText className="w-4 h-4 text-secondary flex-shrink-0" />
            <span className="text-xs text-secondary">Chunk Index:</span>
            <input
              type="number"
              value={chunkIdx}
              onChange={e => setChunkIdx(parseInt(e.target.value) || 0)}
              min="0"
              className="w-20 bg-white/3 rounded-lg px-3 py-1.5 text-xs font-mono text-text focus:outline-none focus:glass-orange"
            />
            <button
              onClick={execute}
              disabled={!selectedFile || loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs glass-orange text-primary disabled:opacity-30 transition-all"
            >
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <ChevronRight className="w-3 h-3" />}
              Fetch
            </button>
          </div>
        )}
      </motion.div>

      {/* Results */}
      <AnimatePresence mode="wait">
        {(results || error || loading) && (
          <motion.div
            key={mode + (results ? 'has-results' : 'no-results')}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="glass rounded-2xl p-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs font-semibold">Results</span>
              {results && (
                <span className="text-[10px] text-secondary font-mono">
                  {mode === 'search' && `${results.results?.length || 0} matches`}
                  {mode === 'sql' && `${results.rows?.length || 0} rows`}
                  {mode === 'chunk' && `chunk #${chunkIdx}`}
                </span>
              )}
            </div>

            {loading && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-4 h-4 text-primary animate-spin" />
                <span className="ml-2 text-xs text-secondary font-mono">Executing...</span>
              </div>
            )}

            {error && (
              <div className="text-xs text-critical font-mono py-4">
                Error: {error}
              </div>
            )}

            {!loading && results && (
              <div className="space-y-2">
                {/* Search results */}
                {mode === 'search' && results.results && results.results.length > 0 && (
                  <div className="space-y-1.5 max-h-96 overflow-y-auto thin-scrollbar">
                    {results.results.map((r, i) => (
                      <div key={i} className="py-2 px-3 rounded-lg bg-white/3 text-[11px] font-mono">
                        <div className="text-secondary/50 mb-1">Line {r.line || r.line_number || i}</div>
                        <div className="text-text">{r.line || r.text || r.content || JSON.stringify(r)}</div>
                      </div>
                    ))}
                  </div>
                )}
                {mode === 'search' && results.results?.length === 0 && (
                  <div className="text-xs text-secondary py-4">No matches found.</div>
                )}

                {/* SQL results */}
                {mode === 'sql' && results.rows && results.rows.length > 0 && (
                  <div className="overflow-x-auto thin-scrollbar">
                    <table className="w-full text-[10px] font-mono">
                      <thead>
                        <tr className="border-b border-white/10">
                          {Object.keys(results.rows[0]).map(col => (
                            <th key={col} className="text-left py-1.5 px-2 text-primary">{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {results.rows.map((row, i) => (
                          <tr key={i} className="border-b border-white/3 hover:bg-white/3">
                            {Object.values(row).map((val, j) => (
                              <td key={j} className="py-1.5 px-2 text-secondary">{String(val)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {mode === 'sql' && results.rows?.length === 0 && (
                  <div className="text-xs text-secondary py-4">Query returned 0 rows.</div>
                )}

                {/* Chunk result */}
                {mode === 'chunk' && (
                  <pre className="text-[10px] font-mono text-secondary leading-relaxed overflow-x-auto thin-scrollbar max-h-96 whitespace-pre-wrap">
                    {results.content || results.chunk_content || results.text || JSON.stringify(results, null, 2)}
                  </pre>
                )}

                {/* Raw JSON fallback */}
                {mode === 'search' && !results.results && (
                  <pre className="text-[10px] font-mono text-secondary leading-relaxed overflow-x-auto thin-scrollbar">
                    {JSON.stringify(results, null, 2)}
                  </pre>
                )}
                {mode === 'sql' && !results.rows && (
                  <pre className="text-[10px] font-mono text-secondary leading-relaxed overflow-x-auto thin-scrollbar">
                    {JSON.stringify(results, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
