# Fry TFTP Server

Cross-platform TFTP server (RFC 1350 + extensions) in Rust with GUI (egui), TUI (ratatui), and headless modes.

## Build & Run

```bash
cargo build --release                        # Full build (GUI + TUI)
cargo build --release --no-default-features  # Headless only
./target/release/fry-tftp-server --gui       # Launch GUI (default)
./target/release/fry-tftp-server --tui       # Launch TUI
./target/release/fry-tftp-server --headless  # Daemon mode
```

## Testing

```bash
cargo test                    # Unit + integration tests (skip heavy ones)
cargo test -- --ignored       # Run heavy tests (block rollover ~32MB)
cargo test --test integration # Integration tests only
cargo test --lib              # Unit tests only
```

- Integration tests use `tempfile::tempdir()` — always pass canonical paths to `mini_server()` via `canonical_temp_path(&dir)` to avoid macOS `/var` → `/private/var` symlink issues.
- Property-based tests use `proptest` for packet fuzzing.
- Fuzz targets: `cargo +nightly fuzz run packet_parser`

## Architecture

```
src/
├── core/           # Server logic (no UI dependency)
│   ├── protocol/   # TFTP packet parsing/serialization
│   ├── session/    # RRQ/WRQ sessions, sliding window, retransmit
│   ├── config/     # TOML config, hot-reload via ArcSwap
│   ├── fs/         # Path resolution, virtual roots, mmap, symlink policy
│   ├── acl/        # IP-based access control (whitelist/blacklist, CIDR)
│   ├── net/        # Socket creation, dual-stack IPv6
│   ├── ipc.rs      # Unix socket / Windows pipe control interface
│   ├── state.rs    # Shared AppState, atomic metrics, bandwidth sampling
│   └── buffer_pool.rs
├── gui/            # egui/eframe: tabs (Dashboard, Files, Transfers, Log, Config, ACL, Help)
├── tui/            # ratatui/crossterm: same tabs in terminal
├── headless/       # Daemon mode with IPC listener
└── platform/       # Signal handlers (Unix: SIGTERM/INT/HUP/USR1, Windows: Ctrl+C/Break)
```

## Key Patterns

- **Config hot-reload**: `ArcSwap<Config>` — lock-free swap on SIGHUP, file watcher, or IPC `reload` command.
- **Graceful shutdown**: `CancellationToken` propagated to all sessions; grace period (default 30s) before force-kill.
- **Metrics**: `AtomicU64` counters (lock-free); `RwLock` only for session maps and transfer history.
- **File I/O**: Files >= 64KB served via `mmap`; smaller files buffered in memory.
- **Error handling**: `anyhow::Result` for propagation, `thiserror` for domain errors (`FsError`, `ParseError`).

## Code Style

- Rust 2021 edition, MSRV 1.75.
- Run `cargo fmt` and `cargo clippy --all-features` before committing.
- Tests treat warnings as errors (`-D warnings`), so unused code in test helpers needs `#[allow(dead_code)]`.
- Platform-specific code guarded by `#[cfg(unix)]` / `#[cfg(windows)]` / `#[cfg(target_os = "macos")]`.

## Features (Cargo)

- `default = ["gui", "tui"]` — both UI modes.
- `gui` — egui, eframe, tray-icon, arboard, rfd.
- `tui` — ratatui, crossterm.
- `--no-default-features` — headless (for Docker/systemd).

## Platform Notes

- **macOS**: Port < 1024 works without sudo (Ventura+). Temp paths use `/private/var` (canonicalize!). `notify` uses kqueue backend.
- **Linux**: Journald logging via `tracing-journald`. Systemd service in `deploy/`.
- **Windows**: Windows Service support (`--install-service`/`--uninstall-service`). Named pipe IPC.

## Config Priority (highest → lowest)

CLI flags → Environment (`TFTP_SERVER_*`) → Config file (`-c` or platform default) → Built-in defaults.

## CI/CD

GitHub Actions: fmt check → clippy → cross-platform tests (Ubuntu/Windows/macOS) → security audit → coverage (tarpaulin → Codecov).

## Common Gotchas

- `nix` crate needs feature `"resource"` for `getrlimit` on Unix — already added.
- `follow_symlinks` defaults to `false` — path resolution checks every component for symlinks.
- Sliding window: duplicate ACKs are intentionally ignored (Sorcerer's Apprentice bug avoidance).
- Block numbers are `u16` — rollover at 65535 is handled via epoch tracking in `block_to_absolute()`.
- OACK handshake: WRQ+OACK flow does NOT send ACK(0) — client sends DATA(1) directly after OACK.
