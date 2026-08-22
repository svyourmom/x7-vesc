# EBMX proprietary CAN protocol — decoded (X9KV3_260714)

Two EBMX message families ride on the CAN bus alongside stock VESC traffic, both handled in the
CAN dispatch `FUN_0801e7a0` (RX only; the ring is hardware-fed — not injectable over BLE).

---

## A. `0x5E4EA3` — set ride mode
- `data[6]` = mode byte → `*0x2001c8c0` (0/1 = Street, 2 = Race). Handler `FUN_08037500` path A.
- See `docs/x9000-firmware-map.md` §3.

---

## B. `0x5E4EB0` — assist level + mode flags   (handler `FUN_08037500` path B)

**`data[0]` = level selector →** writes a float to the **global assist/torque scale `0x20001040`**
(read by ~17 functions across the jump / hold / wheelie / TC / mode modules — it scales control
output):

| `data[0]` | → `0x20001040` | interpretation |
|---:|---|---|
| 1 | 0.4 | 40 % assist (low) |
| 2 | 0.7 | 70 % assist (med) |
| 3 | 1.0 | 100 % assist (high) |
| 0 | 15.0 | anomalous — special/boost or different unit (verify) |
| 0xFF | −1.0 | sentinel (disabled / use-default) |

**`data[1]` = flags byte:**
- bit0 (`0x1`) → `*0x2001c8bc` = 0/1  (a mode-adjacent boolean; addr sits 4 B below the ride-mode
  flag `0x2001c8c0`; also read at `0x080355e8/08036f30/0803707c`).
- bit1 (`0x2`) → toggles a subsystem via `FUN_080302b0(0|1)` with enable-state cached at
  `0x2001d46c` (writes an enable byte + resets state via `FUN_08030280`).

So `0x5E4EB0` is the **gear/assist-level + enable-flags** command; `0x5E4EA3` is the Street/Race
mode. Both originate from the handlebar module over CAN; neither is reachable over the X-9000 BLE.

---

## C. Accessory telemetry — VESC `STATUS(9)` frame-ids 1-5 repurposed

One accessory (handlebar/display) broadcasts on ext-ids **`0x901..0x905`** (`CAN_PACKET_STATUS`
for virtual node ids 1-5) ~every 110 ms, round-robin. Each 8-byte frame packs **two 24-bit
big-endian sensor readings**: `valA = data[0]<<16 | data[1]<<8 | data[2]`,
`valB = data[3]<<16 | data[4]<<8 | data[5]`. The dispatch stores them into `0x2000ac28[]` and
decodes to floats:

| frame (node) | valA → channel | valB → channel | extra |
|---|---|---|---|
| `0x901` (1) | ch0 **TEMP** `0x2000ac58` | ch1 **TEMP** `0x2000ac54` | `data[6]`→`0x20009b28`, `data[7]`→`0x20009db0` |
| `0x902` (2) | ch2 analog×2 `0x2000ac80` | ch3 analog×18 `0x2000ac78` | |
| `0x903` (3) | ch4 analog×2 `0x2000ac84` | ch5 analog×2 `0x2000ac88` | |
| `0x904` (4) | ch6 **TEMP** `0x2000ac60` | ch7 **TEMP** `0x2000ac5c` | |
| `0x905` (5) | ch8 **raw word** `0x200081e8` | ch9 analog×18 `0x2000ac7c` | |

**Temperature channels (ch0,1,6,7)** — standard NTC Beta equation:
```
ratio = (4.095e7 / adc - 10000) / 10000          # 10 kΩ pullup, adc full-scale 4095 (12-bit)
T_C   = 1 / ( ln(ratio)/B + 1/T0 ) - 273.15       # FUN_0803e6a0 = ln
        B  = 3380  (NTC beta)
        T0 = 298.15 K (25 °C)  [1/T0 = 0.00335402]
```
**Analog channels** — linear: `value = adc * 0.000805861 * k`, where `0.000805861*4095 ≈ 3.3`
(ADC→volts). `k=2` (ch2,4,5) → ~0-6.6 V (÷2 divider: throttle / brake / aux). `k=18` (ch3,9) →
~0-59 V (÷18 divider: a pack/aux voltage sense). ch8 is an unscaled raw status word.

**Consumers:** the 9 floats are exposed via getter stubs near `0x0801f798` and read by the
display/telemetry path — **not** by any write gate and **not** by the battery-SoC field
(`mc_state+0x354`, which is controller-internal; see map §5).

> Exact physical assignment of the analog channels (which is throttle vs brake vs which temp is
> motor vs controller) is inferred from scale; confirm on the bench by wiggling inputs and
> reading `0x2000ac54..88` (e.g. via a small terminal/GET_VALUES probe) if needed.

---

## D. Injector exercise results (2026-08-21, via the cmd-113 patch)

- **`0x5E4EA3` mode:** ✅ confirmed — injected frame flips the ride mode flag (`data[6]=0`→Street,
  nonzero→Race), observed live via `tcstrength`.
- **`0x5E4EB0` assist level:** reaches the handler (same `FUN_08037500` path) and sets the internal
  assist scale `0x20001040` + flags, but the value is not surfaced in any static readback
  (`tcstrength` reports the separate TC sliders); its effect is on motor power under throttle.
- **Third mode/assist family `0x32xx`** discovered: the dispatch fallback `FUN_08036f80` handles
  ext-id `(id>>8)==0x32`: node `0x3201` selects an assist float from `data[0]&0xf` (0/1/2/3/4) and
  a flag on `data[1]==0xe4`; node `0x3203` `data[0]=1|2` drives the mode via `set_displays_mode`.
  So EBMX has **three** proprietary mode/assist CAN families: `0x5E4EA3`, `0x5E4EB0`, `0x32xx`.
- **VESC-BMS CAN (packets 38/45):** ❌ **not decoded by this firmware.** The dispatch has no case
  for BMS packet types (cases jump `0x23`→`0x2e`), the fallback only handles `0x32xx`, and nothing
  writes `bms_values` (`0x2001820c`) from CAN. Injecting a synthetic 50% SOC (packet 45, byte4=128)
  left `BMS_GET_VALUES`(96) unchanged (all zeros). EBMX omitted VESC-BMS CAN ingestion — confirms
  the controller ingests no BMS data over CAN, regardless of `bms.type`. (The injector delivered
  the frames faithfully; the firmware simply has no decoder for them.)

---

## E. Verified control commands (2026-08-22, via the cmd-113 injector)

Bench-verified which ext-id actually switches the bike (not just the internal flag):

- **Ride mode → handlebar node `0x03003203`, `data[0] = 1` (Street) / `2` (Race).** This is the
  command to use. It calls `set_displays_mode` directly, moving **both** the ride-mode flag
  (`0x2001c8c0`, read by `tcstrength`) **and** the display byte (`0x1000000c`). Confirmed live: it
  prints `set displays_mode 0/1` and flips `tcstrength mode=`.
  - ⚠️ **`0x5E4EA3` is flag-only.** It sets `0x2001c8c0` (so `tcstrength` changes) but its
    `set_displays_mode` call is behind a gate (`FUN_080350b0`) that stays shut over injection, so
    the **displayed/reported** mode does not change. Use `0x03003203` for a real mode switch.
  - The un-prefixed `0x00003203` does **not** reach the handler over injection — the `0x03______`
    priority prefix is required.
- **Assist level → handlebar node `0x03003201`, `data[0] = level`, `data[1] = 0xE4`.** Writes the
  assist/torque scale `0x20001040`. Firmware float table (from `FUN_08036f80`): level `1`→**0.40**,
  `2`→**0.70**, `3`→**1.00** (0=15.0 anomalous, 4=−1.0 sentinel). i.e. the levels are **40/70/100 %
  power caps**; 100 % is the resting default, so only the lower levels are noticeably different.
- **Reverse → native VESC `SET_DUTY` (COMM id 5), small negative duty** (e.g. −5 % = slow creep).
  There is no dedicated reverse command in the firmware; `SET_DUTY`/`SET_CURRENT` (real
  `mc_interface_set_*` handlers) drive the motor directly and are not overridden at rest.
  **`SET_RPM` (COMM id 8) is repurposed** on this build — its handler (`0x0801c124`→`0x08021d40`)
  doesn't set speed; it float-range-checks and calls the mode/display broadcast (`0x0801ab80`), so
  sending it does nothing to the motor and perturbs the ride mode. See `comm-handlers.md`.
