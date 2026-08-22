# The BLE / VESC channel

The X-9000 is a VESC with the stock VESC BLE bridge. Talking to it needs nothing more than a
standard BLE central and the VESC packet protocol.

## The link

- Advertises as **`CYCMOTOR`** with the **Nordic UART Service (NUS)**
  `6e400001-b5a3-f393-e0a9-e50e24dcca9e`.
  - RX `6e400002` `[write, write-without-response]` — host → controller
  - TX `6e400003` `[notify]` — controller → host
- **No pairing, no bonding, no login.** Any central can transact.
- MTU 23 → 20-byte ATT chunks; larger VESC frames are split across writes and reassembled.

## VESC packet framing

```
[0x02][len:u8]        [payload][crc:u16 BE][0x03]     len <= 255
[0x03][len:u16 BE]    [payload][crc:u16 BE][0x03]     len <= 65535
[0x04][len:u24 BE]    [payload][crc:u16 BE][0x03]
```

- **CRC-16/XMODEM** (poly `0x1021`, init `0`, no reflect, no final xor) over the **payload only**.
- `payload[0]` is the **command id** (VESC `COMM_PACKET_ID`). All multi-byte integers are
  **big-endian**.

## Useful commands (read-only / safe)

| id | name | notes |
|---|---|---|
| 0 | `FW_VERSION` | handshake; returns FW `5.3`, HW string, UUID |
| 4 | `GET_VALUES` | live motor/battery values |
| 14 / 17 | `GET_MCCONF` / `GET_APPCONF` | read configuration |
| 20 | `TERMINAL_CMD` | run a terminal command (see [04-terminal-commands.md](04-terminal-commands.md)); replies arrive as `COMM_PRINT` (id 21) |
| 47 / 51 | `GET_VALUES_SETUP[_SELECTIVE]` | the values the display reads |
| 62 | `PING_CAN` | scan for VESC nodes on the CAN bus |
| 96 | `BMS_GET_VALUES` | BMS struct (all-zero on this build — no BMS-over-CAN ingestion) |

`SET_MCCONF` (13) / `SET_APPCONF` (16) writes are accepted **unauthenticated**; the config is
applied asynchronously (allow a few seconds before reading back).

## Notes specific to this build

- It is genuine VESC FW **5.3**; HW string `X-9000 V3 20260714`; `pairing_done = 0`.
- The GATT exposes **only** GAP/GATT + the NUS — there is no custom EBMX GATT service on the
  controller. (The EBMX phone app's custom characteristic lives on the *handlebar/display* module,
  a different BLE device.)
- The controller ingests **no** BMS data over CAN (`BMS_GET_VALUES` is all-zero regardless of
  `bms.type`), and the displayed state-of-charge is the controller's own voltage-based estimate —
  it does not read a BMS.

See [tools/](../tools/) for a minimal Python client that speaks all of the above.
