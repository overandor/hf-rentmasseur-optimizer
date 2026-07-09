//
// extract_massage_clients.swift
// Conversational Demand Accounting v4 — Priority Review Ledger
// Deterministic triage is source of truth. Ollama is optional schema-constrained enrichment.
// If Ollama is offline, the system still produces the review ledger, priority tiers, action labels, and receipts.
// Ollama can never promote a row past deterministic safety gates.
// Buckets: PRIORITY_REVIEW_CONTACT | HOLD_BOUNDARY | HOLD_INCOMPLETE | REJECTED | REJECTED_SERVICE_REFERENCE
// Every PRIORITY_REVIEW_CONTACT row has review_required=true, campaign_eligible=false until review decision exists.
// Outputs: all_messages.csv, all_thread_triage.csv, qualified_review_clients.csv,
//          response_gap_queue.csv, manual_review_leads.csv, rejected_threads.csv,
//          review_decisions.csv, outcome_events.csv, classification_receipts.jsonl,
//          demand_summary.json, qa_review.txt
// Run: swift extract_massage_clients.swift
//
import Foundation
import SQLite3
import CommonCrypto

// MARK: - Config
let DB = NSString(string: "~").expandingTildeInPath + "/Library/Messages/chat.db"
let OUT = NSString(string: "~").expandingTildeInPath + "/Documents"
let OLLAMA = "http://localhost:11434/api/generate"
let MODEL = ProcessInfo.processInfo.environment["OLLAMA_MODEL"] ?? "llama3.1:latest"
// Deterministic processing is fast — no network calls
let DET_BURST = 50
let DET_BURST_PAUSE = 0.0
let DET_PER_CONVO_DELAY = 0.0
// Ollama enrichment uses calmer micro-bursts — local models can return malformed output under load
let OLLAMA_BURST = 3
let OLLAMA_BURST_PAUSE = 2.0
let OLLAMA_PER_CONVO_DELAY = 0.5
let MAX_MSGS = 40
let PREFILTER = true
let RAW_PHONE_EXPORT = false
let EXPORT_EVIDENCE = false

// MARK: - Models
struct Convo {
    let handle: String; let total: Int; let inbound: Int; let outbound: Int
    let firstDate: String; let lastDate: String
    let inboundTexts: [String]; let outboundTexts: [String]
}
struct CL: Codable {
    var bucket: String?
    var is_massage: Bool?
    var category: String?
    var confidence: Double?
    var evidence: String?
    var intent_summary: String?
    var reply_angle: String?
    var risk_reason: String?
    var client_name: String?
    var booking_intent: Bool?
    var repeat_client: Bool?
    var price_discussed: Bool?
    var location_discussed: Bool?
    var service_keywords: String?
    var suggested_stage: String?
    var notes: String?
    var enrichment_status: String?
    // Deterministic fields
    var reason_code: String?
    var priority_score: Double?
    var priority_tier: String?
    var next_action: String?
    var response_gap: Bool?
    // Review lifecycle fields (always set for PRIORITY_REVIEW_CONTACT)
    var review_required: Bool?
    var review_status: String?
    var reviewed_at: String?
    var review_decision: String?
    var approved_reply_class: String?
}

// MARK: - Helpers
func a2d(_ ns: Double) -> String {
    let r = Date(timeIntervalSinceReferenceDate: 0).addingTimeInterval(ns / 1e9)
    let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime]; return f.string(from: r)
}
func sha256(_ s: String) -> String {
    let d = Data(s.utf8); var h = [UInt8](repeating: 0, count: 32)
    d.withUnsafeBytes { _ = CC_SHA256($0.baseAddress, CC_LONG(d.count), &h) }
    return h.map { String(format: "%02x", $0) }.joined()
}
func last4(_ h: String) -> String { h.count >= 4 ? String(h.suffix(4)) : h }
func esc(_ s: String?) -> String { "\"\((s ?? "").replacingOccurrences(of: "\"", with: "\"\"").replacingOccurrences(of: "\n", with: " "))\"" }
func daysSince(_ iso: String) -> Double {
    let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime]
    guard let d = f.date(from: iso) else { return 9999 }
    return Date().timeIntervalSince(d) / 86400
}

// MARK: - Keyword sets
let serviceKW: Set<String> = ["massage","bodywork","deep tissue","swedish","sports massage","therapeutic","recovery","neck","shoulder","tension","knot","table","draping","lmt","licensed massage","rentmasseur","rent masseur","masseur","table shower"]
// Strong booking keywords — always count as booking evidence on their own
let bookingStrongKW: Set<String> = ["book","booking","appointment","session","schedule","available","availability","rates","rate","price","incall","outcall","studio","address","location","hour","90 min","half hour","can i come","are you free","openings","slot","come over","be right up","travel"]
// Weak/time keywords — only count as booking evidence when paired with a service keyword AND an action/availability phrase
let bookingTimeKW: Set<String> = ["today","tonight","tomorrow","this week","morning","evening"]
// Action/availability phrases that elevate time words to booking evidence
let actionPhraseKW: Set<String> = ["are you","can you","do you","free for","around for","looking for","any availability","your availability","are u","u around","u free","hit you up","come see","come to","be at","let me know","checking your","checking if","wondering if","any chance","still doing","still available","open for"]
// Combined bookingKW for backward compatibility (used in priorityScore, foundKW, etc.)
let bookingKW: Set<String> = bookingStrongKW.union(bookingTimeKW)
// Regression test keyword set: if any inbound text contains massage + any of these, it must pass prefilter
let regressionServiceKW: Set<String> = ["massage","masseur","bodywork","deep tissue"]
let regressionBookingKW: Set<String> = ["tonight","today","tomorrow","available","book","booking","rate","rates","price","appointment","session","schedule","this week","are you free","can i come","openings","slot"]
// Service-reference-only patterns — complaint/warning/scam/story, not booking intent
let serviceRefOnlyKW: Set<String> = ["scammed","scam","fraud","complaint","warning","hired a","third party","nightmare","worried","ripoff","ripped off","bad experience","never again","stay away","beware","predatory"]
let priceKW: Set<String> = ["rate","rates","price","pricing","cost","how much","donation","fee","$","hr","hour","half hour","90 min","60 min","30 min"]
let locationKW: Set<String> = ["incall","outcall","studio","address","apt","apartment","where are you","location","near","zip","cross street"]
let optOutKW: Set<String> = ["stop","unsubscribe","remove","do not text","don't text","not interested","wrong number","stop texting","opt out","don't contact","do not contact","take me off","no more"]
let spamKW: Set<String> = ["verification code","reset code","password","otp","your google","your facebook","usps","delivery status","fedex","ups","loan","delinquent","edfinancial","authenticator","paired with","support team","msg&data","reply stop","reply help"]
let adultKW: Set<String> = ["nude","naked","full service","fs","bbbj","cim","gfe","happy ending","extras","mutual","body slide","sensual touch","erotic","full body release"," prostate","milking"]

// Normalize text for keyword matching: lowercase, strip diacritics, collapse whitespace
func normalize(_ s: String) -> String {
    return s.lowercased()
        .folding(options: .diacriticInsensitive, locale: Locale(identifier: "en_US"))
        .replacingOccurrences(of: "\u{2019}", with: "'") // smart quote to ascii
        .replacingOccurrences(of: "\u{2018}", with: "'")
        .replacingOccurrences(of: "\u{201c}", with: "\"")
        .replacingOccurrences(of: "\u{201d}", with: "\"")
        .replacingOccurrences(of: "\u{2014}", with: "-")
        .replacingOccurrences(of: "\t", with: " ")
        .replacingOccurrences(of: "  ", with: " ")
}
func normJoin(_ texts: [String]) -> String { normalize(texts.joined(separator: " ")) }

func textContains(_ texts: [String], _ kws: Set<String>) -> Bool {
    let c = normJoin(texts)
    return kws.contains { c.contains($0) }
}
func hasServiceAndBookingEvidence(_ texts: [String]) -> Bool {
    let c = normJoin(texts)
    let hasSrv = serviceKW.contains(where: { c.contains($0) })
    if !hasSrv { return false }
    // Strong booking keyword always counts
    if bookingStrongKW.contains(where: { c.contains($0) }) { return true }
    // Regression rule: massage + regression booking keywords must pass
    if regressionServiceKW.contains(where: { c.contains($0) }) && regressionBookingKW.contains(where: { c.contains($0) }) { return true }
    // Weak/time keywords only count when paired with an action/availability phrase
    if bookingTimeKW.contains(where: { c.contains($0) }) && actionPhraseKW.contains(where: { c.contains($0) }) { return true }
    return false
}
func hasServiceAndBookingEvidenceFullThread(_ handle: String, _ db: OpaquePointer?) -> Bool {
    guard let db = db else { return false }
    // Full-thread keyword scan: check ALL messages for service + booking evidence
    var st: OpaquePointer?
    let q = "SELECT m.text FROM message m JOIN handle h ON m.handle_id=h.ROWID WHERE h.id=? AND m.text IS NOT NULL AND m.text!=''"
    guard sqlite3_prepare_v2(db, q, -1, &st, nil) == SQLITE_OK else { return false }
    defer { sqlite3_finalize(st) }
    sqlite3_bind_text(st, 1, handle, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
    var allText: String = ""
    while sqlite3_step(st) == SQLITE_ROW {
        let tx = String(cString: sqlite3_column_text(st, 0))
        allText += " " + tx
        // Early exit: if we find both service and booking evidence, stop scanning
        let c = normalize(allText)
        if serviceKW.contains(where: { c.contains($0) }) {
            if bookingStrongKW.contains(where: { c.contains($0) }) { return true }
            if bookingTimeKW.contains(where: { c.contains($0) }) && actionPhraseKW.contains(where: { c.contains($0) }) { return true }
            if regressionBookingKW.contains(where: { c.contains($0) }) { return true }
        }
    }
    return false
}
func isServiceReferenceOnly(_ texts: [String]) -> Bool {
    let c = normJoin(texts)
    guard serviceKW.contains(where: { c.contains($0) }) else { return false }
    guard !bookingStrongKW.contains(where: { c.contains($0) }) else { return false }
    // If service-reference-only patterns present and no direct booking intent
    if serviceRefOnlyKW.contains(where: { c.contains($0) }) {
        // Check if there's also a direct booking question — if so, it's not reference-only
        let hasBookingQuestion = actionPhraseKW.contains(where: { c.contains($0) }) && bookingTimeKW.contains(where: { c.contains($0) })
        if !hasBookingQuestion { return true }
    }
    return false
}
func foundKW(_ texts: [String], _ kws: Set<String>) -> [String] {
    let c = normJoin(texts)
    return kws.filter { c.contains($0) }.sorted()
}
func detectOptOut(_ texts: [String]) -> Bool { textContains(texts, optOutKW) }

// MARK: - Deterministic triage (hard gate, runs before Ollama)
func deterministicTriage(_ c: Convo) -> (String, String) {
    let allTexts = c.inboundTexts + c.outboundTexts
    let hasService = textContains(allTexts, serviceKW)
    let hasStrongBooking = textContains(allTexts, bookingStrongKW)
    let hasTimeBooking = textContains(allTexts, bookingTimeKW) && textContains(allTexts, actionPhraseKW)
    let hasBooking = hasStrongBooking || hasTimeBooking
    let hasPrice = textContains(allTexts, priceKW)
    let hasLocation = textContains(allTexts, locationKW)
    let isSpam = textContains(allTexts, spamKW)
    let isOptOut = detectOptOut(c.inboundTexts)
    let isAdult = textContains(allTexts, adultKW)
    let isRefOnly = isServiceReferenceOnly(c.inboundTexts)

    if isOptOut { return ("REJECTED", "optout_detected") }
    if isSpam && !hasService { return ("REJECTED", "spam_nonphone_or_system_handle") }
    // Service-reference guard: complaint/scam/warning about a masseur is not booking intent
    if isRefOnly { return ("REJECTED_SERVICE_REFERENCE", "service_reference_only_no_booking_intent") }
    if !hasService && !hasBooking { return ("REJECTED", "no_explicit_service_evidence") }
    if hasBooking && !hasService { return ("REJECTED", "booking_language_without_service") }
    if hasService && isAdult && !hasBooking && !hasPrice && !hasLocation {
        return ("HOLD_BOUNDARY", "service_mention_adult_or_boundary_sensitive")
    }
    if hasService && (hasBooking || hasPrice || hasLocation) {
        if isAdult { return ("HOLD_BOUNDARY", "service_plus_booking_but_adult_coded") }
        return ("PRIORITY_REVIEW_CONTACT", "explicit_service_plus_booking_evidence")
    }
    if hasService && !hasBooking && !hasPrice && !hasLocation {
        return ("HOLD_INCOMPLETE", "service_mention_incomplete_no_booking_cue")
    }
    return ("HOLD_INCOMPLETE", "service_mention_incomplete_no_booking_cue")
}

// MARK: - Transparent priority score (additive weighted formula)
func priorityScore(_ c: Convo, _ cl: CL) -> (Double, String, String) {
    let ageDays = daysSince(c.lastDate)
    let hasService = textContains(c.inboundTexts + c.outboundTexts, serviceKW)
    let hasBooking = textContains(c.inboundTexts + c.outboundTexts, bookingKW)
    let hasPrice = textContains(c.inboundTexts + c.outboundTexts, priceKW)
    let hasLocation = textContains(c.inboundTexts + c.outboundTexts, locationKW)
    let noOutbound = c.outbound == 0
    let twoWay = c.inbound > 0 && c.outbound > 0

    let isRepeat = cl.repeat_client ?? false

    var score: Double = 0
    if hasService { score += 25 }
    if hasBooking { score += 25 }
    if hasPrice { score += 10 }
    if hasLocation { score += 10 }
    // Hardened age decay — stale rows fall fast unless repeat-client evidence
    if ageDays <= 2 { score += 30 }
    else if ageDays <= 7 { score += 20 }
    else if ageDays <= 30 { score += 10 }
    else if ageDays <= 90 { score -= 10 }
    else if ageDays <= 180 { score -= 30 }
    else { score -= 50 }
    if ageDays > 90 && !isRepeat { score -= 10 } // extra penalty for stale non-repeat
    score += min(15, log2(Double(c.inbound + 1)) * 4)
    if twoWay { score += 5 }
    if noOutbound { score += 15 }

    let tier: String
    if score >= 110 && ageDays < 3 { tier = "P0_urgent" }
    else if score >= 50 && ageDays <= 90 { tier = "P1_high" }
    else if score >= 50 && ageDays > 90 && isRepeat { tier = "P1_high" }
    else if score >= 25 { tier = "P2_review" }
    else { tier = "P3_weak_or_old" }

    let action: String
    switch cl.bucket {
    case "PRIORITY_REVIEW_CONTACT":
        switch tier {
        case "P0_urgent": action = noOutbound ? "review_now_prepare_same_day_reply_draft_no_prior_outbound_flag" : "review_now_prepare_same_day_reply_draft"
        case "P1_high": action = noOutbound ? "review_today_prepare_booking_clarity_reply_no_prior_outbound_flag" : "review_today_prepare_booking_clarity_reply"
        case "P2_review": action = "review_when_free_need_context_before_message"
        default: action = "archive_or_low_priority_review"
        }
    case "HOLD_BOUNDARY": action = "manual_boundary_review_do_not_automate"
    case "HOLD_INCOMPLETE": action = "hold_for_new_inbound_recheck"
    case "REJECTED": action = "no_action"
    case "REJECTED_SERVICE_REFERENCE": action = "no_action_service_reference"
    default: action = "review_manually"
    }
    return (score, tier, action)
}

// MARK: - Fetch conversations (parameterized SQLite)
func fetch() -> [Convo] {
    var db: OpaquePointer?
    guard sqlite3_open(DB, &db) == SQLITE_OK else { print("ERR: open \(DB)"); exit(1) }
    defer { sqlite3_close(db) }
    var st: OpaquePointer?
    let q = "SELECT h.id,COUNT(*),SUM(m.is_from_me=0),SUM(m.is_from_me=1),MIN(m.date),MAX(m.date) FROM message m JOIN handle h ON m.handle_id=h.ROWID WHERE m.text IS NOT NULL AND m.text!='' GROUP BY h.id ORDER BY COUNT(*) DESC"
    guard sqlite3_prepare_v2(db, q, -1, &st, nil) == SQLITE_OK else { print("ERR: query"); exit(1) }
    defer { sqlite3_finalize(st) }
    var cs: [Convo] = []
    while sqlite3_step(st) == SQLITE_ROW {
        let h = String(cString: sqlite3_column_text(st, 0))
        let t = Int(sqlite3_column_int(st, 1)), i = Int(sqlite3_column_int(st, 2)), o = Int(sqlite3_column_int(st, 3))
        let f = a2d(sqlite3_column_double(st, 4)), l = a2d(sqlite3_column_double(st, 5))
        var ms: OpaquePointer?; var ib: [String] = []; var ob: [String] = []
        let mq = "SELECT m.text,m.is_from_me FROM message m JOIN handle h ON m.handle_id=h.ROWID WHERE h.id=? AND m.text IS NOT NULL ORDER BY m.date DESC LIMIT ?"
        if sqlite3_prepare_v2(db, mq, -1, &ms, nil) == SQLITE_OK {
            sqlite3_bind_text(ms, 1, h, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
            sqlite3_bind_int(ms, 2, Int32(MAX_MSGS))
            while sqlite3_step(ms) == SQLITE_ROW {
                let tx = String(cString: sqlite3_column_text(ms, 0))
                if sqlite3_column_int(ms, 1) == 1 { ob.append(tx) } else { ib.append(tx) }
            }
            sqlite3_finalize(ms)
        }
        cs.append(Convo(handle: h, total: t, inbound: i, outbound: o, firstDate: f, lastDate: l, inboundTexts: ib, outboundTexts: ob))
    }
    return cs
}

// MARK: - Export ALL messages (streaming, local only)
func exportAllMessages() {
    var db: OpaquePointer?
    guard sqlite3_open(DB, &db) == SQLITE_OK else { print("ERR: open"); return }
    defer { sqlite3_close(db) }
    var st: OpaquePointer?
    let q = """
    SELECT h.id, m.date, m.is_from_me, m.text
    FROM message m JOIN handle h ON m.handle_id = h.ROWID
    WHERE m.text IS NOT NULL AND m.text != ''
    ORDER BY m.date ASC
    """
    guard sqlite3_prepare_v2(db, q, -1, &st, nil) == SQLITE_OK else { print("ERR: all-msg query"); return }
    defer { sqlite3_finalize(st) }
    try? FileManager.default.createDirectory(atPath: OUT, withIntermediateDirectories: true)
    let path = OUT + "/all_messages.csv"
    FileManager.default.createFile(atPath: path, contents: nil)
    let fh = FileHandle(forWritingAtPath: path)!
    fh.write("handle,date_iso,direction,text\n".data(using: .utf8)!)
    var count = 0
    while sqlite3_step(st) == SQLITE_ROW {
        let h = String(cString: sqlite3_column_text(st, 0))
        let dt = a2d(sqlite3_column_double(st, 1))
        let dir = sqlite3_column_int(st, 2) == 1 ? "outbound" : "inbound"
        let txt = String(cString: sqlite3_column_text(st, 3))
            .replacingOccurrences(of: "\"", with: "\"\"")
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: "")
        fh.write("\"\(h)\",\"\(dt)\",\"\(dir)\",\"\(txt)\"\n".data(using: .utf8)!)
        count += 1
    }
    fh.closeFile()
    print("  Exported \(count) messages to all_messages.csv")
}

// MARK: - Ollama structured output schema (enforces response shape)
let enrichSchema: [String: Any] = [
    "type": "object",
    "properties": [
        "is_massage": ["type": "boolean"],
        "category": ["type": "string", "enum": ["MASSAGE_CLIENT", "MASSAGE_LEAD", "MASSAGE_RELATED", "NOT_MASSAGE", "UNKNOWN"]],
        "confidence": ["type": "number"],
        "evidence": ["type": "string", "description": "Direct short quote from the messages proving massage/bodywork"],
        "client_name": ["type": "string"],
        "booking_intent": ["type": "boolean"],
        "repeat_client": ["type": "boolean"],
        "price_discussed": ["type": "boolean"],
        "location_discussed": ["type": "boolean"],
        "intent_summary": ["type": "string", "description": "One-sentence summary of what the person wants"],
        "reply_angle": ["type": "string", "description": "Suggested reply approach in 10 words or less"],
        "risk_reason": ["type": "string", "description": "Any risk, boundary, or ambiguity concern, or 'none'"],
        "service_keywords": ["type": "string"],
        "suggested_stage": ["type": "string", "enum": ["curious", "inquired", "booked", "active", "lapsed", "opted_out"]],
        "notes": ["type": "string"]
    ] as [String: Any],
    "required": ["is_massage", "category", "confidence", "evidence", "client_name", "booking_intent", "repeat_client", "price_discussed", "location_discussed", "intent_summary", "reply_angle", "risk_reason", "suggested_stage", "notes"]
] as [String: Any]

// MARK: - Ollama enrichment (summarizer after deterministic gate, temp=0.0, one retry)
func enrich(_ c: Convo, _ detBucket: String, _ detReason: String) -> CL? {
    let ib = c.inboundTexts.prefix(15).map { String($0.prefix(300)) }
    let ob = c.outboundTexts.prefix(10).map { String($0.prefix(300)) }
    let ibStr = ib.map { $0.replacingOccurrences(of: "\"", with: "'") }.joined(separator: " | ")
    let obStr = ob.map { $0.replacingOccurrences(of: "\"", with: "'") }.joined(separator: " | ")
    let system = """
    You are a classifier for a massage therapy practice's iMessage demand ledger.
    The deterministic triage has ALREADY assigned the bucket. Do NOT reclassify.
    Your job: produce a concise enrichment for the already-assigned bucket.

    Classify only legitimate massage/bodywork business conversations.
    A conversation is MASSAGE_CLIENT only if it contains explicit evidence of massage/bodywork AND at least one booking/session/location/price cue.
    Do not infer massage from:
    - "come over"
    - "be right up"
    - "available"
    - "$300"
    - "effective"
    - "appointment"
    - sexual/personal language
    - relationship conflict
    - legal/personal logistics
    - dinner/social plans
    If the conversation contains adult/sexual/personal content without explicit legitimate massage/bodywork wording, return NOT_MASSAGE.
    If there is no exact quote proving massage/bodywork, return NOT_MASSAGE or UNKNOWN.
    Evidence must be a direct short quote from the messages.

    Given bucket \(detBucket) (reason: \(detReason)), produce:
    - is_massage: true only if explicit massage/bodywork evidence exists
    - category: MASSAGE_CLIENT / MASSAGE_LEAD / MASSAGE_RELATED / NOT_MASSAGE / UNKNOWN
    - confidence: 0.0-1.0
    - evidence: direct short quote from a message
    - intent_summary: what does this person want? (one sentence)
    - reply_angle: suggested reply approach (10 words max)
    - risk_reason: any boundary/adult/ambiguity risk, or "none"
    - booking_intent: did they ask to book/schedule?
    - repeat_client: have they visited before?
    - price_discussed: was rate/price mentioned?
    - location_discussed: was incall/outcall/address mentioned?
    - service_keywords: massage-related terms found
    - suggested_stage: curious/inquired/booked/active/lapsed/opted_out
    """
    let prompt = """
    Bucket: \(detBucket) | Reason: \(detReason)
    Inbound: \(ibStr)
    Outbound: \(obStr)
    Total: \(c.total) | Inbound: \(c.inbound) | Outbound: \(c.outbound)
    """
    let payload: [String: Any] = [
        "model": MODEL, "system": system, "prompt": prompt,
        "stream": false, "format": enrichSchema,
        "options": ["temperature": 0.0, "num_predict": 256]
    ]
    guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return nil }
    guard let url = URL(string: OLLAMA) else { return nil }

    func callOllama() -> Data? {
        var req = URLRequest(url: url); req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body; req.timeoutInterval = 90
        let sem = DispatchSemaphore(value: 0); var result: Data? = nil
        URLSession.shared.dataTask(with: req) { d, _, _ in result = d; sem.signal() }.resume()
        _ = sem.wait(timeout: .distantFuture)
        return result
    }

    // First attempt
    guard let data = callOllama() else { return nil }
    // One retry if response parse fails
    guard let parsed = parseOllamaResponse(data) else {
        guard let retryData = callOllama() else { return nil }
        return parseOllamaResponse(retryData)
    }
    return parsed
}

func parseOllamaResponse(_ data: Data) -> CL? {
    guard let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
    guard let r = j["response"] as? String else { return nil }
    var s = r.trimmingCharacters(in: .whitespacesAndNewlines)
    if s.hasPrefix("```") { s = String(s.dropFirst(3)); if let nl = s.firstIndex(of: "\n") { s = String(s[s.index(after: nl)...]) } }
    if s.hasSuffix("```") { s = String(s.dropLast(3)) }
    s = s.trimmingCharacters(in: .whitespacesAndNewlines)
    if let fb = s.firstIndex(of: "{"), let lb = s.lastIndex(of: "}") { s = String(s[fb...lb]) }
    s = s.replacingOccurrences(of: "//[^\n]*", with: "", options: .regularExpression)
    s = s.replacingOccurrences(of: ",\\s*}", with: "}", options: .regularExpression)
    s = s.replacingOccurrences(of: ",\\s*]", with: "]", options: .regularExpression)
    guard let d = s.data(using: .utf8) else { return nil }
    if let cl = try? JSONDecoder().decode(CL.self, from: d) { return cl }
    if let dict = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
        var cl = CL()
        cl.is_massage = dict["is_massage"] as? Bool
        cl.category = dict["category"] as? String
        cl.confidence = dict["confidence"] as? Double
        cl.intent_summary = dict["intent_summary"] as? String
        cl.reply_angle = dict["reply_angle"] as? String
        cl.risk_reason = dict["risk_reason"] as? String
        cl.evidence = dict["evidence"] as? String
        cl.client_name = dict["client_name"] as? String
        cl.booking_intent = dict["booking_intent"] as? Bool
        cl.repeat_client = dict["repeat_client"] as? Bool
        cl.price_discussed = dict["price_discussed"] as? Bool
        cl.location_discussed = dict["location_discussed"] as? Bool
        cl.service_keywords = dict["service_keywords"] as? String
        cl.suggested_stage = dict["suggested_stage"] as? String
        cl.notes = dict["notes"] as? String
        return cl
    }
    return nil
}

// MARK: - Evidence redaction
func redactedEvidence(_ cl: CL) -> String {
    guard EXPORT_EVIDENCE else { return "[local_only]" }
    return cl.evidence ?? ""
}

// MARK: - Output: all thread triage
func writeTriage(_ res: [(Convo, CL)]) {
    try? FileManager.default.createDirectory(atPath: OUT, withIntermediateDirectories: true)
    let header = "handle_hash,last4,total_messages,inbound_count,outbound_count,first_date,last_date,bucket,reason_code,enrichment_status,confidence,priority_score,priority_tier,next_action,response_gap,booking_intent,repeat_client,price_discussed,location_discussed,opt_out_detected,do_not_contact,campaign_eligible,review_required,review_status,reviewed_at,review_decision,approved_reply_class,suggested_stage,service_keywords,evidence_class,intent_summary,reply_angle,risk_reason,notes"
    var lines = [header]
    for (c, cl) in res {
        let optOut = detectOptOut(c.inboundTexts)
        let dnc = optOut || (cl.bucket == "REJECTED")
        let eligible = false // campaign_eligible is always false until a review decision exists in review_decisions.csv
        let reviewRequired = cl.bucket == "PRIORITY_REVIEW_CONTACT" && !dnc
        let hh = RAW_PHONE_EXPORT ? c.handle : sha256(c.handle)
        lines.append([
            esc(hh), esc(last4(c.handle)), String(c.total), String(c.inbound), String(c.outbound),
            esc(c.firstDate), esc(c.lastDate), esc(cl.bucket), esc(cl.reason_code), esc(cl.enrichment_status ?? "deterministic_only"),
            String(cl.confidence ?? 0), String(cl.priority_score ?? 0), esc(cl.priority_tier), esc(cl.next_action),
            String(cl.response_gap ?? false),
            String(cl.booking_intent ?? false), String(cl.repeat_client ?? false),
            String(cl.price_discussed ?? false), String(cl.location_discussed ?? false),
            String(optOut), String(dnc), String(eligible),
            String(reviewRequired), "pending", "", "", "",
            esc(cl.suggested_stage), esc(cl.service_keywords), esc(redactedEvidence(cl)),
            esc(cl.intent_summary), esc(cl.reply_angle), esc(cl.risk_reason), esc(cl.notes)
        ].joined(separator: ","))
    }
    try? lines.joined(separator: "\n").write(toFile: OUT + "/all_thread_triage.csv", atomically: true, encoding: .utf8)
}

// MARK: - Output: PRIORITY_REVIEW_CONTACT only (qualified_review_clients.csv)
func writePriorityContact(_ res: [(Convo, CL)]) {
    let pool = res.filter { $0.1.bucket == "PRIORITY_REVIEW_CONTACT" && !detectOptOut($0.0.inboundTexts) }
    let header = "handle_hash,last4,bucket,reason_code,priority_score,priority_tier,next_action,response_gap,review_required,review_status,campaign_eligible,suggested_stage,total_messages,inbound_count,outbound_count,age_days,last_date,booking_intent,repeat_client,price_discussed,location_discussed,service_keywords,evidence_class,intent_summary,reply_angle,risk_reason,notes"
    var lines = [header]
    for (c, cl) in pool.sorted(by: { ($0.1.priority_score ?? 0) > ($1.1.priority_score ?? 0) }) {
        lines.append([
            esc(sha256(c.handle)), esc(last4(c.handle)), esc(cl.bucket), esc(cl.reason_code),
            String(cl.priority_score ?? 0), esc(cl.priority_tier), esc(cl.next_action),
            String(cl.response_gap ?? false),
            String(cl.review_required ?? false), esc(cl.review_status ?? "pending"), String(false),
            esc(cl.suggested_stage), String(c.total), String(c.inbound), String(c.outbound),
            String(Int(daysSince(c.lastDate))), esc(c.lastDate),
            String(cl.booking_intent ?? false), String(cl.repeat_client ?? false),
            String(cl.price_discussed ?? false), String(cl.location_discussed ?? false),
            esc(cl.service_keywords), esc(redactedEvidence(cl)),
            esc(cl.intent_summary), esc(cl.reply_angle), esc(cl.risk_reason), esc(cl.notes)
        ].joined(separator: ","))
    }
    try? lines.joined(separator: "\n").write(toFile: OUT + "/qualified_review_clients.csv", atomically: true, encoding: .utf8)
}

// MARK: - Output: response gap queue (PRIORITY_REVIEW_CONTACT with zero outbound — the money tab)
func writeResponseGap(_ res: [(Convo, CL)]) {
    let pool = res.filter { $0.1.bucket == "PRIORITY_REVIEW_CONTACT" && $0.0.outbound == 0 && !detectOptOut($0.0.inboundTexts) }
    let header = "handle_hash,last4,priority_tier,priority_score,age_days,total_messages,inbound_count,last_date,service_keywords,intent_summary,reply_angle,risk_reason,next_action"
    var lines = [header]
    for (c, cl) in pool.sorted(by: { ($0.1.priority_score ?? 0) > ($1.1.priority_score ?? 0) }) {
        lines.append([
            esc(sha256(c.handle)), esc(last4(c.handle)), esc(cl.priority_tier), String(cl.priority_score ?? 0),
            String(Int(daysSince(c.lastDate))), String(c.total), String(c.inbound), esc(c.lastDate),
            esc(cl.service_keywords), esc(cl.intent_summary), esc(cl.reply_angle), esc(cl.risk_reason),
            esc(cl.next_action)
        ].joined(separator: ","))
    }
    try? lines.joined(separator: "\n").write(toFile: OUT + "/response_gap_queue.csv", atomically: true, encoding: .utf8)
}

// MARK: - Output: manual review leads (HOLD_BOUNDARY + HOLD_INCOMPLETE)
func writeReviewLeads(_ res: [(Convo, CL)]) {
    let pool = res.filter { $0.1.bucket == "HOLD_BOUNDARY" || $0.1.bucket == "HOLD_INCOMPLETE" }
    let header = "handle_hash,last4,bucket,reason_code,priority_score,priority_tier,next_action,suggested_stage,total_messages,inbound_count,outbound_count,age_days,last_date,booking_intent,repeat_client,price_discussed,location_discussed,service_keywords,evidence_class,intent_summary,risk_reason,notes"
    var lines = [header]
    for (c, cl) in pool.sorted(by: { ($0.1.priority_score ?? 0) > ($1.1.priority_score ?? 0) }) {
        lines.append([
            esc(sha256(c.handle)), esc(last4(c.handle)), esc(cl.bucket), esc(cl.reason_code),
            String(cl.priority_score ?? 0), esc(cl.priority_tier), esc(cl.next_action),
            esc(cl.suggested_stage), String(c.total), String(c.inbound), String(c.outbound),
            String(Int(daysSince(c.lastDate))), esc(c.lastDate),
            String(cl.booking_intent ?? false), String(cl.repeat_client ?? false),
            String(cl.price_discussed ?? false), String(cl.location_discussed ?? false),
            esc(cl.service_keywords), esc(redactedEvidence(cl)),
            esc(cl.intent_summary), esc(cl.risk_reason), esc(cl.notes)
        ].joined(separator: ","))
    }
    try? lines.joined(separator: "\n").write(toFile: OUT + "/manual_review_leads.csv", atomically: true, encoding: .utf8)
}

// MARK: - Output: rejected threads
func writeRejected(_ res: [(Convo, CL)]) {
    let pool = res.filter { $0.1.bucket == "REJECTED" || $0.1.bucket == "REJECTED_SERVICE_REFERENCE" }
    let header = "handle_hash,last4,bucket,reason_code,priority_tier,total_messages,last_date,notes"
    var lines = [header]
    for (c, cl) in pool.sorted(by: { ($0.1.priority_score ?? 0) > ($1.1.priority_score ?? 0) }) {
        lines.append([
            esc(sha256(c.handle)), esc(last4(c.handle)), esc(cl.bucket), esc(cl.reason_code),
            esc(cl.priority_tier), String(c.total), esc(c.lastDate), esc(cl.notes)
        ].joined(separator: ","))
    }
    try? lines.joined(separator: "\n").write(toFile: OUT + "/rejected_threads.csv", atomically: true, encoding: .utf8)
}

// MARK: - Output: review_decisions.csv (empty template for operator)
func writeReviewDecisionsTemplate() {
    let header = "handle_hash,last4,review_status,reviewed_at,reviewer,review_decision,reason,approved_reply_class,do_not_contact"
    try? header.write(toFile: OUT + "/review_decisions.csv", atomically: true, encoding: .utf8)
}

// MARK: - Output: outcome_events.csv (empty template for operator)
func writeOutcomeEventsTemplate() {
    let header = "handle_hash,last4,event_type,event_ts,amount_collected,notes"
    try? header.write(toFile: OUT + "/outcome_events.csv", atomically: true, encoding: .utf8)
}

// MARK: - Output: receipts (JSONL)
func writeReceipts(_ res: [(Convo, CL)]) {
    var lines: [String] = []
    for (c, cl) in res {
        let receipt: [String: Any] = [
            "ts": ISO8601DateFormatter().string(from: Date()),
            "handle_hash": sha256(c.handle), "last4": last4(c.handle),
            "total_messages": c.total, "bucket": cl.bucket ?? "UNKNOWN",
            "reason_code": cl.reason_code ?? "",
            "enrichment_status": cl.enrichment_status ?? "deterministic_only",
            "priority_tier": cl.priority_tier ?? "", "priority_score": cl.priority_score ?? 0,
            "response_gap": cl.response_gap ?? false,
            "opt_out_detected": detectOptOut(c.inboundTexts),
            "model": MODEL, "local_only": true
        ]
        if let d = try? JSONSerialization.data(withJSONObject: receipt) {
            lines.append(String(data: d, encoding: .utf8) ?? "{}")
        }
    }
    try? lines.joined(separator: "\n").write(toFile: OUT + "/classification_receipts.jsonl", atomically: true, encoding: .utf8)
}

// MARK: - Output: demand summary JSON with KPIs
func writeSummary(_ res: [(Convo, CL)], _ totalThreads: Int) {
    let pc = res.filter { $0.1.bucket == "PRIORITY_REVIEW_CONTACT" }
    let hb = res.filter { $0.1.bucket == "HOLD_BOUNDARY" }
    let hi = res.filter { $0.1.bucket == "HOLD_INCOMPLETE" }
    let rej = res.filter { $0.1.bucket == "REJECTED" || $0.1.bucket == "REJECTED_SERVICE_REFERENCE" }
    let refOnly = res.filter { $0.1.bucket == "REJECTED_SERVICE_REFERENCE" }
    let optOuts = res.filter { detectOptOut($0.0.inboundTexts) }
    let responseGap = pc.filter { $0.0.outbound == 0 }
    let fresh = pc.filter { daysSince($0.0.lastDate) <= 7 }
    let urgent = pc.filter { ($0.1.priority_tier ?? "") == "P0_urgent" }
    let reasonCounts = Dictionary(grouping: res, by: { $0.1.reason_code ?? "unknown" }).mapValues { $0.count }
    let pcMsgs = pc.reduce(0) { $0 + $1.0.total }
    let twoWay = pc.filter { $0.0.inbound > 0 && $0.0.outbound > 0 }.count

    let prefilterPassRate = totalThreads > 0 ? Double(res.count) / Double(totalThreads) : 0
    let pcRateSeen = totalThreads > 0 ? Double(pc.count) / Double(totalThreads) : 0
    let pcRateAnalyzed = res.count > 0 ? Double(pc.count) / Double(res.count) : 0
    let ambRateSeen = totalThreads > 0 ? Double(hb.count + hi.count) / Double(totalThreads) : 0
    let ambRateAnalyzed = res.count > 0 ? Double(hb.count + hi.count) / Double(res.count) : 0
    let rejRateSeen = totalThreads > 0 ? Double(rej.count) / Double(totalThreads) : 0
    let rejRateAnalyzed = res.count > 0 ? Double(rej.count) / Double(res.count) : 0
    let msgDensity = pc.count > 0 ? Double(pcMsgs) / Double(pc.count) : 0
    let gapRate = pc.count > 0 ? Double(responseGap.count) / Double(pc.count) : 0

    let bucketCounts: [String: Int] = [
        "PRIORITY_REVIEW_CONTACT": pc.count,
        "HOLD_BOUNDARY": hb.count,
        "HOLD_INCOMPLETE": hi.count,
        "REJECTED": rej.count,
        "REJECTED_SERVICE_REFERENCE": refOnly.count
    ]

    let reviewKpi: [String: Any] = [
        "unresponded_priority_recovery_rate": "reviewed_zero_outbound_priority_threads / zero_outbound_priority_threads",
        "zero_outbound_priority_threads": responseGap.count,
        "reviewed_zero_outbound": 0,
        "reply_to_call_rate": "real_calls_from_reviewed_priority_threads / approved_priority_threads",
        "booking_recovery_rate": "bookings_from_reviewed_priority_threads / approved_priority_threads",
        "note": "Populate from review_decisions.csv and outcome_events.csv once operator reviews"
    ]

    let kpi: [String: Any] = [
        "priority_contact_rate_seen": pcRateSeen,
        "priority_contact_rate_analyzed": pcRateAnalyzed,
        "manual_ambiguity_rate_seen": ambRateSeen,
        "manual_ambiguity_rate_analyzed": ambRateAnalyzed,
        "rejection_rate_seen": rejRateSeen,
        "rejection_rate_analyzed": rejRateAnalyzed,
        "qualified_message_density": msgDensity,
        "untouched_qualified_demand": responseGap.count,
        "response_gap_rate_within_priority": gapRate,
        "fresh_qualified_demand": fresh.count,
        "urgent_demand_count": urgent.count,
        "two_way_threads": twoWay,
        "opt_outs_detected": optOuts.count,
        "review_kpi": reviewKpi
    ]

    let pcDetail: [[String: Any]] = pc.map { (c, cl) in
        ["handle_hash": sha256(c.handle), "last4": last4(c.handle),
         "priority_score": cl.priority_score ?? 0, "priority_tier": cl.priority_tier ?? "?",
         "stage": cl.suggested_stage ?? "?", "total_messages": c.total,
         "outbound_count": c.outbound, "response_gap": c.outbound == 0,
         "reason_code": cl.reason_code ?? ""] as [String: Any]
    }

    let holdDetail: [[String: Any]] = (hb + hi).map { (c, cl) in
        ["handle_hash": sha256(c.handle), "last4": last4(c.handle),
         "bucket": cl.bucket ?? "?", "reason_code": cl.reason_code ?? "",
         "total_messages": c.total] as [String: Any]
    }

    let summary: [String: Any] = [
        "generated": ISO8601DateFormatter().string(from: Date()),
        "model": MODEL, "local_only": true,
        "total_threads_seen": totalThreads,
        "threads_analyzed_after_prefilter": res.count,
        "prefilter_pass_rate": prefilterPassRate,
        "bucket_counts": bucketCounts,
        "reason_code_breakdown": reasonCounts,
        "kpi": kpi,
        "priority_review_contact_detail": pcDetail,
        "hold_detail": holdDetail
    ]
    if let d = try? JSONSerialization.data(withJSONObject: summary, options: .prettyPrinted) {
        try? d.write(to: URL(fileURLWithPath: OUT + "/demand_summary.json"))
    }
}

// MARK: - Recall regression audit (compares disassembly vs v4 output)
func writeRecallRegressionAudit(_ res: [(Convo, CL)], _ allCs: [Convo]) {
    let disassemblyPath = OUT + "/qualified_priority_disassembly.csv"
    guard FileManager.default.fileExists(atPath: disassemblyPath) else { return }
    guard let disContent = try? String(contentsOfFile: disassemblyPath, encoding: .utf8) else { return }
    let disRows = disContent.split(separator: "\n").dropFirst().map { String($0) }
    var disLast4: [String: [String]] = [:] // last4 -> [raw row fields]
    for row in disRows {
        let cols = row.split(separator: ",", maxSplits: 1).map { String($0) }
        if cols.count >= 1 { disLast4[cols[0]] = cols }
    }

    let v4Last4 = Set(res.compactMap { $0.1.bucket == "PRIORITY_REVIEW_CONTACT" ? last4($0.0.handle) : nil })
    let allByLast4: [String: Convo] = Dictionary(allCs.map { (last4($0.handle), $0) }, uniquingKeysWith: { a, _ in a })
    // Also build a suffix-match index for padded last4 mismatches (e.g. disassembly "206" vs handle "0206")
    let allBySuffix: [String: Convo] = Dictionary(allCs.map { (c) -> (String, Convo) in
        let l4 = last4(c.handle)
        // Index by last 3 chars too, for cases where disassembly stripped leading zero
        let l3 = String(l4.suffix(3))
        return (l3, c)
    }, uniquingKeysWith: { a, _ in a })

    func findConvo(_ l4: String) -> Convo? {
        if let c = allByLast4[l4] { return c }
        // Try zero-padded version
        if l4.count < 4, let c = allByLast4[String(repeating: "0", count: 4 - l4.count) + l4] { return c }
        // Try suffix match (last 3 chars)
        if l4.count >= 3, let c = allBySuffix[String(l4.suffix(3))] { return c }
        return nil
    }

    var lines = ["last4,handle_hash,present_in_disassembly,present_in_v4,expected_bucket,actual_bucket,raw_inbound_preview,raw_outbound_preview,service_hits,booking_hits,boundary_hits,optout_hits,prefilter_pass,drop_stage,drop_reason,recommended_fix"]

    for (l4, disCols) in disLast4.sorted(by: { $0.key < $1.key }) {
        guard let c = findConvo(l4) else {
            lines.append("\(l4),,true,false,\(disCols.count > 1 ? disCols[1] : "?"),NOT_FOUND,,,,,,,false,handle_not_found,handle_not_in_corpus,investigate_handle_mismatch")
            continue
        }
        let actualL4 = last4(c.handle)
        let inV4 = v4Last4.contains(actualL4)
        let inDis = true
        let expectedBucket = "PRIORITY_REVIEW_CONTACT"
        let actualBucket = res.first(where: { last4($0.0.handle) == actualL4 })?.1.bucket ?? "NOT_IN_OUTPUT"
        let ibPreview = esc(String(c.inboundTexts.prefix(3).joined(separator: " | ").prefix(200)))
        let obPreview = esc(String(c.outboundTexts.prefix(3).joined(separator: " | ").prefix(200)))
        let sHits = foundKW(c.inboundTexts + c.outboundTexts, serviceKW).joined(separator: ";")
        let bHits = foundKW(c.inboundTexts + c.outboundTexts, bookingKW).joined(separator: ";")
        let adultHits = foundKW(c.inboundTexts + c.outboundTexts, adultKW).joined(separator: ";")
        let optHits = foundKW(c.inboundTexts, optOutKW).joined(separator: ";")
        let prefilterPass = hasServiceAndBookingEvidence(c.inboundTexts + c.outboundTexts)

        var dropStage = ""
        var dropReason = ""
        var fix = ""

        if inV4 {
            dropStage = "none"
            dropReason = "present_in_v4"
            fix = "no_fix_needed"
        } else if !prefilterPass {
            dropStage = "prefilter"
            if sHits.isEmpty { dropReason = "no_service_keyword_hit_in_sampled_texts" }
            else if bHits.isEmpty { dropReason = "no_booking_keyword_hit_in_sampled_texts" }
            else { dropReason = "service_and_booking_present_but_prefilter_logic_failed" }
            if c.total > MAX_MSGS { fix = "increase_MAX_MSGS_or_check_all_messages_for_keywords" }
            else { fix = "add_missing_keywords_or_fix_prefilter_logic" }
        } else {
            let (bucket, reason) = deterministicTriage(c)
            dropStage = "triage"
            dropReason = "bucket=\(bucket) reason=\(reason)"
            if bucket == "HOLD_BOUNDARY" { fix = "check_adult_keyword_false_positive" }
            else if bucket == "REJECTED" { fix = "check_reason_code_accuracy" }
            else if bucket == "HOLD_INCOMPLETE" { fix = "check_if_booking_cue_exists_in_full_thread" }
            else { fix = "investigate" }
        }

        lines.append("\(l4),\(sha256(c.handle)),\(inDis),\(inV4),\(expectedBucket),\(actualBucket),\(ibPreview),\(obPreview),\(sHits),\(bHits),\(adultHits),\(optHits),\(prefilterPass),\(dropStage),\(dropReason),\(fix)")
    }

    try? lines.joined(separator: "\n").write(toFile: OUT + "/recall_regression_audit.csv", atomically: true, encoding: .utf8)
    print("  recall_regression_audit.csv written (\(disLast4.count) disassembly rows checked)")
}

// MARK: - QA
func writeQA(_ res: [(Convo, CL)]) {
    var out = ""
    let bar60 = String(repeating: "=", count: 60)
    let bar40 = String(repeating: "-", count: 40)

    out += "\(bar60)\nQA METHOD 1: SIDE-BY-SIDE SAMPLE REVIEW\n\(bar60)\n\n"
    for (c, cl) in res.sorted(by: { $0.0.total > $1.0.total }) {
        out += "--- ****\(last4(c.handle)) | \(cl.bucket ?? "?") | \(cl.priority_tier ?? "?") | score=\(Int(cl.priority_score ?? 0)) ---\n"
        for (idx, msg) in c.inboundTexts.prefix(3).enumerated() {
            out += "  [\(idx+1)] \(String(msg.prefix(120)).replacingOccurrences(of: "\n", with: " "))\n"
        }
        out += "  >> Intent: \(cl.intent_summary ?? "(none)")\n"
        out += "  >> Reply angle: \(cl.reply_angle ?? "(none)")\n"
        out += "  >> Risk: \(cl.risk_reason ?? "(none)")\n"
        out += "  >> Reason: \(cl.reason_code ?? "?") | Next: \(cl.next_action ?? "?")\n\n"
    }

    out += "\(bar60)\nQA METHOD 2: BUCKET + PRIORITY TIER AUDIT\n\(bar60)\n\n"
    for bucket in ["PRIORITY_REVIEW_CONTACT", "HOLD_BOUNDARY", "HOLD_INCOMPLETE", "REJECTED"] {
        let pool = res.filter { $0.1.bucket == bucket }
        let p0 = pool.filter { ($0.1.priority_tier ?? "") == "P0_urgent" }
        let p1 = pool.filter { ($0.1.priority_tier ?? "") == "P1_high" }
        let p2 = pool.filter { ($0.1.priority_tier ?? "") == "P2_review" }
        let p3 = pool.filter { ($0.1.priority_tier ?? "") == "P3_weak_or_old" }
        out += "\(bucket) (\(pool.count) total)\n\(bar40)\n"
        for (label, tierPool) in [("P0_urgent", p0), ("P1_high", p1), ("P2_review", p2), ("P3_weak_or_old", p3)] {
            out += "  \(label): \(tierPool.count)\n"
            for (c, cl) in tierPool {
                out += "    ****\(last4(c.handle)) | score=\(Int(cl.priority_score ?? 0)) | \(String((cl.intent_summary ?? cl.evidence ?? "").prefix(80)))\n"
            }
        }
        out += "\n"
    }

    out += "\(bar60)\nQA METHOD 3: RANDOM SPOT-CHECK (5 per bucket)\n\(bar60)\n\n"
    for bucket in ["PRIORITY_REVIEW_CONTACT", "HOLD_BOUNDARY", "HOLD_INCOMPLETE", "REJECTED"] {
        let pool = res.filter { $0.1.bucket == bucket }
        let sample = Array(pool.shuffled().prefix(5))
        out += "BUCKET: \(bucket) (\(pool.count) total, showing \(sample.count))\n\(bar40)\n"
        for (c, cl) in sample {
            out += "  ****\(last4(c.handle)) | score=\(Int(cl.priority_score ?? 0)) | tier=\(cl.priority_tier ?? "?")\n"
            out += "  Inbound (last 5):\n"
            for msg in c.inboundTexts.suffix(5) { out += "    > \(String(msg.prefix(150)).replacingOccurrences(of: "\n", with: " "))\n" }
            out += "  Intent: \(cl.intent_summary ?? "(none)")\n"
            out += "  Reply angle: \(cl.reply_angle ?? "(none)")\n"
            out += "  Risk: \(cl.risk_reason ?? "(none)")\n"
            out += "  Reason: \(cl.reason_code ?? "?") | Next: \(cl.next_action ?? "?")\n\n"
        }
    }
    try? out.write(toFile: OUT + "/qa_review.txt", atomically: true, encoding: .utf8)
}

// MARK: - Main
let bar = String(repeating: "=", count: 60)
print("""
\(bar)
  CONVERSATIONAL DEMAND ACCOUNTING v3 — Swift + chat.db + Ollama
\(bar)
  DB: \(DB)
  Model: \(MODEL)
  Burst: det=\(DET_BURST)/ollama=\(OLLAMA_BURST) / \(OLLAMA_BURST_PAUSE)s pause
  Deterministic triage: hard gate (decider)
  Ollama: summarizer only (temp=0.0, one retry)
  Buckets: PRIORITY_REVIEW_CONTACT | HOLD_BOUNDARY | HOLD_INCOMPLETE | REJECTED | REJECTED_SERVICE_REFERENCE
""")

guard FileManager.default.fileExists(atPath: DB) else { print("ERR: chat.db not found"); exit(1) }

exportAllMessages()

let cs = fetch()
print("  Found \(cs.count) handles\n")

let toClassify: [Convo]
if PREFILTER {
    var passed = cs.filter { hasServiceAndBookingEvidence($0.inboundTexts + $0.outboundTexts) }
    let sampledPass = passed.count
    var ftDb: OpaquePointer?
    if sqlite3_open(DB, &ftDb) == SQLITE_OK {
        let failed = cs.filter { !hasServiceAndBookingEvidence($0.inboundTexts + $0.outboundTexts) }
        var ftRecovered = 0
        for c in failed {
            if hasServiceAndBookingEvidenceFullThread(c.handle, ftDb) {
                passed.append(c)
                ftRecovered += 1
            }
        }
        sqlite3_close(ftDb)
        if ftRecovered > 0 {
            print("  Full-thread scan recovered \(ftRecovered) handles missed by sampled prefilter")
        }
    }
    toClassify = passed
} else {
    toClassify = cs
}
let skipped = cs.count - toClassify.count
print("  Prefilter: \(toClassify.count) passed, \(skipped) skipped\n")

// Phase 1: Deterministic triage (source of truth — runs without Ollama)
print("  Phase 1: Deterministic triage...")
var triaged: [(Convo, String, String)] = []
for c in toClassify {
    let (bucket, reason) = deterministicTriage(c)
    triaged.append((c, bucket, reason))
}
let detPC = triaged.filter { $0.1 == "PRIORITY_REVIEW_CONTACT" }.count
let detHB = triaged.filter { $0.1 == "HOLD_BOUNDARY" }.count
let detHI = triaged.filter { $0.1 == "HOLD_INCOMPLETE" }.count
let detRej = triaged.filter { $0.1 == "REJECTED" || $0.1 == "REJECTED_SERVICE_REFERENCE" }.count
let detRef = triaged.filter { $0.1 == "REJECTED_SERVICE_REFERENCE" }.count
print("    PRIORITY_REVIEW=\(detPC) HOLD_BOUNDARY=\(detHB) HOLD_INCOMPLETE=\(detHI) REJECTED=\(detRej) SERVICE_REF=\(detRef)\n")

// Phase 2: Ollama enrichment (calmer micro-bursts, optional)
print("  Phase 2: Ollama enrichment (optional)...")
var res: [(Convo, CL)] = []
for i in stride(from: 0, to: triaged.count, by: OLLAMA_BURST) {
    let end = min(i + OLLAMA_BURST, triaged.count)
    for j in i..<end {
        let (c, detBucket, detReason) = triaged[j]
        print("  [\(j+1)/\(triaged.count)] \(last4(c.handle)) (\(c.total)m) det=\(detBucket)...", terminator: " ")
        var cl = enrich(c, detBucket, detReason)
        if cl == nil {
            cl = CL()
            cl!.bucket = detBucket
            cl!.confidence = detBucket == "REJECTED" ? 0.9 : 0.0
            cl!.reason_code = detReason
            cl!.enrichment_status = "ENRICHMENT_FAILED"
            cl!.service_keywords = foundKW(c.inboundTexts + c.outboundTexts, serviceKW).joined(separator: ",")
            cl!.booking_intent = textContains(c.inboundTexts + c.outboundTexts, bookingKW)
            cl!.price_discussed = textContains(c.inboundTexts + c.outboundTexts, priceKW)
            cl!.location_discussed = textContains(c.inboundTexts + c.outboundTexts, locationKW)
            cl!.suggested_stage = detBucket == "PRIORITY_REVIEW_CONTACT" ? "booked" : "curious"
            cl!.notes = "ollama_decode_fail_or_refusal"
            print("ENRICHMENT_FAILED")
        } else {
            cl!.bucket = detBucket
            cl!.reason_code = detReason
            cl!.enrichment_status = "enriched"
            print("enriched")
        }
        let (score, tier, action) = priorityScore(c, cl!)
        cl!.priority_score = score
        cl!.priority_tier = tier
        cl!.next_action = action
        cl!.response_gap = (detBucket == "PRIORITY_REVIEW_CONTACT" && c.outbound == 0)
        cl!.review_required = (detBucket == "PRIORITY_REVIEW_CONTACT")
        cl!.review_status = detBucket == "PRIORITY_REVIEW_CONTACT" ? "pending" : "not_required"
        res.append((c, cl!))
        Thread.sleep(forTimeInterval: OLLAMA_PER_CONVO_DELAY)
    }
    if end < triaged.count {
        print("  ...burst pause \(OLLAMA_BURST_PAUSE)s...")
        Thread.sleep(forTimeInterval: OLLAMA_BURST_PAUSE)
    }
}

// Write all outputs
writeTriage(res)
writePriorityContact(res)
writeResponseGap(res)
writeReviewLeads(res)
writeRejected(res)
writeReviewDecisionsTemplate()
writeOutcomeEventsTemplate()
writeReceipts(res)
writeSummary(res, cs.count)
writeRecallRegressionAudit(res, cs)
writeQA(res)

// Print summary
let pc = res.filter { $0.1.bucket == "PRIORITY_REVIEW_CONTACT" }
let hb = res.filter { $0.1.bucket == "HOLD_BOUNDARY" }
let hi = res.filter { $0.1.bucket == "HOLD_INCOMPLETE" }
let rej = res.filter { $0.1.bucket == "REJECTED" || $0.1.bucket == "REJECTED_SERVICE_REFERENCE" }
let refOnly = res.filter { $0.1.bucket == "REJECTED_SERVICE_REFERENCE" }
let gap = pc.filter { $0.0.outbound == 0 }
print("\n  RESULTS:")
print("    PRIORITY_REVIEW_CONTACT:  \(pc.count)")
print("    HOLD_BOUNDARY:     \(hb.count)")
print("    HOLD_INCOMPLETE:   \(hi.count)")
print("    REJECTED:          \(rej.count)  (incl. \(refOnly.count) service-reference)")
print("\n  KPI:")
print("    Threads seen (corpus):     \(cs.count)")
print("    Threads analyzed (prefilter): \(res.count)  (pass rate: \(String(format: "%.1f%%", Double(res.count)/Double(cs.count)*100)))")
print("    Priority Review Contacts:  \(pc.count)  (\(String(format: "%.1f%%", Double(pc.count)/Double(cs.count)*100)) of seen, \(String(format: "%.1f%%", Double(pc.count)/Double(res.count)*100)) of analyzed)")
print("    Response Gap Queue:        \(gap.count) threads with zero outbound  (\(String(format: "%.1f%%", pc.count > 0 ? Double(gap.count)/Double(pc.count)*100 : 0)) of priority)")
print("    Fresh Demand (0-7d):       \(pc.filter { daysSince($0.0.lastDate) <= 7 }.count)")
if !pc.isEmpty {
    print("\n  PRIORITY REVIEW CONTACT (by priority):")
    for (c, cl) in pc.sorted(by: { ($0.1.priority_score ?? 0) > ($1.1.priority_score ?? 0) }) {
        let gapFlag = c.outbound == 0 ? " [GAP]" : ""
        print("    \(last4(c.handle)) | score=\(Int(cl.priority_score ?? 0)) | \(cl.priority_tier ?? "?") | \(c.total) msgs\(gapFlag) | \(cl.next_action ?? "?")")
    }
}
if !gap.isEmpty {
    print("\n  RESPONSE GAP QUEUE (\(gap.count) untouched threads):")
    for (c, cl) in gap.sorted(by: { ($0.1.priority_score ?? 0) > ($1.1.priority_score ?? 0) }) {
        print("    \(last4(c.handle)) | score=\(Int(cl.priority_score ?? 0)) | \(cl.priority_tier ?? "?") | \(c.inbound) inbound | \(Int(daysSince(c.lastDate)))d ago")
    }
}
print("\n  Outputs:")
print("    \(OUT)/all_messages.csv")
print("    \(OUT)/all_thread_triage.csv          (all rows + priority + enrichment)")
print("    \(OUT)/qualified_review_clients.csv   (PRIORITY_REVIEW_CONTACT — review ledger)")
print("    \(OUT)/response_gap_queue.csv         (untouched demand — money tab)")
print("    \(OUT)/manual_review_leads.csv        (HOLD_BOUNDARY + HOLD_INCOMPLETE)")
print("    \(OUT)/rejected_threads.csv           (REJECTED only)")
print("    \(OUT)/review_decisions.csv           (empty template for operator)")
print("    \(OUT)/outcome_events.csv             (empty template for operator)")
print("    \(OUT)/classification_receipts.jsonl")
print("    \(OUT)/demand_summary.json            (KPIs + bucket counts)")
print("    \(OUT)/recall_regression_audit.csv    (disassembly vs v4 missing-row diagnosis)")
print("    \(OUT)/qa_review.txt")
print("\n  Done.")
