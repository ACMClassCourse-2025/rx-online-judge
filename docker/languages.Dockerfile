FROM debian:trixie-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends python3 make ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /workspace /case /output /opt/rx-oj
COPY sandbox/ /opt/rx-oj/
WORKDIR /workspace
USER 1000:1000

FROM base AS python
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*
USER 1000:1000

FROM base AS cpp-base
USER root
RUN apt-get update && apt-get install -y --no-install-recommends g++ cmake ninja-build \
    && rm -rf /var/lib/apt/lists/*
USER 1000:1000

FROM cpp-base AS antlr4-cpp-builder
USER root
ARG ANTLR4_VERSION=4.9.1
ARG ANTLR4_COMMIT=5c2b686f95e1a42f302fefd99271863bf25b2e06
RUN apt-get update && apt-get install -y --no-install-recommends git pkg-config uuid-dev \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 --branch "${ANTLR4_VERSION}" https://github.com/antlr/antlr4.git /tmp/antlr4 \
    && test "$(git -C /tmp/antlr4 rev-parse HEAD)" = "${ANTLR4_COMMIT}" \
    && sed -i \
      -e 's#git://github.com/nemtrif/utfcpp#https://github.com/nemtrif/utfcpp#' \
      -e 's#-Dgtest_force_shared_crt=ON#-Dgtest_force_shared_crt=ON -DUTF8_TESTS=OFF -DUTF8_SAMPLES=OFF -DUTF8_INSTALL=ON#' \
      -e 's/TEST_AFTER_INSTALL[[:space:]]*1/TEST_AFTER_INSTALL 0/' \
      /tmp/antlr4/runtime/Cpp/runtime/CMakeLists.txt \
    && cmake -S /tmp/antlr4/runtime/Cpp -B /tmp/antlr4/build \
      -DANTLR4_INSTALL=ON \
      -DWITH_DEMO=OFF \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      -DCMAKE_INSTALL_LIBDIR=lib \
    && cmake --build /tmp/antlr4/build --target install --parallel 2 \
    && test -f /usr/local/include/antlr4-runtime/antlr4-runtime.h \
    && test -f /usr/local/lib/libantlr4-runtime.a

FROM cpp-base AS cpp
USER root
RUN apt-get update && apt-get install -y --no-install-recommends uuid-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=antlr4-cpp-builder /usr/local/include/antlr4-runtime /usr/local/include/antlr4-runtime
COPY --from=antlr4-cpp-builder /usr/local/lib /usr/local/lib
# The standalone adeharo9 project uses a different CMake package and target name.
COPY docker/antlr4-cpp-runtime-config.cmake /tmp/antlr4-cpp-runtime-config.cmake
RUN ldconfig
RUN install -D /tmp/antlr4-cpp-runtime-config.cmake \
      /usr/local/lib/cmake/antlr4-cpp-runtime/antlr4-cpp-runtime-config.cmake \
    && rm /tmp/antlr4-cpp-runtime-config.cmake
USER 1000:1000

FROM rust:1.95-slim-trixie AS rust-toolchain
RUN rustup target add riscv32im-unknown-none-elf

FROM cpp-base AS rust
USER root
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
ENV RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo PATH=/usr/local/cargo/bin:$PATH
USER 1000:1000

FROM base AS java
USER root
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-21-jdk-headless maven \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_TOOL_OPTIONS="-XX:ActiveProcessorCount=1 -XX:ReservedCodeCacheSize=64m -Xms16m -Xmx512m"
USER 1000:1000

FROM node:22-trixie-slim AS node-toolchain

FROM base AS node
USER root
COPY --from=node-toolchain /usr/local/bin/node /usr/local/bin/node
COPY --from=node-toolchain /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
USER 1000:1000
