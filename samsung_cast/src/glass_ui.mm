#import "glass_ui.h"
#include <sstream>
#include <algorithm>

#pragma mark - GlassMainWindow

@implementation GlassMainWindow

- (instancetype)initWithContentRect:(NSRect)contentRect
    styleMask:(NSWindowStyleMask)style
    backing:(NSBackingStoreType)backingStore
    defer:(BOOL)flag {
    self = [super initWithContentRect:contentRect
        styleMask:style | NSWindowStyleMaskFullSizeContentView
        backing:backingStore
        defer:flag];
    if (self) {
        self.titlebarAppearsTransparent = YES;
        self.titleVisibility = NSWindowTitleHidden;
        self.appearance = [NSAppearance appearanceNamed:NSAppearanceNameVibrantDark];
        self.backgroundColor = [NSColor clearColor];
        self.isOpaque = NO;
        self.hasShadow = YES;
        self.movableByWindowBackground = YES;
    }
    return self;
}

@end

#pragma mark - StatsPanel

@interface StatsPanel()
@property (nonatomic, strong) NSTextField *glyphLabel;
@property (nonatomic, strong) NSTextField *stateLabel;
@property (nonatomic, strong) NSTextField *codecLabel;
@property (nonatomic, strong) NSTextField *resolutionLabel;
@property (nonatomic, strong) NSTextField *fpsLabel;
@property (nonatomic, strong) NSTextField *bitrateLabel;
@property (nonatomic, strong) NSTextField *portLabel;
@property (nonatomic, strong) NSTextField *clientsLabel;
@property (nonatomic, strong) NSBox *box;
@end

@implementation StatsPanel

- (instancetype)initWithFrame:(NSRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        [self buildUI];
    }
    return self;
}

- (void)buildUI {
    self.wantsLayer = YES;
    self.layer.cornerRadius = 12;
    self.layer.borderWidth = 0.5;
    self.layer.borderColor = [NSColor colorWithWhite:1.0 alpha:0.08].CGColor;

    NSVisualEffectView *blur = [[NSVisualEffectView alloc] initWithFrame:self.bounds];
    blur.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    blur.blendingMode = NSVisualEffectBlendingModeWithinWindow;
    blur.material = NSVisualEffectMaterialHudWindow;
    blur.state = NSVisualEffectStateActive;
    [self addSubview:blur];

    NSFont *mono = [NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightMedium];
    NSFont *monoSmall = [NSFont monospacedSystemFontOfSize:9 weight:NSFontWeightRegular];
    NSFont *monoBig = [NSFont monospacedSystemFontOfSize:14 weight:NSFontWeightBold];

    self.glyphLabel = [self makeLabel:@"◌ IDLE" font:monoBig color:[NSColor colorWithSRGBRed:1.0 green:0.55 blue:0.0 alpha:1.0]];
    self.glyphLabel.frame = NSMakeRect(16, frame.size.height - 30, 200, 20);
    [self addSubview:self.glyphLabel];

    self.stateLabel = [self makeLabel:@"awaiting command" font:monoSmall color:[NSColor secondaryLabelColor]];
    self.stateLabel.frame = NSMakeRect(16, frame.size.height - 46, 250, 14);
    [self addSubview:self.stateLabel];

    NSColor *labelColor = [NSColor colorWithWhite:0.6 alpha:1.0];
    NSColor *valueColor = [NSColor colorWithWhite:0.9 alpha:1.0];

    CGFloat y = frame.size.height - 72;
    CGFloat x1 = 16, x2 = 140, x3 = 260;

    self.codecLabel = [self makeStatRow:@"codec" value:@"—" x:x1 y:y labelFont:monoSmall valueFont:mono labelColor:labelColor valueColor:valueColor];
    self.resolutionLabel = [self makeStatRow:@"resolution" value:@"—" x:x2 y:y labelFont:monoSmall valueFont:mono labelColor:labelColor valueColor:valueColor];
    self.fpsLabel = [self makeStatRow:@"fps" value:@"—" x:x3 y:y labelFont:monoSmall valueFont:mono labelColor:labelColor valueColor:valueColor];

    y -= 24;
    self.bitrateLabel = [self makeStatRow:@"bitrate" value:@"—" x:x1 y:y labelFont:monoSmall valueFont:mono labelColor:labelColor valueColor:valueColor];
    self.portLabel = [self makeStatRow:@"port" value:@"—" x:x2 y:y labelFont:monoSmall valueFont:mono labelColor:labelColor valueColor:valueColor];
    self.clientsLabel = [self makeStatRow:@"clients" value:@"0" x:x3 y:y labelFont:monoSmall valueFont:mono labelColor:labelColor valueColor:valueColor];
}

- (NSTextField *)makeLabel:(NSString *)text font:(NSFont *)font color:(NSColor *)color {
    NSTextField *label = [[NSTextField alloc] init];
    label.stringValue = text;
    label.font = font;
    label.textColor = color;
    label.backgroundColor = [NSColor clearColor];
    label.bezeled = NO;
    label.editable = NO;
    label.selectable = NO;
    [label sizeToFit];
    return label;
}

- (NSTextField *)makeStatRow:(NSString *)label value:(NSString *)value x:(CGFloat)x y:(CGFloat)y
    labelFont:(NSFont *)lf valueFont:(NSFont *)vf labelColor:(NSColor *)lc valueColor:(NSColor *)vc {
    NSTextField *l = [self makeLabel:label font:lf color:lc];
    l.frame = NSMakeRect(x, y, 100, 14);
    [self addSubview:l];

    NSTextField *v = [self makeLabel:value font:vf color:vc];
    v.frame = NSMakeRect(x, y - 14, 120, 16);
    [self addSubview:v];

    return v;
}

- (void)updateStats:(const StreamStats &)stats {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.codecLabel.stringValue = stats.codec;
        self.resolutionLabel.stringValue = [NSString stringWithFormat:@"%dx%d", stats.width, stats.height];
        self.fpsLabel.stringValue = [NSString stringWithFormat:@"%d", stats.fps];
        self.bitrateLabel.stringValue = [NSString stringWithFormat:@"%.1f Mbps", stats.bitrate / 1000000.0];
        self.portLabel.stringValue = [NSString stringWithFormat:@"%d", stats.port];
        self.clientsLabel.stringValue = [NSString stringWithFormat:@"%d", stats.clientCount];
    });
}

- (void)updateState:(CastState)state {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSString *glyph, *desc;
        NSColor *color;

        switch (state) {
            case CastState::Idle:
                glyph = @"◌ IDLE";
                desc = @"awaiting command";
                color = [NSColor colorWithWhite:0.5 alpha:1.0];
                break;
            case CastState::Discovering:
                glyph = @"⌁ DISCOVERING";
                desc = @"scanning network for DLNA devices";
                color = [NSColor colorWithSRGBRed:1.0 green:0.55 blue:0.0 alpha:1.0];
                break;
            case CastState::Streaming:
                glyph = @"◉ STREAMING";
                desc = @"live capture → HEVC → TS → HTTP";
                color = [NSColor colorWithSRGBRed:0.0 green:0.9 blue:0.3 alpha:1.0];
                break;
            case CastState::Casting:
                glyph = @"◆ CASTING";
                desc = @"stream sent to TV via DLNA";
                color = [NSColor colorWithSRGBRed:0.0 green:0.95 blue:0.5 alpha:1.0];
                break;
            case CastState::Error:
                glyph = @"⟁ ERROR";
                desc = @"check logs below";
                color = [NSColor colorWithSRGBRed:0.9 green:0.2 blue:0.2 alpha:1.0];
                break;
        }

        self.glyphLabel.stringValue = glyph;
        self.glyphLabel.textColor = color;
        self.stateLabel.stringValue = desc;
    });
}

@end

#pragma mark - DeviceListPanel

@interface DeviceListPanel()
@property (nonatomic, strong) NSVisualEffectView *blur;
@property (nonatomic, strong) NSStackView *stack;
@property (nonatomic, strong) NSTextField *header;
@property (nonatomic, strong) NSTextField *emptyLabel;
@property (nonatomic, strong) NSButton *refreshBtn;
@property (nonatomic, weak) NSView *selectedView;
@property (nonatomic, strong) std::shared_ptr<CastController> controller;
@end

@implementation DeviceListPanel

- (instancetype)initWithFrame:(NSRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        [self buildUI];
    }
    return self;
}

- (void)buildUI {
    self.wantsLayer = YES;
    self.layer.cornerRadius = 12;
    self.layer.borderWidth = 0.5;
    self.layer.borderColor = [NSColor colorWithWhite:1.0 alpha:0.08].CGColor;

    _blur = [[NSVisualEffectView alloc] initWithFrame:self.bounds];
    _blur.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    _blur.blendingMode = NSVisualEffectBlendingModeWithinWindow;
    _blur.material = NSVisualEffectMaterialHudWindow;
    _blur.state = NSVisualEffectStateActive;
    [self addSubview:_blur];

    _header = [[NSTextField alloc] init];
    _header.stringValue = @"◈ DEVICES";
    _header.font = [NSFont monospacedSystemFontOfSize:12 weight:NSFontWeightBold];
    _header.textColor = [NSColor colorWithSRGBRed:1.0 green:0.55 blue:0.0 alpha:1.0];
    _header.backgroundColor = [NSColor clearColor];
    _header.bezeled = NO;
    _header.editable = NO;
    [_header sizeToFit];
    _header.frame = NSMakeRect(14, self.bounds.size.height - 24, 120, 18);
    [self addSubview:_header];

    _refreshBtn = [[NSButton alloc] init];
    _refreshBtn.title = @"⟳ scan";
    _refreshBtn.font = [NSFont monospacedSystemFontOfSize:10 weight:NSFontWeightMedium];
    _refreshBtn.bezelStyle = NSBezelStyleRoundRect;
    _refreshBtn.target = self;
    _refreshBtn.action = @selector(refresh);
    [_refreshBtn sizeToFit];
    _refreshBtn.frame = NSMakeRect(self.bounds.size.width - 80, self.bounds.size.height - 24, 66, 20);
    [self addSubview:_refreshBtn];

    _stack = [[NSStackView alloc] initWithFrame:NSMakeRect(8, 8, self.bounds.size.width - 16, self.bounds.size.height - 44)];
    _stack.orientation = NSUserInterfaceLayoutOrientationVertical;
    _stack.alignment = NSLayoutAttributeLeading;
    _stack.spacing = 6;
    _stack.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    [self addSubview:_stack];

    _emptyLabel = [[NSTextField alloc] init];
    _emptyLabel.stringValue = @"◌ no devices — click scan";
    _emptyLabel.font = [NSFont monospacedSystemFontOfSize:10 weight:NSFontWeightRegular];
    _emptyLabel.textColor = [NSColor secondaryLabelColor];
    _emptyLabel.backgroundColor = [NSColor clearColor];
    _emptyLabel.bezeled = NO;
    _emptyLabel.editable = NO;
    [_emptyLabel sizeToFit];
    [_stack addArrangedSubview:_emptyLabel];
}

- (void)refresh {
    if (_controller) _controller->discoverDevices();
}

- (void)updateDevices:(const std::vector<DLNADevice> &)devices
    controller:(std::shared_ptr<CastController>)controller {
    _controller = controller;

    dispatch_async(dispatch_get_main_queue(), ^{
        for (NSView *v in [_stack arrangedSubviews]) {
            [_stack removeArrangedSubview:v];
            [v removeFromSuperview];
        }

        if (devices.empty()) {
            [_stack addArrangedSubview:self.emptyLabel];
            return;
        }

        for (size_t i = 0; i < devices.size(); i++) {
            const DLNADevice &dev = devices[i];

            NSView *row = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, self.bounds.size.width - 16, 40)];
            row.wantsLayer = YES;
            row.layer.cornerRadius = 8;
            row.layer.borderWidth = 0.5;
            row.layer.borderColor = [NSColor colorWithWhite:1.0 alpha:0.06].CGColor;

            NSTextField *glyph = [[NSTextField alloc] init];
            glyph.stringValue = @"◉";
            glyph.font = [NSFont monospacedSystemFontOfSize:14 weight:NSFontWeightBold];
            glyph.textColor = [NSColor colorWithSRGBRed:1.0 green:0.55 blue:0.0 alpha:1.0];
            glyph.backgroundColor = [NSColor clearColor];
            glyph.bezeled = NO;
            glyph.editable = NO;
            [glyph sizeToFit];
            glyph.frame = NSMakeRect(8, 12, 20, 18);
            [row addSubview:glyph];

            NSTextField *name = [[NSTextField alloc] init];
            name.stringValue = [NSString stringWithUTF8String:dev.friendlyName.c_str()];
            name.font = [NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightMedium];
            name.textColor = [NSColor colorWithWhite:0.9 alpha:1.0];
            name.backgroundColor = [NSColor clearColor];
            name.bezeled = NO;
            name.editable = NO;
            [name sizeToFit];
            name.frame = NSMakeRect(30, 18, 200, 16);
            [row addSubview:name];

            NSTextField *ip = [[NSTextField alloc] init];
            std::string loc = dev.location;
            size_t s = loc.find("://");
            size_t h = (s != std::string::npos) ? s + 3 : 0;
            size_t e = loc.find('/', h);
            std::string hostPort = (e != std::string::npos) ? loc.substr(h, e - h) : loc.substr(h);
            ip.stringValue = [NSString stringWithUTF8String:hostPort.c_str()];
            ip.font = [NSFont monospacedSystemFontOfSize:9 weight:NSFontWeightRegular];
            ip.textColor = [NSColor colorWithWhite:0.5 alpha:1.0];
            ip.backgroundColor = [NSColor clearColor];
            ip.bezeled = NO;
            ip.editable = NO;
            [ip sizeToFit];
            ip.frame = NSMakeRect(30, 4, 200, 12);
            [row addSubview:ip];

            NSButton *castBtn = [[NSButton alloc] init];
            castBtn.title = @"cast →";
            castBtn.font = [NSFont monospacedSystemFontOfSize:10 weight:NSFontWeightBold];
            castBtn.bezelStyle = NSBezelStyleRoundRect;
            castBtn.target = self;
            castBtn.action = @selector(castToDevice:);
            castBtn.tag = (NSInteger)i;
            [castBtn sizeToFit];
            castBtn.frame = NSMakeRect(row.bounds.size.width - 70, 10, 60, 20);
            [row addSubview:castBtn];

            [_stack addArrangedSubview:row];
        }
    });
}

- (void)castToDevice:(NSButton *)sender {
    if (!_controller) return;
    auto devices = _controller->getDiscoveredDevices();
    NSInteger idx = sender.tag;
    if (idx >= 0 && idx < (NSInteger)devices.size()) {
        _controller->castToDevice(devices[idx]);
    }
}

@end

#pragma mark - LogPanel

@interface LogPanel()
@property (nonatomic, strong) NSVisualEffectView *blur;
@property (nonatomic, strong) NSScrollView *scrollView;
@property (nonatomic, strong) NSTextView *textView;
@property (nonatomic, strong) NSTextField *header;
@end

@implementation LogPanel

- (instancetype)initWithFrame:(NSRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        [self buildUI];
    }
    return self;
}

- (void)buildUI {
    self.wantsLayer = YES;
    self.layer.cornerRadius = 12;
    self.layer.borderWidth = 0.5;
    self.layer.borderColor = [NSColor colorWithWhite:1.0 alpha:0.08].CGColor;

    _blur = [[NSVisualEffectView alloc] initWithFrame:self.bounds];
    _blur.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    _blur.blendingMode = NSVisualEffectBlendingModeWithinWindow;
    _blur.material = NSVisualEffectMaterialHudWindow;
    _blur.state = NSVisualEffectStateActive;
    [self addSubview:_blur];

    _header = [[NSTextField alloc] init];
    _header.stringValue = @"◈ SIGNAL LOG";
    _header.font = [NSFont monospacedSystemFontOfSize:12 weight:NSFontWeightBold];
    _header.textColor = [NSColor colorWithSRGBRed:1.0 green:0.55 blue:0.0 alpha:1.0];
    _header.backgroundColor = [NSColor clearColor];
    _header.bezeled = NO;
    _header.editable = NO;
    [_header sizeToFit];
    _header.frame = NSMakeRect(14, self.bounds.size.height - 24, 120, 18);
    [self addSubview:_header];

    _scrollView = [[NSScrollView alloc] initWithFrame:NSMakeRect(8, 8, self.bounds.size.width - 16, self.bounds.size.height - 40)];
    _scrollView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    _scrollView.hasVerticalScroller = YES;
    _scrollView.autohidesScrollers = YES;
    _scrollView.drawsBackground = NO;

    _textView = [[NSTextView alloc] initWithFrame:_scrollView.bounds];
    _textView.font = [NSFont monospacedSystemFontOfSize:10 weight:NSFontWeightRegular];
    _textView.textColor = [NSColor colorWithWhite:0.7 alpha:1.0];
    _textView.backgroundColor = [NSColor clearColor];
    _textView.editable = NO;
    _textView.selectable = YES;
    _textView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    _textView.textContainerInset = NSMakeSize(6, 4);
    _textView.textContainer.lineFragmentPadding = 0;

    _scrollView.documentView = _textView;
    [self addSubview:_scrollView];
}

- (void)appendLog:(NSString *)msg {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSAttributedString *attr = [[NSAttributedString alloc] initWithString:msg
            attributes:@{
                NSFontAttributeName: [NSFont monospacedSystemFontOfSize:10 weight:NSFontWeightRegular],
                NSForegroundColorAttributeName: [NSColor colorWithWhite:0.7 alpha:1.0]
            }];

        [_textView.textStorage appendAttributedString:attr];
        [_textView.textStorage appendAttributedString:[[NSAttributedString alloc] initWithString:@"\n"]];

        [_textView scrollRangeToVisible:NSMakeRange(_textView.string.length, 0)];

        if (_textView.string.length > 10000) {
            NSRange range = NSMakeRange(0, _textView.string.length - 5000);
            [_textView.string deleteCharactersInRange:range];
        }
    });
}

@end

#pragma mark - LLMCommandBar

@interface LLMCommandBar()
@property (nonatomic, strong) NSVisualEffectView *blur;
@property (nonatomic, strong) NSTextField *inputField;
@property (nonatomic, strong) NSButton *sendBtn;
@property (nonatomic, strong) NSTextField *llmStatus;
@property (nonatomic, strong) NSProgressIndicator *spinner;
@property (nonatomic, strong) std::shared_ptr<CastController> controller;
@end

@implementation LLMCommandBar

- (instancetype)initWithFrame:(NSRect)frame controller:(std::shared_ptr<CastController>)controller {
    self = [super initWithFrame:frame];
    if (self) {
        _controller = controller;
        [self buildUI];
    }
    return self;
}

- (void)buildUI {
    self.wantsLayer = YES;
    self.layer.cornerRadius = 12;
    self.layer.borderWidth = 0.5;
    self.layer.borderColor = [NSColor colorWithWhite:1.0 alpha:0.08].CGColor;

    _blur = [[NSVisualEffectView alloc] initWithFrame:self.bounds];
    _blur.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    _blur.blendingMode = NSVisualEffectBlendingModeWithinWindow;
    _blur.material = NSVisualEffectMaterialHudWindow;
    _blur.state = NSVisualEffectStateActive;
    [self addSubview:_blur];

    NSTextField *prompt = [[NSTextField alloc] init];
    prompt.stringValue = @"⟡";
    prompt.font = [NSFont monospacedSystemFontOfSize:18 weight:NSFontWeightBold];
    prompt.textColor = [NSColor colorWithSRGBRed:1.0 green:0.55 blue:0.0 alpha:1.0];
    prompt.backgroundColor = [NSColor clearColor];
    prompt.bezeled = NO;
    prompt.editable = NO;
    [prompt sizeToFit];
    prompt.frame = NSMakeRect(12, 10, 24, 22);
    [self addSubview:prompt];

    _inputField = [[NSTextField alloc] init];
    _inputField.placeholderString = @"tell the agent what to do — \"cast to samsung at 1080p 60fps\"";
    _inputField.font = [NSFont monospacedSystemFontOfSize:12 weight:NSFontWeightRegular];
    _inputField.backgroundColor = [NSColor colorWithWhite:0.1 alpha:0.5];
    _inputField.bezeled = YES;
    _inputField.bezelStyle = NSTextFieldRoundedBezel;
    _inputField.target = self;
    _inputField.action = @selector(send);
    _inputField.frame = NSMakeRect(40, 10, self.bounds.size.width - 160, 24);
    _inputField.autoresizingMask = NSViewWidthSizable;
    [self addSubview:_inputField];

    _sendBtn = [[NSButton alloc] init];
    _sendBtn.title = @"⚡ execute";
    _sendBtn.font = [NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightBold];
    _sendBtn.bezelStyle = NSBezelStyleRounded;
    _sendBtn.target = self;
    _sendBtn.action = @selector(send);
    [_sendBtn sizeToFit];
    _sendBtn.frame = NSMakeRect(self.bounds.size.width - 100, 9, 90, 26);
    _sendBtn.autoresizingMask = NSViewMinXMargin;
    [self addSubview:_sendBtn];

    _llmStatus = [[NSTextField alloc] init];
    _llmStatus.stringValue = @"◌ LLM offline";
    _llmStatus.font = [NSFont monospacedSystemFontOfSize:9 weight:NSFontWeightRegular];
    _llmStatus.textColor = [NSColor colorWithWhite:0.4 alpha:1.0];
    _llmStatus.backgroundColor = [NSColor clearColor];
    _llmStatus.bezeled = NO;
    _llmStatus.editable = NO;
    [_llmStatus sizeToFit];
    _llmStatus.frame = NSMakeRect(40, -2, 200, 12);
    [self addSubview:_llmStatus];
}

- (void)send {
    NSString *text = _inputField.stringValue;
    if (text.length == 0) return;

    if (_controller) {
        _controller->sendLLMCommand([text UTF8String]);
    }

    _inputField.stringValue = @"";
}

- (void)updateConnectionState:(BOOL)connected model:(NSString *)model {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (connected) {
            self.llmStatus.stringValue = [NSString stringWithFormat:@"◆ %@ ready", model];
            self.llmStatus.textColor = [NSColor colorWithSRGBRed:0.0 green:0.8 blue:0.3 alpha:1.0];
        } else {
            self.llmStatus.stringValue = @"◌ LLM offline — start ollama";
            self.llmStatus.textColor = [NSColor colorWithWhite:0.4 alpha:1.0];
        }
    });
}

@end

#pragma mark - DisplayPicker

@interface DisplayPicker()
@property (nonatomic, strong) NSPopUpButton *popup;
@property (nonatomic, strong) std::shared_ptr<CastController> controller;
@property (nonatomic, strong) NSTextField *label;
@end

@implementation DisplayPicker

- (instancetype)initWithFrame:(NSRect)frame controller:(std::shared_ptr<CastController>)controller {
    self = [super initWithFrame:frame];
    if (self) {
        _controller = controller;
        [self buildUI];
    }
    return self;
}

- (void)buildUI {
    _label = [[NSTextField alloc] init];
    _label.stringValue = @"display";
    _label.font = [NSFont monospacedSystemFontOfSize:9 weight:NSFontWeightRegular];
    _label.textColor = [NSColor colorWithWhite:0.5 alpha:1.0];
    _label.backgroundColor = [NSColor clearColor];
    _label.bezeled = NO;
    _label.editable = NO;
    [_label sizeToFit];
    _label.frame = NSMakeRect(0, 16, 50, 12);
    [self addSubview:_label];

    _popup = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(0, 0, 160, 22) pullsDown:NO];
    _popup.target = self;
    _popup.action = @selector(selected:);
    [self addSubview:_popup];

    [self refresh];
}

- (void)refresh {
    if (!_controller) return;
    auto displays = _controller->getDisplays();

    [_popup removeAllItems];

    for (const auto &d : displays) {
        NSString *title = [NSString stringWithFormat:@"[%d] %dx%d%@", d.index, d.width, d.height,
            d.isMain ? @" (main)" : @""];
        [_popup addItemWithTitle:title];
    }
}

- (void)selected:(NSPopUpButton *)sender {
    if (!_controller) return;
    auto displays = _controller->getDisplays();
    NSInteger idx = sender.indexOfSelectedItem;
    if (idx >= 0 && idx < (NSInteger)displays.size()) {
        // Store selection — actual display switch happens on next stream start
    }
}

@end

#pragma mark - CastViewController

@interface CastViewController()
@property (nonatomic, strong) std::shared_ptr<CastController> controller;
@property (nonatomic, strong) StatsPanel *statsPanel;
@property (nonatomic, strong) DeviceListPanel *devicePanel;
@property (nonatomic, strong) LogPanel *logPanel;
@property (nonatomic, strong) LLMCommandBar *commandBar;
@property (nonatomic, strong) DisplayPicker *displayPicker;
@property (nonatomic, strong) NSButton *startBtn;
@property (nonatomic, strong) NSButton *stopBtn;
@property (nonatomic, strong) NSTimer *statsTimer;
@end

@implementation CastViewController

- (instancetype)initWithController:(std::shared_ptr<CastController>)controller {
    self = [super initWithNibName:nil bundle:nil];
    if (self) {
        _controller = controller;
    }
    return self;
}

- (void)loadView {
    NSRect frame = NSMakeRect(0, 0, 960, 640);
    self.view = [[NSView alloc] initWithFrame:frame];
    self.view.wantsLayer = YES;

    NSColor *bgColor = [NSColor colorWithSRGBRed:0.04 green:0.04 blue:0.05 alpha:1.0];
    self.view.layer.backgroundColor = bgColor.CGColor;

    CGFloat pad = 16;
    CGFloat contentW = frame.size.width - pad * 2;

    // Top bar: title + display picker + start/stop
    NSView *topBar = [[NSView alloc] initWithFrame:NSMakeRect(pad, frame.size.height - 52, contentW, 40)];
    [self.view addSubview:topBar];

    NSTextField *title = [[NSTextField alloc] init];
    title.stringValue = @"◈ SAMSUNG CAST";
    title.font = [NSFont monospacedSystemFontOfSize:16 weight:NSFontWeightBold];
    title.textColor = [NSColor colorWithSRGBRed:1.0 green:0.55 blue:0.0 alpha:1.0];
    title.backgroundColor = [NSColor clearColor];
    title.bezeled = NO;
    title.editable = NO;
    [title sizeToFit];
    title.frame = NSMakeRect(0, 8, 200, 24);
    [topBar addSubview:title];

    NSTextField *subtitle = [[NSTextField alloc] init];
    subtitle.stringValue = @"proprietary screen cast control surface";
    subtitle.font = [NSFont monospacedSystemFontOfSize:9 weight:NSFontWeightRegular];
    subtitle.textColor = [NSColor colorWithWhite:0.4 alpha:1.0];
    subtitle.backgroundColor = [NSColor clearColor];
    subtitle.bezeled = NO;
    subtitle.editable = NO;
    [subtitle sizeToFit];
    subtitle.frame = NSMakeRect(0, -4, 250, 12);
    [topBar addSubview:subtitle];

    _displayPicker = [[DisplayPicker alloc] initWithFrame:NSMakeRect(260, 6, 170, 28) controller:_controller];
    [topBar addSubview:_displayPicker];

    _startBtn = [[NSButton alloc] init];
    _startBtn.title = @"◉ start stream";
    _startBtn.font = [NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightBold];
    _startBtn.bezelStyle = NSBezelStyleRounded;
    _startBtn.target = self;
    _startBtn.action = @selector(startStream);
    [_startBtn sizeToFit];
    _startBtn.frame = NSMakeRect(contentW - 200, 6, 95, 28);
    [topBar addSubview:_startBtn];

    _stopBtn = [[NSButton alloc] init];
    _stopBtn.title = @"◌ stop";
    _stopBtn.font = [NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightBold];
    _stopBtn.bezelStyle = NSBezelStyleRounded;
    _stopBtn.target = self;
    _stopBtn.action = @selector(stopStream);
    _stopBtn.enabled = NO;
    [_stopBtn sizeToFit];
    _stopBtn.frame = NSMakeRect(contentW - 95, 6, 80, 28);
    [topBar addSubview:_stopBtn];

    // Stats panel (top-left)
    _statsPanel = [[StatsPanel alloc] initWithFrame:NSMakeRect(pad, frame.size.height - 52 - 16 - 100, contentW, 100)];
    [self.view addSubview:_statsPanel];

    // Middle row: device list (left) + log (right)
    CGFloat midY = pad + 160;
    CGFloat midH = frame.size.height - 52 - 16 - 100 - 16 - 160 - 16;
    CGFloat deviceW = 320;
    CGFloat logW = contentW - deviceW - 12;

    _devicePanel = [[DeviceListPanel alloc] initWithFrame:NSMakeRect(pad, midY, deviceW, midH)];
    [self.view addSubview:_devicePanel];

    _logPanel = [[LogPanel alloc] initWithFrame:NSMakeRect(pad + deviceW + 12, midY, logW, midH)];
    [self.view addSubview:_logPanel];

    // Bottom: LLM command bar
    _commandBar = [[LLMCommandBar alloc] initWithFrame:NSMakeRect(pad, pad, contentW, 48) controller:_controller];
    [self.view addSubview:_commandBar];

    // Wire callbacks
    __weak typeof(self) weakSelf = self;

    _controller->setStateCallback([weakSelf](CastState state) {
        [weakSelf.statsPanel updateState:state];
        BOOL active = (state == CastState::Streaming || state == CastState::Casting);
        weakSelf.startBtn.enabled = !active;
        weakSelf.stopBtn.enabled = active;
    });

    _controller->setStatsCallback([weakSelf](const StreamStats &stats) {
        [weakSelf.statsPanel updateStats:stats];
    });

    _controller->setLogCallback([weakSelf](const std::string &msg) {
        [weakSelf.logPanel appendLog:[NSString stringWithUTF8String:msg.c_str()]];
    });

    _controller->setDeviceCallback([weakSelf](const std::vector<DLNADevice> &devices) {
        [weakSelf.devicePanel updateDevices:devices controller:weakSelf.controller];
    });

    // Check LLM connection
    [self checkLLM];

    // Stats refresh timer
    _statsTimer = [NSTimer scheduledTimerWithTimeInterval:1.0 target:self selector:@selector(refreshStats) userInfo:nil repeats:YES];

    // Auto-discover on launch
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        [weakSelf.controller discoverDevices];
    });
}

- (void)checkLLM {
    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
        __weak typeof(self) weakSelf = self;
        bool connected = self.controller->checkLLMConnection();
        NSString *model = @"llama3";

        if (connected) {
            std::string discovered = self.controller->discoverLLMModel();
            if (!discovered.empty()) {
                model = [NSString stringWithUTF8String:discovered.c_str()];
            }
        }

        [self.commandBar updateConnectionState:connected ? YES : NO model:model];
    });
}

- (void)refreshStats {
    // Stats are pushed via callback, nothing to poll here
}

- (void)startStream {
    auto displays = _controller->getDisplays();
    if (displays.empty()) {
        [_logPanel appendLog:@"⟁ no displays found"];
        return;
    }

    uint32_t displayId = displays[0].id;
    NSInteger sel = _displayPicker.popup.indexOfSelectedItem;
    if (sel >= 0 && sel < (NSInteger)displays.size()) {
        displayId = displays[sel].id;
    }

    _controller->startStreaming(displayId, 1920, 1080, 30, 4000000);
}

- (void)stopStream {
    _controller->stopStreaming();
}

- (void)dealloc {
    [_statsTimer invalidate];
}

@end
