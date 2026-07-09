import type { LambdaReceipt } from '../types';

interface Props {
  receipts: LambdaReceipt[];
  focusedIndex?: number;
}

export function ProofCards({ receipts, focusedIndex = 0 }: Props) {
  if (receipts.length === 0) {
    return (
      <div className="empty-state glass-panel">
        <span className="glyph glyph-dim mono-xl">◌</span>
        <span className="mono-md glyph-dim">no lambda receipts compiled</span>
        <span className="mono-sm glyph-dim">run: python3 forge.py rc compile</span>
      </div>
    );
  }

  return (
    <div className="proof-grid">
      <div className="panel-header">
        <span className="glyph glyph-orange mono-lg">◆ PROOF CARDS</span>
        <span className="mono-sm glyph-dim">lambda receipts · transferability scored</span>
      </div>
      <div className="proof-card-grid">
        {receipts.map((r, i) => {
          const score = r.lambda_score ?? 0;
          const pct = Math.round(score * 100);
          const transferable = score >= 0.6;
          const color = transferable ? 'var(--green)' : 'var(--orange)';
          return (
            <div
              key={r.id || i}
              className={`glass-card proof-card ${i === focusedIndex ? 'focused' : ''}`}
            >
              <div className="proof-card-header">
                <span className="glyph mono-lg" style={{ color: transferable ? 'var(--green)' : 'var(--orange)' }}>
                  {transferable ? '◆' : '◇'}
                </span>
                <span className="mono-sm glyph-dim">
                  {transferable ? 'TRANSFERABLE' : 'BUILDING'}
                </span>
              </div>
              <div className="proof-intent mono-md">
                {r.intent || '—'}
              </div>
              <div className="proof-score mono-xl" style={{ color }}>
                {pct}
                <span className="mono-sm glyph-dim"> λ</span>
              </div>
              <div className="kpi-bar-container">
                <div className="kpi-bar" style={{ width: `${pct}%`, background: color }} />
              </div>
              <div className="proof-meta mono-sm glyph-dim">
                <div>transferability: {Math.round((r.transferability ?? 0) * 100)}%</div>
                <div>created: {(r.created_at || '—').substring(0, 19)}</div>
                <div className="proof-hash">
                  <span className="glyph" style={{ color: 'var(--orange)' }}>◆</span>{' '}
                  {(() => {
                    const h = r.source_hash || r.receipt_hash || r.hash || '';
                    return h ? h.substring(0, 16) + '…' : '—';
                  })()}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
