# Build and flash the custom firmware (end to end)

This is the full path from a stock controller to one running the **CAN-RX injector** patch
([06-mods-mode-over-ble.md](06-mods-mode-over-ble.md)) that lets x7 control ride mode and gear over
Bluetooth. It ties together the pieces the other docs describe:

1. **Step 0 — get the official baseline image** (download it).
2. **Step 1 — assemble the stub.**
3. **Step 2 — build the patched image** with `tools/build-canrx-fw.py`.
4. **Step 3 — check it.**
5. **Step 4 — flash it** with `tools/vesc-fw-upload.py`.

> ⚠️ **Read this first.** Flashing controller firmware can **brick** the controller; recovery then
> needs an **ST-Link on the STM32 SWD pads** (open the enclosure). This changes safety-relevant
> behavior and voids your warranty. Do it only on hardware you own, wheel off the ground, on stable
> power. Read [05-flashing-over-ble.md](05-flashing-over-ble.md) and
> [06-mods-mode-over-ble.md](06-mods-mode-over-ble.md) before you start.

> **No firmware is shared in this repo, by design.** The vendor firmware is copyrighted; this repo
> ships only tools and notes. You work on **your own** image, and both your baseline and your
> patched image stay on your machine (`*.bin` is gitignored). Never commit or share either one.

---

## Step 0 — get the official baseline image

You need a copy of the official firmware to patch. Official X-9000 / CYC images are published in the
**[CYC-EBMX-Development/firmware](https://github.com/CYC-EBMX-Development/firmware)** repository —
download the image for your controller from there. (You do not need to, and on this build cannot,
pull the running firmware off your own controller over Bluetooth: the only memory-read command
targets the BLE module, not the main STM32 flash — [07-firmware-map-full.md](07-firmware-map-full.md)
§10.)

This repo does **not** mirror those files; it points at the official source and works on the copy
you download.

> The addresses this repo documents were derived from one specific build,
> **`X9KV3_260714`** (393208 bytes, md5 `5748c5d5ecd3456da81c96afbc31c06b`). The build script
> checks your download against that fingerprint (see Step 2) and refuses anything else, so grab the
> matching build. A different build needs its addresses re-derived.

---

## Step 1 — assemble the stub

The injector stub is [`../tools/canrx_stub.s`](../tools/canrx_stub.s). It calls four existing
firmware routines — the ring-buffer **lock** and **unlock**, the dispatch-thread **signal**, and
the handler **exit**/return. Their addresses are build-specific, so you supply them when you
assemble.

Find the four addresses in your own disassembly of the baseline (they are the routines the real
CAN-RX enqueue path uses; [03-firmware-map.md](03-firmware-map.md) and
[07-firmware-map-full.md](07-firmware-map-full.md) point at the CAN-RX ring and worker thread that
call them). You need a `arm-none-eabi` toolchain:

```bash
# Debian/Ubuntu
sudo apt-get install binutils-arm-none-eabi
```

You can assemble by hand, or just let the build script do it in Step 2 (recommended — it links the
stub at the exact address it places it).

---

## Step 2 — build the patched image

`tools/build-canrx-fw.py` performs the three edits from
[06-mods-mode-over-ble.md](06-mods-mode-over-ble.md): it places the assembled stub in unused flash,
writes a 4-byte trampoline into padding, and repoints the unused **id-113** COMM handler at the
trampoline. It never touches the running code.

```bash
# dry run: shows every byte it would change, writes nothing
python3 tools/build-canrx-fw.py plan my_baseline.bin \
    --defsym lock=0x...   --defsym unlock=0x... \
    --defsym signal=0x... --defsym exit=0x...

# build the patched image
python3 tools/build-canrx-fw.py build my_baseline.bin -o build/x9kv3-canrx.bin \
    --defsym lock=0x...   --defsym unlock=0x... \
    --defsym signal=0x... --defsym exit=0x...
```

What it does for you:

- **Refuses any image that is not the known build** (size + md5). This is the main guard against
  patching with wrong addresses.
- **Places the stub** in the largest run of erased (`0xFF`) flash, or where you point it with
  `--stub-addr`. It refuses to write over anything that is not `0xFF`, so it cannot clobber code.
- **Places the trampoline** in a padding hole within reach of the jump table, or at `--tramp-addr`.
  Same no-overwrite check.
- **Rewrites the id-113 jump-table entry** to reach the trampoline, and warns if that entry is not
  currently the reject handler (a sign the build does not match).
- Prints a plan like this and, for `build`, writes the output and its md5:

  ```
  stub load address  : 0x0805eff8
  trampoline address : 0x0801b000
  id-113 TBH entry   : 0x0801afb6
    stub       @ 0x0805eff8  112B  ff... -> 17...
    trampoline @ 0x0801b000    4B  00000000 -> 43f0fabf
    tbh_entry  @ 0x0801afb6    2B  3c03 -> 9600
  total bytes changed: 118
  ```

If you assembled the stub yourself, pass it with `--stub-bin stub.bin --stub-addr 0x...` instead of
the `--defsym` set.

The build script does **not** add the upload header — `vesc-fw-upload.py` adds the
`[size][crc16]` wrapper at flash time. The output is a plain firmware image.

---

## Step 3 — check it before you flash

- Re-read the plan: only the stub region, the 4-byte trampoline, and the 2-byte jump-table entry
  change. Nothing else.
- **Disassemble the patched regions** in your own tools and confirm: the trampoline is a `b.w` to
  the stub, the stub landed in padding, and the id-113 entry now points at the trampoline. The
  addresses are build-specific, so this manual check is your real safety net.
- This build disables the app-level CRC-32 self-check (`crc_flag = 0xFFFFFFFF`,
  [05](05-flashing-over-ble.md)), so a byte patch does not trip a fault. Confirm that flag is still
  `0xFFFFFFFF` in your image.

---

## Step 4 — flash it

Use the uploader. Start with the dry run, which uses **no** Bluetooth:

```bash
python3 tools/vesc-fw-upload.py plan build/x9kv3-canrx.bin      # inspect the upload, no BLE
python3 tools/vesc-fw-upload.py preflight                       # read fw id over BLE
python3 tools/vesc-fw-upload.py flash build/x9kv3-canrx.bin --yes
```

The bootloader validates the staged image (size + CRC-16) **before** copying it over the running
app, so a rejected image leaves the current firmware intact ([05](05-flashing-over-ble.md)). The
real brick risks are power loss during the copy, or an unexpected bootloader — read
[05](05-flashing-over-ble.md) for the full risk model.

After it reboots, reconnect and confirm the firmware id, then test id-113 injection with the wheel
off the ground ([06](06-mods-mode-over-ble.md) has the packet format and verified examples).

---

## Reverting

Keep your **unpatched baseline** from Step 0. To go back to stock, flash that image the same way.
Because the patch only adds an inert handler, stock behavior is otherwise unchanged even before you
revert.

## A different build

Everything above is pinned to `X9KV3_260714`. On another firmware version the stub's four symbol
addresses, the free-flash placement, the jump-table location, and the fingerprint all differ. Redo
the disassembly, update `KNOWN_BUILD` in `tools/build-canrx-fw.py`, and re-derive the addresses
before trusting the output.
