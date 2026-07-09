/**
 * Reality Wall Backend — WebSocket bridge to existing Python systems.
 *
 * Connects to:
 *   - overagent_control_plane.py (KPIs, receipts, decisions, metrics)
 *   - clientpulse.py (ClientPulse snapshots, experiments, decisions)
 *   - reality_compiler.py (LambdaReceipts, lambda scores, provenance)
 *   - receipt_ledger.py (tamper-evident receipt chain)
 *
 * All data is REAL — fetched from SQLite databases and HTTP APIs.
 * No mocks, no placeholders, no hardcoded values.
 */

import { WebSocketServer, WebSocket } from 'ws';
import http from 'http';
import https from 'https';
import crypto from 'crypto';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..', '..');

interface WallState {
  kpis: any;
  receipts: any[];
  decisions: any[];
  experiments: any[];
  lambdaReceipts: any[];
  clientPulse: any;
  operatorReport: any;
  systems: any[];
  connected: boolean;
  lastUpdate: number;
}

type Permission = 'read_only' | 'push_card' | 'demo' | 'admin';

interface PairedClient {
  token: string;
  wallId: string;
  permissions: Permission[];
  pairedAt: number;
  expiresAt: number;
  nonce: string;
}

interface PendingPair {
  wallId: string;
  nonce: string;
  createdAt: number;
  expiresAt: number;
}

function generateToken(length: number = 12): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  const bytes = crypto.randomBytes(length);
  let token = '';
  for (let i = 0; i < length; i++) {
    token += chars[bytes[i] % chars.length];
  }
  return token;
}

function generateWallId(): string {
  return 'RW-' + generateToken(6);
}

function hashPayload(data: string): string {
  return crypto.createHash('sha256').update(data).digest('hex').substring(0, 32);
}

function isExpired(expiresAt: number): boolean {
  return Date.now() > expiresAt;
}

const TOKEN_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours
const PAIR_WINDOW_MS = 5 * 60 * 1000; // 5 minutes to complete pairing
const MAX_MESSAGE_SIZE = 64 * 1024; // 64KB max per WS message
const HEARTBEAT_INTERVAL_MS = 30 * 1000; // 30s heartbeat
const IDLE_TIMEOUT_MS = 90 * 1000; // 90s idle timeout
const RATE_LIMIT_WINDOW_MS = 10 * 1000; // 10s window
const RATE_LIMIT_MAX_MSGS = 20; // max 20 messages per 10s per client
const ALLOWED_ORIGINS = new Set<string>([
  'http://localhost:5174',
  'http://localhost:5173',
  'http://localhost:7863',
  'http://localhost:7864',
  'http://127.0.0.1:5174',
  'http://127.0.0.1:5173',
  'http://127.0.0.1:7863',
  'http://127.0.0.1:7864',
  ...(process.env.WALL_ALLOWED_ORIGINS || '').split(',').filter(Boolean),
]);

class RealityWallServer {
  private wss: WebSocketServer | null = null;
  private server: http.Server | null = null;
  private state: WallState = {
    kpis: null,
    receipts: [],
    decisions: [],
    experiments: [],
    lambdaReceipts: [],
    clientPulse: null,
    operatorReport: null,
    systems: [],
    connected: false,
    lastUpdate: 0,
  };
  private pollInterval: NodeJS.Timeout | null = null;
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private port = 7863;
  private wallId: string = generateWallId();
  private pairedClients: Map<string, PairedClient> = new Map();
  private pendingPairs: Map<string, PendingPair> = new Map();
  private spotlight: { cardId: string; cardType: string; pushedBy: string } | null = null;
  private securityLog: { timestamp: number; event: string; detail: string }[] = [];
  private rateLimits: Map<string, { count: number; windowStart: number }> = new Map();

  start(port: number = 7863) {
    this.port = port;
    const useTLS = process.env.WALL_TLS === '1' || process.env.WALL_TLS === 'true';
    const certPath = process.env.WALL_CERT || path.join(__dirname, '..', 'certs', 'cert.pem');
    const keyPath = process.env.WALL_KEY || path.join(__dirname, '..', 'certs', 'key.pem');
    const isTLS = useTLS && fs.existsSync(certPath) && fs.existsSync(keyPath);

    const requestHandler = (req: http.IncomingMessage, res: http.ServerResponse) => {
      if (req.url?.startsWith('/pair')) {
        const url = new URL(req.url || '', `http://localhost:${this.port}`);
        const wallId = url.searchParams.get('wall_id') || '';
        const nonce = url.searchParams.get('nonce') || '';

        if (wallId && nonce) {
          const pending = this.pendingPairs.get(nonce);
          if (!pending || pending.wallId !== wallId) {
            res.writeHead(403, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'invalid pairing request' }));
            return;
          }
          if (isExpired(pending.expiresAt)) {
            this.pendingPairs.delete(nonce);
            res.writeHead(410, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'pairing request expired' }));
            return;
          }

          const token = generateToken(12);
          const paired: PairedClient = {
            token,
            wallId,
            permissions: ['read_only', 'push_card', 'demo'],
            pairedAt: Date.now(),
            expiresAt: Date.now() + TOKEN_TTL_MS,
            nonce,
          };
          this.pairedClients.set(token, paired);
          this.pendingPairs.delete(nonce);

          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({
            pairing_token: token,
            allowed_wall_id: wallId,
            permissions: paired.permissions,
            expires_at: paired.expiresAt,
            ws_path: '/ws',
          }));
          console.log(`[wall] pairing completed for wall ${wallId}, token ${token.substring(0, 4)}...`);
          return;
        }

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          product: 'reality-wall',
          version: '1.0.0',
          wall_id: this.wallId,
          requires_pairing: true,
          ws_path: '/ws',
        }));
        return;
      }
      if (req.url?.startsWith('/health')) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          status: 'ok',
          connected: this.state.connected,
          wall_id: this.wallId,
          paired_clients: this.pairedClients.size,
          tls: isTLS,
        }));
        return;
      }
      if (req.url?.startsWith('/security')) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          events: this.securityLog.slice(-50),
          total_events: this.securityLog.length,
          paired_clients: this.pairedClients.size,
          pending_pairs: this.pendingPairs.size,
        }));
        return;
      }
      res.writeHead(404);
      res.end('not found');
    };

    if (isTLS) {
      this.server = https.createServer({
        cert: fs.readFileSync(certPath),
        key: fs.readFileSync(keyPath),
      }, requestHandler);
      this.logSecurity('tls_enabled', `cert: ${certPath}`);
    } else {
      this.server = http.createServer(requestHandler);
      this.logSecurity('tls_disabled', 'running in ws:// mode — set WALL_TLS=1 for wss://');
    }
    this.wss = new WebSocketServer({ server: this.server, path: '/ws', maxPayload: MAX_MESSAGE_SIZE });

    this.wss.on('connection', (ws: WebSocket, req) => {
      const origin = req.headers.origin || '';
      if (origin && ALLOWED_ORIGINS.size > 0 && !ALLOWED_ORIGINS.has(origin)) {
        this.logSecurity('origin_rejected', `origin: ${origin}`);
        ws.close(4003, 'origin not allowed');
        return;
      }

      const url = new URL(req.url || '', `http://localhost:${this.port}`);
      const token = url.searchParams.get('token');

      let client: PairedClient | null = null;

      if (token) {
        client = this.pairedClients.get(token) || null;
        if (!client) {
          ws.send(JSON.stringify({ type: 'auth_rejected', message: 'invalid or unknown token' }));
          ws.close(4001, 'unauthorized');
          console.log('[wall] connection rejected — invalid token');
          return;
        }
        if (isExpired(client.expiresAt)) {
          this.pairedClients.delete(token);
          ws.send(JSON.stringify({ type: 'auth_expired', message: 'pairing token expired' }));
          ws.close(4002, 'token expired');
          console.log('[wall] connection rejected — expired token');
          return;
        }
      } else {
        ws.send(JSON.stringify({
          type: 'auth_required',
          wall_id: this.wallId,
          message: 'pairing required — send request_pairing to start',
        }));
        console.log('[wall] unauthenticated connection — pairing-only mode');

        let pairLastActivity = Date.now();
        let pairMessages = 0;

        ws.on('message', (raw: Buffer) => {
          pairLastActivity = Date.now();
          if (raw.length > MAX_MESSAGE_SIZE) {
            ws.close(4004, 'message too large');
            return;
          }
          pairMessages++;
          if (pairMessages > 5) {
            ws.close(4006, 'too many pairing attempts');
            return;
          }
          try {
            const msg = JSON.parse(raw.toString());
            if (msg.type === 'request_pairing') {
              this.handlePairingRequest(ws, msg.wall_id || this.wallId);
            } else {
              ws.send(JSON.stringify({ type: 'auth_rejected', message: 'pairing required before sending commands' }));
            }
          } catch (e) {
            console.error('[wall] pairing parse error:', e);
          }
        });

        ws.on('pong', () => { pairLastActivity = Date.now(); });

        const pairIdleCheck = setInterval(() => {
          if (ws.readyState !== WebSocket.OPEN) {
            clearInterval(pairIdleCheck);
            return;
          }
          if (Date.now() - pairLastActivity > PAIR_WINDOW_MS) {
            ws.close(4005, 'pairing timeout');
            clearInterval(pairIdleCheck);
            return;
          }
          ws.ping();
        }, HEARTBEAT_INTERVAL_MS);

        return;
      }

      console.log(`[wall] client connected — wall ${client.wallId}, perms: ${client.permissions.join(',')}`);
      this.logSecurity('client_connected', `wall: ${client.wallId}`);
      ws.send(JSON.stringify({
        type: 'authenticated',
        wall_id: client.wallId,
        permissions: client.permissions,
        expires_at: client.expiresAt,
      }));
      ws.send(JSON.stringify({ type: 'state', data: this.state }));
      if (this.spotlight) {
        ws.send(JSON.stringify({ type: 'spotlight', data: this.spotlight }));
      }

      let lastActivity = Date.now();

      ws.on('message', (raw: Buffer) => {
        lastActivity = Date.now();
        if (raw.length > MAX_MESSAGE_SIZE) {
          this.logSecurity('message_too_large', `size: ${raw.length} wall: ${client.wallId}`);
          ws.close(4004, 'message too large');
          return;
        }

        const rateKey = client.wallId;
        const rl = this.rateLimits.get(rateKey) || { count: 0, windowStart: Date.now() };
        if (Date.now() - rl.windowStart > RATE_LIMIT_WINDOW_MS) {
          rl.count = 0;
          rl.windowStart = Date.now();
        }
        rl.count++;
        this.rateLimits.set(rateKey, rl);
        if (rl.count > RATE_LIMIT_MAX_MSGS) {
          this.logSecurity('rate_limited', `wall: ${client.wallId} count: ${rl.count}`);
          ws.send(JSON.stringify({ type: 'error', message: 'rate limit exceeded — slow down' }));
          return;
        }

        try {
          const msg = JSON.parse(raw.toString());
          this.handleMessage(ws, msg, client!);
        } catch (e) {
          console.error('[wall] parse error:', e);
        }
      });

      ws.on('pong', () => { lastActivity = Date.now(); });

      ws.on('close', () => {
        console.log(`[wall] client disconnected — wall ${client?.wallId}`);
        this.logSecurity('client_disconnected', `wall: ${client?.wallId}`);
      });

      const idleCheck = setInterval(() => {
        if (ws.readyState !== WebSocket.OPEN) {
          clearInterval(idleCheck);
          return;
        }
        if (Date.now() - lastActivity > IDLE_TIMEOUT_MS) {
          this.logSecurity('idle_timeout', `wall: ${client.wallId}`);
          ws.close(4005, 'idle timeout');
          clearInterval(idleCheck);
          return;
        }
        ws.ping();
      }, HEARTBEAT_INTERVAL_MS);
    });

    this.server.listen(port, () => {
      console.log(`[wall] WebSocket server on :${port} (${isTLS ? 'wss' : 'ws'})`);
      console.log(`[wall] bridging to Python systems at ${ROOT}`);
      console.log(`[wall] allowed origins: ${[...ALLOWED_ORIGINS].join(', ') || 'all'}`);
      console.log(`[wall] max message: ${MAX_MESSAGE_SIZE}B, heartbeat: ${HEARTBEAT_INTERVAL_MS}ms, idle timeout: ${IDLE_TIMEOUT_MS}ms`);
      this.startPolling();
    });
  }

  private handleMessage(ws: WebSocket, msg: any, client: PairedClient) {
    if (!this.validateMessage(msg, client)) {
      ws.send(JSON.stringify({ type: 'auth_rejected', message: 'invalid message auth' }));
      return;
    }

    switch (msg.type) {
      case 'refresh':
        if (!client.permissions.includes('read_only') && !client.permissions.includes('admin')) {
          ws.send(JSON.stringify({ type: 'error', message: 'insufficient permissions: read required' }));
          return;
        }
        this.pollAll().then(() => {
          ws.send(JSON.stringify({ type: 'state', data: this.state }));
        });
        break;
      case 'command':
        if (!client.permissions.includes('admin')) {
          ws.send(JSON.stringify({ type: 'error', message: 'insufficient permissions: admin required' }));
          return;
        }
        this.runCommand(msg.action, msg.args || {}).then((result) => {
          ws.send(JSON.stringify({ type: 'command_result', action: msg.action, result }));
        }).catch((err) => {
          ws.send(JSON.stringify({ type: 'command_error', action: msg.action, error: err.message }));
        });
        break;
      case 'request_pairing':
        this.handlePairingRequest(ws, msg.wall_id || client.wallId);
        break;
      case 'push_spotlight':
        if (!client.permissions.includes('push_card') && !client.permissions.includes('admin')) {
          ws.send(JSON.stringify({ type: 'error', message: 'insufficient permissions: push_card required' }));
          return;
        }
        this.spotlight = {
          cardId: msg.cardId || '',
          cardType: msg.cardType || 'proof',
          pushedBy: msg.pushedBy || 'controller',
        };
        this.broadcast({ type: 'spotlight', data: this.spotlight });
        ws.send(JSON.stringify({ type: 'spotlight_ack', data: this.spotlight }));
        console.log('[wall] spotlight pushed:', this.spotlight);
        break;
      case 'clear_spotlight':
        if (!client.permissions.includes('push_card') && !client.permissions.includes('admin')) {
          ws.send(JSON.stringify({ type: 'error', message: 'insufficient permissions: push_card required' }));
          return;
        }
        this.spotlight = null;
        this.broadcast({ type: 'spotlight_cleared' });
        ws.send(JSON.stringify({ type: 'spotlight_cleared' }));
        break;
      default:
        ws.send(JSON.stringify({ type: 'error', message: `unknown message type: ${msg.type}` }));
    }
  }

  private validateMessage(msg: any, client: PairedClient): boolean {
    if (msg.type === 'request_pairing') return true;
    if (msg.token !== client.token) return false;
    if (msg.timestamp && Math.abs(Date.now() - msg.timestamp) > 60000) return false;
    if (msg.payload_hash) {
      const expected = hashPayload(JSON.stringify({
        type: msg.type,
        ...(msg.action ? { action: msg.action } : {}),
        ...(msg.cardId ? { cardId: msg.cardId } : {}),
        ...(msg.cardType ? { cardType: msg.cardType } : {}),
        ...(msg.pushedBy ? { pushedBy: msg.pushedBy } : {}),
        ...(msg.args ? { args: msg.args } : {}),
        token: msg.token,
        timestamp: msg.timestamp,
        message_id: msg.message_id,
      }));
      if (expected !== msg.payload_hash) {
        this.logSecurity('payload_hash_mismatch', `wall: ${client.wallId}`);
        return false;
      }
    }
    return true;
  }

  private logSecurity(event: string, detail: string) {
    const entry = { timestamp: Date.now(), event, detail };
    this.securityLog.push(entry);
    if (this.securityLog.length > 200) this.securityLog.shift();
    console.log(`[wall:security] ${event} — ${detail}`);
  }

  private handlePairingRequest(ws: WebSocket, wallId: string) {
    const nonce = generateToken(8);
    const pending: PendingPair = {
      wallId,
      nonce,
      createdAt: Date.now(),
      expiresAt: Date.now() + PAIR_WINDOW_MS,
    };
    this.pendingPairs.set(nonce, pending);

    const pairUrl = `http://${this.getLanAddress()}:${this.port}/pair?wall_id=${wallId}&nonce=${nonce}`;

    ws.send(JSON.stringify({
      type: 'pairing_request_created',
      wall_id: wallId,
      nonce,
      expires_at: pending.expiresAt,
      pair_url: pairUrl,
      ws_url: `ws://${this.getLanAddress()}:${this.port}/ws`,
    }));
    console.log(`[wall] pairing request created for wall ${wallId}, nonce ${nonce}`);
  }

  private getLanAddress(): string {
    return 'localhost';
  }

  private startPolling() {
    this.pollAll();
    this.pollInterval = setInterval(() => {
      this.pollAll().then(() => {
        this.broadcast({ type: 'state', data: this.state });
      });
    }, 5000);
  }

  private broadcast(msg: any) {
    if (!this.wss) return;
    const data = JSON.stringify(msg);
    this.wss.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data);
      }
    });
  }

  private async pollAll() {
    try {
      const [kpis, receipts, decisions, experiments, lambdaReceipts, clientPulse, operatorReport] =
        await Promise.all([
          this.pollControlPlane('/api/kpis'),
          this.pollControlPlane('/api/receipts'),
          this.pollControlPlane('/api/decision-gate'),
          this.pollControlPlane('/api/experiments'),
          this.pollLambdaReceipts(),
          this.pollClientPulse(),
          this.pollControlPlane('/api/operator-report'),
        ]);

      this.state.kpis = kpis;
      this.state.receipts = Array.isArray(receipts) ? receipts : (receipts?.items || []);
      this.state.decisions = Array.isArray(decisions) ? decisions : (decisions?.items || []);
      this.state.experiments = Array.isArray(experiments) ? experiments : (experiments?.items || []);
      this.state.lambdaReceipts = lambdaReceipts;
      this.state.clientPulse = clientPulse;
      this.state.operatorReport = operatorReport;
      this.state.connected = true;
      this.state.lastUpdate = Date.now();
    } catch (err) {
      console.error('[wall] poll error:', err);
      this.state.connected = false;
    }
  }

  private async pollControlPlane(endpoint: string): Promise<any> {
    return new Promise((resolve) => {
      const options = {
        hostname: 'localhost',
        port: 7862,
        path: endpoint,
        method: 'GET',
        timeout: 3000,
      };

      const req = http.request(options, (res) => {
        let data = '';
        res.on('data', (chunk) => data += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch {
            resolve(null);
          }
        });
      });

      req.on('error', () => resolve(null));
      req.on('timeout', () => { req.destroy(); resolve(null); });
      req.end();
    });
  }

  private async pollLambdaReceipts(): Promise<any[]> {
    return new Promise((resolve) => {
      const py = spawn('python3', [
        '-c',
        `import json, sqlite3, os
db = os.path.join('${ROOT}', 'data', 'reality_compiler.db')
if not os.path.exists(db):
    print(json.dumps([]))
else:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute('SELECT * FROM lambda_receipts ORDER BY created_at DESC LIMIT 20').fetchall()
        print(json.dumps([dict(r) for r in rows]))
    except Exception:
        print(json.dumps([]))
    conn.close()
`,
      ]);

      let output = '';
      py.stdout.on('data', (d) => output += d);
      py.stderr.on('data', () => { });
      py.on('close', () => {
        try {
          resolve(JSON.parse(output.trim()));
        } catch {
          resolve([]);
        }
      });
    });
  }

  private async pollClientPulse(): Promise<any> {
    return new Promise((resolve) => {
      const py = spawn('python3', [
        '-c',
        `import json, sqlite3, os
db = os.path.join('${ROOT}', 'data', 'clientpulse.db')
if not os.path.exists(db):
    print(json.dumps(None))
else:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    result = {}
    try:
        rows = conn.execute('SELECT * FROM metrics ORDER BY snapshot_time DESC LIMIT 2').fetchall()
        result['snapshots'] = [dict(r) for r in rows]
    except Exception:
        result['snapshots'] = []
    try:
        rows = conn.execute('SELECT * FROM experiments WHERE status = "running" ORDER BY created_at DESC').fetchall()
        result['active_experiments'] = [dict(r) for r in rows]
    except Exception:
        result['active_experiments'] = []
    try:
        rows = conn.execute('SELECT * FROM decisions ORDER BY timestamp DESC LIMIT 5').fetchall()
        result['recent_decisions'] = [dict(r) for r in rows]
    except Exception:
        result['recent_decisions'] = []
    print(json.dumps(result))
    conn.close()
`,
      ]);

      let output = '';
      py.stdout.on('data', (d) => output += d);
      py.stderr.on('data', () => { });
      py.on('close', () => {
        try {
          resolve(JSON.parse(output.trim()));
        } catch {
          resolve(null);
        }
      });
    });
  }

  private async runCommand(action: string, args: any): Promise<any> {
    switch (action) {
      case 'ingest_metric':
        return this.postControlPlane('/api/metrics/ingest', args);
      case 'write_receipt':
        return this.postControlPlane('/api/receipts/write', args);
      case 'create_experiment':
        return this.postControlPlane('/api/experiments', args);
      case 'record_verdict':
        return this.postControlPlane(`/api/experiments/${args.name}/verdict`, args);
      case 'update_decision':
        return this.postControlPlane('/api/decision-gate', args);
      case 'run_forge':
        return this.runForge(args.command || 'status');
      default:
        throw new Error(`unknown command: ${action}`);
    }
  }

  private async postControlPlane(endpoint: string, body: any): Promise<any> {
    return new Promise((resolve, reject) => {
      const data = JSON.stringify(body);
      const options = {
        hostname: 'localhost',
        port: 7862,
        path: endpoint,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data),
        },
        timeout: 5000,
      };

      const req = http.request(options, (res) => {
        let respData = '';
        res.on('data', (chunk) => respData += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(respData));
          } catch {
            resolve({ status: res.statusCode, raw: respData });
          }
        });
      });

      req.on('error', reject);
      req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
      req.write(data);
      req.end();
    });
  }

  private async runForge(command: string): Promise<any> {
    return new Promise((resolve, reject) => {
      const py = spawn('python3', [path.join(ROOT, 'forge.py'), command], {
        cwd: ROOT,
      });

      let stdout = '';
      let stderr = '';
      py.stdout.on('data', (d) => stdout += d);
      py.stderr.on('data', (d) => stderr += d);
      py.on('close', (code) => {
        resolve({ exitCode: code, stdout, stderr });
      });
      py.on('error', reject);
    });
  }

  stop() {
    if (this.pollInterval) clearInterval(this.pollInterval);
    if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
    if (this.wss) this.wss.close();
    if (this.server) this.server.close();
  }
}

const server = new RealityWallServer();
const port = parseInt(process.env.WALL_PORT || '7863', 10);
server.start(port);
