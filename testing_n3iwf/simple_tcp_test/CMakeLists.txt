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
set(PICO_BOARD pico2_w CACHE STRING "Board type")

cmake_minimum_required(VERSION 3.13)

# Pull in Pico SDK (must be before project())
include(pico_sdk_import.cmake)

project(simple_tcp_test C CXX ASM)
pico_sdk_init()

add_executable(simple_tcp_test main.c)

# Add definitions
target_compile_definitions(simple_tcp_test PRIVATE
    WIFI_SSID=\"Check\"
    WIFI_PASSWORD=\"12345678901234567890\"
    N3IWF_SERVER_IP=\"192.168.100.79\"
    N3IWF_PORT=5005
)

# Enable USB serial
pico_enable_stdio_usb(simple_tcp_test 1)
pico_enable_stdio_uart(simple_tcp_test 0)

# Link libraries
target_link_libraries(simple_tcp_test
    pico_stdlib
    pico_cyw43_arch_lwip_threadsafe_background
)

# Set path to lwipopts.h
target_include_directories(simple_tcp_test PRIVATE ${CMAKE_CURRENT_LIST_DIR})

pico_add_extra_outputs(simple_tcp_test)
