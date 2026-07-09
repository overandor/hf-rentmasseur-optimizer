APP_NAME    = TVHub
APP_DIR     = build/$(APP_NAME).app
EXECUTABLE  = $(APP_NAME)
SOURCES     = $(wildcard Sources/TVHub/*.swift)
INFO_PLIST  = Resources/Info.plist
ENTITLEMENTS = Resources/TVHub.entitlements
MACOSX_DEPLOYMENT_TARGET = 14.0

SWIFT_FLAGS = \
	-sdk $(shell xcrun --sdk macosx --show-sdk-path) \
	-target $(shell uname -m)-apple-macosx$(MACOSX_DEPLOYMENT_TARGET) \
	-framework SwiftUI -framework AppKit -framework AVFoundation -framework AVKit \
	-framework MediaPlayer -framework CoreGraphics \
	-parse-as-library

.PHONY: all clean run

all: $(APP_DIR)

$(APP_DIR): $(SOURCES) $(INFO_PLIST) $(ENTITLEMENTS)
	@echo "Building $(APP_NAME)..."
	@mkdir -p $(APP_DIR)/Contents/MacOS
	@mkdir -p $(APP_DIR)/Contents/Resources
	@cp $(INFO_PLIST) $(APP_DIR)/Contents/Info.plist
	@cp $(ENTITLEMENTS) $(APP_DIR)/Contents/TVHub.entitlements
	@swiftc $(SWIFT_FLAGS) $(SOURCES) -o $(APP_DIR)/Contents/MacOS/$(EXECUTABLE)
	@echo "Built: $(APP_DIR)"

run: $(APP_DIR)
	@open $(APP_DIR)

clean:
	@rm -rf build
	@echo "Cleaned."
