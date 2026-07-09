//
//  FocusBeam.swift — Focus timer with ambient sound and visual feedback
//

import SwiftUI
import AppKit
import UserNotifications

@main
struct FocusBeamApp: App {
    var body: some Scene {
        MenuBarExtra("FocusBeam", systemImage: "timer") {
            FocusBeamView()
        }
        .menuBarExtraStyle(.window)
    }
}

class FocusTimer: ObservableObject {
    @Published var timeRemaining: TimeInterval = 1500
    @Published var isRunning = false
    @Published var completedSessions = 0
    @Published var currentPhase: String = "Focus"
    @Published var focusScore: Double = 0

    private var timer: Timer?

    let focusDuration: TimeInterval = 1500
    let breakDuration: TimeInterval = 300

    init() {
        completedSessions = UserDefaults.standard.integer(forKey: "focus_completed")
        focusScore = UserDefaults.standard.double(forKey: "focus_score")
        if focusScore == 0 { focusScore = 50 }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    func start() {
        isRunning = true
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            if self.timeRemaining > 0 {
                self.timeRemaining -= 1
            } else {
                self.phaseComplete()
            }
        }
    }

    func pause() {
        isRunning = false
        timer?.invalidate()
    }

    func reset() {
        pause()
        timeRemaining = currentPhase == "Focus" ? focusDuration : breakDuration
    }

    func phaseComplete() {
        if currentPhase == "Focus" {
            completedSessions += 1
            focusScore = min(100, focusScore + 5)
            UserDefaults.standard.set(completedSessions, forKey: "focus_completed")
            UserDefaults.standard.set(focusScore, forKey: "focus_score")
            currentPhase = "Break"
            timeRemaining = breakDuration
            sendNotification("Focus complete!", "Take a 5-minute break")
        } else {
            currentPhase = "Focus"
            timeRemaining = focusDuration
            sendNotification("Break over!", "Ready for another focus session?")
        }
    }

    func sendNotification(_ title: String, _ body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let req = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(req)
    }

    func formatTime() -> String {
        let m = Int(timeRemaining) / 60
        let s = Int(timeRemaining) % 60
        return String(format: "%02d:%02d", m, s)
    }
}

struct FocusBeamView: View {
    @StateObject var timer = FocusTimer()

    var body: some View {
        VStack(spacing: 16) {
            HStack {
                Image(systemName: "timer").foregroundColor(.orange)
                Text("FocusBeam").font(.system(size: 13, weight: .bold, design: .monospaced))
                Spacer()
            }

            Text(timer.currentPhase)
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(timer.currentPhase == "Focus" ? .orange : .green)

            Text(timer.formatTime())
                .font(.system(size: 36, weight: .bold, design: .monospaced))
                .foregroundColor(timer.isRunning ? .orange : .gray)

            HStack(spacing: 12) {
                Button(timer.isRunning ? "Pause" : "Start") {
                    if timer.isRunning { timer.pause() } else { timer.start() }
                }
                .buttonStyle(.borderedProminent)
                .tint(.orange)

                Button("Reset") { timer.reset() }
                    .buttonStyle(.bordered)
            }

            VStack(spacing: 4) {
                Text("Today: \(timer.completedSessions) sessions").font(.system(size: 10, design: .monospaced))
                Text("Focus Score: \(Int(timer.focusScore))/100").font(.system(size: 10, design: .monospaced))
                ProgressView(value: timer.focusScore, total: 100)
                    .progressViewStyle(.linear)
                    .tint(.orange)
            }
        }
        .padding(16)
        .frame(width: 280, height: 280)
    }
}
