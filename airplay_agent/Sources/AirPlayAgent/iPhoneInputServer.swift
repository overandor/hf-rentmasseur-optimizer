import Foundation
import Network

final class iPhoneInputServer {
    private var listener: NWListener?
    private let queue = DispatchQueue(label: "iphone.http")
    private let port: UInt16
    private let wsPort: UInt16
    private var html: String { """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>FitArena Remote</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #111; color: #fff; font-family: -apple-system, sans-serif; padding: 16px; max-width: 600px; margin: 0 auto; }
h1 { font-size: 22px; text-align: center; margin-bottom: 4px; }
h2 { font-size: 16px; margin-bottom: 8px; }
h3 { font-size: 14px; margin-bottom: 6px; }
.status { text-align: center; font-size: 13px; color: #888; margin-bottom: 12px; }
.connected { color: #4caf50; }
.disconnected { color: #f44336; }
.section { background: #222; border-radius: 12px; padding: 14px; margin-bottom: 12px; }
.btn { background: #0a84ff; color: #fff; border: none; padding: 14px 20px; border-radius: 10px; font-size: 16px; width: 100%; margin-bottom: 8px; cursor: pointer; }
.btn:active { transform: scale(0.97); }
.btn:disabled { opacity: 0.4; }
.btn-orange { background: #ff9500; }
.btn-green { background: #34c759; }
.btn-red { background: #ff3b30; }
.btn-purple { background: #af52de; }
.btn-gray { background: #48484a; }
input { background: #333; border: 1px solid #555; color: #fff; border-radius: 8px; padding: 12px; font-size: 16px; width: 100%; margin-bottom: 8px; }
.camera-box video { width: 100%; border-radius: 8px; }
.motion-data { color: #4caf50; font-family: monospace; font-size: 12px; }
.vote-btn { padding: 14px; margin-bottom: 6px; border-radius: 10px; border: none; font-size: 15px; font-weight: bold; width: 100%; color: #fff; cursor: pointer; }
.agent-status { display: flex; align-items: center; gap: 8px; padding: 8px; border-radius: 8px; margin-bottom: 6px; }
.agent-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.agent-name { font-size: 13px; font-weight: bold; flex: 1; }
.agent-score { font-size: 12px; color: #aaa; }
.agent-output { font-size: 11px; color: #ccc; max-height: 60px; overflow: hidden; line-height: 1.3; }
.round-info { text-align: center; font-size: 13px; color: #aaa; margin-bottom: 8px; }
.exercise-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 8px; }
.exercise-btn { background: #333; border: 1px solid #555; color: #fff; padding: 10px; border-radius: 8px; font-size: 14px; cursor: pointer; }
.exercise-btn:active { background: #444; }
.exercise-btn.active { background: #0a84ff; border-color: #0a84ff; }
</style>
</head>
<body>
<h1>🏋️ FitArena</h1>
<div id="status" class="status disconnected">Connecting to Mac...</div>

<div class="section">
<h3>🎯 Exercise</h3>
<div class="exercise-grid">
<button class="exercise-btn active" onclick="setExercise('squats')">Squats</button>
<button class="exercise-btn" onclick="setExercise('pushups')">Push-ups</button>
<button class="exercise-btn" onclick="setExercise('plank')">Plank</button>
<button class="exercise-btn" onclick="setExercise('lunges')">Lunges</button>
<button class="exercise-btn" onclick="setExercise('burpees')">Burpees</button>
<button class="exercise-btn" onclick="setExercise('situps')">Sit-ups</button>
</div>
<input type="text" id="exerciseInput" placeholder="Custom exercise..." oninput="setExercise(this.value)">
</div>

<div class="section">
<h3>🤖 Agent Arena</h3>
<div id="roundInfo" class="round-info">Round 0 — Ready</div>
<button class="btn btn-green" id="startBtn" onclick="sendControl('startRound')">▶ Start Round</button>
<button class="btn btn-red" id="stopBtn" onclick="sendControl('stopRound')" disabled>⏹ Stop</button>
<button class="btn btn-gray" onclick="sendControl('resetScores')">↺ Reset Scores</button>
<div id="agentStatus" style="margin-top:10px;"></div>
</div>

<div class="section">
<h3>📷 Camera</h3>
<div class="camera-box">
<video id="video" autoplay playsinline></video>
<button class="btn btn-green" id="camBtn" onclick="toggleCamera()">Start Camera</button>
</div>
</div>

<div class="section">
<h3>📊 Motion Sensor</h3>
<div id="motionData" class="motion-data">Waiting for motion data...</div>
</div>

<div class="section">
<h3>🗳️ Vote for Best Coach</h3>
<button class="vote-btn" style="background:#0a84ff" onclick="sendVote(0)">FormCoach</button>
<button class="vote-btn" style="background:#ff9500" onclick="sendVote(1)">HypeTrainer</button>
<button class="vote-btn" style="background:#34c759" onclick="sendVote(2)">PhysioPro</button>
</div>

<script>
let ws = null;
let cameraStream = null;
let cameraActive = false;
let currentExercise = 'squats';
let isRunning = false;

function connect() {
    const host = window.location.hostname;
    ws = new WebSocket('ws://' + host + ':\(wsPort)');

    ws.onopen = () => {
        document.getElementById('status').textContent = 'Connected to Mac ✓';
        document.getElementById('status').className = 'status connected';
        ws.send(JSON.stringify({type: 'hello', data: 'iPhone connected'}));
        startMotion();
    };

    ws.onclose = () => {
        document.getElementById('status').textContent = 'Disconnected — retrying...';
        document.getElementById('status').className = 'status disconnected';
        setTimeout(connect, 2000);
    };

    ws.onerror = () => { ws.close(); };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'arenaState') {
                updateArenaState(msg);
            }
        } catch(e) {}
    };
}

function updateArenaState(msg) {
    if (msg.round !== undefined) {
        document.getElementById('roundInfo').textContent = 'Round ' + msg.round + (msg.isRunning ? ' — Analyzing...' : ' — Complete');
    }
    if (msg.isRunning !== undefined) {
        isRunning = msg.isRunning;
        document.getElementById('startBtn').disabled = isRunning;
        document.getElementById('stopBtn').disabled = !isRunning;
    }
    if (msg.agents) {
        let html = '';
        const colors = {FormCoach: '#0a84ff', HypeTrainer: '#ff9500', PhysioPro: '#34c759'};
        msg.agents.forEach((a, i) => {
            const c = colors[a.name] || '#888';
            const dot = a.isStreaming ? '#ff9500' : c;
            const preview = a.output ? a.output.substring(0, 120) + '...' : (a.isStreaming ? 'Analyzing...' : 'Waiting...');
            html += '<div class="agent-status" style="background:' + c + '22">';
            html += '<div class="agent-dot" style="background:' + dot + '"></div>';
            html += '<div class="agent-name" style="color:' + c + '">' + a.name + '</div>';
            html += '<div class="agent-score">Score: ' + a.score + '</div>';
            html += '</div>';
            html += '<div class="agent-output" style="margin-bottom:8px;padding-left:8px;">' + preview + '</div>';
        });
        document.getElementById('agentStatus').innerHTML = html;
    }
}

function setExercise(name) {
    currentExercise = name;
    document.querySelectorAll('.exercise-btn').forEach(b => b.classList.remove('active'));
    if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({type: 'exercise', data: name, timestamp: Date.now()}));
    }
    document.getElementById('exerciseInput').value = name;
}

function sendControl(cmd) {
    if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({type: 'control', data: cmd, timestamp: Date.now()}));
    }
}

async function toggleCamera() {
    if (cameraActive) {
        if (cameraStream) { cameraStream.getTracks().forEach(t => t.stop()); cameraStream = null; }
        cameraActive = false;
        document.getElementById('camBtn').textContent = 'Start Camera';
        document.getElementById('video').srcObject = null;
        if (ws) ws.send(JSON.stringify({type: 'camera', data: 'off'}));
        return;
    }
    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'environment'}});
        document.getElementById('video').srcObject = cameraStream;
        cameraActive = true;
        document.getElementById('camBtn').textContent = 'Stop Camera';
        if (ws) ws.send(JSON.stringify({type: 'camera', data: 'on'}));
    } catch(e) {
        document.getElementById('camBtn').textContent = 'Camera Denied';
    }
}

function startMotion() {
    if (window.DeviceMotionEvent && typeof DeviceMotionEvent.requestPermission === 'function') {
        DeviceMotionEvent.requestPermission().then(state => {
            if (state === 'granted') { setupMotion(); }
        });
    }
    if (window.DeviceMotionEvent) { setupMotion(); }
}

function setupMotion() {
    if (!window.DeviceMotionEvent) return;
    window.addEventListener('devicemotion', (e) => {
        if (!e.accelerationIncludingGravity) return;
        const a = e.accelerationIncludingGravity;
        const data = 'x:' + a.x.toFixed(1) + ' y:' + a.y.toFixed(1) + ' z:' + a.z.toFixed(1);
        document.getElementById('motionData').textContent = data;
        if (ws && ws.readyState === 1) {
            ws.send(JSON.stringify({type: 'motion', data: data, timestamp: Date.now()}));
        }
    }, true);
}

function sendVote(agentIndex) {
    if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({type: 'vote', vote: agentIndex, timestamp: Date.now()}));
    }
}

connect();
</script>
</body>
</html>
""" }

    init(httpPort: UInt16 = 8080, wsPort: UInt16 = 8765) {
        self.port = httpPort
        self.wsPort = wsPort
    }

    func start() {
        stop()
        do {
            let params = NWParameters.tcp
            params.allowLocalEndpointReuse = true
            let listener = try NWListener(using: params, on: NWEndpoint.Port(integerLiteral: port))
            self.listener = listener
            listener.newConnectionHandler = { [weak self] conn in
                self?.handle(conn)
            }
            listener.start(queue: queue)
        } catch {
            print("Failed to start iPhone input server: \(error)")
        }
    }

    func stop() {
        listener?.cancel()
        listener = nil
    }

    private func handle(_ conn: NWConnection) {
        conn.start(queue: queue)
        conn.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, _, _ in
            if let data = data, !data.isEmpty {
                let request = String(data: data, encoding: .utf8) ?? ""
                if request.contains("GET /") {
                    let html = self?.html ?? ""
                    let response = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: \(html.utf8.count)\r\nConnection: close\r\n\r\n\(html)"
                    let responseData = response.data(using: .utf8) ?? Data()
                    conn.send(content: responseData, completion: .contentProcessed { _ in })
                }
            }
            conn.cancel()
        }
    }
}
