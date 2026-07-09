import type { KPIData } from '../types';

interface Props {
  kpis: KPIData | null;
  compact?: boolean;
  focusedIndex?: number;
}

const KPI_META = [
  { key: 'immortality', glyph: '◈', label: 'IMMORTALITY', desc: 'durability · visibility · persistence' },
  { key: 'virality', glyph: '⌁', label: 'VIRALITY', desc: 'attention · acceleration · spread' },
  { key: 'conversion', glyph: '▲', label: 'CONVERSION', desc: 'profile views → contact actions' },
  { key: 'proof', glyph: '◆', label: 'PROOF', desc: 'receipts · metrics · artifacts' },
];

export function KPIPanel({ kpis, compact, focusedIndex = 0 }: Props) {
  const score = (key: string): number => {
    if (!kpis) return 0;
    const v = kpis[key];
    if (typeof v === 'number') return v;
    if (v && typeof v === 'object' && 'score' in v) return (v as any).score;
    return 0;
  };

  const composite = kpis?.composite ?? 0;

  return (
    <div className={`kpi-panel ${compact ? 'compact' : ''}`}>
      {!compact && (
        <div className="panel-header">
          <span className="glyph glyph-orange mono-lg">▲ KPI SURFACE</span>
          <span className="mono-sm glyph-dim">live production metrics</span>
        </div>
      )}
      <div className={`kpi-grid ${compact ? 'compact' : ''}`}>
        {KPI_META.map((kpi, i) => {
          const val = score(kpi.key);
          const pct = Math.round(val * 100);
          const color = pct >= 70 ? 'var(--green)' : pct >= 40 ? 'var(--orange)' : 'var(--red)';
          return (
            <div
              key={kpi.key}
              className={`glass-card kpi-card ${!compact && i === focusedIndex ? 'focused' : ''}`}
            >
              <div className="kpi-card-header">
                <span className="glyph mono-lg" style={{ color }}>{kpi.glyph}</span>
                <span className="mono-sm glyph-dim">{kpi.label}</span>
              </div>
              <div className="kpi-value mono-2xl" style={{ color }}>
                {kpis ? `${pct}` : '—'}
                <span className="mono-sm glyph-dim"> /100</span>
              </div>
              {!compact && (
                <div className="kpi-bar-container">
                  <div className="kpi-bar" style={{ width: `${pct}%`, background: color }} />
                </div>
              )}
              {!compact && (
                <div className="mono-sm glyph-dim kpi-desc">{kpi.desc}</div>
              )}
            </div>
          );
        })}
      </div>
      {!compact && (
        <div className="composite-score glass-card">
          <span className="glyph glyph-orange mono-md">◈ COMPOSITE</span>
          <span className="mono-xl" style={{ color: 'var(--orange)' }}>
            {kpis ? Math.round(composite * 100) : '—'}
          </span>
        </div>
      )}
    </div>
  );
}
