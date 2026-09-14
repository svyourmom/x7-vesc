# Bootloader update & recovery over Bluetooth

The controller's **resident bootloader** (the code at `0x080E0000` that validates and copies a
staged app image — see [05-flashing-over-ble.md](05-flashing-over-ble.md)) is itself
**field-updatable over the same BLE VESC channel.** This page documents that flow, decoded from the
**official EBMX / CYC "Firmware Update" Android app** (`com.cyc.firmware_update` v1.0.6, apk sha256
`199fb28c…09ce`), and how to use it as a **bootloader-recovery** path.

> ⚠️⚠️ **This is the single most dangerous operation on the controller.** Erasing the resident
> bootloader and failing to write a complete, valid replacement removes the recovery mechanism that
> makes app-flashing fail-safe. A bad or interrupted bootloader write can leave the board only
> recoverable with an **ST-Link on the SWD pads**. Wheel off the ground, stable power, hardware you
> own. See [`tools/bl-recover.py`](../tools/bl-recover.py), which is dry-run-first and replays only a
> transcript you supply.

## Where the vendor bootloader lives

The app ships its bootloader payload as a `boot_loader.json` asset: a recorded `txd`/`rxd`
transcript of the update. Decoding it (`tools/decode-bootloader-json.py`) and LZO-decompressing the
write blocks yields a **~5.3 KB ChibiOS-based VESC bootloader** whose Cortex-M vector table reads
`SP=0x20000800`, `Reset=0x080E04F0`. That **positively confirms the resident-bootloader link
address `0x080E0000`** that §10 of [07-firmware-map-full.md](07-firmware-map-full.md) and the map in
[05](05-flashing-over-ble.md) had marked "confirm against your own dump."

We do **not** redistribute that payload (it is EBMX/VESC copyright — same policy as the firmware
image). Extract `boot_loader.json` from your own copy of the app if you need it; it is gitignored here.

## The on-wire sequence (decoded from the app)

Standard VESC framing throughout (`[start][len][payload][crc16-xmodem][0x03]`). The app sends:

| step | payload | meaning |
|---|---|---|
| 1 | `[0x49]` (id **73** `ERASE_BOOTLOADER`) | device acks `[73, 1]` |
| 2..N | `[0x51][off:u32 BE][declen:u16 BE][lzo1x]` (id **81** `WRITE_NEW_APP_DATA_LZO`) | each block **384 (0x180) bytes decompressed**; offsets start at `0x00060000`, step `0x180`; device acks `[3, 1, off:u32 BE]` |
| last | `[0x03][off:u32 BE][raw]` (id **3** `WRITE_NEW_APP_DATA`) | the tail block, sent uncompressed |

Notes:
- The write blocks are **LZO1X** (the app bundles `liblzokay_ffi.so`; the system `liblzo2` decodes
  the same stream). The `declen` field is the decompressed size; for id 3 there is no `declen`.
- The **offset base is `0x60000`**, i.e. flash `0x08060000` (the `WRITE_NEW_APP_DATA` staging/target
  base from §10) — **not** the 0-based offset used for a normal *app* upload
  ([05](05-flashing-over-ble.md) wire format). So a normal app upload and a bootloader update use
  the same COMM ids but **different offset conventions**.
- No `JUMP_TO_BOOTLOADER` / copy command appears **inside** this transcript. Whatever moves the
  staged bootloader to its resident `0x080E0000` sector happens outside the recorded bytes (a later
  app step, or a copier the erase/write handlers invoke). Treat this as an **open question** (below);
  the recovery tool sidesteps it by replaying exactly what the app sends.

## Official-app update state machine (for reference)

Reconstructed from the app's Dart symbols (`ble/tasks/…`) and UI strings:

```
connect (NUS)  →  get_device_detail (FW_VERSION)  →  verify bootloader
      →  "Compressing firmware…" (LZO)  →  "Uploading bootloader…" (73 → 81×N → 3)
      →  "Uploading firmware…"  (app image, LZO id 81)  →  reboot
```

The app has **no `INTERNET` permission** and bundles **no firmware image**: it takes the application
`.bin` from the user via a file picker (`GET_CONTENT` + `READ_EXTERNAL_STORAGE`). So the vendor tool
itself stages **arbitrary user-supplied, unsigned** firmware — consistent with the CRC-16-only
finding in [05](05-flashing-over-ble.md).

## Recovery by replay

Because the transcript is a complete, self-contained "write the stock bootloader" recording, the
safest recovery is to **replay it verbatim and verify each device ack** — exactly what
[`tools/bl-recover.py`](../tools/bl-recover.py) does:

```bash
python3 tools/bl-recover.py plan  boot_loader.json     # decode + print, NO Bluetooth
python3 tools/bl-recover.py preflight                  # read fw id over BLE
python3 tools/bl-recover.py send  boot_loader.json --yes   # DANGER: replays 73 → 81×N → 3
```

`send` aborts immediately if any device ack does not match the recorded `rxd`, and never invents
packets. It is still capable of bricking the board — only run it to recover a controller whose
bootloader is suspect, with SWD recovery available as a backstop.

## Open questions

- **What `ERASE_BOOTLOADER` (73) actually erases** — the resident sector at `0x080E0000`, a
  bootloader staging area, or both — and **what performs the staging→`0x080E0000` copy.** Needs the
  handler disassembly (`0x0801ba78` erase, `0x0801ba4e` write) or an SWD dump; the firmware image is
  not in this repo.
- **`ENCRYPTED_SIZE`** — an app-defined field in `libapp.so`. The app has no crypto library, so this
  is either a header field in the vendor's distributed `.bin` (diff a real vendor image against a raw
  VESC image to find out) or vestigial.
- **"Bootloader cannot be verified. Please contact customer support."** — the app performs a
  bootloader verification step; identify what it compares (device BL hash vs. the bundled transcript?).
