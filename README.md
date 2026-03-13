# Fry TFTP Server

Cross-platform high-performance TFTP server in Rust with GUI, TUI, and headless modes.

## Features

- **Full RFC compliance:** RFC 1350, 2347 (options), 2348 (blksize), 2349 (timeout/tsize), 7440 (windowsize/sliding window)
- **Three modes:** GUI (egui), TUI (ratatui), Headless (daemon)
- **Dual-stack networking:** IPv4 + IPv6 on a single socket
- **Sliding window transfers:** Configurable windowsize for high throughput
- **Netascii + Octet modes**
- **Access control:** IP-based ACL with CIDR, whitelist/blacklist modes
- **Hot-reloadable config:** TOML config with live reload via ArcSwap
- **System tray** (GUI mode): Start/stop/show from tray icon
- **Cross-platform:** Windows, macOS, Linux

## Quick Start

```bash
# GUI mode (default)
cargo run -- --gui

# TUI mode
cargo run -- --tui

# Headless mode
cargo run -- --headless

# Custom options
cargo run -- --headless -p 6969 -r ./my-tftp-root --allow-write
```

## Build

```bash
# Full build (GUI + TUI + headless)
cargo build --release

# Headless only (no GUI/TUI dependencies)
cargo build --release --no-default-features

# TUI only
cargo build --release --no-default-features --features tui
```

## Configuration

Config file is auto-detected from platform-specific paths, or specify with `-c`:

```bash
fry-tftp-server --headless -c /path/to/config.toml
```

Default config location:
- **Windows:** `%APPDATA%\fry-tftp-server\config.toml`
- **Linux:** `/etc/fry-tftp-server/config.toml`
- **macOS:** `~/Library/Application Support/fry-tftp-server/config.toml`

See [`config/default.toml`](config/default.toml) for all options.

## Docker

```bash
# Recommended (Linux, full port access)
docker build -t fry-tftp-server .
docker run --net=host -v /srv/tftp:/srv/tftp fry-tftp-server

# Alternative (limited — only main socket)
docker run -p 69:69/udp -v /srv/tftp:/srv/tftp fry-tftp-server
```

> **Note:** TFTP uses ephemeral ports for each session. `--net=host` is recommended for full functionality.

## Service Installation

**Linux (systemd):**
```bash
sudo cp deploy/fry-tftp-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fry-tftp-server
```

**macOS (launchd):**
```bash
sudo cp deploy/com.fry-tftp-server.plist /Library/LaunchDaemons/
sudo launchctl load /Library/LaunchDaemons/com.fry-tftp-server.plist
```

**Windows (Service):**
```powershell
# Run as Administrator
.\deploy\install-windows-service.ps1
Start-Service TftpServerPro
```

## Firewall

TFTP requires UDP port 69 (main) plus ephemeral ports for sessions.

**Linux:**
```bash
sudo ufw allow 69/udp
```

**Windows:**
```powershell
New-NetFirewallRule -DisplayName "TFTP" -Direction Inbound -Protocol UDP -LocalPort 69 -Action Allow
```

**macOS:**
```bash
# Port 69 requires root. Run with sudo or use port > 1024 with -p flag.
```

## CLI Options

```
Options:
      --gui              Run in GUI mode
      --tui              Run in TUI mode
      --headless         Run in headless mode (daemon)
  -c, --config <FILE>    Path to config file
  -r, --root <DIR>       Root directory (overrides config)
  -p, --port <PORT>      Port number (overrides config)
  -b, --bind <ADDR>      Bind address (overrides config)
      --allow-write      Allow write requests
      --max-sessions <N> Maximum parallel sessions
      --blksize <N>      Maximum block size
      --windowsize <N>   Maximum window size
      --ip-version <V>   IP version: dual | v4 | v6
  -v, --verbose          Increase verbosity (-v info, -vv debug, -vvv trace)
  -q, --quiet            Quiet mode (errors only)
```

## TUI Keybindings

| Key | Action |
|---|---|
| `1`-`6` | Switch tabs |
| `Tab`/`Shift+Tab` | Next/prev tab |
| `j`/`k`, `Up`/`Down` | Scroll |
| `Enter` | Select / edit |
| `Esc` | Back / cancel |
| `s` | Stop server |
| `r` | Reload config |
| `q` | Quit |
| `?` | Help |

## License

MIT
