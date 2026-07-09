APP_NAME    = SamsungCast
APP_DIR     = build/$(APP_NAME).app
EXECUTABLE  = SamsungCast
SOURCES     = $(wildcard src/*.cpp) $(wildcard src/*.mm)
INFO_PLIST  = Resources/Info.plist
MACOSX_DEPLOYMENT_TARGET = 14.0

CXX         = clang++
CXXFLAGS    = -std=c++17 -Wall -Wextra -O2 -stdlib=libc++ -fobjc-arc
OBJCFLAGS   = -x objective-c++ -std=c++17 -Wall -Wextra -O2 -stdlib=libc++ -fobjc-arc

FRAMEWORKS  = -framework AppKit -framework CoreGraphics -framework CoreVideo \
              -framework VideoToolbox -framework CoreMedia -framework IOSurface \
              -framework Foundation -framework ScreenCaptureKit

SDK         = $(shell xcrun --sdk macosx --show-sdk-path)
TARGET      = $(shell uname -m)-apple-macosx$(MACOSX_DEPLOYMENT_TARGET)

BUILD_DIR   = build
OBJ_DIR     = build/obj
BIN         = $(BUILD_DIR)/$(EXECUTABLE)

CPP_SRCS    = $(wildcard src/*.cpp)
MM_SRCS     = $(wildcard src/*.mm)
CPP_OBJS    = $(patsubst src/%.cpp,$(OBJ_DIR)/%.o,$(CPP_SRCS))
MM_OBJS     = $(patsubst src/%.mm,$(OBJ_DIR)/%.o,$(MM_SRCS))

.PHONY: all clean run

all: $(APP_DIR)

$(APP_DIR): $(BIN) $(INFO_PLIST)
	@echo "Packaging $(APP_NAME)..."
	@mkdir -p $(APP_DIR)/Contents/MacOS
	@mkdir -p $(APP_DIR)/Contents/Resources
	@cp $(INFO_PLIST) $(APP_DIR)/Contents/Info.plist
	@cp $(BIN) $(APP_DIR)/Contents/MacOS/$(EXECUTABLE)
	@echo "Built: $(APP_DIR)"

$(BIN): $(CPP_OBJS) $(MM_OBJS)
	@mkdir -p $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $^ -o $@ $(FRAMEWORKS) -lpthread

$(OBJ_DIR)/%.o: src/%.cpp
	@mkdir -p $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) -isysroot $(SDK) -target $(TARGET) -c $< -o $@

$(OBJ_DIR)/%.o: src/%.mm
	@mkdir -p $(OBJ_DIR)
	$(CXX) $(OBJCFLAGS) -isysroot $(SDK) -target $(TARGET) -c $< -o $@

run: $(APP_DIR)
	@open $(APP_DIR)

clean:
	rm -rf $(BUILD_DIR)
