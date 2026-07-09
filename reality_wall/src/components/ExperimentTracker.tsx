import type { Experiment, ClientPulseData } from '../types';

interface Props {
  experiments: Experiment[];
  clientPulse: ClientPulseData | null;
  focusedIndex?: number;
}

const STATUS_GLYPHS: Record<string, { glyph: string; color: string }> = {
  running: { glyph: '⌁', color: 'var(--orange)' },
  completed: { glyph: '◆', color: 'var(--green)' },
  rolled_back: { glyph: '▼', color: 'var(--red)' },
  iterating: { glyph: '⟡', color: 'var(--orange)' },
  pending: { glyph: '◌', color: 'var(--text-dim)' },
};

export function ExperimentTracker({ experiments, clientPulse, focusedIndex = 0 }: Props) {
  const allExperiments = [
    ...experiments,
    ...(clientPulse?.active_experiments || []).map((e: any) => ({
      id: e.id,
      name: e.name,
      hypothesis: e.hypothesis || e.description || '—',
      status: e.status || 'running',
      created_at: e.created_at || '—',
    })),
  ];

  if (allExperiments.length === 0) {
    return (
      <div className="empty-state glass-panel">
        <span className="glyph glyph-dim mono-xl">◌</span>
        <span className="mono-md glyph-dim">no active experiments</span>
      </div>
    );
  }

  return (
    <div className="experiment-tracker">
      <div className="panel-header">
        <span className="glyph glyph-orange mono-lg">⟡ EXPERIMENT TRACKER</span>
        <span className="mono-sm glyph-dim">hypothesis · verdict · keep/rollback</span>
      </div>
      <div className="experiment-list">
        {allExperiments.map((e, i) => {
          const meta = STATUS_GLYPHS[e.status] || STATUS_GLYPHS.pending;
          return (
            <div
              key={e.id || i}
              className={`glass-card experiment-row ${i === focusedIndex ? 'focused' : ''}`}
            >
              <div className="experiment-glyph">
                <span className="glyph mono-lg" style={{ color: meta.color }}>
                  {meta.glyph}
                </span>
              </div>
              <div className="experiment-content">
                <div className="experiment-name mono-md">
                  {e.name}
                </div>
                <div className="mono-sm glyph-dim experiment-hypothesis">
                  {e.hypothesis}
                </div>
              </div>
              <div className="experiment-status">
                <span className="mono-sm" style={{ color: meta.color }}>
                  {e.status.toUpperCase()}
                </span>
                <span className="mono-sm glyph-dim">
                  {(e.created_at || '—').substring(0, 10)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
