# Build context is the parent directory containing both repositories.
# REIMU comes from rx-compiler's pinned submodule, never from a submission.
FROM debian:trixie-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends g++ libfmt-dev \
    && rm -rf /var/lib/apt/lists/*
COPY rx-compiler/vendor/REIMU/include/ /src/include/
COPY rx-compiler/vendor/REIMU/src/ /src/src/
WORKDIR /src
RUN g++ -std=c++23 -O2 -Iinclude src/main.cpp src/*/*.cpp -lfmt -o /reimu

FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libfmt10 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /workspace /case /output
COPY --from=build /reimu /usr/local/bin/reimu
WORKDIR /workspace
USER 1000:1000
