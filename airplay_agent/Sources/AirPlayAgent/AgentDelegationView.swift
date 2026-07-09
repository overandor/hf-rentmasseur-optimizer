import SwiftUI

struct AgentDelegationView: View {
    @ObservedObject var model: AgentModel

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            taskInput
            Divider()
            agentList
            Divider()
            taskLog
        }
        .background(Color(NSColor.windowBackgroundColor))
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Agent Delegation")
                    .font(.headline)
                    .fontWeight(.bold)
                Text("Delegate tasks to LLM agents")
                    .font(.caption)
                    .foregroundColor(.secondary)
                if model.isStreaming {
                    HStack(spacing: 4) {
                        ProgressView()
                            .scaleEffect(0.6)
                            .frame(width: 10, height: 10)
                        Text("Streaming...")
                            .font(.system(size: 10))
                            .foregroundColor(.orange)
                    }
                }
            }
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    private var taskInput: some View {
        HStack(spacing: 8) {
            TextField("Enter task for agent...", text: $model.taskInput)
                .textFieldStyle(.roundedBorder)
                .onSubmit { model.delegateTask() }
                .disabled(model.isStreaming)

            if model.isStreaming {
                Button(action: { model.cancelCurrentTask() }) {
                    Image(systemName: "stop.fill")
                        .foregroundColor(.white)
                        .frame(width: 32, height: 24)
                }
                .buttonStyle(.borderedProminent)
                .tint(.red)
                .help("Cancel current task")
            } else {
                Button(action: { model.delegateTask() }) {
                    Image(systemName: "paperplane.fill")
                        .foregroundColor(.white)
                        .frame(width: 32, height: 24)
                }
                .buttonStyle(.borderedProminent)
                .disabled(model.taskInput.trimmingCharacters(in: .whitespaces).isEmpty || !model.isConnected)
                .help(model.isConnected ? "Send task" : "Connect to Ollama first")
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    private var agentList: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Agents")
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundColor(.secondary)
                .padding(.horizontal, 16)
                .padding(.top, 8)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(model.agents, id: \.self) { agent in
                        HStack(spacing: 4) {
                            Image(systemName: "cpu")
                                .font(.caption)
                            Text(agent)
                                .font(.caption)
                                .fontWeight(.medium)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Color.accentColor.opacity(0.15))
                        .cornerRadius(6)
                    }
                }
                .padding(.horizontal, 16)
            }
        }
        .padding(.bottom, 8)
    }

    private var taskLog: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Task Log")
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundColor(.secondary)
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 4)

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 6) {
                    ForEach(model.tasks) { task in
                        taskRow(task)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 16)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func taskRow(_ task: AgentTask) -> some View {
        Button(action: { model.selectTask(task) }) {
            HStack(spacing: 8) {
                Circle()
                    .fill(statusColor(task.status))
                    .frame(width: 8, height: 8)

                VStack(alignment: .leading, spacing: 2) {
                    Text(task.title)
                        .font(.caption)
                        .lineLimit(2)
                        .foregroundColor(.primary)
                    HStack(spacing: 4) {
                        Text(task.assignedTo)
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                        Text("•")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                        Text(task.timestamp, style: .time)
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                }
                Spacer()
            }
            .padding(.vertical, 4)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func statusColor(_ status: AgentStatus) -> Color {
        switch status {
        case .idle: return .gray
        case .working: return .orange
        case .done: return .green
        case .error: return .red
        }
    }
}
