import Foundation
import Network

final class PhoneHttpServer: ObservableObject {
    private var listener: NWListener?
    private let queue = DispatchQueue(label: "voice.http")
    private let port: UInt16
    private let wsPort: UInt16

    init(httpPort: UInt16 = 8081, wsPort: UInt16 = 8766) {
        self.port = httpPort
        self.wsPort = wsPort
    }

    func start() {
        stop()
        NSLog("PhoneHttpServer: starting on port \(port)")
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        do {
            let listener = try NWListener(using: params, on: NWEndpoint.Port(integerLiteral: port))
            self.listener = listener
            listener.newConnectionHandler = { [weak self] conn in
                self?.handle(conn)
            }
            listener.stateUpdateHandler = { state in
                NSLog("PhoneHttpServer: listener state = \(state)")
            }
            listener.start(queue: queue)
            NSLog("PhoneHttpServer: listening on port \(port)")
        } catch {
            NSLog("PhoneHttpServer: failed to start: \(error)")
        }
    }

    func stop() {
        listener?.cancel()
        listener = nil
    }

    private func handle(_ conn: NWConnection) {
        conn.start(queue: queue)
        conn.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, isComplete, error in
            if let data = data, !data.isEmpty {
                let request = String(data: data, encoding: .utf8) ?? ""
                if request.contains("GET /") {
                    let html = self?.html ?? ""
                    let response = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: \(html.utf8.count)\r\nConnection: close\r\n\r\n\(html)"
                    let responseData = response.data(using: .utf8) ?? Data()
                    conn.send(content: responseData, completion: .contentProcessed { _ in
                        conn.cancel()
                    })
                    return
                }
            }
            conn.cancel()
        }
    }

    private var html: String { """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>VoiceMacRemote</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#fff;font-family:-apple-system,sans-serif;padding:16px;max-width:600px;margin:0 auto;min-height:100vh}
h1{font-size:24px;text-align:center;margin-bottom:4px}
.subtitle{text-align:center;font-size:13px;color:#888;margin-bottom:16px}
.status{text-align:center;font-size:14px;margin-bottom:16px;padding:8px;border-radius:10px}
.connected{background:#1a3a1a;color:#4caf50}
.disconnected{background:#3a1a1a;color:#f44336}
.section{background:#1a1a1a;border-radius:14px;padding:16px;margin-bottom:12px}
h3{font-size:15px;margin-bottom:10px;color:#aaa}
.mic-btn{width:120px;height:120px;border-radius:50%;border:none;font-size:48px;cursor:pointer;display:block;margin:0 auto 12px;transition:all 0.2s}
.mic-btn.listening{background:#f44336;animation:pulse 1.5s infinite}
.mic-btn.idle{background:#0a84ff}
.mic-btn:active{transform:scale(0.95)}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(244,67,54,0.4)}70%{box-shadow:0 0 0 20px rgba(244,67,54,0)}100%{box-shadow:0 0 0 0 rgba(244,67,54,0)}}
.transcript{background:#222;border-radius:10px;padding:14px;min-height:60px;font-size:16px;line-height:1.5;margin-bottom:12px}
.transcript.interim{color:#888}
.transcript.final{color:#fff}
.cmd-btn{background:#333;color:#fff;border:1px solid #555;padding:12px;border-radius:10px;font-size:14px;cursor:pointer;width:100%;margin-bottom:6px;text-align:left}
.cmd-btn:active{background:#444}
.cmd-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.history-item{background:#222;border-radius:8px;padding:10px;margin-bottom:6px;font-size:13px}
.history-cmd{color:#0a84ff;font-weight:bold}
.history-result{color:#4caf50;font-size:12px;margin-top:2px}
.history-fail{color:#f44336}
.hint{text-align:center;font-size:12px;color:#666;margin-top:8px}
</style>
</head>
<body>
<h1>🎙️ VoiceMacRemote</h1>
<div class="subtitle">Control your Mac with your voice</div>
<div id="status" class="status disconnected">Connecting to Mac...</div>

<div class="section">
<h3>🎤 Voice Command</h3>
<button class="mic-btn idle" id="micBtn" onclick="toggleMic()">🎙️</button>
<div id="transcript" class="transcript interim">Tap the microphone and speak...</div>
<button class="cmd-btn" onclick="sendTranscript()" style="background:#0a84ff;border:none;text-align:center;font-weight:bold">▶ Execute Command</button>
</div>

<div class="section">
<h3>⚡ Quick Commands</h3>
<div class="cmd-grid">
<button class="cmd-btn" onclick="sendCmd('open safari')">🦁 Open Safari</button>
<button class="cmd-btn" onclick="sendCmd('open terminal')">💻 Open Terminal</button>
<button class="cmd-btn" onclick="sendCmd('open finder')">📁 Open Finder</button>
<button class="cmd-btn" onclick="sendCmd('open notes')">📝 Open Notes</button>
<button class="cmd-btn" onclick="sendCmd('open music')">🎵 Open Music</button>
<button class="cmd-btn" onclick="sendCmd('open messages')">💬 Open Messages</button>
<button class="cmd-btn" onclick="sendCmd('open mail')">✉️ Open Mail</button>
<button class="cmd-btn" onclick="sendCmd('open calculator')">🧮 Calculator</button>
<button class="cmd-btn" onclick="sendCmd('open activity monitor')">📊 Activity Monitor</button>
<button class="cmd-btn" onclick="sendCmd('open system settings')">⚙️ System Settings</button>
</div>
</div>

<div class="section">
<h3>🖥️ System Controls</h3>
<div class="cmd-grid">
<button class="cmd-btn" onclick="sendCmd('volume up')">🔊 Volume Up</button>
<button class="cmd-btn" onclick="sendCmd('volume down')">🔉 Volume Down</button>
<button class="cmd-btn" onclick="sendCmd('mute')">🔇 Mute</button>
<button class="cmd-btn" onclick="sendCmd('screenshot')">📸 Screenshot</button>
<button class="cmd-btn" onclick="sendCmd('lock screen')">🔒 Lock Screen</button>
<button class="cmd-btn" onclick="sendCmd('sleep')">😴 Sleep Display</button>
<button class="cmd-btn" onclick="sendCmd('play')">▶️ Play/Pause</button>
<button class="cmd-btn" onclick="sendCmd('next')">⏭️ Next Track</button>
</div>
</div>

<div class="section">
<h3>📋 Command History</h3>
<div id="history"></div>
</div>

<div class="hint">Say things like "open safari", "search best pizza near me", "type hello world", "volume up"</div>

<script>
let ws = null;
let recognition = null;
let isListening = false;
let finalTranscript = '';
let interimTranscript = '';

function connect() {
    const host = window.location.hostname;
    ws = new WebSocket('ws://' + host + ':\(wsPort)');
    ws.onopen = () => {
        document.getElementById('status').textContent = 'Connected to Mac ✓';
        document.getElementById('status').className = 'status connected';
        ws.send(JSON.stringify({type: 'hello', data: 'iPhone connected'}));
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
            if (msg.type === 'result') {
                addHistory(msg.command, msg.result, msg.success);
            }
        } catch(e) {}
    };
}

function setupSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
        document.getElementById('transcript').textContent = 'Speech Recognition not supported. Use Safari on iOS.';
        return null;
    }
    let r = new SR();
    r.continuous = true;
    r.interimResults = true;
    r.lang = 'en-US';
    r.onresult = (event) => {
        interimTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }
        updateTranscript();
    };
    r.onend = () => {
        if (isListening) {
            try { r.start(); } catch(e) {}
        }
    };
    r.onerror = (e) => {
        if (e.error === 'not-allowed') {
            document.getElementById('transcript').textContent = 'Microphone access denied. Allow in Safari settings.';
            isListening = false;
            document.getElementById('micBtn').className = 'mic-btn idle';
        }
    };
    return r;
}

function toggleMic() {
    if (!recognition) {
        recognition = setupSpeech();
        if (!recognition) return;
    }
    if (isListening) {
        isListening = false;
        recognition.stop();
        document.getElementById('micBtn').className = 'mic-btn idle';
    } else {
        finalTranscript = '';
        interimTranscript = '';
        isListening = true;
        recognition.start();
        document.getElementById('micBtn').className = 'mic-btn listening';
        document.getElementById('transcript').textContent = 'Listening... speak now';
        document.getElementById('transcript').className = 'transcript interim';
    }
}

function updateTranscript() {
    const el = document.getElementById('transcript');
    if (finalTranscript) {
        el.textContent = finalTranscript + (interimTranscript ? ' ' + interimTranscript : '');
        el.className = 'transcript final';
    } else if (interimTranscript) {
        el.textContent = interimTranscript;
        el.className = 'transcript interim';
    }
}

function sendTranscript() {
    const text = finalTranscript.trim() || interimTranscript.trim();
    if (!text) return;
    if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({type: 'command', data: text, timestamp: Date.now()}));
    }
    finalTranscript = '';
    interimTranscript = '';
    document.getElementById('transcript').textContent = 'Sent: ' + text;
    document.getElementById('transcript').className = 'transcript final';
    if (isListening) {
        isListening = false;
        recognition.stop();
        document.getElementById('micBtn').className = 'mic-btn idle';
    }
}

function sendCmd(cmd) {
    if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({type: 'command', data: cmd, timestamp: Date.now()}));
    }
}

function addHistory(cmd, result, success) {
    const el = document.getElementById('history');
    let html = '<div class="history-item">';
    html += '<div class="history-cmd">' + cmd + '</div>';
    html += '<div class="' + (success ? 'history-result' : 'history-result history-fail') + '">' + result + '</div>';
    html += '</div>';
    el.innerHTML = html + el.innerHTML;
}

connect();
</script>
</body>
</html>
""" }
}
