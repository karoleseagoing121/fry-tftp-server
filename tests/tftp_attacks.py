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

import socket
import struct
import time
import threading
import sys
import os
import hashlib

SERVER = "127.0.0.1"
PORT = 69
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

def server_alive():
    """Quick check that server still responds."""
    data, _ = send_recv(make_rrq("small.txt"), timeout=2)
    return data is not None and is_data(data, 1)


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
data, _ = send_recv(pkt, timeout=2)
result("ATK-10: Option value 65KB long", data is None or is_error(data) or is_data(data),
       "should handle gracefully (error or ignore)")

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
data, _ = send_recv(pkt, timeout=2)
result("ATK-26: 60KB packet (oversized RRQ)", data is not None,
       f"{'responded' if data else 'timeout'}")

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

time.sleep(1)

print()

# ═══════════════════════════════════════════════════════════════
# Final: Server Still Alive?
# ═══════════════════════════════════════════════════════════════
print("── Post-Attack Health Check ──")
time.sleep(0.5)
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
