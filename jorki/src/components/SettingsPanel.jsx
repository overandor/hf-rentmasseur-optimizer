import { useState } from 'react'
import { motion } from 'framer-motion'
import { Settings, Shield, Zap, Bell, Palette, Key, Globe, Database } from 'lucide-react'

function Toggle({ label, desc, defaultOn = false }) {
  const [on, setOn] = useState(defaultOn)
  return (
    <div className="flex items-center justify-between py-3">
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-[10px] text-secondary">{desc}</div>
      </div>
      <button
        onClick={() => setOn(!on)}
        className={`relative w-10 h-6 rounded-full transition-all ${on ? 'bg-primary/80' : 'bg-white/10'}`}
      >
        <motion.div
          className="absolute top-0.5 w-5 h-5 rounded-full bg-text"
          animate={{ left: on ? '20px' : '2px' }}
          transition={{ type: 'spring', stiffness: 300, damping: 25 }}
        />
      </button>
    </div>
  )
}

export default function SettingsPanel() {
  const [theme, setTheme] = useState('graphite')

  return (
    <div className="p-6 h-full overflow-y-auto thin-scrollbar space-y-4 max-w-2xl">
      {/* Theme */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Palette className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Appearance</span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {['Graphite', 'Midnight', 'Amber'].map(t => (
            <button
              key={t}
              onClick={() => setTheme(t.toLowerCase())}
              className={`p-4 rounded-xl text-xs font-medium transition-all ${
                theme === t.toLowerCase() ? 'glass-orange text-primary' : 'glass text-secondary hover:text-text'
              }`}
            >
              <div className={`w-full h-12 rounded-lg mb-2 ${
                t === 'Graphite' ? 'bg-gradient-to-br from-bg to-surface' :
                t === 'Midnight' ? 'bg-gradient-to-br from-black to-surface' :
                'bg-gradient-to-br from-primary/30 to-surface'
              }`} />
              {t}
            </button>
          ))}
        </div>
      </motion.div>

      {/* Security */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-2">
          <Shield className="w-4 h-4 text-success" />
          <span className="text-sm font-semibold">Security</span>
        </div>
        <Toggle label="End-to-end encryption" desc="All transfers encrypted in transit and at rest" defaultOn={true} />
        <Toggle label="Hash verification" desc="SHA-256 integrity check on every upload" defaultOn={true} />
        <Toggle label="Auto-revoke expired links" desc="Automatically revoke share links after 7 days" defaultOn={true} />
        <Toggle label="IP allowlist" desc="Restrict access to specified IP ranges" defaultOn={false} />
      </motion.div>

      {/* Performance */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-2">
          <Zap className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Performance</span>
        </div>
        <Toggle label="Edge replication" desc="Replicate files to nearest edge nodes" defaultOn={true} />
        <Toggle label="Compression" desc="Compress files during transfer" defaultOn={true} />
        <Toggle label="Parallel transfers" desc="Allow multiple concurrent transfer streams" defaultOn={true} />
        <Toggle label="Predictive prefetch" desc="Pre-fetch likely requested chunks" defaultOn={false} />
      </motion.div>

      {/* Notifications */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-2">
          <Bell className="w-4 h-4 text-warning" />
          <span className="text-sm font-semibold">Notifications</span>
        </div>
        <Toggle label="Transfer complete" desc="Notify when a transfer finishes" defaultOn={true} />
        <Toggle label="Integrity alerts" desc="Notify on hash verification failures" defaultOn={true} />
        <Toggle label="Anomaly detection" desc="Alert on unusual activity patterns" defaultOn={false} />
      </motion.div>

      {/* API Keys */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <Key className="w-4 h-4 text-accent" />
          <span className="text-sm font-semibold">API Keys</span>
        </div>
        <div className="space-y-2">
          {['Production', 'Development', 'Analytics'].map(env => (
            <div key={env} className="flex items-center justify-between glass rounded-xl px-3 py-2">
              <div>
                <div className="text-xs font-medium">{env}</div>
                <div className="text-[10px] text-secondary font-mono">jorki_{'•'.repeat(20)}</div>
              </div>
              <button className="text-[10px] text-primary hover:text-accent transition-colors">Rotate</button>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  )
}
