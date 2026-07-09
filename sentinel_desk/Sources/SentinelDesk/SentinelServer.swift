import Foundation
import Network
import CryptoKit

final class SentinelServer: ObservableObject {
    private var httpListener: NWListener?
    private var wsListener: NWListener?
    private let httpQueue = DispatchQueue(label: "sentinel.http")
    private let wsQueue = DispatchQueue(label: "sentinel.ws")
    private var wsConnections: [NWConnection] = []
    private var wsHandshake: Set<ObjectIdentifier> = []
    private let httpPort: UInt16
    private let wsPort: UInt16

    @Published var isRunning = false
    var onMessage: ((String) -> Void)?
    var onBinaryMessage: ((Data) -> Void)?
    var onBinaryFrame: ((Data) -> Void)?

    init(httpPort: UInt16 = 8082, wsPort: UInt16 = 8767) {
        self.httpPort = httpPort
        self.wsPort = wsPort
    }

    func start() {
        stop()
        startHTTP()
        startWS()
        DispatchQueue.main.async { self.isRunning = true }
        NSLog("SentinelServer: started (http:\(httpPort) ws:\(wsPort))")
    }

    func stop() {
        httpListener?.cancel()
        wsListener?.cancel()
        httpListener = nil
        wsListener = nil
        wsConnections.forEach { $0.cancel() }
        wsConnections.removeAll()
        wsHandshake.removeAll()
        DispatchQueue.main.async { self.isRunning = false }
    }

    func broadcast(_ message: String) {
        let frame = frameText(message.data(using: .utf8) ?? Data())
        for conn in wsConnections {
            conn.send(content: frame, completion: .contentProcessed { _ in })
        }
    }

    func broadcastBinary(_ data: Data) {
        let frame = frameBinary(data)
        for conn in wsConnections {
            conn.send(content: frame, completion: .contentProcessed { _ in })
        }
    }

    private func startHTTP() {
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        do {
            let listener = try NWListener(using: params, on: NWEndpoint.Port(integerLiteral: httpPort))
            listener.newConnectionHandler = { [weak self] conn in
                self?.handleHTTP(conn)
            }
            listener.start(queue: httpQueue)
            httpListener = listener
        } catch {
            NSLog("SentinelServer: HTTP failed: \(error)")
        }
    }

    private func startWS() {
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        do {
            let listener = try NWListener(using: params, on: NWEndpoint.Port(integerLiteral: wsPort))
            listener.newConnectionHandler = { [weak self] conn in
                self?.handleWS(conn)
            }
            listener.start(queue: wsQueue)
            wsListener = listener
        } catch {
            NSLog("SentinelServer: WS failed: \(error)")
        }
    }

    private func handleHTTP(_ conn: NWConnection) {
        conn.start(queue: httpQueue)
        conn.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, _, _ in
            if let data = data, !data.isEmpty {
                let req = String(data: data, encoding: .utf8) ?? ""
                if req.contains("GET /") {
                    let html = self?.iphoneHTML ?? ""
                    let resp = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: \(html.utf8.count)\r\nConnection: close\r\n\r\n\(html)"
                    conn.send(content: resp.data(using: .utf8) ?? Data(), completion: .contentProcessed { _ in
                        conn.cancel()
                    })
                    return
                }
            }
            conn.cancel()
        }
    }

    private func handleWS(_ conn: NWConnection) {
        wsConnections.append(conn)
        conn.start(queue: wsQueue)
        wsReceiveLoop(conn)
    }

    private func wsReceiveLoop(_ conn: NWConnection) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            if let data = data, !data.isEmpty {
                self?.processWS(data, from: conn)
            }
            if isComplete || error != nil {
                self?.removeWSConnection(conn)
                return
            }
            self?.wsReceiveLoop(conn)
        }
    }

    private func processWS(_ data: Data, from conn: NWConnection) {
        let connId = ObjectIdentifier(conn)
        if !wsHandshake.contains(connId) {
            let text = String(data: data, encoding: .utf8) ?? ""
            if text.contains("Upgrade: websocket") || text.contains("Upgrade: WebSocket") {
                performWSHandshake(text, on: conn)
                wsHandshake.insert(connId)
                NSLog("SentinelServer: iPhone connected")
            }
            return
        }

        if let payload = decodeFrame(data) {
            DispatchQueue.main.async {
                self.onMessage?(payload)
            }
        } else if let binaryPayload = decodeBinaryFrame(data) {
            DispatchQueue.main.async {
                self.onBinaryFrame?(binaryPayload)
            }
        }
    }

    private func decodeFrame(_ data: Data) -> String? {
        guard data.count >= 2 else { return nil }
        let opcode = data[0] & 0x0F
        guard opcode == 1 else { return nil }
        var payloadLen = Int(data[1] & 0x7F)
        var offset = 2
        if payloadLen == 126 {
            guard data.count >= 4 else { return nil }
            payloadLen = Int(data[2]) << 8 | Int(data[3])
            offset = 4
        } else if payloadLen == 127 {
            guard data.count >= 10 else { return nil }
            payloadLen = 0
            for i in 0..<8 { payloadLen = (payloadLen << 8) | Int(data[2 + i]) }
            offset = 10
        }
        let masked = (data[1] & 0x80) != 0
        if masked {
            guard data.count >= offset + 4 + payloadLen else { return nil }
            let mask = Array(data[offset..<offset+4])
            offset += 4
            var payload = Data(data[offset..<offset+payloadLen])
            for i in 0..<payload.count { payload[i] ^= mask[i % 4] }
            return String(data: payload, encoding: .utf8)
        } else {
            guard data.count >= offset + payloadLen else { return nil }
            return String(data: data[offset..<offset+payloadLen], encoding: .utf8)
        }
    }

    private func decodeBinaryFrame(_ data: Data) -> Data? {
        guard data.count >= 2 else { return nil }
        let opcode = data[0] & 0x0F
        guard opcode == 2 else { return nil }
        var payloadLen = Int(data[1] & 0x7F)
        var offset = 2
        if payloadLen == 126 {
            guard data.count >= 4 else { return nil }
            payloadLen = Int(data[2]) << 8 | Int(data[3])
            offset = 4
        } else if payloadLen == 127 {
            guard data.count >= 10 else { return nil }
            payloadLen = 0
            for i in 0..<8 { payloadLen = (payloadLen << 8) | Int(data[2 + i]) }
            offset = 10
        }
        let masked = (data[1] & 0x80) != 0
        if masked {
            guard data.count >= offset + 4 + payloadLen else { return nil }
            let mask = Array(data[offset..<offset+4])
            offset += 4
            var payload = Data(data[offset..<offset+payloadLen])
            for i in 0..<payload.count { payload[i] ^= mask[i % 4] }
            return payload
        } else {
            guard data.count >= offset + payloadLen else { return nil }
            return data[offset..<offset+payloadLen]
        }
    }

    private func performWSHandshake(_ request: String, on conn: NWConnection) {
        var key = ""
        for line in request.components(separatedBy: "\r\n") {
            if line.lowercased().hasPrefix("sec-websocket-key:") {
                key = line.split(separator: ":").dropFirst().joined(separator: ":").trimmingCharacters(in: .whitespaces)
                break
            }
        }
        let combined = key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        let hash = Insecure.SHA1.hash(data: Data(combined.utf8))
        let accept = hash.withUnsafeBytes { Data($0) }.base64EncodedString()
        let response = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: \(accept)\r\n\r\n"
        conn.send(content: response.data(using: .utf8) ?? Data(), completion: .contentProcessed { _ in })
    }

    private func removeWSConnection(_ conn: NWConnection) {
        let idx = wsConnections.firstIndex { $0 === conn }
        wsConnections.removeAll { $0 === conn }
        wsHandshake.remove(ObjectIdentifier(conn))
        conn.cancel()
        if let i = idx, i < wsConnections.count {
            NSLog("SentinelServer: iPhone disconnected")
        }
    }

    private func frameText(_ data: Data) -> Data {
        var frame = Data([0x81])
        let len = data.count
        if len <= 125 {
            frame.append(UInt8(len))
        } else if len <= 65535 {
            frame.append(126)
            frame.append(UInt8((len >> 8) & 0xFF))
            frame.append(UInt8(len & 0xFF))
        } else {
            frame.append(127)
            for i in (0..<8).reversed() { frame.append(UInt8((len >> (i * 8)) & 0xFF)) }
        }
        frame.append(data)
        return frame
    }

    private func frameBinary(_ data: Data) -> Data {
        var frame = Data([0x82])
        let len = data.count
        if len <= 125 {
            frame.append(UInt8(len))
        } else if len <= 65535 {
            frame.append(126)
            frame.append(UInt8((len >> 8) & 0xFF))
            frame.append(UInt8(len & 0xFF))
        } else {
            frame.append(127)
            for i in (0..<8).reversed() { frame.append(UInt8((len >> (i * 8)) & 0xFF)) }
        }
        frame.append(data)
        return frame
    }

    var iphoneHTML: String { """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>SentinelDesk</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#fff;font-family:-apple-system,sans-serif;padding:12px;max-width:600px;margin:0 auto;-webkit-user-select:none;user-select:none}
h1{font-size:20px;text-align:center;margin-bottom:2px}
.sub{text-align:center;font-size:12px;color:#888;margin-bottom:12px}
.card{background:#1a1a1a;border-radius:12px;padding:14px;margin-bottom:10px}
h3{font-size:13px;color:#aaa;margin-bottom:8px;display:flex;align-items:center;gap:6px}
.status-row{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.present{background:#34c759}.absent{background:#ff3b30}
.working{background:#ff9500;animation:pulse 1.5s infinite}
.armed{background:#ffd60a}
.idle{background:#48484a}
@keyframes pulse{0%{opacity:1}50%{opacity:0.4}100%{opacity:1}}
.label{font-size:13px;font-weight:600}
.value{font-size:12px;color:#888;margin-left:auto}
.mission-text{font-size:14px;color:#fff;margin-bottom:8px;line-height:1.4}
.task-item{background:#222;border-radius:8px;padding:8px;margin-bottom:4px}
.task-title{font-size:12px;font-weight:600;color:#0a84ff}
.task-status{font-size:10px;padding:2px 6px;border-radius:4px;display:inline-block;margin-top:3px}
.s-completed{background:#1a3a1a;color:#4caf50}.s-running{background:#3a2a0a;color:#ff9500}
.s-pending{background:#333;color:#888}.s-failed{background:#3a1a1a;color:#f44336}
.s-skipped{background:#333;color:#666}
.task-result{font-size:10px;color:#aaa;margin-top:3px;max-height:60px;overflow:hidden}
.btn{background:#0a84ff;color:#fff;border:none;padding:12px;border-radius:10px;font-size:15px;width:100%;margin-bottom:6px;cursor:pointer}
.btn:active{transform:scale(0.97)}
.btn-green{background:#34c759}.btn-red{background:#ff3b30}.btn-gray{background:#48484a}.btn-purple{background:#bf5af2}
.btn-row{display:flex;gap:6px}
.btn-row .btn{margin-bottom:0}
input,textarea{background:#222;border:1px solid #444;color:#fff;border-radius:8px;padding:10px;font-size:14px;width:100%;margin-bottom:6px}
.log{font-size:10px;color:#888;font-family:monospace;max-height:150px;overflow-y:auto;line-height:1.4;white-space:pre-wrap}
.summary-card{background:#1a2a1a;border:1px solid #34c759;border-radius:12px;padding:14px;margin-bottom:10px}
.screen-container{position:relative;width:100%;border-radius:8px;overflow:hidden;background:#000;touch-action:none}
#screenImg{width:100%;display:block;cursor:crosshair}
.screen-overlay{position:absolute;inset:0}
.tab-bar{display:flex;gap:4px;margin-bottom:10px;overflow-x:auto}
.tab{padding:8px 14px;border-radius:8px 8px 0 0;background:#1a1a1a;color:#888;font-size:12px;white-space:nowrap;cursor:pointer}
.tab.active{background:#0a84ff;color:#fff}
.tab-content{display:none}
.tab-content.active{display:block}
.chat-msg{padding:8px 12px;border-radius:10px;margin-bottom:6px;max-width:85%;font-size:13px;line-height:1.4}
.chat-user{background:#0a84ff;color:#fff;margin-left:auto;text-align:right}
.chat-llm{background:#222;color:#ccc}
.chat-cmd{background:#1a2a1a;color:#4caf50;font-family:monospace;font-size:11px}
.chat-out{background:#222;color:#aaa;font-family:monospace;font-size:11px;white-space:pre-wrap}
.chat-container{max-height:300px;overflow-y:auto;margin-bottom:8px}
.vision-result{font-size:12px;color:#ccc;line-height:1.5;padding:10px;background:#222;border-radius:8px}
.kbd-row{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:4px}
.kbd-btn{background:#333;color:#fff;border:none;padding:8px 12px;border-radius:6px;font-size:13px;cursor:pointer;min-width:36px}
.kbd-btn:active{background:#555}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid #444;border-top-color:#0a84ff;border-radius:50%;animation:spin 0.8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<h1>🛡️ SentinelDesk</h1>
<div class="sub">TeamViewer + AirPlay + LLM</div>

<div class="tab-bar">
<div class="tab active" onclick="showTab('screen')">🖥️ Screen</div>
<div class="tab" onclick="showTab('mission')">🤖 Mission</div>
<div class="tab" onclick="showTab('chat')">💬 LLM Chat</div>
<div class="tab" onclick="showTab('terminal')">⌨️ Terminal</div>
<div class="tab" onclick="showTab('vision')">👁️ Vision</div>
<div class="tab" onclick="showTab('settle')">🏛️ Settle</div>
</div>

<div class="tab-content active" id="tab-screen">
<div class="card">
<h3>🖥️ Live Mac Screen <span id="screenFps"></span></h3>
<div class="screen-container" id="screenContainer">
<img id="screenImg" src="" style="display:none">
<div class="screen-overlay" id="screenOverlay"></div>
</div>
<div class="btn-row" style="margin-top:8px">
<button class="btn btn-green" id="streamBtn" onclick="toggleStream()">▶ Start Stream</button>
<button class="btn btn-purple" onclick="screenshot()">📸 Screenshot</button>
</div>
</div>
<div class="card">
<h3>Remote Control</h3>
<div class="kbd-row">
<button class="kbd-btn" onclick="sendKey(53)">ESC</button>
<button class="kbd-btn" onclick="sendKey(36)">⏎</button>
<button class="kbd-btn" onclick="sendKey(51)">⌫</button>
<button class="kbd-btn" onclick="sendKey(123)">◀</button>
<button class="kbd-btn" onclick="sendKey(124)">▶</button>
<button class="kbd-btn" onclick="sendKey(126)">▲</button>
<button class="kbd-btn" onclick="sendKey(125)">▼</button>
</div>
<div class="kbd-row">
<button class="kbd-btn" onclick="sendCmd('open -a Safari')">🌐</button>
<button class="kbd-btn" onclick="sendCmd('open -a Terminal')">⬛</button>
<button class="kbd-btn" onclick="sendCmd('open -a Finder')">📁</button>
<button class="kbd-btn" onclick="sendCmd('pmset displaysleepnow')">🌙</button>
<button class="kbd-btn" onclick="sendCmd('osascript -e \\'tell application \\"System Events\\" to keystroke \\"c\\" using command down\\'')">⌘C</button>
<button class="kbd-btn" onclick="sendCmd('osascript -e \\'tell application \\"System Events\\" to keystroke \\"v\\" using command down\\'')">⌘V</button>
</div>
<input type="text" id="typeInput" placeholder="Type text on Mac..." style="margin-top:6px">
<button class="btn" onclick="sendType()">Send Text</button>
</div>
</div>

<div class="tab-content" id="tab-mission">
<div class="card">
<h3>Presence</h3>
<div class="status-row">
<div class="dot idle" id="presenceDot"></div>
<span class="label" id="presenceLabel">Connecting...</span>
<span class="value" id="presenceTime"></span>
</div>
<div class="status-row">
<div class="dot idle" id="workDot"></div>
<span class="label" id="workLabel">Idle</span>
</div>
</div>
<div class="card" id="missionCard">
<h3>🤖 Mission</h3>
<textarea id="missionInput" rows="3" placeholder="What should your Mac do while you're away?"></textarea>
<button class="btn btn-green" onclick="setMission()">Set Mission</button>
</div>
<div class="card" id="controlCard" style="display:none">
<h3>Autonomous Control</h3>
<div class="mission-text" id="missionDisplay"></div>
<div class="btn-row">
<button class="btn btn-green" id="armBtn" onclick="armAgent()">🛡️ Arm</button>
<button class="btn btn-gray" id="disarmBtn" onclick="disarmAgent()" style="display:none">🔓 Disarm</button>
</div>
<div class="btn-row">
<button class="btn btn-green" id="startBtn" onclick="startWork()" style="display:none">▶ Start Now</button>
<button class="btn btn-red" id="stopBtn" onclick="stopWork()" style="display:none">⏹ Stop</button>
</div>
</div>
<div class="card" id="tasksCard" style="display:none">
<h3>Tasks (<span id="taskProgress">0/0</span>)</h3>
<div id="taskList"></div>
</div>
<div class="card" id="summaryCard" style="display:none">
<h3>📋 Work Summary</h3>
<div id="summaryText"></div>
</div>
<div class="card">
<h3>Work Log</h3>
<div class="log" id="logText">Waiting...</div>
</div>
</div>

<div class="tab-content" id="tab-chat">
<div class="card">
<h3>💬 LLM Chat — Natural Language → Mac Actions</h3>
<div class="chat-container" id="chatContainer">
<div class="chat-msg chat-llm">Ask me anything. I can run commands on your Mac, analyze files, search, and more.</div>
</div>
<div class="btn-row" style="margin-bottom:6px">
<select id="chatModel" style="background:#222;border:1px solid #444;color:#fff;border-radius:8px;padding:10px;font-size:13px;flex:1">
<option value="">Loading models...</option>
</select>
</div>
<input type="text" id="chatInput" placeholder="e.g. 'What files are in my Downloads?'">
<button class="btn btn-purple" onclick="sendChat()">Send to Mac LLM</button>
</div>
</div>

<div class="tab-content" id="tab-terminal">
<div class="card">
<h3>⌨️ Remote Terminal</h3>
<div class="log" id="termOutput" style="max-height:300px">$ Ready</div>
<input type="text" id="termInput" placeholder="Enter shell command..." style="margin-top:6px">
<button class="btn" onclick="sendTerminal()">Execute</button>
</div>
</div>

<div class="tab-content" id="tab-vision">
<div class="card">
<h3>👁️ AI Vision — Screenshot Analysis</h3>
<p style="font-size:12px;color:#888;margin-bottom:8px">Captures your Mac screen and sends it to LLaVA for AI analysis</p>
<div class="btn-row" style="margin-bottom:8px">
<button class="btn btn-purple" onclick="visionAnalyze('What is on my screen?')">📸 Analyze Screen</button>
</div>
<div class="btn-row" style="margin-bottom:8px">
<button class="btn btn-gray" onclick="visionAnalyze('What apps are open?')" style="font-size:12px">What apps are open?</button>
<button class="btn btn-gray" onclick="visionAnalyze('Read any visible text')" style="font-size:12px">Read text</button>
</div>
<div class="btn-row" style="margin-bottom:8px">
<button class="btn btn-gray" onclick="visionAnalyze('Describe the UI layout')" style="font-size:12px">Describe UI</button>
<button class="btn btn-gray" onclick="visionAnalyze('What should I do next?')" style="font-size:12px">What next?</button>
</div>
<div id="visionResult" style="display:none">
<h3>AI Analysis</h3>
<div class="vision-result" id="visionText"></div>
</div>
<div id="visionSpinner" style="display:none;text-align:center;padding:20px">
<div class="spinner"></div> <span style="font-size:12px;color:#888">Analyzing screen with LLaVA...</span>
</div>
</div>
</div>

<div class="tab-content" id="tab-settle">
<div class="card">
<h3>🏛️ Proof of Autonomy</h3>
<p style="font-size:12px;color:#888;margin-bottom:10px">Every autonomous work session is receipted, chain-verified, and settleable. Accepted work accumulates into proof-of-autonomy value.</p>
<div style="display:flex;gap:12px;margin-bottom:12px">
<div style="flex:1;background:#222;border-radius:8px;padding:12px;text-align:center">
<div style="font-size:24px;font-weight:bold;color:#34c759" id="cumValue">$0.00</div>
<div style="font-size:10px;color:#888">Cumulative Value</div>
</div>
<div style="flex:1;background:#222;border-radius:8px;padding:12px;text-align:center">
<div style="font-size:24px;font-weight:bold;color:#0a84ff" id="sessCount">0/0</div>
<div style="font-size:10px;color:#888">Accepted/Total</div>
</div>
</div>
</div>
<div class="card" id="settlementCard" style="display:none">
<h3>📋 Settlement Pending Review</h3>
<div style="font-size:13px;color:#ccc;margin-bottom:8px" id="settleMission"></div>
<div style="font-size:12px;color:#888;margin-bottom:4px">Actions: <span id="settleActions"></span> | Confidence: <span id="settleConf"></span></div>
<div style="font-size:12px;color:#888;margin-bottom:4px">Commands: <span id="settleCmds"></span> | Files: <span id="settleFiles"></span> | LLM: <span id="settleLlm"></span></div>
<div style="font-size:16px;font-weight:bold;color:#34c759;margin-bottom:8px">Est. Value: $<span id="settleValue"></span></div>
<div style="font-size:11px;margin-bottom:10px" id="settleChain"></div>
<div class="btn-row">
<button class="btn btn-green" onclick="settleAccept()">✓ Accept</button>
<button class="btn btn-gray" onclick="settleDiscount()">~ Discount</button>
</div>
<div class="btn-row">
<button class="btn btn-red" onclick="settleReject()">✗ Reject</button>
</div>
</div>
<div class="card" id="noSettlementCard">
<div style="font-size:13px;color:#888;text-align:center;padding:20px">No pending settlements. Run an autonomous session to generate one.</div>
</div>
</div>

<script>
let ws=null,streaming=false,frameTimes=[];
function connect(){
    const h=window.location.hostname;
    ws=new WebSocket('ws://'+h+':\(wsPort)');
    ws.binaryType='arraybuffer';
    ws.onopen=()=>{ws.send(JSON.stringify({type:'hello'}))};
    ws.onclose=()=>{setTimeout(connect,2000)};
    ws.onerror=()=>{ws.close()};
    ws.onmessage=(e)=>{
        if(e.data instanceof ArrayBuffer){handleBinary(e.data);return}
        try{const m=JSON.parse(e.data);handleMessage(m)}catch(x){}
    };
}
function handleBinary(data){
    const blob=new Blob([data],{type:'image/jpeg'});
    const url=URL.createObjectURL(blob);
    const img=document.getElementById('screenImg');
    img.src=url;
    img.style.display='block';
    frameTimes.push(Date.now());
    if(frameTimes.length>10)frameTimes.shift();
    if(frameTimes.length>1){
        const fps=Math.round(10000/(frameTimes[frameTimes.length-1]-frameTimes[0]));
        document.getElementById('screenFps').textContent='('+fps+' fps)';
    }
}
function handleMessage(m){
    if(m.type==='state'){
        document.getElementById('presenceDot').className='dot '+(m.isPresent?'present':'absent');
        document.getElementById('presenceLabel').textContent=m.isPresent?'You are here':'You are away';
        document.getElementById('presenceTime').textContent=m.faceCount>0?'('+m.faceCount+' face'+(m.faceCount>1?'s':'')+')':'';
        document.getElementById('workDot').className='dot '+(m.isWorking?'working':(m.isArmed?'armed':'idle'));
        document.getElementById('workLabel').textContent=m.isWorking?'Working':(m.isArmed?'Armed':'Idle');
        if(m.mission){
            document.getElementById('missionDisplay').textContent=m.mission;
            document.getElementById('controlCard').style.display='block';
        }
        document.getElementById('armBtn').style.display=(m.isArmed||m.isWorking)?'none':'block';
        document.getElementById('disarmBtn').style.display=m.isArmed?'block':'none';
        document.getElementById('startBtn').style.display=m.isWorking?'none':'block';
        document.getElementById('stopBtn').style.display=m.isWorking?'block':'none';
        if(m.tasks&&m.tasks.length>0){
            document.getElementById('tasksCard').style.display='block';
            let done=m.tasks.filter(t=>t.status==='completed').length;
            document.getElementById('taskProgress').textContent=done+'/'+m.tasks.length;
            let html='';
            m.tasks.forEach(t=>{
                html+='<div class="task-item"><div class="task-title">'+t.title+'</div>';
                html+='<span class="task-status s-'+t.status+'">'+t.status+'</span>';
                if(t.result)html+='<div class="task-result">'+t.result.substring(0,200)+'</div>';
                html+='</div>';
            });
            document.getElementById('taskList').innerHTML=html;
        }
        if(m.log)document.getElementById('logText').textContent=m.log;
        if(m.summary){
            document.getElementById('summaryCard').style.display='block';
            document.getElementById('summaryText').textContent=m.summary;
        }
        if(m.models){
            const sel=document.getElementById('chatModel');
            sel.innerHTML=m.models.map(mo=>'<option value="'+mo+'">'+mo+'</option>').join('');
        }
        if(typeof m.cumulativeValue!=='undefined'){
            document.getElementById('cumValue').textContent='$'+m.cumulativeValue.toFixed(2);
            document.getElementById('sessCount').textContent=m.acceptedSessions+'/'+m.totalSessions;
        }
        if(m.hasPendingSettlement){
            document.getElementById('settlementCard').style.display='block';
            document.getElementById('noSettlementCard').style.display='none';
        }else{
            document.getElementById('settlementCard').style.display='none';
            document.getElementById('noSettlementCard').style.display='block';
        }
    }
    if(m.type==='chatResponse'){
        addChatMsg(m.response,'llm');
    }
    if(m.type==='chatCommand'){
        addChatMsg(m.command,'cmd');
    }
    if(m.type==='chatOutput'){
        addChatMsg(m.output,'out');
    }
    if(m.type==='termOutput'){
        const el=document.getElementById('termOutput');
        el.textContent+='\\n'+m.output;
        el.scrollTop=el.scrollHeight;
    }
    if(m.type==='visionResult'){
        document.getElementById('visionSpinner').style.display='none';
        document.getElementById('visionResult').style.display='block';
        document.getElementById('visionText').textContent=m.result;
    }
    if(m.type==='screenshot'){
        const img=document.getElementById('screenImg');
        img.src='data:image/jpeg;base64,'+m.data;
        img.style.display='block';
    }
}
function showTab(t){
    document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(c=>c.classList.remove('active'));
    document.getElementById('tab-'+t).classList.add('active');
    event.target.classList.add('active');
}
function toggleStream(){
    if(streaming){
        ws.send(JSON.stringify({type:'stopStream'}));
        streaming=false;
        document.getElementById('streamBtn').textContent='▶ Start Stream';
    }else{
        ws.send(JSON.stringify({type:'startStream'}));
        streaming=true;
        document.getElementById('streamBtn').textContent='⏹ Stop Stream';
    }
}
function screenshot(){
    ws.send(JSON.stringify({type:'screenshot'}));
}
function sendChat(){
    const input=document.getElementById('chatInput');
    const model=document.getElementById('chatModel').value;
    const msg=input.value.trim();
    if(!msg||!ws||ws.readyState!==1)return;
    addChatMsg(msg,'user');
    ws.send(JSON.stringify({type:'llmChat',message:msg,model:model}));
    input.value='';
}
function addChatMsg(text,cls){
    const c=document.getElementById('chatContainer');
    const d=document.createElement('div');
    d.className='chat-msg chat-'+cls;
    d.textContent=text;
    c.appendChild(d);
    c.scrollTop=c.scrollHeight;
}
function sendTerminal(){
    const input=document.getElementById('termInput');
    const cmd=input.value.trim();
    if(!cmd||!ws||ws.readyState!==1)return;
    const el=document.getElementById('termOutput');
    el.textContent+='\\n$ '+cmd;
    ws.send(JSON.stringify({type:'terminal',command:cmd}));
    input.value='';
}
function visionAnalyze(prompt){
    if(!ws||ws.readyState!==1)return;
    document.getElementById('visionResult').style.display='none';
    document.getElementById('visionSpinner').style.display='block';
    ws.send(JSON.stringify({type:'visionAnalyze',prompt:prompt}));
}
function setMission(){
    const m=document.getElementById('missionInput').value.trim();
    if(m&&ws&&ws.readyState===1)ws.send(JSON.stringify({type:'setMission',mission:m}));
}
function startWork(){if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'startWork'}))}
function stopWork(){if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'stopWork'}))}
function armAgent(){if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'arm'}))}
function disarmAgent(){if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'disarm'}))}
function settleAccept(){if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'settleAccept'}))}
function settleDiscount(){if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'settleDiscount'}))}
function settleReject(){if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'settleReject'}))}
function sendKey(kc){if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'key',keyCode:kc}))}
function sendCmd(c){if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'cmd',command:c}))}
function sendType(){
    const t=document.getElementById('typeInput').value;
    if(t&&ws&&ws.readyState===1)ws.send(JSON.stringify({type:'type',text:t}));
    document.getElementById('typeInput').value='';
}
document.getElementById('chatInput').addEventListener('keydown',e=>{if(e.key==='Enter')sendChat()});
document.getElementById('termInput').addEventListener('keydown',e=>{if(e.key==='Enter')sendTerminal()});

const overlay=document.getElementById('screenOverlay');
overlay.addEventListener('click',e=>{
    const rect=document.getElementById('screenImg').getBoundingClientRect();
    const x=(e.clientX-rect.left)/rect.width;
    const y=(e.clientY-rect.top)/rect.height;
    if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'click',x:x,y:y,button:'left'}));
});
overlay.addEventListener('contextmenu',e=>{
    e.preventDefault();
    const rect=document.getElementById('screenImg').getBoundingClientRect();
    const x=(e.clientX-rect.left)/rect.width;
    const y=(e.clientY-rect.top)/rect.height;
    if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'click',x:x,y:y,button:'right'}));
});
let touchStart=null;
overlay.addEventListener('touchstart',e=>{
    e.preventDefault();
    const rect=document.getElementById('screenImg').getBoundingClientRect();
    const t=e.touches[0];
    touchStart={x:(t.clientX-rect.left)/rect.width,y:(t.clientY-rect.top)/rect.height,t:Date.now()};
});
overlay.addEventListener('touchmove',e=>{
    e.preventDefault();
    if(!touchStart)return;
    const rect=document.getElementById('screenImg').getBoundingClientRect();
    const t=e.touches[0];
    const x=(t.clientX-rect.left)/rect.width;
    const y=(t.clientY-rect.top)/rect.height;
    if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'move',x:x,y:y}));
});
overlay.addEventListener('touchend',e=>{
    e.preventDefault();
    if(!touchStart)return;
    const dt=Date.now()-touchStart.t;
    if(dt<200){
        if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'click',x:touchStart.x,y:touchStart.y,button:'left'}));
    }
    touchStart=null;
});
connect();
</script>
</body>
</html>
""" }
}
