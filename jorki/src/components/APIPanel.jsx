import { useState } from 'react'
import { motion } from 'framer-motion'
import { Code, Copy, Terminal } from 'lucide-react'

const endpoints = [
  { method: 'POST', path: '/session/start', desc: 'Create a new file session' },
  { method: 'POST', path: '/session/stop', desc: 'Stop and cleanup a session' },
  { method: 'POST', path: '/index', desc: 'Index a file for AI access' },
  { method: 'GET', path: '/meta/{file_id}', desc: 'Get file metadata' },
  { method: 'GET', path: '/summary/{file_id}', desc: 'Get file summary' },
  { method: 'POST', path: '/search', desc: 'Search indexed file content' },
  { method: 'POST', path: '/sql', desc: 'SQL query on file index' },
  { method: 'GET', path: '/chunk/{file_id}/{idx}', desc: 'Retrieve a specific chunk' },
  { method: 'POST', path: '/revoke/{file_id}', desc: 'Revoke file access' },
  { method: 'GET', path: '/verify/{file_id}', desc: 'Verify file integrity' },
  { method: 'GET', path: '/capabilities/{file_id}', desc: 'List available capabilities' },
  { method: 'GET', path: '/health', desc: 'Health check' },
]

const codeExamples = {
  curl: `curl -X POST https://jorki.ai/index \\
  -H "Authorization: Bearer jorki_••••" \\
  -F "file=@dataset.zip"`,
  python: `import requests

r = requests.post("https://jorki.ai/index",
    headers={"Authorization": "Bearer jorki_••••"},
    files={"file": open("dataset.zip", "rb")}
)
file_id = r.json()["file_id"]
print(f"jorki://query/{file_id}")`,
  js: `const formData = new FormData();
formData.append('file', fileInput.files[0]);

const res = await fetch('https://jorki.ai/index', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer jorki_••••' },
  body: formData
});
const { file_id } = await res.json();`,
}

const methodColors = {
  GET: 'text-success bg-success/10',
  POST: 'text-primary bg-primary/10',
  DELETE: 'text-critical bg-critical/10',
}

export default function APIPanel() {
  const [lang, setLang] = useState('curl')
  const [copied, setCopied] = useState(false)

  const copyCode = () => {
    navigator.clipboard?.writeText(codeExamples[lang])
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="p-6 h-full overflow-y-auto thin-scrollbar space-y-4 max-w-3xl">
      {/* Code example */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold">Quick Start</span>
          </div>
          <div className="flex items-center gap-2">
            {Object.keys(codeExamples).map(l => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={`px-2 py-1 rounded-lg text-[10px] font-mono transition-all ${
                  lang === l ? 'glass-orange text-primary' : 'text-secondary hover:text-text'
                }`}
              >
                {l}
              </button>
            ))}
            <button
              onClick={copyCode}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] glass hover:glass-orange transition-all"
            >
              <Copy className="w-3 h-3" />
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>
        <pre className="p-4 text-[11px] font-mono text-text/80 leading-relaxed overflow-x-auto thin-scrollbar">
          {codeExamples[lang]}
        </pre>
      </motion.div>

      {/* Endpoints */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Code className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Endpoints</span>
        </div>
        <div className="space-y-1">
          {endpoints.map((ep, i) => (
            <motion.div
              key={ep.path}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.1 + i * 0.03 }}
              className="flex items-center gap-3 py-2 px-3 rounded-xl hover:bg-white/5 transition-all group cursor-pointer"
            >
              <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${methodColors[ep.method]}`}>
                {ep.method}
              </span>
              <span className="text-xs font-mono text-text flex-1">{ep.path}</span>
              <span className="text-[10px] text-secondary opacity-0 group-hover:opacity-100 transition-opacity">{ep.desc}</span>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* MCP config */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-sm font-semibold">MCP Configuration</span>
        </div>
        <pre className="text-[11px] font-mono text-secondary leading-relaxed">
{`{
  "mcpServers": {
    "jorki": {
      "url": "https://jorki.ai/mcp",
      "headers": {
        "Authorization": "Bearer jorki_••••"
      }
    }
  }
}`}
        </pre>
      </motion.div>
    </div>
  )
}
