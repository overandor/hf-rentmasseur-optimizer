/**
 * Screen Cast — captures half the Mac screen and streams it as MJPEG over HTTP.
 * 
 * Usage:
 *   npx tsx server/cast.ts [--left|--right] [--port 7864] [--fps 15] [--quality 80]
 * 
 * The TV's Reality Wall app connects to this endpoint and displays the stream.
 * Uses ffmpeg + avfoundation to capture the screen region.
 */

import http from 'http';
import { spawn, ChildProcess } from 'child_process';
import { execSync } from 'child_process';

const args = process.argv.slice(2);
const side = args.includes('--right') ? 'right' : 'left';
const port = parseInt(args.find(a => a.startsWith('--port='))?.split('=')[1] || '7864', 10);
const fps = parseInt(args.find(a => a.startsWith('--fps='))?.split('=')[1] || '15', 10);
const quality = parseInt(args.find(a => a.startsWith('--quality='))?.split('=')[1] || '80', 10);

function getScreenResolution(): { width: number; height: number } {
  try {
    const output = execSync('system_profiler SPDisplaysDataType 2>/dev/null', { encoding: 'utf-8' });
    const match = output.match(/Resolution:\s*(\d+)\s*x\s*(\d+)/);
    if (match) {
      return { width: parseInt(match[1]), height: parseInt(match[2]) };
    }
  } catch {}
  return { width: 1920, height: 1080 };
}

const screen = getScreenResolution();
const halfWidth = Math.floor(screen.width / 2);
const offsetX = side === 'left' ? 0 : halfWidth;

console.log(`[cast] screen: ${screen.width}x${screen.height}`);
console.log(`[cast] capturing ${side} half: ${halfWidth}x${screen.height} at offset ${offsetX},0`);
console.log(`[cast] streaming MJPEG on :${port} at ${fps}fps quality ${quality}`);

let currentProcess: ChildProcess | null = null;
let currentFrame: Buffer | null = null;
let clients: http.ServerResponse[] = [];

function startCapture() {
  const ffmpegArgs = [
    '-f', 'avfoundation',
    '-framerate', String(fps),
    '-capture_cursor', '1',
    '-i', '2:none',
    '-vf', `crop=${halfWidth}:${screen.height}:${offsetX}:0,scale=1280:-2`,
    '-f', 'mjpeg',
    '-q:v', String(Math.max(2, Math.round(31 - (quality * 29 / 100)))),
    '-fps_mode', 'cfr',
    '-r', String(fps),
    '-an',
    '-',
  ];

  console.log(`[cast] ffmpeg ${ffmpegArgs.join(' ')}`);

  currentProcess = spawn('ffmpeg', ffmpegArgs, { stdio: ['pipe', 'pipe', 'pipe'] });

  let buffer: Buffer[] = [];

  currentProcess.stdout!.on('data', (chunk: Buffer) => {
    buffer.push(chunk);

    const combined = Buffer.concat(buffer);
    const jpegStart = combined.indexOf(Buffer.from([0xFF, 0xD8]));
    const jpegEnd = combined.indexOf(Buffer.from([0xFF, 0xD9]));

    if (jpegStart !== -1 && jpegEnd !== -1 && jpegEnd > jpegStart) {
      const frame = combined.subarray(jpegStart, jpegEnd + 2);
      currentFrame = Buffer.from(frame);
      buffer = [combined.subarray(jpegEnd + 2)];

      const boundary = '--realitywall\r\n';
      const header = `Content-Type: image/jpeg\r\nContent-Length: ${currentFrame.length}\r\n\r\n`;
      const payload = boundary + header;
      const data = Buffer.concat([Buffer.from(payload), currentFrame, Buffer.from('\r\n')]);

      clients = clients.filter((res) => {
        try {
          res.write(data);
          return !res.writableEnded;
        } catch {
          return false;
        }
      });
    }
  });

  currentProcess.stderr!.on('data', (d: Buffer) => {
    const line = d.toString().trim();
    if (line.includes('Error') || line.includes('error')) {
      console.error('[cast] ffmpeg:', line);
    }
  });

  currentProcess.on('close', (code) => {
    console.log(`[cast] ffmpeg exited with code ${code}`);
    currentProcess = null;
    setTimeout(() => {
      if (clients.length > 0) {
        console.log('[cast] restarting capture — clients waiting');
        startCapture();
      }
    }, 1000);
  });
}

const server = http.createServer((req, res) => {
  if (req.url === '/stream') {
    res.writeHead(200, {
      'Content-Type': 'multipart/x-mixed-replace; boundary=realitywall',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      'Connection': 'keep-alive',
    });
    res.write('--realitywall\r\n');
    clients.push(res);

    if (!currentProcess) {
      startCapture();
    }

    req.on('close', () => {
      clients = clients.filter((c) => c !== res);
      console.log(`[cast] client disconnected — ${clients.length} remaining`);
      if (clients.length === 0 && currentProcess) {
        console.log('[cast] no clients — stopping capture');
        currentProcess.kill('SIGTERM');
        currentProcess = null;
      }
    });
    return;
  }

  if (req.url === '/status') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      active: currentProcess !== null,
      clients: clients.length,
      side,
      resolution: `${halfWidth}x${screen.height}`,
      fps,
      quality,
    }));
    return;
  }

  if (req.url === '/' || req.url === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(`<!DOCTYPE html>
<html><head><title>Reality Wall Cast</title>
<style>body{margin:0;background:#000;display:flex;align-items:center;justify-content:center;height:100vh}img{width:100%;height:100%;object-fit:contain}</style>
</head><body>
<img src="/stream" alt="cast" />
</body></html>`);
    return;
  }

  res.writeHead(404);
  res.end('not found');
});

server.listen(port, () => {
  console.log(`[cast] MJPEG stream ready at http://localhost:${port}/stream`);
  console.log(`[cast] preview at http://localhost:${port}/`);
  console.log(`[cast] status at http://localhost:${port}/status`);
});
