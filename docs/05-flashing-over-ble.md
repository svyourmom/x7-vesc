# Firmware update over Bluetooth

The X-9000 implements the **stock VESC OTA-upload flow** over its BLE channel, and it validates a
staged image with a **CRC-16 only — there is no firmware signature or model lock.** In practice
that means a user-built firmware image (e.g. a small patch of the stock image) will be accepted,
copied, and run.

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
| running application | `0x08000000` (~384 KB) |
| new-app staging | `0x08080000` (sectors 8–10) |
| resident bootloader | `0x080E0000` |

## Wire format (matches `vesc_tool`)

1. Build the image: `[u32 size][u16 crc16-xmodem(fw)]` (both **big-endian**) followed by the
   firmware bytes.
2. `ERASE_NEW_APP` — `[2][u32 image_size]`.
3. `WRITE_NEW_APP_DATA` — `[3][u32 offset][chunk]`, streaming the image from offset 0 in chunks
   (≤ ~240 data bytes keeps it in short frames).
4. `JUMP_TO_BOOTLOADER` — `[1]`. The bootloader checks the CRC-16 and, if valid, copies staging →
   application, then boots it.

**Fail-safe:** the bootloader validates before copying, so a rejected/malformed image leaves the
running firmware intact. The controller's app-level CRC-32 self-check is disabled on this build
(`crc_flag = 0xFFFFFFFF`), so a byte-level patch does not raise a fault.

See [`tools/vesc-fw-upload.py`](../tools/vesc-fw-upload.py) for a complete, dry-run-first uploader.

## Reverting

Keep a copy of your original firmware (dump it before you change anything) and reflash it to
return to stock.
