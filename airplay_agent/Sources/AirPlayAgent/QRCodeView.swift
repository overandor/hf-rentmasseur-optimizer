import SwiftUI
import CoreImage.CIFilterBuiltins
import AppKit

struct QRCodeView: NSViewRepresentable {
    let text: String
    var scale: CGFloat = 8

    func makeNSView(context: Context) -> NSImageView {
        let imageView = NSImageView()
        imageView.image = generateQRCode(from: text)
        return imageView
    }

    func updateNSView(_ nsView: NSImageView, context: Context) {
        nsView.image = generateQRCode(from: text)
    }

    private func generateQRCode(from string: String) -> NSImage? {
        let context = CIContext()
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        filter.correctionLevel = "M"

        guard let outputImage = filter.outputImage else { return nil }

        let transformed = outputImage.transformed(by: CGAffineTransform(scaleX: scale, y: scale))

        guard let cgImage = context.createCGImage(transformed, from: transformed.extent) else { return nil }

        return NSImage(cgImage: cgImage, size: NSSize(width: transformed.extent.width, height: transformed.extent.height))
    }
}
