#!/usr/bin/env python3
"""Jorki menubar app — sits in macOS status bar, copy URL or open in browser."""

import subprocess
import sys

JORKI_URL = "https://josephrw-llm-file-proxy.hf.space"

def main():
    # Use osascript to create a simple menubar item via NSStatusItem
    script = f'''
use framework "AppKit"
use framework "Foundation"
use scripting additions

set statusBar to current application's NSStatusBar's systemStatusBar()
set statusItem to statusBar's statusItemWithLength:(current application's NSVariableStatusItemLength)
statusItem's setTitle:"◉"
statusItem's setHighlightMode:true

set theMenu to current application's NSMenu's alloc()'s init()

-- "Copy URL" menu item
set copyItem to current application's NSMenuItem's alloc()'s initWithTitle:"Copy URL" action:"copyUrl:" keyEquivalent:""
copyItem's setTarget:me
copyItem's setEnabled:true
theMenu's addItem:copyItem

-- "Open in Browser" menu item
set openItem to current application's NSMenuItem's alloc()'s initWithTitle:"Open in Browser" action:"openBrowser:" keyEquivalent:""
openItem's setTarget:me
openItem's setEnabled:true
theMenu's addItem:openItem

-- Separator
theMenu's addItem:(current application's NSMenuItem's separatorItem())

-- "Quit" menu item
set quitItem to current application's NSMenuItem's alloc()'s initWithTitle:"Quit Jorki" action:"quitApp:" keyEquivalent:"q"
quitItem's setTarget:me
theMenu's addItem:quitItem

statusItem's setMenu:theMenu

on copyUrl:sender
    set theClipboard to current application's NSPasteboard's generalPasteboard()
    theClipboard's clearContents()
    theClipboard's setString:"{JORKI_URL}" forType:(current application's NSStringPboardType)
end copyUrl:

on openBrowser:sender
    do shell script "open '{JORKI_URL}'"
end openBrowser:

on quitApp:sender
    current application's NSApp's terminate:(missing value)
end quitApp:

-- Keep the app running
current application's NSApp's run()
'''
    subprocess.run(["osascript", "-l", "AppleScript", "-e", script])

if __name__ == "__main__":
    main()
