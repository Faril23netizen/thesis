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
set(PICO_BOARD pico_w CACHE STRING "Board type")

cmake_minimum_required(VERSION 3.13)

# Pull in Pico SDK (must be before project())
include(pico_sdk_import.cmake)

project(dummy_node C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialize the Pico SDK
pico_sdk_init()

# Add executable
add_executable(dummy_node
    main.c
)

# Pull in our pico_stdlib which aggregates commonly used features
target_link_libraries(dummy_node
    pico_stdlib
    pico_cyw43_arch_lwip_threadsafe_background
)

# Enable usb output, disable uart output
pico_enable_stdio_usb(dummy_node 1)
pico_enable_stdio_uart(dummy_node 0)

# Create map/bin/hex/uf2 file etc.
pico_add_extra_outputs(dummy_node)
