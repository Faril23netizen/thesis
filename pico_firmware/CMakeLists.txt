# == DO NOT EDIT THE FOLLOWING LINES for the Raspberry Pi Pico VS Code Extension to work ==
if(WIN32)
    set(USERHOME $ENV{USERPROFILE})
else()
    set(USERHOME $ENV{HOME})
endif()
set(sdkVersion 2.2.0)
set(toolchainVersion 14_2_Rel1)
set(picotoolVersion 2.2.0-a4)
set(picoVscode ${USERHOME}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${picoVscode})
    include(${picoVscode})
endif()
# ====================================================================================
set(PICO_BOARD pico CACHE STRING "Board type")

cmake_minimum_required(VERSION 3.13)

# Include Pico SDK
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(aquaculture_monitoring C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialize Pico SDK
pico_sdk_init()

# Add executable
add_executable(aquaculture_monitoring
    main.c
    ph_sensor.c
    ds18b20.c
    fql_inference.c
)

# Link libraries
target_link_libraries(aquaculture_monitoring
    pico_stdlib
    pico_cyw43_arch_lwip_threadsafe_background
    hardware_adc
)

# Enable USB output, disable UART output
pico_enable_stdio_usb(aquaculture_monitoring 1)
pico_enable_stdio_uart(aquaculture_monitoring 0)

# Create map/bin/hex/uf2 files
pico_add_extra_outputs(aquaculture_monitoring)
