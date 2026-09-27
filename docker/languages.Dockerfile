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

FROM base AS cpp
USER root
RUN apt-get update && apt-get install -y --no-install-recommends g++ cmake ninja-build \
    && rm -rf /var/lib/apt/lists/*
USER 1000:1000

FROM rust:1.95-slim-trixie AS rust-toolchain
RUN rustup target add riscv32im-unknown-none-elf

FROM cpp AS rust
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
