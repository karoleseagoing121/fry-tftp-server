# Fry TFTP Server — Multi-stage Docker build (headless only)
#
# Build:   docker build -t fry-tftp -f deploy/docker/Dockerfile .
# Run:     docker run --net=host -v /srv/tftp:/srv/tftp fry-tftp
#
# IMPORTANT: TFTP uses ephemeral ports for each session.
# --net=host is STRONGLY recommended on Linux.
# Without it, you need: -p 69:69/udp -p 10000-60000:10000-60000/udp

FROM rust:1.77-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y pkg-config && rm -rf /var/lib/apt/lists/*
COPY Cargo.toml Cargo.lock* rust-toolchain.toml ./
COPY src/ src/
COPY tests/ tests/
RUN cargo build --release --no-default-features

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
RUN groupadd -r tftp && useradd -r -g tftp -d /srv/tftp -s /sbin/nologin tftp
COPY --from=builder /build/target/release/fry-tftp-server /usr/local/bin/fry-tftp-server
RUN mkdir -p /srv/tftp && chown tftp:tftp /srv/tftp

EXPOSE 69/udp
VOLUME /srv/tftp

USER tftp
ENTRYPOINT ["fry-tftp-server", "--headless"]
