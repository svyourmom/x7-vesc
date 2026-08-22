# Firmware map (X-9000 V3, VESC FW 5.3 + EBMX app layer)

High-level reverse-engineering map of the controller firmware. STM32F4 (Cortex-M4, Thumb-2),
image loaded at `0x08000000`. This documents *how it works* — no binary or decompiled source is
redistributed.

## Key RAM globals

| address | meaning |
|---|---|
| `0x2001c8c0` | ride-mode flag (`0` = Street, non-zero = Race) |
| `0x1000000c` | display ride-mode byte (CCM RAM) |
| `0x20001040` | assist / power scale (set by the assist-level CAN commands) |
| `0x2000b4c8 + 0x354` | **displayed battery/SoC value** (float, low-pass filtered) |
| `0x2000b0c0[0x0b]` | the pre-filter source for the SoC value (controller-internal ADC path) |
| `0x2000ac54..ac88` | decoded accessory-telemetry channels (temps + analog; see CAN doc) |
| `0x2000a0c0` | CAN-RX ring buffer (100 × 20 B); write-index `0x2000a0bc`, mutex `0x20008208` |
| `0x2001820c` | `bms_values` struct — never written from CAN on this build |

## Two dispatch tables

**BLE / VESC COMM** — `commands_process_packet`. A 256-entry TBH jump table at `0x0801aed4`
indexed by command id. Unimplemented ids route to a common reject handler. Notably:
- `COMM_LISP_*` (130–136) and `COMM_BMS_FWD_CAN_RX` (113) are **unimplemented** here (LispBM is
  stripped; there is no stock CAN-RX injection command).
- EBMX customisation mostly lives *inside* stock handlers, not as new command ids — e.g.
  `SET_MCCONF` sentinel-validates some fields, and `GET_VALUES_SETUP` repurposes the battery-level
  field.

**CAN RX** — the standard VESC `comm_can` decoder plus EBMX's proprietary IDs
([02-ebmx-can-protocol.md](02-ebmx-can-protocol.md)). The RX ring is fed **only** by the hardware
CAN peripheral (a worker thread blocked on `canReceive`); there is no software path that enqueues
frames — which is why arbitrary CAN injection over BLE requires a firmware change
([06-mods-mode-over-ble.md](06-mods-mode-over-ble.md)).

## Ride mode / assist mechanism

- The mode command handler writes the ride-mode flag `0x2001c8c0 = data[6]`; `get_mode` reads it.
- The physical mode button is a simple toggle of the same flag.
- The mode handler is reached **only** from the CAN dispatch — there is no BLE/COMM path to it on
  stock firmware.

## Displayed state-of-charge

- The SW102 display reads the battery field via `GET_VALUES_SETUP` (selective mask bit 7), which
  returns `*(0x2000b4c8 + 0x354)`.
- That value is a low-pass filter (α = 0.02) of a **controller-internal ADC-derived** quantity
  (`0x2000b0c0[0x0b]`). It is **not** `bms_values` and **not** the accessory telemetry.
- Consequence: the displayed SoC is the controller's own voltage-based estimate. Neither a BMS on
  CAN nor injected accessory data can move it — only a firmware change to that read path can.

## Custom subsystems (EBMX "Ultrabee" app layer)

Traction control, jump/airtime detection, hold mode, a pitch-controlled wheel-lift (wheelie)
limiter, a BMI270 IMU driver, the mode/display logic, and a terminal-based user/credential store.
Each exposes terminal commands ([04-terminal-commands.md](04-terminal-commands.md)).
