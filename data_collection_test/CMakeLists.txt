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

project(data_collection_test C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(data_collection_test
    main.c
    ds18b20.c
    ph_sensor.c
    fql_inference.c
)

# USB Serial as stdout (no UART)
pico_enable_stdio_usb(data_collection_test 1)
pico_enable_stdio_uart(data_collection_test 0)

target_link_libraries(data_collection_test
    pico_stdlib
    hardware_adc
    hardware_gpio
    hardware_timer
    pico_cyw43_arch_none
)

# Generate UF2, HEX, BIN
pico_add_extra_outputs(data_collection_test)
