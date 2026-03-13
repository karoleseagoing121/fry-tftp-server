# PRD — Fry TFTP Server: Remaining Gaps

**Version:** 1.0
**Date:** 2026-03-13
**Status:** Draft
**Parent PRD:** PRD_TFTP_Server.md v2.0
**Context:** Gap analysis after implementation phases A–G. This document covers all unimplemented, partially implemented, and deferred items from the original PRD.

---

## 1. Overview

After completing phases A–G of the main PRD, an audit identified **9 missing**, **8 partial**, and **6 deferred** items. This PRD defines the scope, acceptance criteria, and priority for closing every remaining gap.

### 1.1 Scope

| Category | Count | Items |
|----------|-------|-------|
| Not implemented | 9 | JSON export, launchd, Docker, benchmarks, fuzz, CI/CD, release builds, code signing, packaging |
| Partially implemented | 8 | Syslog, Windows Event Log, dashboard sparklines, config reset/import, CTRL+BREAK, native Windows Service handler, Rust test client |
| Intentionally deferred | 6 | mmap, BufferPool, read-ahead, custom fonts, Named Pipe IPC, Unix domain socket IPC |

### 1.2 Out of Scope

The 6 **intentionally deferred** items (mmap, BufferPool, read-ahead buffer, custom Noto Sans fonts, Named Pipe IPC, Unix domain socket IPC) remain deferred. Current performance (233 MB/s throughput, 29/29 integration tests passing) does not justify the complexity. They can be revisited in a future PRD if bottlenecks emerge.

---

## 2. Priority Definitions

| Priority | Meaning | Timeline |
|----------|---------|----------|
| P0 | Must-have for v1.0 release | Immediate |
| P1 | Should-have, significant user value | Before v1.0 |
| P2 | Nice-to-have, polish | After v1.0 or v1.1 |

---

## 3. Missing Features (Not Implemented)

### 3.1 Transfers Tab: JSON Export — P2

**Parent PRD ref:** §4.3.3

**Current state:** CSV export works via `rfd` file dialog. JSON export not implemented.

**Requirements:**

1. Add "Export JSON" button next to existing "Export CSV" button in `src/gui/tabs/transfers.rs`
2. On click, open `rfd::FileDialog` with `.json` filter
3. Serialize filtered transfer records as JSON array using `serde_json`
4. Each record: `{ "client", "file", "direction", "bytes", "duration_ms", "speed_mbps", "status", "retransmits", "timestamp" }`
5. Write to selected file path

**Dependencies:** Add `serde_json = "1"` to `[dependencies]` in Cargo.toml (it may already be a transitive dep).

**Acceptance criteria:**
- Button visible in Transfers tab
- JSON file written matches current filter state
- Valid JSON parseable by `jq` / `python -m json.tool`

---

### 3.2 launchd Plist (macOS) — P1

**Parent PRD ref:** §6.5

**Current state:** No file exists.

**Requirements:**

1. Create `deploy/launchd/com.2f-it.tftp-server.plist`
2. Contents per PRD §6.5:
   - Label: `com.2f-it.tftp-server`
   - ProgramArguments: `/usr/local/bin/tftp-server --headless`
   - RunAtLoad: true
   - KeepAlive: true
   - StandardOutPath: `/usr/local/var/log/tftp-server.out.log`
   - StandardErrorPath: `/usr/local/var/log/tftp-server.err.log`
3. Add installation instructions in a comment block at top of file

**Acceptance criteria:**
- File parses with `plutil -lint`
- `sudo launchctl load` succeeds on macOS

---

### 3.3 Dockerfile — P1

**Parent PRD ref:** §6.6

**Current state:** No Dockerfile exists.

**Requirements:**

1. Create `deploy/docker/Dockerfile`
2. Multi-stage build:
   - Builder: `rust:1.77-slim`, `cargo build --release --no-default-features` (headless only)
   - Runtime: `debian:bookworm-slim`
   - Copy binary to `/usr/local/bin/tftp-server`
3. `EXPOSE 69/udp`
4. `VOLUME /srv/tftp`
5. `ENTRYPOINT ["tftp-server", "--headless"]`
6. Add comments about `--net=host` recommendation for session ports
7. Create `deploy/docker/.dockerignore` (exclude target/, .git/, etc.)

**Acceptance criteria:**
- `docker build -t fry-tftp .` succeeds
- `docker run --net=host fry-tftp` starts server and responds to TFTP requests

---

### 3.4 Criterion Benchmarks — P2

**Parent PRD ref:** §12.3

**Current state:** No `benches/` directory.

**Requirements:**

1. Create `benches/packet_bench.rs`:
   - `packet_parse`: Parse 1000 RRQ/DATA/ACK/ERROR packets
   - `packet_serialize`: Serialize 1000 packets of each type
2. Create `benches/throughput_bench.rs`:
   - `session_creation`: Measure time to create 1000 SessionInfo structs
   - `acl_matching`: Match 1000 IPs against 50-rule ACL
   - `path_resolution`: Resolve 1000 filenames against root
3. Add to `Cargo.toml`:
   ```toml
   [[bench]]
   name = "packet_bench"
   harness = false

   [[bench]]
   name = "throughput_bench"
   harness = false
   ```
4. `criterion` is already in `[dev-dependencies]`

**Acceptance criteria:**
- `cargo bench` runs all benchmarks without errors
- HTML reports generated in `target/criterion/`

---

### 3.5 Fuzz Testing Targets — P2

**Parent PRD ref:** §12.4

**Current state:** No `fuzz/` directory. Proptest exists in packet.rs (roundtrip + parse_never_panics).

**Requirements:**

1. Install `cargo-fuzz` (document in README)
2. Create `fuzz/Cargo.toml` with `libfuzzer-sys` dependency
3. Create `fuzz/fuzz_targets/packet_parser.rs`:
   ```rust
   fuzz_target!(|data: &[u8]| {
       let _ = tftp_server::core::protocol::packet::parse_packet(data);
   });
   ```
4. Create `fuzz/fuzz_targets/filename_validation.rs`:
   ```rust
   fuzz_target!(|data: &[u8]| {
       if let Ok(s) = std::str::from_utf8(data) {
           let root = std::path::PathBuf::from("/tmp/fuzz-root");
           let _ = tftp_server::core::fs::resolve_path(&root, s, false);
       }
   });
   ```

**Acceptance criteria:**
- `cargo fuzz run packet_parser -- -max_total_time=60` runs without crashes
- `cargo fuzz run filename_validation -- -max_total_time=60` runs without crashes

---

### 3.6 GitHub Actions CI — P0

**Parent PRD ref:** §13.1

**Current state:** No `.github/workflows/` directory.

**Requirements:**

1. Create `.github/workflows/ci.yml`:
   ```yaml
   name: CI
   on: [push, pull_request]

   jobs:
     lint:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: dtolnay/rust-toolchain@stable
           with:
             components: clippy, rustfmt
         - run: cargo fmt --check
         - run: cargo clippy --features gui -- -D warnings
         - run: cargo clippy --no-default-features -- -D warnings

     test:
       strategy:
         matrix:
           os: [ubuntu-latest, windows-latest, macos-latest]
       runs-on: ${{ matrix.os }}
       steps:
         - uses: actions/checkout@v4
         - uses: dtolnay/rust-toolchain@stable
         - run: cargo test --workspace
         - run: cargo test --workspace --no-default-features

     test-tui:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: dtolnay/rust-toolchain@stable
         - run: cargo test --workspace --no-default-features --features tui
   ```

2. Pin Rust version via `rust-toolchain.toml`:
   ```toml
   [toolchain]
   channel = "1.77"
   ```

**Acceptance criteria:**
- CI passes on push to any branch
- All 3 OS matrix jobs green
- Clippy zero warnings enforced

---

### 3.7 Release Build Pipeline — P1

**Parent PRD ref:** §13.2

**Current state:** No release workflow.

**Requirements:**

1. Create `.github/workflows/release.yml`:
   - Trigger: push tag `v*`
   - Matrix builds per PRD §13.2:
     - Windows x64 (x86_64-pc-windows-msvc)
     - Linux x64 glibc (x86_64-unknown-linux-gnu)
     - Linux x64 musl (x86_64-unknown-linux-musl) — static binary
     - Linux ARM64 (aarch64-unknown-linux-gnu) via `cross`
     - macOS Intel (x86_64-apple-darwin)
     - macOS ARM (aarch64-apple-darwin)
   - Each target builds two variants:
     - Full (default features: gui + tui)
     - Headless (--no-default-features)
   - Strip binaries (`cargo build --release`, `strip`)
   - Archive: `.zip` for Windows, `.tar.gz` for Unix
   - Create GitHub Release with all artifacts

**Acceptance criteria:**
- Tag push triggers release build
- All 6 platform artifacts uploaded to GitHub Release
- Headless binaries < 5 MB, GUI binaries < 15 MB (stripped)

---

### 3.8 Code Signing — P2

**Parent PRD ref:** §13.3

**Current state:** Not implemented.

**Requirements:**

1. **Windows:** Add `signtool.exe` step in release workflow
   - Secrets: `WINDOWS_CERT_PFX`, `WINDOWS_CERT_PASSWORD`
   - Sign `.exe` and `.msi` artifacts
2. **macOS:** Add `codesign` + `notarytool` step
   - Secrets: `APPLE_CERT_P12`, `APPLE_ID`, `APPLE_TEAM_ID`
   - Sign and notarize `.app` / binary
3. **Linux:** GPG detached signature (`.sig` file)
   - Secret: `GPG_PRIVATE_KEY`
   - `gpg --detach-sign --armor` for each archive

**Note:** Requires purchasing certificates. Can be deferred until community adoption justifies cost.

**Acceptance criteria:**
- Windows: `signtool verify /pa tftp-server.exe` succeeds
- macOS: `codesign --verify tftp-server` succeeds
- Linux: `gpg --verify tftp-server.tar.gz.sig` succeeds

---

### 3.9 Packaging (MSI, DMG, deb, rpm) — P2

**Parent PRD ref:** §13.4

**Current state:** No packaging configuration.

**Requirements:**

1. **Windows MSI** (`cargo-wix`):
   - Create `wix/main.wxs` template
   - Include firewall rule for port 69/UDP
   - Add to PATH
   - Optional: register Windows Service
   - Build in release workflow

2. **Debian .deb** (`cargo-deb`):
   - Add `[package.metadata.deb]` section to Cargo.toml:
     ```toml
     [package.metadata.deb]
     maintainer = "Slava <slava@2f-it.de>"
     copyright = "2026, 2F-IT GmbH"
     depends = "$auto"
     section = "net"
     assets = [
       ["target/release/tftp-server", "usr/local/bin/", "755"],
       ["deploy/tftp-server.service", "lib/systemd/system/", "644"],
       ["config/default.toml", "etc/tftp-server/config.toml", "644"],
     ]
     conf-files = ["/etc/tftp-server/config.toml"]
     ```

3. **RPM** (`cargo-generate-rpm`):
   - Add `[package.metadata.generate-rpm]` section
   - Similar asset mapping as deb

4. **macOS DMG** (`create-dmg`):
   - Create `.app` bundle wrapper
   - DMG with drag-to-Applications layout

5. **Docker image** — covered in §3.3 above

**Acceptance criteria:**
- `cargo deb` produces installable .deb
- `cargo wix` produces installable .msi
- `cargo generate-rpm` produces installable .rpm

---

## 4. Partially Implemented Features

### 4.1 Syslog Integration (Linux) — P1

**Parent PRD ref:** §3.6.3

**Current state:** Logging goes to stdout and file. No syslog output.

**Requirements:**

1. Add `tracing-syslog` crate (or `syslog` crate with tracing adapter) to Cargo.toml as optional dependency behind feature flag `syslog`
2. In `init_logging()` (headless mode), if `config.server.syslog_enabled` (new config field):
   - Create syslog layer targeting `LOG_DAEMON` facility
   - Add as additional tracing layer
3. New config field:
   ```toml
   [server]
   syslog = false  # enable syslog output (Linux/macOS only)
   ```
4. Only compile syslog support on Unix (`#[cfg(unix)]`)

**Acceptance criteria:**
- With `syslog = true`, messages appear in `journalctl -t tftp-server`
- Without config change, behavior unchanged

---

### 4.2 Windows Event Log — P2

**Parent PRD ref:** §3.6.3

**Current state:** No Windows Event Log integration.

**Requirements:**

1. Add `eventlog` or `winlog` crate behind `#[cfg(windows)]`
2. Register event source "FryTFTPServer" during `--install-service`
3. In headless mode on Windows, add Event Log tracing layer
4. Log levels mapping: ERROR → Error, WARN → Warning, INFO → Information

**Acceptance criteria:**
- Events visible in Windows Event Viewer under Application log
- Source: "FryTFTPServer"

---

### 4.3 Dashboard Sparklines on Status Cards — P2

**Parent PRD ref:** §4.3.1

**Current state:** Dashboard has bandwidth graph (egui_plot). Status cards show current values but no mini-sparklines.

**Requirements:**

1. In `src/gui/tabs/dashboard.rs`, add sparkline rendering to each status card:
   - Active Sessions: 60-second history as mini line chart
   - TX Rate: 60-second bandwidth history
   - RX Rate: 60-second bandwidth history
2. Use `egui::plot::Plot` with fixed height (40px), no axes, no labels — pure sparkline
3. Data source: existing `BandwidthSample` history in AppState

**Acceptance criteria:**
- Each card shows a mini graph below the number
- Graphs update in real-time with ~1 Hz sample rate

---

### 4.4 Config Tab: Reset to Defaults Button — P2

**Parent PRD ref:** §4.3.5

**Current state:** Config tab has Apply and Save buttons. No Reset button.

**Requirements:**

1. Add "Reset to Defaults" button in `src/gui/tabs/config_tab.rs`
2. On click, replace all editable fields with `Config::default()` values
3. Show confirmation dialog before resetting: "Reset all settings to defaults?"
4. Mark config as dirty after reset (user must click Apply to activate)

**Acceptance criteria:**
- Button visible in Config tab
- After click + confirm, all fields show default values
- Apply activates the defaults

---

### 4.5 Config Tab: Import TOML — P2

**Parent PRD ref:** §4.3.5

**Current state:** Save/export works. No import from external TOML file.

**Requirements:**

1. Add "Import" button next to "Save" in Config tab
2. On click, open `rfd::FileDialog` with `.toml` filter
3. Parse selected file as `Config`
4. If parse succeeds: populate all editor fields with imported values, mark dirty
5. If parse fails: show error message in status bar

**Acceptance criteria:**
- Import button opens file dialog
- Valid TOML file populates all fields
- Invalid TOML shows error without crashing

---

### 4.6 Windows CTRL+BREAK Handler — P2

**Parent PRD ref:** §6.2.2

**Current state:** Only Ctrl+C is handled via `tokio::signal::ctrl_c()`.

**Requirements:**

1. In `src/platform/windows.rs`, add CTRL+BREAK handler using `windows-sys` `SetConsoleCtrlHandler`
2. CTRL+BREAK → immediate shutdown (cancel token + process exit without grace period)
3. Differentiate from CTRL+C (graceful) vs CTRL+BREAK (immediate)

**Acceptance criteria:**
- Ctrl+C: graceful shutdown with grace period
- Ctrl+Break: immediate exit

---

### 4.7 Native Windows Service Control Handler — P1

**Parent PRD ref:** §6.4

**Current state:** Windows Service install/uninstall via `sc.exe` wrapper. No native `service_main` / service control handler.

**Requirements:**

1. Create `src/platform/windows_service.rs`
2. Implement `service_main` entry point using `windows-service` crate:
   ```rust
   define_windows_service!(ffi_service_main, service_main);

   fn service_main(arguments: Vec<OsString>) {
       // 1. Register service control handler
       // 2. Set status: SERVICE_RUNNING
       // 3. Run server (headless mode)
       // 4. On SERVICE_CONTROL_STOP: graceful shutdown
       // 5. Set status: SERVICE_STOPPED
   }
   ```
3. Handle service control events:
   - `SERVICE_CONTROL_STOP` → graceful shutdown (CancellationToken)
   - `SERVICE_CONTROL_SHUTDOWN` → graceful shutdown
   - `SERVICE_CONTROL_PARAMCHANGE` → config reload
4. Detect if running as service (check parent process or use `--service` hidden flag)
5. Update `--install-service` to use proper service registration

**Acceptance criteria:**
- `services.msc` can Start/Stop the service
- Service reports Running/Stopped status correctly
- Config reload works via `sc.exe control FryTFTPServer paramchange`

---

### 4.8 Rust Test Client — P2

**Parent PRD ref:** §12.5

**Current state:** Python test client (`tests/tftp_integration.py`) covers 29 test scenarios. No Rust test client.

**Requirements:**

1. Create `tests/test_client/mod.rs` (or `tests/test_client.rs`):
   - Minimal TFTP client supporting RRQ/WRQ
   - OACK negotiation (all 4 flows)
   - Configurable blksize, windowsize
   - IPv4 and IPv6
2. Optional advanced features:
   - Packet loss simulation (drop N% of outgoing ACKs)
   - Duplicate ACK simulation
   - Concurrent mode (N parallel clients via tokio::spawn)
3. Use in integration tests for scenarios that Python client doesn't cover well

**Acceptance criteria:**
- `cargo test` includes Rust-based integration tests using this client
- Covers at minimum: basic RRQ, basic WRQ, OACK flows, sliding window

---

## 5. Implementation Plan

### Phase 1 — CI/CD Foundation (P0)

| # | Task | Est. |
|---|------|------|
| 1.1 | Create `.github/workflows/ci.yml` (§3.6) | 1h |
| 1.2 | Create `rust-toolchain.toml` | 5min |
| 1.3 | Verify CI passes on all 3 OS | 1h |

### Phase 2 — Deployment Artifacts (P1)

| # | Task | Est. |
|---|------|------|
| 2.1 | Create launchd plist (§3.2) | 30min |
| 2.2 | Create Dockerfile (§3.3) | 1h |
| 2.3 | Create release workflow (§3.7) | 3h |
| 2.4 | Syslog integration (§4.1) | 2h |
| 2.5 | Native Windows Service handler (§4.7) | 4h |

### Phase 3 — GUI/UX Polish (P2)

| # | Task | Est. |
|---|------|------|
| 3.1 | JSON export in Transfers tab (§3.1) | 1h |
| 3.2 | Dashboard sparklines (§4.3) | 2h |
| 3.3 | Config: Reset to Defaults button (§4.4) | 1h |
| 3.4 | Config: Import TOML button (§4.5) | 1h |

### Phase 4 — Testing & Quality (P2)

| # | Task | Est. |
|---|------|------|
| 4.1 | Criterion benchmarks (§3.4) | 2h |
| 4.2 | Fuzz testing targets (§3.5) | 1h |
| 4.3 | Rust test client (§4.8) | 4h |

### Phase 5 — Platform Extras (P2)

| # | Task | Est. |
|---|------|------|
| 5.1 | Windows Event Log (§4.2) | 2h |
| 5.2 | Windows CTRL+BREAK (§4.6) | 1h |
| 5.3 | Code signing setup (§3.8) | 3h |
| 5.4 | Packaging: deb, rpm, MSI, DMG (§3.9) | 4h |

---

## 6. Verification

After each phase:

1. `cargo build --features gui` — compiles cleanly
2. `cargo clippy --features gui -- -D warnings` — zero warnings
3. `cargo test` — all tests pass
4. `python tests/tftp_integration.py` — 29/29 pass
5. Manual smoke test for UI changes (GUI + TUI)

---

## 7. Estimated Total Effort

| Phase | Priority | Est. Hours |
|-------|----------|------------|
| Phase 1 — CI/CD | P0 | 2h |
| Phase 2 — Deployment | P1 | 11h |
| Phase 3 — GUI Polish | P2 | 5h |
| Phase 4 — Testing | P2 | 7h |
| Phase 5 — Platform | P2 | 10h |
| **Total** | | **~35h** |

---

## 8. Appendix: Deferred Items (Not in Scope)

These items from the original PRD remain intentionally deferred:

| Item | Original PRD Ref | Reason |
|------|-----------------|--------|
| mmap for large files | §3.3.3 | Current throughput (233 MB/s) exceeds PRD target; premature optimization |
| Pre-allocated BufferPool | §3.3.3 | Per-session Vec<u8> is sufficient for real TFTP workloads |
| Read-ahead buffer | §3.3.3 | Sliding window already provides adequate pipelining |
| Custom fonts (Noto Sans) | §4.5 | egui default fonts render correctly; cosmetic improvement only |
| Named Pipe IPC (Windows) | §6.2.2 | Headless + config file + sc.exe is sufficient for management |
| Unix domain socket IPC | §6.2.3 | SIGHUP + file watcher covers all reload scenarios |

These can be revisited in a future PRD if user feedback or performance profiling indicates a need.
