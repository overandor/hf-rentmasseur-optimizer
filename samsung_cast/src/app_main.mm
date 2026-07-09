#import <AppKit/AppKit.h>
#import "glass_ui.h"
#include "cast_controller.h"
#include <memory>

@interface CastAppDelegate : NSObject <NSApplicationDelegate>
@property (nonatomic, strong) GlassMainWindow *window;
@property (nonatomic, strong) CastViewController *viewController;
@end

@implementation CastAppDelegate {
    std::shared_ptr<CastController> _controller;
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    NSApplication *app = [NSApplication sharedApplication];
    app.activationPolicy = NSApplicationActivationPolicyRegular;

    _controller = std::make_shared<CastController>();

    NSRect frame = NSMakeRect(0, 0, 960, 640);
    self.window = [[GlassMainWindow alloc]
        initWithContentRect:frame
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
        backing:NSBackingStoreBuffered
        defer:NO];

    self.viewController = [[CastViewController alloc] initWithController:_controller];
    self.window.contentViewController = self.viewController;

    [self.window center];
    [self.window makeKeyAndOrderFront:self];

    [app activateIgnoringOtherApps:YES];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    return YES;
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    if (self.controller) {
        self.controller->stopStreaming();
    }
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        CastAppDelegate *delegate = [[CastAppDelegate alloc] init];
        app.delegate = delegate;

        NSDictionary *infoDict = @{
            @"NSHighResolutionCapable": @YES,
            @"LSUIElement": @NO,
        };
        [[NSBundle mainBundle] setValue:infoDict forKey:@"__dummy"];

        [app run];
    }
    return 0;
}
