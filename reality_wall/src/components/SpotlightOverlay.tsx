import type { WallState, LambdaReceipt, Receipt } from '../types';

interface SpotlightData {
  cardId: string;
  cardType: string;
  pushedBy: string;
}

interface Props {
  spotlight: SpotlightData;
  state: WallState;
  onDismiss: () => void;
}

export function SpotlightOverlay({ spotlight, state, onDismiss }: Props) {
  const card = findCard(spotlight, state);

  return (
    <div className="spotlight-overlay" onClick={onDismiss}>
      <div className="spotlight-card glass-panel">
        <div className="spotlight-header">
          <span className="glyph glyph-orange mono-lg pulse">⧉</span>
          <span className="mono-md" style={{ color: 'var(--orange)', fontWeight: 'bold' }}>
            SPOTLIGHT
          </span>
          <span className="mono-sm glyph-dim">
            pushed by {spotlight.pushedBy}
          </span>
          <button className="spotlight-dismiss mono-sm" onClick={onDismiss}>
            <span className="glyph glyph-dim">✕ dismiss</span>
          </button>
        </div>

        {card ? (
          <div className="spotlight-body">
            {spotlight.cardType === 'proof' && card as LambdaReceipt && (
              <ProofSpotlight receipt={card as LambdaReceipt} />
            )}
            {spotlight.cardType === 'receipt' && card as Receipt && (
              <ReceiptSpotlight receipt={card as Receipt} />
            )}
          </div>
        ) : (
          <div className="spotlight-empty">
            <span className="glyph glyph-dim mono-xl">◌</span>
            <span className="mono-sm glyph-dim">
              card {spotlight.cardId} not found in current state
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function findCard(spotlight: SpotlightData, state: WallState): any | null {
  if (spotlight.cardType === 'proof') {
    return state.lambdaReceipts.find((r) => String(r.id) === spotlight.cardId) || null;
  }
  if (spotlight.cardType === 'receipt') {
    return state.receipts.find((r) => String(r.id) === spotlight.cardId) || null;
  }
  return null;
}

function ProofSpotlight({ receipt }: { receipt: LambdaReceipt }) {
  const score = receipt.lambda_score ?? 0;
  const pct = Math.round(score * 100);
  const transferable = score >= 0.6;
  const color = transferable ? 'var(--green)' : 'var(--orange)';
  const hash = receipt.source_hash || receipt.receipt_hash || receipt.hash || '';

  return (
    <>
      <div className="spotlight-status">
        <span className="glyph mono-xl" style={{ color }}>
          {transferable ? '◆' : '◇'}
        </span>
        <span className="mono-md" style={{ color }}>
          {transferable ? 'TRANSFERABLE' : 'BUILDING'}
        </span>
      </div>
      <div className="spotlight-intent mono-lg">
        {receipt.intent || '—'}
      </div>
      <div className="spotlight-score mono-2xl" style={{ color }}>
        {pct}<span className="mono-sm glyph-dim"> λ</span>
      </div>
      <div className="kpi-bar-container" style={{ height: '4px' }}>
        <div className="kpi-bar" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="spotlight-meta">
        <div className="mono-sm glyph-dim">
          transferability: {Math.round((receipt.transferability ?? 0) * 100)}%
        </div>
        <div className="mono-sm glyph-dim">
          created: {(receipt.created_at || '—').substring(0, 19)}
        </div>
        <div className="mono-sm spotlight-hash">
          <span className="glyph" style={{ color: 'var(--orange)' }}>◆</span>{' '}
          {hash ? hash : '—'}
        </div>
      </div>
    </>
  );
}

function ReceiptSpotlight({ receipt }: { receipt: Receipt }) {
  const verified = receipt.verified !== false;
  const hash = receipt.artifact_hash || receipt.hash || '';

  return (
    <>
      <div className="spotlight-status">
        <span className={`glyph mono-xl ${verified ? 'glyph-green' : 'glyph-red'}`}>
          {verified ? '◆' : '⟁'}
        </span>
        <span className={`mono-md ${verified ? 'glyph-green' : 'glyph-red'}`}>
          {verified ? 'VERIFIED' : 'TAMPERED'}
        </span>
      </div>
      <div className="spotlight-intent mono-lg">
        {receipt.action || receipt.type || 'unknown'}
      </div>
      <div className="spotlight-meta">
        <div className="mono-sm glyph-dim">
          agent: {receipt.agent || receipt.source || '—'}
        </div>
        <div className="mono-sm glyph-dim">
          timestamp: {(receipt.timestamp || '—').substring(0, 19)}
        </div>
        <div className="mono-sm spotlight-hash">
          <span className="glyph" style={{ color: 'var(--orange)' }}>◆</span>{' '}
          {hash || '—'}
        </div>
      </div>
    </>
  );
}
