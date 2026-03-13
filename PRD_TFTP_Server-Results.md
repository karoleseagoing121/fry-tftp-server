# Fry TFTP Server — Development Results

## Phase 1: Core Engine (MVP) — COMPLETED

**Status:** DONE
**Date:** 2026-03-12
**Tests:** 36/36 passed (31 unit + 5 integration)
**Build:** `cargo build --no-default-features` — success, 0 errors

### 1.1 Project Structure + Cargo.toml

- Created full project structure per PRD §7.1
- Cargo.toml with feature flags: `default = ["gui", "tui"]`, optional GUI/TUI deps
- Three build variants work: full, tui-only, headless-only
- Platform-specific deps: `windows-service`, `windows-sys` (Windows), `nix` (Unix)

**Files:**
- `Cargo.toml` — workspace config with all dependencies
- `rust-toolchain.toml` — stable toolchain
- `config/default.toml` — default configuration file

### 1.2 Platform Module

- `src/platform/mod.rs` — conditional compilation dispatcher
- `src/platform/windows.rs` — Ctrl+C handler via `tokio::signal::ctrl_c()`
- `src/platform/unix.rs` — SIGTERM, SIGINT, SIGHUP handlers via `tokio::signal::unix`

### 1.3 Packet Parser/Serializer (RFC 1350)

- All 6 packet types: RRQ, WRQ, DATA, ACK, ERROR, OACK
- Zero-copy parsing from `&[u8]`
- Serialization via `bytes::BytesMut`
- Filename validation: rejects `..`, `~`, control chars (0x00-0x1F)
- Case-insensitive mode parsing ("OCTET", "octet", "Octet" all work)
- Option parsing for RFC 2347 (blksize, windowsize, timeout, tsize)
- Sorcerer's Apprentice protection: duplicate ACKs ignored, retransmit only on timeout

**Tests:** 16 unit tests covering all packet types, roundtrips, security rejections

### 1.4 Main Socket Listener (Dual-Stack)

- `src/core/net/mod.rs` — socket creation with `socket2`
- Dual-stack IPv6 with `IPV6_V6ONLY=false` for simultaneous IPv4+IPv6
- V4-only, V6-only modes via config
- Configurable SO_RCVBUF/SO_SNDBUF
- Per-session ephemeral port sockets

### 1.5 RRQ Handler + OACK Flow

- `src/core/session/mod.rs` — full RRQ session lifecycle
- Stop-and-wait DATA/ACK exchange
- OACK negotiation for options (blksize, windowsize, timeout, tsize)
- OACK → ACK(0) → DATA(1) flow per RFC 2347
- Block number u16 wrapping for rollover support
- Zero-byte file: single DATA with empty payload
- Trailing empty block when file_size % blksize == 0
- Timeout + retransmission (configurable max_retries)
- WRQ stub returns ERROR (planned for Phase 2)

### 1.6 File System Abstraction + Path Security

- `src/core/fs/mod.rs` — secure path resolution
- Path traversal prevention: rejects `..`, `~`, absolute paths, control chars
- Canonicalization + prefix check against root directory
- Leading slash/backslash stripping
- Platform-normalized separators (Windows: `/` → `\`)
- Must-exist validation for RRQ (regular file check)
- Parent-directory validation for WRQ paths

**Tests:** 8 unit tests covering traversal, tilde, control chars, missing files, subdirs

### 1.7 TOML Config + Platform Defaults + CLI Args

- `src/core/config/mod.rs` — full config schema with serde
- Platform-specific defaults:
  - Windows: `C:\TFTP`, `%APPDATA%\tftp-server\tftp-server.log`
  - Linux: `/srv/tftp`, `/var/log/tftp-server.log`
  - macOS: `~/Library/TFTP`, `~/Library/Logs/tftp-server.log`
- Config search paths per platform
- CLI overrides via `clap` derive API (port, bind, root, allow-write, etc.)
- Priority: CLI > env > config file > defaults

### 1.8 Structured Logging (tracing) + AppState

- `tracing` + `tracing-subscriber` with env-filter
- File logging via `tracing-appender` (daily rotation)
- `AppState` with lock-free atomic counters (bytes_tx/rx, sessions, errors)
- Active sessions tracking (`RwLock<HashMap<Uuid, SessionInfo>>`)
- Transfer history (ring buffer, last 1000 records)
- Per-IP rate limiting (sliding window)
- Hot-reloadable config via `ArcSwap<Config>`

### 1.9 Graceful Shutdown

- `CancellationToken` propagation from server → sessions
- Signal handlers: SIGTERM/SIGINT (Unix), Ctrl+C (Windows)
- Grace period (configurable, default 30s) for active sessions
- Main loop breaks on cancellation, waits for sessions to finish

### 1.10 Tests

**Unit tests (31):**
- Protocol parser: 16 tests (all packet types, roundtrips, security)
- Filesystem: 8 tests (path resolution, traversal, edge cases)
- ACL engine: 7 tests (whitelist, blacklist, disabled, IPv6, rule order)

**Integration tests (5):**
- `test_basic_rrq` — server startup/shutdown lifecycle
- `test_packet_roundtrip_rrq` — RRQ with options roundtrip
- `test_rrq_localhost` — full RRQ transfer on localhost (1536 bytes, 4 blocks)
- `test_rrq_zero_byte_file` — empty file transfer (1 block, empty payload)
- `test_rrq_file_not_found` — error response for missing file

### Architecture Summary

```
src/
├── main.rs              — CLI entry point (clap), mode dispatch
├── lib.rs               — module re-exports
├── core/
│   ├── mod.rs           — main server loop (recv → parse → dispatch)
│   ├── protocol/
│   │   ├── mod.rs
│   │   └── packet.rs    — parse/serialize all TFTP packet types
│   ├── session/
│   │   └── mod.rs       — RRQ session handler, OACK negotiation
│   ├── fs/
│   │   └── mod.rs       — secure path resolution
│   ├── acl/
│   │   └── mod.rs       — IP-based access control (CIDR matching)
│   ├── config/
│   │   └── mod.rs       — TOML config with platform defaults
│   ├── net/
│   │   └── mod.rs       — dual-stack socket creation
│   └── state.rs         — AppState (shared between all modes)
├── headless/
│   └── mod.rs           — headless mode entry point
├── platform/
│   ├── mod.rs           — platform dispatcher
│   ├── unix.rs          — Unix signal handlers
│   └── windows.rs       — Windows signal handlers
├── gui/                 — stub (Phase 3)
└── tui/                 — stub (Phase 4)
```

### Phase 1 Deliverable Verified

`cargo run --no-default-features -- --headless -r ./testfiles` — server starts, binds socket, handles RRQ via localhost test client, responds with correct DATA blocks, handles errors.

---

## Phase 2: Full Protocol — COMPLETED

**Status:** DONE
**Tests:** 47/47 passed (38 unit + 9 integration)

### Implemented

- **Sliding Window (RFC 7440):** RRQ sends windowsize blocks, waits for ACK of last. Partial ACK slides window. Timeout retransmits entire window. Tested with windowsize=4.
- **WRQ handler:** Full write support with DATA reception, ACK(0) flow (no options) and OACK flow (with options — client sends DATA(1) directly). Out-of-order buffering via BTreeMap. File written on completion.
- **Netascii mode:** encode (LF→CR+LF, bare CR→CR+NUL) and decode (CR+LF→LF, CR+NUL→CR). Applied transparently in RRQ/WRQ sessions.
- **Exponential backoff:** `timeout * 2^attempt`, capped at `max_timeout`. Configurable via `session.exponential_backoff`.
- **Block number rollover:** `block_to_absolute()` maps u16 block to u64 using epoch tracking. Supports files >32MB.
- **Virtual roots:** `VirtualRoots` struct with longest-prefix match. Config: `filesystem.virtual_roots`. Falls back to main root.
- **OACK all 4 flows:** RRQ+options (OACK→ACK(0)→DATA), RRQ no options (DATA(1)), WRQ+options (OACK→DATA(1)), WRQ no options (ACK(0)→DATA(1)).

### New Tests (Phase 2)

| Test | What |
|---|---|
| `test_rrq_with_blksize` | OACK negotiation, blksize=1024, full transfer |
| `test_wrq_basic` | WRQ upload 1500 bytes, verify file content |
| `test_rrq_sliding_window` | windowsize=4, 4096 bytes, ACK every 4th block |
| `test_netascii_encode_decode` | Netascii roundtrip |
| `test_virtual_roots` | Virtual root resolution + fallback |
| `test_compute_backoff` | Exponential backoff calculation |
| `test_block_to_absolute` | Block number rollover mapping |
| `test_compute_total_blocks` | Trailing empty block edge cases |

### Not Yet Done (deferred)

- Hot config reload via file watcher (`notify` crate added but not wired)
- Benchmarks (criterion)

---

## Phase 3: GUI — COMPLETED

**Status:** DONE
**Tests:** 47/47 passed (38 unit + 9 integration)
**Build:** `cargo build` (default features) — success, 0 errors, 0 warnings

### Implemented

- **3.1 eframe skeleton:** `TftpApp` struct with `Arc<AppState>`, tokio server spawned in background, `block_in_place` for eframe event loop. Custom `GuiLayer` tracing subscriber captures log events to `LogBuffer` for GUI display.
- **3.2 Dashboard:** 3 status cards (Active Sessions, TX Rate, RX Rate), active transfers table (client, file, direction, progress bar, speed, duration, blksize, windowsize).
- **3.3 Bandwidth graph:** `egui_plot` line chart TX/RX (MB/s) over last 5 minutes, 1-second sampling, auto-scale.
- **3.4 Files tab:** Directory browser with file listing, size/type columns, click-to-navigate dirs, "Change Root" via `rfd` file dialog, "Up" navigation.
- **3.5 Transfers tab:** History table (client, file, dir, size, duration, speed, status, retransmits), filters by IP/filename/status, reverse chronological.
- **3.6 Log tab:** Realtime log with color-coded levels (TRACE→gray, DEBUG→cyan, INFO→green, WARN→yellow, ERROR→red), level filter dropdown, text search filter, auto-scroll toggle, clear button.
- **3.7 Config tab:** Collapsible groups (Server, Protocol, Session, Security, Filesystem), all fields editable, Apply (hot-reload via ArcSwap), Reset, Export TOML via `rfd`.
- **3.8 ACL tab:** Mode selector (disabled/whitelist/blacklist), rules table with inline editing (action, CIDR, operations, comment, enabled toggle), add/delete rules, Apply to hot-reload.
- **3.9 Dark/Light theme:** Dark theme (PRD colors: #1a1a2e bg, #16213e sidebar, #0f3460 accent), Light theme, toggle button in title bar.
- **3.10 System tray:** `tray-icon` crate, green/gray circle icon (running/stopped), context menu (Show/Stop/Quit), auto-updates icon on state change.

### Architecture

```
src/gui/
├── mod.rs          — entry point: spawn server + eframe + tray
├── app.rs          — TftpApp (eframe::App), sidebar + tab dispatch
├── log_layer.rs    — GuiLayer (tracing Layer) + LogBuffer
├── theme.rs        — Dark/Light themes with PRD color palette
├── tray.rs         — System tray icon + context menu
└── tabs/
    ├── mod.rs      — Tab enum
    ├── dashboard.rs — status cards + transfers table + bandwidth plot
    ├── files.rs     — file browser with rfd dialog
    ├── transfers.rs — transfer history with filters
    ├── log_tab.rs   — realtime color-coded log viewer
    ├── config_tab.rs — visual config editor + hot reload
    └── acl_tab.rs   — ACL rules editor
```

---

## Phase 4: TUI — COMPLETED

**Status:** DONE
**Tests:** 47/47 passed (38 unit + 9 integration)
**Build:** `cargo build` — success, 0 errors
**Run:** `cargo run -- --tui`

### Implemented

- **4.1 ratatui skeleton:** `TuiApp` struct, crossterm terminal setup (raw mode, alternate screen, mouse capture), 250ms poll event loop, server spawned in background, `block_in_place` for blocking loop.
- **4.2 Dashboard tab:** Status line (state, bind addr, sessions, errors, bytes TX/RX), bandwidth sparklines (TX/RX last 60 samples), active transfers table (client, file, dir, progress, speed, time).
- **4.3 Files tab:** Directory listing with navigation (Enter=open dir, Backspace=parent), file size/type columns, sorted dirs-first.
- **4.4 Transfers tab:** History table (client, file, dir, size, duration, speed, status, retransmits), color-coded status, reverse chronological.
- **4.5 Log tab:** Color-coded log entries (ERROR=red, WARN=yellow, INFO=green, DEBUG=cyan, TRACE=darkgray), auto-scroll, capped at 500 entries.
- **4.6 Config tab:** Editable config list, Enter opens edit popup, type new value + Enter saves (hot-reload via ArcSwap), Esc cancels.
- **4.7 ACL tab:** Rules table with mode/action/CIDR/operations/comment columns.
- **4.8 Shared LogBuffer:** `core::log_buffer` module shared between GUI and TUI. GUI's `log_layer.rs` re-exports from core. `main.rs` has `init_logging_with_buffer()` for TUI path.
- **4.9 Keybindings:** 1-6 tab switch, Tab/BackTab, j/k/Up/Down scroll, Enter select, Esc back, s stop server, r reload config, q quit, ? help overlay. Mouse scroll support.

### Architecture

```
src/tui/
├── mod.rs  — entry point: spawn server + terminal setup + event loop
└── app.rs  — TuiApp (~1050 lines): input handling, 6 tab renderers, help overlay, edit popup

src/core/log_buffer.rs — shared AppLogLayer + LogBuffer (used by GUI + TUI)
src/main.rs — init_logging_with_buffer() for TUI, init_logging_gui() for GUI
```

---

## Phase 5: Polish & Release — COMPLETED

**Status:** DONE
**Tests:** 47/47 passed (38 unit + 9 integration)
**Build:** `cargo build` — 0 errors, 0 clippy warnings
**Targets:** 7 cross-compile targets in CI (x86_64/aarch64 Linux/Windows/macOS + musl)

### Implemented

- **5.1 CI/CD:** `.github/workflows/ci.yml` — format check, clippy (all features + headless), tests on 3 OS (ubuntu/windows/macos), security audit (`rustsec/audit-check`), code coverage (`cargo-tarpaulin` → Codecov).
- **5.2 Cross-compile:** `.github/workflows/release.yml` — triggered on `v*` tags. Builds 7 targets: `x86_64-unknown-linux-gnu`, `x86_64-unknown-linux-musl`, `aarch64-unknown-linux-gnu`, `x86_64-pc-windows-msvc`, `aarch64-pc-windows-msvc`, `x86_64-apple-darwin`, `aarch64-apple-darwin`. Auto-packages `.tar.gz`/`.zip`, creates GitHub Release.
- **5.5 Service files:** `deploy/tftp-server.service` (systemd, security-hardened: NoNewPrivileges, ProtectSystem, CAP_NET_BIND_SERVICE), `deploy/com.tftp-server.plist` (launchd), `deploy/install-windows-service.ps1` (New-Service + firewall rule).
- **5.6 Docker:** `Dockerfile` (multi-stage: rust:1.77-slim builder → debian:bookworm-slim runtime), `.dockerignore`. Headless mode, exposes 69/udp, documents `--net=host` recommendation.
- **5.7 README:** Full documentation: features, quick start (3 modes), build variants, config locations, Docker usage, service installation (Linux/macOS/Windows), firewall instructions, CLI options, TUI keybindings.
- **5.8 Clippy strict:** 0 warnings. Auto-fixed 10 suggestions. 4 structural `#[allow]` annotations (too_many_arguments, should_implement_trait).
- **5.9 Performance:** Zero-copy DATA packet serialization — `serialize_data_packet()` writes directly into pre-allocated buffer, avoiding `Vec<u8>` allocation per block. `get_block_payload()` returns `&[u8]` slice instead of cloning.

### Files Added

```
.github/workflows/ci.yml          — CI pipeline
.github/workflows/release.yml     — Cross-compile + release pipeline
deploy/tftp-server.service         — systemd unit
deploy/com.tftp-server.plist       — launchd plist
deploy/install-windows-service.ps1 — Windows service installer
Dockerfile                         — Multi-stage Docker build
.dockerignore
README.md                          — Full project documentation
```
