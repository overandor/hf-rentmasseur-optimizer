//
//  TelemetryEngine.swift
//  CursorAgent OS
//
//  Telemetry and observability system.
//  - Real-time metrics collection
//  - Time-series storage
//  - Metric aggregation and rollup
//  - Alerting and thresholds
//  - Trace correlation
//  - Performance profiling
//

import Foundation
import Combine

// MARK: - Metric Definition

public struct MetricDefinition: Codable, Identifiable {
    public let id: String
    public let name: String
    public let unit: MetricUnit
    public let description: String
    public let category: MetricCategory
    public let aggregation: AggregationType

    public enum MetricUnit: String, Codable, CaseIterable {
        case count     = "count"
        case seconds   = "seconds"
        case bytes     = "bytes"
        case percent   = "percent"
        case ratio     = "ratio"
        case tokens    = "tokens"
        case actions   = "actions"
        case none      = "none"

        public var glyph: String {
            switch self {
            case .count:   return "#"
            case .seconds: return "s"
            case .bytes:   return "B"
            case .percent: return "%"
            case .ratio:   return "x"
            case .tokens:  return "tok"
            case .actions: return "act"
            case .none:    return ""
            }
        }
    }

    public enum MetricCategory: String, Codable, CaseIterable {
        case performance = "performance"
        case security    = "security"
        case budget      = "budget"
        case agent       = "agent"
        case system      = "system"
        case receipt     = "receipt"
        case task        = "task"
        case network     = "network"

        public var glyph: String {
            switch self {
            case .performance: return "⚡"
            case .security:    return "🛡"
            case .budget:      return "⧖"
            case .agent:       return "🤖"
            case .system:      return "⚙"
            case .receipt:     return "🧾"
            case .task:        return "☐"
            case .network:     return "🌐"
            }
        }
    }

    public enum AggregationType: String, Codable, CaseIterable {
        case sum     = "sum"
        case avg     = "avg"
        case max     = "max"
        case min     = "min"
        case last    = "last"
        case count   = "count"
        case p95     = "p95"
        case p99     = "p99"
    }

    public init(name: String, unit: MetricUnit, description: String,
                category: MetricCategory, aggregation: AggregationType = .avg) {
        self.id = name
        self.name = name
        self.unit = unit
        self.description = description
        self.category = category
        self.aggregation = aggregation
    }
}

// MARK: - Metric Sample

public struct MetricSample: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let metricName: String
    public let value: Double
    public let tags: [String: String]

    public init(metricName: String, value: Double, tags: [String: String] = [:]) {
        self.id = UUID().uuidString.prefix(16).description
        self.timestamp = Date().timeIntervalSince1970
        self.metricName = metricName
        self.value = value
        self.tags = tags
    }
}

// MARK: - Telemetry Engine

public final class TelemetryEngine: ObservableObject {
    @Published public var samples: [MetricSample] = []
    @Published public var definitions: [MetricDefinition] = []
    @Published public var alerts: [TelemetryAlert] = []
    @Published public var thresholds: [String: AlertThreshold] = [:]
    @Published public var totalSamples: Int = 0
    @Published public var activeAlerts: Int = 0

    private let maxSamples: Int = 5000

    public init() {
        registerDefaultMetrics()
        setupDefaultThresholds()
    }

    // MARK: - Default Metrics

    private func registerDefaultMetrics() {
        definitions = [
            MetricDefinition(name: "agent.count", unit: .count, description: "Number of active agents",
                            category: .agent, aggregation: .last),
            MetricDefinition(name: "agent.tasks_completed", unit: .count, description: "Total tasks completed",
                            category: .agent, aggregation: .sum),
            MetricDefinition(name: "agent.success_rate", unit: .percent, description: "Agent success rate",
                            category: .agent, aggregation: .avg),
            MetricDefinition(name: "receipt.count", unit: .count, description: "Total receipts written",
                            category: .receipt, aggregation: .sum),
            MetricDefinition(name: "receipt.chain_valid", unit: .ratio, description: "Chain validity (1=valid, 0=broken)",
                            category: .receipt, aggregation: .last),
            MetricDefinition(name: "receipt.write_time", unit: .seconds, description: "Time to write a receipt",
                            category: .receipt, aggregation: .p95),
            MetricDefinition(name: "security.threats", unit: .count, description: "Active threat count",
                            category: .security, aggregation: .last),
            MetricDefinition(name: "security.blocks", unit: .count, description: "Blocked actions",
                            category: .security, aggregation: .sum),
            MetricDefinition(name: "budget.tokens_used", unit: .tokens, description: "Tokens consumed",
                            category: .budget, aggregation: .sum),
            MetricDefinition(name: "budget.actions_used", unit: .actions, description: "Actions consumed",
                            category: .budget, aggregation: .sum),
            MetricDefinition(name: "budget.remaining_pct", unit: .percent, description: "Budget remaining",
                            category: .budget, aggregation: .avg),
            MetricDefinition(name: "system.cpu", unit: .percent, description: "CPU usage",
                            category: .system, aggregation: .avg),
            MetricDefinition(name: "system.memory", unit: .percent, description: "Memory usage",
                            category: .system, aggregation: .avg),
            MetricDefinition(name: "system.disk", unit: .percent, description: "Disk usage",
                            category: .system, aggregation: .last),
            MetricDefinition(name: "task.duration", unit: .seconds, description: "Task execution duration",
                            category: .task, aggregation: .p95),
            MetricDefinition(name: "task.queue_size", unit: .count, description: "Pending task queue size",
                            category: .task, aggregation: .last),
            MetricDefinition(name: "network.requests", unit: .count, description: "Network requests made",
                            category: .network, aggregation: .sum),
            MetricDefinition(name: "network.latency", unit: .seconds, description: "Network latency",
                            category: .network, aggregation: .avg),
        ]
    }

    private func setupDefaultThresholds() {
        thresholds["agent.success_rate"] = AlertThreshold(metric: "agent.success_rate",
                                                          warning: 0.7, critical: 0.5, comparison: .lessThan)
        thresholds["receipt.chain_valid"] = AlertThreshold(metric: "receipt.chain_valid",
                                                           warning: 0.5, critical: 0.0, comparison: .lessThan)
        thresholds["security.threats"] = AlertThreshold(metric: "security.threats",
                                                        warning: 3, critical: 10, comparison: .greaterThan)
        thresholds["budget.remaining_pct"] = AlertThreshold(metric: "budget.remaining_pct",
                                                            warning: 20, critical: 5, comparison: .lessThan)
        thresholds["system.cpu"] = AlertThreshold(metric: "system.cpu",
                                                  warning: 80, critical: 95, comparison: .greaterThan)
        thresholds["system.memory"] = AlertThreshold(metric: "system.memory",
                                                     warning: 80, critical: 95, comparison: .greaterThan)
        thresholds["task.duration"] = AlertThreshold(metric: "task.duration",
                                                     warning: 60, critical: 300, comparison: .greaterThan)
        thresholds["task.queue_size"] = AlertThreshold(metric: "task.queue_size",
                                                       warning: 50, critical: 200, comparison: .greaterThan)
    }

    // MARK: - Record

    public func record(_ metricName: String, value: Double, tags: [String: String] = [:]) {
        let sample = MetricSample(metricName: metricName, value: value, tags: tags)
        samples.append(sample)
        totalSamples += 1

        if samples.count > maxSamples {
            samples.removeFirst(samples.count - maxSamples)
        }

        checkThreshold(metric: metricName, value: value)
    }

    public func recordBatch(_ samples: [(String, Double)]) {
        for (name, value) in samples {
            record(name, value: value)
        }
    }

    // MARK: - Threshold Checking

    private func checkThreshold(metric: String, value: Double) {
        guard let threshold = thresholds[metric] else { return }

        let triggered: TelemetryAlert.AlertLevel
        switch threshold.comparison {
        case .greaterThan:
            if value > threshold.critical { triggered = .critical }
            else if value > threshold.warning { triggered = .warning }
            else { return }
        case .lessThan:
            if value < threshold.critical { triggered = .critical }
            else if value < threshold.warning { triggered = .warning }
            else { return }
        }

        let alert = TelemetryAlert(
            metric: metric, value: value,
            threshold: threshold, level: triggered
        )
        alerts.append(alert)
        if alerts.count > 100 { alerts.removeFirst(alerts.count - 100) }
        if triggered == .critical { activeAlerts += 1 }
    }

    // MARK: - Query

    public func samplesFor(_ metric: String, limit: Int = 100) -> [MetricSample] {
        samples.filter { $0.metricName == metric }.suffix(limit).map { $0 }
    }

    public func aggregate(_ metric: String, type: MetricDefinition.AggregationType,
                          window: TimeInterval = 300) -> Double? {
        let cutoff = Date().timeIntervalSince1970 - window
        let relevant = samples.filter { $0.metricName == metric && $0.timestamp >= cutoff }

        guard !relevant.isEmpty else { return nil }
        let values = relevant.map { $0.value }

        switch type {
        case .sum:   return values.reduce(0, +)
        case .avg:   return values.reduce(0, +) / Double(values.count)
        case .max:   return values.max()
        case .min:   return values.min()
        case .last:  return values.last
        case .count: return Double(values.count)
        case .p95:
            let sorted = values.sorted()
            let idx = Int(Double(sorted.count) * 0.95)
            return sorted[min(idx, sorted.count - 1)]
        case .p99:
            let sorted = values.sorted()
            let idx = Int(Double(sorted.count) * 0.99)
            return sorted[min(idx, sorted.count - 1)]
        }
    }

    public func latestValue(_ metric: String) -> Double? {
        samples.filter { $0.metricName == metric }.last?.value
    }

    // MARK: - Rollup

    public func rollup(window: TimeInterval = 60) -> [MetricRollup] {
        let cutoff = Date().timeIntervalSince1970 - window
        let recent = samples.filter { $0.timestamp >= cutoff }

        var grouped: [String: [Double]] = [:]
        for sample in recent {
            grouped[sample.metricName, default: []].append(sample.value)
        }

        return grouped.map { (metric, values) in
            let def = definitions.first { $0.name == metric }
            let aggValue: Double
            switch def?.aggregation ?? .avg {
            case .sum:   aggValue = values.reduce(0, +)
            case .avg:   aggValue = values.reduce(0, +) / Double(values.count)
            case .max:   aggValue = values.max() ?? 0
            case .min:   aggValue = values.min() ?? 0
            case .last:  aggValue = values.last ?? 0
            case .count: aggValue = Double(values.count)
            case .p95:
                let sorted = values.sorted()
                aggValue = sorted[Int(Double(sorted.count) * 0.95)]
            case .p99:
                let sorted = values.sorted()
                aggValue = sorted[Int(Double(sorted.count) * 0.99)]
            }

            return MetricRollup(
                metric: metric,
                value: aggValue,
                sampleCount: values.count,
                unit: def?.unit ?? .none,
                category: def?.category ?? .system
            )
        }
    }

    // MARK: - Summary

    public var summary: String {
        "Telemetry: \(totalSamples) samples, \(definitions.count) metrics, \(activeAlerts) active alerts"
    }

    public func dashboard() -> [String: Double] {
        var dash: [String: Double] = [:]
        for def in definitions {
            if let val = latestValue(def.name) {
                dash[def.name] = val
            }
        }
        return dash
    }
}

// MARK: - Alert Threshold

public struct AlertThreshold: Codable {
    public let metric: String
    public let warning: Double
    public let critical: Double
    public let comparison: Comparison

    public enum Comparison: String, Codable {
        case greaterThan = "greater_than"
        case lessThan    = "less_than"
    }
}

// MARK: - Telemetry Alert

public struct TelemetryAlert: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let metric: String
    public let value: Double
    public let threshold: AlertThreshold
    public let level: AlertLevel

    public enum AlertLevel: String, Codable, CaseIterable {
        case warning  = "warning"
        case critical = "critical"

        public var glyph: String {
            switch self {
            case .warning:  return "⧖"
            case .critical: return "⟁"
            }
        }
    }

    public init(metric: String, value: Double, threshold: AlertThreshold, level: AlertLevel) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.metric = metric
        self.value = value
        self.threshold = threshold
        self.level = level
    }

    public var summary: String {
        "\(level.glyph) \(metric): \(value) (threshold: \(level == .critical ? threshold.critical : threshold.warning))"
    }
}

// MARK: - Metric Rollup

public struct MetricRollup: Identifiable, Codable {
    public let id: String
    public let metric: String
    public let value: Double
    public let sampleCount: Int
    public let unit: MetricDefinition.MetricUnit
    public let category: MetricDefinition.MetricCategory

    public init(metric: String, value: Double, sampleCount: Int,
                unit: MetricDefinition.MetricUnit, category: MetricDefinition.MetricCategory) {
        self.id = metric
        self.metric = metric
        self.value = value
        self.sampleCount = sampleCount
        self.unit = unit
        self.category = category
    }

    public var summary: String {
        "\(category.glyph) \(metric): \(String(format: "%.2f", value))\(unit.glyph) [\(sampleCount) samples]"
    }
}

// MARK: - Trace Correlator

public final class TraceCorrelator: ObservableObject {
    @Published public var traces: [Trace] = []
    @Published public var correlations: [TraceCorrelation] = []

    public init() {}

    public func startTrace(agentId: String, operation: String) -> Trace {
        let trace = Trace(agentId: agentId, operation: operation)
        traces.append(trace)
        if traces.count > 500 { traces.removeFirst(traces.count - 500) }
        return trace
    }

    public func endTrace(_ traceId: String, success: Bool) {
        if let idx = traces.firstIndex(where: { $0.id == traceId }) {
            traces[idx].endTime = Date().timeIntervalSince1970
            traces[idx].success = success
            traces[idx].duration = traces[idx].endTime - traces[idx].startTime
        }
    }

    public func correlate(anomalyMetric: String, anomalyTime: Double) -> [Trace] {
        let window: TimeInterval = 30
        let correlated = traces.filter { trace in
            abs(trace.startTime - anomalyTime) < window
        }
        if !correlated.isEmpty {
            correlations.append(TraceCorrelation(
                anomalyMetric: anomalyMetric,
                anomalyTime: anomalyTime,
                correlatedTraces: correlated.map { $0.id }
            ))
        }
        return correlated
    }

    public func slowestTraces(limit: Int = 10) -> [Trace] {
        traces.filter { $0.duration > 0 }.sorted { $0.duration > $1.duration }.prefix(limit).map { $0 }
    }

    public func failedTraces() -> [Trace] {
        traces.filter { !$0.success }
    }

    public var summary: String {
        "Traces: \(traces.count) total, \(failedTraces().count) failed, \(correlations.count) correlations"
    }
}

public struct Trace: Identifiable, Codable {
    public let id: String
    public let agentId: String
    public let operation: String
    public let startTime: Double
    public var endTime: Double
    public var duration: Double
    public var success: Bool
    public var spans: [TraceSpan]

    public init(agentId: String, operation: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.agentId = agentId
        self.operation = operation
        self.startTime = Date().timeIntervalSince1970
        self.endTime = 0
        self.duration = 0
        self.success = true
        self.spans = []
    }

    public mutating func addSpan(name: String, duration: Double) {
        spans.append(TraceSpan(name: name, duration: duration, timestamp: Date().timeIntervalSince1970))
    }
}

public struct TraceSpan: Identifiable, Codable {
    public let id: String
    public let name: String
    public let duration: Double
    public let timestamp: Double

    public init(name: String, duration: Double, timestamp: Double) {
        self.id = UUID().uuidString.prefix(16).description
        self.name = name
        self.duration = duration
        self.timestamp = timestamp
    }
}

public struct TraceCorrelation: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let anomalyMetric: String
    public let anomalyTime: Double
    public let correlatedTraces: [String]

    public init(anomalyMetric: String, anomalyTime: Double, correlatedTraces: [String]) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.anomalyMetric = anomalyMetric
        self.anomalyTime = anomalyTime
        self.correlatedTraces = correlatedTraces
    }
}

// MARK: - Performance Profiler

public final class PerformanceProfiler: ObservableObject {
    @Published public var profiles: [ProfileEntry] = []
    @Published public var hotspots: [Hotspot] = []

    public init() {}

    public func profile(agentId: String, operation: String, duration: Double, metadata: [String: String] = [:]) {
        let entry = ProfileEntry(agentId: agentId, operation: operation,
                                  duration: duration, metadata: metadata)
        profiles.append(entry)
        if profiles.count > 1000 { profiles.removeFirst(profiles.count - 1000) }
        detectHotspots()
    }

    private func detectHotspots() {
        var byOperation: [String: (total: Double, count: Int)] = [:]
        for profile in profiles.suffix(100) {
            let key = "\(profile.agentId):\(profile.operation)"
            byOperation[key, default: (0, 0)].total += profile.duration
            byOperation[key, default: (0, 0)].count += 1
        }

        hotspots = byOperation.map { (key, value) in
            let parts = key.split(separator: ":")
            let agentId = String(parts.first ?? "")
            let operation = String(parts.last ?? "")
            return Hotspot(
                agentId: agentId,
                operation: operation,
                avgDuration: value.total / Double(value.count),
                totalDuration: value.total,
                count: value.count
            )
        }.sorted { $0.avgDuration > $1.avgDuration }
    }

    public var summary: String {
        "Profiler: \(profiles.count) profiles, \(hotspots.count) hotspots"
    }
}

public struct ProfileEntry: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let operation: String
    public let duration: Double
    public let metadata: [String: String]

    public init(agentId: String, operation: String, duration: Double, metadata: [String: String]) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.operation = operation
        self.duration = duration
        self.metadata = metadata
    }
}

public struct Hotspot: Identifiable, Codable {
    public let id: String
    public let agentId: String
    public let operation: String
    public let avgDuration: Double
    public let totalDuration: Double
    public let count: Int

    public init(agentId: String, operation: String, avgDuration: Double, totalDuration: Double, count: Int) {
        self.id = "\(agentId):\(operation)"
        self.agentId = agentId
        self.operation = operation
        self.avgDuration = avgDuration
        self.totalDuration = totalDuration
        self.count = count
    }

    public var summary: String {
        "▲ \(agentId):\(operation) avg \(String(format: "%.2fs", avgDuration)) x\(count)"
    }
}
