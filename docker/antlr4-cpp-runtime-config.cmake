# Compatibility package for https://github.com/adeharo9/antlr4-cpp-runtime.
# The image ships the same ANTLR 4.13.2 runtime through the official CMake
# package; expose the standalone project's target and variable names as aliases.

include_guard(GLOBAL)

include("${CMAKE_CURRENT_LIST_DIR}/../antlr4-runtime/antlr4-runtime-config.cmake")

if(NOT TARGET antlr4_cpp_runtime)
  add_library(antlr4_cpp_runtime INTERFACE IMPORTED)
  set_target_properties(antlr4_cpp_runtime PROPERTIES
    INTERFACE_INCLUDE_DIRECTORIES "${ANTLR4_INCLUDE_DIR}"
    INTERFACE_LINK_LIBRARIES antlr4_static
  )
endif()

set(ANTLR4_CPP_RUNTIME antlr4_cpp_runtime)
set(antlr4_cpp_runtime_FOUND TRUE)
set(antlr4-cpp-runtime_FOUND TRUE)
