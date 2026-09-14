# Firmware update over Bluetooth

The X-9000 implements the **stock VESC OTA-upload flow** over its BLE channel, and it validates a
staged image with a **CRC-16 only — there is no firmware signature or model lock.** In practice
that means a user-built firmware image (e.g. a small patch of the stock image) will be accepted,
copied, and run.

This is corroborated by the **official EBMX / CYC "Firmware Update" app** itself (analysed at
`com.cyc.firmware_update` v1.0.6): it holds **no `INTERNET` permission** and bundles **no firmware
image** — it flashes whatever `.bin` the user hands it via a file picker. So the vendor's own tool
stages arbitrary, unsigned, user-supplied firmware; a custom BLE central is not even required. The
same app also performs **resident-bootloader updates** over this channel — see
[10-bootloader-over-ble.md](10-bootloader-over-ble.md).

> ⚠️ **Serious risk.** A bad or interrupted flash can brick the controller; recovery then needs an
> **ST-Link on the STM32 SWD pads** (open the enclosure). This modifies safety-relevant behavior
> and voids your warranty. Do it only on hardware you own, at your own risk, with the wheel off
> the ground and stable power.

## The upload commands (all implemented, over BLE)

| id | name |
|---|---|
| 1 | `JUMP_TO_BOOTLOADER` |
| 2 | `ERASE_NEW_APP` |
| 3 / 81 | `WRITE_NEW_APP_DATA` (+ LZO variant) |
| 29 | `REBOOT` |

The app-side handlers are stock VESC and perform **no signature check** — they erase the staging
area and write the raw bytes you send. Validation happens in the resident bootloader.

## Flash memory map (STM32F4, 1 MB)

| region | address |
|---|---|
| running application | `0x08000000` (~384 KB, ends ~`0x0805FFF8`) |
| new-app staging | high sectors above the app (see note) |
| resident bootloader | `0x080E0000` |

> **Staging base — corroborated by the vendor app.** The full map
> ([07-firmware-map-full.md](07-firmware-map-full.md) §10) reads the `WRITE_NEW_APP_DATA` target as
> `0x08060000` (erase clears `0x08080000`/`0x080A0000`/`0x080C0000`); earlier notes said `0x08080000`.
> The vendor app's bootloader-update writes carry offsets based at exactly **`0x60000` (= flash
> `0x08060000`)**, consistent with the `0x08060000` reading. For a normal **app** upload the exact
> base does **not** matter — the host sends chunks from **offset 0** and the firmware places them.
> Note the two flows use **different offset conventions**: app upload is 0-based; the bootloader
> update is `0x60000`-based (see [10-bootloader-over-ble.md](10-bootloader-over-ble.md)).

## Wire format (matches `vesc_tool`)

1. Build the image: `[u32 size][u16 crc16-xmodem(fw)]` (both **big-endian**) followed by the
   firmware bytes.
2. `ERASE_NEW_APP` — `[2][u32 image_size]`.
3. `WRITE_NEW_APP_DATA` — `[3][u32 offset][chunk]`, streaming the image from offset 0 in chunks
   (≤ ~240 data bytes keeps it in short frames).
4. `JUMP_TO_BOOTLOADER` — `[1]`. The bootloader checks the CRC-16 and, if valid, copies staging →
   application, then boots it.

**LZO variant (faster).** The firmware also implements `WRITE_NEW_APP_DATA_LZO` (id **81**),
`[81][u32 offset][u16 decompressed_len][lzo1x-block]`, decompressed by the same handler and acked
as id 3. This is what the vendor app uses ("Compressing firmware…"). It cuts bytes-on-air
substantially. `tools/vesc-fw-upload.py --lzo` streams this format (compression is host-verified per
block); the uncompressed id-3 path remains the default.

**Fail-safe:** the bootloader validates before copying, so a rejected/malformed image leaves the
running firmware intact. The controller's app-level CRC-32 self-check is disabled on this build
(`crc_flag = 0xFFFFFFFF`), so a byte-level patch does not raise a fault.

See [`tools/vesc-fw-upload.py`](../tools/vesc-fw-upload.py) for a complete, dry-run-first uploader.

## Reverting

Keep a copy of your original firmware (dump it before you change anything) and reflash it to
return to stock.
