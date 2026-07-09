import { useState, useEffect, useRef } from 'react';

interface Props {
  castUrl: string;
}

export function CastView({ castUrl }: Props) {
  const [status, setStatus] = useState<'connecting' | 'streaming' | 'error'>('connecting');
  const [meta, setMeta] = useState<{ side: string; resolution: string; fps: number } | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    fetch(`${castUrl}/status`)
      .then((r) => r.json())
      .then((data) => {
        setMeta({ side: data.side, resolution: data.resolution, fps: data.fps });
      })
      .catch(() => {});
  }, [castUrl]);

  return (
    <div className="cast-view">
      <div className="cast-header glass-panel">
        <span className="glyph glyph-orange mono-lg pulse">⌁</span>
        <span className="mono-md" style={{ color: 'var(--orange)', fontWeight: 'bold' }}>
          SCREEN CAST
        </span>
        {meta && (
          <>
            <span className="mono-sm glyph-dim">
              {meta.side} half · {meta.resolution} · {meta.fps}fps
            </span>
          </>
        )}
        <span className={`mono-sm ${status === 'streaming' ? 'glyph-green' : status === 'error' ? 'glyph-red' : 'glyph-orange'}`}>
          {status === 'streaming' ? '◉ streaming' : status === 'error' ? '⟁ error' : '◌ connecting'}
        </span>
      </div>

      <div className="cast-display glass-panel">
        <img
          ref={imgRef}
          src={`${castUrl}/stream`}
          alt="mac screen cast"
          className="cast-stream"
          onLoad={() => setStatus('streaming')}
          onError={() => setStatus('error')}
        />
      </div>

      <div className="cast-footer glass-panel">
        <span className="mono-sm glyph-dim">
          ⌁ live MJPEG stream from Mac · no audio · proof display only
        </span>
        <span className="mono-sm glyph-dim">
          ◈ Reality Wall · Samsung Tizen
        </span>
      </div>
    </div>
  );
}
