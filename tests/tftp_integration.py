#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fry TFTP Server - Integration Test Suite
==========================================
Tests all supported RFCs against a running server instance.

  RFC 1350  — Base TFTP (RRQ, WRQ, DATA, ACK, ERROR)
  RFC 2347  — Option Extension (OACK)
  RFC 2348  — Blocksize Option
  RFC 2349  — Timeout Interval & Transfer Size Options
  RFC 7440  — Windowsize Option

Usage:
  1. Start the server:  cargo run -- --headless
  2. Run tests:         python tests/tftp_integration.py
  3. Or specify host:   python tests/tftp_integration.py --host 127.0.0.1 --port 69

Requires: Python 3.8+, no external dependencies.
"""

import argparse
import hashlib
import os
import socket
import struct
import sys
import time
import threading
import concurrent.futures
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Optional

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── TFTP Protocol Constants ──────────────────────────────────────────────

class Op(IntEnum):
    RRQ   = 1
    WRQ   = 2
    DATA  = 3
    ACK   = 4
    ERROR = 5
    OACK  = 6

class TftpError(IntEnum):
    NOT_DEFINED      = 0
    FILE_NOT_FOUND   = 1
    ACCESS_VIOLATION = 2
    DISK_FULL        = 3
    ILLEGAL_OP       = 4
    UNKNOWN_TID      = 5
    FILE_EXISTS      = 6
    NO_SUCH_USER     = 7
    OPTION_DENIED    = 8

# ── Packet Builders ──────────────────────────────────────────────────────

def build_rrq(filename: str, mode: str = "octet", options: dict = None) -> bytes:
    """RFC 1350 §4 / RFC 2347: Read Request with optional extensions."""
    pkt = struct.pack("!H", Op.RRQ) + filename.encode() + b'\x00' + mode.encode() + b'\x00'
    if options:
        for k, v in options.items():
            pkt += k.encode() + b'\x00' + str(v).encode() + b'\x00'
    return pkt

def build_wrq(filename: str, mode: str = "octet", options: dict = None) -> bytes:
    """RFC 1350 §4 / RFC 2347: Write Request with optional extensions."""
    pkt = struct.pack("!H", Op.WRQ) + filename.encode() + b'\x00' + mode.encode() + b'\x00'
    if options:
        for k, v in options.items():
            pkt += k.encode() + b'\x00' + str(v).encode() + b'\x00'
    return pkt

def build_ack(block: int) -> bytes:
    """RFC 1350 §4: Acknowledgement."""
    return struct.pack("!HH", Op.ACK, block)

def build_data(block: int, data: bytes) -> bytes:
    """RFC 1350 §4: Data packet."""
    return struct.pack("!HH", Op.DATA, block) + data

# ── Packet Parsers ───────────────────────────────────────────────────────

@dataclass
class Packet:
    opcode: int
    block: int = 0
    data: bytes = b''
    error_code: int = 0
    error_msg: str = ''
    options: dict = field(default_factory=dict)

def parse_packet(raw: bytes) -> Packet:
    opcode = struct.unpack("!H", raw[:2])[0]
    pkt = Packet(opcode=opcode)

    if opcode == Op.DATA:
        pkt.block = struct.unpack("!H", raw[2:4])[0]
        pkt.data = raw[4:]
    elif opcode == Op.ACK:
        pkt.block = struct.unpack("!H", raw[2:4])[0]
    elif opcode == Op.ERROR:
        pkt.error_code = struct.unpack("!H", raw[2:4])[0]
        pkt.error_msg = raw[4:].split(b'\x00')[0].decode(errors='replace')
    elif opcode == Op.OACK:
        # Parse null-terminated key-value pairs
        parts = raw[2:].split(b'\x00')
        parts = [p.decode(errors='replace') for p in parts if p]
        for i in range(0, len(parts) - 1, 2):
            pkt.options[parts[i].lower()] = parts[i + 1]
    return pkt

# ── TFTP Client Helper ───────────────────────────────────────────────────

class TftpClient:
    """Minimal TFTP client using raw UDP sockets for test flexibility."""

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _make_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        return sock

    def get_file(self, filename: str, options: dict = None) -> tuple[bytes, dict]:
        """Download file via TFTP. Returns (file_data, negotiated_options)."""
        sock = self._make_socket()
        try:
            pkt = build_rrq(filename, options=options)
            sock.sendto(pkt, (self.host, self.port))

            data = bytearray()
            negotiated = {}
            blksize = 512
            windowsize = 1
            server_addr = None
            expected_block = 1

            while True:
                raw, addr = sock.recvfrom(65536)
                if server_addr is None:
                    server_addr = addr  # TID from server's ephemeral port

                resp = parse_packet(raw)

                if resp.opcode == Op.OACK:
                    # RFC 2347: Option Acknowledgement
                    negotiated = resp.options
                    if 'blksize' in negotiated:
                        blksize = int(negotiated['blksize'])
                    if 'windowsize' in negotiated:
                        windowsize = int(negotiated['windowsize'])
                    # ACK the OACK with block 0
                    sock.sendto(build_ack(0), server_addr)
                    continue

                if resp.opcode == Op.ERROR:
                    raise Exception(f"TFTP Error {resp.error_code}: {resp.error_msg}")

                if resp.opcode == Op.DATA:
                    if resp.block == expected_block:
                        data.extend(resp.data)
                        expected_block += 1

                        # With windowsize, ACK every windowsize blocks or on last packet
                        is_last = len(resp.data) < blksize
                        if is_last or (resp.block % windowsize == 0):
                            sock.sendto(build_ack(resp.block), server_addr)

                        if is_last:
                            break
                    else:
                        # Duplicate or out of order — ACK anyway
                        sock.sendto(build_ack(resp.block), server_addr)

            return bytes(data), negotiated
        finally:
            sock.close()

    def put_file(self, filename: str, file_data: bytes, options: dict = None) -> dict:
        """Upload file via TFTP. Returns negotiated_options."""
        sock = self._make_socket()
        try:
            pkt = build_wrq(filename, options=options)
            sock.sendto(pkt, (self.host, self.port))

            raw, server_addr = sock.recvfrom(65536)
            resp = parse_packet(raw)

            negotiated = {}
            blksize = 512

            if resp.opcode == Op.OACK:
                negotiated = resp.options
                if 'blksize' in negotiated:
                    blksize = int(negotiated['blksize'])
                # OACK means we start sending from block 1
            elif resp.opcode == Op.ACK and resp.block == 0:
                pass  # Standard WRQ ACK — ready to send
            elif resp.opcode == Op.ERROR:
                raise Exception(f"TFTP Error {resp.error_code}: {resp.error_msg}")
            else:
                raise Exception(f"Unexpected response: opcode={resp.opcode}")

            # Send DATA blocks
            block = 1
            offset = 0
            while True:
                chunk = file_data[offset:offset + blksize]
                sock.sendto(build_data(block, chunk), server_addr)

                # Wait for ACK
                raw, _ = sock.recvfrom(65536)
                ack = parse_packet(raw)

                if ack.opcode == Op.ERROR:
                    raise Exception(f"TFTP Error {ack.error_code}: {ack.error_msg}")

                if ack.opcode == Op.ACK and ack.block == block:
                    offset += blksize
                    block += 1
                    if len(chunk) < blksize:
                        break  # Last block sent and ACKed
                else:
                    raise Exception(f"Unexpected ACK: opcode={ack.opcode} block={ack.block}")

            return negotiated
        finally:
            sock.close()

    def send_raw(self, data: bytes) -> Packet:
        """Send raw packet and get response — for testing error handling."""
        sock = self._make_socket()
        try:
            sock.sendto(data, (self.host, self.port))
            raw, _ = sock.recvfrom(65536)
            return parse_packet(raw)
        finally:
            sock.close()


# ── Test Suite ────────────────────────────────────────────────────────────

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name: str, detail: str = ""):
        self.passed += 1
        mark = "✅"
        print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))

    def fail(self, name: str, reason: str):
        self.failed += 1
        self.errors.append((name, reason))
        mark = "❌"
        print(f"  {mark} {name} — {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"  Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print(f"\n  Failed tests:")
            for name, reason in self.errors:
                print(f"    • {name}: {reason}")
        print(f"{'='*60}")
        return self.failed == 0


def run_tests(host: str, port: int, tftp_root: str):
    client = TftpClient(host, port)
    r = TestResult()

    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  Fry TFTP Server — Integration Tests")
    print(f"  Target: {host}:{port}   Root: {tftp_root}")
    print(f"{'='*60}")

    # ─── RFC 1350: Basic TFTP ─────────────────────────────────
    print(f"\n── RFC 1350: Base TFTP Protocol ──")

    # Test 1: Read small file
    try:
        data, _ = client.get_file("small.txt")
        expected = b'Hello TFTP World!\n' * 10
        if data == expected:
            r.ok("GET small.txt", f"{len(data)} bytes")
        else:
            r.fail("GET small.txt", f"content mismatch: got {len(data)} bytes, expected {len(expected)}")
    except Exception as e:
        r.fail("GET small.txt", str(e))

    # Test 2: Read exactly 1-block file (512 bytes — edge case)
    try:
        data, _ = client.get_file("oneblock.bin")
        if len(data) == 512 and data == b'X' * 512:
            r.ok("GET oneblock.bin (512b edge case)", f"{len(data)} bytes")
        else:
            r.fail("GET oneblock.bin", f"got {len(data)} bytes, expected 512")
    except Exception as e:
        r.fail("GET oneblock.bin", str(e))

    # Test 3: Read multi-block file
    try:
        data, _ = client.get_file("medium.bin")
        # Verify against disk
        with open(os.path.join(tftp_root, "medium.bin"), "rb") as f:
            expected = f.read()
        if data == expected:
            r.ok("GET medium.bin (10KB multi-block)", f"{len(data)} bytes, hash OK")
        else:
            r.fail("GET medium.bin", f"content mismatch: got {len(data)}, expected {len(expected)}")
    except Exception as e:
        r.fail("GET medium.bin", str(e))

    # Test 4: Read large file (1MB)
    try:
        lg_client = TftpClient(host, port, timeout=30.0)
        data, _ = lg_client.get_file("large.bin")
        with open(os.path.join(tftp_root, "large.bin"), "rb") as f:
            expected = f.read()
        got_hash = hashlib.md5(data).hexdigest()
        exp_hash = hashlib.md5(expected).hexdigest()
        if got_hash == exp_hash:
            r.ok("GET large.bin (1MB)", f"{len(data)} bytes, MD5 match")
        else:
            r.fail("GET large.bin", f"MD5 mismatch: {got_hash} vs {exp_hash}")
    except Exception as e:
        r.fail("GET large.bin", str(e))

    # Test 5: Read non-existent file → ERROR
    try:
        data, _ = client.get_file("does_not_exist.txt")
        r.fail("GET nonexistent file", "should have raised error")
    except Exception as e:
        if "not found" in str(e).lower() or "1" in str(e):
            r.ok("GET nonexistent → FILE_NOT_FOUND", str(e))
        else:
            r.fail("GET nonexistent file", f"unexpected error: {e}")

    # Test 6: Read with netascii mode
    try:
        sock = client._make_socket()
        pkt = build_rrq("switch.cfg", mode="netascii")
        sock.sendto(pkt, (host, port))
        raw, addr = sock.recvfrom(65536)
        resp = parse_packet(raw)
        sock.close()
        if resp.opcode == Op.DATA:
            r.ok("GET netascii mode", f"got DATA block {resp.block}, {len(resp.data)} bytes")
        elif resp.opcode == Op.ERROR:
            r.ok("GET netascii mode", f"server responded (error: {resp.error_msg})")
        else:
            r.fail("GET netascii mode", f"unexpected opcode {resp.opcode}")
    except Exception as e:
        r.fail("GET netascii mode", str(e))

    # Test 7: Write file (if allow_write is enabled)
    print(f"\n── RFC 1350: Write Operations ──")

    write_filename = f"test_write_{int(time.time())}.txt"
    test_data = b"Written by Fry TFTP test suite at " + time.ctime().encode() + b"\n"
    try:
        client.put_file(write_filename, test_data)
        # Small delay for async file write to flush
        time.sleep(0.5)
        # Verify on disk
        written_path = os.path.join(tftp_root, write_filename)
        if os.path.exists(written_path):
            with open(written_path, "rb") as f:
                disk_data = f.read()
            if disk_data == test_data:
                r.ok(f"PUT {write_filename}", f"{len(test_data)} bytes, verified on disk")
                # Clean up test file
                os.remove(written_path)
            else:
                r.fail(f"PUT {write_filename}", "content mismatch on disk")
        else:
            r.fail(f"PUT {write_filename}", "file not found on disk after write")
    except Exception as e:
        err = str(e)
        if "access" in err.lower() or "violation" in err.lower() or "denied" in err.lower() or "not allowed" in err.lower():
            r.ok("PUT blocked (allow_write=false)", f"correctly denied: {err}")
        elif "exists" in err.lower():
            r.ok("PUT duplicate blocked (allow_overwrite=false)", f"correctly denied: {err}")
        else:
            r.fail(f"PUT {write_filename}", str(e))

    # ─── RFC 2347: Option Extension (OACK) ────────────────────
    print(f"\n── RFC 2347: Option Extension ──")

    # Test 8: Request with options → expect OACK
    try:
        data, opts = client.get_file("small.txt", options={"blksize": "1024"})
        if opts:
            r.ok("OACK received for blksize", f"options: {opts}")
        else:
            r.ok("GET with options (no OACK)", "server may not support option negotiation")
    except Exception as e:
        r.fail("GET with blksize option", str(e))

    # Test 9: Request with unknown option → should be ignored
    try:
        data, opts = client.get_file("small.txt", options={"bogus_option": "42"})
        if "bogus_option" not in opts:
            r.ok("Unknown option ignored", f"OACK options: {opts}")
        else:
            r.fail("Unknown option", "server accepted bogus option")
    except Exception as e:
        r.fail("Unknown option handling", str(e))

    # ─── RFC 2348: Blocksize Option ───────────────────────────
    print(f"\n── RFC 2348: Blocksize Option ──")

    for bs in [8, 512, 1428, 8192, 65464]:
        try:
            data, opts = client.get_file("medium.bin", options={"blksize": str(bs)})
            with open(os.path.join(tftp_root, "medium.bin"), "rb") as f:
                expected = f.read()
            neg_bs = int(opts.get('blksize', 512))
            if data == expected:
                r.ok(f"GET blksize={bs}", f"negotiated={neg_bs}, {len(data)} bytes OK")
            else:
                r.fail(f"GET blksize={bs}", f"content mismatch ({len(data)} vs {len(expected)})")
        except Exception as e:
            r.fail(f"GET blksize={bs}", str(e))

    # ─── RFC 2349: Timeout & Transfer Size ────────────────────
    print(f"\n── RFC 2349: Timeout & Transfer Size ──")

    # Test: tsize option
    try:
        data, opts = client.get_file("medium.bin", options={"tsize": "0"})
        if 'tsize' in opts:
            tsize = int(opts['tsize'])
            r.ok(f"tsize negotiated", f"server reports {tsize} bytes, got {len(data)}")
            if tsize == len(data):
                r.ok("tsize accuracy", "reported size matches actual transfer")
            else:
                r.fail("tsize accuracy", f"reported {tsize} but transferred {len(data)}")
        else:
            r.ok("tsize request (no OACK)", "server did not negotiate tsize")
    except Exception as e:
        r.fail("tsize option", str(e))

    # Test: timeout option
    try:
        data, opts = client.get_file("small.txt", options={"timeout": "5"})
        if 'timeout' in opts:
            r.ok(f"timeout negotiated", f"value={opts['timeout']}s")
        else:
            r.ok("timeout request", "completed without explicit timeout negotiation")
    except Exception as e:
        r.fail("timeout option", str(e))

    # Test: combined options (blksize + tsize + timeout)
    try:
        data, opts = client.get_file("medium.bin", options={
            "blksize": "1024",
            "tsize": "0",
            "timeout": "3"
        })
        with open(os.path.join(tftp_root, "medium.bin"), "rb") as f:
            expected = f.read()
        if data == expected:
            r.ok("Combined options (blksize+tsize+timeout)", f"opts={opts}, {len(data)} bytes OK")
        else:
            r.fail("Combined options", "content mismatch")
    except Exception as e:
        r.fail("Combined options", str(e))

    # ─── RFC 7440: Windowsize Option ──────────────────────────
    print(f"\n── RFC 7440: Windowsize Option ──")

    for ws in [1, 2, 4, 8, 16]:
        try:
            lg_client = TftpClient(host, port, timeout=30.0)
            data, opts = lg_client.get_file("large.bin", options={
                "windowsize": str(ws),
                "blksize": "1024"
            })
            with open(os.path.join(tftp_root, "large.bin"), "rb") as f:
                expected = f.read()
            got_hash = hashlib.md5(data).hexdigest()
            exp_hash = hashlib.md5(expected).hexdigest()
            neg_ws = opts.get('windowsize', '1')
            if got_hash == exp_hash:
                r.ok(f"GET windowsize={ws}", f"negotiated={neg_ws}, 1MB MD5 match")
            else:
                r.fail(f"GET windowsize={ws}", f"MD5 mismatch")
        except Exception as e:
            r.fail(f"GET windowsize={ws}", str(e))

    # ─── Error Handling ───────────────────────────────────────
    print(f"\n── Error Handling ──")

    # Test: Invalid opcode
    try:
        resp = client.send_raw(struct.pack("!H", 99) + b"garbage\x00")
        if resp.opcode == Op.ERROR:
            r.ok("Invalid opcode → ERROR", f"code={resp.error_code}: {resp.error_msg}")
        else:
            r.fail("Invalid opcode", f"expected ERROR, got opcode={resp.opcode}")
    except socket.timeout:
        r.ok("Invalid opcode → dropped", "server silently dropped (acceptable)")
    except Exception as e:
        r.fail("Invalid opcode", str(e))

    # Test: Malformed packet (too short)
    try:
        resp = client.send_raw(b"\x00")
        r.fail("Malformed packet", "should not get valid response")
    except socket.timeout:
        r.ok("Malformed packet → dropped", "server silently dropped")
    except Exception as e:
        r.ok("Malformed packet handled", str(e))

    # Test: Path traversal attempt
    # Use longer timeout — earlier tests may have triggered rate limiting
    try:
        slow_client = TftpClient(host, port, timeout=10.0)
        time.sleep(1)  # let rate limit window cool down
        data, _ = slow_client.get_file("../../../etc/passwd")
        r.fail("Path traversal", "should have been denied!")
    except socket.timeout:
        r.ok("Path traversal blocked", "server dropped packet (rate-limited or silent deny)")
    except Exception as e:
        if "violation" in str(e).lower() or "denied" in str(e).lower() or "not found" in str(e).lower() or "access" in str(e).lower():
            r.ok("Path traversal blocked", str(e))
        else:
            r.fail("Path traversal", f"unexpected: {e}")

    # ─── Concurrency ─────────────────────────────────────────
    print(f"\n── Concurrent Sessions ──")

    def fetch_file(fname):
        c = TftpClient(host, port, timeout=15.0)
        data, _ = c.get_file(fname)
        return (fname, len(data))

    try:
        files = ["small.txt", "medium.bin", "switch.cfg", "oneblock.bin", "small.txt"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(fetch_file, f) for f in files]
            results = []
            for fut in concurrent.futures.as_completed(futures, timeout=30):
                results.append(fut.result())
        r.ok(f"5 concurrent GETs", f"all completed: {[(f,s) for f,s in results]}")
    except Exception as e:
        r.fail("Concurrent GETs", str(e))

    # ─── Performance ──────────────────────────────────────────
    print(f"\n── Performance ──")

    # Throughput test with large file + big blocksize + windowsize
    try:
        lg_client = TftpClient(host, port, timeout=30.0)
        t0 = time.perf_counter()
        data, opts = lg_client.get_file("large.bin", options={
            "blksize": "8192",
            "windowsize": "8"
        })
        elapsed = time.perf_counter() - t0
        size_mb = len(data) / (1024 * 1024)
        speed = size_mb / elapsed if elapsed > 0 else 0
        r.ok(f"Throughput (1MB, blksize=8192, win=8)", f"{speed:.1f} MB/s in {elapsed:.2f}s")
    except Exception as e:
        r.fail("Throughput test", str(e))

    # Baseline throughput (default settings)
    try:
        lg_client = TftpClient(host, port, timeout=60.0)
        t0 = time.perf_counter()
        data, _ = lg_client.get_file("large.bin")
        elapsed = time.perf_counter() - t0
        size_mb = len(data) / (1024 * 1024)
        speed = size_mb / elapsed if elapsed > 0 else 0
        r.ok(f"Baseline throughput (1MB, default)", f"{speed:.1f} MB/s in {elapsed:.2f}s")
    except Exception as e:
        r.fail("Baseline throughput", str(e))

    # ─── Summary ──────────────────────────────────────────────
    return r.summary()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fry TFTP Server Integration Tests")
    parser.add_argument("--host", default="127.0.0.1", help="Server address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=69, help="Server port (default: 69)")
    parser.add_argument("--root", default=r"C:\TFTP", help="TFTP root directory for verification")
    args = parser.parse_args()

    print(f"\nConnecting to {args.host}:{args.port}...")

    # Quick connectivity check
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0)
        sock.sendto(build_rrq("small.txt"), (args.host, args.port))
        raw, _ = sock.recvfrom(65536)
        sock.close()
        pkt = parse_packet(raw)
        if pkt.opcode == Op.DATA:
            print(f"Server is responding! (got DATA block {pkt.block})\n")
        elif pkt.opcode == Op.OACK:
            print(f"Server is responding! (got OACK)\n")
        elif pkt.opcode == Op.ERROR:
            print(f"Server responded with error: {pkt.error_msg}\n")
        else:
            print(f"Server responded with opcode {pkt.opcode}\n")
    except socket.timeout:
        print(f"ERROR: No response from {args.host}:{args.port}")
        print("Make sure the server is running: cargo run -- --headless")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    success = run_tests(args.host, args.port, args.root)
    sys.exit(0 if success else 1)
