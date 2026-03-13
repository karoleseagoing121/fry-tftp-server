# Fry TFTP Server — Plan: Fix All Remaining PRD Gaps

## Context
Audit of PRD vs implementation revealed **32 missing** and **10 partial** features out of 129 total requirements. This plan addresses all actionable gaps grouped by priority and complexity.

---

## Phase A: Critical Protocol & Security Fixes (HIGH priority)

### A1. Wire virtual roots into sessions
- **Files:** `src/core/session/mod.rs` (lines 297, 514), `src/core/state.rs`, `src/core/fs/mod.rs`
- **What:** Sessions call `fs::resolve_path()` but should call `fs::resolve_path_with_virtual()`
- **Plan:**
  1. Add `VirtualRoots` to `AppState` (constructed from `config.filesystem.virtual_roots` on load/reload)
  2. In `spawn_read_session` (line 297): replace `fs::resolve_path(&config.server.root, &filename, true)` with `fs::resolve_path_with_virtual(&config.server.root, &vroots, &filename, true)`
  3. Same for `spawn_write_session` (line 514)

### A2. Enforce max_file_size during WRQ
- **Files:** `src/core/config/mod.rs`, `src/core/session/mod.rs`
- **What:** `max_file_size` is a String ("4GB"), never parsed or checked
- **Plan:**
  1. Add `parse_size(s: &str) -> Option<u64>` helper in config (parse "4GB", "100MB", etc.)
  2. Add `max_file_size_bytes() -> u64` method to `FilesystemConfig`
  3. In WRQ tsize negotiation: reject if `tsize > max_file_size_bytes`
  4. In WRQ write loop: track total received, abort if exceeds limit

### A3. TID mismatch → send ERROR 5
- **Files:** `src/core/session/mod.rs` (lines 230, 428, 648)
- **What:** Wrong TID packets silently ignored; RFC 1350 requires ERROR(5)
- **Plan:** At each `if from != client_addr { continue; }`, add before `continue`:
  ```rust
  let err = serialize_packet(&Packet::Error { code: ErrorCode::UnknownTransferId, message: "Unknown TID".into() });
  let _ = session_socket.send_to(&err, from).await;
  ```

### A4. Session timeout & stale cleanup
- **Files:** `src/core/state.rs`, `src/core/mod.rs`
- **What:** `session_timeout` config exists but no cleanup task
- **Plan:**
  1. Add `cleanup_stale_sessions(&self, timeout_secs: u64)` method to `AppState`
  2. Spawn periodic task (every 10s) in `run_server()` that calls cleanup
  3. Mark sessions exceeding timeout as `Failed`, cancel their token

### A5. follow_symlinks enforcement
- **Files:** `src/core/fs/mod.rs`
- **What:** `follow_symlinks=false` should reject symlinks, but `canonicalize()` resolves them
- **Plan:**
  1. Pass `follow_symlinks: bool` to `resolve_path` / `resolve_against_root`
  2. After canonicalization, if `!follow_symlinks`, check `std::fs::symlink_metadata()` — if `.file_type().is_symlink()` on any path component, reject with `AccessViolation`

### A6. WRQ tsize validation against max_file_size
- Combined with A2 above

---

## Phase B: Configuration & Hot Reload (MEDIUM priority)

### B1. Environment variable overrides (TFTP_SERVER_*)
- **Files:** `src/core/config/mod.rs`
- **What:** PRD specifies env vars as priority 2 (CLI > env > file > defaults)
- **Plan:** After loading from TOML, apply env overrides:
  ```
  TFTP_SERVER_PORT, TFTP_SERVER_ROOT, TFTP_SERVER_BIND_ADDRESS,
  TFTP_SERVER_LOG_LEVEL, TFTP_SERVER_LOG_FILE, TFTP_SERVER_ALLOW_WRITE,
  TFTP_SERVER_MAX_SESSIONS, TFTP_SERVER_IP_VERSION
  ```
  Add `apply_env_overrides(&mut self)` method called after `load()`

### B2. SIGHUP config reload (Unix)
- **Files:** `src/platform/unix.rs`
- **What:** Handler registered but has `// TODO`
- **Plan:** In the SIGHUP handler:
  1. Call `Config::load()` to re-read from disk
  2. Store new config via `state.config.store(Arc::new(new_config))`
  3. Log "config reloaded via SIGHUP"

### B3. File watcher hot reload (notify crate)
- **Files:** `src/core/config/mod.rs` or new `src/core/watcher.rs`
- **What:** `notify` crate is in Cargo.toml but unused
- **Plan:**
  1. Create `spawn_config_watcher(config_path, state)` function
  2. Watch config file for changes, debounce 2s
  3. On change: `Config::load()` → `state.config.store()`
  4. Call from `run_server()` after startup

### B4. Add [gui] and [tui] config sections
- **Files:** `src/core/config/mod.rs`
- **What:** PRD specifies `[gui]` (theme, refresh_rate_ms, graph_history_seconds) and `[tui]` sections
- **Plan:** Add structs:
  ```rust
  #[derive(Serialize, Deserialize, Clone, Debug)]
  pub struct GuiConfig {
      pub theme: String,           // "dark" | "light"
      pub refresh_rate_ms: u64,    // default 250
      pub graph_history_seconds: u64, // default 300
  }
  #[derive(Serialize, Deserialize, Clone, Debug)]
  pub struct TuiConfig {
      pub mouse: bool,             // default true
      pub refresh_rate_ms: u64,    // default 250
  }
  ```

---

## Phase C: GUI Polish (MEDIUM priority)

### C1. Transfers tab: Export CSV
- **Files:** `src/gui/tabs/transfers.rs`
- **Plan:** Add "Export CSV" button → rfd save dialog → write CSV of filtered transfers

### C2. Transfers tab: column sorting
- **Files:** `src/gui/tabs/transfers.rs`
- **Plan:** Add clickable column headers, sort state (column + asc/desc), sort before render

### C3. Log tab: Copy & Export
- **Files:** `src/gui/tabs/log_tab.rs`
- **Plan:** Add "Copy All" (clipboard via `arboard`) and "Export" (rfd save → write file) buttons

### C4. ACL tab: CIDR inline validation
- **Files:** `src/gui/tabs/acl_tab.rs`
- **Plan:** On source field change, try `source.parse::<IpNet>()`, show red border / tooltip if invalid

### C5. ACL tab: drag-drop reorder
- **Files:** `src/gui/tabs/acl_tab.rs`
- **Plan:** Add Up/Down arrow buttons per rule to reorder (true drag-drop is complex in egui)

### C6. Tray icon: red for error state
- **Files:** `src/gui/tray.rs`
- **Plan:** Add third icon variant (red), set when `server_state == Error` or `total_errors > threshold`

### C7. Minimize to tray
- **Files:** `src/gui/app.rs`, `src/gui/tray.rs`
- **Plan:** On window close, hide window instead of exiting; "Show" tray menu item restores

---

## Phase D: TUI Enhancements (MEDIUM priority)

### D1. ACL editing in TUI
- **Files:** `src/tui/app.rs` (ACL tab section)
- **Plan:** Add popup for Add/Edit/Delete rule, similar to existing Config edit popup

### D2. Search/filter with /
- **Files:** `src/tui/app.rs`
- **Plan:** `/` opens filter input bar, filters current tab's content (logs, transfers, files)

---

## Phase E: Headless & System Integration (LOW priority)

### E1. SIGUSR1 state dump
- **Files:** `src/platform/unix.rs`
- **Plan:** On SIGUSR1, log full server state (sessions, stats, config) at INFO level

### E2. Resource limits check at startup (ulimit)
- **Files:** `src/core/mod.rs` or `src/main.rs`
- **Plan:** On Unix, check `getrlimit(RLIMIT_NOFILE)` and warn if < recommended (e.g., 4096)

### E3. Windows Service in-binary integration
- **Files:** `src/main.rs`, new `src/platform/windows_service.rs`
- **What:** Add `--install-service` and `--uninstall-service` CLI flags using `windows-service` crate
- **Plan:** Implement `service_main`, service control handler, install/uninstall via `sc.exe` wrapper

### E4. systemd Type=notify
- **Files:** `deploy/tftp-server.service`, `src/core/mod.rs`
- **Plan:** Add `sd_notify` call after socket bind; change service type to `notify`

---

## Phase F: Logging & Monitoring Extras (LOW priority)

### F1. Bandwidth sampling in AppState
- **Files:** `src/core/state.rs`
- **Plan:** Move `BandwidthSample` to state.rs, sample periodically, share across GUI/TUI/headless

### F2. Syslog integration
- **Files:** `src/main.rs`, Cargo.toml
- **Plan:** Add `tracing-syslog` or `syslog` crate, optional feature flag, configure in headless mode

### F3. Windows Event Log
- **Files:** `src/main.rs`, Cargo.toml
- **Plan:** Add `tracing-eventlog` crate behind `windows` feature, register event source

---

## Phase G: Testing & Quality (LOW priority)

### G1. Benchmarks (criterion)
- **Files:** new `benches/packet_bench.rs`, `benches/session_bench.rs`, Cargo.toml
- **Plan:** Add criterion benchmarks for packet parse/serialize, file read throughput

### G2. Property-based testing (proptest)
- **Files:** Cargo.toml, add proptest tests in `src/core/protocol/packet.rs`
- **Plan:** Generate random packets, verify parse(serialize(p)) == p roundtrip

### G3. Fuzz testing
- **Files:** new `fuzz/` directory
- **Plan:** cargo-fuzz targets for `parse_packet`, `validate_filename`

---

## Intentionally Deferred

These PRD items are nice-to-have but provide minimal real-world value for MVP:

| Item | Reason |
|------|--------|
| mmap for large files | Current performance (125 MB/s) is excellent; premature optimization |
| BufferPool (shared) | Same — per-session Vec is fine for real TFTP workloads |
| Read-ahead buffer | Same |
| Custom fonts (Noto Sans) | Cosmetic; egui defaults work well |
| Dashboard sparklines on cards | Bandwidth graph exists; mini-sparklines are cosmetic |
| Named Pipe IPC | Rarely needed; headless + config file is sufficient |
| Unix domain socket IPC | Same |

---

## Execution Order

| Order | Phase | Items | Est. Complexity |
|-------|-------|-------|-----------------|
| 1 | A | A1-A5 (critical fixes) | Medium |
| 2 | B | B1-B4 (config improvements) | Medium |
| 3 | C | C1-C7 (GUI polish) | Medium |
| 4 | D | D1-D2 (TUI enhancements) | Small |
| 5 | E | E1-E4 (system integration) | Large |
| 6 | F | F1-F3 (logging extras) | Small |
| 7 | G | G1-G3 (testing) | Medium |

## Verification

After each phase:
1. `cargo build --features gui` — compiles
2. `cargo clippy --features gui` — no warnings
3. `cargo test` — all unit tests pass
4. `python tests/tftp_integration.py` — all 29+ integration tests pass
5. Manual GUI/TUI smoke test for UI changes
