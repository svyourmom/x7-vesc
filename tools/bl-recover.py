#!/usr/bin/env python3
"""Bootloader recovery over the X-9000's BLE Nordic UART bridge, by REPLAYING the
official app's boot_loader.json transcript verbatim and verifying every device ack.

    python3 bl-recover.py plan       boot_loader.json      # decode + print, NO Bluetooth
    python3 bl-recover.py preflight                        # read fw id over BLE (no writing)
    python3 bl-recover.py send       boot_loader.json --yes   # DANGER: replays 73 -> 81xN -> 3

Why replay (not synthesize): the transcript is a complete, self-contained "write the
stock bootloader" recording (ERASE_BOOTLOADER(73), then WRITE_NEW_APP_DATA_LZO(81)
blocks, then a raw WRITE tail). Replaying the exact bytes and checking each recorded
`rxd` ack is the safest form of recovery -- this tool never invents a packet and
aborts the instant an ack does not match. See ../docs/10-bootloader-over-ble.md.

boot_loader.json is EBMX/VESC copyright and is NOT shipped here (gitignored); extract
it from your own copy of the app.

DANGER: this erases and rewrites the RESIDENT BOOTLOADER. A bad/interrupted run can
brick the controller; recovery then = ST-Link on the SWD pads. Wheel off the ground,
stable power, hardware you own, only on a controller whose bootloader is already suspect.
"""
import argparse, asyncio, json, sys, time

ADDR   = "C5:22:A5:12:A4:9F"      # set to your controller, or adapt to scan by name CYCMOTOR
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
FW_VERSION = 0

def crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc
assert crc16(b"123456789") == 0x31C3

def deframe(p):
    b = bytes(p)
    if b[0] == 2: ln = b[1];                       off = 2 + ln
    elif b[0] == 3: ln = (b[1] << 8) | b[2];       off = 3 + ln
    elif b[0] == 4: ln = (b[1]<<16)|(b[2]<<8)|b[3];off = 4 + ln
    else: raise ValueError("bad frame start")
    payload = b[b[0]: off]  # after the [start + len] bytes, up to the crc
    crc = (b[off] << 8) | b[off+1]
    return payload, crc, b[off+2]

def _load_transcript(path):
    doc = json.load(open(path))
    txd = [bytes(p) for p in doc["txd"]]
    rxd = [bytes(p) for p in doc["rxd"]]
    # sanity: every frame well-formed and crc-correct
    for tag, seq in (("txd", txd), ("rxd", rxd)):
        for i, fr in enumerate(seq):
            pl, crc, end = deframe(fr)
            if end != 3 or crc != crc16(pl):
                sys.exit(f"{tag}[{i}] is not a valid VESC frame -- refusing")
    return txd, rxd

def _describe(txd):
    names = {0x49: "ERASE_BOOTLOADER(73)", 0x51: "WRITE_NEW_APP_DATA_LZO(81)", 0x03: "WRITE(3,raw)"}
    for i, fr in enumerate(txd):
        pl, _, _ = deframe(fr)
        print(f"  txd[{i:2}] {names.get(pl[0], hex(pl[0])):26} framed={len(fr)}B")

def cmd_plan(a):
    txd, rxd = _load_transcript(a.json)
    print(f"transcript {a.json}: {len(txd)} txd / {len(rxd)} rxd, all frames CRC-valid\n")
    _describe(txd)
    print("\n(plan only -- no Bluetooth was used)")

class Unframer:
    def __init__(self): self.buf = bytearray()
    def feed(self, chunk):
        self.buf += chunk; out = []
        while True:
            while self.buf and self.buf[0] not in (2, 3, 4): self.buf.pop(0)
            if not self.buf: break
            s = self.buf[0]; nlen = s - 1
            if len(self.buf) < 1 + nlen: break
            n = int.from_bytes(self.buf[1:1+nlen], "big")
            total = 1 + nlen + n + 3
            if len(self.buf) < total: break
            pl = bytes(self.buf[1+nlen:1+nlen+n])
            rx = int.from_bytes(self.buf[1+nlen+n:1+nlen+n+2], "big")
            if self.buf[total-1] == 3 and rx == crc16(pl):
                out.append(pl); del self.buf[:total]
            else:
                self.buf.pop(0)
        return out

async def _connect():
    from bleak import BleakScanner
    dev = await BleakScanner.find_device_by_address(ADDR, timeout=25.0)
    if dev is None: sys.exit(f"{ADDR} not advertising -- powered on and in range?")
    return dev

def _decode_fw(pl):
    hw = pl[3:].split(b"\x00")[0].decode("utf-8", "replace") if len(pl) > 3 else ""
    return {"fw": f"{pl[1]}.{pl[2]}", "hw": hw} if len(pl) >= 3 else None

def cmd_preflight(a):
    from bleak import BleakClient
    async def run():
        dev = await _connect(); un = Unframer(); got = []
        def on(_, d):
            for pl in un.feed(bytes(d)):
                if pl and pl[0] == FW_VERSION: got.append(_decode_fw(pl))
        # frame a FW_VERSION request
        pl = bytes([FW_VERSION]); c = crc16(pl); pkt = bytes([2, len(pl)]) + pl + bytes([c >> 8, c & 0xFF, 3])
        async with BleakClient(dev, timeout=30.0) as c2:
            print(f"connected to {dev.name} [{dev.address}]")
            await c2.start_notify(NUS_TX, on)
            for i in range(0, len(pkt), 20):
                await c2.write_gatt_char(NUS_RX, pkt[i:i+20], response=False); await asyncio.sleep(0.02)
            await asyncio.sleep(2.0); await c2.stop_notify(NUS_TX)
        print("FW_VERSION:", got[-1] if got else "(no reply)")
    asyncio.run(run())

def cmd_send(a):
    from bleak import BleakClient
    txd, rxd = _load_transcript(a.json)
    print(f"about to REPLAY {len(txd)} packets that ERASE and REWRITE the resident bootloader.")
    print("this is the highest-brick-risk operation. SWD/ST-Link is the only recovery if it fails.")
    if not a.yes:
        sys.exit("refusing without --yes")
    if input('type "RECOVER" to proceed: ').strip() != "RECOVER":
        sys.exit("aborted")

    async def run():
        dev = await _connect(); un = Unframer(); acks = asyncio.Queue()
        def on(_, d):
            for pl in un.feed(bytes(d)): acks.put_nowait(pl)
        async def send_raw(client, framed):
            for i in range(0, len(framed), 20):
                await client.write_gatt_char(NUS_RX, framed[i:i+20], response=False)
                await asyncio.sleep(0.006)
        async def next_ack(timeout):
            try: return await asyncio.wait_for(acks.get(), timeout=timeout)
            except asyncio.TimeoutError: return None
        async with BleakClient(dev, timeout=30.0) as client:
            print(f"connected to {dev.name} [{dev.address}]")
            await client.start_notify(NUS_TX, on)
            for i, fr in enumerate(txd):
                exp_pl, _, _ = deframe(rxd[i])
                await send_raw(client, fr)
                got = await next_ack(15 if i == 0 else 8)
                if got is None:
                    sys.exit(f"\n  ack timeout at txd[{i}] -- ABORTING. Do NOT power-cycle blindly; "
                             f"re-run 'preflight' to see if the app still responds.")
                if got != exp_pl:
                    sys.exit(f"\n  ack MISMATCH at txd[{i}]: got {got.hex()} expected {exp_pl.hex()} "
                             f"-- ABORTING before sending more.")
                print(f"\r  replayed {i+1}/{len(txd)} (ack ok: {got.hex()})", end="", flush=True)
            print("\n  all packets acked as recorded. Bootloader write replayed successfully.")
            print("  reconnect and run 'preflight'; then re-flash your app image (vesc-fw-upload.py).")
            await client.stop_notify(NUS_TX)
    asyncio.run(run())

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan");      p.add_argument("json"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("preflight"); p.set_defaults(fn=cmd_preflight)
    p = sub.add_parser("send");      p.add_argument("json"); p.add_argument("--yes", action="store_true"); p.set_defaults(fn=cmd_send)
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
