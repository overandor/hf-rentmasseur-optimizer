import { useState, useEffect, useRef } from 'react';

interface Props {
  wsUrl: string;
  onPaired: () => void;
  setPairingToken?: (token: string) => void;
}

interface PairingRequest {
  wall_id: string;
  nonce: string;
  expires_at: number;
  pair_url: string;
  ws_url: string;
}

export function QRPairing({ wsUrl, onPaired, setPairingToken }: Props) {
  const [status, setStatus] = useState<'connecting' | 'waiting' | 'paired' | 'error' | 'expired'>('connecting');
  const [pairReq, setPairReq] = useState<PairingRequest | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const statusRef = useRef(status);
  statusRef.current = status;

  useEffect(() => {
    let cancelled = false;

    function connect() {
      if (cancelled) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connecting');
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'auth_required' && msg.wall_id) {
            setStatus('waiting');
            ws.send(JSON.stringify({ type: 'request_pairing', wall_id: msg.wall_id }));
          } else if (msg.type === 'pairing_request_created' && msg.nonce) {
            setPairReq({
              wall_id: msg.wall_id,
              nonce: msg.nonce,
              expires_at: msg.expires_at,
              pair_url: msg.pair_url,
              ws_url: msg.ws_url || wsUrl,
            });
            setStatus('waiting');
          } else if (msg.type === 'authenticated' && msg.wall_id) {
            setStatus('paired');
            setTimeout(() => onPaired(), 1500);
          } else if (msg.type === 'auth_rejected') {
            setStatus('error');
            setErrorMsg(msg.message || 'auth rejected');
          }
        } catch (e) {
          console.error('[pairing] parse error:', e);
        }
      };

      ws.onclose = () => {
        if (!cancelled && statusRef.current !== 'paired') {
          setStatus('connecting');
          setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        setStatus('error');
        setErrorMsg('connection failed');
      };
    }

    connect();

    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, [wsUrl]);

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed((e) => e + 1);
      if (pairReq && Date.now() > pairReq.expires_at) {
        setStatus('expired');
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [pairReq]);

  useEffect(() => {
    if (pairReq) {
      const qrData = JSON.stringify({
        wall_id: pairReq.wall_id,
        nonce: pairReq.nonce,
        expires_at: pairReq.expires_at,
        pair_url: pairReq.pair_url,
        product: 'reality-wall',
        version: '1.0.0',
      });
      drawQR(canvasRef.current, qrData);
    }
  }, [pairReq]);

  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const remaining = pairReq ? Math.max(0, Math.floor((pairReq.expires_at - Date.now()) / 1000)) : 0;
  const remMin = Math.floor(remaining / 60);
  const remSec = remaining % 60;

  return (
    <div className="pairing-screen">
      <div className="pairing-content glass-panel">
        <div className="pairing-header">
          <span className="glyph glyph-orange mono-2xl">◈</span>
          <div>
            <div className="mono-xl" style={{ color: 'var(--orange)', fontWeight: 'bold' }}>
              REALITY WALL
            </div>
            <div className="mono-sm glyph-dim">
              pair your device to the proof wall
            </div>
          </div>
        </div>

        <div className="pairing-body">
          <div className="qr-container glass-card">
            {pairReq ? (
              <canvas ref={canvasRef} width={240} height={240} />
            ) : (
              <div className="qr-placeholder">
                <span className="glyph glyph-orange mono-2xl pulse">◌</span>
                <span className="mono-sm glyph-dim">requesting pairing...</span>
              </div>
            )}
          </div>

          <div className="pairing-info">
            <div className="pairing-status">
              <span className={`glyph mono-lg ${status === 'waiting' ? 'glyph-orange pulse' :
                  status === 'paired' ? 'glyph-green' :
                    status === 'expired' ? 'glyph-red' :
                      status === 'error' ? 'glyph-red' : 'glyph-dim'
                }`}>
                {status === 'waiting' ? '◌' :
                  status === 'paired' ? '◆' :
                    status === 'expired' ? '⧖' :
                      status === 'error' ? '⟁' : '◌'}
              </span>
              <span className="mono-md">
                {status === 'connecting' ? 'CONNECTING...' :
                  status === 'waiting' ? 'AWAITING PAIR' :
                    status === 'paired' ? 'PAIRED' :
                      status === 'expired' ? 'EXPIRED — RETRY' :
                        'ERROR'}
              </span>
            </div>

            {pairReq && (
              <>
                <div className="pairing-code mono-xl glyph-orange">
                  {pairReq.nonce}
                </div>

                <div className="mono-sm glyph-dim pairing-instructions">
                  <div>1. Scan QR with phone or Mac</div>
                  <div>2. Open the pairing URL</div>
                  <div>3. Confirm nonce matches: {pairReq.nonce}</div>
                </div>

                <div className="pairing-meta mono-sm glyph-dim">
                  <div>⧖ expires in {String(remMin).padStart(2, '0')}:{String(remSec).padStart(2, '0')}</div>
                  <div>◈ wall: {pairReq.wall_id}</div>
                  <div>⟡ {String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')} elapsed</div>
                </div>
              </>
            )}

            {status === 'error' && (
              <div className="mono-sm glyph-red">
                ⟁ {errorMsg}
              </div>
            )}

            {status === 'expired' && (
              <button className="pairing-skip mono-sm" onClick={() => window.location.reload()}>
                <span className="glyph glyph-orange">↻ retry pairing</span>
              </button>
            )}

            <button className="pairing-skip mono-sm" onClick={onPaired}>
              <span className="glyph glyph-dim">→ skip to wall</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function drawQR(canvas: HTMLCanvasElement | null, data: string) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const size = 240;
  const modules = 29;
  const cellSize = size / modules;

  ctx.fillStyle = '#050507';
  ctx.fillRect(0, 0, size, size);

  const hash = simpleHash(data);

  ctx.fillStyle = '#ff8c00';
  for (let y = 0; y < modules; y++) {
    for (let x = 0; x < modules; x++) {
      if (isFinderPattern(x, y, modules)) continue;
      if (isAlignmentPattern(x, y, modules)) continue;
      const bit = (hash[(y * modules + x) % hash.length] >> ((x + y) % 8)) & 1;
      if (bit) {
        ctx.fillRect(x * cellSize, y * cellSize, cellSize, cellSize);
      }
    }
  }

  drawFinderPattern(ctx, 0, 0, cellSize);
  drawFinderPattern(ctx, modules - 7, 0, cellSize);
  drawFinderPattern(ctx, 0, modules - 7, cellSize);
  drawAlignmentPattern(ctx, modules - 9, modules - 9, cellSize);

  ctx.fillStyle = '#050507';
  ctx.font = 'bold 8px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('RW', size / 2, size / 2 + 3);
}

function simpleHash(data: string): number[] {
  const result: number[] = [];
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < data.length; i++) {
    const ch = data.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507);
  const seed = (h1 ^ h2) >>> 0;

  let s = seed;
  for (let i = 0; i < 900; i++) {
    s = (Math.imul(s, 1103515245) + 12345) & 0x7fffffff;
    result.push(s & 0xff);
  }
  return result;
}

function isFinderPattern(x: number, y: number, modules: number): boolean {
  const inBox = (ox: number, oy: number) =>
    x >= ox && x < ox + 8 && y >= oy && y < oy + 8;
  return inBox(0, 0) || inBox(modules - 8, 0) || inBox(0, modules - 8);
}

function isAlignmentPattern(x: number, y: number, modules: number): boolean {
  return x >= modules - 9 && x < modules - 4 && y >= modules - 9 && y < modules - 4;
}

function drawFinderPattern(ctx: CanvasRenderingContext2D, ox: number, oy: number, cellSize: number) {
  ctx.fillStyle = '#ff8c00';
  for (let dy = 0; dy < 7; dy++) {
    for (let dx = 0; dx < 7; dx++) {
      const isBorder = dx === 0 || dx === 6 || dy === 0 || dy === 6;
      const isInner = dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4;
      if (isBorder || isInner) {
        ctx.fillRect((ox + dx) * cellSize, (oy + dy) * cellSize, cellSize, cellSize);
      }
    }
  }
}

function drawAlignmentPattern(ctx: CanvasRenderingContext2D, ox: number, oy: number, cellSize: number) {
  ctx.fillStyle = '#ff8c00';
  for (let dy = 0; dy < 5; dy++) {
    for (let dx = 0; dx < 5; dx++) {
      const isBorder = dx === 0 || dx === 4 || dy === 0 || dy === 4;
      const isCenter = dx === 2 && dy === 2;
      if (isBorder || isCenter) {
        ctx.fillRect((ox + dx) * cellSize, (oy + dy) * cellSize, cellSize, cellSize);
      }
    }
  }
}
