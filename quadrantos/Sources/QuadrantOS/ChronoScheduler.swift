//
//  ChronoScheduler.swift
//  ChronoSwarm
//
//  The scheduler wakes panes by time, event, file change, or task priority.
//  You are not opening windows reactively. You are planting future executable surfaces.
//
//  Morning:  ClientPulse pane wakes, KPI pane collects, Builder checks repo
//  Afternoon: Finance pane appears, Dossier pane generates, Reality Wall prepares
//  Night:    Cleanup pane runs, Receipt pane closes the day, Tomorrow's schedule evolves
//

import Foundation
import Combine

public enum WakeTrigger: String, Codable {
    case timeOfDay    = "time_of_day"
    case fileChange   = "file_change"
    case event        = "event"
    case attention    = "attention"
    case taskPriority = "task_priority"
    case manual       = "manual"
}

public struct ScheduledWake: Identifiable, Codable {
    public let id: String
    public let paneId: String
    public let trigger: WakeTrigger
    public let scheduledTime: Date
    public let reason: String
    public var fired: Bool

    public init(paneId: String, trigger: WakeTrigger, scheduledTime: Date, reason: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.paneId = paneId
        self.trigger = trigger
        self.scheduledTime = scheduledTime
        self.reason = reason
        self.fired = false
    }
}

public final class ChronoScheduler: ObservableObject {
    @Published public private(set) var schedule: [ScheduledWake] = []
    @Published public private(set) var firedWakes: [ScheduledWake] = []
    @Published public private(set) var isRunning: Bool = false
    @Published public var tickCount: Int = 0

    public var panes: [ChronoPane] = []
    private var timer: Timer?
    private var governor: GeneticLayoutGovernor?

    public init() {}

    public func configure(panes: [ChronoPane], governor: GeneticLayoutGovernor) {
        self.panes = panes
        self.governor = governor
        rebuildSchedule()
    }

    // MARK: - Schedule Building

    public func rebuildSchedule() {
        schedule.removeAll()
        for pane in panes {
            let wake = ScheduledWake(
                paneId: pane.id,
                trigger: .timeOfDay,
                scheduledTime: pane.genome.wakeTime,
                reason: "Genetic schedule: \(pane.name) wakes at \(pane.genome.wakeHour):\(String(format: "%02d", pane.genome.wakeMinute))"
            )
            schedule.append(wake)

            // Co-operating panes wake shortly after
            for coopId in pane.genome.coOperatesWith {
                if let coopPane = panes.first(where: { $0.id == coopId }) {
                    let coopWake = ScheduledWake(
                        paneId: coopPane.id,
                        trigger: .taskPriority,
                        scheduledTime: pane.genome.wakeTime.addingTimeInterval(120),
                        reason: "Co-operates with \(pane.name)"
                    )
                    schedule.append(coopWake)
                }
            }
        }
        schedule.sort { $0.scheduledTime < $1.scheduledTime }
    }

    // MARK: - Tick

    public func tick() {
        tickCount += 1
        let now = Date()

        for i in schedule.indices where !schedule[i].fired {
            if schedule[i].scheduledTime <= now {
                schedule[i].fired = true
                let wake = schedule[i]
                firedWakes.append(wake)
                if firedWakes.count > 100 { firedWakes.removeFirst() }

                if let pane = panes.first(where: { $0.id == wake.paneId }) {
                    pane.lifecycle.wake(reason: wake.reason)
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                        pane.lifecycle.activate(reason: "warmed up")
                    }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
                        pane.lifecycle.work(reason: "task started")
                    }
                }
            }
        }

        // Check for panes that should retire
        for pane in panes where pane.isActive {
            if now >= pane.genome.retireTime {
                pane.lifecycle.prove(reason: "generating receipt before retirement")
                DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
                    pane.lifecycle.cool(reason: "work complete")
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                        pane.lifecycle.sleep(reason: "retired on schedule")
                    }
                }
            }
        }

        // Reborn archived panes that have a new schedule
        for pane in panes where pane.lifecycle.currentPhase == .archived {
            let nextWake = schedule.first { $0.paneId == pane.id && !$0.fired }
            if let wake = nextWake, wake.scheduledTime.timeIntervalSince(now) < 3600 {
                pane.lifecycle.reborn(reason: "scheduled return")
            }
        }
    }

    // MARK: - Start/Stop

    public func start() {
        guard !isRunning else { return }
        isRunning = true
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.tick()
        }
    }

    public func stop() {
        isRunning = false
        timer?.invalidate()
        timer = nil
    }

    // MARK: - Manual Wake

    public func manualWake(paneId: String, reason: String = "manual") {
        guard let pane = panes.first(where: { $0.id == paneId }) else { return }
        pane.lifecycle.wake(reason: reason)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            pane.lifecycle.activate(reason: "manual activation")
        }
        let wake = ScheduledWake(paneId: paneId, trigger: .manual, scheduledTime: Date(), reason: reason)
        firedWakes.append(wake)
    }

    public func manualSleep(paneId: String) {
        guard let pane = panes.first(where: { $0.id == paneId }) else { return }
        pane.lifecycle.cool(reason: "manual sleep")
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            pane.lifecycle.sleep(reason: "manual retirement")
        }
    }

    // MARK: - Hourly Density

    public var hourlySpawnDensity: [Int] {
        var density = Array(repeating: 0, count: 24)
        for wake in schedule where !wake.fired {
            let hour = Calendar.current.component(.hour, from: wake.scheduledTime)
            density[hour] += 1
        }
        return density
    }

    public var nextWakes: [ScheduledWake] {
        schedule.filter { !$0.fired }.prefix(5).map { $0 }
    }

    public var activePaneCount: Int {
        panes.filter { $0.isActive }.count
    }

    public var summaryLine: String {
        "\(schedule.count) scheduled · \(firedWakes.count) fired · \(activePaneCount) active · tick #\(tickCount)"
    }
}
