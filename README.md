# EBMX X-9000 Controller — BLE / CAN / Firmware Reference

Reverse-engineering notes and interoperability reference for the **EBMX X-9000** motor
controller (as used on modified Talaria / Sur-Ron-class ebikes). Companion to the
[Talaria Greenway BMS Protocol Reference](https://github.com/svyourmom/Talaria-Greenway-BMS-Protocol-Reference)
— part of an open collection of ebike how-tos, teardowns, and mods.

Everything here was produced from a controller the author owns, over its own Bluetooth
interface and from a dump of its own firmware. The goal is **documentation and interoperability**
(talk to the hardware you own), in the spirit of right-to-repair.

## TL;DR — what the X-9000 exposes

- The controller is a real **VESC (FW 5.3)** with an EBMX/"Ultrabee" custom application layer.
- It advertises as **`CYCMOTOR`** over the **Nordic UART Service** and speaks the standard **VESC
  packet protocol** — **unpaired and unauthenticated**. Any BLE central can read values, run
  terminal commands, and read/write configuration.
- The bike's controls (**ride mode**, **gear/level**) come from the **SW102T display** as
  **EBMX-proprietary CAN frames** — documented here. Gear + mode are **readable over BLE**
  (`GET_VALUES_SELECTIVE`), and with the display removed the bike can be **driven entirely from
  Bluetooth** ([docs/08](docs/08-display-less-operation.md)).
- Firmware update over BLE is the **stock VESC OTA flow** with a **CRC-16 check only (no
  signature)**, so the controller will accept and run a user-built firmware image.

## Contents

| doc | what's in it |
|---|---|
| [docs/01-ble-vesc-channel.md](docs/01-ble-vesc-channel.md) | the BLE link, GATT, VESC packet framing, how to talk to it |
| [docs/02-ebmx-can-protocol.md](docs/02-ebmx-can-protocol.md) | **the protocol reference** — EBMX CAN commands (mode, assist) + accessory telemetry |
| [docs/03-firmware-map.md](docs/03-firmware-map.md) | firmware memory map, dispatch tables, custom subsystems |
| [docs/04-terminal-commands.md](docs/04-terminal-commands.md) | the custom terminal command set (traction control, wheelie, IMU, user auth…) |
| [docs/05-flashing-over-ble.md](docs/05-flashing-over-ble.md) | the OTA flash flow, flash map, and the "no signature" finding |
| [docs/06-mods-mode-over-ble.md](docs/06-mods-mode-over-ble.md) | how-to: control ride mode from Bluetooth (a small firmware patch) |
| [docs/07-firmware-map-full.md](docs/07-firmware-map-full.md) | **the full firmware map** — memory globals, dispatch tables, subsystems, addresses |
| [docs/08-display-less-operation.md](docs/08-display-less-operation.md) | **how-to: drive from Bluetooth with the display removed** — read/set gear + mode, current-limit scale, app-as-cockpit |
| [reference/](reference/) | firmware analysis: function inventory + command/dispatch maps + protocol decodes (logic, not code) |
| [tools/](tools/) | Python tools: BLE VESC client, firmware uploader |
| [hardware/](hardware/) | teardown / hardware notes (WIP) |

## Safety & legal

- This documents a **VESC-based** controller. VESC firmware is open source (GPL); the EBMX
  application layer on top is EBMX's. **No firmware binary or wholesale decompiled source is
  redistributed here** — only behavioral/protocol documentation and original tools.
- Modifying controller firmware or injecting motor-relevant commands can be **dangerous** and can
  **brick** the controller (recovery needs SWD/ST-Link). Everything here is provided **as-is, at
  your own risk**, and voids your warranty. Keep the motor parked and the wheel off the ground when
  experimenting.
- Interact only with hardware you own.

## Status

Actively worked on. Verified on an X-9000 V3 (HW string `X-9000 V3 20260714`, VESC FW 5.3).
Contributions / corrections welcome.
