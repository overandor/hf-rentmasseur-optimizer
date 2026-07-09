import type { View } from '../types';

interface Props {
  views: View[];
  current: View;
  onSelect: (v: View) => void;
}

const VIEW_GLYPHS: Record<View, string> = {
  overview: '◉',
  proof: '◆',
  receipts: '⧉',
  kpi: '▲',
  experiments: '⟡',
  cast: '⌁',
  pairing: '⧖',
  demo: '◈',
};

const VIEW_LABELS: Record<View, string> = {
  overview: 'OVERVIEW',
  proof: 'PROOF',
  receipts: 'RECEIPTS',
  kpi: 'KPI',
  experiments: 'EXPERIMENTS',
  cast: 'CAST',
  pairing: 'PAIRING',
  demo: 'DEMO',
};

export function ViewNav({ views, current, onSelect }: Props) {
  return (
    <nav className="view-nav glass-panel">
      {views.map((v) => (
        <button
          key={v}
          className={`nav-item ${current === v ? 'active' : ''}`}
          onClick={() => onSelect(v)}
        >
          <span className={`glyph mono-md ${current === v ? 'glyph-orange' : 'glyph-dim'}`}>
            {VIEW_GLYPHS[v]}
          </span>
          <span className={`mono-sm ${current === v ? '' : 'glyph-dim'}`}>
            {VIEW_LABELS[v]}
          </span>
        </button>
      ))}
    </nav>
  );
}
