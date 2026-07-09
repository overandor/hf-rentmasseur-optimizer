//
//  SecretsDetector.swift
//  CursorAgent OS
//
//  Scans file content and commands for secrets before execution.
//  Blocks writes containing API keys, private keys, tokens, passwords.
//  OWASP-aligned: prevent secret exfiltration through agent file writes.
//

import Foundation
import CryptoKit

// MARK: - Secret Pattern

public struct SecretPattern: Identifiable, Codable {
    public let id: String
    public let name: String
    public let pattern: String
    public let severity: SecretSeverity
    public let description: String

    public init(name: String, pattern: String, severity: SecretSeverity, description: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.name = name
        self.pattern = pattern
        self.severity = severity
        self.description = description
    }
}

public enum SecretSeverity: String, Codable, CaseIterable {
    case info     = "info"
    case warning  = "warning"
    case critical = "critical"

    public var glyph: String {
        switch self {
        case .info:     return "◇"
        case .warning:  return "▲"
        case .critical: return "⟁"
        }
    }
}

// MARK: - Secret Detection Result

public struct SecretDetectionResult: Identifiable {
    public let id: String
    public let pattern: SecretPattern
    public let matchedText: String
    public let lineNumber: Int
    public let column: Int
    public let context: String

    public init(pattern: SecretPattern, matchedText: String, lineNumber: Int, column: Int, context: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.pattern = pattern
        self.matchedText = matchedText
        self.lineNumber = lineNumber
        self.column = column
        self.context = context
    }
}

// MARK: - Secrets Detector

public final class SecretsDetector {
    public let patterns: [SecretPattern]

    public init() {
        self.patterns = SecretsDetector.defaultPatterns()
    }

    public init(customPatterns: [SecretPattern]) {
        self.patterns = customPatterns
    }

    // MARK: - Scan Content

    public func scan(_ content: String) -> [SecretDetectionResult] {
        var results: [SecretDetectionResult] = []
        let lines = content.components(separatedBy: "\n")

        for (lineIdx, line) in lines.enumerated() {
            for pattern in self.patterns {
                guard let regex = try? NSRegularExpression(pattern: pattern.pattern, options: [.caseInsensitive]) else {
                    continue
                }

                let nsLine = line as NSString
                let matches = regex.matches(in: line, options: [], range: NSRange(location: 0, length: nsLine.length))

                for match in matches {
                    let matchedText = nsLine.substring(with: match.range)
                    let context = line.trimmingCharacters(in: .whitespaces)

                    // Redact the secret in the stored context
                    let redactedContext = redactSecrets(in: context, pattern: pattern.pattern)

                    results.append(SecretDetectionResult(
                        pattern: pattern,
                        matchedText: String(matchedText.prefix(8)) + "...(redacted)",
                        lineNumber: lineIdx + 1,
                        column: match.range.location + 1,
                        context: redactedContext
                    ))
                }
            }
        }

        return results
    }

    // MARK: - Quick Check (boolean)

    public func containsSecrets(_ content: String) -> Bool {
        !scan(content).filter { $0.pattern.severity == .critical || $0.pattern.severity == .warning }.isEmpty
    }

    public func containsCriticalSecrets(_ content: String) -> Bool {
        !scan(content).filter { $0.pattern.severity == .critical }.isEmpty
    }

    // MARK: - Scan File

    public func scanFile(at url: URL) -> [SecretDetectionResult] {
        guard let content = try? String(contentsOf: url, encoding: .utf8) else {
            return []
        }
        return scan(content)
    }

    // MARK: - Scan Command

    public func scanCommand(_ command: String, arguments: [String]) -> [SecretDetectionResult] {
        let fullCommand = command + " " + arguments.joined(separator: " ")
        return scan(fullCommand)
    }

    // MARK: - Block Decision

    public func shouldBlock(content: String) -> Bool {
        let results = scan(content)
        return results.contains { $0.pattern.severity == .critical }
    }

    public func shouldWarn(content: String) -> Bool {
        let results = scan(content)
        return results.contains { $0.pattern.severity == .warning }
    }

    // MARK: - Redaction

    public func redactSecrets(in content: String) -> String {
        var redacted = content

        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern.pattern, options: [.caseInsensitive]) {
                let range = NSRange(location: 0, length: (redacted as NSString).length)
                redacted = regex.stringByReplacingMatches(
                    in: redacted,
                    options: [],
                    range: range,
                    withTemplate: "[REDACTED:\(pattern.name)]"
                )
            }
        }

        return redacted
    }

    private func redactSecrets(in text: String, pattern: String) -> String {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else {
            return text
        }
        let range = NSRange(location: 0, length: (text as NSString).length)
        return regex.stringByReplacingMatches(in: text, options: [], range: range, withTemplate: "[REDACTED]")
    }

    // MARK: - Summary

    public func summary(for results: [SecretDetectionResult]) -> String {
        let critical = results.filter { $0.pattern.severity == .critical }.count
        let warning = results.filter { $0.pattern.severity == .warning }.count
        let info = results.filter { $0.pattern.severity == .info }.count

        if results.isEmpty {
            return "No secrets detected"
        }

        return "Secrets: \(critical) critical, \(warning) warning, \(info) info"
    }

    // MARK: - Default Patterns

    public static func defaultPatterns() -> [SecretPattern] {
        [
            // AWS
            SecretPattern(
                name: "AWS Access Key",
                pattern: "AKIA[0-9A-Z]{16}",
                severity: .critical,
                description: "AWS access key ID"
            ),
            SecretPattern(
                name: "AWS Secret Key",
                pattern: "aws_secret_access_key\\s*[=:]\\s*[A-Za-z0-9/+=]{40}",
                severity: .critical,
                description: "AWS secret access key"
            ),

            // GitHub
            SecretPattern(
                name: "GitHub PAT",
                pattern: "ghp_[a-zA-Z0-9]{36}",
                severity: .critical,
                description: "GitHub personal access token"
            ),
            SecretPattern(
                name: "GitHub OAuth",
                pattern: "gho_[a-zA-Z0-9]{36}",
                severity: .critical,
                description: "GitHub OAuth token"
            ),
            SecretPattern(
                name: "GitHub App",
                pattern: "ghs_[a-zA-Z0-9]{36}",
                severity: .critical,
                description: "GitHub App token"
            ),

            // OpenAI
            SecretPattern(
                name: "OpenAI API Key",
                pattern: "sk-[a-zA-Z0-9]{48}",
                severity: .critical,
                description: "OpenAI API key"
            ),

            // Private Keys
            SecretPattern(
                name: "RSA Private Key",
                pattern: "-----BEGIN RSA PRIVATE KEY-----",
                severity: .critical,
                description: "RSA private key block"
            ),
            SecretPattern(
                name: "EC Private Key",
                pattern: "-----BEGIN EC PRIVATE KEY-----",
                severity: .critical,
                description: "EC private key block"
            ),
            SecretPattern(
                name: "Private Key",
                pattern: "-----BEGIN PRIVATE KEY-----",
                severity: .critical,
                description: "Generic private key block"
            ),
            SecretPattern(
                name: "OpenSSH Private Key",
                pattern: "-----BEGIN OPENSSH PRIVATE KEY-----",
                severity: .critical,
                description: "OpenSSH private key"
            ),

            // Slack
            SecretPattern(
                name: "Slack Token",
                pattern: "xox[baprs]-[0-9a-zA-Z-]{10,}",
                severity: .critical,
                description: "Slack API token"
            ),

            // JWT
            SecretPattern(
                name: "JWT Token",
                pattern: "eyJ[a-zA-Z0-9_-]+\\.[a-zA-Z0-9_-]+\\.[a-zA-Z0-9_-]+",
                severity: .warning,
                description: "JSON Web Token"
            ),

            // Generic secrets
            SecretPattern(
                name: "API Key Variable",
                pattern: "(?i)(api[_-]?key|apikey)\\s*[=:]\\s*[\"'][^\"']{20,}[\"']",
                severity: .warning,
                description: "API key in variable assignment"
            ),
            SecretPattern(
                name: "Secret Key Variable",
                pattern: "(?i)(secret[_-]?key|secretkey)\\s*[=:]\\s*[\"'][^\"']{16,}[\"']",
                severity: .warning,
                description: "Secret key in variable assignment"
            ),
            SecretPattern(
                name: "Password Variable",
                pattern: "(?i)(password|passwd|pwd)\\s*[=:]\\s*[\"'][^\"']{8,}[\"']",
                severity: .warning,
                description: "Password in variable assignment"
            ),
            SecretPattern(
                name: "Token Variable",
                pattern: "(?i)(auth[_-]?token|access[_-]?token|token)\\s*[=:]\\s*[\"'][^\"']{20,}[\"']",
                severity: .warning,
                description: "Token in variable assignment"
            ),

            // Connection strings
            SecretPattern(
                name: "Database URL",
                pattern: "(postgres|mongodb|mysql|redis)://[^:\\s]+:[^@\\s]+@",
                severity: .critical,
                description: "Database connection string with credentials"
            ),
            SecretPattern(
                name: "Generic Connection String",
                pattern: "://[^:\\s]+:[^@\\s]+@[a-zA-Z0-9.-]+",
                severity: .warning,
                description: "Connection string with credentials"
            ),

            // Cloud provider tokens
            SecretPattern(
                name: "Google API Key",
                pattern: "AIza[0-9A-Za-z_-]{35}",
                severity: .critical,
                description: "Google API key"
            ),
            SecretPattern(
                name: "Stripe Key",
                pattern: "sk_(live|test)_[a-zA-Z0-9]{24,}",
                severity: .critical,
                description: "Stripe secret key"
            ),
            SecretPattern(
                name: "Twilio Key",
                pattern: "SK[0-9a-fA-F]{32}",
                severity: .warning,
                description: "Twilio API key"
            ),

            // .env file indicators
            SecretPattern(
                name: "Env File Assignment",
                pattern: "(?i)\\b[A-Z_]{3,}_KEY\\s*=\\s*[\"']?[A-Za-z0-9/+=]{20,}[\"']?",
                severity: .info,
                description: "Environment variable key assignment"
            ),

            // Sensitive file paths
            SecretPattern(
                name: "SSH Path Reference",
                pattern: "~/.ssh/(id_rsa|id_ecdsa|id_ed25519|config|known_hosts)",
                severity: .warning,
                description: "Reference to SSH key files"
            ),
            SecretPattern(
                name: "AWS Credentials Path",
                pattern: "~/.aws/credentials",
                severity: .warning,
                description: "Reference to AWS credentials file"
            ),
        ]
    }
}

// MARK: - Sensitive Path Detector

public final class SensitivePathDetector {
    public static let sensitivePaths: [String] = [
        "/.ssh/",
        "/.env",
        "/.env.local",
        "/.env.production",
        "/.aws/credentials",
        "/.aws/config",
        "/.gnupg/",
        "/.keychain",
        "/Library/Keychains/",
        "/.zshrc",
        "/.bashrc",
        "/.bash_profile",
        "/.profile",
        "/.netrc",
        "/.npmrc",
        "/.pypirc",
        "/.docker/config.json",
        "/.kube/config",
        "/.gitconfig",
        "/.git-credentials",
    ]

    public static func isSensitive(_ path: String) -> Bool {
        let expanded = path.replacingOccurrences(of: "~", with: FileManager.default.homeDirectoryForCurrentUser.path)
        let lower = expanded.lowercased()
        return sensitivePaths.contains { lower.contains($0.lowercased()) }
    }

    public static func checkCommand(_ command: String, args: [String]) -> [String] {
        let fullCommand = (command + " " + args.joined(separator: " ")).lowercased()
        return sensitivePaths.filter { fullCommand.contains($0.lowercased()) }
    }
}

// MARK: - Content Sanitizer

public final class ContentSanitizer {
    private let detector: SecretsDetector

    public init(detector: SecretsDetector = SecretsDetector()) {
        self.detector = detector
    }

    // Sanitize content before writing to disk
    public func sanitize(_ content: String) -> SanitizationResult {
        let results = detector.scan(content)
        let criticalResults = results.filter { $0.pattern.severity == .critical }
        let warningResults = results.filter { $0.pattern.severity == .warning }

        if !criticalResults.isEmpty {
            return SanitizationResult(
                shouldBlock: true,
                shouldWarn: true,
                sanitizedContent: detector.redactSecrets(in: content),
                detections: results,
                reason: "Critical secrets detected: \(criticalResults.map { $0.pattern.name }.joined(separator: ", "))"
            )
        }

        if !warningResults.isEmpty {
            return SanitizationResult(
                shouldBlock: false,
                shouldWarn: true,
                sanitizedContent: content,
                detections: results,
                reason: "Potential secrets detected: \(warningResults.map { $0.pattern.name }.joined(separator: ", "))"
            )
        }

        return SanitizationResult(
            shouldBlock: false,
            shouldWarn: false,
            sanitizedContent: content,
            detections: results,
            reason: nil
        )
    }
}

public struct SanitizationResult {
    public let shouldBlock: Bool
    public let shouldWarn: Bool
    public let sanitizedContent: String
    public let detections: [SecretDetectionResult]
    public let reason: String?

    public var isClean: Bool { !shouldBlock && !shouldWarn }
}
