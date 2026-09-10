#!/usr/bin/env python3
"""Build the CAN-RX injector patched firmware from YOUR baseline image.

This does the byte surgery described in docs/06 + docs/09: it takes a copy of
your own baseline firmware (see docs/09 for how to get one), drops in the
hand-written CAN-RX stub, and rewires the unused id-113 COMM handler to reach
it. The result is a raw firmware image you flash with vesc-fw-upload.py.

    # dry run: show every edit, write nothing
    python3 build-canrx-fw.py plan  my_baseline.bin \\
        --defsym lock=0x... --defsym unlock=0x... \\
        --defsym signal=0x... --defsym exit=0x...

    # actually build the patched image
    python3 build-canrx-fw.py build my_baseline.bin -o build/x9kv3-canrx.bin \\
        --defsym lock=0x... --defsym unlock=0x... \\
        --defsym signal=0x... --defsym exit=0x...

NO firmware blob ships in this repo. You supply your own baseline; the patched
output is gitignored. Both are derivatives of the vendor firmware -- keep them
private.

IMPORTANT: every address here is specific to the ONE build below. The script
refuses any image whose fingerprint does not match, because on a different
build the addresses would be wrong and flashing the result could brick the
controller. The stub also calls four firmware functions (lock/unlock/signal/
exit) whose addresses you pass with --defsym -- find them in your disassembly
(docs/09). For a different build, re-derive everything and update KNOWN_BUILD.
"""
import argparse, hashlib, os, struct, subprocess, sys, tempfile
from shutil import which

# --- the one build these addresses were derived for -------------------------
# Fingerprint gate. A mismatch means the addresses below do not apply.
KNOWN_BUILD = {
    "name": "X9KV3_260714",
    "size": 393208,
    "md5": "5748c5d5ecd3456da81c96afbc31c06b",
    "load_base": 0x08000000,            # image byte 0 lives at this flash address

    # COMM dispatch: a Thumb TBH table indexed by command id (docs/03, docs/07).
    #   cmp r8,#0xff ; tbh [pc, r8, lsl #1]
    # Each entry is a u16 halfword; branch target = tbl_base + 2*halfword.
    "tbh_table": 0x0801aed4,            # also the PC base the TBH offsets count from
    "inject_cmd_id": 113,               # COMM_BMS_FWD_CAN_RX -- unused here
    "reject_handler": 0x0801b54c,       # where id 113 points today (sanity check)
}

# TBH offsets are u16, so a table entry can only reach the window below.
TBH_MAX_TARGET = KNOWN_BUILD["tbh_table"] + 2 * 0xFFFF

AS, LD, OC = "arm-none-eabi-as", "arm-none-eabi-ld", "arm-none-eabi-objcopy"


def md5(b): return hashlib.md5(b).hexdigest()


def check_fingerprint(fw):
    """Refuse anything that is not the known build. Bricking insurance."""
    if len(fw) != KNOWN_BUILD["size"] or md5(fw) != KNOWN_BUILD["md5"]:
        sys.exit(
            f"input does not match the known build {KNOWN_BUILD['name']} "
            f"(size {KNOWN_BUILD['size']}, md5 {KNOWN_BUILD['md5']}).\n"
            f"got size {len(fw)}, md5 {md5(fw)}.\n"
            "The patch addresses are build-specific. Re-derive them from your\n"
            "own disassembly (docs/09) before patching a different image."
        )


def assemble_stub(src, load_addr, defsyms):
    """Assemble+link canrx_stub.s at load_addr and return raw bytes.

    The stub's `bl lock/unlock/signal` and `b.w exit` are PC-relative to
    absolute firmware addresses, so it must be linked at its FINAL load address
    for those offsets to come out right. defsyms supplies those four addresses.
    """
    for t in (AS, LD, OC):
        if not which(t):
            sys.exit(f"{t} not found. Install the arm-none-eabi toolchain, or "
                     "pass a pre-assembled stub with --stub-bin (see docs/09).")
    need = {"lock", "unlock", "signal", "exit"}
    missing = need - set(defsyms)
    if missing:
        sys.exit("assembling the stub needs --defsym for: " + ", ".join(sorted(missing)) +
                 "\nfind these firmware addresses in your disassembly (docs/09), "
                 "or pass --stub-bin.")
    with tempfile.TemporaryDirectory() as d:
        obj, elf, binf = f"{d}/s.o", f"{d}/s.elf", f"{d}/s.bin"
        subprocess.run([AS, "-mthumb", "-mcpu=cortex-m4", src, "-o", obj], check=True)
        cmd = [LD, "-Ttext", hex(load_addr), obj, "-o", elf]
        for k, v in defsyms.items():
            cmd += ["--defsym", f"{k}=0x{v:08x}"]
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        subprocess.run([OC, "-O", "binary", elf, binf], check=True)
        return open(binf, "rb").read()


def find_fill_region(fw, need, fill, end=None):
    """Return (offset, length) of the LARGEST run of `fill` bytes >= need, else None.

    Used to place the stub in unused flash (0xFF) and the trampoline in padding
    (0x00) without ever overwriting code.
    """
    best_off, best_len, off, n = -1, 0, 0, len(fw) if end is None else min(end, len(fw))
    while off < n:
        if fw[off] != fill:
            off += 1; continue
        run = off
        while run < n and fw[run] == fill:
            run += 1
        if run - off > best_len:
            best_off, best_len = off, run - off
        off = run
    return (best_off, best_len) if best_len >= need else None


def make_trampoline(tramp_addr, stub_addr):
    """One Thumb-2 `b.w stub` (4 bytes). stub_addr should carry the Thumb bit."""
    off = (stub_addr & ~1) - (tramp_addr + 4)
    if off % 2:
        sys.exit("trampoline/stub misaligned")
    if not (-(1 << 24) <= off < (1 << 24)):
        sys.exit("stub too far for a b.w trampoline")
    s = (off >> 24) & 1
    imm10 = (off >> 12) & 0x3FF
    imm11 = (off >> 1) & 0x7FF
    i1 = (off >> 23) & 1
    i2 = (off >> 22) & 1
    j1 = (~(i1 ^ s)) & 1
    j2 = (~(i2 ^ s)) & 1
    hw1 = 0xF000 | (s << 10) | imm10
    hw2 = 0x9000 | (j1 << 13) | (j2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


def tbh_halfword(tbl_base, target_addr):
    """u16 that makes the TBH branch to target_addr (even, forward, in range)."""
    if target_addr <= tbl_base or target_addr > TBH_MAX_TARGET:
        sys.exit(f"trampoline 0x{target_addr:08x} is out of TBH reach "
                 f"(0x{tbl_base:08x}..0x{TBH_MAX_TARGET:08x})")
    if (target_addr - tbl_base) % 2:
        sys.exit("TBH target must be halfword-aligned")
    hw = (target_addr - tbl_base) // 2
    if hw > 0xFFFF:
        sys.exit("TBH offset overflows u16")
    return hw


def build_edits(fw, args, defsyms):
    """Compute the three edits. Returns (edits, stub_addr, tramp_addr).

    edit = (name, file_offset, old_bytes, new_bytes)
    """
    base = KNOWN_BUILD["load_base"]

    # --- 1. decide where the stub goes, then get its bytes at that address ---
    if args.stub_bin:
        stub = open(args.stub_bin, "rb").read()
        if args.stub_addr is None:
            sys.exit("--stub-bin needs --stub-addr (the address it was linked at)")
        stub_addr = args.stub_addr
    else:
        # probe size (byte length is stable across load addresses), then place.
        probe = assemble_stub(args.stub_src, base, defsyms)
        if args.stub_addr is not None:
            stub_addr = args.stub_addr
        else:
            region = find_fill_region(fw, len(probe), 0xFF)
            if region is None:
                sys.exit("no 0xFF region big enough for the stub; pass --stub-addr")
            stub_addr = base + region[0]
        stub = assemble_stub(args.stub_src, stub_addr, defsyms)   # link at final addr

    stub_off = stub_addr - base
    if stub_off < 0 or stub_off + len(stub) > len(fw):
        sys.exit(f"stub at 0x{stub_addr:08x} does not fit in the image")
    if any(b != 0xFF for b in fw[stub_off:stub_off + len(stub)]):
        sys.exit(f"stub target 0x{stub_addr:08x} is not all-0xFF (would overwrite "
                 "code); choose another --stub-addr")
    edits = [("stub", stub_off, fw[stub_off:stub_off + len(stub)], stub)]

    # --- 2. trampoline in a padding hole within TBH reach ---
    reach_end = TBH_MAX_TARGET - base
    if args.tramp_addr is not None:
        tramp_off = args.tramp_addr - base
    else:
        hole = find_fill_region(fw, 4, 0x00, end=reach_end) or \
               find_fill_region(fw, 4, 0xFF, end=reach_end)
        if hole is None:
            sys.exit("no padding hole within TBH reach for the trampoline; pass --tramp-addr")
        tramp_off = hole[0]
    tramp_addr = base + tramp_off
    if any(b not in (0x00, 0xFF) for b in fw[tramp_off:tramp_off + 4]):
        sys.exit(f"trampoline target 0x{tramp_addr:08x} is not padding (would "
                 "overwrite code); choose another --tramp-addr")
    edits.append(("trampoline", tramp_off, fw[tramp_off:tramp_off + 4],
                  make_trampoline(tramp_addr, stub_addr)))

    # --- 3. point the id-113 TBH entry at the trampoline ---
    ent_off = (KNOWN_BUILD["tbh_table"] + 2 * KNOWN_BUILD["inject_cmd_id"]) - base
    old_hw = struct.unpack_from("<H", fw, ent_off)[0]
    old_target = KNOWN_BUILD["tbh_table"] + 2 * old_hw
    if old_target != KNOWN_BUILD["reject_handler"]:
        print(f"  note: id-{KNOWN_BUILD['inject_cmd_id']} currently -> 0x{old_target:08x} "
              f"(expected reject 0x{KNOWN_BUILD['reject_handler']:08x})", file=sys.stderr)
    new_hw = tbh_halfword(KNOWN_BUILD["tbh_table"], tramp_addr)
    edits.append(("tbh_entry", ent_off,
                  struct.pack("<H", old_hw), struct.pack("<H", new_hw)))
    return edits, stub_addr, tramp_addr


def apply_edits(fw, edits):
    out = bytearray(fw)
    for _n, off, _old, new in edits:
        out[off:off + len(new)] = new
    return bytes(out)


def print_plan(edits, stub_addr, tramp_addr):
    base = KNOWN_BUILD["load_base"]
    print(f"stub load address  : 0x{stub_addr:08x}")
    print(f"trampoline address : 0x{tramp_addr:08x}")
    print(f"id-{KNOWN_BUILD['inject_cmd_id']} TBH entry   : "
          f"0x{KNOWN_BUILD['tbh_table'] + 2*KNOWN_BUILD['inject_cmd_id']:08x}")
    total = 0
    for name, off, old, new in edits:
        total += len(new)
        more = " ..." if len(new) > 8 else ""
        print(f"  {name:10s} @ 0x{base+off:08x}  {len(new):4d}B  "
              f"{old[:8].hex()}{more} -> {new[:8].hex()}{more}")
    print(f"total bytes changed: {total}")


def parse_defsyms(pairs):
    out = {}
    for p in pairs or []:
        if "=" not in p:
            sys.exit(f"--defsym expects NAME=ADDR, got {p!r}")
        k, v = p.split("=", 1)
        out[k.strip()] = int(v, 0)
    return out


def run(args):
    fw = open(args.bin, "rb").read()
    if not args.no_fingerprint:
        check_fingerprint(fw)
    defsyms = parse_defsyms(args.defsym)
    edits, stub_addr, tramp_addr = build_edits(fw, args, defsyms)
    print_plan(edits, stub_addr, tramp_addr)
    if args.cmd == "plan":
        print("\n(plan only -- nothing written)")
        return
    out = apply_edits(fw, edits)
    assert len(out) == len(fw), "patch changed image length"
    d = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(d, exist_ok=True)
    with open(args.out, "wb") as f:
        f.write(out)
    print(f"\nwrote {args.out}  ({len(out)} bytes, md5 {md5(out)})")
    print(f"next: python3 vesc-fw-upload.py plan {args.out}   (then flash -- read docs/05)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stub-src", default=os.path.join(os.path.dirname(__file__), "canrx_stub.s"),
                    help="stub assembly source (default: tools/canrx_stub.s)")
    ap.add_argument("--stub-bin", help="use a pre-assembled stub .bin (needs --stub-addr)")
    ap.add_argument("--stub-addr", type=lambda x: int(x, 0),
                    help="force the stub load address (else largest 0xFF region)")
    ap.add_argument("--tramp-addr", type=lambda x: int(x, 0),
                    help="force the trampoline address (else a padding hole in TBH reach)")
    ap.add_argument("--defsym", action="append", metavar="NAME=ADDR", default=[],
                    help="firmware symbol address for the stub (repeatable): "
                         "lock, unlock, signal, exit")
    ap.add_argument("--no-fingerprint", action="store_true",
                    help="DEV ONLY: skip the known-build gate (unsafe -- for testing)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("plan", "show edits, write nothing"),
                           ("build", "write the patched image")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("bin")
        if name == "build":
            p.add_argument("-o", "--out", default="build/canrx-patched.bin")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
