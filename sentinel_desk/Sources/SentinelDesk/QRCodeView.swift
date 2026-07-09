import SwiftUI
import CoreImage.CIFilterBuiltins
import AppKit

struct QRCodeView: NSViewRepresentable {
    let text: String
    var scale: CGFloat = 6

    func makeNSView(context: Context) -> NSImageView {
        let iv = NSImageView()
        iv.image = generateQRCode(from: text)
        return iv
    }

    func updateNSView(_ nsView: NSImageView, context: Context) {
        nsView.image = generateQRCode(from: text)
    }

    private func generateQRCode(from string: String) -> NSImage? {
        let context = CIContext()
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage else { return nil }
        let transformed = output.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        guard let cg = context.createCGImage(transformed, from: transformed.extent) else { return nil }
        return NSImage(cgImage: cg, size: NSSize(width: transformed.extent.width, height: transformed.extent.height))
    }
}
