.PHONY: build build-headless test test-headless test-heavy lint fmt check bench fuzz clean fixtures run run-headless integration docker

# ─── Build ──────────────────────────────────────────────────────────────────

build:
	cargo build --release

build-headless:
	cargo build --release --no-default-features

# ─── Test ───────────────────────────────────────────────────────────────────

test:
	cargo test --workspace

test-headless:
	cargo test --workspace --no-default-features

test-heavy:
	cargo test --workspace -- --ignored

# ─── Quality ────────────────────────────────────────────────────────────────

lint:
	cargo clippy -- -D warnings

fmt:
	cargo fmt --check

check: fmt lint test
	@echo "All checks passed."

# ─── Benchmarks & Fuzz ─────────────────────────────────────────────────────

bench:
	cargo bench --workspace

fuzz:
	cd fuzz && cargo fuzz run packet_parser -- -max_total_time=60

# ─── Run ────────────────────────────────────────────────────────────────────

run:
	cargo run --release

run-headless:
	cargo run --release -- --headless

# ─── Fixtures ───────────────────────────────────────────────────────────────

fixtures:
	python tests/generate_fixtures.py

# ─── Integration (Python) ──────────────────────────────────────────────────

integration: build-headless
	@echo "Starting headless server and running Python integration tests..."
	@echo "NOTE: Ensure test_root/ exists with fixture files. See tests/tftp_integration.py."
	python tests/tftp_integration.py

# ─── Docker ─────────────────────────────────────────────────────────────────

docker:
	docker build -t fry-tftp-server -f deploy/docker/Dockerfile .

# ─── Clean ──────────────────────────────────────────────────────────────────

clean:
	cargo clean
