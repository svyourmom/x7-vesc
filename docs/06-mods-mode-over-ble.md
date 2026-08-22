# Mod: control ride mode (and any CAN command) from Bluetooth

On **stock** firmware you can read everything and change configuration over BLE, but you **cannot**
set the ride mode/assist level from Bluetooth — those arrive only as CAN frames from the handlebar,
and the controller's CAN-RX ring is fed solely by the hardware CAN peripheral. This mod adds a tiny
firmware patch that turns the BLE channel into a **CAN-RX injector**, so a BLE packet becomes a
synthetic CAN frame processed by the controller's existing dispatch.

> ⚠️ This is a firmware modification. Read [05-flashing-over-ble.md](05-flashing-over-ble.md) first,
> understand the brick/SWD-recovery risk, keep the wheel off the ground, and only do this on
> hardware you own.

## Idea

`COMM_BMS_FWD_CAN_RX` (id 113) is the VESC command *meant* for exactly this ("forward a CAN frame
as if received"), but it is **unimplemented** on this build. The patch:

1. Points the id-113 jump-table entry at a small hand-written Thumb stub (placed in free flash).
2. The stub parses `[113][ext_id:u32][8 data bytes]`, builds a CAN-RX ring entry in the exact
   format the dispatch expects, and enqueues it using the same ring/mutex/semaphore the CAN worker
   thread uses.

Total change is ~120 bytes, fully reversible by reflashing the original image. It reuses the
existing, battle-tested dispatch, so it is inert unless you send id 113.

## Packet format (host → controller, over the VESC BLE channel)

```
[113] [ext_id : u32 big-endian] [can_data : 8 bytes]     (13-byte payload)
```

## Examples (once patched)

Using the CAN command reference in [02-ebmx-can-protocol.md](02-ebmx-can-protocol.md):

```
# Ride mode via 0x5E4EA3 (data[6] = mode flag)
#   Street:  71 00 5E 4E A3 00 00 00 00 00 00 00 00
#   Race:    71 00 5E 4E A3 00 00 00 00 00 00 02 00

# Ride mode via the alternate 0x03003203 (data[0] = 1 or 2)
#   71 03 00 32 03 01 00 00 00 00 00 00 00
#   71 03 00 32 03 02 00 00 00 00 00 00 00

# Assist level via 0x5E4EB0 (data[0] = level)
#   71 00 5E 4E B0 02 00 00 00 00 00 00 00
```

Verified live: both mode paths flip the reported mode (`tcstrength` shows `mode=1/2`) over
Bluetooth, motor parked. Assist and the alternate families inject the same way.

## The stub

The stub is ~30 Thumb-2 instructions that mirror the controller's own CAN-RX enqueue (lock the ring
mutex, write a 20-byte frame entry — flags/DLC, extended ID, data bytes — bump the write index,
unlock, signal the dispatch thread, return). Source: [`../tools/canrx_stub.s`](../tools/canrx_stub.s).

Building the patched image is straightforward: assemble the stub with `arm-none-eabi-as`/`ld` at
its load address, write it plus the 4-byte trampoline and the 2-byte jump-table edit into a copy of
your firmware dump, then flash with [`vesc-fw-upload.py`](../tools/vesc-fw-upload.py). Addresses are
build-specific — verify against your own dump (disassemble to confirm the trampoline lands in
inter-function padding and the jump-table math is right) before flashing.

## Why it can't (yet) put BMS SoC on the display

This injector reaches everything the CAN dispatch decodes — but the **displayed SoC is not one of
those things.** That field is the controller's own internal ADC-derived value
([03-firmware-map.md](03-firmware-map.md)); no CAN frame feeds it, and this firmware has **no
VESC-BMS CAN decoder** at all. Putting a real BMS SoC on the display needs a *different* small patch
(override the `GET_VALUES_SETUP` battery getter to read a value pushed over BLE) — documented
separately when it's built.
