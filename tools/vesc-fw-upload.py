#!/usr/bin/env python3
"""VESC firmware uploader over the X-9000's BLE Nordic UART bridge.

Replicates vesc_tool's app-upload flow (verified against this firmware in Ghidra:
ERASE_NEW_APP=2, WRITE_NEW_APP_DATA=3, JUMP_TO_BOOTLOADER=1; NEW_APP_BASE = flash
sector 8 @0x08080000; header = big-endian [u32 size][u16 crc16-xmodem(fw)] then fw;
the bootloader validates the CRC BEFORE copying staging->app, so a bad/rejected
image fails safe and leaves the running app intact).

    # zero-risk: build the stream and inspect it, NO Bluetooth
    .venv/bin/python src/vesc-fw-upload.py plan  reference/firmware/X9KV3_260714.bin

    # read the current fw id over BLE (no writing)
    .venv/bin/python src/vesc-fw-upload.py preflight

    # ACTUALLY FLASH (requires the bin, --yes, and you present with recovery ready)
    .venv/bin/python src/vesc-fw-upload.py flash reference/firmware/X9KV3_260714.bin --yes

DANGER: `flash` erases the new-app staging area and, on JUMP_TO_BOOTLOADER, asks the
bootloader to overwrite the running firmware. Brick recovery = SWD/ST-Link on the board.
"""
import argparse, asyncio, struct, sys, time
from bleak import BleakScanner, BleakClient

ADDR   = "C5:22:A5:12:A4:9F"
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
ERASE_NEW_APP, WRITE_NEW_APP_DATA, JUMP_TO_BOOTLOADER, FW_VERSION = 2, 3, 1, 0
CHUNK = 240                       # data bytes/packet -> payload 245 <= 255 (short frame)

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
    def __init__(self): self.buf = bytearray()
    def feed(self, chunk: bytes):
        self.buf += chunk; out = []
        while True:
            while self.buf and self.buf[0] not in (2, 3, 4): self.buf.pop(0)
            if not self.buf: break
            s = self.buf[0]; nlen = s - 1
            if len(self.buf) < 1 + nlen: break
            n = int.from_bytes(self.buf[1:1 + nlen], "big")
            total = 1 + nlen + n + 3
            if len(self.buf) < total: break
            pl = bytes(self.buf[1 + nlen:1 + nlen + n])
            rx = int.from_bytes(self.buf[1 + nlen + n:1 + nlen + n + 2], "big")
            if self.buf[total - 1] == 3 and rx == crc16(pl):
                out.append(pl); del self.buf[:total]
            else:
                self.buf.pop(0)
        return out

def build_image(fw: bytes) -> bytes:
    """[u32 size BE][u16 crc16(fw) BE][fw]  -- exactly what vesc_tool stages."""
    return struct.pack(">IH", len(fw), crc16(fw)) + fw

def decode_fw(pl: bytes):
    if len(pl) < 3: return None
    hw = pl[3:].split(b"\x00")[0].decode("utf-8", "replace")
    return {"fw": f"{pl[1]}.{pl[2]}", "hw": hw}

def cmd_plan(args):
    fw = open(args.bin, "rb").read()
    img = build_image(fw)
    nchunks = (len(img) + CHUNK - 1) // CHUNK
    print(f"firmware file : {args.bin}")
    print(f"fw size       : {len(fw)} bytes")
    print(f"crc16(fw)     : 0x{crc16(fw):04X}")
    print(f"staged image  : {len(img)} bytes  (6-byte header + fw)")
    print(f"header (hex)   : {img[:6].hex()}   = size={struct.unpack('>I',img[:4])[0]} crc=0x{struct.unpack('>H',img[4:6])[0]:04X}")
    print(f"ERASE_NEW_APP  : 02 {len(img):08x}  (payload id=2 + u32 image size)")
    print(f"WRITE packets  : {nchunks} x (id=3 + u32 offset + <=240 data)")
    print(f"JUMP_TO_BOOTLOADER: 01")
    print(f"first WRITE pl : {(bytes([WRITE_NEW_APP_DATA])+struct.pack('>I',0)+img[:16]).hex()} ...")
    print("\n(plan only -- no Bluetooth was used)")

async def _connect():
    dev = await BleakScanner.find_device_by_address(ADDR, timeout=25.0)
    if dev is None: sys.exit(f"{ADDR} not advertising -- powered on and in range?")
    return dev

def cmd_preflight(args):
    async def run():
        dev = await _connect(); un = Unframer(); got = []
        def on(_, d):
            for pl in un.feed(bytes(d)):
                if pl and pl[0] == FW_VERSION: got.append(decode_fw(pl))
        async with BleakClient(dev, timeout=30.0) as c:
            print(f"connected to {dev.name} [{dev.address}]")
            await c.start_notify(NUS_TX, on)
            pkt = frame(bytes([FW_VERSION]))
            for i in range(0, len(pkt), 20):
                await c.write_gatt_char(NUS_RX, pkt[i:i+20], response=False); await asyncio.sleep(0.02)
            await asyncio.sleep(2.0); await c.stop_notify(NUS_TX)
        print("FW_VERSION:", got[-1] if got else "(no reply)")
    asyncio.run(run())

def cmd_flash(args):
    fw = open(args.bin, "rb").read()
    img = build_image(fw)
    nchunks = (len(img) + CHUNK - 1) // CHUNK
    print(f"about to FLASH {args.bin}: fw={len(fw)}B crc=0x{crc16(fw):04X} image={len(img)}B "
          f"({nchunks} write packets)")
    if not args.yes:
        sys.exit("refusing to flash without --yes")
    if input('type "FLASH" to proceed: ').strip() != "FLASH":
        sys.exit("aborted")

    async def run():
        dev = await _connect(); un = Unframer()
        acks = asyncio.Queue()
        def on(_, d):
            for pl in un.feed(bytes(d)):
                if pl: acks.put_nowait(pl)
        async def send(client, payload):
            pkt = frame(payload)
            for i in range(0, len(pkt), 20):
                await client.write_gatt_char(NUS_RX, pkt[i:i+20], response=False)
                await asyncio.sleep(0.006)
        async def wait_ack(cmd_id, timeout):
            end = time.time() + timeout
            while time.time() < end:
                try:
                    pl = await asyncio.wait_for(acks.get(), timeout=max(end - time.time(), 0.01))
                except asyncio.TimeoutError:
                    break
                if pl and pl[0] == cmd_id: return pl
            return None
        async with BleakClient(dev, timeout=30.0) as client:
            print(f"connected to {dev.name} [{dev.address}]")
            await client.start_notify(NUS_TX, on)
            # pre-flight fw id
            await send(client, bytes([FW_VERSION])); pl = await wait_ack(FW_VERSION, 3)
            print("  before:", decode_fw(pl) if pl else "(no fw reply)")
            # erase
            print("  ERASE_NEW_APP ...")
            await send(client, bytes([ERASE_NEW_APP]) + struct.pack(">I", len(img)))
            pl = await wait_ack(ERASE_NEW_APP, 15)
            if pl is None: sys.exit("  ERASE ack timeout -- aborting (nothing copied yet)")
            print(f"  erase ack: {pl.hex()}")
            # write chunks
            t0 = time.time()
            for k in range(nchunks):
                off = k * CHUNK
                await send(client, bytes([WRITE_NEW_APP_DATA]) + struct.pack(">I", off) + img[off:off+CHUNK])
                pl = await wait_ack(WRITE_NEW_APP_DATA, 4)
                if pl is None: sys.exit(f"\n  WRITE ack timeout at offset {off} -- aborting (no jump sent; running app intact)")
                if k % 25 == 0 or k == nchunks-1:
                    pct = 100*(k+1)/nchunks; rate=(off+CHUNK)/max(time.time()-t0,1e-3)
                    print(f"\r  writing {k+1}/{nchunks} ({pct:4.1f}%)  {rate/1024:5.1f} KiB/s", end="", flush=True)
            print("\n  all chunks acked.")
            if args.no_jump:
                print("  --no-jump: staged but NOT jumping. Send JUMP_TO_BOOTLOADER later to apply.")
            else:
                print("  JUMP_TO_BOOTLOADER (device will reboot & bootloader validates+copies) ...")
                await send(client, bytes([JUMP_TO_BOOTLOADER]))
                await asyncio.sleep(1.0)
            await client.stop_notify(NUS_TX)
        print("done. If it took: reconnect and check fw id. If not: running app was kept (CRC-validated copy).")
    asyncio.run(run())

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("bin"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("preflight"); p.set_defaults(fn=cmd_preflight)
    p = sub.add_parser("flash"); p.add_argument("bin"); p.add_argument("--yes", action="store_true")
    p.add_argument("--no-jump", action="store_true", help="stage only, do not JUMP_TO_BOOTLOADER")
    p.set_defaults(fn=cmd_flash)
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
