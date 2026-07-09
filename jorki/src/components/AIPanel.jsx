import { useState } from 'react'
import { motion } from 'framer-motion'
import { Zap, Send, Sparkles, FileSearch, GitCompare, Languages, FileText, Tag, Search, Eye } from 'lucide-react'
import { aiQueries, mockAIModels } from '../data/mockData.js'

const queryIcons = {
  'Summarize': FileText,
  'Find duplicates': GitCompare,
  'Extract tables': FileSearch,
  'Generate metadata': Tag,
  'Translate': Languages,
  'Create captions': Sparkles,
  'Index for search': Search,
  'Compare versions': GitCompare,
  'Generate embeddings': Zap,
  'Explain contents': Eye,
}

export default function AIPanel() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([
    { role: 'system', content: 'AI Operations ready. Select a query type or ask a question about your files.' },
  ])

  const sendQuery = (query) => {
    setMessages(prev => [
      ...prev,
      { role: 'user', content: query },
      { role: 'system', content: `Processing: ${query}... Results will appear in the file index.`, pending: true },
    ])
    setTimeout(() => {
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1 ? { ...m, pending: false, content: `${query} complete. 3 matches found across indexed files.` } : m
      ))
    }, 1500)
  }

  return (
    <div className="p-6 h-full flex flex-col gap-4 overflow-hidden">
      {/* Model status */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl p-4 flex-shrink-0"
      >
        <div className="flex items-center gap-2 mb-3">
          <Zap className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">AI Operations</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {mockAIModels.map(m => (
            <div key={m.name} className="flex items-center justify-between glass rounded-xl px-3 py-2">
              <span className="text-xs font-medium">{m.name}</span>
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                <span className="text-[10px] text-success font-mono">{m.status}</span>
              </div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* Query buttons */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex-shrink-0"
      >
        <div className="text-[10px] uppercase tracking-wider text-secondary mb-2">Ask your file</div>
        <div className="flex flex-wrap gap-2">
          {aiQueries.map(q => {
            const Icon = queryIcons[q] || Sparkles
            return (
              <button
                key={q}
                onClick={() => sendQuery(q)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl glass hover:glass-orange text-xs text-secondary hover:text-primary transition-all"
              >
                <Icon className="w-3 h-3" />
                {q}
              </button>
            )
          })}
        </div>
      </motion.div>

      {/* Chat area */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass rounded-2xl p-4 flex-1 flex flex-col overflow-hidden"
      >
        <div className="flex-1 overflow-y-auto thin-scrollbar space-y-3 mb-3">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-xl px-3 py-2 text-xs ${
                msg.role === 'user'
                  ? 'glass-orange text-primary'
                  : 'glass text-secondary'
              }`}>
                {msg.pending && (
                  <span className="inline-flex gap-1 mr-1">
                    <span className="w-1 h-1 rounded-full bg-primary animate-pulse" />
                    <span className="w-1 h-1 rounded-full bg-primary animate-pulse" style={{ animationDelay: '0.2s' }} />
                    <span className="w-1 h-1 rounded-full bg-primary animate-pulse" style={{ animationDelay: '0.4s' }} />
                  </span>
                )}
                {msg.content}
              </div>
            </div>
          ))}
        </div>

        {/* Input */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && input.trim()) {
                sendQuery(input.trim())
                setInput('')
              }
            }}
            placeholder="Ask anything about your files..."
            className="flex-1 px-3 py-2 rounded-xl glass text-xs text-text placeholder-secondary/50 focus:outline-none focus:glass-orange transition-all"
          />
          <button
            onClick={() => { if (input.trim()) { sendQuery(input.trim()); setInput('') } }}
            className="w-9 h-9 rounded-xl glass-orange flex items-center justify-center text-primary hover:scale-105 transition-transform"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </motion.div>
    </div>
  )
}
