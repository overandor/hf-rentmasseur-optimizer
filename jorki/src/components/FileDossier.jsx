import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText, Dna, DollarSign, Scale, Brain, TrendingUp,
  AlertTriangle, Lightbulb, Loader2, FileCode, Hash,
  ChevronDown, ChevronRight, Copy, Check, Eye, Code, Sparkles,
} from 'lucide-react'

const API_BASE = ''

const GRADE_COLORS = {
  A: 'text-success', B: 'text-success', C: 'text-warning',
  D: 'text-critical', F: 'text-critical',
}

const RISK_COLORS = {
  low: 'text-success', medium: 'text-warning', high: 'text-critical',
}

const PRIORITY_COLORS = {
  critical: 'text-critical bg-critical/10',
  high: 'text-warning bg-warning/10',
  medium: 'text-primary bg-primary/10',
  low: 'text-secondary bg-white/5',
  info: 'text-secondary bg-white/3',
}

const PRIORITY_GLYPHS = {
  critical: '⟁', high: '▲', medium: '◆', low: '◇', info: '◌',
}

export default function FileDossier({ fileId, onClose }) {
  const [dossier, setDossier] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [viewMode, setViewMode] = useState('visual')
  const [asciiDossier, setAsciiDossier] = useState('')
  const [expandedSections, setExpandedSections] = useState({})
  const [copied, setCopied] = useState(false)

  const fetchDossier = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/resume/${fileId}`)
      const data = await res.json()
      if (data.error) {
        setError(data.error)
      } else {
        setDossier(data.resume)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [fileId])

  const fetchAscii = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/resume/${fileId}?format=text`)
      const text = await res.text()
      setAsciiDossier(text)
    } catch {
      // ignore
    }
  }, [fileId])

  useEffect(() => { fetchDossier() }, [fetchDossier])
  useEffect(() => { if (viewMode === 'ascii' && !asciiDossier) fetchAscii() }, [viewMode, asciiDossier, fetchAscii])

  const toggleSection = (key) => {
    setExpandedSections(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const copyDossier = () => {
    if (asciiDossier) {
      navigator.clipboard?.writeText(asciiDossier)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 text-primary animate-spin" />
          <div className="text-sm text-secondary font-mono">
            Compiling dossier · profile · valuation · ML · KPIs · DNA…
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="flex flex-col items-center gap-3">
          <AlertTriangle className="w-6 h-6 text-critical" />
          <div className="text-sm text-critical">{error}</div>
        </div>
      </div>
    )
  }

  if (!dossier) return null

  const r = dossier
  const id = r.identity || {}
  const dna = r.structural_dna || {}
  const kpi = r.kpi_summary || {}
  const fin = r.financial_profile || {}
  const legal = r.legal_profile || {}
  const ml = r.ml_insights || {}
  const val = r.valuation_summary || {}
  const risk = r.risk_assessment || {}
  const recs = r.recommendations || []
  const llmFacts = r.llm_facts || []
  const header = r.header || {}

  return (
    <div className="p-6 space-y-4 h-full overflow-y-auto thin-scrollbar">
      {/* Header bar */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-2xl p-5"
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center glow-orange">
              <FileText className="w-4 h-4 text-bg" />
            </div>
            <div>
              <div className="text-sm font-bold">{header.title || id.name || 'Unknown'}</div>
              <div className="text-[10px] text-secondary font-mono">
                {header.file_id || fileId} · v{header.dossier_version || '1.0'}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 p-1 rounded-lg bg-white/5">
              <button
                onClick={() => setViewMode('visual')}
                className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono transition-all ${viewMode === 'visual' ? 'glass-orange text-primary' : 'text-secondary hover:text-text'
                  }`}
              >
                <Eye className="w-3 h-3" /> VISUAL
              </button>
              <button
                onClick={() => setViewMode('ascii')}
                className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono transition-all ${viewMode === 'ascii' ? 'glass-orange text-primary' : 'text-secondary hover:text-text'
                  }`}
              >
                <Code className="w-3 h-3" /> DOSSIER
              </button>
            </div>
            {onClose && (
              <button onClick={onClose} className="text-[10px] text-secondary/60 hover:text-text px-2 py-1">✕</button>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 text-[10px] font-mono text-secondary/60">
          <span className="flex items-center gap-1">
            <Hash className="w-3 h-3" />
            {header.merkle_root?.slice(0, 24) || id.merkle_prefix || '—'}…
          </span>
          <span>│</span>
          <span>{id.primary_purpose || 'unknown'}</span>
          {id.all_purposes?.length > 1 && (
            <span className="text-secondary/40">+{id.all_purposes.length - 1} more</span>
          )}
        </div>
      </motion.div>

      <AnimatePresence mode="wait">
        {viewMode === 'ascii' ? (
          <motion.div
            key="ascii"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="glass rounded-2xl p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold">Declassified Intelligence Report</span>
              <button
                onClick={copyDossier}
                className="flex items-center gap-1 text-[10px] text-secondary hover:text-primary transition-colors"
              >
                {copied ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
            <pre className="text-[10px] font-mono text-text/80 bg-bg/60 rounded-xl p-4 overflow-x-auto whitespace-pre leading-tight">
              {asciiDossier || 'Loading…'}
            </pre>
          </motion.div>
        ) : (
          <motion.div
            key="visual"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            {/* Identity + DNA row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <DossierSection icon={FileCode} glyph="◉" title="Identity"
                expanded={expandedSections.identity !== false}
                onToggle={() => toggleSection('identity')}>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <StatRow label="Species" value={id.species} mono />
                  <StatRow label="Size" value={id.size} mono />
                  <StatRow label="Lines" value={id.lines} mono />
                  <StatRow label="Words" value={id.words} mono />
                  <StatRow label="Chunks" value={id.chunks} mono />
                  <StatRow label="Symbols" value={id.symbols} mono />
                  <StatRow label="Vocabulary" value={id.vocabulary} mono />
                  <StatRow label="DNA Seq" value={id.dna_sequence ? `${id.dna_sequence}…` : '—'} mono />
                </div>
                {id.all_purposes?.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-white/5">
                    <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">Detected Purposes</div>
                    <div className="flex flex-wrap gap-1.5">
                      {id.all_purposes.map((p, i) => (
                        <span key={i} className="text-[10px] px-2 py-1 rounded-lg glass-orange text-primary font-mono">{p}</span>
                      ))}
                    </div>
                  </div>
                )}
              </DossierSection>

              <DossierSection icon={Dna} glyph="◇" title="Structural DNA"
                expanded={expandedSections.dna !== false}
                onToggle={() => toggleSection('dna')}>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-secondary">Complexity</span>
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div className="h-full bar-fill" style={{ width: `${Math.min(dna.complexity_score || 0, 100)}%` }} />
                      </div>
                      <span className="text-xs font-mono text-primary">{(dna.complexity_score || 0).toFixed(1)}</span>
                    </div>
                  </div>
                  <StatRow label="Interpretation" value={dna.interpretation} />
                  <StatRow label="Genome Size" value={`${dna.genome_size || 0} bytes`} mono />
                  {dna.genes && Object.keys(dna.genes).length > 0 && (
                    <div className="pt-2 border-t border-white/5">
                      <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">Genes</div>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(dna.genes).slice(0, 12).map(([k, v]) => (
                          <span key={k} className="text-[10px] px-2 py-1 rounded-lg bg-white/5 text-secondary font-mono">
                            {k}: {String(v).slice(0, 20)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </DossierSection>
            </div>

            {/* Valuation */}
            <DossierSection icon={DollarSign} glyph="$" title="Valuation"
              expanded={expandedSections.valuation !== false}
              onToggle={() => toggleSection('valuation')}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <ValueCard label="Build Cost" value={val.build_cost_usd} glyph="⌁" />
                <ValueCard label="Replacement" value={val.replacement_cost_usd} glyph="↻" />
                <ValueCard label="Depreciated" value={val.depreciated_value_usd} glyph="▼" sub={`${val.remaining_value_pct}% remaining`} />
                <ValueCard label="Insurance" value={val.insurance_value_usd} glyph="◆" />
              </div>
              <div className="mt-4 grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                <div className="glass rounded-xl p-3">
                  <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-1">Prod Readiness</div>
                  <div className="flex items-center gap-2">
                    <span className={`text-lg font-bold ${GRADE_COLORS[val.production_readiness_grade] || 'text-secondary'}`}>
                      {val.production_readiness_grade || 'F'}
                    </span>
                    <span className="text-secondary font-mono">{val.production_readiness_score}/100</span>
                  </div>
                  <div className="text-[10px] text-secondary/60 mt-1">{val.distance_to_prod}</div>
                </div>
                <div className="glass rounded-xl p-3">
                  <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-1">Time to Rebuild</div>
                  <div className="text-sm font-mono">{val.time_to_rebuild_days} days</div>
                  <div className="text-[10px] text-secondary/60 mt-1 capitalize">{val.difficulty}</div>
                </div>
                <div className="glass rounded-xl p-3">
                  <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-1">Depreciation</div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-mono">{val.depreciation_score}/100</span>
                  </div>
                  <div className="text-[10px] text-secondary/60 mt-1">{val.remaining_value_pct}% value remaining</div>
                </div>
              </div>
              {val.blocking_issues?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {val.blocking_issues.map((issue, i) => (
                    <span key={i} className="text-[10px] px-2 py-1 rounded-lg bg-critical/10 text-critical font-mono">
                      ⟁ {issue}
                    </span>
                  ))}
                </div>
              )}
            </DossierSection>

            {/* Financial + Legal row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <DossierSection icon={TrendingUp} glyph="▲" title="Financial Profile"
                expanded={expandedSections.financial !== false}
                onToggle={() => toggleSection('financial')}>
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <GradeCard label="Collateral" grade={fin.collateral_grade} score={fin.collateral_score} />
                    <GradeCard label="Liquidity" grade={fin.liquidity_grade} score={fin.liquidity_score} />
                  </div>
                  <StatRow label="Time to Liquidate" value={fin.time_to_liquidate} />
                  <StatRow label="Monetary Refs" value={fin.monetary_references} mono />
                  {fin.has_financial_statements && (
                    <span className="text-[10px] px-2 py-1 rounded-lg bg-success/10 text-success font-mono">◆ Financial statements detected</span>
                  )}
                  {fin.standards?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {fin.standards.map(s => (
                        <span key={s} className="text-[10px] px-2 py-1 rounded-lg bg-white/5 text-secondary font-mono uppercase">{s}</span>
                      ))}
                    </div>
                  )}
                  {fin.finance_metrics && Object.keys(fin.finance_metrics).length > 0 && (
                    <div className="pt-2 border-t border-white/5">
                      <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">Metrics Detected</div>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(fin.finance_metrics).map(([k, v]) => (
                          <span key={k} className="text-[10px] px-2 py-1 rounded-lg bg-white/5 text-secondary font-mono">
                            {k} ×{v}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </DossierSection>

              <DossierSection icon={Scale} glyph="§" title="Legal Profile"
                expanded={expandedSections.legal !== false}
                onToggle={() => toggleSection('legal')}>
                <div className="space-y-3">
                  {legal.has_contract_language && (
                    <span className="text-[10px] px-2 py-1 rounded-lg bg-warning/10 text-warning font-mono">⚠ Contract language detected</span>
                  )}
                  {legal.regulatory?.length > 0 && (
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">Regulatory</div>
                      <div className="flex flex-wrap gap-1.5">
                        {legal.regulatory.map(r => (
                          <span key={r} className="text-[10px] px-2 py-1 rounded-lg bg-critical/10 text-critical font-mono">{r}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {legal.ip_references?.length > 0 && (
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">IP References</div>
                      <div className="flex flex-wrap gap-1.5">
                        {legal.ip_references.map(r => (
                          <span key={r} className="text-[10px] px-2 py-1 rounded-lg bg-white/5 text-secondary font-mono">{r}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {legal.concepts && Object.keys(legal.concepts).length > 0 && (
                    <div className="pt-2 border-t border-white/5">
                      <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">Legal Concepts</div>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(legal.concepts).map(([k, v]) => (
                          <span key={k} className="text-[10px] px-2 py-1 rounded-lg bg-white/5 text-secondary font-mono">
                            {k} ×{v}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </DossierSection>
            </div>

            {/* ML Insights */}
            <DossierSection icon={Brain} glyph="⟡" title="ML Insights"
              expanded={expandedSections.ml !== false}
              onToggle={() => toggleSection('ml')}>
              {ml.available ? (
                <div className="space-y-3">
                  {/* Topics */}
                  {ml.topics?.length > 0 && (
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">NMF Topics</div>
                      <div className="space-y-2">
                        {ml.topics.map((t, i) => (
                          <div key={i} className="flex items-center gap-3 py-2 px-3 rounded-lg bg-white/3">
                            <span className="text-[10px] font-mono text-primary flex-shrink-0">T{t.id}</span>
                            <div className="flex-1 flex flex-wrap gap-1">
                              {t.keywords?.map((kw, j) => (
                                <span key={j} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-secondary font-mono">{kw}</span>
                              ))}
                            </div>
                            <span className="text-[10px] font-mono text-secondary/40 flex-shrink-0">{t.chunk_count} chunks</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {/* TF-IDF top terms */}
                  {ml.tfidf_top?.length > 0 && (
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">TF-IDF Top Terms</div>
                      <div className="flex flex-wrap gap-1.5">
                        {ml.tfidf_top.map((t, i) => (
                          <span key={i} className="text-[10px] px-2 py-1 rounded-lg glass-orange text-primary font-mono">
                            {t} {typeof t === 'object' ? t.score : ''}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {/* Inferred KPIs */}
                  {ml.inferred_kpis?.length > 0 && (
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">Inferred KPIs (ML)</div>
                      <div className="grid grid-cols-2 gap-2">
                        {ml.inferred_kpis.map((k, i) => (
                          <div key={i} className="flex items-center gap-2 py-1.5 px-2 rounded-lg bg-white/3">
                            <span className="text-[10px] font-mono text-primary flex-shrink-0">{k.name}</span>
                            <span className="text-[10px] font-mono text-text flex-1 truncate">{k.value}</span>
                            <span className="text-[9px] font-mono text-secondary/40">{k.method}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {/* Anomalies */}
                  {ml.anomaly_count > 0 && (
                    <div className="flex items-center gap-2 text-xs text-warning">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      {ml.anomaly_count} anomalous chunks detected (Isolation Forest)
                    </div>
                  )}
                  {/* LLM extrapolation */}
                  {ml.llm_extrapolation && (
                    <div className="pt-2 border-t border-white/5">
                      <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">LLM Extrapolation</div>
                      <div className="space-y-2 text-xs">
                        {ml.llm_extrapolation.inferred_purpose && (
                          <div className="text-secondary"><span className="text-primary font-mono">Purpose:</span> {ml.llm_extrapolation.inferred_purpose}</div>
                        )}
                        {ml.llm_extrapolation.hidden_value && (
                          <div className="text-secondary"><span className="text-primary font-mono">Hidden Value:</span> {ml.llm_extrapolation.hidden_value}</div>
                        )}
                        {ml.llm_extrapolation.counterparty_risk && (
                          <div className="text-secondary"><span className="text-critical font-mono">Risk:</span> {ml.llm_extrapolation.counterparty_risk}</div>
                        )}
                        {ml.llm_extrapolation.monetization_vector && (
                          <div className="text-secondary"><span className="text-success font-mono">Monetization:</span> {ml.llm_extrapolation.monetization_vector}</div>
                        )}
                        {ml.llm_extrapolation.compliance_flags?.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {ml.llm_extrapolation.compliance_flags.map((f, i) => (
                              <span key={i} className="text-[10px] px-2 py-1 rounded-lg bg-critical/10 text-critical font-mono">⟁ {f}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-xs text-secondary/50 py-4 text-center">
                  ML features unavailable — {ml.error || 'scikit-learn not installed'}
                </div>
              )}
            </DossierSection>

            {/* KPI Summary */}
            <DossierSection icon={Hash} glyph="#" title={`KPI Summary (${kpi.total || 0})`}
              expanded={expandedSections.kpi !== false}
              onToggle={() => toggleSection('kpi')}>
              <div className="space-y-3">
                {kpi.by_category && Object.keys(kpi.by_category).length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(kpi.by_category).map(([cat, count]) => (
                      <span key={cat} className="text-[10px] px-2 py-1 rounded-lg bg-white/5 text-secondary font-mono">
                        {cat}: {count}
                      </span>
                    ))}
                  </div>
                )}
                {kpi.top_financial?.length > 0 && (
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">Top Financial</div>
                    <div className="space-y-1">
                      {kpi.top_financial.map((k, i) => (
                        <div key={i} className="flex items-center gap-2 text-[11px] font-mono">
                          <span className="text-primary flex-shrink-0">{k.name}</span>
                          <span className="text-text flex-1 truncate">{k.value}</span>
                          <span className="text-secondary/40">L{k.line}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {kpi.top_technical?.length > 0 && (
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-2">Top Technical</div>
                    <div className="space-y-1">
                      {kpi.top_technical.map((k, i) => (
                        <div key={i} className="flex items-center gap-2 text-[11px] font-mono">
                          <span className="text-primary flex-shrink-0">{k.name}</span>
                          <span className="text-text flex-1 truncate">{k.value}</span>
                          <span className="text-secondary/40">L{k.line}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </DossierSection>

            {/* Risk Assessment */}
            <DossierSection icon={AlertTriangle} glyph="⟁" title="Risk Assessment"
              expanded={expandedSections.risk !== false}
              onToggle={() => toggleSection('risk')}>
              <div className="space-y-3">
                <div className="flex items-center gap-4">
                  <div className={`text-2xl font-bold ${RISK_COLORS[risk.level] || 'text-secondary'}`}>
                    {risk.level?.toUpperCase()}
                  </div>
                  <div className="text-sm font-mono text-secondary">{risk.score}/100</div>
                  <div className="flex-1" />
                  <div className="text-right">
                    <div className="text-[10px] text-secondary/50">Origin</div>
                    <div className="text-xs font-mono text-primary">{risk.origin}</div>
                  </div>
                </div>
                {risk.signals?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {risk.signals.map((s, i) => (
                      <span key={i} className="text-[10px] px-2 py-1 rounded-lg bg-critical/10 text-critical font-mono">
                        ⟁ {s}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </DossierSection>

            {/* LLM-Generated Facts (30 KPIs) */}
            {llmFacts.length > 0 && (
              <DossierSection icon={Sparkles} glyph="⟡" title={`LLM Facts (${llmFacts.length})`}
                expanded={expandedSections.llmfacts !== false}
                onToggle={() => toggleSection('llmfacts')}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {llmFacts.map((fact, i) => (
                    <div key={fact.id || i} className="flex items-center gap-3 py-2 px-3 rounded-lg bg-white/3 hover:bg-white/5 transition-all">
                      <span className="text-[10px] font-mono text-primary/60 flex-shrink-0 w-6">{String(fact.id || i + 1).padStart(2, '0')}</span>
                      <span className="text-[10px] font-mono text-primary flex-shrink-0 w-28 truncate">{fact.label}</span>
                      <span className="text-[10px] font-mono text-text flex-1 truncate">{fact.value}</span>
                      <span className="text-[9px] font-mono text-secondary/40 flex-shrink-0 uppercase">{fact.category}</span>
                      <span className="text-[9px] font-mono text-secondary/30 flex-shrink-0">{((fact.confidence || 0) * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 pt-3 border-t border-white/5 flex items-center gap-3 text-[10px] font-mono text-secondary/40">
                  <span>⟡ Groq LLM · llama-3.3-70b</span>
                  <span>│</span>
                  <span>{llmFacts.length} facts generated</span>
                  <span>│</span>
                  <span>source: file content + extracted KPIs + ML topics</span>
                </div>
              </DossierSection>
            )}

            {/* Recommendations */}
            <DossierSection icon={Lightbulb} glyph="✦" title={`Recommendations (${recs.length})`}
              expanded={expandedSections.recs !== false}
              onToggle={() => toggleSection('recs')}>
              <div className="space-y-2">
                {recs.map((rec, i) => (
                  <div key={i} className={`flex items-center gap-3 py-2.5 px-3 rounded-xl ${PRIORITY_COLORS[rec.priority] || ''}`}>
                    <span className="text-sm font-mono flex-shrink-0">{PRIORITY_GLYPHS[rec.priority] || '◌'}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-medium">{rec.action}</span>
                        <span className="text-[9px] uppercase tracking-wider opacity-60">{rec.priority}</span>
                      </div>
                      <div className="text-[10px] opacity-70 mt-0.5">{rec.reason}</div>
                    </div>
                  </div>
                ))}
              </div>
            </DossierSection>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Sub-components ──────────────────────────────────────────────────────

function DossierSection({ icon: Icon, glyph, title, expanded, onToggle, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-2xl overflow-hidden"
    >
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-white/3 transition-all"
      >
        <span className="text-primary text-sm font-mono">{glyph}</span>
        <Icon className="w-4 h-4 text-primary" />
        <span className="text-sm font-semibold flex-1 text-left">{title}</span>
        {expanded ? <ChevronDown className="w-4 h-4 text-secondary/50" /> : <ChevronRight className="w-4 h-4 text-secondary/50" />}
      </button>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function StatRow({ label, value, mono }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-secondary/60 text-[10px] uppercase tracking-wider">{label}</span>
      <span className={`text-text ${mono ? 'font-mono' : ''} text-xs truncate ml-2`}>{value ?? '—'}</span>
    </div>
  )
}

function ValueCard({ label, value, glyph, sub }) {
  const formatted = typeof value === 'number' && value > 0
    ? `$${value.toLocaleString()}`
    : value ? `$${value}` : '—'
  return (
    <div className="glass rounded-xl p-3">
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-primary text-xs font-mono">{glyph}</span>
        <span className="text-[10px] uppercase tracking-wider text-secondary/50">{label}</span>
      </div>
      <div className="text-sm font-bold font-mono text-text">{formatted}</div>
      {sub && <div className="text-[9px] text-secondary/40 mt-0.5">{sub}</div>}
    </div>
  )
}

function GradeCard({ label, grade, score }) {
  return (
    <div className="glass rounded-xl p-3">
      <div className="text-[10px] uppercase tracking-wider text-secondary/50 mb-1">{label}</div>
      <div className="flex items-center gap-2">
        <span className={`text-lg font-bold ${GRADE_COLORS[grade] || 'text-secondary'}`}>{grade || 'F'}</span>
        <span className="text-xs font-mono text-secondary">{score || 0}/100</span>
      </div>
    </div>
  )
}
