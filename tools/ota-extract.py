#!/usr/bin/env python3
"""Rebuild a baseline firmware image from a captured official OTA update.

You cannot read the controller's app flash back over Bluetooth (docs/07 §10),
so the way to get your own baseline image is to capture the vendor app doing an
official firmware update and reassemble the bytes it sends. See docs/09 for the
capture steps (Android Bluetooth HCI snoop log).

This tool takes a btsnoop log, finds the VESC WRITE_NEW_APP_DATA (id 3) packets
on the Nordic UART RX characteristic, orders their chunks by offset, and writes
the reassembled firmware image. It also understands the ERASE_NEW_APP (id 2)
header so it can size the image and drop the 6-byte staging header.

    python3 ota-extract.py btsnoop_hci.log -o my_baseline.bin

The output is a firmware blob -- a derivative of the vendor firmware. It is
gitignored and must stay private; never commit or share it.

NOTE: btsnoop captures raw ATT writes. VESC frames are reassembled across the
20-byte BLE chunks first, then decoded. If the app compresses with the LZO
variant (id 81) this simple extractor will not decompress it -- capture an
uncompressed update, or extend this tool.
"""
import argparse, struct, sys

WRITE_NEW_APP_DATA, ERASE_NEW_APP = 3, 2

# reuse the exact framing/CRC from the uploader so decode matches the device.
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "vesc_fw_upload", os.path.join(os.path.dirname(__file__), "vesc-fw-upload.py"))
_vfu = importlib.util.module_from_spec(_spec)
# the uploader imports bleak at module load; guard so this tool runs without it.
try:
    _spec.loader.exec_module(_vfu)
    Unframer, build_image = _vfu.Unframer, _vfu.build_image
except Exception:  # bleak missing -- fall back to a local copy of the framing.
    def _crc16(data):
        crc = 0
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        return crc

    class Unframer:
        def __init__(self): self.buf = bytearray()
        def feed(self, chunk):
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
                if self.buf[total - 1] == 3 and rx == _crc16(pl):
                    out.append(pl); del self.buf[:total]
                else:
                    self.buf.pop(0)
            return out


def read_btsnoop(path):
    """Yield the payload bytes of each packet record in a btsnoop file.

    btsnoop v1: 16-byte header ("btsnoop\\0" + u32 version + u32 datalink),
    then records of [u32 orig_len][u32 incl_len][u32 flags][u32 drops]
    [u64 timestamp][data]. We hand back the raw HCI data for the caller to
    scan; VESC reassembly tolerates non-UART noise because the Unframer
    resyncs on the frame start bytes.
    """
    with open(path, "rb") as f:
        hdr = f.read(16)
        if hdr[:8] != b"btsnoop\x00":
            sys.exit("not a btsnoop file (missing magic). See docs/09 for capture steps.")
        while True:
            rec = f.read(24)
            if len(rec) < 24:
                break
            _orig, incl, _flags, _drops, _ts = struct.unpack(">IIIIq", rec)
            data = f.read(incl)
            if len(data) < incl:
                break
            yield data


def extract(path, verbose):
    """Return the reassembled firmware bytes from the capture."""
    un = Unframer()
    chunks = {}          # offset -> data
    image_size = None
    for data in read_btsnoop(path):
        # feed the whole HCI record; the Unframer locks onto VESC frames and
        # ignores the surrounding ACL/L2CAP/ATT bytes by resyncing on 0x02/03/04.
        for pl in un.feed(data):
            if not pl:
                continue
            if pl[0] == ERASE_NEW_APP and len(pl) >= 5:
                image_size = struct.unpack(">I", pl[1:5])[0]
                if verbose:
                    print(f"  ERASE_NEW_APP: staged image size = {image_size}", file=sys.stderr)
            elif pl[0] == WRITE_NEW_APP_DATA and len(pl) >= 5:
                off = struct.unpack(">I", pl[1:5])[0]
                chunks[off] = pl[5:]
    if not chunks:
        sys.exit("no WRITE_NEW_APP_DATA packets found. Was a firmware update actually "
                 "captured on the controller's Nordic UART RX? See docs/09.")

    # stitch chunks in offset order into the staged image.
    staged = bytearray()
    for off in sorted(chunks):
        if off != len(staged):
            print(f"  warning: gap/overlap at offset {off} (have {len(staged)})", file=sys.stderr)
        staged[off:off + len(chunks[off])] = chunks[off]

    # staged image = [u32 size BE][u16 crc16 BE][fw]. drop the 6-byte header.
    if len(staged) < 6:
        sys.exit("captured data too short to be a staged image")
    declared = struct.unpack(">I", staged[:4])[0]
    fw = bytes(staged[6:6 + declared]) if declared else bytes(staged[6:])
    if verbose:
        print(f"  staged bytes captured: {len(staged)}", file=sys.stderr)
        print(f"  header declares fw size: {declared}", file=sys.stderr)
        print(f"  firmware extracted: {len(fw)} bytes", file=sys.stderr)
    if image_size and image_size != len(staged):
        print(f"  warning: captured {len(staged)} bytes but ERASE declared "
              f"{image_size}; capture may be incomplete", file=sys.stderr)
    return fw


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("btsnoop", help="path to the captured btsnoop_hci.log")
    ap.add_argument("-o", "--out", default="my_baseline.bin", help="output firmware image")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    fw = extract(a.btsnoop, a.verbose)
    with open(a.out, "wb") as f:
        f.write(fw)
    import hashlib
    print(f"wrote {a.out}  ({len(fw)} bytes, md5 {hashlib.md5(fw).hexdigest()})")
    print("check this against build-canrx-fw.py's known fingerprint before patching.")


if __name__ == "__main__":
    main()
