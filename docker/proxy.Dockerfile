FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*
USER 1000:1000
ENTRYPOINT ["socat"]
