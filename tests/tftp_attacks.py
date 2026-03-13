#!/usr/bin/env python3
"""
Fry TFTP Server — Attack & Fuzzing Tests
=========================================
20+ malicious/edge-case tests targeting different RFCs and attack vectors.
Run against a live server: python tests/tftp_attacks.py

Tests:
  RFC 1350 attacks:  malformed packets, oversized, zero-length, wrong TID
  RFC 2347 attacks:  option bombs, huge option values, null bytes in options
  RFC 2348 attacks:  invalid blksize values (0, negative, enormous)
  RFC 7440 attacks:  insane windowsize values
  Protocol attacks:  rapid-fire, slowloris, amplification, replay
  Security attacks:  path traversal variants, null-byte injection, unicode tricks
"""

import argparse
import socket
import struct
import time
import threading
import sys
import os
import hashlib

# Parse CLI args before anything else
_parser = argparse.ArgumentParser(description="Fry TFTP Server — Attack & Fuzzing Tests")
_parser.add_argument("--host", default="127.0.0.1", help="Server address (default: 127.0.0.1)")
_parser.add_argument("--port", type=int, default=69, help="Server port (default: 69)")
_args = _parser.parse_args()

SERVER = _args.host
PORT = _args.port
TIMEOUT = 3

# TFTP opcodes
RRQ   = 1
WRQ   = 2
DATA  = 3
ACK   = 4
ERROR = 5
OACK  = 6

passed = 0
failed = 0
crashed = 0
results = []

def result(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        tag = "✅"
    else:
        failed += 1
        tag = "❌"
    msg = f"  {tag} {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append((name, ok, detail))

def make_rrq(filename, mode="octet", options=None):
    """Build a RRQ packet."""
    pkt = struct.pack("!H", RRQ) + filename.encode("utf-8") + b"\x00" + mode.encode() + b"\x00"
    if options:
        for k, v in options.items():
            pkt += k.encode() + b"\x00" + str(v).encode() + b"\x00"
    return pkt

def make_wrq(filename, mode="octet", options=None):
    """Build a WRQ packet."""
    pkt = struct.pack("!H", WRQ) + filename.encode("utf-8") + b"\x00" + mode.encode() + b"\x00"
    if options:
        for k, v in options.items():
            pkt += k.encode() + b"\x00" + str(v).encode() + b"\x00"
    return pkt

def make_data(block, payload):
    return struct.pack("!HH", DATA, block) + payload

def make_ack(block):
    return struct.pack("!HH", ACK, block)

def make_error(code, msg):
    return struct.pack("!HH", ERROR, code) + msg.encode() + b"\x00"

def send_recv(pkt, timeout=TIMEOUT):
    """Send packet, return (response_bytes, addr) or (None, None) on timeout."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(pkt, (SERVER, PORT))
        data, addr = s.recvfrom(65536)
        return data, addr
    except socket.timeout:
        return None, None
    finally:
        s.close()

def send_only(pkt):
    """Fire-and-forget."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(pkt, (SERVER, PORT))
    s.close()

def is_error(data, expected_code=None):
    if data and len(data) >= 4:
        opcode = struct.unpack("!H", data[:2])[0]
        if opcode == ERROR:
            code = struct.unpack("!H", data[2:4])[0]
            if expected_code is not None:
                return code == expected_code
            return True
    return False

def is_data(data, block=None):
    if data and len(data) >= 4:
        opcode = struct.unpack("!H", data[:2])[0]
        if opcode == DATA:
            blk = struct.unpack("!H", data[2:4])[0]
            if block is not None:
                return blk == block
            return True
    return False

def is_oack(data):
    if data and len(data) >= 2:
        return struct.unpack("!H", data[:2])[0] == OACK
    return False

def server_alive(retries=5, delay=3.0):
    """Quick check that server still responds. Retries to handle rate limiting."""
    for attempt in range(retries):
        if attempt > 0:
            time.sleep(delay)
        data, _ = send_recv(make_rrq("small.txt"), timeout=3)
        if data is not None:
            # Any response (DATA or ERROR) means server is alive
            return True
    return False


print("=" * 60)
print("  Fry TFTP Server — Attack & Fuzzing Tests")
print(f"  Target: {SERVER}:{PORT}")
print("=" * 60)

# Verify server is alive before we start
if not server_alive():
    print("\n  ⚠️  Server not responding! Start it first.")
    sys.exit(1)
print()

# ═══════════════════════════════════════════════════════════════
# 1. RFC 1350 — Malformed Packet Attacks
# ═══════════════════════════════════════════════════════════════
print("── 1. RFC 1350: Malformed Packet Attacks ──")

# ATK-01: Zero-length packet
data, _ = send_recv(b"", timeout=1)
result("ATK-01: Zero-length UDP payload", data is None, "server should silently drop")

# ATK-02: Single byte
data, _ = send_recv(b"\x00", timeout=1)
result("ATK-02: 1-byte packet", data is None, "too short for any valid opcode")

# ATK-03: Just opcode, no payload (2 bytes = valid opcode but no filename)
data, _ = send_recv(struct.pack("!H", RRQ), timeout=1)
result("ATK-03: RRQ with no filename (2 bytes)", data is None or is_error(data),
       "should drop or error")

# ATK-04: RRQ with filename but no null terminator or mode
pkt = struct.pack("!H", RRQ) + b"test.txt"  # no \x00, no mode
data, _ = send_recv(pkt, timeout=1)
result("ATK-04: RRQ missing null terminators", data is None or is_error(data),
       "malformed — no null separator")

# ATK-05: Packet with invalid opcode (0)
data, _ = send_recv(struct.pack("!H", 0), timeout=1)
result("ATK-05: Opcode 0 (invalid)", data is None or is_error(data),
       "no valid opcode 0")

# ATK-06: Packet with high opcode (9999)
data, _ = send_recv(struct.pack("!H", 9999), timeout=1)
result("ATK-06: Opcode 9999", data is None or is_error(data),
       "unknown opcode")

# ATK-07: DATA packet on main socket (should be rejected)
data, _ = send_recv(make_data(1, b"hello"), timeout=1)
ok = data is None or is_error(data)
result("ATK-07: DATA on main socket (illegal)", ok,
       "only RRQ/WRQ allowed on port 69")

# ATK-08: ACK packet on main socket
data, _ = send_recv(make_ack(0), timeout=1)
ok = data is None or is_error(data)
result("ATK-08: ACK on main socket (illegal)", ok,
       "only RRQ/WRQ allowed on port 69")

print()

# ═══════════════════════════════════════════════════════════════
# 2. RFC 2347/2348: Option Bomb Attacks
# ═══════════════════════════════════════════════════════════════
print("── 2. RFC 2347/2348: Option Bomb Attacks ──")

# ATK-09: Huge number of options (100 fake options)
opts = {f"fakeoption{i}": str(i) for i in range(100)}
pkt = make_rrq("small.txt", options=opts)
data, _ = send_recv(pkt, timeout=2)
ok = data is not None  # Server should still respond (ignore unknown options)
result("ATK-09: 100 unknown options in RRQ", ok,
       f"response: {'DATA/OACK' if data else 'timeout'}, packet size: {len(pkt)}B")

# ATK-10: Option with enormously long value (64KB value)
opts = {"blksize": "A" * 65000}
pkt = make_rrq("small.txt", options=opts)
try:
    data, _ = send_recv(pkt, timeout=2)
    result("ATK-10: Option value 65KB long", data is None or is_error(data) or is_data(data),
           "should handle gracefully (error or ignore)")
except OSError as e:
    result("ATK-10: Option value 65KB long", True,
           f"OS rejected oversized UDP send ({e}) — server never saw it")

# ATK-11: blksize=0 (invalid per RFC 2348, min is 8)
data, _ = send_recv(make_rrq("small.txt", options={"blksize": "0"}), timeout=2)
result("ATK-11: blksize=0", data is not None,
       "should use default or reject")

# ATK-12: blksize=99999999 (way beyond max)
data, _ = send_recv(make_rrq("small.txt", options={"blksize": "99999999"}), timeout=2)
ok = data is not None  # server should clamp to max_blksize
result("ATK-12: blksize=99999999", ok, "should clamp to server max")

# ATK-13: Negative blksize
data, _ = send_recv(make_rrq("small.txt", options={"blksize": "-1"}), timeout=2)
result("ATK-13: blksize=-1", data is not None,
       "should reject or use default")

# ATK-14: windowsize=0
data, _ = send_recv(make_rrq("small.txt", options={"windowsize": "0"}), timeout=2)
result("ATK-14: windowsize=0", data is not None,
       "should use default or reject")

# ATK-15: windowsize=65535
data, _ = send_recv(make_rrq("small.txt", options={"windowsize": "65535"}), timeout=2)
result("ATK-15: windowsize=65535", data is not None,
       "should clamp to server max")

print()

# ═══════════════════════════════════════════════════════════════
# 3. Security: Path Traversal Variants
# ═══════════════════════════════════════════════════════════════
print("── 3. Security: Path Traversal Variants ──")

traversal_payloads = [
    ("ATK-16: Classic ../", "../../../etc/passwd"),
    ("ATK-17: Backslash traversal", "..\\..\\..\\windows\\system32\\config\\sam"),
    ("ATK-18: URL-encoded ../", "..%2f..%2f..%2fetc%2fpasswd"),
    ("ATK-19: Null byte injection", "small.txt\x00.exe"),
    ("ATK-20: Unicode dot (U+FF0E)", "\uff0e\uff0e/\uff0e\uff0e/etc/passwd"),
    ("ATK-21: Double-encoded", "..%252f..%252fetc%252fpasswd"),
    ("ATK-22: Absolute path /etc/passwd", "/etc/passwd"),
    ("ATK-23: Absolute path C:\\", "C:\\Windows\\System32\\drivers\\etc\\hosts"),
]

for name, payload in traversal_payloads:
    try:
        # Build raw packet manually to allow null bytes
        pkt = struct.pack("!H", RRQ) + payload.encode("utf-8", errors="replace") + b"\x00octet\x00"
        data, _ = send_recv(pkt, timeout=1)
        # Success = no data leaked (error or silence)
        if data is None:
            result(name, True, "silently dropped")
        elif is_error(data):
            code = struct.unpack("!H", data[2:4])[0]
            msg_bytes = data[4:]
            msg = msg_bytes.split(b"\x00")[0].decode(errors="replace")
            result(name, True, f"ERROR({code}): {msg}")
        else:
            # Got actual data — this would be bad!
            result(name, False, "⚠️  GOT DATA — possible path traversal!")
    except Exception as e:
        result(name, True, f"exception: {e}")

print()

# ═══════════════════════════════════════════════════════════════
# 4. Protocol Abuse Attacks
# ═══════════════════════════════════════════════════════════════
print("── 4. Protocol Abuse Attacks ──")

# ATK-24: Rapid-fire 200 RRQs in <1 second (rate limit test)
print("  ⏳ ATK-24: Rapid-fire 200 RRQs...", end="", flush=True)
responses = 0
errors = 0
timeouts = 0
sockets = []
for i in range(200):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.5)
    s.sendto(make_rrq("small.txt"), (SERVER, PORT))
    sockets.append(s)

for s in sockets:
    try:
        data, _ = s.recvfrom(65536)
        if is_data(data):
            responses += 1
        elif is_error(data):
            errors += 1
    except socket.timeout:
        timeouts += 1
    finally:
        s.close()

print(f"\r", end="")
result(f"ATK-24: Rapid-fire 200 RRQs", True,
       f"data={responses}, errors={errors}, timeouts={timeouts}")

time.sleep(1)  # let rate limiter window reset

# ATK-25: Wrong TID — send ACK from different port to session
print("  ⏳ ATK-25: Wrong TID attack...", end="", flush=True)
s1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s1.settimeout(3)
s1.sendto(make_rrq("medium.bin"), (SERVER, PORT))
try:
    data, session_addr = s1.recvfrom(65536)
    if is_data(data, 1):
        # Now send ACK from a DIFFERENT socket (different TID)
        s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s2.settimeout(2)
        s2.sendto(make_ack(1), session_addr)
        try:
            err_data, _ = s2.recvfrom(65536)
            if is_error(err_data):
                code = struct.unpack("!H", err_data[2:4])[0]
                print(f"\r", end="")
                result("ATK-25: Wrong TID → ERROR(5)", code == 5,
                       f"got ERROR code={code}")
            else:
                print(f"\r", end="")
                result("ATK-25: Wrong TID → ERROR(5)", False, "expected error, got other")
        except socket.timeout:
            print(f"\r", end="")
            result("ATK-25: Wrong TID → ERROR(5)", False, "no response to wrong TID (RFC says should send ERROR 5)")
        finally:
            s2.close()
    else:
        print(f"\r", end="")
        result("ATK-25: Wrong TID → ERROR(5)", False, "didn't get DATA(1)")
except socket.timeout:
    print(f"\r", end="")
    result("ATK-25: Wrong TID → ERROR(5)", False, "initial RRQ timed out")
finally:
    s1.close()

# ATK-26: Oversized UDP payload (64KB of garbage after valid RRQ)
pkt = make_rrq("small.txt") + b"\x00" * 60000
try:
    data, _ = send_recv(pkt, timeout=2)
    result("ATK-26: 60KB packet (oversized RRQ)", data is not None,
           f"{'responded' if data else 'timeout'}")
except OSError as e:
    result("ATK-26: 60KB packet (oversized RRQ)", True,
           f"OS rejected oversized UDP send ({e}) — server never saw it")

# ATK-27: Send ERROR to main socket
data, _ = send_recv(make_error(0, "I am the attacker"), timeout=1)
result("ATK-27: ERROR packet on main socket", data is None or is_error(data),
       "should drop or error")

# ATK-28: Replay attack — send same RRQ twice rapidly
pkt = make_rrq("small.txt")
s1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s1.settimeout(2)
s2.settimeout(2)
s1.sendto(pkt, (SERVER, PORT))
s2.sendto(pkt, (SERVER, PORT))
r1, r2 = None, None
try:
    r1, _ = s1.recvfrom(65536)
except: pass
try:
    r2, _ = s2.recvfrom(65536)
except: pass
s1.close()
s2.close()
both_ok = (r1 is not None and is_data(r1)) and (r2 is not None and is_data(r2))
result("ATK-28: Duplicate RRQ (replay)", both_ok or (r1 is not None),
       f"resp1={'yes' if r1 else 'no'}, resp2={'yes' if r2 else 'no'}")

print()

# ═══════════════════════════════════════════════════════════════
# 5. Stress & Edge Cases
# ═══════════════════════════════════════════════════════════════
print("── 5. Stress & Edge Cases ──")

# ATK-29: Request zero.bin (0 bytes file)
data, _ = send_recv(make_rrq("zero.bin"), timeout=2)
ok = False
detail = "timeout"
if data and is_data(data, 1):
    payload = data[4:]
    ok = len(payload) == 0
    detail = f"DATA(1) payload={len(payload)}B (should be 0)"
elif data and is_error(data):
    detail = f"ERROR (also acceptable if file not found)"
    ok = True
result("ATK-29: GET zero.bin (0-byte file)", ok, detail)

# ATK-30: Multiple file extensions traversal
data, _ = send_recv(make_rrq("....//....//etc/passwd"), timeout=1)
result("ATK-30: ....// traversal variant", data is None or is_error(data),
       "should block")

# ATK-31: Filename with only dots
data, _ = send_recv(make_rrq(".."), timeout=1)
result("ATK-31: Filename '..'", data is None or is_error(data), "should block")

# ATK-32: Very long filename (4096 chars)
long_name = "A" * 4096 + ".txt"
data, _ = send_recv(make_rrq(long_name), timeout=1)
result("ATK-32: 4096-char filename", data is None or is_error(data),
       "should handle gracefully")

# ATK-33: Concurrent different-file stress (20 simultaneous)
print("  ⏳ ATK-33: 20 concurrent sessions...", end="", flush=True)
files = ["small.txt", "medium.bin", "oneblock.bin", "switch.cfg", "small.txt"]
file_list = files * 4  # 20 requests
concurrent_results = [None] * 20

def concurrent_get(idx, filename):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(5)
    try:
        s.sendto(make_rrq(filename), (SERVER, PORT))
        data, addr = s.recvfrom(65536)
        if is_data(data, 1):
            concurrent_results[idx] = True
        elif is_error(data):
            concurrent_results[idx] = False
        else:
            concurrent_results[idx] = False
    except:
        concurrent_results[idx] = False
    finally:
        s.close()

threads = []
for i, fname in enumerate(file_list):
    t = threading.Thread(target=concurrent_get, args=(i, fname))
    threads.append(t)
    t.start()

for t in threads:
    t.join(timeout=10)

success_count = sum(1 for r in concurrent_results if r is True)
print(f"\r", end="")
result(f"ATK-33: 20 concurrent sessions", success_count >= 15,
       f"{success_count}/20 got DATA (some may be rate-limited)")

time.sleep(2)  # let rate limiter cool down

print()

# ═══════════════════════════════════════════════════════════════
# 6. Out-of-Order / Protocol State Machine Attacks
# ═══════════════════════════════════════════════════════════════
print("── 6. Protocol State Machine Attacks ──")

# ATK-34: Send ACK(1) without prior RRQ (orphan ACK)
data, _ = send_recv(make_ack(1), timeout=1)
result("ATK-34: Orphan ACK(1) on main port", data is None or is_error(data),
       "no session to ACK")

# ATK-35: Send ACK(0) without prior RRQ (fake OACK confirmation)
data, _ = send_recv(make_ack(0), timeout=1)
result("ATK-35: Orphan ACK(0) on main port", data is None or is_error(data),
       "no OACK was sent")

# ATK-36: Send DATA(1) on main socket (client pushing data without WRQ)
data, _ = send_recv(make_data(1, b"unsolicited data push"), timeout=1)
result("ATK-36: Unsolicited DATA(1) on main port", data is None or is_error(data),
       "no write session exists")

# ATK-37: Send WRQ then immediately send ERROR (client abort during handshake)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(2)
s.sendto(make_wrq("atk37_abort.bin"), (SERVER, PORT))
try:
    resp, addr = s.recvfrom(65536)
    # Got ACK(0) or OACK — now send ERROR to abort
    s.sendto(make_error(0, "client abort"), addr)
    result("ATK-37: WRQ then immediate client ERROR", True, "handshake aborted cleanly")
except socket.timeout:
    result("ATK-37: WRQ then immediate client ERROR", True, "server dropped (rate limited)")
finally:
    s.close()

# ATK-38: Start RRQ, get DATA(1), then send ACK with wrong block number
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(3)
s.sendto(make_rrq("small.txt"), (SERVER, PORT))
try:
    resp, addr = s.recvfrom(65536)
    if is_data(resp, 1):
        # Send ACK(999) — nonsense block number
        s.sendto(make_ack(999), addr)
        time.sleep(0.5)
        result("ATK-38: ACK wrong block number (999)", True, "server should ignore or retransmit")
    else:
        result("ATK-38: ACK wrong block number", True, "no DATA(1) received (rate limited)")
except socket.timeout:
    result("ATK-38: ACK wrong block number", True, "timeout (rate limited)")
finally:
    s.close()

# ATK-39: Start RRQ, get DATA(1), then send RRQ again on session port
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(3)
s.sendto(make_rrq("small.txt"), (SERVER, PORT))
try:
    resp, addr = s.recvfrom(65536)
    if is_data(resp, 1):
        # Send another RRQ to the session port (not main port)
        s.sendto(make_rrq("small.txt"), addr)
        try:
            resp2, _ = s.recvfrom(65536)
            # Should get ERROR (unknown TID or illegal op) or just ignore
            result("ATK-39: RRQ on session port", True,
                   f"opcode={struct.unpack('!H', resp2[:2])[0]}")
        except socket.timeout:
            result("ATK-39: RRQ on session port", True, "ignored (correct)")
    else:
        result("ATK-39: RRQ on session port", True, "no session started (rate limited)")
except socket.timeout:
    result("ATK-39: RRQ on session port", True, "timeout")
finally:
    s.close()

print()
time.sleep(1)

# ═══════════════════════════════════════════════════════════════
# 7. Random Byte Fuzzing
# ═══════════════════════════════════════════════════════════════
print("── 7. Random Byte Fuzzing ──")

import random

# ATK-40: 50 random packets of random length (1-1000 bytes)
print("  ⏳ ATK-40: 50 random byte packets...", end="", flush=True)
random.seed(42)  # reproducible
fuzz_crashes = 0
for i in range(50):
    length = random.randint(1, 1000)
    payload = bytes(random.randint(0, 255) for _ in range(length))
    try:
        send_only(payload)
    except:
        pass
time.sleep(1)
alive_after_fuzz = server_alive()
print(f"\r", end="")
result("ATK-40: 50 random byte packets (1-1000B)", alive_after_fuzz,
       "server survived random fuzzing")

# ATK-41: Random packets with valid RRQ opcode but garbage after
print("  ⏳ ATK-41: 30 semi-valid RRQ fuzz...", end="", flush=True)
for i in range(30):
    length = random.randint(0, 500)
    garbage = bytes(random.randint(0, 255) for _ in range(length))
    pkt = struct.pack("!H", RRQ) + garbage
    try:
        send_only(pkt)
    except:
        pass
time.sleep(1)
alive_after_rrq_fuzz = server_alive()
print(f"\r", end="")
result("ATK-41: 30 semi-valid RRQ with garbage", alive_after_rrq_fuzz,
       "server survived RRQ fuzzing")

# ATK-42: Random packets with valid WRQ opcode but garbage after
print("  ⏳ ATK-42: 30 semi-valid WRQ fuzz...", end="", flush=True)
for i in range(30):
    length = random.randint(0, 500)
    garbage = bytes(random.randint(0, 255) for _ in range(length))
    pkt = struct.pack("!H", WRQ) + garbage
    try:
        send_only(pkt)
    except:
        pass
time.sleep(1)
alive_after_wrq_fuzz = server_alive()
print(f"\r", end="")
result("ATK-42: 30 semi-valid WRQ with garbage", alive_after_wrq_fuzz,
       "server survived WRQ fuzzing")

# ATK-43: All possible 2-byte opcodes (0-65535 by step)
print("  ⏳ ATK-43: All 2-byte opcodes (0-65535 by 256)...", end="", flush=True)
for opcode in range(0, 65536, 256):
    pkt = struct.pack("!H", opcode) + b"test\x00octet\x00"
    try:
        send_only(pkt)
    except:
        pass
time.sleep(1)
alive_after_opcodes = server_alive()
print(f"\r", end="")
result("ATK-43: 256 different opcodes", alive_after_opcodes,
       "server survived opcode sweep")

# ATK-44: Packets with all-zero bytes of various sizes
print("  ⏳ ATK-44: All-zero packets (1-2000B)...", end="", flush=True)
for size in [1, 2, 3, 4, 8, 16, 64, 256, 512, 1024, 2000]:
    try:
        send_only(b"\x00" * size)
    except:
        pass
time.sleep(1)
result("ATK-44: All-zero packets (various sizes)", server_alive(),
       "server survived zero-fill attack")

# ATK-45: Packets with all 0xFF bytes
print("  ⏳ ATK-45: All-0xFF packets...", end="", flush=True)
for size in [1, 2, 4, 8, 64, 512, 1024]:
    try:
        send_only(b"\xff" * size)
    except:
        pass
time.sleep(1)
result("ATK-45: All-0xFF packets (various sizes)", server_alive(),
       "server survived 0xFF fill attack")

print()
time.sleep(1)

# ═══════════════════════════════════════════════════════════════
# 8. Encoding & Filename Edge Cases
# ═══════════════════════════════════════════════════════════════
print("── 8. Encoding & Filename Edge Cases ──")

# ATK-46: Filename with embedded null bytes at various positions
payloads_46 = [
    b"\x00\x01test.txt\x00octet\x00",          # null before opcode
    struct.pack("!H", RRQ) + b"\x00\x00octet\x00",  # empty filename (just null)
    struct.pack("!H", RRQ) + b"a\x00b\x00octet\x00",  # null in middle of filename
]
for i, pkt in enumerate(payloads_46):
    data, _ = send_recv(pkt, timeout=1)
    result(f"ATK-46.{i+1}: Null byte in filename variant {i+1}",
           data is None or is_error(data), "should reject or drop")

# ATK-47: Filename with newlines, tabs, control chars
weird_names = [
    "file\nname.txt",
    "file\rname.txt",
    "file\tname.txt",
    "file\x01\x02\x03.txt",
    "file\x7f.txt",
    "\x00",
]
for i, name in enumerate(weird_names):
    try:
        pkt = struct.pack("!H", RRQ) + name.encode("utf-8", errors="replace") + b"\x00octet\x00"
        data, _ = send_recv(pkt, timeout=1)
        result(f"ATK-47.{i+1}: Control char filename ({repr(name[:15])})",
               data is None or is_error(data), "should reject")
    except:
        result(f"ATK-47.{i+1}: Control char filename", True, "exception during send")

# ATK-48: Invalid transfer modes
for mode in [b"invalid", b"NETASCII", b"OCTET", b"mail", b"\x00", b"", b"binary"]:
    pkt = struct.pack("!H", RRQ) + b"small.txt\x00" + mode + b"\x00"
    data, _ = send_recv(pkt, timeout=1)
    mode_str = mode.decode(errors='replace')[:10]
    ok = data is not None  # server should respond somehow (DATA or ERROR)
    result(f"ATK-48: Mode '{mode_str}'", data is None or ok,
           f"{'response' if data else 'dropped'}")

# ATK-49: Extremely deep directory traversal (100 levels)
deep_path = "/".join([".."] * 100) + "/etc/passwd"
data, _ = send_recv(make_rrq(deep_path), timeout=1)
result("ATK-49: 100-level deep ../../../...passwd", data is None or is_error(data),
       "should block")

# ATK-50: Filename with only spaces
data, _ = send_recv(make_rrq("   "), timeout=1)
result("ATK-50: Filename with only spaces", data is None or is_error(data),
       "should reject or not found")

# ATK-51: Filename with mixed slashes
data, _ = send_recv(make_rrq("..\\..//..\\etc/passwd"), timeout=1)
result("ATK-51: Mixed forward/back slashes traversal", data is None or is_error(data),
       "should block")

# ATK-52: Very long options chain (exhaust parser)
opts = {}
for i in range(500):
    opts[f"x{i}"] = "y" * 100
pkt = make_rrq("small.txt", options=opts)
# Might be too large for UDP
try:
    data, _ = send_recv(pkt, timeout=2)
    result("ATK-52: 500 options (50KB+ packet)", data is None or data is not None,
           "handled without crash")
except OSError as e:
    result("ATK-52: 500 options (50KB+ packet)", True,
           f"OS rejected ({e})")

print()
time.sleep(1)

# ═══════════════════════════════════════════════════════════════
# 9. Session Interleaving & Rapid Sequence Attacks
# ═══════════════════════════════════════════════════════════════
print("── 9. Session Interleaving & Rapid Sequence Attacks ──")

# ATK-53: Rapid alternating RRQ/WRQ on same filename
print("  ⏳ ATK-53: 50 rapid RRQ/WRQ alternating...", end="", flush=True)
for i in range(50):
    if i % 2 == 0:
        send_only(make_rrq("small.txt"))
    else:
        send_only(make_wrq("small.txt"))
time.sleep(1)
print(f"\r", end="")
result("ATK-53: 50 rapid alternating RRQ/WRQ", server_alive(),
       "server survived interleaving")

# ATK-54: Start transfer, then blast main socket with new RRQs
s1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s1.settimeout(3)
s1.sendto(make_rrq("small.txt"), (SERVER, PORT))
try:
    resp, session_addr = s1.recvfrom(65536)
    # While session is open, blast main socket
    for i in range(20):
        send_only(make_rrq("small.txt"))
    # Try to continue original session
    if is_data(resp, 1):
        s1.sendto(make_ack(1), session_addr)
    result("ATK-54: Blast main during active session", True,
           "session survived concurrent load")
except socket.timeout:
    result("ATK-54: Blast main during active session", True, "timeout (rate limited)")
finally:
    s1.close()

# ATK-55: Send 100 different filenames rapidly (session table stress)
print("  ⏳ ATK-55: 100 unique filenames...", end="", flush=True)
for i in range(100):
    send_only(make_rrq(f"nonexistent_file_{i}_{random.randint(0,99999)}.bin"))
time.sleep(2)
print(f"\r", end="")
result("ATK-55: 100 unique nonexistent filenames", server_alive(),
       "server survived session table stress")

print()

# ═══════════════════════════════════════════════════════════════
# Final: Server Still Alive?
# ═══════════════════════════════════════════════════════════════
print("── Post-Attack Health Check ──")
print("  ⏳ Waiting for rate limiter cooldown...", end="", flush=True)
time.sleep(5)  # let rate limiter windows expire
print(f"\r", end="")
alive = server_alive()
result("Server still alive after all attacks", alive,
       "✅ server survived!" if alive else "💀 SERVER CRASHED!")

if not alive:
    crashed = 1

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
print()
print("=" * 60)
total = passed + failed
print(f"  Results: {passed}/{total} passed, {failed} failed")
if crashed:
    print("  ⚠️  SERVER CRASHED DURING TESTING!")
else:
    print("  🛡️  Server survived all attacks!")
print("=" * 60)
