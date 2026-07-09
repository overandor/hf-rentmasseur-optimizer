import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { UploadCloud, CheckCircle2, FileVideo, FileArchive, FileText, FileImage, Database, Zap, ShieldCheck } from 'lucide-react'
import { useAnimatedNumber } from '../hooks/useUtils.js'

const fileIcons = {
  video: FileVideo,
  archive: FileArchive,
  file: FileText,
  image: FileImage,
  database: Database,
}

export default function UploadScreen() {
  const [dragging, setDragging] = useState(false)
  const [uploads, setUploads] = useState([
    { id: 1, name: 'movie.mov', size: '12.4 GB', progress: 84, speed: 1.82, status: 'uploading' },
  ])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const files = Array.from(e.dataTransfer?.files || [])
    if (files.length === 0) {
      const fakeFiles = [
        { name: 'dataset_' + Math.random().toString(36).slice(2, 8) + '.tar.gz', size: '4.2 GB' },
        { name: 'model_weights.bin', size: '8.1 GB' },
      ]
      fakeFiles.forEach((f, i) => {
        setUploads(prev => [...prev, {
          id: Date.now() + i,
          name: f.name,
          size: f.size,
          progress: 0,
          speed: 2.0 + Math.random() * 2,
          status: 'uploading',
        }])
      })
    }
  }, [])

  return (
    <div className="p-6 h-full flex flex-col gap-4 overflow-y-auto thin-scrollbar">
      {/* Drop zone */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className={`relative flex-shrink-0 rounded-3xl border-2 border-dashed transition-all cursor-pointer overflow-hidden ${
          dragging ? 'border-primary glass-orange glow-orange scale-[1.01]' : 'border-white/10 glass'
        }`}
        style={{ height: '280px' }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => setDragging(true)}
      >
        {/* Ripple background */}
        {dragging && (
          <>
            <motion.div
              className="absolute rounded-full border-2 border-primary/30"
              style={{ left: '50%', top: '50%', width: 100, height: 100 }}
              initial={{ scale: 0, x: '-50%', y: '-50%' }}
              animate={{ scale: 4, opacity: 0 }}
              transition={{ duration: 1.5, repeat: Infinity }}
            />
            <motion.div
              className="absolute rounded-full border-2 border-primary/20"
              style={{ left: '50%', top: '50%', width: 100, height: 100 }}
              initial={{ scale: 0, x: '-50%', y: '-50%' }}
              animate={{ scale: 6, opacity: 0 }}
              transition={{ duration: 1.5, delay: 0.3, repeat: Infinity }}
            />
          </>
        )}

        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
          <motion.div
            animate={dragging ? { scale: 1.2, y: -5 } : { scale: 1, y: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 20 }}
          >
            <UploadCloud className={`w-12 h-12 ${dragging ? 'text-primary' : 'text-secondary/50'}`} />
          </motion.div>
          <div className="text-center">
            <p className={`text-lg font-semibold ${dragging ? 'text-primary' : 'text-text'}`}>
              {dragging ? 'Release to upload' : 'Drop anything here'}
            </p>
            <p className="text-sm text-secondary mt-1">or click to browse</p>
          </div>
          <div className="flex items-center gap-4 text-[10px] text-secondary/60">
            <span className="flex items-center gap-1"><Zap className="w-3 h-3 text-primary" /> Instant start</span>
            <span className="flex items-center gap-1"><ShieldCheck className="w-3 h-3 text-success" /> Hash verified</span>
          </div>
        </div>
      </motion.div>

      {/* Active uploads */}
      <div className="flex-1 space-y-3">
        <AnimatePresence>
          {uploads.map(u => (
            <UploadCard key={u.id} upload={u} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}

function UploadCard({ upload }) {
  const [progress, setProgress] = useState(upload.progress)
  const animatedSpeed = useAnimatedNumber(upload.speed, 500)

  useState(() => {
    if (upload.status === 'uploading') {
      const id = setInterval(() => {
        setProgress(prev => {
          if (prev >= 100) {
            clearInterval(id)
            return 100
          }
          return prev + Math.random() * 4
        })
      }, 200)
      return () => clearInterval(id)
    }
  }, [])

  const remaining = ((100 - progress) / animatedSpeed * 10).toFixed(1)
  const isComplete = progress >= 100

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="glass rounded-2xl p-5"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <FileVideo className="w-5 h-5 text-primary" />
          <div>
            <div className="text-sm font-medium">{upload.name}</div>
            <div className="text-[10px] text-secondary">{upload.size}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isComplete ? (
            <span className="flex items-center gap-1.5 text-xs text-success">
              <CheckCircle2 className="w-4 h-4" /> Verified
            </span>
          ) : (
            <span className="text-xs text-secondary font-mono">{Math.round(progress)}%</span>
          )}
        </div>
      </div>

      <div className="h-2 rounded-full bg-white/5 overflow-hidden mb-3">
        <motion.div
          className="h-full bar-fill"
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.3 }}
        />
      </div>

      <div className="grid grid-cols-4 gap-3 text-[10px]">
        <div>
          <span className="block text-secondary/50 mb-0.5">Progress</span>
          <span className="text-text font-mono">{Math.round(progress)}%</span>
        </div>
        <div>
          <span className="block text-secondary/50 mb-0.5">Speed</span>
          <span className="text-text font-mono">{animatedSpeed.toFixed(2)} GB/s</span>
        </div>
        <div>
          <span className="block text-secondary/50 mb-0.5">Remaining</span>
          <span className="text-text font-mono">{isComplete ? 'Done' : remaining + 's'}</span>
        </div>
        <div>
          <span className="block text-secondary/50 mb-0.5">Hash</span>
          <span className={isComplete ? 'text-success' : 'text-warning'}>
            {isComplete ? 'Verified' : 'Verifying'}
          </span>
        </div>
      </div>
    </motion.div>
  )
}
