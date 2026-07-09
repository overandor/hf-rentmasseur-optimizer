import type { WallState, DisplayMode, DisplayModeState } from '../types';

interface Props {
  state: WallState;
  onPair?: () => void;
  onDemo?: () => void;
  isDemo?: boolean;
  displayMode?: DisplayModeState;
  onSwitchMode?: (mode: DisplayMode) => void;
}

type ConnState = 'LIVE_VERIFIED' | 'CACHED_READ_ONLY' | 'NO_BACKEND' | 'PAIRING_REQUIRED';

function getConnState(state: WallState, isDemo: boolean): ConnState {
  if (isDemo) return 'CACHED_READ_ONLY';
  if (state.connected) return 'LIVE_VERIFIED';
  if (state.lastUpdate > 0) return 'NO_BACKEND';
  return 'PAIRING_REQUIRED';
}

const CONN_LABELS: Record<ConnState, { glyph: string; color: string; label: string }> = {
  LIVE_VERIFIED: { glyph: '◉', color: 'var(--green)', label: 'LIVE VERIFIED' },
  CACHED_READ_ONLY: { glyph: '◈', color: 'var(--orange)', label: 'CACHED READ-ONLY' },
  NO_BACKEND: { glyph: '⟁', color: 'var(--red)', label: 'NO BACKEND' },
  PAIRING_REQUIRED: { glyph: '◌', color: 'var(--orange)', label: 'PAIRING REQUIRED' },
};

export function Header({ state, onPair, onDemo, isDemo, displayMode, onSwitchMode }: Props) {
  const connState = getConnState(state, isDemo || false);
  const conn = CONN_LABELS[connState];
  const lastUpdate = state.lastUpdate
    ? new Date(state.lastUpdate).toLocaleTimeString()
    : '—';

  const modeGlyph = displayMode?.screenSharingActive ? '⌁' : '◈';
  const modeLabel = displayMode?.screenSharingActive ? 'CAST' : 'DASHBOARD';
  const modeColor = displayMode?.screenSharingActive ? 'var(--orange)' : 'var(--green)';

  return (
    <header className="header glass-panel">
      <div className="header-left">
        <span className="glyph glyph-orange mono-xl">◈</span>
        <div>
          <div className="mono-lg" style={{ color: 'var(--orange)', fontWeight: 'bold' }}>
            REALITY WALL
          </div>
          <div className="mono-sm glyph-dim">
            proprietary proof control surface
          </div>
        </div>
      </div>
      <div className="header-right">
        <div className={`status-pill ${connState === 'LIVE_VERIFIED' ? 'connected' : 'disconnected'}`}>
          <span className="glyph mono-sm" style={{ color: conn.color }}>
            {conn.glyph}
          </span>
          <span className="mono-sm" style={{ color: conn.color, fontWeight: 'bold' }}>
            {conn.label}
          </span>
        </div>
        <div className="mono-sm glyph-dim">
          ⟡ {lastUpdate}
        </div>
        <div className="mono-sm glyph-dim">
          ◆ {state.receipts.length} receipts
        </div>
        <div className="mono-sm glyph-dim">
          ⧉ {state.lambdaReceipts.length} lambda
        </div>
        {displayMode && onSwitchMode && (
          <div className="display-mode-switcher">
            <button
              className={`header-btn mono-sm ${!displayMode.screenSharingActive ? 'active-mode' : ''}`}
              onClick={() => onSwitchMode('dashboard')}
              title="Remote management — dashboard controls"
            >
              <span className="glyph" style={{ color: modeColor }}>◈</span> dashboard
            </button>
            <button
              className={`header-btn mono-sm ${displayMode.screenSharingActive ? 'active-mode' : ''}`}
              onClick={() => onSwitchMode('cast')}
              title="Screen sharing — cast Mac display"
            >
              <span className="glyph" style={{ color: modeColor }}>⌁</span> cast
            </button>
            {displayMode.conflict && (
              <span className="mono-sm glyph-red pulse">
                ⟁ conflict
              </span>
            )}
          </div>
        )}
        <div className="remote-hints">
          <span className="mono-sm glyph-dim"><span className="glyph glyph-red">A</span> refresh</span>
          <span className="mono-sm glyph-dim"><span className="glyph glyph-green">B</span> next</span>
          <span className="mono-sm glyph-dim"><span className="glyph glyph-orange" style={{ color: '#dd0' }}>C</span> prev</span>
          <span className="mono-sm glyph-dim"><span className="glyph" style={{ color: '#48f' }}>D</span> home</span>
        </div>
        {onPair && (
          <button className="header-btn mono-sm" onClick={onPair}>
            <span className="glyph glyph-orange">⧉</span> pair
          </button>
        )}
        {onDemo && (
          <button className="header-btn mono-sm" onClick={onDemo}>
            <span className="glyph glyph-dim">◈</span> demo
          </button>
        )}
      </div>
    </header>
  );
}
