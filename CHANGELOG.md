# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-03-14

### Added
- Internationalization (i18n): English, Russian, German, Spanish, French
- Auto-detect system language from OS locale on first launch
- Language selector in Config tab
- GUI About panel (right-side slide-out)
- TUI Help tab (7:Help) with RFCs, features, about info
- TUI start/stop server toggle (s key)
- TUI colored status indicator (Running=green, Error=red)
- TUI file list scrolling with proper viewport follow
- Custom app and tray icons
- macOS DMG distribution
- 98 security attack tests
- Docker support verified

### Fixed
- Rate limiter memory leak (unbounded HashMap growth)
- block_to_absolute() wraparound logic at u16 boundary
- OACK handshake DoS via garbage packet flooding
- TOCTOU race in WRQ file creation (now uses create_new)
- Mmap SIGBUS on file truncation (size verification + fallback)
- Bytes transferred double-counting in TX stats
- IPC connection DoS (added semaphore + timeout)
- Config reload losing CLI overrides (-p, -r, --allow-write)
- Windows service reload infinite loop (CancellationToken → Notify)
- WRQ with windowsize>1 truncation on out-of-order blocks
- bind_address config option now actually used in socket creation
- Buffer pool not resized on hot-reload of max_blksize
- Server state stuck on "Starting" when port occupied
- TUI display corruption from tracing console output
- TUI files not loading (tick() not called in event loop)
- macOS integration tests (symlink canonicalization)
- Dark theme text visibility and button contrast
- ACL row highlight white flash in dark theme

### Changed
- Default mode is now GUI (no --gui flag needed)
- Window closes app instead of minimizing to tray
- Default window size 1000x600, min 800x500
- Bandwidth chart disabled by default
- Version bumped to 1.0.1

## [0.1.0] - 2026-03-13

### Added
- Initial release
- TFTP server with RFC 1350, 2347, 2348, 2349, 7440 support
- GUI mode (egui) with dashboard, file browser, transfers, log, config, ACL tabs
- TUI mode (ratatui) with matching functionality
- Headless mode for daemon/service deployment
- Sliding window transfers for high throughput
- IP-based ACL with whitelist/blacklist and CIDR support
- Per-IP rate limiting and session limits
- Hot-reloadable TOML configuration
- Memory-mapped I/O for large files
- Path traversal protection and symlink policy
- System tray integration
- IPC control socket (Unix/Windows)
- systemd, launchd, Windows Service support
- Docker support
