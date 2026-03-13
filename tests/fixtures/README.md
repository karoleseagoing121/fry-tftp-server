# Test Fixtures

Test data files for TFTP server integration tests.

## Text fixtures (tracked in git)

| File | Size | Description |
|---|---|---|
| `small.txt` | ~180 B | Small ASCII text for basic RRQ tests |
| `netascii.txt` | ~70 B | Text with LF endings for netascii mode tests |
| `switch.cfg` | ~550 B | Cisco IOS-like config (realistic TFTP use case) |

## Binary fixtures (generated, in .gitignore)

Run `python tests/generate_fixtures.py` to generate these:

| File | Size | Description |
|---|---|---|
| `zero.bin` | 0 B | Zero-byte file edge case |
| `oneblock.bin` | 512 B | Exactly one TFTP block (edge case) |
| `medium.bin` | 10 KB | Medium binary for multi-block tests |
| `large.bin` | 1 MB | Large binary for throughput/performance tests |

All binary files use deterministic byte patterns for reproducibility.
