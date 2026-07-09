import SwiftUI

struct AgentStageView: View {
    @Binding var agentName: String
    @Binding var output: String
    @Binding var isStreaming: Bool
    @Binding var isConnected: Bool

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 24) {
                header
                content
                Spacer()
                footer
            }
            .padding(40)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var header: some View {
        VStack(spacing: 8) {
            HStack(spacing: 12) {
                Image(systemName: "cpu")
                    .font(.system(size: 32))
                    .foregroundColor(.accentColor)
                Text(agentName.isEmpty ? "No Agent Active" : agentName)
                    .font(.system(size: 36, weight: .bold))
                    .foregroundColor(.white)
                if isStreaming {
                    ProgressView()
                        .scaleEffect(0.8)
                        .frame(width: 20, height: 20)
                }
            }
            RoundedRectangle(cornerRadius: 2)
                .fill(Color.accentColor)
                .frame(width: 80, height: 3)
        }
        .padding(.top, 20)
    }

    private var content: some View {
        ScrollView {
            Text(output)
                .font(.system(size: 24, weight: .medium))
                .foregroundColor(.white.opacity(0.9))
                .frame(maxWidth: .infinity, alignment: .leading)
                .multilineTextAlignment(.leading)
                .lineSpacing(6)
        }
        .frame(maxHeight: .infinity)
    }

    private var footer: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(isConnected ? Color.green : Color.red)
                .frame(width: 10, height: 10)
            Text(isConnected ? "Live Agent Output" : "Disconnected")
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.5))
            Spacer()
            if isStreaming {
                Text("Streaming")
                    .font(.system(size: 14))
                    .foregroundColor(.orange.opacity(0.7))
            } else {
                Text("AirPlay Agent Stage")
                    .font(.system(size: 14))
                    .foregroundColor(.white.opacity(0.5))
            }
        }
        .padding(.bottom, 16)
    }
}
