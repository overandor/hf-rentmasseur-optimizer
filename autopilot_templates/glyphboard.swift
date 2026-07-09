//
//  GlyphBoard.swift — Unicode glyph picker with custom collections
//

import SwiftUI
import AppKit

@main
struct GlyphBoardApp: App {
    var body: some Scene {
        MenuBarExtra("GlyphBoard", systemImage: "speedometer") {
            GlyphBoardView()
        }
        .menuBarExtraStyle(.window)
    }
}

struct GlyphCategory: Identifiable {
    let id = UUID()
    let name: String
    let icon: String
    let glyphs: [String]
}

let CATEGORIES: [GlyphCategory] = [
    GlyphCategory(name: "Arrows", icon: "arrow.up.right", glyphs: ["↑","↓","←","→","↖","↗","↙","↘","↕","↔","⇧","⇩","⇦","⇨","⬆","⬇","⬅","➡","⟁","⟡"]),
    GlyphCategory(name: "Math", icon: "function", glyphs: ["∑","∏","∫","∂","√","∞","≈","≠","≤","≥","±","×","÷","π","λ","μ","σ","Ω","∇","∝"]),
    GlyphCategory(name: "Symbols", icon: "star", glyphs: ["◉","◇","◆","▲","▼","◈","⟡","⌁","⧉","⧖","◍","◌","⟁","✦","✧","★","☆","♦","♣","♥"]),
    GlyphCategory(name: "Tech", icon: "keyboard", glyphs: ["⌘","⌥","⌃","⇧","⏎","⎋","⌫","⌦","⇥","⇤","␣","⌁","⎈","⌖","⌗","⎉","⎊","⌬"]),
    GlyphCategory(name: "Currency", icon: "dollarsign.circle", glyphs: ["$","€","£","¥","₿","¢","₩","₹","₽","₴","₸","₡","₦","₱","₲","₪","₫","₭","₮","₯"]),
    GlyphCategory(name: "Greek", icon: "abc", glyphs: ["α","β","γ","δ","ε","ζ","η","θ","ι","κ","λ","μ","ν","ξ","π","ρ","σ","τ","φ","ψ","ω","Σ","Π","Δ","Ω"]),
]

class GlyphStore: ObservableObject {
    @Published var searchText = ""
    @Published var selectedCategory: GlyphCategory? = nil
    @Published var recents: [String] = []
    @Published var favorites: [String] = []

    init() {
        recents = UserDefaults.standard.stringArray(forKey: "glyph_recents") ?? []
        favorites = UserDefaults.standard.stringArray(forKey: "glyph_favorites") ?? []
    }

    var filteredGlyphs: [String] {
        if !searchText.isEmpty {
            return CATEGORIES.flatMap { $0.glyphs }.filter { $0.contains(searchText) || searchText.contains($0) }
        }
        return selectedCategory?.glyphs ?? CATEGORIES.flatMap { $0.glyphs }
    }

    func copyGlyph(_ g: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(g, forType: .string)
        recents.removeAll { $0 == g }
        recents.insert(g, at: 0)
        if recents.count > 20 { recents = Array(recents.prefix(20)) }
        UserDefaults.standard.set(recents, forKey: "glyph_recents")
    }

    func toggleFavorite(_ g: String) {
        if favorites.contains(g) {
            favorites.removeAll { $0 == g }
        } else {
            favorites.append(g)
        }
        UserDefaults.standard.set(favorites, forKey: "glyph_favorites")
    }
}

struct GlyphBoardView: View {
    @StateObject var store = GlyphStore()

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Image(systemName: "speedometer").foregroundColor(.orange)
                Text("GlyphBoard").font(.system(size: 13, weight: .bold, design: .monospaced))
                Spacer()
                Text("\(store.filteredGlyphs.count) glyphs").font(.system(size: 9, design: .monospaced)).foregroundColor(.gray)
            }

            TextField("Search glyphs...", text: $store.searchText)
                .textFieldStyle(.roundedBorder)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    Button("All") { store.selectedCategory = nil }
                        .buttonStyle(.bordered).font(.system(size: 9))
                    ForEach(CATEGORIES) { cat in
                        Button(cat.name) { store.selectedCategory = cat }
                            .buttonStyle(.bordered).font(.system(size: 9))
                    }
                }}
            }

            if !store.recents.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Recent").font(.system(size: 9, weight: .bold, design: .monospaced)).foregroundColor(.gray)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            ForEach(store.recents.prefix(10), id: \.self) { g in
                                Text(g).font(.system(size: 16)).onTapGesture { store.copyGlyph(g) }
                            }
                        }
                    }
                }
            }

            ScrollView {
                LazyVGrid(columns: Array(repeating: GridItem(.fixed(28)), count: 8), spacing: 4) {
                    ForEach(store.filteredGlyphs, id: \.self) { g in
                        Text(g)
                            .font(.system(size: 18))
                            .frame(width: 28, height: 28)
                            .background(store.favorites.contains(g) ? Color.orange.opacity(0.2) : Color.clear)
                            .cornerRadius(6)
                            .onTapGesture { store.copyGlyph(g) }
                            .onLongPressGesture { store.toggleFavorite(g) }
                    }
                }
            }

            Text("Click to copy • Long-press to favorite")
                .font(.system(size: 8, design: .monospaced)).foregroundColor(.gray)
        }
        .padding(12)
        .frame(width: 340, height: 460)
    }
}
