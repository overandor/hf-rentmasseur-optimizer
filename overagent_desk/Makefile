APP_NAME = OverAgentDesk
BUILD_DIR = build
APP_BUNDLE = $(BUILD_DIR)/$(APP_NAME).app
ENTITLEMENTS = Resources/OverAgentDesk.entitlements
INFO_PLIST = Resources/Info.plist

SOURCES = $(wildcard Sources/OverAgentDesk/*.swift)
RESOURCES = $(INFO_PLIST) $(ENTITLEMENTS)

SWIFTC = swiftc
SWIFT_FLAGS = -framework SwiftUI -framework AppKit -framework Network -framework CryptoKit -framework Charts

.PHONY: all clean run

all: $(APP_BUNDLE)

$(APP_BUNDLE): $(SOURCES) $(RESOURCES)
	@echo "Building $(APP_NAME)..."
	@mkdir -p $(BUILD_DIR)
	$(SWIFTC) $(SOURCES) $(SWIFT_FLAGS) -o $(BUILD_DIR)/$(APP_NAME)
	@mkdir -p $(APP_BUNDLE)/Contents/MacOS
	@mkdir -p $(APP_BUNDLE)/Contents/Resources
	@cp $(BUILD_DIR)/$(APP_NAME) $(APP_BUNDLE)/Contents/MacOS/
	@cp $(INFO_PLIST) $(APP_BUNDLE)/Contents/
	@cp $(ENTITLEMENTS) $(APP_BUNDLE)/Contents/Resources/
	@echo "Built: $(APP_BUNDLE)"

run: $(APP_BUNDLE)
	open $(APP_BUNDLE)

clean:
	rm -rf $(BUILD_DIR)
	@echo "Cleaned."
