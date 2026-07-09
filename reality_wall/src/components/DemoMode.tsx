import type { WallState } from '../types';
import { KPIPanel } from './KPIPanel';
import { ReceiptChain } from './ReceiptChain';
import { ProofCards } from './ProofCards';
import { OperatorReport } from './OperatorReport';
import { ClientPulsePanel } from './ClientPulsePanel';

interface Props {
  state: WallState;
}

export function DemoMode({ state }: Props) {
  const hasData = state.kpis || state.receipts.length > 0 || state.lambdaReceipts.length > 0;
  const cacheAge = state.lastUpdate
    ? Math.round((Date.now() - state.lastUpdate) / 1000)
    : 0;

  return (
    <div className="demo-mode">
      <div className="demo-banner glass-panel">
        <div className="demo-banner-left">
          <span className="glyph glyph-orange mono-lg pulse">◈</span>
          <div>
            <div className="mono-md" style={{ color: 'var(--orange)', fontWeight: 'bold' }}>
              INVESTOR DEMO MODE
            </div>
            <div className="mono-sm glyph-dim">
              read-only · cached proof display · no live backend required
            </div>
          </div>
        </div>
        <div className="demo-banner-right">
          {hasData ? (
            <>
              <span className="glyph glyph-green mono-md">◆</span>
              <span className="mono-sm">cached data available</span>
              <span className="mono-sm glyph-dim">
                ⟡ {cacheAge}s ago
              </span>
            </>
          ) : (
            <>
              <span className="glyph glyph-red mono-md">⟁</span>
              <span className="mono-sm">no cached data — connect to backend first</span>
            </>
          )}
        </div>
      </div>

      {hasData ? (
        <div className="demo-content">
          <div className="demo-row">
            <KPIPanel kpis={state.kpis} compact />
            <OperatorReport report={state.operatorReport} />
          </div>
          <div className="demo-row">
            <ProofCards receipts={state.lambdaReceipts} />
          </div>
          <div className="demo-row">
            <ReceiptChain receipts={state.receipts.slice(0, 10)} compact />
            <ClientPulsePanel data={state.clientPulse} compact />
          </div>
        </div>
      ) : (
        <div className="empty-state glass-panel" style={{ marginTop: '40px' }}>
          <span className="glyph glyph-dim mono-xl">◌</span>
          <span className="mono-md glyph-dim">no cached proof data</span>
          <span className="mono-sm glyph-dim">
            connect to a live backend at least once to populate the cache
          </span>
          <span className="mono-sm glyph-dim">
            the TV will display the last known state in demo mode
          </span>
        </div>
      )}

      <div className="demo-footer glass-panel">
        <span className="mono-sm glyph-dim">
          ◈ Reality Wall · proprietary proof control surface · Samsung Tizen
        </span>
        <span className="mono-sm glyph-dim">
          {state.receipts.length} receipts · {state.lambdaReceipts.length} lambda · {state.experiments.length} experiments
        </span>
      </div>
    </div>
  );
}
