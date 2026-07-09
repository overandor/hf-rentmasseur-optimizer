import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileVideo, FileArchive, FileText, FileImage, Database,
  Copy, Share2, Eye, BarChart3, Link2, Trash2, Download,
} from 'lucide-react'
import { mockFiles } from '../data/mockData.js'

const iconMap = {
  video: FileVideo,
  archive: FileArchive,
  file: FileText,
  image: FileImage,
  database: Database,
}

const statusColors = {
  Shared: 'text-accent',
  Processing: 'text-warning',
  Ready: 'text-success',
  Downloaded: 'text-secondary',
}

export default function FileCards() {
  const [files] = useState(mockFiles)
  const [selected, setSelected] = useState(null)
  const [copied, setCopied] = useState(false)

  const copyUrl = (file) => {
    const url = `https://jorki.ai/f/${Math.random().toString(36).slice(2, 8).toUpperCase()}`
    navigator.clipboard?.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="p-6 h-full overflow-y-auto thin-scrollbar">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {files.map((file, i) => {
          const Icon = iconMap[file.icon] || FileText
          return (
            <motion.div
              key={file.name}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
              whileHover={{ y: -4, scale: 1.01 }}
              onHoverStart={() => setSelected(file.name)}
              onHoverEnd={() => setSelected(null)}
              className="glass rounded-2xl p-5 group cursor-pointer"
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl glass-orange flex items-center justify-center">
                    <Icon className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">{file.name}</div>
                    <div className="text-[10px] text-secondary">{file.size}</div>
                  </div>
                </div>
                <span className={`text-[10px] font-mono ${statusColors[file.status]}`}>
                  {file.status}
                </span>
              </div>

              {/* Stats */}
              <div className="flex items-center gap-4 mb-4 text-[10px] text-secondary">
                <span className="flex items-center gap-1">
                  <Download className="w-3 h-3" />
                  {file.downloads} downloads
                </span>
                <span className="flex items-center gap-1">
                  <Link2 className="w-3 h-3" />
                  {file.status === 'Shared' ? 'Public' : 'Private'}
                </span>
              </div>

              {/* Actions */}
              <AnimatePresence>
                {selected === file.name && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="flex items-center gap-2"
                  >
                    <button
                      onClick={() => copyUrl(file)}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl glass hover:glass-orange text-xs transition-all"
                    >
                      {copied ? <span className="text-success">Copied!</span> : (
                        <><Copy className="w-3 h-3" /> Copy URL</>
                      )}
                    </button>
                    <button className="flex items-center justify-center w-9 h-9 rounded-xl glass hover:glass-orange transition-all">
                      <Share2 className="w-3.5 h-3.5" />
                    </button>
                    <button className="flex items-center justify-center w-9 h-9 rounded-xl glass hover:glass-orange transition-all">
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                    <button className="flex items-center justify-center w-9 h-9 rounded-xl glass hover:glass-orange transition-all">
                      <BarChart3 className="w-3.5 h-3.5" />
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>

              {selected !== file.name && (
                <div className="flex items-center justify-between text-[10px] text-secondary/50">
                  <span>Hover for actions</span>
                  <span className="font-mono">jorki.ai/f/···</span>
                </div>
              )}
            </motion.div>
          )
        })}
      </div>

      {/* Upload zone */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
        className="mt-4 glass rounded-2xl p-8 flex flex-col items-center justify-center border-2 border-dashed border-white/10 hover:border-primary/30 transition-all cursor-pointer"
      >
        <FileArchive className="w-8 h-8 text-secondary/40 mb-2" />
        <span className="text-sm text-secondary">Drop files here to index and share</span>
      </motion.div>
    </div>
  )
}
