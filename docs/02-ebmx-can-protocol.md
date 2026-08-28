# EBMX X-9000 — proprietary CAN protocol

The X-9000 is a VESC, so its CAN bus carries the standard VESC `CAN_PACKET_*` traffic. On top of
that, EBMX runs a **proprietary command + telemetry protocol** between the handlebar/display module
and the controller. This is that protocol.

- **Extended (29-bit) CAN IDs.** The controller matches on the full 29-bit ID (masked `& 0x1FFFFFFF`).
- Frames are received by the controller's CAN RX task and dispatched; the commands below set
  controller state (ride mode, assist scale). The telemetry frames flow the other way
  (handlebar → controller).

> These IDs and layouts were recovered by reverse-engineering the controller firmware and verified
> live. Data bytes are `data[0..7]`; `DLC` is the frame length.

## Commands (handlebar/display → controller)

### Ride mode — `0x5E4EA3`
Sets the Street/Race ride mode.

| byte | field |
|---|---|
| `data[6]` | mode flag: **`0` = Street, non-zero = Race** |

The controller stores this flag and the ride mode follows it (`get_mode`: flag==0 → Street(1),
else → Race(2)). This is the same effect as the physical mode button.

### Ride mode — `0x03003203` (alternate)
| byte | field |
|---|---|
| `data[0]` | `1` → one mode, `2` → the other |
| `data[1]` | `1` = also toggle an associated subsystem |

A second protocol path to the mode (the firmware honours both).

### Level / gear — `0x5E4EB0`
Selects the **gear/level** — this is what the display's up/down buttons send. It is the
gear selector, not a separate "assist" axis.

| `data[0]` | level | internal float |
|---|---|---|
| `0xFF` | **Reverse** | `-1.0` |
| `0x00` | neutral / 0 (OFF) | `15.0` (sentinel) |
| `0x01` | gear 1 | `0.4` |
| `0x02` | gear 2 | `0.7` |
| `0x03` | gear 3 | `1.0` |

`data[1]` carries associated flag bits. The level is readable over Bluetooth on
`GET_VALUES_SELECTIVE` bit 25, and — with the display removed — settable by injecting this frame;
see [08-display-less-operation.md](08-display-less-operation.md).

### Assist level — `0x07003201` and `0x03003201` (alternates)
| byte | field |
|---|---|
| `data[0] & 0x0F` | level → internal power scale (same idea as `0x5E4EB0`) |
| `data[1]` | `0x03003201` only: `0xE4` sets an associated flag |

The handlebar emits the assist level over more than one of these IDs for compatibility; the
controller decodes all of them.

> **Not on CAN:** traction-control strength and the wheel-lift (wheelie) limiter are **not**
> handlebar CAN commands — they're controller-side tuning, set via terminal/app commands
> (`tcstrength`, `vwheelie_diag`; see [04-terminal-commands.md](04-terminal-commands.md)) and
> reachable over Bluetooth without any CAN traffic.

## Accessory telemetry (handlebar/display → controller)

The accessory module ships sensor data to the controller by **repurposing VESC `STATUS(9)` frames
for virtual node IDs 1–5** — i.e. extended IDs **`0x901`–`0x905`**, refreshed ~every 110 ms,
round-robin. Each 8-byte frame packs **two 24-bit big-endian readings**:

```
valA = data[0]<<16 | data[1]<<8 | data[2]
valB = data[3]<<16 | data[4]<<8 | data[5]
```

decoded into a fixed channel map:

| frame | valA | valB | extra |
|---|---|---|---|
| `0x901` | temperature ch0 | temperature ch1 | `data[6]`, `data[7]` = two status bytes |
| `0x902` | analog ×2 | analog ×18 | |
| `0x903` | analog ×2 | analog ×2 | |
| `0x904` | temperature ch6 | temperature ch7 | |
| `0x905` | raw status word | analog ×18 | |

**Temperatures** are decoded with a standard NTC Beta equation:

```
ratio = (4.095e7 / adc - 10000) / 10000        # 10 kΩ pull-up, 12-bit ADC (full scale 4095)
T_°C  = 1 / ( ln(ratio)/B + 1/T0 ) - 273.15
        B  = 3380
        T0 = 298.15 K  (25 °C)
```

**Analog channels** are linear: `value = adc * 0.000805861 * k`, where `0.000805861 × 4095 ≈ 3.3`
(ADC→volts). `k=2` (≈0–6.6 V, likely throttle / brake / aux) and `k=18` (≈0–59 V, a pack/aux
voltage sense). The exact physical assignment (which analog is throttle vs brake, which NTC is
motor vs controller) can be confirmed on the bench by wiggling an input and watching the decoded
values.

> Standard VESC `PING_CAN` returns *empty* on this bus — the accessory modules broadcast but don't
> answer VESC command pings. The controller's own `controller_id` is `0x20` (32).
