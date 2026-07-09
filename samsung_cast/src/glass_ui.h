#pragma once
#include <AppKit/AppKit.h>
#include "cast_controller.h"

@interface GlassMainWindow : NSWindow
@end

@interface CastViewController : NSViewController
- (instancetype)initWithController:(std::shared_ptr<CastController>)controller;
@end

@interface LLMCommandBar : NSView
- (instancetype)initWithController:(std::shared_ptr<CastController>)controller;
- (void)updateConnectionState:(BOOL)connected model:(NSString *)model;
@end

@interface StatsPanel : NSView
- (void)updateStats:(const StreamStats &)stats;
- (void)updateState:(CastState)state;
@end

@interface DeviceListPanel : NSView
- (void)updateDevices:(const std::vector<DLNADevice> &)devices
    controller:(std::shared_ptr<CastController>)controller;
@end

@interface LogPanel : NSView
- (void)appendLog:(NSString *)msg;
@end

@interface DisplayPicker : NSView
- (instancetype)initWithController:(std::shared_ptr<CastController>)controller;
@end
