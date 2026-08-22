#!/usr/bin/env python3
"""Speak the VESC packet protocol to the X-9000 over its BLE Nordic UART bridge.

    ./src/vesc-ble.py fw                 # COMM_FW_VERSION  -- the handshake test
    ./src/vesc-ble.py values             # COMM_GET_VALUES
    ./src/vesc-ble.py setup              # COMM_GET_VALUES_SETUP (battery level lives here)
    ./src/vesc-ble.py listen --secs 20   # passive: does it push anything unasked?
    ./src/vesc-ble.py raw 00             # arbitrary payload, hex

THE LINK
  C5:22:A5:12:A4:9F "CYCMOTOR" advertises the Nordic UART Service
  6e400001-b5a3-f393-e0a9-e50e24dcca9e -- the standard VESC BLE bridge.
    RX 6e400002 [write, write-without-response]   host -> controller
    TX 6e400003 [notify]                          controller -> host
  No pairing, no bonding. MTU 23, so 20-byte ATT chunks in both directions.

FRAMING (VESC, verified against util/crc.c and packet.c)
    [0x02][len:u8]              [payload][crc:u16 BE][0x03]     len <= 255
    [0x03][len:u16 BE]          [payload][crc:u16 BE][0x03]     len <= 65535
    [0x04][len:u24 BE]          [payload][crc:u16 BE][0x03]
  CRC-16/XMODEM (poly 0x1021, init 0, no reflect, no final xor) over PAYLOAD ONLY.
  payload[0] is the command id.  All integers big-endian.

SAFETY
  Command ids that can spin the motor are refused unless --force is given.
  Nothing in the default subcommands writes state; they are all queries.
"""
import argparse, asyncio, struct, sys, time
from bleak import BleakScanner, BleakClient

ADDR    = "C5:22:A5:12:A4:9F"
NUS_RX  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX  = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# ---- command ids (VESC 5.x/6.x commands.h). Confirm against the fw version reply.
COMM = {
    "FW_VERSION": 0, "GET_VALUES": 4,
    "SET_DUTY": 5, "SET_CURRENT": 6, "SET_CURRENT_BRAKE": 7, "SET_RPM": 8,
    "SET_POS": 9, "SET_HANDBRAKE": 10, "SET_DETECT": 11, "SET_SERVO_POS": 12,
    "SET_MCCONF": 13, "GET_MCCONF": 14, "GET_MCCONF_DEFAULT": 15,
    "SET_APPCONF": 16, "GET_APPCONF": 17, "GET_APPCONF_DEFAULT": 18,
    "TERMINAL_CMD": 20, "GET_DECODED_PPM": 31, "GET_DECODED_ADC": 32,
    "GET_DECODED_CHUK": 33, "CUSTOM_APP_DATA": 36,
    "GET_VALUES_SETUP": 47, "SET_MCCONF_TEMP": 48, "SET_MCCONF_TEMP_SETUP": 49,
    "GET_VALUES_SELECTIVE": 50, "GET_VALUES_SETUP_SELECTIVE": 51,
    "PING_CAN": 62, "GET_IMU_DATA": 65,
}
# Anything that can command torque. Refused without --force.
DANGEROUS = {1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 24, 25, 26, 27, 28, 29, 30}

def crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc

assert crc16(b"123456789") == 0x31C3, "CRC-16/XMODEM check value failed"

def frame(payload: bytes) -> bytes:
    n = len(payload)
    if n <= 255:      hdr = bytes([2, n])
    elif n <= 65535:  hdr = bytes([3, n >> 8, n & 0xFF])
    else:             hdr = bytes([4, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])
    c = crc16(payload)
    return hdr + payload + bytes([c >> 8, c & 0xFF, 3])

class Unframer:
    """Reassembles VESC packets out of the 20-byte notification chunks."""
    def __init__(self): self.buf = bytearray()
    def feed(self, chunk: bytes):
        self.buf += chunk
        out = []
        while True:
            # resync to a plausible start byte
            while self.buf and self.buf[0] not in (2, 3, 4):
                self.buf.pop(0)
            if not self.buf: break
            s = self.buf[0]; nlen = s - 1
            if len(self.buf) < 1 + nlen: break
            n = int.from_bytes(self.buf[1:1 + nlen], "big")
            total = 1 + nlen + n + 3
            if len(self.buf) < total: break
            pl = bytes(self.buf[1 + nlen:1 + nlen + n])
            rx_crc = int.from_bytes(self.buf[1 + nlen + n:1 + nlen + n + 2], "big")
            stop = self.buf[total - 1]
            if stop == 3 and rx_crc == crc16(pl):
                out.append(pl); del self.buf[:total]
            else:
                self.buf.pop(0)          # bad frame: resync one byte on
        return out

def decode_fw(pl: bytes):
    if len(pl) < 3: return None
    major, minor = pl[1], pl[2]
    rest = pl[3:]
    hw = rest.split(b"\x00")[0].decode("utf-8", "replace")
    rest = rest[len(hw) + 1:]
    uuid = rest[:12].hex() if len(rest) >= 12 else ""
    tail = rest[12:]
    d = {"fw": f"{major}.{minor}", "hw": hw, "uuid": uuid}
    names = ["pairing_done", "test_version", "hw_type", "cfg_num"]
    for i, nm in enumerate(names):
        if len(tail) > i: d[nm] = tail[i]
    return d

async def session(payloads, listen_secs, verbose=True):
    dev = await BleakScanner.find_device_by_address(ADDR, timeout=25.0)
    if dev is None:
        sys.exit(f"{ADDR} is not advertising -- powered on and in range?")
    un = Unframer()
    got = []
    def on_notify(_, data: bytearray):
        if verbose: print(f"  [rx chunk {len(data):2d}] {bytes(data).hex()}")
        for pl in un.feed(bytes(data)):
            got.append((time.time(), pl))
            print(f"  <== PACKET id={pl[0]} len={len(pl)}  {pl.hex()}")
            if pl[0] == 21:   # COMM_PRINT -- terminal output
                print("      PRINT: " + pl[1:].decode("utf-8", "replace").rstrip())
            if pl[0] == COMM["FW_VERSION"]:
                print(f"      FW_VERSION -> {decode_fw(pl)}")
    async with BleakClient(dev, timeout=30.0) as c:
        print(f"connected to {dev.name} [{dev.address}]")
        await c.start_notify(NUS_TX, on_notify)
        for pl in payloads:
            pkt = frame(pl)
            print(f"  ==> id={pl[0]} payload={pl.hex()}  frame={pkt.hex()}")
            for i in range(0, len(pkt), 20):
                await c.write_gatt_char(NUS_RX, pkt[i:i + 20], response=False)
                await asyncio.sleep(0.02)
            await asyncio.sleep(1.5)
        if listen_secs:
            print(f"listening {listen_secs}s ...")
            await asyncio.sleep(listen_secs)
        await c.stop_notify(NUS_TX)
    return got

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fw", "values", "setup", "listen", "raw", "probe", "sel", "term"])
    ap.add_argument("hex", nargs="?", help="payload hex, for `raw`")
    ap.add_argument("--secs", type=float, default=0.0)
    ap.add_argument("--force", action="store_true", help="permit motion command ids")
    a = ap.parse_args()

    if a.cmd == "fw":       pls = [bytes([COMM["FW_VERSION"]])]
    elif a.cmd == "values": pls = [bytes([COMM["GET_VALUES"]])]
    elif a.cmd == "setup":  pls = [bytes([COMM["GET_VALUES_SETUP"]])]
    elif a.cmd == "listen": pls = []; a.secs = a.secs or 20
    elif a.cmd == "term":
        pls = [bytes([COMM["TERMINAL_CMD"]]) + (a.hex or "help").encode()]
    elif a.cmd == "sel":
        # COMM_GET_VALUES_SETUP_SELECTIVE: one field at a time, no offset guesswork.
        pls = [bytes([COMM["GET_VALUES_SETUP_SELECTIVE"]]) + struct.pack(">I", 1 << b)
               for b in (int(x) for x in (a.hex or "7,8,9,19").split(","))]
    elif a.cmd == "probe":  pls = [bytes([i]) for i in (0, 4, 47, 14, 17, 65)]
    else:
        if not a.hex: sys.exit("raw needs a hex payload")
        pls = [bytes.fromhex(a.hex.replace(" ", ""))]

    for pl in pls:
        if pl[0] in DANGEROUS and not a.force:
            sys.exit(f"refusing command id {pl[0]}: it can command torque. --force to override.")
    asyncio.run(session(pls, a.secs))

if __name__ == "__main__":
    main()
