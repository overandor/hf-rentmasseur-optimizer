import SwiftUI
import UniformTypeIdentifiers

struct WallWindowView: View {
    @ObservedObject var controller: WallController
    @State private var showFileDrop = false
    @State private var questionText = ""
    @State private var showQuestionBar = false

    var body: some View {
        ZStack {
            Color(red: 0.02, green: 0.02, blue: 0.03).ignoresSafeArea()

            VStack(spacing: 0) {
                wallHeader
                cardDisplay
                wallFooter
            }

            if showFileDrop {
                fileDropOverlay
            }

            if showQuestionBar {
                questionBar
            }
        }
        .onAppear {
            controller.loadReceiptCards()
        }
        .onKeyPress(.leftArrow) { controller.prevCard(); return .handled }
        .onKeyPress(.rightArrow) { controller.nextCard(); return .handled }
        .onKeyPress(.space) { showQuestionBar.toggle(); return .handled }
        .onKeyPress(.return) {
            if showQuestionBar && !questionText.isEmpty {
                Task { await controller.askQuestion(questionText) }
                questionText = ""
                showQuestionBar = false
            }
            return .handled
        }
    }

    private var wallHeader: some View {
        HStack(spacing: 12) {
            Text("◈")
                .font(.system(size: 28, design: .monospaced))
                .foregroundColor(.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text(controller.wallTitle)
                    .font(.system(size: 22, weight: .bold, design: .monospaced))
                    .foregroundColor(.orange)
                Text("local LLM · private · room-scale")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.gray)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text("◉ \(controller.connectionState)")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.green)
                Text("\(controller.cards.count) cards")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.gray)
            }
        }
        .padding(.horizontal, 40)
        .padding(.vertical, 20)
    }

    @ViewBuilder
    private var cardDisplay: some View {
        Spacer()
        if controller.isProcessing {
            VStack(spacing: 16) {
                ProgressView()
                    .scaleEffect(1.5)
                Text("LLM processing...")
                    .font(.system(size: 16, design: .monospaced))
                    .foregroundColor(.orange)
            }
        } else if let card = controller.currentCard {
            WallCardView(card: card, index: controller.currentCardIndex, total: controller.cards.count)
        } else if controller.cards.isEmpty {
            VStack(spacing: 20) {
                Text("◌")
                    .font(.system(size: 48, design: .monospaced))
                    .foregroundColor(.gray.opacity(0.5))
                Text("Drop files here or press SPACE to ask")
                    .font(.system(size: 18, design: .monospaced))
                    .foregroundColor(.gray)
                Text("← → to navigate · SPACE for question · drop PDF/txt/code for summary")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.gray.opacity(0.6))
            }
        }
        Spacer()
    }

    private var wallFooter: some View {
        HStack(spacing: 16) {
            Text("← →")
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(.gray)
            Text("navigate")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.gray)
            Text("SPACE")
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(.gray)
            Text("ask LLM")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.gray)
            Text("⌘+drop")
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(.gray)
            Text("summarize file")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.gray)
            Spacer()
            if let card = controller.currentCard {
                Text("◆ \(card.hash)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.orange.opacity(0.7))
            }
        }
        .padding(.horizontal, 40)
        .padding(.vertical, 16)
    }

    private var fileDropOverlay: some View {
        RoundedRectangle(cornerRadius: 20)
            .stroke(Color.orange, lineWidth: 3)
            .background(Color.orange.opacity(0.05))
            .overlay(
                VStack(spacing: 16) {
                    Image(systemName: "arrow.down.doc")
                        .font(.system(size: 48))
                        .foregroundColor(.orange)
                    Text("Drop files to summarize")
                        .font(.system(size: 20, weight: .bold, design: .monospaced))
                        .foregroundColor(.orange)
                    Text("PDF · TXT · MD · Code · CSV · JSON")
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundColor(.gray)
                }
            )
            .padding(40)
            .onDrop(of: [.fileURL], isTargeted: nil) { providers in
                handleDrop(providers: providers)
                showFileDrop = false
                return true
            }
            .onHover { hovering in
                showFileDrop = hovering
            }
    }

    private var questionBar: some View {
        VStack {
            Spacer()
            HStack {
                Image(systemName: "brain")
                    .foregroundColor(.orange)
                TextField("Ask the room brain...", text: $questionText)
                    .font(.system(size: 16, design: .monospaced))
                    .textFieldStyle(.plain)
                    .foregroundColor(.white)
                if !questionText.isEmpty {
                    Button("Send") {
                        Task { await controller.askQuestion(questionText) }
                        questionText = ""
                        showQuestionBar = false
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(.orange)
                }
            }
            .padding(16)
            .background(Color.white.opacity(0.08))
            .cornerRadius(8)
            .padding(40)
        }
    }

    private func handleDrop(providers: [NSItemProvider]) {
        for provider in providers {
            provider.loadItem(forTypeIdentifier: "public.file-url", options: nil) { item, _ in
                guard let data = item as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) else { return }
                Task { await controller.summarizeFile(url: url) }
            }
        }
    }
}

struct WallCardView: View {
    let card: WallCard
    let index: Int
    let total: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            HStack(spacing: 12) {
                Text(card.glyph)
                    .font(.system(size: 36, design: .monospaced))
                    .foregroundColor(.orange)
                Text(card.title)
                    .font(.system(size: 32, weight: .bold, design: .monospaced))
                    .foregroundColor(.white)
                    .lineLimit(2)
                Spacer()
            }

            Text(card.body)
                .font(.system(size: 20, design: .monospaced))
                .foregroundColor(.white.opacity(0.85))
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)

            HStack {
                Text("◆ \(card.hash)")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.orange.opacity(0.6))
                Spacer()
                Text("\(index + 1) / \(total)")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.gray)
            }
        }
        .padding(60)
        .frame(maxWidth: 900)
        .transition(.opacity.combined(with: .move(edge: .trailing)))
        .animation(.easeInOut(duration: 0.3), value: index)
    }
}
