import type { Receipt } from '../types';

interface Props {
  receipts: Receipt[];
  compact?: boolean;
  focusedIndex?: number;
}

export function ReceiptChain({ receipts, compact, focusedIndex = 0 }: Props) {
  if (receipts.length === 0) {
    return (
      <div className="empty-state glass-panel">
        <span className="glyph glyph-dim mono-xl">◌</span>
        <span className="mono-md glyph-dim">no receipts in ledger</span>
      </div>
    );
  }

  return (
    <div className={`receipt-chain ${compact ? 'compact' : ''}`}>
      {!compact && (
        <div className="panel-header">
          <span className="glyph glyph-orange mono-lg">⧉ RECEIPT CHAIN</span>
          <span className="mono-sm glyph-dim">tamper-evident ledger</span>
        </div>
      )}
      <div className="receipt-list">
        {receipts.map((r, i) => {
          const verified = r.verified !== false;
          const hash = r.artifact_hash || r.hash || '—';
          const shortHash = hash.length > 16 ? hash.substring(0, 16) + '…' : hash;
          const ts = r.timestamp || r.ts || '—';
          const shortTs = ts.length > 19 ? ts.substring(0, 19) : ts;
          return (
            <div
              key={r.id || i}
              className={`glass-card receipt-row ${!compact && i === focusedIndex ? 'focused' : ''}`}
            >
              <div className="receipt-glyph">
                <span className={`glyph mono-md ${verified ? 'glyph-green' : 'glyph-red'}`}>
                  {verified ? '◆' : '⟁'}
                </span>
              </div>
              <div className="receipt-content">
                <div className="receipt-action mono-md">
                  {r.action || r.type || 'unknown'}
                </div>
                <div className="mono-sm glyph-dim receipt-meta">
                  {r.agent || r.source || '—'} · {shortTs}
                </div>
              </div>
              <div className="receipt-hash">
                <span className="mono-sm glyph-dim">{shortHash}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
