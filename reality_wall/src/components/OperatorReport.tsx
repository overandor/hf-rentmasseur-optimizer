import type { OperatorReport as OperatorReportType } from '../types';

interface Props {
  report: OperatorReportType | null;
}

export function OperatorReport({ report }: Props) {
  if (!report) {
    return (
      <div className="glass-panel operator-report">
        <div className="panel-header">
          <span className="glyph glyph-orange mono-lg">◈ OPERATOR REPORT</span>
        </div>
        <div className="mono-md glyph-dim">awaiting data…</div>
      </div>
    );
  }

  const lines = [
    { label: 'STATUS', value: report.status, glyph: '◉', color: 'var(--green)' },
    { label: 'PROOF', value: report.proof, glyph: '◆', color: 'var(--orange)' },
    { label: 'RISK', value: report.risk, glyph: '⟁', color: 'var(--red)' },
    { label: 'NEXT', value: report.next_move, glyph: '⟡', color: 'var(--orange)' },
  ];

  return (
    <div className="glass-panel operator-report">
      <div className="panel-header">
        <span className="glyph glyph-orange mono-lg">◈ OPERATOR REPORT</span>
        <span className="mono-sm glyph-dim">status · proof · risk · next move</span>
      </div>
      <div className="operator-lines">
        {lines.map((l) => (
          <div key={l.label} className="operator-line">
            <span className="glyph mono-md" style={{ color: l.color }}>{l.glyph}</span>
            <span className="mono-sm" style={{ color: l.color, fontWeight: 'bold' }}>{l.label}</span>
            <span className="mono-sm operator-value">{l.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
