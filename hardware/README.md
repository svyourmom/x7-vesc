# Hardware notes (WIP)

Teardown and hardware-level notes for the EBMX X-9000 controller. Placeholder — contributions
(board photos, connector pinouts, MCU/gate-driver part numbers, SWD pad locations) welcome.

## What's known so far

- **MCU:** STM32F4-class (Cortex-M4F), 1 MB flash. Runs VESC firmware.
- **HW string** (from `COMM_FW_VERSION`): `X-9000 V3 20260714`; VESC FW `5.3`.
- **IMU:** Bosch **BMI270** (used by the wheel-lift limiter and jump detection).
- **CAN:** the controller's `controller_id` is `0x20` (32); the handlebar/display accessory
  broadcasts telemetry + commands on the bus (see [../docs/02-ebmx-can-protocol.md](../docs/02-ebmx-can-protocol.md)).
- **BLE:** onboard module bridging to the VESC packet protocol (Nordic UART Service, advertises
  `CYCMOTOR`).
- **Recovery:** firmware recovery from a bad flash needs an ST-Link on the STM32 SWD pads — pad
  locations TBD (contributions welcome).

## To document
- Connector pinouts (phase, hall/encoder, CAN, throttle/accessory).
- SWD pad locations and how to reach them.
- Display/handlebar module internals (it hosts the EBMX phone-app BLE service).
