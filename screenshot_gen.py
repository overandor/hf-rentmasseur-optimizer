"""
Screenshot generator — launches a SwiftUI app, captures screenshots via screencapture.
"""

import subprocess
import time
import os
from pathlib import Path
from PIL import Image


def capture_app_screenshot(app_path, output_dir, app_name, widths=(1280, 2560)):
    """Launch app, capture screenshots at multiple resolutions."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    screenshots = []

    # Launch the app
    proc = subprocess.Popen(
        ["open", str(app_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    # Wait for app to open and render
    time.sleep(4)

    # Find the app's window via osascript
    try:
        r = subprocess.run(
            ["osascript", "-e",
             f'tell application "{app_name}" to activate'],
            capture_output=True, text=True, timeout=5
        )
        time.sleep(1)
    except:
        pass

    # Capture the screen region where the menu bar extra window appears
    # Menu bar apps open near the top-right, so capture that region
    for width in widths:
        shot_path = output_dir / f"{app_name}_{width}.png"

        # Use screencapture to grab the window
        r = subprocess.run(
            ["screencapture", "-x", "-o", "-C", str(shot_path)],
            capture_output=True, text=True, timeout=10
        )

        if shot_path.exists():
            # Crop to a reasonable app screenshot size
            img = Image.open(shot_path)
            # For menu bar apps, crop the top-right corner where the popover appears
            crop_w = min(width, img.width)
            crop_h = min(800, img.height)
            # Right-align the crop for menu bar apps
            left = max(0, img.width - crop_w)
            top = 0
            cropped = img.crop((left, top, left + crop_w, top + crop_h))
            cropped.save(str(shot_path))
            screenshots.append(str(shot_path))

    # Quit the app
    try:
        subprocess.run(
            ["osascript", "-e", f'quit app "{app_name}"'],
            capture_output=True, text=True, timeout=5
        )
    except:
        pass

    try:
        proc.terminate()
    except:
        pass

    return screenshots


def generate_app_icon(app_name, icon_name, output_path, size=1024):
    """Generate a simple app icon using SF Symbols via swift."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Use a Swift one-liner to render an SF Symbol to PNG
    swift_code = f'''
import AppKit

let config = NSImage.SymbolConfiguration(pointSize: 400, weight: .regular)
guard let baseImage = NSImage(systemSymbolName: "{icon_name}", accessibilityDescription: nil) else {{ exit(1) }}
let image = baseImage.withSymbolConfiguration(config) ?? baseImage

let targetSize = NSSize(width: {size}, height: {size})
let finalImage = NSImage(size: targetSize)
finalImage.lockFocus()
NSGraphicsContext.current?.imageFlipped = false

// Orange background
NSColor(red: 0.05, green: 0.05, blue: 0.05, alpha: 1.0).setFill()
NSRect(origin: .zero, size: targetSize).fill()

// Draw symbol centered
let symbolSize = image.size
let scale = min(targetSize.width / symbolSize.width, targetSize.height / symbolSize.height) * 0.6
let drawWidth = symbolSize.width * scale
let drawHeight = symbolSize.height * scale
let drawX = (targetSize.width - drawWidth) / 2
let drawY = (targetSize.height - drawHeight) / 2
image.draw(in: NSRect(x: drawX, y: drawY, width: drawWidth, height: drawHeight),
           from: .zero, operation: .sourceOver, fraction: 1.0)

finalImage.unlockFocus()

guard let tiffData = finalImage.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiffData),
      let pngData = rep.representation(using: .png, properties: [:]) else {{ exit(1) }}

try? pngData.write(to: URL(fileURLWithPath: "{output_path}"))
'''

    swift_file = output_path.parent / f"{app_name}_icon_gen.swift"
    swift_file.write_text(swift_code)

    r = subprocess.run(
        ["swift", str(swift_file)],
        capture_output=True, text=True, timeout=30
    )

    swift_file.unlink(missing_ok=True)

    if output_path.exists():
        return str(output_path)
    return None


def create_iconset(app_name, icon_name, output_dir):
    """Create a proper .iconset with all required sizes for App Store."""
    output_dir = Path(output_dir)
    iconset_dir = output_dir / f"{app_name}.iconset"
    iconset_dir.mkdir(parents=True, exist_ok=True)

    # Generate the base 1024x1024 icon
    base_icon = output_dir / f"{app_name}_base.png"
    base_path = generate_app_icon(app_name, icon_name, base_icon)

    if not base_path:
        return None

    # Create all required sizes
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    base_img = Image.open(base_path)

    for size in sizes:
        # Regular
        resized = base_img.resize((size, size), Image.LANCZOS)
        resized.save(str(iconset_dir / f"icon_{size}x{size}.png"))

        # Retina (@2x)
        if size * 2 <= 1024:
            resized2x = base_img.resize((size * 2, size * 2), Image.LANCZOS)
            resized2x.save(str(iconset_dir / f"icon_{size}x{size}@2x.png"))

    # Convert to .icns
    icns_path = output_dir / f"{app_name}.icns"
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
        capture_output=True, text=True, timeout=10
    )

    # Cleanup
    base_icon.unlink(missing_ok=True)

    if icns_path.exists():
        return str(icns_path)
    return None
