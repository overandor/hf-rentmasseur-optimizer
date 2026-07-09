import SwiftUI

struct ArenaStageView: View {
    @Binding var agents: [ArenaAgent]
    @Binding var round: Int
    @Binding var isRunning: Bool
    @Binding var formFeedback: String
    @Binding var iphoneConnected: Bool

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 20) {
                header
                panels
                Spacer()
                footer
            }
            .padding(30)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var header: some View {
        VStack(spacing: 8) {
            HStack(spacing: 12) {
                Image(systemName: "figure.strengthtraining.traditional")
                    .font(.system(size: 32))
                    .foregroundColor(.orange)
                Text("FitArena")
                    .font(.system(size: 36, weight: .bold))
                    .foregroundColor(.white)
                if isRunning {
                    ProgressView()
                        .scaleEffect(0.8)
                        .frame(width: 20, height: 20)
                }
            }
            HStack(spacing: 16) {
                Text("Round \(round)")
                    .font(.system(size: 18))
                    .foregroundColor(.white.opacity(0.6))
                if iphoneConnected {
                    HStack(spacing: 4) {
                        Image(systemName: "iphone")
                            .font(.system(size: 14))
                        Text("iPhone Connected")
                            .font(.system(size: 14))
                    }
                    .foregroundColor(.green)
                }
            }
            RoundedRectangle(cornerRadius: 2)
                .fill(Color.orange)
                .frame(width: 80, height: 3)
        }
        .padding(.top, 10)
    }

    private var panels: some View {
        HStack(spacing: 16) {
            ForEach(agents.indices, id: \.self) { i in
                let agent = agents[i]
                let agentColor = stageColor(agent.color)

                VStack(spacing: 12) {
                    HStack {
                        Circle()
                            .fill(agent.isStreaming ? Color.orange : agentColor)
                            .frame(width: 10, height: 10)
                        Text(agent.name)
                            .font(.system(size: 20, weight: .bold))
                            .foregroundColor(agentColor)
                        Spacer()
                        Text("★ \(agent.score)")
                            .font(.system(size: 16))
                            .foregroundColor(.white.opacity(0.5))
                    }

                    ScrollView {
                        Text(agent.output.isEmpty ? "..." : agent.output)
                            .font(.system(size: 16))
                            .foregroundColor(.white.opacity(0.85))
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .multilineTextAlignment(.leading)
                            .lineSpacing(4)
                    }
                    .frame(maxHeight: .infinity)
                }
                .padding(16)
                .background(agentColor.opacity(0.08))
                .cornerRadius(12)
            }
        }
        .frame(maxHeight: .infinity)
    }

    private var footer: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(iphoneConnected ? Color.green : Color.red)
                .frame(width: 10, height: 10)
            Text(formFeedback)
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.5))
            Spacer()
            Text("FitArena")
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.3))
        }
        .padding(.bottom, 10)
    }

    private func stageColor(_ name: String) -> Color {
        switch name {
        case "blue": return .blue
        case "orange": return .orange
        case "green": return .green
        default: return .gray
        }
    }
}
