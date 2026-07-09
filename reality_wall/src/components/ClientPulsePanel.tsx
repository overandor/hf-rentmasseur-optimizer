import type { ClientPulseData } from '../types';

interface Props {
  data: ClientPulseData | null;
  compact?: boolean;
}

export function ClientPulsePanel({ data, compact }: Props) {
  if (!data) {
    return (
      <div className="glass-panel client-pulse">
        <div className="panel-header">
          <span className="glyph glyph-orange mono-lg">⌁ CLIENTPULSE</span>
        </div>
        <div className="mono-md glyph-dim">no pulse data</div>
      </div>
    );
  }

  const snapshots = data.snapshots || [];
  const latest = snapshots[0];
  const previous = snapshots[1];

  const ctr = latest?.ctr ?? 0;
  const prevCtr = previous?.ctr ?? 0;
  const ctrDelta = ctr - prevCtr;
  const ctrArrow = ctrDelta > 0 ? '▲' : ctrDelta < 0 ? '▼' : '◆';
  const ctrColor = ctrDelta > 0 ? 'var(--green)' : ctrDelta < 0 ? 'var(--red)' : 'var(--text-dim)';

  const decisions = data.recent_decisions || [];
  const latestDecision = decisions[0];

  return (
    <div className="glass-panel client-pulse">
      <div className="panel-header">
        <span className="glyph glyph-orange mono-lg">⌁ CLIENTPULSE</span>
        <span className="mono-sm glyph-dim">hourly evidence engine</span>
      </div>
      <div className="pulse-grid">
        <div className="glass-card pulse-stat">
          <span className="mono-sm glyph-dim">CTR</span>
          <span className="mono-lg" style={{ color: ctrColor }}>
            {(ctr * 100).toFixed(2)}%
          </span>
          <span className="mono-sm" style={{ color: ctrColor }}>
            {ctrArrow} {Math.abs(ctrDelta * 100).toFixed(2)}%
          </span>
        </div>
        <div className="glass-card pulse-stat">
          <span className="mono-sm glyph-dim">VIEWS</span>
          <span className="mono-lg">{latest?.daily_views ?? '—'}</span>
          <span className="mono-sm glyph-dim">today</span>
        </div>
        <div className="glass-card pulse-stat">
          <span className="mono-sm glyph-dim">CONTACT</span>
          <span className="mono-lg">{latest?.contact_clicks ?? '—'}</span>
          <span className="mono-sm glyph-dim">clicks</span>
        </div>
        <div className="glass-card pulse-stat">
          <span className="mono-sm glyph-dim">DAYS</span>
          <span className="mono-lg">{latest?.days_online ?? '—'}</span>
          <span className="mono-sm glyph-dim">online</span>
        </div>
      </div>
      {latestDecision && (
        <div className="decision-banner glass-card">
          <span className="glyph glyph-orange mono-md">◈ DECISION</span>
          <span className="mono-sm">{latestDecision.state || latestDecision.decision || '—'}</span>
        </div>
      )}
    </div>
  );
}
