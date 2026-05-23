#!/bin/bash
# Build script for Pico WH firmware

set -e

echo "=========================================="
echo "  Building Pico WH Firmware"
echo "=========================================="

# Check if Pico SDK is installed
if [ -z "$PICO_SDK_PATH" ]; then
    echo "Error: PICO_SDK_PATH not set"
    echo ""
    echo "Install Pico SDK first:"
    echo "  cd ~"
    echo "  git clone https://github.com/raspberrypi/pico-sdk.git"
    echo "  cd pico-sdk"
    echo "  git submodule update --init"
    echo "  export PICO_SDK_PATH=~/pico-sdk"
    echo ""
    echo "Add to ~/.bashrc:"
    echo "  export PICO_SDK_PATH=~/pico-sdk"
    exit 1
fi

# Check if ARM toolchain is installed
if ! command -v arm-none-eabi-gcc &> /dev/null; then
    echo "Error: ARM toolchain not installed"
    echo ""
    echo "Install toolchain:"
    echo "  sudo apt install cmake gcc-arm-none-eabi libnewlib-arm-none-eabi build-essential"
    exit 1
fi

# Create build directory
mkdir -p build
cd build

# Configure
echo ""
echo "Configuring..."
cmake ..

# Build
echo ""
echo "Building..."
make -j$(nproc)

# Check output
if [ -f aquaculture_monitoring.uf2 ]; then
    echo ""
    echo "=========================================="
    echo "  Build SUCCESS!"
    echo "=========================================="
    echo "Output: build/aquaculture_monitoring.uf2"
    echo ""
    echo "To flash:"
    echo "  1. Hold BOOTSEL button on Pico WH"
    echo "  2. Connect USB to computer"
    echo "  3. Copy aquaculture_monitoring.uf2 to RPI-RP2 drive"
    echo "=========================================="
else
    echo ""
    echo "Build FAILED!"
    exit 1
fi
