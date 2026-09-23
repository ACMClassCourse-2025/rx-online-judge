# Match the LLVM 22 IR emitted by the pinned Rust 1.95 reference toolchain.
FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key \
       | gpg --dearmor -o /usr/share/keyrings/llvm.gpg \
    && echo 'deb [signed-by=/usr/share/keyrings/llvm.gpg] https://apt.llvm.org/trixie/ llvm-toolchain-trixie-22 main' \
       > /etc/apt/sources.list.d/llvm.list \
    && apt-get update && apt-get install -y --no-install-recommends clang-22 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /workspace /case /output
WORKDIR /workspace
USER 1000:1000
