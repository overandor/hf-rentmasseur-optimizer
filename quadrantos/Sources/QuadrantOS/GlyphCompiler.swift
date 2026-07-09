//
//  GlyphCompiler.swift
//  CursorAgent OS
//
//  .glyph language compiler — glyph-based programming language.
//  - Lexer: tokenizes glyph source code
//  - Parser: builds AST from glyph tokens
//  - Compiler: compiles AST to bytecode
//  - VM: executes glyph bytecode
//  - LLM integration: the compiler uses the LLM engine for semantic analysis
//  - Glyph operators, state transitions, quantum panels
//  - Receipt generation for every compiled unit
//

import Foundation
import Combine

// MARK: - Glyph Token

public struct GCToken: Identifiable {
    public let id: Int
    public let type: GCTokenType
    public let value: String
    public let position: Int
    public let line: Int
    public let column: Int

    public enum GCTokenType: String, Equatable {
        case glyph         = "glyph"
        case identifier    = "identifier"
        case number        = "number"
        case string        = "string"
        case op            = "operator"
        case lparen        = "lparen"
        case rparen        = "rparen"
        case lbracket      = "lbracket"
        case rbracket      = "rbracket"
        case lbrace        = "lbrace"
        case rbrace        = "rbrace"
        case arrow         = "arrow"
        case colon         = "colon"
        case semicolon     = "semicolon"
        case comma         = "comma"
        case dot           = "dot"
        case pipe          = "pipe"
        case bang          = "bang"
        case question      = "question"
        case at            = "at"
        case hash          = "hash"
        case dollar        = "dollar"
        case ampersand     = "ampersand"
        case caret         = "caret"
        case tilde         = "tilde"
        case percent       = "percent"
        case eof           = "eof"

        public var glyph: String {
            switch self {
            case .glyph:      return "⟡"
            case .identifier: return "◇"
            case .number:     return "#"
            case .string:     return "S"
            case .op:         return "⌁"
            case .lparen:     return "("
            case .rparen:     return ")"
            case .lbracket:   return "["
            case .rbracket:   return "]"
            case .lbrace:     return "{"
            case .rbrace:     return "}"
            case .arrow:      return "→"
            case .colon:      return ":"
            case .semicolon:  return ";"
            case .comma:      return ","
            case .dot:        return "."
            case .pipe:       return "|"
            case .bang:       return "!"
            case .question:   return "?"
            case .at:         return "@"
            case .hash:       return "#"
            case .dollar:     return "$"
            case .ampersand:  return "&"
            case .caret:      return "^"
            case .tilde:      return "~"
            case .percent:    return "%"
            case .eof:        return "⏹"
            }
        }
    }

    public init(id: Int, type: GCTokenType, value: String,
                position: Int, line: Int, column: Int) {
        self.id = id
        self.type = type
        self.value = value
        self.position = position
        self.line = line
        self.column = column
    }
}

// MARK: - Glyph Lexer

public final class GCLexer {
    public var source: String
    public var position: Int = 0
    public var line: Int = 1
    public var column: Int = 1
    public var tokens: [GCToken] = []

    public let glyphSet: Set<String> = [
        "◉", "◇", "▲", "▼", "◆", "⟁", "◌", "◍", "⧉", "⌁", "⟡", "⧖",
        "▶", "⏹", "⇄", "★", "⚡", "🛡", "🧾", "🧠", "⚙", "👤", "🤖", "📁",
        "👁", "✕", "✓", "✗", "☼", "☾", "∞", "∇", "∮", "⊕", "⊗", "⊘",
        "⊙", "⊚", "⊛", "⊜", "⊝", "⌬", "⌘", "⌥", "⌃", "⇧", "⇥", "⇤",
        "⇣", "⇡", "⇠", "⇢", "⇦", "⇨", "⇧", "⇩", "⇪", "⇫", "⇬", "⇭",
        "⇮", "⇯", "⇰", "⇱", "⇲", "⇳", "⇴", "⇵", "⇶", "⇷", "⇸", "⇹",
        "⇺", "⇻", "⇼", "⇽", "⇾", "⇿"
    ]

    public init(source: String) {
        self.source = source
    }

    public func tokenize() -> [GCToken] {
        tokens = []
        position = 0
        line = 1
        column = 1

        while position < source.count {
            let ch = currentChar()

            if ch == " " || ch == "\t" {
                advance()
                continue
            }

            if ch == "\n" {
                advance()
                line += 1
                column = 1
                continue
            }

            if ch == "/" && peekChar() == "/" {
                skipComment()
                continue
            }

            if ch == "\"" {
                tokenizeString()
                continue
            }

            if let c = ch.first, c.isNumber {
                tokenizeNumber()
                continue
            }

            if let c = ch.first, c.isLetter || ch == "_" {
                tokenizeIdentifier()
                continue
            }

            if isGlyphChar(ch) {
                tokenizeGlyph()
                continue
            }

            tokenizeSymbol(ch)
        }

        tokens.append(GCToken(id: tokens.count, type: .eof, value: "",
                                  position: position, line: line, column: column))
        return tokens
    }

    private func currentChar() -> String {
        guard position < source.count else { return "" }
        let idx = source.index(source.startIndex, offsetBy: position)
        return String(source[idx])
    }

    private func peekChar() -> String {
        guard position + 1 < source.count else { return "" }
        let idx = source.index(source.startIndex, offsetBy: position + 1)
        return String(source[idx])
    }

    private func advance() {
        position += 1
        column += 1
    }

    private func isGlyphChar(_ ch: String) -> Bool {
        return glyphSet.contains(ch)
    }

    private func skipComment() {
        while position < source.count && currentChar() != "\n" {
            advance()
        }
    }

    private func tokenizeString() {
        let startPos = position
        let startLine = line
        let startCol = column
        advance()

        var value = ""
        while position < source.count && currentChar() != "\"" {
            if currentChar() == "\\" {
                advance()
                let escaped = currentChar()
                switch escaped {
                case "n":  value += "\n"
                case "t":  value += "\t"
                case "r":  value += "\r"
                case "\\": value += "\\"
                case "\"": value += "\""
                default:   value += escaped
                }
                advance()
            } else {
                value += currentChar()
                advance()
            }
        }

        if currentChar() == "\"" { advance() }

        tokens.append(GCToken(id: tokens.count, type: .string, value: value,
                                  position: startPos, line: startLine, column: startCol))
    }

    private func tokenizeNumber() {
        let startPos = position
        let startLine = line
        let startCol = column
        var value = ""

        while position < source.count && ((currentChar().first?.isNumber ?? false) || currentChar() == ".") {
            value += currentChar()
            advance()
        }

        tokens.append(GCToken(id: tokens.count, type: .number, value: value,
                                  position: startPos, line: startLine, column: startCol))
    }

    private func tokenizeIdentifier() {
        let startPos = position
        let startLine = line
        let startCol = column
        var value = ""

        while position < source.count && ((currentChar().first?.isLetter ?? false) || (currentChar().first?.isNumber ?? false) || currentChar() == "_") {
            value += currentChar()
            advance()
        }

        tokens.append(GCToken(id: tokens.count, type: .identifier, value: value,
                                  position: startPos, line: startLine, column: startCol))
    }

    private func tokenizeGlyph() {
        let startPos = position
        let startLine = line
        let startCol = column
        var value = ""

        while position < source.count && isGlyphChar(currentChar()) {
            value += currentChar()
            advance()
        }

        tokens.append(GCToken(id: tokens.count, type: .glyph, value: value,
                                  position: startPos, line: startLine, column: startCol))
    }

    private func tokenizeSymbol(_ ch: String) {
        let startPos = position
        let startLine = line
        let startCol = column

        let type: GCToken.GCTokenType
        var value = ch

        switch ch {
        case "(": type = .lparen
        case ")": type = .rparen
        case "[": type = .lbracket
        case "]": type = .rbracket
        case "{": type = .lbrace
        case "}": type = .rbrace
        case ":": type = .colon
        case ";": type = .semicolon
        case ",": type = .comma
        case ".": type = .dot
        case "|": type = .pipe
        case "!": type = .bang
        case "?": type = .question
        case "@": type = .at
        case "#": type = .hash
        case "$": type = .dollar
        case "&": type = .ampersand
        case "^": type = .caret
        case "~": type = .tilde
        case "%": type = .percent
        case "-":
            if peekChar() == ">" {
                advance()
                value = "->"
                type = .arrow
            } else {
                type = .op
            }
        case "+", "*", "/", "<", ">", "=": type = .op
        default: type = .op
        }

        advance()
        tokens.append(GCToken(id: tokens.count, type: type, value: value,
                                  position: startPos, line: startLine, column: startCol))
    }
}

// MARK: - Glyph AST

public indirect enum GlyphASTNode {
    case program([GlyphASTNode])
    case glyphDecl(String, [GlyphASTNode])
    case stateDecl(String, [GlyphASTNode])
    case transition(String, String, [GlyphASTNode])
    case panelDecl(String, [GlyphASTNode])
    case assignment(String, GlyphASTNode)
    case binaryOp(String, GlyphASTNode, GlyphASTNode)
    case unaryOp(String, GlyphASTNode)
    case literal(GlyphValue)
    case identifier(String)
    case call(String, [GlyphASTNode])
    case pipeline([GlyphASTNode])
    case conditional(GlyphASTNode, [GlyphASTNode], [GlyphASTNode]?)
    case loop([GlyphASTNode], [GlyphASTNode])
    case match(GlyphASTNode, [(GlyphASTNode, [GlyphASTNode])])
    case receipt([GlyphASTNode])
    case agentRef(String)
    case cursorRef(String)
    case workspaceRef(String)
    case llmCall(String, [GlyphASTNode])
    case glyphExpr(String, [GlyphASTNode])
    case quantumState(String, [GlyphASTNode])
    case trendSurface([GlyphASTNode])
    case heatMap([GlyphASTNode])
    case ramSurface([GlyphASTNode])
    case agentCommand(String, [GlyphASTNode])
    case exportNode(String, [GlyphASTNode])
    case importNode(String)
    case comment(String)
    case empty
}

public enum GlyphValue: Codable {
    case string(String)
    case number(Double)
    case boolean(Bool)
    case glyph(String)
    case array([GlyphValue])
    case dictionary([String: GlyphValue])
    case null

    public var description: String {
        switch self {
        case .string(let s):   return "\"\(s)\""
        case .number(let n):   return String(n)
        case .boolean(let b):  return String(b)
        case .glyph(let g):    return g
        case .array(let a):    return "[\(a.map { $0.description }.joined(separator: ", "))]"
        case .dictionary(let d): return "{\(d.map { "\($0.key): \($0.value.description)" }.joined(separator: ", "))}"
        case .null:            return "null"
        }
    }
}

// MARK: - Glyph Parser

public final class GlyphParser {
    public var tokens: [GCToken]
    public var position: Int = 0
    public var errors: [GlyphCompileError] = []

    public init(tokens: [GCToken]) {
        self.tokens = tokens
    }

    public func parse() -> GlyphASTNode {
        var nodes: [GlyphASTNode] = []

        while !isAtEnd() {
            if let node = parseStatement() {
                nodes.append(node)
            } else {
                advance()
            }
        }

        return .program(nodes)
    }

    // MARK: - Helpers

    private func current() -> GCToken {
        return tokens[position]
    }

    private func peek() -> GCToken {
        guard position + 1 < tokens.count else { return tokens.last! }
        return tokens[position + 1]
    }

    private func advance() -> GCToken {
        let token = tokens[position]
        if position < tokens.count - 1 { position += 1 }
        return token
    }

    private func isAtEnd() -> Bool {
        return current().type == .eof
    }

    private func match(_ type: GCToken.GCTokenType) -> Bool {
        if current().type == type {
            advance()
            return true
        }
        return false
    }

    private func expect(_ type: GCToken.GCTokenType, _ message: String) -> GCToken {
        if current().type == type {
            return advance()
        }
        errors.append(GlyphCompileError(line: current().line, column: current().column, message: message))
        return current()
    }

    // MARK: - Statements

    private func parseStatement() -> GlyphASTNode? {
        let token = current()

        switch token.type {
        case .glyph:
            return parseGlyphStatement()
        case .identifier:
            switch token.value {
            case "state":     return parseStateDecl()
            case "panel":     return parsePanelDecl()
            case "transition": return parseTransition()
            case "if":        return parseConditional()
            case "loop":      return parseLoop()
            case "match":     return parseMatch()
            case "receipt":   return parseReceipt()
            case "agent":     return parseAgentRef()
            case "cursor":    return parseCursorRef()
            case "workspace": return parseWorkspaceRef()
            case "llm":       return parseLLMCall()
            case "export":    return parseExport()
            case "import":    return parseImport()
            case "trend":     return parseTrendSurface()
            case "heat":      return parseHeatMap()
            case "ram":       return parseRamSurface()
            case "quantum":   return parseQuantumState()
            default:
                if peek().type == .op && (peek().value == "=" || peek().value == "->") {
                    return parseAssignment()
                }
                return parseExpression()
            }
        case .lbrace:
            return parseBlock()
        case .pipe:
            return parsePipeline()
        default:
            return parseExpression()
        }
    }

    private func parseGlyphStatement() -> GlyphASTNode {
        let glyphToken = advance()
        var children: [GlyphASTNode] = []

        if match(.colon) {
            while !isAtEnd() && current().type != .semicolon && current().type != .eof {
                if let node = parseStatement() {
                    children.append(node)
                }
            }
            _ = match(.semicolon)
        } else if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    children.append(node)
                }
            }
            _ = match(.rbrace)
        }

        return .glyphDecl(glyphToken.value, children)
    }

    private func parseStateDecl() -> GlyphASTNode {
        advance()
        let name = expect(.identifier, "Expected state name").value
        var children: [GlyphASTNode] = []

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    children.append(node)
                }
            }
            _ = match(.rbrace)
        }

        return .stateDecl(name, children)
    }

    private func parsePanelDecl() -> GlyphASTNode {
        advance()
        let name = expect(.identifier, "Expected panel name").value
        var children: [GlyphASTNode] = []

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    children.append(node)
                }
            }
            _ = match(.rbrace)
        }

        return .panelDecl(name, children)
    }

    private func parseTransition() -> GlyphASTNode {
        advance()
        let from = expect(.identifier, "Expected source state").value
        _ = expect(.arrow, "Expected ->")
        let to = expect(.identifier, "Expected target state").value
        var children: [GlyphASTNode] = []

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    children.append(node)
                }
            }
            _ = match(.rbrace)
        }

        return .transition(from, to, children)
    }

    private func parseConditional() -> GlyphASTNode {
        advance()
        let condition = parseExpression()
        var thenBranch: [GlyphASTNode] = []
        var elseBranch: [GlyphASTNode]? = nil

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    thenBranch.append(node)
                }
            }
            _ = match(.rbrace)
        }

        if current().type == .identifier && current().value == "else" {
            advance()
            if match(.lbrace) {
                var elseNodes: [GlyphASTNode] = []
                while !isAtEnd() && current().type != .rbrace {
                    if let node = parseStatement() {
                        elseNodes.append(node)
                    }
                }
                _ = match(.rbrace)
                elseBranch = elseNodes
            }
        }

        return .conditional(condition, thenBranch, elseBranch)
    }

    private func parseLoop() -> GlyphASTNode {
        advance()
        var condition: [GlyphASTNode] = []
        var body: [GlyphASTNode] = []

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    condition.append(node)
                }
            }
            _ = match(.rbrace)
        }

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    body.append(node)
                }
            }
            _ = match(.rbrace)
        }

        return .loop(condition, body)
    }

    private func parseMatch() -> GlyphASTNode {
        advance()
        let subject = parseExpression()
        _ = expect(.lbrace, "Expected { after match subject")

        var cases: [(GlyphASTNode, [GlyphASTNode])] = []

        while !isAtEnd() && current().type != .rbrace {
            let pattern = parseExpression()
            _ = expect(.arrow, "Expected -> in match case")
            var body: [GlyphASTNode] = []
            while !isAtEnd() && current().type != .rbrace && current().type != .semicolon {
                if let node = parseStatement() {
                    body.append(node)
                }
            }
            _ = match(.semicolon)
            cases.append((pattern, body))
        }
        _ = match(.rbrace)

        return .match(subject, cases)
    }

    private func parseReceipt() -> GlyphASTNode {
        advance()
        var children: [GlyphASTNode] = []

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    children.append(node)
                }
            }
            _ = match(.rbrace)
        }

        return .receipt(children)
    }

    private func parseAgentRef() -> GlyphASTNode {
        advance()
        let name = expect(.identifier, "Expected agent name").value
        return .agentRef(name)
    }

    private func parseCursorRef() -> GlyphASTNode {
        advance()
        let name = expect(.identifier, "Expected cursor name").value
        return .cursorRef(name)
    }

    private func parseWorkspaceRef() -> GlyphASTNode {
        advance()
        let name = expect(.identifier, "Expected workspace name").value
        return .workspaceRef(name)
    }

    private func parseLLMCall() -> GlyphASTNode {
        advance()
        let prompt = expect(.string, "Expected LLM prompt string").value
        var args: [GlyphASTNode] = [.literal(.string(prompt))]

        if match(.lparen) {
            while !isAtEnd() && current().type != .rparen {
                args.append(parseExpression())
                _ = match(.comma)
            }
            _ = match(.rparen)
        }

        return .llmCall("llm", args)
    }

    private func parseExport() -> GlyphASTNode {
        advance()
        let target = expect(.identifier, "Expected export target").value
        var args: [GlyphASTNode] = []

        if match(.lparen) {
            while !isAtEnd() && current().type != .rparen {
                args.append(parseExpression())
                _ = match(.comma)
            }
            _ = match(.rparen)
        }

        return .exportNode(target, args)
    }

    private func parseImport() -> GlyphASTNode {
        advance()
        let module = expect(.string, "Expected import path").value
        return .importNode(module)
    }

    private func parseTrendSurface() -> GlyphASTNode {
        advance()
        var children: [GlyphASTNode] = []

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    children.append(node)
                }
            }
            _ = match(.rbrace)
        }

        return .trendSurface(children)
    }

    private func parseHeatMap() -> GlyphASTNode {
        advance()
        var children: [GlyphASTNode] = []

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    children.append(node)
                }
            }
            _ = match(.rbrace)
        }

        return .heatMap(children)
    }

    private func parseRamSurface() -> GlyphASTNode {
        advance()
        var children: [GlyphASTNode] = []

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    children.append(node)
                }
            }
            _ = match(.rbrace)
        }

        return .ramSurface(children)
    }

    private func parseQuantumState() -> GlyphASTNode {
        advance()
        let state = expect(.identifier, "Expected quantum state name").value
        var children: [GlyphASTNode] = []

        if match(.lbrace) {
            while !isAtEnd() && current().type != .rbrace {
                if let node = parseStatement() {
                    children.append(node)
                }
            }
            _ = match(.rbrace)
        }

        return .quantumState(state, children)
    }

    private func parseAssignment() -> GlyphASTNode {
        let name = advance().value
        _ = expect(.op, "Expected =")
        let value = parseExpression()
        return .assignment(name, value)
    }

    private func parsePipeline() -> GlyphASTNode {
        advance()
        var stages: [GlyphASTNode] = []

        while !isAtEnd() && current().type != .semicolon && current().type != .eof {
            stages.append(parseExpression())
            if current().type == .pipe { advance() }
        }
        _ = match(.semicolon)

        return .pipeline(stages)
    }

    private func parseBlock() -> GlyphASTNode {
        _ = match(.lbrace)
        var nodes: [GlyphASTNode] = []

        while !isAtEnd() && current().type != .rbrace {
            if let node = parseStatement() {
                nodes.append(node)
            }
        }
        _ = match(.rbrace)

        return .program(nodes)
    }

    // MARK: - Expressions

    private func parseExpression() -> GlyphASTNode {
        return parseBinaryOp(0)
    }

    private func parseBinaryOp(_ precedence: Int) -> GlyphASTNode {
        var left = parseUnary()

        while true {
            let op = current()
            guard op.type == .op else { break }
            let opPrec = operatorPrecedence(op.value)
            guard opPrec >= precedence else { break }

            advance()
            let right = parseBinaryOp(opPrec + 1)
            left = .binaryOp(op.value, left, right)
        }

        return left
    }

    private func operatorPrecedence(_ op: String) -> Int {
        switch op {
        case "*", "/", "%":           return 5
        case "+", "-":                return 4
        case "<", ">", "<=", ">=":    return 3
        case "==", "!=":              return 2
        case "=", "&":                return 1
        default:                      return 0
        }
    }

    private func parseUnary() -> GlyphASTNode {
        if current().type == .op && (current().value == "-" || current().value == "!") {
            let op = advance().value
            let operand = parseUnary()
            return .unaryOp(op, operand)
        }
        return parsePrimary()
    }

    private func parsePrimary() -> GlyphASTNode {
        let token = current()

        switch token.type {
        case .number:
            advance()
            return .literal(.number(Double(token.value) ?? 0))
        case .string:
            advance()
            return .literal(.string(token.value))
        case .glyph:
            advance()
            return .literal(.glyph(token.value))
        case .identifier:
            advance()
            if match(.lparen) {
                var args: [GlyphASTNode] = []
                while !isAtEnd() && current().type != .rparen {
                    args.append(parseExpression())
                    _ = match(.comma)
                }
                _ = match(.rparen)
                return .call(token.value, args)
            }
            return .identifier(token.value)
        case .lparen:
            advance()
            let expr = parseExpression()
            _ = expect(.rparen, "Expected )")
            return expr
        case .lbracket:
            advance()
            var elements: [GlyphASTNode] = []
            while !isAtEnd() && current().type != .rbracket {
                elements.append(parseExpression())
                _ = match(.comma)
            }
            _ = match(.rbracket)
            var values: [GlyphValue] = []
            for elem in elements {
                if case .literal(let val) = elem {
                    values.append(val)
                }
            }
            return .literal(.array(values))
        default:
            advance()
            return .empty
        }
    }
}

// MARK: - Compile Error

public struct GlyphCompileError: Identifiable, Codable {
    public let id: Int
    public let line: Int
    public let column: Int
    public let message: String

    public init(line: Int, column: Int, message: String) {
        self.id = line * 1000 + column
        self.line = line
        self.column = column
        self.message = message
    }

    public var summary: String {
        "✕ Error at \(line):\(column) — \(message)"
    }
}

// MARK: - Glyph Bytecode

public enum GlyphBytecode: Codable {
    case pushValue(GlyphValue)
    case pushGlyph(String)
    case pop
    case store(String)
    case load(String)
    case binaryOp(String)
    case unaryOp(String)
    case call(String, Int)
    case llmCall(Int)
    case jump(Int)
    case jumpIfFalse(Int)
    case jumpIfTrue(Int)
    case transition(String, String)
    case setState(String)
    case getState
    case emitReceipt
    case log
    case halt
    case nop

    public var description: String {
        switch self {
        case .pushValue(let v):  return "PUSH \(v.description)"
        case .pushGlyph(let g):  return "GLYPH \(g)"
        case .pop:               return "POP"
        case .store(let n):      return "STORE \(n)"
        case .load(let n):       return "LOAD \(n)"
        case .binaryOp(let op):  return "OP \(op)"
        case .unaryOp(let op):   return "UNOP \(op)"
        case .call(let n, let a): return "CALL \(n) \(a)"
        case .llmCall(let a):    return "LLM \(a)"
        case .jump(let i):       return "JMP \(i)"
        case .jumpIfFalse(let i): return "JMPF \(i)"
        case .jumpIfTrue(let i): return "JMPT \(i)"
        case .transition(let f, let t): return "TRANS \(f)→\(t)"
        case .setState(let s):   return "SETSTATE \(s)"
        case .getState:          return "GETSTATE"
        case .emitReceipt:       return "RECEIPT"
        case .log:               return "LOG"
        case .halt:              return "HALT"
        case .nop:               return "NOP"
        }
    }
}

// MARK: - Glyph Compiler

public final class GlyphCompiler: ObservableObject {
    @Published public var source: String = ""
    @Published public var tokens: [GCToken] = []
    @Published public var ast: GlyphASTNode = .empty
    @Published public var bytecode: [GlyphBytecode] = []
    @Published public var errors: [GlyphCompileError] = []
    @Published public var warnings: [String] = []
    @Published public var compileTime: Double = 0
    @Published public var isCompiled: Bool = false
    @Published public var receiptHash: String = ""

    public let llmEngine: LLMEngine?

    public init(llmEngine: LLMEngine? = nil) {
        self.llmEngine = llmEngine
    }

    public func compile(_ source: String) -> CompileResult {
        let startTime = Date().timeIntervalSince1970
        self.source = source
        errors = []
        warnings = []
        bytecode = []

        let lexer = GCLexer(source: source)
        tokens = lexer.tokenize()

        let parser = GlyphParser(tokens: tokens)
        ast = parser.parse()
        errors.append(contentsOf: parser.errors)

        if errors.isEmpty {
            generateBytecode(from: ast)

            if let llm = llmEngine {
                let semanticResult = llm.generateGreedy(
                    prompt: "Analyze this glyph program for semantic issues: \(source.prefix(200))",
                    maxTokens: 20
                )
                if !semanticResult.isEmpty {
                    warnings.append("LLM semantic check: \(semanticResult)")
                }
            }

            receiptHash = sha256(bytecode.map { $0.description }.joined())
        }

        compileTime = Date().timeIntervalSince1970 - startTime
        isCompiled = errors.isEmpty

        return CompileResult(
            success: errors.isEmpty,
            bytecode: bytecode,
            errors: errors,
            warnings: warnings,
            receiptHash: receiptHash,
            compileTime: compileTime
        )
    }

    private func generateBytecode(from node: GlyphASTNode) {
        switch node {
        case .program(let nodes):
            for child in nodes {
                generateBytecode(from: child)
            }
            bytecode.append(.halt)

        case .glyphDecl(let glyph, let children):
            bytecode.append(.pushGlyph(glyph))
            for child in children {
                generateBytecode(from: child)
            }

        case .stateDecl(let name, let children):
            bytecode.append(.setState(name))
            for child in children {
                generateBytecode(from: child)
            }

        case .transition(let from, let to, let children):
            bytecode.append(.transition(from, to))
            for child in children {
                generateBytecode(from: child)
            }

        case .panelDecl(_, let children):
            for child in children {
                generateBytecode(from: child)
            }

        case .assignment(let name, let value):
            generateBytecode(from: value)
            bytecode.append(.store(name))

        case .binaryOp(let op, let left, let right):
            generateBytecode(from: left)
            generateBytecode(from: right)
            bytecode.append(.binaryOp(op))

        case .unaryOp(let op, let operand):
            generateBytecode(from: operand)
            bytecode.append(.unaryOp(op))

        case .literal(let value):
            bytecode.append(.pushValue(value))

        case .identifier(let name):
            bytecode.append(.load(name))

        case .call(let name, let args):
            for arg in args {
                generateBytecode(from: arg)
            }
            bytecode.append(.call(name, args.count))

        case .pipeline(let stages):
            for stage in stages {
                generateBytecode(from: stage)
            }

        case .conditional(let cond, let thenBranch, let elseBranch):
            generateBytecode(from: cond)
            let jumpIfFalsePos = bytecode.count
            bytecode.append(.jumpIfFalse(0))

            for node in thenBranch {
                generateBytecode(from: node)
            }

            if let elseB = elseBranch {
                let jumpEndPos = bytecode.count
                bytecode.append(.jump(0))

                if case .jumpIfFalse(let target) = bytecode[jumpIfFalsePos] {
                    bytecode[jumpIfFalsePos] = .jumpIfFalse(bytecode.count)
                }

                for node in elseB {
                    generateBytecode(from: node)
                }

                if case .jump(let target) = bytecode[jumpEndPos] {
                    bytecode[jumpEndPos] = .jump(bytecode.count)
                }
            } else {
                if case .jumpIfFalse(let target) = bytecode[jumpIfFalsePos] {
                    bytecode[jumpIfFalsePos] = .jumpIfFalse(bytecode.count)
                }
            }

        case .loop(let condition, let body):
            let loopStart = bytecode.count
            for node in condition {
                generateBytecode(from: node)
            }
            let jumpExitPos = bytecode.count
            bytecode.append(.jumpIfFalse(0))

            for node in body {
                generateBytecode(from: node)
            }
            bytecode.append(.jump(loopStart))

            if case .jumpIfFalse(let target) = bytecode[jumpExitPos] {
                bytecode[jumpExitPos] = .jumpIfFalse(bytecode.count)
            }

        case .match(let subject, let cases):
            generateBytecode(from: subject)

            var jumpEnds: [Int] = []

            for (pattern, body) in cases {
                generateBytecode(from: pattern)
                bytecode.append(.binaryOp("=="))

                let jumpNextPos = bytecode.count
                bytecode.append(.jumpIfFalse(0))

                for node in body {
                    generateBytecode(from: node)
                }

                let jumpEndPos = bytecode.count
                bytecode.append(.jump(0))
                jumpEnds.append(jumpEndPos)

                if case .jumpIfFalse(let target) = bytecode[jumpNextPos] {
                    bytecode[jumpNextPos] = .jumpIfFalse(bytecode.count)
                }
            }

            for pos in jumpEnds {
                if case .jump(let target) = bytecode[pos] {
                    bytecode[pos] = .jump(bytecode.count)
                }
            }

        case .receipt(let children):
            for child in children {
                generateBytecode(from: child)
            }
            bytecode.append(.emitReceipt)

        case .agentRef(let name):
            bytecode.append(.load("agent.\(name)"))

        case .cursorRef(let name):
            bytecode.append(.load("cursor.\(name)"))

        case .workspaceRef(let name):
            bytecode.append(.load("workspace.\(name)"))

        case .llmCall(_, let args):
            for arg in args {
                generateBytecode(from: arg)
            }
            bytecode.append(.llmCall(args.count))

        case .glyphExpr(let glyph, let children):
            bytecode.append(.pushGlyph(glyph))
            for child in children {
                generateBytecode(from: child)
            }

        case .quantumState(let state, let children):
            bytecode.append(.setState(state))
            for child in children {
                generateBytecode(from: child)
            }

        case .trendSurface(let children):
            for child in children {
                generateBytecode(from: child)
            }

        case .heatMap(let children):
            for child in children {
                generateBytecode(from: child)
            }

        case .ramSurface(let children):
            for child in children {
                generateBytecode(from: child)
            }

        case .agentCommand(let cmd, let args):
            for arg in args {
                generateBytecode(from: arg)
            }
            bytecode.append(.call("agent.\(cmd)", args.count))

        case .exportNode(let target, let args):
            for arg in args {
                generateBytecode(from: arg)
            }
            bytecode.append(.call("export.\(target)", args.count))

        case .importNode(let module):
            bytecode.append(.call("import.\(module)", 0))

        case .comment:
            break

        case .empty:
            bytecode.append(.nop)
        }
    }

    public var summary: String {
        "Glyph: \(tokens.count) tokens, \(bytecode.count) instructions, \(errors.count) errors | \(isCompiled ? "◉ compiled" : "✕ failed") | \(String(format: "%.2fms", compileTime * 1000))"
    }

    public func disassemble() -> String {
        var output = "# Glyph Bytecode Disassembly\n\n"
        for (i, instruction) in bytecode.enumerated() {
            output += String(format: "%04d  %@\n", i, instruction.description)
        }
        return output
    }
}

// MARK: - Compile Result

public struct CompileResult: Codable {
    public let success: Bool
    public let bytecode: [GlyphBytecode]
    public let errors: [GlyphCompileError]
    public let warnings: [String]
    public let receiptHash: String
    public let compileTime: Double

    public var summary: String {
        success ? "✓ Compiled: \(bytecode.count) instructions, \(String(format: "%.2fms", compileTime * 1000))" : "✕ Failed: \(errors.count) errors"
    }
}

// MARK: - Glyph VM

public final class GlyphVM: ObservableObject {
    @Published public var bytecode: [GlyphBytecode] = []
    @Published public var stack: [GlyphValue] = []
    @Published public var variables: [String: GlyphValue] = [:]
    @Published public var state: String = "idle"
    @Published public var pc: Int = 0
    @Published public var isRunning: Bool = false
    @Published public var outputLog: [String] = []
    @Published public var receipts: [String] = []
    @Published public var transitions: [(String, String, Double)] = []
    @Published public var glyphStack: [String] = []

    public let llmEngine: LLMEngine?
    public var maxSteps: Int = 10000

    public init(llmEngine: LLMEngine? = nil) {
        self.llmEngine = llmEngine
    }

    public func load(_ bytecode: [GlyphBytecode]) {
        self.bytecode = bytecode
        reset()
    }

    public func reset() {
        stack = []
        variables = [:]
        state = "idle"
        pc = 0
        isRunning = false
        outputLog = []
        receipts = []
        transitions = []
        glyphStack = []
    }

    public func run() -> VMResult {
        reset()
        isRunning = true
        var steps = 0

        while isRunning && pc < bytecode.count && steps < maxSteps {
            let instruction = bytecode[pc]
            execute(instruction)
            steps += 1

            if case .halt = instruction {
                isRunning = false
            }
        }

        isRunning = false

        return VMResult(
            success: pc >= bytecode.count || steps >= maxSteps,
            output: outputLog.joined(separator: "\n"),
            finalState: state,
            receipts: receipts,
            transitions: transitions,
            steps: steps
        )
    }

    public func step() -> Bool {
        guard pc < bytecode.count else { return false }

        let instruction = bytecode[pc]
        execute(instruction)

        if case .halt = instruction { return false }
        return pc < bytecode.count
    }

    private func execute(_ instruction: GlyphBytecode) {
        switch instruction {
        case .pushValue(let value):
            stack.append(value)
            pc += 1

        case .pushGlyph(let glyph):
            glyphStack.append(glyph)
            outputLog.append("⟡ \(glyph)")
            pc += 1

        case .pop:
            if !stack.isEmpty { stack.removeLast() }
            pc += 1

        case .store(let name):
            if let value = stack.popLast() {
                variables[name] = value
            }
            pc += 1

        case .load(let name):
            stack.append(variables[name] ?? .null)
            pc += 1

        case .binaryOp(let op):
            let right = stack.popLast() ?? .null
            let left = stack.popLast() ?? .null
            stack.append(applyBinaryOp(op, left, right))
            pc += 1

        case .unaryOp(let op):
            let operand = stack.popLast() ?? .null
            stack.append(applyUnaryOp(op, operand))
            pc += 1

        case .call(let name, let argCount):
            var args: [GlyphValue] = []
            for _ in 0..<argCount {
                args.insert(stack.popLast() ?? .null, at: 0)
            }
            let result = callFunction(name, args)
            stack.append(result)
            pc += 1

        case .llmCall(let argCount):
            var args: [GlyphValue] = []
            for _ in 0..<argCount {
                args.insert(stack.popLast() ?? .null, at: 0)
            }
            let prompt = args.first?.description ?? ""
            let result: GlyphValue

            if let llm = llmEngine {
                let generated = llm.generateGreedy(prompt: prompt, maxTokens: 50)
                result = .string(generated)
                outputLog.append("🤖 LLM: \(generated)")
            } else {
                result = .string("[LLM not available]")
            }

            stack.append(result)
            pc += 1

        case .jump(let target):
            pc = target

        case .jumpIfFalse(let target):
            let cond = stack.popLast() ?? .null
            if isTruthy(cond) {
                pc += 1
            } else {
                pc = target
            }

        case .jumpIfTrue(let target):
            let cond = stack.popLast() ?? .null
            if isTruthy(cond) {
                pc = target
            } else {
                pc += 1
            }

        case .transition(let from, let to):
            if state == from {
                let timestamp = Date().timeIntervalSince1970
                transitions.append((from, to, timestamp))
                state = to
                outputLog.append("→ \(from) → \(to)")
            }
            pc += 1

        case .setState(let newState):
            state = newState
            outputLog.append("◉ state: \(newState)")
            pc += 1

        case .getState:
            stack.append(.string(state))
            pc += 1

        case .emitReceipt:
            let receiptId = sha256("\(receipts.count)-\(Date().timeIntervalSince1970)-\(state)")
            receipts.append(receiptId)
            outputLog.append("🧾 receipt: \(receiptId.prefix(16))")
            pc += 1

        case .log:
            let value = stack.popLast() ?? .null
            outputLog.append(value.description)
            pc += 1

        case .halt:
            isRunning = false
            outputLog.append("⏹ halt")

        case .nop:
            pc += 1
        }
    }

    private func applyBinaryOp(_ op: String, _ left: GlyphValue, _ right: GlyphValue) -> GlyphValue {
        switch (left, right) {
        case (.number(let l), .number(let r)):
            switch op {
            case "+": return .number(l + r)
            case "-": return .number(l - r)
            case "*": return .number(l * r)
            case "/": return .number(r != 0 ? l / r : 0)
            case "%": return .number(r != 0 ? l.truncatingRemainder(dividingBy: r) : 0)
            case "<": return .boolean(l < r)
            case ">": return .boolean(l > r)
            case "==": return .boolean(l == r)
            case "!=": return .boolean(l != r)
            default: return .null
            }
        case (.string(let l), .string(let r)):
            switch op {
            case "+": return .string(l + r)
            case "==": return .boolean(l == r)
            case "!=": return .boolean(l != r)
            default: return .null
            }
        case (.boolean(let l), .boolean(let r)):
            switch op {
            case "==": return .boolean(l == r)
            case "!=": return .boolean(l != r)
            case "&": return .boolean(l && r)
            default: return .null
            }
        default:
            return .null
        }
    }

    private func applyUnaryOp(_ op: String, _ operand: GlyphValue) -> GlyphValue {
        switch (op, operand) {
        case ("-", .number(let n)): return .number(-n)
        case ("!", .boolean(let b)): return .boolean(!b)
        default: return .null
        }
    }

    private func callFunction(_ name: String, _ args: [GlyphValue]) -> GlyphValue {
        switch name {
        case "print":
            outputLog.append(args.map { $0.description }.joined(separator: " "))
            return .null
        case "len":
            if case .array(let a) = args.first { return .number(Double(a.count)) }
            if case .string(let s) = args.first { return .number(Double(s.count)) }
            return .number(0)
        case "sum":
            if case .array(let a) = args.first {
                return .number(a.compactMap { if case .number(let n) = $0 { return n } else { return nil } }.reduce(0, +))
            }
            return .number(0)
        case "concat":
            return .string(args.map { $0.description }.joined())
        case "upper":
            if case .string(let s) = args.first { return .string(s.uppercased()) }
            return .null
        case "lower":
            if case .string(let s) = args.first { return .string(s.lowercased()) }
            return .null
        case "glyph":
            if let first = args.first { return .glyph(first.description) }
            return .glyph("◌")
        case "state":
            return .string(state)
        case "receipt":
            let receiptId = sha256("\(receipts.count)-\(Date().timeIntervalSince1970)")
            receipts.append(receiptId)
            return .string(receiptId)
        default:
            if name.hasPrefix("agent.") {
                outputLog.append("🤖 agent: \(name) \(args.map { $0.description })")
                return .string("[agent:\(name)]")
            }
            if name.hasPrefix("export.") {
                outputLog.append("⇄ export: \(name)")
                return .string("[export:\(name)]")
            }
            if name.hasPrefix("import.") {
                outputLog.append("⇄ import: \(name)")
                return .null
            }
            return .null
        }
    }

    private func isTruthy(_ value: GlyphValue) -> Bool {
        switch value {
        case .boolean(let b): return b
        case .number(let n):  return n != 0
        case .string(let s):  return !s.isEmpty
        case .null:           return false
        default:              return true
        }
    }

    public var summary: String {
        "VM: \(isRunning ? "◉ running" : "◌ idle") | state=\(state) | pc=\(pc)/\(bytecode.count) | stack=\(stack.count) | \(receipts.count) receipts"
    }
}

// MARK: - VM Result

public struct VMResult {
    public let success: Bool
    public let output: String
    public let finalState: String
    public let receipts: [String]
    public let transitions: [(String, String, Double)]
    public let steps: Int

    public var summary: String {
        success ? "✓ VM: \(steps) steps, state=\(finalState), \(receipts.count) receipts" : "✕ VM: halted after \(steps) steps"
    }
}

// MARK: - Glyph Program

public struct GlyphProgram: Identifiable, Codable {
    public let id: String
    public let name: String
    public let source: String
    public let bytecode: [GlyphBytecode]
    public let receiptHash: String
    public let createdAt: Double
    public var lastRun: Double?
    public var runCount: Int

    public init(name: String, source: String, bytecode: [GlyphBytecode], receiptHash: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.name = name
        self.source = source
        self.bytecode = bytecode
        self.receiptHash = receiptHash
        self.createdAt = Date().timeIntervalSince1970
        self.lastRun = nil
        self.runCount = 0
    }

    public var summary: String {
        "⟡ \(name): \(bytecode.count) instructions, run \(runCount)x [\(receiptHash.prefix(12))]"
    }
}

// MARK: - Glyph Runtime

public final class GlyphRuntime: ObservableObject {
    @Published public var compiler: GlyphCompiler
    @Published public var vm: GlyphVM
    @Published public var programs: [GlyphProgram] = []
    @Published public var lastResult: VMResult?
    @Published public var lastCompile: CompileResult?

    public let llmEngine: LLMEngine?

    public init(llmEngine: LLMEngine? = nil) {
        self.llmEngine = llmEngine
        self.compiler = GlyphCompiler(llmEngine: llmEngine)
        self.vm = GlyphVM(llmEngine: llmEngine)
    }

    public func compileAndRun(_ source: String, name: String = "program") -> VMResult {
        let compileResult = compiler.compile(source)
        lastCompile = compileResult

        guard compileResult.success else {
            return VMResult(success: false, output: compileResult.errors.map { $0.summary }.joined(separator: "\n"),
                           finalState: "error", receipts: [], transitions: [], steps: 0)
        }

        let program = GlyphProgram(name: name, source: source,
                                    bytecode: compileResult.bytecode,
                                    receiptHash: compileResult.receiptHash)
        programs.append(program)

        vm.load(compileResult.bytecode)
        let result = vm.run()
        lastResult = result

        if let idx = programs.firstIndex(where: { $0.id == program.id }) {
            programs[idx].lastRun = Date().timeIntervalSince1970
            programs[idx].runCount += 1
        }

        return result
    }

    public func compileOnly(_ source: String) -> CompileResult {
        return compiler.compile(source)
    }

    public func runProgram(_ id: String) -> VMResult? {
        guard let program = programs.first(where: { $0.id == id }) else { return nil }
        vm.load(program.bytecode)
        let result = vm.run()
        if let idx = programs.firstIndex(where: { $0.id == id }) {
            programs[idx].lastRun = Date().timeIntervalSince1970
            programs[idx].runCount += 1
        }
        return result
    }

    public var summary: String {
        "GlyphRuntime: \(programs.count) programs | \(compiler.summary) | \(vm.summary)"
    }
}

// MARK: - Glyph Standard Library

public struct GlyphStdLib {
    public static let exampleProgram = """
    // Example .glyph program
    ◉ state: idle

    transition idle -> active {
        ◌ initialize
        🧾 receipt
    }

    transition active -> complete {
        ◆ finalize
        🧾 receipt
    }

    llm "Analyze current state and suggest next action"

    if state == "active" {
        ⌁ execute
    }

    match state {
        idle -> { ◌ waiting }
        active -> { ⌁ working }
        complete -> { ◆ done }
    }
    """

    public static let quantumPanelProgram = """
    quantum superposition {
        panel alpha { ◉ live }
        panel beta { ◇ indexed }
        panel gamma { ⧖ expiring }
        panel delta { ⟁ anomalous }
    }

    trend {
        ▲ rising_files
        ▼ falling_activity
        ⟡ emerging_patterns
    }

    heat {
        ◉◆⌁ live_verified_stream
        ◇⟡▲ indexed_ai_readable_trending
        ⟁⧖▼ anomaly_expiring_degrading
    }

    ram {
        resident 42MB
        streamed 9.4GB
        cached 128MB
        discarded 8.8GB
    }
    """

    public static let agentProgram = """
    agent builder {
        workspace main
        cursor primary

        state scanning
        transition scanning -> analyzing { ◌ scan_complete }
        transition analyzing -> executing { ⟡ analysis_done }
        transition executing -> verifying { ⌁ exec_done }
        transition verifying -> complete { ◆ verified }

        llm "Generate execution plan for current task"

        receipt { 🧾 every_action }
    }
    """

    public static let allExamples: [String] = [
        exampleProgram,
        quantumPanelProgram,
        agentProgram
    ]
}

// MARK: - Glyph Debugger

public final class GlyphDebugger: ObservableObject {
    @Published public var breakpoints: Set<Int> = []
    @Published public var watchVariables: Set<String> = []
    @Published public var traceLog: [TraceEntry] = []
    @Published public var isPaused: Bool = false

    public let vm: GlyphVM

    public init(vm: GlyphVM) {
        self.vm = vm
    }

    public func toggleBreakpoint(_ pc: Int) {
        if breakpoints.contains(pc) {
            breakpoints.remove(pc)
        } else {
            breakpoints.insert(pc)
        }
    }

    public func watch(_ variable: String) {
        watchVariables.insert(variable)
    }

    public func unwatch(_ variable: String) {
        watchVariables.remove(variable)
    }

    public func step() -> Bool {
        let stepped = vm.step()
        traceLog.append(TraceEntry(
            pc: vm.pc,
            state: vm.state,
            stackDepth: vm.stack.count,
            watchedValues: watchVariables.reduce(into: [:]) { dict, name in
                dict[name] = vm.variables[name]?.description ?? "undefined"
            }
        ))
        if traceLog.count > 500 { traceLog.removeFirst(traceLog.count - 500) }
        return stepped
    }

    public func runUntilBreakpoint() {
        while vm.pc < vm.bytecode.count {
            if breakpoints.contains(vm.pc) {
                isPaused = true
                break
            }
            if !step() { break }
        }
    }

    public func clearTrace() {
        traceLog = []
    }

    public var summary: String {
        "Debugger: \(breakpoints.count) breakpoints, \(watchVariables.count) watches, \(traceLog.count) trace entries"
    }
}

public struct TraceEntry: Identifiable, Codable {
    public let id: Int
    public let timestamp: Double
    public let pc: Int
    public let state: String
    public let stackDepth: Int
    public let watchedValues: [String: String]

    public init(pc: Int, state: String, stackDepth: Int, watchedValues: [String: String]) {
        self.id = pc
        self.timestamp = Date().timeIntervalSince1970
        self.pc = pc
        self.state = state
        self.stackDepth = stackDepth
        self.watchedValues = watchedValues
    }

    public var summary: String {
        "pc=\(pc) state=\(state) stack=\(stackDepth) \(watchedValues.map { "\($0.key)=\($0.value)" }.joined(separator: " "))"
    }
}

// MARK: - Glyph REPL

public final class GlyphREPL: ObservableObject {
    @Published public var history: [REPLEntry] = []
    @Published public var currentInput: String = ""
    @Published public var output: String = ""

    public let runtime: GlyphRuntime

    public init(runtime: GlyphRuntime) {
        self.runtime = runtime
    }

    public func evaluate(_ input: String) -> String {
        let result = runtime.compileAndRun(input, name: "repl")
        let entry = REPLEntry(input: input, output: result.output, success: result.success)
        history.append(entry)
        if history.count > 100 { history.removeFirst(history.count - 100) }
        output = result.output
        return result.output
    }

    public func clear() {
        history = []
        output = ""
        currentInput = ""
    }

    public var summary: String {
        "REPL: \(history.count) entries | \(runtime.summary)"
    }
}

public struct REPLEntry: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let input: String
    public let output: String
    public let success: Bool

    public init(input: String, output: String, success: Bool) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.input = input
        self.output = output
        self.success = success
    }

    public var summary: String {
        "\(success ? "✓" : "✕") \(input.prefix(40)) → \(output.prefix(40))"
    }
}
