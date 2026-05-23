cmake_minimum_required(VERSION 3.13)

# Include Pico SDK
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(aquaculture_firmware C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialize Pico SDK
pico_sdk_init()

# Add executable
add_executable(aquaculture
    main.c
)

# Link libraries
target_link_libraries(aquaculture
    pico_stdlib
    pico_cyw43_arch_lwip_threadsafe_background
    hardware_adc
)

# Enable USB output, disable UART output
pico_enable_stdio_usb(aquaculture 1)
pico_enable_stdio_uart(aquaculture 0)

# Create map/bin/hex/uf2 files
pico_add_extra_outputs(aquaculture)
