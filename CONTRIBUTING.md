# Contributing to Fry TFTP Server

Thank you for your interest in contributing! Here's how to get started.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/fry-tftp-server.git`
3. Create a branch: `git checkout -b feature/my-feature`
4. Install Rust: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`

## Development

### Build

```bash
cargo build --release                        # Full (GUI + TUI)
cargo build --release --no-default-features  # Headless only
```

### Linux GUI Dependencies

```bash
sudo apt-get install -y libglib2.0-dev libgtk-3-dev libxdo-dev libxcb-shape0-dev libxcb-xfixes0-dev
```

### Test

```bash
cargo test          # All tests
cargo test --lib    # Unit tests only
```

### Lint

```bash
cargo fmt --check
cargo clippy --all-features --all-targets -- -D warnings
```

## Before Submitting a PR

- [ ] Run `cargo fmt`
- [ ] Run `cargo clippy --all-features` with no warnings
- [ ] Run `cargo test` and ensure all tests pass
- [ ] Add tests for new functionality if applicable
- [ ] Update documentation if behavior changed

## Code Style

- Follow standard Rust conventions
- Use `anyhow::Result` for error propagation, `thiserror` for domain errors
- Guard platform-specific code with `#[cfg(unix)]` / `#[cfg(windows)]` / `#[cfg(target_os = "macos")]`
- Keep functions focused and short
- Add i18n keys for new user-facing strings (see `src/core/i18n.rs`)

## Reporting Issues

- Use the [Bug Report](https://github.com/qulisun/fry-tftp-server/issues/new?template=bug_report.md) template
- Include OS, version, and steps to reproduce
- Attach logs if available

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
