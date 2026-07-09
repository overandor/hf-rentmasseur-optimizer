import { useEffect, useRef, useState, useCallback } from 'react';
import type { WallState, View, DisplayMode, DisplayModeState } from './types';

const TIZEN_KEY_MAP: Record<string, string> = {
  'ArrowLeft': 'ArrowLeft',
  'ArrowRight': 'ArrowRight',
  'ArrowUp': 'ArrowUp',
  'ArrowDown': 'ArrowDown',
  'Enter': 'Enter',
  'Escape': 'Back',
  'Backspace': 'Back',
  'XF86Back': 'Back',
  'XF86AudioPlay': 'Play',
  'XF86AudioPause': 'Pause',
  'XF86AudioStop': 'Stop',
  'MediaPlay': 'Play',
  'MediaPause': 'Pause',
  'MediaTrackNext': 'Next',
  'MediaTrackPrevious': 'Prev',
  'ColorF0Red': 'Red',
  'ColorF1Green': 'Green',
  'ColorF2Yellow': 'Yellow',
  'ColorF3Blue': 'Blue',
  'ChannelList': 'ChannelList',
  'PreChannel': 'PreChannel',
  'Tools': 'Tools',
  'Info': 'Info',
  'Guide': 'Guide',
  'Menu': 'Menu',
  'Source': 'Source',
  'Exit': 'Exit',
};

function normalizeKey(e: KeyboardEvent): string {
  const mapped = TIZEN_KEY_MAP[e.key];
  if (mapped) return mapped;
  if (e.key === 'Back' || e.key === 'XF86Back') return 'Back';
  return e.key;
}

function registerTizenKeys() {
  try {
    const tizen = (window as any).tizen;
    if (!tizen?.tvinputdevice?.registerKey) return;

    const keys = [
      'ColorF0Red', 'ColorF1Green', 'ColorF2Yellow', 'ColorF3Blue',
      'XF86Back', 'XF86AudioPlay', 'XF86AudioPause', 'XF86AudioStop',
      'MediaPlay', 'MediaPause', 'MediaTrackNext', 'MediaTrackPrevious',
      'ChannelList', 'PreChannel', 'Tools', 'Info', 'Guide', 'Menu', 'Source', 'Exit',
    ];

    try {
      tizen.tvinputdevice.registerKeyBatch(keys);
    } catch {
      for (const key of keys) {
        try { tizen.tvinputdevice.registerKey(key); } catch { }
      }
    }
    console.log('[wall] tizen remote keys registered');
  } catch (e) {
    console.log('[wall] tizen key registration skipped — not on TV');
  }
}

const CACHE_KEY = 'reality-wall-cache';
const TOKEN_KEY = 'reality-wall-token';
const WALL_ID_KEY = 'reality-wall-wall-id';

function loadCache(): WallState | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (raw) return JSON.parse(raw);
  } catch { }
  return null;
}

function saveCache(state: WallState) {
  try {
    const safe = {
      kpis: state.kpis,
      receipts: state.receipts?.map((r: any) => ({
        id: r.id, action: r.action, type: r.type, agent: r.agent,
        source: r.source, timestamp: r.timestamp, verified: r.verified,
        artifact_hash: r.artifact_hash, hash: r.hash,
      })),
      decisions: state.decisions?.map((d: any) => ({
        id: d.id, decision: d.decision, timestamp: d.timestamp, reason: d.reason,
      })),
      experiments: state.experiments?.map((e: any) => ({
        id: e.id, name: e.name, status: e.status, hypothesis: e.hypothesis,
        created_at: e.created_at, verdict: e.verdict,
      })),
      lambdaReceipts: state.lambdaReceipts?.map((r: any) => ({
        id: r.id, intent: r.intent, lambda_score: r.lambda_score,
        transferability: r.transferability, created_at: r.created_at,
        source_hash: r.source_hash, receipt_hash: r.receipt_hash,
      })),
      clientPulse: state.clientPulse ? {
        snapshots: state.clientPulse.snapshots?.map((s: any) => ({
          snapshot_time: s.snapshot_time, ctr: s.ctr, views: s.views,
          contact_clicks: s.contact_clicks,
        })),
        recent_decisions: state.clientPulse.recent_decisions?.map((d: any) => ({
          decision: d.decision, timestamp: d.timestamp,
        })),
      } : null,
      operatorReport: state.operatorReport ? {
        status: state.operatorReport.status,
        proof: state.operatorReport.proof,
        risk: state.operatorReport.risk,
        next_move: state.operatorReport.next_move,
      } : null,
      connected: false,
      lastUpdate: state.lastUpdate,
    };
    localStorage.setItem(CACHE_KEY, JSON.stringify(safe));
  } catch { }
}

function hashPayload(data: string): string {
  const encoder = new TextEncoder();
  const buffer = encoder.encode(data);
  return crypto.subtle.digest('SHA-256', buffer).then((hash) => {
    return Array.from(new Uint8Array(hash)).slice(0, 16).map((b) => b.toString(16).padStart(2, '0')).join('');
  }) as any;
}

let messageCounter = 0;

async function signMessage(msg: any, token: string): Promise<string> {
  const payload = JSON.stringify({ ...msg, token, timestamp: Date.now(), message_id: ++messageCounter });
  const hash = await hashPayload(payload);
  return JSON.stringify({ ...msg, token, timestamp: Date.now(), message_id: messageCounter, payload_hash: hash });
}

export function useWallState(serverUrl: string) {
  const cached = loadCache();
  const [state, setState] = useState<WallState>(cached ?? {
    kpis: null,
    receipts: [],
    decisions: [],
    experiments: [],
    lambdaReceipts: [],
    clientPulse: null,
    operatorReport: null,
    connected: false,
    lastUpdate: 0,
  });
  const [spotlight, setSpotlight] = useState<{ cardId: string; cardType: string; pushedBy: string } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tokenRef = useRef<string>(localStorage.getItem(TOKEN_KEY) || '');
  const wallIdRef = useRef<string>(localStorage.getItem(WALL_ID_KEY) || '');

  useEffect(() => {
    registerTizenKeys();
  }, []);

  useEffect(() => {
    let cancelled = false;

    function connect() {
      if (cancelled) return;
      const token = tokenRef.current;
      const url = token ? `${serverUrl}?token=${encodeURIComponent(token)}` : serverUrl;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[wall] connected');
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'authenticated' && msg.wall_id) {
            wallIdRef.current = msg.wall_id;
            localStorage.setItem(WALL_ID_KEY, msg.wall_id);
            console.log('[wall] authenticated — wall:', msg.wall_id, 'perms:', msg.permissions);
          } else if (msg.type === 'auth_required' || msg.type === 'auth_rejected' || msg.type === 'auth_expired') {
            console.log('[wall] auth required — need pairing');
            tokenRef.current = '';
            localStorage.removeItem(TOKEN_KEY);
          } else if (msg.type === 'state' && msg.data) {
            setState(msg.data);
            saveCache(msg.data);
          } else if (msg.type === 'spotlight' && msg.data) {
            setSpotlight(msg.data);
          } else if (msg.type === 'spotlight_cleared') {
            setSpotlight(null);
          }
        } catch (e) {
          console.error('[wall] parse error:', e);
        }
      };

      ws.onclose = () => {
        console.log('[wall] disconnected — retrying in 3s');
        wsRef.current = null;
        if (!cancelled) {
          reconnectRef.current = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        console.error('[wall] connection error');
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [serverUrl]);

  const sendAuthMessage = useCallback((msg: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      signMessage(msg, tokenRef.current).then((signed) => {
        wsRef.current?.send(signed);
      }).catch(() => {
        wsRef.current?.send(JSON.stringify({ ...msg, token: tokenRef.current, timestamp: Date.now() }));
      });
    }
  }, []);

  const sendCommand = useCallback((action: string, args?: any) => {
    sendAuthMessage({ type: 'command', action, args });
  }, [sendAuthMessage]);

  const refresh = useCallback(() => {
    sendAuthMessage({ type: 'refresh' });
  }, [sendAuthMessage]);

  const pushSpotlight = useCallback((cardId: string, cardType: string, pushedBy: string) => {
    sendAuthMessage({ type: 'push_spotlight', cardId, cardType, pushedBy });
  }, [sendAuthMessage]);

  const clearSpotlight = useCallback(() => {
    sendAuthMessage({ type: 'clear_spotlight' });
    setSpotlight(null);
  }, [sendAuthMessage]);

  const setPairingToken = useCallback((token: string) => {
    tokenRef.current = token;
    localStorage.setItem(TOKEN_KEY, token);
  }, []);

  return { state, sendCommand, refresh, spotlight, pushSpotlight, clearSpotlight, setPairingToken, wallId: wallIdRef.current };
}

export function useRemoteNavigation(
  views: View[],
  currentView: View,
  setCurrentView: (v: View) => void,
  cardCount: number,
  refresh?: () => void,
) {
  const [focusedCard, setFocusedCard] = useState(0);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const key = normalizeKey(e);
      switch (key) {
        case 'ArrowLeft':
          if (focusedCard > 0) setFocusedCard(focusedCard - 1);
          break;
        case 'ArrowRight':
          if (focusedCard < cardCount - 1) setFocusedCard(focusedCard + 1);
          break;
        case 'ArrowUp':
          const curIdx = views.indexOf(currentView);
          if (curIdx > 0) {
            setCurrentView(views[curIdx - 1]);
            setFocusedCard(0);
          }
          break;
        case 'ArrowDown':
          const curIdx2 = views.indexOf(currentView);
          if (curIdx2 < views.length - 1) {
            setCurrentView(views[curIdx2 + 1]);
            setFocusedCard(0);
          }
          break;
        case 'Enter':
          break;
        case 'Back':
          if (currentView !== 'overview') {
            setCurrentView('overview');
            setFocusedCard(0);
          }
          break;
        case 'Red':
          refresh?.();
          break;
        case 'Green':
          const curIdx3 = views.indexOf(currentView);
          if (curIdx3 < views.length - 1) {
            setCurrentView(views[curIdx3 + 1]);
            setFocusedCard(0);
          }
          break;
        case 'Yellow':
          const curIdx4 = views.indexOf(currentView);
          if (curIdx4 > 0) {
            setCurrentView(views[curIdx4 - 1]);
            setFocusedCard(0);
          }
          break;
        case 'Blue':
          setCurrentView('overview');
          setFocusedCard(0);
          break;
        case 'Play':
        case 'Pause':
          refresh?.();
          break;
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [views, currentView, setCurrentView, focusedCard, cardCount, refresh]);

  // Touch navigation for Samsung TV digitizer
  useEffect(() => {
    let touchStartX = 0;
    let touchStartY = 0;
    let touchStartTime = 0;
    const SWIPE_THRESHOLD = 50;
    const TAP_THRESHOLD = 200;

    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length > 0) {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchStartTime = Date.now();
      }
    };

    const onTouchEnd = (e: TouchEvent) => {
      if (e.changedTouches.length === 0) return;
      const dx = e.changedTouches[0].clientX - touchStartX;
      const dy = e.changedTouches[0].clientY - touchStartY;
      const dt = Date.now() - touchStartTime;
      const absDx = Math.abs(dx);
      const absDy = Math.abs(dy);

      // Tap — navigate to next view
      if (dt < TAP_THRESHOLD && absDx < 20 && absDy < 20) {
        const curIdx = views.indexOf(currentView);
        if (curIdx < views.length - 1) {
          setCurrentView(views[curIdx + 1]);
          setFocusedCard(0);
        } else {
          setCurrentView(views[0]);
          setFocusedCard(0);
        }
        return;
      }

      // Swipe horizontal — card navigation
      if (absDx > absDy && absDx > SWIPE_THRESHOLD) {
        if (dx > 0 && focusedCard > 0) {
          setFocusedCard(focusedCard - 1);
        } else if (dx < 0 && focusedCard < cardCount - 1) {
          setFocusedCard(focusedCard + 1);
        }
        return;
      }

      // Swipe vertical — view navigation
      if (absDy > absDx && absDy > SWIPE_THRESHOLD) {
        const curIdx = views.indexOf(currentView);
        if (dy < 0 && curIdx < views.length - 1) {
          setCurrentView(views[curIdx + 1]);
          setFocusedCard(0);
        } else if (dy > 0 && curIdx > 0) {
          setCurrentView(views[curIdx - 1]);
          setFocusedCard(0);
        }
        return;
      }
    };

    window.addEventListener('touchstart', onTouchStart, { passive: true });
    window.addEventListener('touchend', onTouchEnd, { passive: true });
    return () => {
      window.removeEventListener('touchstart', onTouchStart);
      window.removeEventListener('touchend', onTouchEnd);
    };
  }, [views, currentView, setCurrentView, focusedCard, cardCount]);

  return { focusedCard, setFocusedCard };
}

export function useDisplayMode() {
  const [displayMode, setDisplayMode] = useState<DisplayModeState>({
    mode: 'auto',
    screenSharingActive: false,
    remoteManagementActive: true,
    conflict: false,
    lastSwitch: 0,
  });

  useEffect(() => {
    function detectTizenDisplay() {
      try {
        const tizen = (window as any).tizen;
        if (!tizen) return;

        // Check if screen mirroring / Smart View is active
        // Tizen exposes this via the application manager or display API
        let screenSharing = false;
        try {
          const appCtx = tizen.application.getCurrentApplication();
          // If we're not the active app, screen sharing likely took over
          screenSharing = false;
        } catch { }

        // Check for TTM (Tizen Target Manager) remote session
        let remoteMgmt = true;
        try {
          // If webapis are available, check display state
          const webapis = (window as any).webapis;
          if (webapis?.productinfo?.isTvmEnabled?.() === false) {
            remoteMgmt = false;
          }
        } catch { }

        setDisplayMode(prev => ({
          ...prev,
          screenSharingActive: screenSharing,
          remoteManagementActive: remoteMgmt,
          conflict: screenSharing && remoteMgmt,
        }));
      } catch {
        // Not on Tizen — no conflict
      }
    }

    detectTizenDisplay();
    const interval = setInterval(detectTizenDisplay, 2000);
    return () => clearInterval(interval);
  }, []);

  // Listen for visibility change — when screen sharing takes over, our app gets hidden
  useEffect(() => {
    const onVisibility = () => {
      const hidden = document.hidden;
      setDisplayMode(prev => {
        const screenSharing = hidden;
        const remoteMgmt = !hidden;
        return {
          ...prev,
          screenSharingActive: screenSharing,
          remoteManagementActive: remoteMgmt,
          conflict: false, // can't conflict if we're hidden
          mode: hidden ? 'cast' : prev.mode === 'cast' ? 'dashboard' : prev.mode,
          lastSwitch: hidden !== prev.screenSharingActive ? Date.now() : prev.lastSwitch,
        };
      });
    };

    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);

  const switchMode = useCallback((mode: DisplayMode) => {
    setDisplayMode(prev => {
      if (mode === 'cast') {
        // Release remote management — Samsung only allows one display consumer
        return {
          ...prev,
          mode: 'cast',
          screenSharingActive: true,
          remoteManagementActive: false,
          conflict: false,
          lastSwitch: Date.now(),
        };
      } else if (mode === 'dashboard') {
        // Reclaim display for dashboard — screen sharing must stop
        return {
          ...prev,
          mode: 'dashboard',
          screenSharingActive: false,
          remoteManagementActive: true,
          conflict: false,
          lastSwitch: Date.now(),
        };
      } else {
        // auto — let visibility determine
        return {
          ...prev,
          mode: 'auto',
          conflict: false,
          lastSwitch: Date.now(),
        };
      }
    });
  }, []);

  return { displayMode, switchMode };
}
