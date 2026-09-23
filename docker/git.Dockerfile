FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /workspace /case /output
USER 1000:1000
WORKDIR /workspace
