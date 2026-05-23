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

project(risk_monitor C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(risk_monitor
    main.c
    ds18b20.c
    ph_sensor.c
)

# USB Serial as stdout — retained for debug monitoring via PuTTY/minicom
pico_enable_stdio_usb(risk_monitor 1)
# UART is also enabled for additional debug output
pico_enable_stdio_uart(risk_monitor 1)

# Don't wait forever for USB serial connection - timeout after 500ms
target_compile_definitions(risk_monitor PRIVATE
    PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS=500
)

# Add current directory to include path for lwipopts.h
target_include_directories(risk_monitor PRIVATE ${CMAKE_CURRENT_LIST_DIR})

target_link_libraries(risk_monitor
    pico_stdlib
    hardware_adc
    hardware_gpio
    hardware_timer
    pico_cyw43_arch_lwip_threadsafe_background
)

# Generate UF2, HEX, BIN
pico_add_extra_outputs(risk_monitor)
