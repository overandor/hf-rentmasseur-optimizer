//
//  GlyphLanguage.swift
//  CursorAgent OS
//
//  Glyph Operating Layer for QuadrantOS.
//  Replace labels with compressed visual syntax.
//  Compound glyphs become system language.
//  Labels fade as user becomes expert.
//

import SwiftUI
import Foundation

// MARK: - System Glyphs

public enum SysGlyph: String, CaseIterable {
    // Life states
    case live       = "◉"
    case indexed    = "◇"
    case rising     = "▲"
    case falling    = "▼"
    case verified   = "◆"
    case anomalous  = "⟁"
    case dormant    = "◌"
    case mirrored   = "◍"
    case duplicated = "⧉"
    case streaming  = "⌁"
    case aiReadable = "⟡"
    case expiring   = "⧖"

    // Action glyphs
    case inspect    = "🔍"
    case summarize  = "📋"
    case diff       = "⚖"
    case trace      = "📍"
    case extract    = "⬇"
    case compress   = "📦"
    case compare    = "⇄"
    case route      = "→"
    case revoke     = "⊘"
    case predict    = "🔮"
    case approve    = "✓"
    case deny       = "✕"
    case pause      = "⏸"
    case kill       = "☠"
    case spawn      = "⚡"

    // Object glyphs
    case file       = "📄"
    case folder     = "📁"
    case receipt    = "🧾"
    case task       = "☐"
    case done       = "☑"
    case agent      = "🤖"
    case window     = "🪟"
    case process    = "⚙"
    case quadrant   = "⊞"
    case message    = "✉"
    case command    = "⌘"
    case terminal   = "⌥"
    case database   = "🗄"
    case network    = "🌐"
    case security   = "🛡"
    case finance    = "💰"
    case research   = "🔬"
    case builder    = "🔨"
    case verifier   = "✔"
    case human      = "👤"

    public var label: String {
        switch self {
        case .live:       return "live"
        case .indexed:    return "indexed"
        case .rising:     return "rising"
        case .falling:    return "falling"
        case .verified:   return "verified"
        case .anomalous:  return "anomalous"
        case .dormant:    return "dormant"
        case .mirrored:   return "mirrored"
        case .duplicated: return "duplicated"
        case .streaming:  return "streaming"
        case .aiReadable: return "AI-readable"
        case .expiring:   return "expiring"
        case .inspect:    return "inspect"
        case .summarize:  return "summarize"
        case .diff:       return "diff"
        case .trace:      return "trace"
        case .extract:    return "extract"
        case .compress:   return "compress"
        case .compare:    return "compare"
        case .route:      return "route"
        case .revoke:     return "revoke"
        case .predict:    return "predict"
        case .approve:    return "approve"
        case .deny:       return "deny"
        case .pause:      return "pause"
        case .kill:       return "kill"
        case .spawn:      return "spawn"
        case .file:       return "file"
        case .folder:     return "folder"
        case .receipt:    return "receipt"
        case .task:       return "task"
        case .done:       return "done"
        case .agent:      return "agent"
        case .window:     return "window"
        case .process:    return "process"
        case .quadrant:   return "quadrant"
        case .message:    return "message"
        case .command:    return "command"
        case .terminal:   return "terminal"
        case .database:   return "database"
        case .network:    return "network"
        case .security:   return "security"
        case .finance:    return "finance"
        case .research:   return "research"
        case .builder:    return "builder"
        case .verifier:   return "verifier"
        case .human:      return "human"
        }
    }
}

// MARK: - Compound Glyph

public struct CompoundGlyph: Hashable {
    public let glyphs: [SysGlyph]

    public init(_ glyphs: SysGlyph...) {
        self.glyphs = glyphs
    }

    public init(glyphs: [SysGlyph]) {
        self.glyphs = glyphs
    }

    public var rendered: String {
        glyphs.map { $0.rawValue }.joined()
    }

    public var meaning: String {
        glyphs.map { $0.label }.joined(separator: " ")
    }

    // Preset compounds
    public static let liveVerifiedStream = CompoundGlyph(.live, .verified, .streaming)
    public static let indexedAIReadableTrending = CompoundGlyph(.indexed, .aiReadable, .rising)
    public static let anomalyExpiringDegrading = CompoundGlyph(.anomalous, .expiring, .falling)
    public static let dormantReceiptPending = CompoundGlyph(.dormant, .receipt, .expiring)
    public static let liveAgentActing = CompoundGlyph(.live, .agent, .streaming)
    public static let verifiedReceiptChain = CompoundGlyph(.verified, .receipt, .verified)
    public static let anomalousSecurityBlocked = CompoundGlyph(.anomalous, .security, .deny)
    public static let risingFileAttention = CompoundGlyph(.rising, .file, .aiReadable)
}

// MARK: - Glyph Density Controller

public final class GlyphDensityController: ObservableObject {
    @Published public var expertiseLevel: ExpertiseLevel = .novice
    @Published public var labelOpacity: Double = 1.0
    @Published public var glyphDensity: Double = 0.3

    public enum ExpertiseLevel: String, CaseIterable {
        case novice    = "novice"
        case oper      = "operator"
        case expert    = "expert"
        case master    = "master"

        public var labelOpacity: Double {
            switch self {
            case .novice:   return 1.0
            case .oper:     return 0.7
            case .expert:   return 0.3
            case .master:   return 0.0
            }
        }

        public var glyphDensity: Double {
            switch self {
            case .novice:   return 0.3
            case .oper:     return 0.5
            case .expert:   return 0.8
            case .master:   return 1.0
            }
        }
    }

    public init() {}

    public func setLevel(_ level: ExpertiseLevel) {
        expertiseLevel = level
        labelOpacity = level.labelOpacity
        glyphDensity = level.glyphDensity
    }

    public func shouldShowLabel(for glyph: SysGlyph) -> Bool {
        labelOpacity > 0.1
    }

    public func glyphView(_ glyph: SysGlyph, size: CGFloat = 14) -> some View {
        VStack(spacing: 2) {
            Text(glyph.rawValue)
                .font(.system(size: size))
                .foregroundColor(.orange)
            if shouldShowLabel(for: glyph) {
                Text(glyph.label)
                    .font(.system(size: 7, weight: .light, design: .monospaced))
                    .foregroundColor(.orange.opacity(labelOpacity * 0.5))
            }
        }
    }

    public var summary: String {
        "Glyphs: \(expertiseLevel.rawValue) | labels \(String(format: "%.0f%%", labelOpacity * 100)) | density \(String(format: "%.0f%%", glyphDensity * 100))"
    }
}

// MARK: - Glyph Stream

public struct GlyphStream: View {
    public let compounds: [CompoundGlyph]
    public let density: Double

    public init(compounds: [CompoundGlyph], density: Double = 0.5) {
        self.compounds = compounds
        self.density = density
    }

    public var body: some View {
        HStack(spacing: 8) {
            ForEach(compounds, id: \.rendered) { compound in
                Text(compound.rendered)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.orange.opacity(density))
            }
        }
    }
}

// MARK: - Status Bar Glyphs

public struct StatusBarGlyphs: View {
    @ObservedObject var density: GlyphDensityController
    public let receipts: Int
    public let chainValid: Bool
    public let threatLevel: ThreatLevel
    public let activeAgents: Int
    public let pendingApprovals: Int

    public init(density: GlyphDensityController, receipts: Int, chainValid: Bool,
                threatLevel: ThreatLevel, activeAgents: Int, pendingApprovals: Int) {
        self.density = density
        self.receipts = receipts
        self.chainValid = chainValid
        self.threatLevel = threatLevel
        self.activeAgents = activeAgents
        self.pendingApprovals = pendingApprovals
    }

    public var body: some View {
        HStack(spacing: 12) {
            // Receipt status
            HStack(spacing: 3) {
                Text(SysGlyph.receipt.rawValue)
                Text("\(receipts)")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                Text(chainValid ? SysGlyph.verified.rawValue : "⛓")
                    .foregroundColor(chainValid ? .green : .red)
            }
            .foregroundColor(.orange)

            // Threat
            HStack(spacing: 3) {
                Text(threatLevel.glyph)
                if density.shouldShowLabel(for: .security) {
                    Text(threatLevel.label)
                        .font(.system(size: 8, design: .monospaced))
                }
            }
            .foregroundColor(threatColor)

            // Agents
            HStack(spacing: 3) {
                Text(SysGlyph.agent.rawValue)
                Text("\(activeAgents)")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
            }
            .foregroundColor(.orange)

            // Approvals
            if pendingApprovals > 0 {
                HStack(spacing: 3) {
                    Text(SysGlyph.expiring.rawValue)
                    Text("\(pendingApprovals)")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                }
                .foregroundColor(.yellow)
            }
        }
    }

    private var threatColor: Color {
        switch threatLevel {
        case .safe:     return .green
        case .low:      return .blue
        case .medium:   return .yellow
        case .high:     return .orange
        case .critical: return .red
        }
    }
}

// MARK: - Glyph Lexer

public final class GlyphLexer {
    public init() {}

    public func tokenize(_ input: String) -> [GlyphToken] {
        var tokens: [GlyphToken] = []
        var current = ""

        for char in input {
            current.append(char)
            if let glyph = SysGlyph(rawValue: current) {
                tokens.append(GlyphToken(glyph: glyph, position: tokens.count))
                current = ""
            }
        }

        if !current.isEmpty {
            tokens.append(GlyphToken(raw: current, position: tokens.count))
        }

        return tokens
    }

    public func parse(_ input: String) -> [CompoundGlyph] {
        let tokens = tokenize(input)
        var compounds: [CompoundGlyph] = []
        var currentGroup: [SysGlyph] = []

        for token in tokens {
            if let glyph = token.glyph {
                currentGroup.append(glyph)
            } else {
                if !currentGroup.isEmpty {
                    compounds.append(CompoundGlyph(glyphs: currentGroup))
                    currentGroup.removeAll()
                }
            }
        }

        if !currentGroup.isEmpty {
            compounds.append(CompoundGlyph(glyphs: currentGroup))
        }

        return compounds
    }
}

public struct GlyphToken {
    public let glyph: SysGlyph?
    public let raw: String
    public let position: Int

    public init(glyph: SysGlyph, position: Int) {
        self.glyph = glyph
        self.raw = glyph.rawValue
        self.position = position
    }

    public init(raw: String, position: Int) {
        self.glyph = nil
        self.raw = raw
        self.position = position
    }
}

// MARK: - Glyph Command Surface

public struct GlyphCommandSurface: View {
    public let commands: [GlyphCommand]
    @ObservedObject var density: GlyphDensityController
    public let onCommand: (GlyphCommand) -> Void

    public init(commands: [GlyphCommand], density: GlyphDensityController,
                onCommand: @escaping (GlyphCommand) -> Void) {
        self.commands = commands
        self.density = density
        self.onCommand = onCommand
    }

    public var body: some View {
        HStack(spacing: 6) {
            ForEach(commands, id: \.id) { cmd in
                Button(action: { onCommand(cmd) }) {
                    HStack(spacing: 3) {
                        Text(cmd.glyph.rawValue)
                            .font(.system(size: 14))
                        if density.shouldShowLabel(for: cmd.glyph) {
                            Text(cmd.label)
                                .font(.system(size: 8, weight: .bold, design: .monospaced))
                                .foregroundColor(.orange.opacity(density.labelOpacity * 0.5))
                        }
                    }
                    .foregroundColor(cmd.available ? .orange : .orange.opacity(0.2))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(Color.orange.opacity(cmd.available ? 0.08 : 0.02))
                    )
                }
                .buttonStyle(.plain)
                .disabled(!cmd.available)
            }
        }
    }
}

public struct GlyphCommand: Identifiable {
    public let id: String
    public let glyph: SysGlyph
    public let label: String
    public let action: String
    public let available: Bool

    public init(glyph: SysGlyph, label: String, action: String, available: Bool = true) {
        self.id = action
        self.glyph = glyph
        self.label = label
        self.action = action
        self.available = available
    }

    public static let agentCommands: [GlyphCommand] = [
        GlyphCommand(glyph: .inspect, label: "inspect", action: "inspect"),
        GlyphCommand(glyph: .summarize, label: "summarize", action: "summarize"),
        GlyphCommand(glyph: .diff, label: "diff", action: "diff"),
        GlyphCommand(glyph: .trace, label: "trace", action: "trace"),
        GlyphCommand(glyph: .extract, label: "extract", action: "extract"),
        GlyphCommand(glyph: .compress, label: "compress", action: "compress"),
        GlyphCommand(glyph: .compare, label: "compare", action: "compare"),
        GlyphCommand(glyph: .route, label: "route", action: "route"),
        GlyphCommand(glyph: .revoke, label: "revoke", action: "revoke"),
        GlyphCommand(glyph: .predict, label: "predict", action: "predict"),
    ]
}
