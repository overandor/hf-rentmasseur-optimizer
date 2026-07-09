APP_NAME    = AirPlayAgent
APP_DIR     = build/$(APP_NAME).app
EXECUTABLE  = $(APP_NAME)
SOURCES     = $(wildcard Sources/AirPlayAgent/*.swift)
INFO_PLIST  = Resources/Info.plist
ENTITLEMENTS = Resources/AirPlayAgent.entitlements
PRIVACY     = Resources/PrivacyInfo.xcprivacy
MACOSX_DEPLOYMENT_TARGET = 14.0

SWIFT_FLAGS = \
	-sdk $(shell xcrun --sdk macosx --show-sdk-path) \
	-target $(shell uname -m)-apple-macosx$(MACOSX_DEPLOYMENT_TARGET) \
	-framework SwiftUI -framework AppKit -framework AVFoundation -framework AVKit \
	-parse-as-library

.PHONY: all clean run

all: $(APP_DIR)

$(APP_DIR): $(SOURCES) $(INFO_PLIST) $(ENTITLEMENTS) $(PRIVACY)
	@echo "Building $(APP_NAME)..."
	@mkdir -p $(APP_DIR)/Contents/MacOS
	@mkdir -p $(APP_DIR)/Contents/Resources
	@cp $(INFO_PLIST) $(APP_DIR)/Contents/Info.plist
	@cp $(PRIVACY) $(APP_DIR)/Contents/Resources/PrivacyInfo.xcprivacy
	@swiftc $(SWIFT_FLAGS) $(SOURCES) -o $(APP_DIR)/Contents/MacOS/$(EXECUTABLE)
	@echo "Built: $(APP_DIR)"

run: $(APP_DIR)
	@open $(APP_DIR)

clean:
	@rm -rf build
	@echo "Cleaned."
