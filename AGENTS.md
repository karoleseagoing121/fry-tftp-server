# AGENTS.md

## Project Overview

Fry TFTP Server — cross-platform high-performance TFTP server (RFC 1350 + RFC 2347-2349, RFC 7440) written in Rust. Supports GUI (egui), TUI (ratatui), and headless (daemon) modes. Features sliding window transfers, OACK option negotiation, virtual roots, ACL, hot-reloadable config, and per-IP rate limiting.

## Setup

- **Rust toolchain**: stable (MSRV 1.75), see `rust-toolchain.toml`
- **No external C libraries required** — all dependencies are pure Rust
- **Platform targets**: Linux (glibc/musl), macOS (arm64/x86_64), Windows (MSVC)

```bash
# Install Rust (if needed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
```

## Build

```bash
cargo build --release                        # Full (GUI + TUI)
cargo build --release --no-default-features  # Headless only (Docker/systemd)
cargo build --release --features gui         # GUI only
cargo build --release --features tui         # TUI only
```

Cargo features: `default = ["gui", "tui"]`. Use `--no-default-features` for minimal binary.

## Test

```bash
cargo test                    # All tests (unit + integration, ~5s)
cargo test --lib              # Unit tests only (~0.2s)
cargo test --test integration # Integration tests only (~4s)
cargo test -- --ignored       # Heavy tests (block rollover, ~32MB transfer)
```

**Important**: Integration tests create temp directories. On macOS, always canonicalize temp paths before passing to `mini_server()` — macOS `/var` is a symlink to `/private/var`, which triggers the server's symlink protection. Use the `canonical_temp_path(&dir)` helper in test code.

## Lint & Format

```bash
cargo fmt --check              # Check formatting
cargo fmt                      # Auto-format
cargo clippy --all-features    # Lint with all features
cargo clippy --no-default-features  # Lint headless build
```

Tests treat warnings as errors (`-D warnings`). Unused test helpers need `#[allow(dead_code)]`.

## Code Conventions

- **Error handling**: `anyhow::Result` for propagation, `thiserror` for domain errors.
- **Async**: Tokio runtime, `tokio::select!` for cancellation, `CancellationToken` for shutdown.
- **Config**: `ArcSwap<Config>` for lock-free hot-reload. Never hold locks during I/O.
- **Metrics**: `AtomicU64` for counters. `RwLock` only for session maps.
- **Platform code**: Guard with `#[cfg(unix)]`, `#[cfg(windows)]`, `#[cfg(target_os = "macos")]`.
- **File I/O**: Files >= 64KB use `mmap`; smaller files are buffered.

## Project Structure

```
src/core/           # Protocol, sessions, config, filesystem, ACL, networking, IPC, state
src/gui/            # egui app with tabs: Dashboard, Files, Transfers, Log, Config, ACL, Help
src/tui/            # ratatui app with matching tabs
src/headless/       # Daemon mode with IPC listener
src/platform/       # OS-specific: signal handlers (Unix), Windows service
tests/integration/  # TFTP protocol integration tests with mini test server
tests/common/       # Reusable TftpTestClient for integration tests
benches/            # Criterion benchmarks (packet parsing, throughput)
fuzz/               # libfuzzer targets for packet parser
deploy/             # systemd service, launchd plist, install scripts
config/             # Default TOML config
```

## PR & Commit Guidelines

- Run `cargo fmt` and `cargo clippy --all-features` before committing.
- Run `cargo test` and ensure all tests pass.
- Commit messages: imperative mood, concise summary line, body for context if needed.
- Keep PRs focused — one feature or fix per PR.

## Security Considerations

- **Never disable path traversal protection** — `resolve_path()` canonicalizes and validates all paths.
- **Symlink policy**: `follow_symlinks` defaults to `false`. Every path component is checked.
- **ACL/rate limiting**: Changes to ACL or rate-limit logic must preserve deny-by-default in whitelist mode.
- **Packet parsing**: `parse_packet()` must never panic on arbitrary input (fuzz-tested).
- **Sensitive files**: Do not commit config files containing real IPs or credentials.

## Deployment

- **Docker**: Use `--net=host` (TFTP needs ephemeral UDP ports). Build with `--no-default-features`.
- **Linux**: `deploy/fry-tftp-server.service` for systemd.
- **macOS**: `deploy/com.fry-tftp-server.plist` for launchd. Port 69 works without sudo on Ventura+.
- **Windows**: `--install-service` / `--uninstall-service` for Windows Service registration.

## Troubleshooting

- **"symlink in path" errors**: Canonicalize the root path. On macOS, `/var` → `/private/var`.
- **Port 69 permission denied**: Use `sudo` or `-p <port>` with port > 1024.
- **Tests fail with timeouts**: Integration tests use 5s timeouts; slow CI may need adjustment.
- **Missing `nix::sys::resource`**: Ensure `"resource"` feature is in `nix` dependency in `Cargo.toml`.
