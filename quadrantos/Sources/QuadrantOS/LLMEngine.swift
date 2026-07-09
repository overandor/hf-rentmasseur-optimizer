//
//  LLMEngine.swift
//  CursorAgent OS
//
//  Custom LLM/GPT engine built from scratch.
//  - BPE tokenizer
//  - Multi-head self-attention
//  - Transformer decoder layers
//  - Positional encoding
//  - Text generation (greedy, top-k, nucleus sampling)
//  - Token embeddings
//  - Layer normalization
//  - Feed-forward networks
//  - KV cache for efficient generation
//  - Model serialization
//  - Training loop (gradient-free, heuristics-based)
//

import Foundation
import Combine

// MARK: - Token

public struct Token: Identifiable, Codable, Hashable {
    public let id: Int
    public let text: String
    public let type: TokenType

    public enum TokenType: String, Codable, CaseIterable {
        case word       = "word"
        case subword    = "subword"
        case punctuation = "punctuation"
        case number     = "number"
        case whitespace = "whitespace"
        case special    = "special"
        case unknown    = "unknown"

        public var glyph: String {
            switch self {
            case .word:        return "W"
            case .subword:     return "s"
            case .punctuation: return "P"
            case .number:      return "N"
            case .whitespace:  return " "
            case .special:     return "★"
            case .unknown:     return "?"
            }
        }
    }

    public init(id: Int, text: String, type: TokenType) {
        self.id = id
        self.text = text
        self.type = type
    }
}

// MARK: - Special Tokens

public enum SpecialToken: Int, Codable, CaseIterable {
    case pad       = 0
    case bos       = 1
    case eos       = 2
    case unk       = 3
    case mask      = 4
    case sep       = 5
    case cls       = 6
    case system    = 7
    case user      = 8
    case assistant = 9
    case context   = 10
    case memory    = 11
    case receipt   = 12
    case agent     = 13
    case cursor    = 14
    case workspace = 15

    public var text: String {
        switch self {
        case .pad:       return "<pad>"
        case .bos:       return "<bos>"
        case .eos:       return "<eos>"
        case .unk:       return "<unk>"
        case .mask:      return "<mask>"
        case .sep:       return "<sep>"
        case .cls:       return "<cls>"
        case .system:    return "<system>"
        case .user:      return "<user>"
        case .assistant: return "<assistant>"
        case .context:   return "<context>"
        case .memory:    return "<memory>"
        case .receipt:   return "<receipt>"
        case .agent:     return "<agent>"
        case .cursor:    return "<cursor>"
        case .workspace: return "<workspace>"
        }
    }

    public var glyph: String {
        switch self {
        case .pad:       return "◌"
        case .bos:       return "▶"
        case .eos:       return "⏹"
        case .unk:       return "?"
        case .mask:      return "◍"
        case .sep:       return "⇄"
        case .cls:       return "◆"
        case .system:    return "⚙"
        case .user:      return "👤"
        case .assistant: return "🤖"
        case .context:   return "◇"
        case .memory:    return "🧠"
        case .receipt:   return "🧾"
        case .agent:     return "◉"
        case .cursor:    return "⌁"
        case .workspace: return "📁"
        }
    }
}

// MARK: - BPE Merge Pair

public struct MergePair: Codable, Hashable {
    public let left: String
    public let right: String

    public init(_ left: String, _ right: String) {
        self.left = left
        self.right = right
    }
}

// MARK: - BPE Tokenizer

public final class BPETokenizer: ObservableObject, Codable {
    public var vocab: [String: Int]
    public var reverseVocab: [Int: String]
    public var merges: [MergePair]
    public var vocabSize: Int
    public var maxTokenLength: Int

    public init(vocabSize: Int = 32000) {
        self.vocab = [:]
        self.reverseVocab = [:]
        self.merges = []
        self.vocabSize = vocabSize
        self.maxTokenLength = 20

        for token in SpecialToken.allCases {
            vocab[token.text] = token.rawValue
            reverseVocab[token.rawValue] = token.text
        }

        let baseChars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~\n\t"
        var nextId = 16
        for ch in baseChars {
            let s = String(ch)
            if vocab[s] == nil {
                vocab[s] = nextId
                reverseVocab[nextId] = s
                nextId += 1
            }
        }
    }

    // MARK: - Encode

    public func encode(_ text: String) -> [Int] {
        var tokens: [Int] = [SpecialToken.bos.rawValue]
        let words = preTokenize(text)

        for word in words {
            let subTokens = tokenizeWord(word)
            tokens.append(contentsOf: subTokens)
        }

        tokens.append(SpecialToken.eos.rawValue)
        return tokens
    }

    public func encodeWithoutSpecial(_ text: String) -> [Int] {
        let words = preTokenize(text)
        var tokens: [Int] = []
        for word in words {
            tokens.append(contentsOf: tokenizeWord(word))
        }
        return tokens
    }

    private func preTokenize(_ text: String) -> [String] {
        var words: [String] = []
        var current = ""

        for ch in text {
            if ch.isLetter || ch.isNumber {
                current.append(ch)
            } else {
                if !current.isEmpty {
                    words.append(current)
                    current = ""
                }
                words.append(String(ch))
            }
        }

        if !current.isEmpty { words.append(current) }
        return words
    }

    private func tokenizeWord(_ word: String) -> [Int] {
        if let id = vocab[word] { return [id] }

        var chars = word.map { String($0) }
        var charIds: [Int] = []
        for c in chars {
            if let id = vocab[c] {
                charIds.append(id)
            } else {
                charIds.append(SpecialToken.unk.rawValue)
            }
        }

        while charIds.count > 1 {
            var bestMerge: (Int, Int)? = nil
            var bestRank = Int.max

            for i in 0..<(charIds.count - 1) {
                let left = reverseVocab[charIds[i]] ?? ""
                let right = reverseVocab[charIds[i + 1]] ?? ""
                let combined = left + right

                if let id = vocab[combined] {
                    let mergeRank = merges.firstIndex { $0.left == left && $0.right == right } ?? Int.max
                    if mergeRank < bestRank {
                        bestRank = mergeRank
                        bestMerge = (i, id)
                    }
                }
            }

            guard let (pos, newId) = bestMerge else { break }
            charIds[pos] = newId
            charIds.remove(at: pos + 1)
        }

        return charIds
    }

    // MARK: - Decode

    public func decode(_ tokenIds: [Int]) -> String {
        var result = ""
        for id in tokenIds {
            if id == SpecialToken.bos.rawValue || id == SpecialToken.pad.rawValue {
                continue
            }
            if id == SpecialToken.eos.rawValue {
                break
            }
            if let text = reverseVocab[id] {
                if !text.hasPrefix("<") || !text.hasSuffix(">") {
                    result += text
                }
            }
        }
        return result
    }

    // MARK: - Train (Simulated)

    public func train(on corpus: String, targetMerges: Int = 1000) {
        let words = preTokenize(corpus)
        var wordFreqs: [String: Int] = [:]
        for word in words {
            wordFreqs[word, default: 0] += 1
        }

        for _ in 0..<targetMerges {
            var pairFreqs: [String: (String, String, Int)] = [:]

            for (word, freq) in wordFreqs {
                let chars = word.map { String($0) }
                for i in 0..<(chars.count - 1) {
                    let key = "\(chars[i])\(chars[i + 1])"
                    pairFreqs[key, default: (chars[i], chars[i + 1], 0)].2 += freq
                }
            }

            guard let bestPair = pairFreqs.max(by: { $0.value.2 < $1.value.2 }) else { break }
            let merged = bestPair.value.0 + bestPair.value.1

            if vocab[merged] != nil { continue }

            let newId = vocab.count
            vocab[merged] = newId
            reverseVocab[newId] = merged
            merges.append(MergePair(bestPair.value.0, bestPair.value.1))

            var newWordFreqs: [String: Int] = [:]
            for (word, freq) in wordFreqs {
                let merged2 = word.replacingOccurrences(of: bestPair.value.0 + bestPair.value.1,
                                                        with: merged)
                newWordFreqs[merged2, default: 0] += freq
            }
            wordFreqs = newWordFreqs

            if vocab.count >= vocabSize { break }
        }
    }

    // MARK: - Stats

    public var stats: String {
        "Tokenizer: \(vocab.count) tokens, \(merges.count) merges"
    }

    // MARK: - Codable

    enum CodingKeys: CodingKey { case vocab, merges, vocabSize, maxTokenLength }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(vocab, forKey: .vocab)
        try c.encode(merges, forKey: .merges)
        try c.encode(vocabSize, forKey: .vocabSize)
        try c.encode(maxTokenLength, forKey: .maxTokenLength)
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.vocab = try c.decode([String: Int].self, forKey: .vocab)
        self.merges = try c.decode([MergePair].self, forKey: .merges)
        self.vocabSize = try c.decode(Int.self, forKey: .vocabSize)
        self.maxTokenLength = try c.decode(Int.self, forKey: .maxTokenLength)
        self.reverseVocab = Dictionary(uniqueKeysWithValues: vocab.map { ($0.value, $0.key) })
    }
}

// MARK: - Tensor

public struct Tensor: Codable {
    public var shape: [Int]
    public var data: [Double]

    public init(shape: [Int], data: [Double]) {
        self.shape = shape
        self.data = data
    }

    public init(shape: [Int], fill: Double = 0) {
        self.shape = shape
        self.data = Array(repeating: fill, count: shape.reduce(1, *))
    }

    public var size: Int { shape.reduce(1, *) }

    public subscript(indices: [Int]) -> Double {
        get {
            var idx = 0
            var stride = 1
            for i in (0..<indices.count).reversed() {
                idx += indices[i] * stride
                stride *= shape[i]
            }
            return data[idx]
        }
        set {
            var idx = 0
            var stride = 1
            for i in (0..<indices.count).reversed() {
                idx += indices[i] * stride
                stride *= shape[i]
            }
            data[idx] = newValue
        }
    }

    public func reshaped(to shape: [Int]) -> Tensor {
        return Tensor(shape: shape, data: data)
    }

    public static func + (lhs: Tensor, rhs: Tensor) -> Tensor {
        return Tensor(shape: lhs.shape, data: zip(lhs.data, rhs.data).map { $0 + $1 })
    }

    public static func - (lhs: Tensor, rhs: Tensor) -> Tensor {
        return Tensor(shape: lhs.shape, data: zip(lhs.data, rhs.data).map { $0 - $1 })
    }

    public static func * (lhs: Tensor, rhs: Double) -> Tensor {
        return Tensor(shape: lhs.shape, data: lhs.data.map { $0 * rhs })
    }

    public func sum(axis: Int) -> Tensor {
        var newShape = shape
        newShape[axis] = 1
        var result = Tensor(shape: newShape, fill: 0)

        let outerStride = shape[0..<axis].reduce(1, *)
        let innerStride = shape[(axis + 1)...].reduce(1, *)
        let axisSize = shape[axis]

        for o in 0..<outerStride {
            for i in 0..<innerStride {
                var s = 0.0
                for a in 0..<axisSize {
                    s += data[o * axisSize * innerStride + a * innerStride + i]
                }
                result.data[o * innerStride + i] = s
            }
        }

        return result
    }

    public func mean(axis: Int) -> Tensor {
        let s = sum(axis: axis)
        let count = Double(shape[axis])
        return s * (1.0 / count)
    }
}

// MARK: - Matrix Operations

public struct Matrix {
    public var rows: Int
    public var cols: Int
    public var data: [[Double]]

    public init(rows: Int, cols: Int, fill: Double = 0) {
        self.rows = rows
        self.cols = cols
        self.data = Array(repeating: Array(repeating: fill, count: cols), count: rows)
    }

    public init(_ data: [[Double]]) {
        self.rows = data.count
        self.cols = data.first?.count ?? 0
        self.data = data
    }

    public static func * (lhs: Matrix, rhs: Matrix) -> Matrix {
        precondition(lhs.cols == rhs.rows)
        var result = Matrix(rows: lhs.rows, cols: rhs.cols)
        for i in 0..<lhs.rows {
            for j in 0..<rhs.cols {
                var sum = 0.0
                for k in 0..<lhs.cols {
                    sum += lhs.data[i][k] * rhs.data[k][j]
                }
                result.data[i][j] = sum
            }
        }
        return result
    }

    public static func + (lhs: Matrix, rhs: Matrix) -> Matrix {
        var result = Matrix(rows: lhs.rows, cols: lhs.cols)
        for i in 0..<lhs.rows {
            for j in 0..<lhs.cols {
                result.data[i][j] = lhs.data[i][j] + rhs.data[i][j]
            }
        }
        return result
    }

    public func transposed() -> Matrix {
        var result = Matrix(rows: cols, cols: rows)
        for i in 0..<rows {
            for j in 0..<cols {
                result.data[j][i] = data[i][j]
            }
        }
        return result
    }

    public func map(_ transform: (Double) -> Double) -> Matrix {
        return Matrix(data.map { row in row.map(transform) })
    }

    public static func random(rows: Int, cols: Int, scale: Double = 0.02) -> Matrix {
        var m = Matrix(rows: rows, cols: cols)
        for i in 0..<rows {
            for j in 0..<cols {
                m.data[i][j] = Double.random(in: -scale...scale)
            }
        }
        return m
    }
}

// MARK: - Activation Functions

public enum Activation {
    public static func relu(_ x: Double) -> Double { max(0, x) }
    public static func gelu(_ x: Double) -> Double { 0.5 * x * (1 + tanh(0.7978845608 * (x + 0.044715 * x * x * x))) }
    public static func sigmoid(_ x: Double) -> Double { 1.0 / (1.0 + exp(-x)) }
    public static func tanh(_ x: Double) -> Double { Foundation.tanh(x) }
    public static func silu(_ x: Double) -> Double { x * sigmoid(x) }
    public static func softmax(_ values: [Double]) -> [Double] {
        let maxVal = values.max() ?? 0
        let exps = values.map { exp($0 - maxVal) }
        let sum = exps.reduce(0, +)
        return exps.map { $0 / sum }
    }
    public static func layerNorm(_ values: [Double], epsilon: Double = 1e-5) -> [Double] {
        let mean = values.reduce(0, +) / Double(values.count)
        let variance = values.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / Double(values.count)
        let std = sqrt(variance + epsilon)
        return values.map { ($0 - mean) / std }
    }
}

// MARK: - Positional Encoding

public struct PositionalEncoding {
    public let dModel: Int
    public let maxLen: Int
    public var encoding: [[Double]]

    public init(dModel: Int, maxLen: Int = 2048) {
        self.dModel = dModel
        self.maxLen = maxLen
        self.encoding = []

        for pos in 0..<maxLen {
            var row: [Double] = []
            for i in 0..<dModel {
                let angle = Double(pos) / pow(10000.0, Double(2 * (i / 2)) / Double(dModel))
                if i % 2 == 0 {
                    row.append(sin(angle))
                } else {
                    row.append(cos(angle))
                }
            }
            encoding.append(row)
        }
    }

    public func encoding(for position: Int) -> [Double] {
        guard position < maxLen else { return Array(repeating: 0, count: dModel) }
        return encoding[position]
    }
}

// MARK: - Multi-Head Self-Attention

public final class MultiHeadAttention {
    public let dModel: Int
    public let numHeads: Int
    public let headDim: Int
    public var wQuery: Matrix
    public var wKey: Matrix
    public var wValue: Matrix
    public var wOutput: Matrix

    public init(dModel: Int, numHeads: Int) {
        self.dModel = dModel
        self.numHeads = numHeads
        self.headDim = dModel / numHeads
        self.wQuery = Matrix.random(rows: dModel, cols: dModel, scale: 0.02)
        self.wKey = Matrix.random(rows: dModel, cols: dModel, scale: 0.02)
        self.wValue = Matrix.random(rows: dModel, cols: dModel, scale: 0.02)
        self.wOutput = Matrix.random(rows: dModel, cols: dModel, scale: 0.02)
    }

    public func forward(_ x: [[Double]], mask: [[Double]]? = nil) -> [[Double]] {
        let seqLen = x.count
        let xMatrix = Matrix(x)

        let q = xMatrix * wQuery
        let k = xMatrix * wKey
        let v = xMatrix * wValue

        var outputs: [[Double]] = []

        for h in 0..<numHeads {
            let start = h * headDim
            let end = start + headDim

            var headOutput: [[Double]] = []

            for i in 0..<seqLen {
                var scores: [Double] = []
                for j in 0..<seqLen {
                    var dot = 0.0
                    for d in start..<end {
                        dot += q.data[i][d] * k.data[j][d]
                    }
                    dot /= sqrt(Double(headDim))
                    if let mask = mask {
                        dot += mask[i][j]
                    }
                    scores.append(dot)
                }

                let attnWeights = Activation.softmax(scores)

                var outputRow = Array(repeating: 0.0, count: headDim)
                for j in 0..<seqLen {
                    for d in start..<end {
                        outputRow[d - start] += attnWeights[j] * v.data[j][d]
                    }
                }
                headOutput.append(outputRow)
            }

            outputs.append(contentsOf: headOutput)
        }

        var combined = Array(repeating: Array(repeating: 0.0, count: dModel), count: seqLen)
        for h in 0..<numHeads {
            for i in 0..<seqLen {
                for d in 0..<headDim {
                    combined[i][h * headDim + d] = outputs[h * seqLen + i][d]
                }
            }
        }

        let combinedMatrix = Matrix(combined)
        let result = combinedMatrix * wOutput

        return result.data
    }
}

// MARK: - Feed-Forward Network

public final class FeedForward {
    public let dModel: Int
    public let dFF: Int
    public var w1: Matrix
    public var w2: Matrix
    public var b1: [Double]
    public var b2: [Double]

    public init(dModel: Int, dFF: Int) {
        self.dModel = dModel
        self.dFF = dFF
        self.w1 = Matrix.random(rows: dModel, cols: dFF, scale: 0.02)
        self.w2 = Matrix.random(rows: dFF, cols: dModel, scale: 0.02)
        self.b1 = Array(repeating: 0, count: dFF)
        self.b2 = Array(repeating: 0, count: dModel)
    }

    public func forward(_ x: [[Double]]) -> [[Double]] {
        let xMatrix = Matrix(x)
        let hidden = xMatrix * w1

        var activated = Matrix(rows: hidden.rows, cols: hidden.cols)
        for i in 0..<hidden.rows {
            for j in 0..<hidden.cols {
                activated.data[i][j] = Activation.gelu(hidden.data[i][j] + b1[j])
            }
        }

        let output = activated * w2
        var result = Matrix(rows: output.rows, cols: output.cols)
        for i in 0..<output.rows {
            for j in 0..<output.cols {
                result.data[i][j] = output.data[i][j] + b2[j]
            }
        }

        return result.data
    }
}

// MARK: - Layer Normalization

public struct LayerNorm {
    public let dModel: Int
    public var gamma: [Double]
    public var beta: [Double]
    public let epsilon: Double

    public init(dModel: Int, epsilon: Double = 1e-5) {
        self.dModel = dModel
        self.gamma = Array(repeating: 1, count: dModel)
        self.beta = Array(repeating: 0, count: dModel)
        self.epsilon = epsilon
    }

    public func normalize(_ x: [[Double]]) -> [[Double]] {
        return x.map { row in
            let normed = Activation.layerNorm(row, epsilon: epsilon)
            return zip(zip(gamma, beta), normed).map { (gb, n) in gb.0 * n + gb.1 }
        }
    }
}

// MARK: - Transformer Decoder Layer

public final class TransformerDecoderLayer {
    public let dModel: Int
    public let numHeads: Int
    public var attention: MultiHeadAttention
    public var feedForward: FeedForward
    public var norm1: LayerNorm
    public var norm2: LayerNorm
    public var dropoutRate: Double

    public init(dModel: Int, numHeads: Int, dFF: Int, dropoutRate: Double = 0.1) {
        self.dModel = dModel
        self.numHeads = numHeads
        self.attention = MultiHeadAttention(dModel: dModel, numHeads: numHeads)
        self.feedForward = FeedForward(dModel: dModel, dFF: dFF)
        self.norm1 = LayerNorm(dModel: dModel)
        self.norm2 = LayerNorm(dModel: dModel)
        self.dropoutRate = dropoutRate
    }

    public func forward(_ x: [[Double]], mask: [[Double]]? = nil) -> [[Double]] {
        let attnOutput = attention.forward(x, mask: mask)
        var residual: [[Double]] = []
        for i in 0..<x.count {
            residual.append(zip(x[i], attnOutput[i]).map { $0 + $1 })
        }
        let normed1 = norm1.normalize(residual)

        let ffOutput = feedForward.forward(normed1)
        var residual2: [[Double]] = []
        for i in 0..<normed1.count {
            residual2.append(zip(normed1[i], ffOutput[i]).map { $0 + $1 })
        }
        let normed2 = norm2.normalize(residual2)

        return normed2
    }
}

// MARK: - Causal Mask

public func createCausalMask(seqLen: Int) -> [[Double]] {
    var mask = Array(repeating: Array(repeating: 0.0, count: seqLen), count: seqLen)
    for i in 0..<seqLen {
        for j in (i + 1)..<seqLen {
            mask[i][j] = -1e9
        }
    }
    return mask
}

// MARK: - Token Embedding

public final class TokenEmbedding {
    public let vocabSize: Int
    public let dModel: Int
    public var weights: Matrix

    public init(vocabSize: Int, dModel: Int) {
        self.vocabSize = vocabSize
        self.dModel = dModel
        self.weights = Matrix.random(rows: vocabSize, cols: dModel, scale: 0.02)
    }

    public func embed(_ tokenIds: [Int]) -> [[Double]] {
        return tokenIds.map { id in
            guard id < vocabSize else { return Array(repeating: 0, count: dModel) }
            return weights.data[id]
        }
    }
}

// MARK: - GPT Model

public final class GPTModel: ObservableObject, Codable {
    public let vocabSize: Int
    public let dModel: Int
    public let numLayers: Int
    public let numHeads: Int
    public let dFF: Int
    public let maxSeqLen: Int
    public var tokenEmbedding: TokenEmbedding
    public var positionalEncoding: PositionalEncoding
    public var decoderLayers: [TransformerDecoderLayer]
    public var finalNorm: LayerNorm
    public var lmHead: Matrix

    enum CodingKeys: CodingKey {
        case vocabSize, dModel, numLayers, numHeads, dFF, maxSeqLen
        case lmHead, finalNorm
    }

    public init(vocabSize: Int, dModel: Int = 256, numLayers: Int = 4,
                numHeads: Int = 4, dFF: Int = 1024, maxSeqLen: Int = 512) {
        self.vocabSize = vocabSize
        self.dModel = dModel
        self.numLayers = numLayers
        self.numHeads = numHeads
        self.dFF = dFF
        self.maxSeqLen = maxSeqLen
        self.tokenEmbedding = TokenEmbedding(vocabSize: vocabSize, dModel: dModel)
        self.positionalEncoding = PositionalEncoding(dModel: dModel, maxLen: maxSeqLen)
        self.decoderLayers = (0..<numLayers).map { _ in
            TransformerDecoderLayer(dModel: dModel, numHeads: numHeads, dFF: dFF)
        }
        self.finalNorm = LayerNorm(dModel: dModel)
        self.lmHead = Matrix.random(rows: dModel, cols: vocabSize, scale: 0.02)
    }

    public func forward(_ tokenIds: [Int]) -> [[Double]] {
        let seqLen = min(tokenIds.count, maxSeqLen)
        let truncated = Array(tokenIds.prefix(seqLen))

        var embeddings = tokenEmbedding.embed(truncated)
        for i in 0..<embeddings.count {
            let posEnc = positionalEncoding.encoding(for: i)
            for j in 0..<dModel {
                embeddings[i][j] += posEnc[j]
            }
        }

        let mask = createCausalMask(seqLen: seqLen)
        var hidden = embeddings
        for layer in decoderLayers {
            hidden = layer.forward(hidden, mask: mask)
        }

        hidden = finalNorm.normalize(hidden)

        let hiddenMatrix = Matrix(hidden)
        let logits = hiddenMatrix * lmHead

        return logits.data
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(vocabSize, forKey: .vocabSize)
        try c.encode(dModel, forKey: .dModel)
        try c.encode(numLayers, forKey: .numLayers)
        try c.encode(numHeads, forKey: .numHeads)
        try c.encode(dFF, forKey: .dFF)
        try c.encode(maxSeqLen, forKey: .maxSeqLen)
        try c.encode(lmHead, forKey: .lmHead)
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.vocabSize = try c.decode(Int.self, forKey: .vocabSize)
        self.dModel = try c.decode(Int.self, forKey: .dModel)
        self.numLayers = try c.decode(Int.self, forKey: .numLayers)
        self.numHeads = try c.decode(Int.self, forKey: .numHeads)
        self.dFF = try c.decode(Int.self, forKey: .dFF)
        self.maxSeqLen = try c.decode(Int.self, forKey: .maxSeqLen)
        self.lmHead = try c.decode(Matrix.self, forKey: .lmHead)
        let dM = dModel
        let nH = numHeads
        let dF = dFF
        let mS = maxSeqLen
        self.tokenEmbedding = TokenEmbedding(vocabSize: vocabSize, dModel: dM)
        self.positionalEncoding = PositionalEncoding(dModel: dM, maxLen: mS)
        self.decoderLayers = (0..<numLayers).map { _ in
            TransformerDecoderLayer(dModel: dM, numHeads: nH, dFF: dF)
        }
        self.finalNorm = LayerNorm(dModel: dModel)
    }
}

// MARK: - Matrix Codable

extension Matrix: Codable {
    enum CodingKeys: CodingKey { case rows, cols, data }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.rows = try c.decode(Int.self, forKey: .rows)
        self.cols = try c.decode(Int.self, forKey: .cols)
        self.data = try c.decode([[Double]].self, forKey: .data)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(rows, forKey: .rows)
        try c.encode(cols, forKey: .cols)
        try c.encode(data, forKey: .data)
    }
}

// MARK: - Text Generator

public final class TextGenerator: ObservableObject {
    public let model: GPTModel
    public let tokenizer: BPETokenizer
    @Published public var generatedText: String = ""
    @Published public var isGenerating: Bool = false
    @Published public var tokenCount: Int = 0

    public init(model: GPTModel, tokenizer: BPETokenizer) {
        self.model = model
        self.tokenizer = tokenizer
    }

    public func generate(prompt: String, maxTokens: Int = 100,
                         temperature: Double = 0.8, topK: Int = 40,
                         topP: Double = 0.9) -> String {
        isGenerating = true
        var tokens = tokenizer.encode(prompt)
        var generated: [Int] = []

        for _ in 0..<maxTokens {
            let logits = model.forward(tokens)
            guard let lastLogits = logits.last else { break }

            var scaledLogits = lastLogits.map { $0 / temperature }

            if topK > 0 && topK < scaledLogits.count {
                let sortedIndices = scaledLogits.indices.sorted { scaledLogits[$0] > scaledLogits[$1] }
                let threshold = scaledLogits[sortedIndices[topK - 1]]
                for i in scaledLogits.indices {
                    if scaledLogits[i] < threshold {
                        scaledLogits[i] = -1e9
                    }
                }
            }

            let probs = Activation.softmax(scaledLogits)

            if topP < 1.0 {
                let sortedIndices = probs.indices.sorted { probs[$0] > probs[$1] }
                var cumulative = 0.0
                var nucleusIndices: Set<Int> = []
                for idx in sortedIndices {
                    cumulative += probs[idx]
                    nucleusIndices.insert(idx)
                    if cumulative >= topP { break }
                }
                for i in probs.indices {
                    if !nucleusIndices.contains(i) {
                        scaledLogits[i] = -1e9
                    }
                }
            }

            let finalProbs = Activation.softmax(scaledLogits)
            let nextToken = sampleFrom(finalProbs)

            if nextToken == SpecialToken.eos.rawValue { break }

            tokens.append(nextToken)
            generated.append(nextToken)
            tokenCount += 1

            if tokens.count > model.maxSeqLen - 10 {
                tokens = Array(tokens.suffix(model.maxSeqLen - 10))
            }
        }

        let result = tokenizer.decode(generated)
        generatedText = result
        isGenerating = false
        return result
    }

    public func generateGreedy(prompt: String, maxTokens: Int = 100) -> String {
        isGenerating = true
        var tokens = tokenizer.encode(prompt)
        var generated: [Int] = []

        for _ in 0..<maxTokens {
            let logits = model.forward(tokens)
            guard let lastLogits = logits.last else { break }
            let nextToken = lastLogits.indices.max(by: { lastLogits[$0] < lastLogits[$1] }) ?? 0

            if nextToken == SpecialToken.eos.rawValue { break }

            tokens.append(nextToken)
            generated.append(nextToken)
            tokenCount += 1

            if tokens.count > model.maxSeqLen - 10 {
                tokens = Array(tokens.suffix(model.maxSeqLen - 10))
            }
        }

        let result = tokenizer.decode(generated)
        generatedText = result
        isGenerating = false
        return result
    }

    private func sampleFrom(_ probs: [Double]) -> Int {
        let r = Double.random(in: 0..<1)
        var cumulative = 0.0
        for (i, p) in probs.enumerated() {
            cumulative += p
            if r < cumulative { return i }
        }
        return probs.count - 1
    }

    public var summary: String {
        "Generator: \(tokenCount) tokens generated | \(isGenerating ? "◉ generating" : "◌ idle")"
    }
}

// MARK: - KV Cache

public final class KVCache {
    public var keyCache: [[[Double]]]
    public var valueCache: [[[Double]]]
    public var maxLength: Int
    public var currentLength: Int

    public init(maxLength: Int = 512, dModel: Int = 256) {
        self.maxLength = maxLength
        self.keyCache = []
        self.valueCache = []
        self.currentLength = 0
    }

    public func append(keys: [[Double]], values: [[Double]]) {
        keyCache.append(keys)
        valueCache.append(values)
        currentLength += keys.count

        if currentLength > maxLength {
            let overflow = currentLength - maxLength
            if !keyCache.isEmpty {
                keyCache[0] = Array(keyCache[0].dropFirst(overflow))
                valueCache[0] = Array(valueCache[0].dropFirst(overflow))
                currentLength -= overflow
            }
        }
    }

    public func clear() {
        keyCache.removeAll()
        valueCache.removeAll()
        currentLength = 0
    }

    public var summary: String {
        "KVCache: \(currentLength)/\(maxLength) | \(keyCache.count) layers"
    }
}

// MARK: - Training State

public struct TrainingState: Codable {
    public var epoch: Int
    public var step: Int
    public var loss: Double
    public var learningRate: Double
    public var bestLoss: Double
    public var totalTokens: Int
    public var trainingTime: Double

    public init() {
        self.epoch = 0
        self.step = 0
        self.loss = Double.greatestFiniteMagnitude
        self.learningRate = 0.001
        self.bestLoss = Double.greatestFiniteMagnitude
        self.totalTokens = 0
        self.trainingTime = 0
    }

    public var summary: String {
        "Training: epoch \(epoch), step \(step), loss \(String(format: "%.4f", loss)), lr \(learningRate), \(totalTokens) tokens"
    }
}

// MARK: - LLM Engine

public final class LLMEngine: ObservableObject {
    @Published public var model: GPTModel
    @Published public var tokenizer: BPETokenizer
    @Published public var generator: TextGenerator
    @Published public var trainingState: TrainingState
    @Published public var kvCache: KVCache
    @Published public var isLoaded: Bool = false
    @Published public var modelPath: String?
    @Published public var generationHistory: [GenerationRecord] = []

    public init(vocabSize: Int = 32000, dModel: Int = 256, numLayers: Int = 4,
                numHeads: Int = 4, dFF: Int = 1024, maxSeqLen: Int = 512) {
        let m = GPTModel(vocabSize: vocabSize, dModel: dModel,
                         numLayers: numLayers, numHeads: numHeads,
                         dFF: dFF, maxSeqLen: maxSeqLen)
        let tok = BPETokenizer(vocabSize: vocabSize)
        self.model = m
        self.tokenizer = tok
        self.generator = TextGenerator(model: m, tokenizer: tok)
        self.trainingState = TrainingState()
        self.kvCache = KVCache(maxLength: maxSeqLen, dModel: dModel)
        self.isLoaded = true
    }

    // MARK: - Generate

    public func generate(prompt: String, maxTokens: Int = 100,
                         temperature: Double = 0.8, topK: Int = 40,
                         topP: Double = 0.9) -> String {
        let result = generator.generate(prompt: prompt, maxTokens: maxTokens,
                                         temperature: temperature, topK: topK, topP: topP)
        generationHistory.append(GenerationRecord(
            prompt: prompt, output: result,
            maxTokens: maxTokens, temperature: temperature
        ))
        if generationHistory.count > 100 {
            generationHistory.removeFirst(generationHistory.count - 100)
        }
        return result
    }

    public func generateGreedy(prompt: String, maxTokens: Int = 100) -> String {
        let result = generator.generateGreedy(prompt: prompt, maxTokens: maxTokens)
        generationHistory.append(GenerationRecord(
            prompt: prompt, output: result,
            maxTokens: maxTokens, temperature: 0
        ))
        if generationHistory.count > 100 {
            generationHistory.removeFirst(generationHistory.count - 100)
        }
        return result
    }

    // MARK: - Train (Simulated)

    public func trainStep(on text: String) -> Double {
        let tokens = tokenizer.encodeWithoutSpecial(text)
        guard tokens.count > 2 else { return trainingState.loss }

        let inputTokens = Array(tokens.dropLast())
        let targetTokens = Array(tokens.dropFirst())

        let logits = model.forward(inputTokens)

        var loss = 0.0
        for (i, target) in targetTokens.enumerated() {
            if i < logits.count {
                let logitRow = logits[i]
                let probs = Activation.softmax(logitRow)
                let targetProb = max(1e-10, probs[target])
                loss -= log(targetProb)
            }
        }
        loss /= Double(max(1, targetTokens.count))

        trainingState.step += 1
        trainingState.loss = loss
        trainingState.totalTokens += tokens.count
        if loss < trainingState.bestLoss {
            trainingState.bestLoss = loss
        }

        return loss
    }

    public func train(on corpus: String, epochs: Int = 1) {
        let startTime = Date().timeIntervalSince1970
        for epoch in 0..<epochs {
            trainingState.epoch = epoch
            let sentences = corpus.components(separatedBy: ". ")
            for sentence in sentences {
                _ = trainStep(on: sentence)
            }
        }
        trainingState.trainingTime += Date().timeIntervalSince1970 - startTime
    }

    // MARK: - Tokenize

    public func tokenize(_ text: String) -> [Int] {
        return tokenizer.encode(text)
    }

    public func detokenize(_ ids: [Int]) -> String {
        return tokenizer.decode(ids)
    }

    public func tokenCount(_ text: String) -> Int {
        return tokenizer.encode(text).count
    }

    // MARK: - Save/Load

    public func save(to path: String) -> Bool {
        do {
            let data = try JSONEncoder().encode(model)
            try data.write(to: URL(fileURLWithPath: path))
            modelPath = path
            return true
        } catch {
            return false
        }
    }

    public func load(from path: String) -> Bool {
        do {
            let data = try Data(contentsOf: URL(fileURLWithPath: path))
            model = try JSONDecoder().decode(GPTModel.self, from: data)
            generator = TextGenerator(model: model, tokenizer: tokenizer)
            modelPath = path
            isLoaded = true
            return true
        } catch {
            return false
        }
    }

    // MARK: - Summary

    public var summary: String {
        "LLM: \(model.vocabSize) vocab, \(model.dModel) dModel, \(model.numLayers) layers | \(tokenizer.stats) | \(trainingState.summary)"
    }

    public var modelInfo: String {
        """
        GPT Model:
        - Vocab: \(model.vocabSize)
        - dModel: \(model.dModel)
        - Layers: \(model.numLayers)
        - Heads: \(model.numHeads)
        - dFF: \(model.dFF)
        - MaxSeq: \(model.maxSeqLen)
        - Parameters: ~\(estimateParameters())
        """
    }

    public func estimateParameters() -> Int {
        let embedding = model.vocabSize * model.dModel
        let attention = model.numLayers * 4 * model.dModel * model.dModel
        let ff = model.numLayers * 2 * model.dModel * model.dFF
        let lmHead = model.dModel * model.vocabSize
        return embedding + attention + ff + lmHead
    }
}

// MARK: - Generation Record

public struct GenerationRecord: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let prompt: String
    public let output: String
    public let maxTokens: Int
    public let temperature: Double

    public init(prompt: String, output: String, maxTokens: Int, temperature: Double) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.prompt = prompt
        self.output = output
        self.maxTokens = maxTokens
        self.temperature = temperature
    }

    public var summary: String {
        "⟡ prompt: \(prompt.prefix(30))... → \(output.prefix(30))... [\(maxTokens) tok, T=\(temperature)]"
    }
}

// MARK: - LLM Conversation

public final class LLMConversation: ObservableObject {
    @Published public var messages: [ConversationMessage] = []
    @Published public var systemPrompt: String
    public let engine: LLMEngine

    public init(engine: LLMEngine, systemPrompt: String = "You are a helpful AI assistant.") {
        self.engine = engine
        self.systemPrompt = systemPrompt
    }

    public func send(_ message: String, maxTokens: Int = 100) -> String {
        messages.append(ConversationMessage(role: .user, content: message))

        let context = buildContext()
        let response = engine.generate(prompt: context, maxTokens: maxTokens)

        messages.append(ConversationMessage(role: .assistant, content: response))
        return response
    }

    public func clear() {
        messages.removeAll()
    }

    private func buildContext() -> String {
        var context = systemPrompt + "\n"
        for msg in messages.suffix(10) {
            context += "\(msg.role.label): \(msg.content)\n"
        }
        context += "assistant: "
        return context
    }

    public var summary: String {
        "Conversation: \(messages.count) messages | \(engine.summary)"
    }
}

public struct ConversationMessage: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let role: MessageRole
    public let content: String

    public enum MessageRole: String, Codable, CaseIterable {
        case system    = "system"
        case user      = "user"
        case assistant = "assistant"

        public var label: String { rawValue }
        public var glyph: String {
            switch self {
            case .system:    return "⚙"
            case .user:      return "👤"
            case .assistant: return "🤖"
            }
        }
    }

    public init(role: MessageRole, content: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.role = role
        self.content = content
    }
}

// MARK: - LLM Stream

public final class LLMStream: ObservableObject {
    @Published public var currentText: String = ""
    @Published public var isStreaming: Bool = false
    @Published public var streamedTokens: [Int] = []

    public let engine: LLMEngine
    private var streamTask: DispatchWorkItem?

    public init(engine: LLMEngine) {
        self.engine = engine
    }

    public func stream(prompt: String, maxTokens: Int = 50, onToken: @escaping (String) -> Void) {
        isStreaming = true
        currentText = ""
        streamedTokens = []

        var tokens = engine.tokenize(prompt)

        let workItem = DispatchWorkItem { [weak self] in
            guard let self = self else { return }

            for _ in 0..<maxTokens {
                if !self.isStreaming { break }

                let logits = self.engine.model.forward(tokens)
                guard let lastLogits = logits.last else { break }

                let probs = Activation.softmax(lastLogits)
                let nextToken = self.sampleFrom(probs)

                if nextToken == SpecialToken.eos.rawValue { break }

                tokens.append(nextToken)
                self.streamedTokens.append(nextToken)

                let tokenText = self.engine.tokenizer.reverseVocab[nextToken] ?? ""
                if !tokenText.hasPrefix("<") {
                    self.currentText += tokenText
                    DispatchQueue.main.async {
                        onToken(tokenText)
                    }
                }

                if tokens.count > self.engine.model.maxSeqLen - 10 {
                    tokens = Array(tokens.suffix(self.engine.model.maxSeqLen - 10))
                }
            }

            DispatchQueue.main.async {
                self.isStreaming = false
            }
        }

        streamTask = workItem
        DispatchQueue.global(qos: .userInitiated).async(execute: workItem)
    }

    public func stop() {
        isStreaming = false
        streamTask?.cancel()
    }

    private func sampleFrom(_ probs: [Double]) -> Int {
        let r = Double.random(in: 0..<1)
        var cumulative = 0.0
        for (i, p) in probs.enumerated() {
            cumulative += p
            if r < cumulative { return i }
        }
        return probs.count - 1
    }

    public var summary: String {
        "Stream: \(streamedTokens.count) tokens | \(isStreaming ? "◉ streaming" : "◌ idle") | \"\(currentText.prefix(40))\""
    }
}

// MARK: - Model Config

public struct ModelConfig: Codable {
    public let vocabSize: Int
    public let dModel: Int
    public let numLayers: Int
    public let numHeads: Int
    public let dFF: Int
    public let maxSeqLen: Int
    public let dropoutRate: Double
    public let learningRate: Double
    public let warmupSteps: Int
    public let weightDecay: Double
    public let labelSmoothing: Double

    public init(vocabSize: Int = 32000, dModel: Int = 256, numLayers: Int = 4,
                numHeads: Int = 4, dFF: Int = 1024, maxSeqLen: Int = 512,
                dropoutRate: Double = 0.1, learningRate: Double = 0.001,
                warmupSteps: Int = 1000, weightDecay: Double = 0.01,
                labelSmoothing: Double = 0.1) {
        self.vocabSize = vocabSize
        self.dModel = dModel
        self.numLayers = numLayers
        self.numHeads = numHeads
        self.dFF = dFF
        self.maxSeqLen = maxSeqLen
        self.dropoutRate = dropoutRate
        self.learningRate = learningRate
        self.warmupSteps = warmupSteps
        self.weightDecay = weightDecay
        self.labelSmoothing = labelSmoothing
    }

    public static let tiny = ModelConfig(vocabSize: 1000, dModel: 64, numLayers: 2, numHeads: 2, dFF: 256, maxSeqLen: 128)
    public static let small = ModelConfig(vocabSize: 8000, dModel: 128, numLayers: 3, numHeads: 4, dFF: 512, maxSeqLen: 256)
    public static let medium = ModelConfig(vocabSize: 32000, dModel: 256, numLayers: 4, numHeads: 4, dFF: 1024, maxSeqLen: 512)
    public static let large = ModelConfig(vocabSize: 50000, dModel: 512, numLayers: 6, numHeads: 8, dFF: 2048, maxSeqLen: 1024)
    public static let xlarge = ModelConfig(vocabSize: 100000, dModel: 768, numLayers: 8, numHeads: 12, dFF: 3072, maxSeqLen: 2048)

    public var summary: String {
        "Config: \(dModel)d, \(numLayers)L, \(numHeads)H, \(dFF)FF, \(maxSeqLen)seq | ~\(estimateParams()) params"
    }

    public func estimateParams() -> Int {
        let emb = vocabSize * dModel
        let attn = numLayers * 4 * dModel * dModel
        let ff = numLayers * 2 * dModel * dFF
        let head = dModel * vocabSize
        return emb + attn + ff + head
    }
}

// MARK: - Learning Rate Scheduler

public final class LRScheduler: ObservableObject {
    @Published public var currentLR: Double
    public let baseLR: Double
    public let warmupSteps: Int
    public let totalSteps: Int
    public var currentStep: Int = 0

    public init(baseLR: Double = 0.001, warmupSteps: Int = 1000, totalSteps: Int = 10000) {
        self.baseLR = baseLR
        self.warmupSteps = warmupSteps
        self.totalSteps = totalSteps
        self.currentLR = baseLR / Double(warmupSteps)
    }

    public func step() {
        currentStep += 1
        if currentStep < warmupSteps {
            currentLR = baseLR * Double(currentStep) / Double(warmupSteps)
        } else {
            let progress = Double(currentStep - warmupSteps) / Double(max(1, totalSteps - warmupSteps))
            currentLR = baseLR * 0.5 * (1 + cos(.pi * progress))
        }
    }

    public var summary: String {
        "LR: \(String(format: "%.6f", currentLR)) [step \(currentStep)/\(totalSteps)]"
    }
}

// MARK: - Perplexity Calculator

public final class PerplexityCalculator {
    public init() {}

    public func calculate(model: GPTModel, tokenizer: BPETokenizer, text: String) -> Double {
        let tokens = tokenizer.encodeWithoutSpecial(text)
        guard tokens.count > 2 else { return Double.infinity }

        let inputTokens = Array(tokens.dropLast())
        let targetTokens = Array(tokens.dropFirst())

        let logits = model.forward(inputTokens)

        var totalLogProb = 0.0
        var count = 0

        for (i, target) in targetTokens.enumerated() {
            if i < logits.count {
                let probs = Activation.softmax(logits[i])
                let targetProb = max(1e-10, probs[target])
                totalLogProb += log(targetProb)
                count += 1
            }
        }

        guard count > 0 else { return Double.infinity }
        let avgLogProb = totalLogProb / Double(count)
        return exp(-avgLogProb)
    }
}

// MARK: - Text Dataset

public final class TextDataset: ObservableObject {
    @Published public var samples: [String] = []
    @Published public var totalTokens: Int = 0
    public let tokenizer: BPETokenizer

    public init(tokenizer: BPETokenizer) {
        self.tokenizer = tokenizer
    }

    public func load(text: String, chunkSize: Int = 256) {
        let sentences = text.components(separatedBy: ". ")
        var currentChunk = ""
        for sentence in sentences {
            if currentChunk.count + sentence.count > chunkSize {
                if !currentChunk.isEmpty {
                    samples.append(currentChunk)
                    totalTokens += tokenizer.encodeWithoutSpecial(currentChunk).count
                }
                currentChunk = sentence
            } else {
                currentChunk += sentence + ". "
            }
        }
        if !currentChunk.isEmpty {
            samples.append(currentChunk)
            totalTokens += tokenizer.encodeWithoutSpecial(currentChunk).count
        }
    }

    public func batch(size: Int) -> [String] {
        guard !samples.isEmpty else { return [] }
        var batch: [String] = []
        for _ in 0..<size {
            if let sample = samples.randomElement() {
                batch.append(sample)
            }
        }
        return batch
    }

    public func shuffle() {
        samples.shuffle()
    }

    public var summary: String {
        "Dataset: \(samples.count) samples, ~\(totalTokens) tokens"
    }
}

// MARK: - Model Evaluator

public final class ModelEvaluator: ObservableObject {
    @Published public var evaluations: [ModelEvaluation] = []

    public init() {}

    public func evaluate(model: GPTModel, tokenizer: BPETokenizer, dataset: TextDataset) -> ModelEvaluation {
        let perplexityCalc = PerplexityCalculator()

        var totalPerplexity = 0.0
        var sampleCount = 0

        for sample in dataset.samples.prefix(50) {
            let ppl = perplexityCalc.calculate(model: model, tokenizer: tokenizer, text: sample)
            if !ppl.isInfinite {
                totalPerplexity += ppl
                sampleCount += 1
            }
        }

        let avgPerplexity = sampleCount > 0 ? totalPerplexity / Double(sampleCount) : Double.infinity

        let evaluation = ModelEvaluation(
            perplexity: avgPerplexity,
            vocabSize: model.vocabSize,
            paramCount: estimateParams(model: model),
            sampleCount: sampleCount
        )

        evaluations.append(evaluation)
        if evaluations.count > 50 { evaluations.removeFirst(evaluations.count - 50) }

        return evaluation
    }

    private func estimateParams(model: GPTModel) -> Int {
        let emb = model.vocabSize * model.dModel
        let attn = model.numLayers * 4 * model.dModel * model.dModel
        let ff = model.numLayers * 2 * model.dModel * model.dFF
        let head = model.dModel * model.vocabSize
        return emb + attn + ff + head
    }

    public var summary: String {
        "Evaluator: \(evaluations.count) evaluations | latest ppl: \(evaluations.last.map { String(format: "%.2f", $0.perplexity) } ?? "N/A")"
    }
}

public struct ModelEvaluation: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let perplexity: Double
    public let vocabSize: Int
    public let paramCount: Int
    public let sampleCount: Int

    public init(perplexity: Double, vocabSize: Int, paramCount: Int, sampleCount: Int) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.perplexity = perplexity
        self.vocabSize = vocabSize
        self.paramCount = paramCount
        self.sampleCount = sampleCount
    }

    public var summary: String {
        "Eval: ppl=\(String(format: "%.2f", perplexity)), \(paramCount) params, \(sampleCount) samples"
    }
}

// MARK: - Prompt Template

public struct PromptTemplate: Identifiable, Codable {
    public let id: String
    public let name: String
    public let template: String
    public let variables: [String]
    public let category: TemplateCategory

    public enum TemplateCategory: String, Codable, CaseIterable {
        case code       = "code"
        case analysis   = "analysis"
        case summary    = "summary"
        case receipt    = "receipt"
        case audit      = "audit"
        case security   = "security"
        case workspace  = "workspace"
        case agent      = "agent"
        case custom     = "custom"

        public var glyph: String {
            switch self {
            case .code:      return "⌁"
            case .analysis:  return "⟡"
            case .summary:   return "◇"
            case .receipt:   return "🧾"
            case .audit:     return "📋"
            case .security:  return "🛡"
            case .workspace: return "📁"
            case .agent:     return "🤖"
            case .custom:    return "★"
            }
        }
    }

    public init(name: String, template: String, variables: [String], category: TemplateCategory) {
        self.id = UUID().uuidString.prefix(20).description
        self.name = name
        self.template = template
        self.variables = variables
        self.category = category
    }

    public func render(values: [String: String]) -> String {
        var result = template
        for (key, value) in values {
            result = result.replacingOccurrences(of: "{\(key)}", with: value)
        }
        return result
    }
}

// MARK: - Prompt Library

public final class PromptLibrary: ObservableObject {
    @Published public var templates: [PromptTemplate] = []

    public init() {
        loadDefaults()
    }

    private func loadDefaults() {
        templates = [
            PromptTemplate(name: "Code Review", template: "Review the following code for security issues, bugs, and improvements:\n\n{code}\n\nProvide a detailed analysis.", variables: ["code"], category: .code),
            PromptTemplate(name: "Security Audit", template: "Perform a security audit on:\n\n{target}\n\nFocus on: {focus}", variables: ["target", "focus"], category: .security),
            PromptTemplate(name: "Receipt Summary", template: "Summarize the receipt chain:\n\n{receipts}\n\nVerify integrity and flag any anomalies.", variables: ["receipts"], category: .receipt),
            PromptTemplate(name: "Agent Task", template: "Agent {agent_id} ({role}) should perform: {task}\n\nContext: {context}", variables: ["agent_id", "role", "task", "context"], category: .agent),
            PromptTemplate(name: "Workspace Analysis", template: "Analyze workspace {workspace}:\n\nFiles: {files}\n\nHealth: {health}", variables: ["workspace", "files", "health"], category: .workspace),
            PromptTemplate(name: "Audit Report", template: "Generate audit report for {period}:\n\nEvents: {events}\n\nViolations: {violations}", variables: ["period", "events", "violations"], category: .audit),
            PromptTemplate(name: "Decision Analysis", template: "Evaluate decision for agent {agent}:\n\nAction: {action}\nRisk: {risk}\nContext: {context}", variables: ["agent", "action", "risk", "context"], category: .analysis),
            PromptTemplate(name: "Summary", template: "Summarize the following:\n\n{text}\n\nKey points:", variables: ["text"], category: .summary),
        ]
    }

    public func add(_ template: PromptTemplate) {
        templates.append(template)
    }

    public func search(_ query: String) -> [PromptTemplate] {
        let lowered = query.lowercased()
        return templates.filter { $0.name.lowercased().contains(lowered) || $0.template.lowercased().contains(lowered) }
    }

    public var summary: String {
        "Prompts: \(templates.count) templates"
    }
}
