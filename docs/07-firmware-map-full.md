# EBMX X-9000 (X9KV3_260714) firmware — reverse-engineering map

Complete-as-practical map of the controller firmware, focused on the **EBMX/Ultrabee custom
code** layered on stock **VESC FW 5.3**. Produced with Ghidra 12.1.3 (PyGhidra headless) on a
Proxmox box; all analysis local, no EBMX network contact.

- Image: `reference/firmware/X9KV3_260714.bin`, 393208 B, md5 `5748c5d5ecd3456da81c96afbc31c06b`
- Load base `0x08000000`, Thumb-2 / ARM Cortex-M (STM32), unencrypted.
- HW string `X-9000 V3 20260714`, FW `5.3`, `pairing_done=0`.
- 1126 functions recovered and inventoried (`reference/functions.csv`); the 102 EBMX custom-layer
  functions were analysed to produce this map. (The decompiled *code* itself is not redistributed —
  see `reference/README.md`.)

> Naming: `FUN_xxxxxxxx` = Ghidra auto-name at that address. Where we've identified a function it
> is annotated. Stock VESC internals are labelled but not deeply re-documented (they are the
> public bldc tree); the value here is the **custom** layer.

---

## 1. Memory map — key globals

RAM: SRAM `0x2000xxxx`, CCM `0x1000xxxx`.

| addr | meaning | found via |
|---|---|---|
| `0x10000000` | CCM state struct; `+0xc` = **display ride-mode** byte; `+0x11/+0x15` also read by status printf | `set_displays_mode` |
| `0x2001c8c0` | **ride-mode flag** (`0`→Street(1), nonzero→Race(2)) | `get_mode`/mode handler |
| `0x2000b4c8` | `mc_interface` state struct; **`+0x354` = displayed battery/SoC** (float, low-pass filtered) | display trace |
| `0x2000b0c0` | `mc_interface` measured-values struct; **`[0xb]`=`0x2000b0ec`** = raw battery source | display trace |
| `0x2000ac28` | peer-STATUS decode array (CAN nodes 1-5) | CAN dispatch |
| `0x2000ac54..ac88` | 9 peer-derived sensor floats (NTC/thermistor-decoded telemetry) | CAN dispatch |
| `0x2000a0b8 / a0bc / a0c0` | CAN-RX ring: read-idx / write-idx / buffer base (100 × 20 B) | CAN worker |
| `0x2001820c` | `bms_values` (VESC BMS struct) — **not read by the display** | BMS analysis |
| `0x20006d0c` | `CUSTOM_APP_DATA` callback ptr — **never registered → no-op** | CUSTOM_APP_DATA trace |
| controller_id | **`0x20` (32)** (from appconf) | appconf read |

---

## 2. Dispatch tables (the two entry points)

### BLE / VESC COMM  — `commands_process_packet` = `FUN_0801ae70`
- TBH jump table @ **`0x0801aed4`**, indexed by command id (`cmp r8,#0xff; tbh [pc,r8,lsl #1]`).
- Reject/default handler = `0x0801b54c`. Full table: `reference/comm-handlers.md`.
- **LISP (130-136) and BMS_FWD_CAN_RX (113) all route to reject** → LispBM stripped, no CAN-RX
  injection command. `FORWARD_CAN`(34)=`FUN_0801befe`, `CUSTOM_APP_DATA`(36)=`FUN_0801c4da`.
- EBMX customisation is mostly **inside** stock handlers, not new ids:
  - `SET_MCCONF`(13): applies asynchronously; `bms.type` is **sentinel-validated** (reverts to 0
    if BMS temp limits sit at defaults t_start=45 / t_end=50|65). Writes otherwise succeed.
  - `GET_VALUES_SETUP`/`_SELECTIVE`(47/51)=`0x0801b8ec`: **battery_level (selective mask bit 7)**
    repurposed — packed from `FUN_08022cb0` ×10 (reads raw ~3376), see §5.

### CAN RX — `can_rx_dispatch` = `FUN_0801e7a0`
Standard VESC `comm_can` decoder (switch on `(ext_id>>8)` = `CAN_PACKET_*`) **plus** EBMX
extensions. Fed **only** by `FUN_0801dc70` (CAN-RX worker thread; blocks on `canReceive` from the
hardware mailbox → ring buffer). No software/BLE path writes the ring. See §4.

---

## 3. Ride mode / gear / button  (CAN-only)

| fn | role |
|---|---|
| `FUN_08037500` | mode command handler. `ext_id==0x5E4EA3` → `*0x2001c8c0 = data[6]` (set mode). `ext_id==0x5E4EB0` → strength/config (`data[0]==0xFF` marker; per-mode float sliders, `0x3f800000`=1.0) |
| `FUN_080363d2` | **button** = toggle: `*flag = (*flag==0)`; then `set_displays_mode` |
| `FUN_08023a20` | `set_displays_mode(m)` → writes CCM `0x1000000c`; echoes `"set displays_mode %i"` |
| `FUN_08034e00` | `get_mode()` → `*0x2001c8c0==0 ? 1 : 2` |
| `FUN_08023a40` | `get_desired_mode()` → reads `0x1000000c` |
| `FUN_080350b0` | display-update gate (`FUN_08037500` only refreshes display when this returns 0) |

`FUN_08037500` is called from **exactly one** site — the CAN dispatch `FUN_0801e7a0` @`0x0801f59a`.
There is **no BLE/COMM caller**. See §7.

---

## 4. CAN protocol on this bus

- **`0x5E4EA3`** (EBMX) — set ride mode; `data[6]` = mode (1=Street, 2=Race).
- **`0x5E4EB0`** (EBMX) — TC-strength / per-mode config; `data[0]==0xFF` marker.
- **VESC `STATUS(9)` frame-ids 1-5** — repurposed as **EBMX accessory telemetry channels**.
  The handlebar/accessory module(s) broadcast on ext-ids `0x901..0x905` every ~110 ms; the
  dispatch decodes them into `0x2000ac28[]` and runs NTC/thermistor math → 9 sensor floats
  (`0x2000ac54..ac88`). `can_devs` mis-labels these as absurd RPM/current.
- **VESC `CAN_PACKET_*` 5/6/7/8** (FILL_RX_BUFFER/_LONG, PROCESS_RX_BUFFER, PROCESS_SHORT_BUFFER)
  — what `FORWARD_CAN` emits (`comm_can_send_buffer`=`FUN_0801e1d0`): ext-id `(type<<8)|target_id`,
  only the low byte (node id) controllable → **cannot forge `0x5E4EA3`**.
- Live bus: `PING_CAN` returns empty (no VESC-command node answers); peers 1-5 are
  broadcast-only proprietary modules. `controller_id=0x20`.
- **Full decode of `0x5E4EB0` (assist level + flags) and the peer STATUS 1-5 channels (4 NTC
  temps + analog voltages) is in `reference/can-ebmx-protocol.md`.**

---

## 5. Display battery / SoC path  (controller-internal, not BMS, not peers)

```
SW102 <- GET_VALUES_SETUP (bit 7) <- FUN_08022cb0() = *(float*)(0x2000b4c8 + 0x354)
0x2000b4c8+0x354  <- FUN_08023e30 : field += (raw - field)*0.02   (low-pass, alpha=0.02)
raw               <- float(*(0x2000b0c0 + 0xb*4))                  (mc_interface measured value)
```
Neither `0x2000b4c8` nor `0x2000b0c0` is the peer cluster (`0x2000ac..`) or `bms_values`
(`0x2001820c`). **The displayed SoC is the controller's own filtered estimate.** Setting
`bms.type=VESC` + a BMS on CAN does **not** move it — `bms_values` never flows into
`mc_state+0x354`. Moving the number requires changing `FUN_08023e30`'s source (firmware patch).

---

## 6. Custom subsystems

| module | key fns | terminal cmds | notes |
|---|---|---|---|
| Traction control | `FUN_08038fe0` (tcerpm), `FUN_08038a30` (tcdiag), `FUN_08038d00` (tcstrength), `FUN_08039780` (init) | tcerpm/tcdiag/tcstrength/tc_monitor | sensorless TC, strength per bike mode |
| Jump / airtime | `FUN_0802fdb0` (handler), `FUN_08030790` (8 KB core), `FUN_08030170` (init) | jump | freefall/land/minair/lockout/monitor |
| Hold mode | `FUN_08032bb0` (handler), `FUN_080337b0` (init) | hold_diag | hold phase-current cap logic |
| Wheelie limiter | `FUN_08033a40` (handler+PID), `FUN_08033820`, `FUN_08034650` (init) | vwheelie_diag | pitch-controlled, IMU-driven, `spid` PID |
| IMU (BMI270) | `FUN_08035f00`, `FUN_08036230` (init) | BMI270_Start/Stop/ResetHorizon | horizon/attitude for wheelie + jump |
| Mode / display | `FUN_08023a20`,`FUN_08034e00`,`FUN_08037500`,`FUN_080364a0`,`FUN_08015a80` (main app/display thread, 8.6 KB) | UltrabeeDisplayStatus | §3, §5 |
| User / auth | `FUN_0803c6b0` (dispatch), `FUN_0803ca40` (help) | register_user/login/logout/… | terminal-string credential store; STM32 UUID = `FUN_08034980` |

Registrar = `terminal_register_command_callback` = **`FUN_080182f0`**. Full map:
`reference/terminal-commands.md`.

---

## 7. BLE reachability — what can and cannot be done over Bluetooth

The X-9000 exposes **only** the Nordic UART VESC bridge (GATT verified live: `0x1800`, `0x1801`,
NUS `6e40000x`; the app's custom characteristic `ebccabf0-…` does **not** exist here — that's a
different device, the handlebar module).

Over BLE you **can**: read all values, run terminal commands, read/write `mcconf`/`appconf`
(async, unauthenticated for general fields), set `bms.type` (satisfy the temp-limit sentinel),
`FORWARD_CAN` a VESC packet to a node id.

Over BLE you **cannot** (all verified from firmware + hardware):
- set ride mode / gear — handler is CAN-only (`0x5E4EA3`), reachable only via the hardware CAN
  mailbox; no COMM path, no self-loopback (FORWARD_CAN-to-self does not come back).
- inject any CAN-RX frame — the ring is hardware-fed only; `BMS_FWD_CAN_RX`(113) unimplemented.
- run LispBM — `COMM_LISP_*` (130-136) all unimplemented.
- use `CUSTOM_APP_DATA` for anything — its callback (`0x20006d0c`) is never registered (no-op).
- move the displayed SoC — it reads a controller-internal value (§5).

**Only true BLE-only lever:** firmware patch + BLE-bootloader reflash (`JUMP_TO_BOOTLOADER`(1) is
implemented) — e.g. repoint an unused COMM id at a handler writing `0x2001c8c0` and/or
`mc_state+0x354`. Brick risk real; VESC has bootloader recovery.

---

## 8. Open questions / future research
- **[DONE]** `0x5E4EB0` payload and peer `STATUS 1-5` channels decoded — see
  `reference/can-ebmx-protocol.md`. Remaining: bench-confirm which analog channel is
  throttle vs brake and which NTC is motor vs controller (wiggle inputs, watch `0x2000ac54..88`).
- Exact meaning of the displayed `mc_state+0x354` value (raw ~3376 = ×10) and what writes
  `0x2000b0c0[0xb]` (the pre-filter source) — trace the ADC/measurement path.
- The user-auth store (`FUN_0803c6b0`): where credentials persist, and whether `login` gates any
  write we haven't exercised.
- Jump/wheelie/hold control paths into torque — for safety, not for enabling.
- Bootloader-reflash feasibility check (design only): confirm `JUMP_TO_BOOTLOADER` + app-write
  work over this BLE link before attempting a patch.

## 9. Artifacts
See `reference/` — `README.md`, `functions.csv` (full inventory), `comm-handlers.md`,
`terminal-commands.md`, `can-ebmx-protocol.md`, `strings.txt`, `comm_table.json`, `callgraph.json`.
(The decompiled source that informed this analysis is **not** redistributed — see `reference/README.md`.)

---

## 10. Firmware upload / flash map (OTA-over-BLE feasibility)

All VESC upload COMM ids are **implemented** and reachable over the NUS channel:
`JUMP_TO_BOOTLOADER`(1)=`0x0801bab8`, `ERASE_NEW_APP`(2)=`0x0801bade`,
`WRITE_NEW_APP_DATA`(3)/`_LZO`(81)=`0x0801ba4e`, `REBOOT`(29), `ERASE_BOOTLOADER`(73)=`0x0801ba78`.

**App-side path is stock VESC with NO signature check** (decompiled):
- `ERASE_NEW_APP`→`FUN_08020bd0`: erases staging sectors, returns 9=OK. No verification.
- `WRITE_NEW_APP_DATA`→`FUN_08020ca0`: writes raw chunks (LZO-decompressed for id 81 via
  `0x0803b480`) to staging, returns 9=OK. No verification; just stores what the host sends.
- `JUMP_TO_BOOTLOADER`→`FUN_08020db0`: de-inits peripherals, then jumps to the bootloader vector
  at `0x080E0000`.

**Flash memory map (STM32F4, 1 MB):**
| region | address | notes |
|---|---|---|
| running **app** | `0x08000000` | our image (~384 KB, ends ~`0x0805FFF8`) |
| **new-app staging** | `0x08060000` | `WRITE_NEW_APP_DATA` target; erase clears `0x08080000/0A0000/0C0000` → staging spans ~`0x08060000–0x080DFFFF` |
| **bootloader** | `0x080E0000` | resident, field-updatable; **NOT in our .bin** |

**Signature question — undecided at the app level.** The app stages any bytes without checking;
whatever validation exists (CRC-only in stock VESC, or an added signature/model lock) lives in the
**bootloader at `0x080E0000`**, which is outside our image. There is no over-BLE arbitrary-flash-read
primitive to dump it (`BM_MEM_READ` targets the nRF module, not main flash), so confirming
signature-vs-CRC-only requires an **SWD dump of `0x080E0000`** (bench), or an empirical flash test.

**Risk model:** stock VESC bootloader validates the staged image (size+CRC) **before** copying
staging→app; a rejected image leaves the running app intact (recoverable, just "update didn't
take"). Real brick paths: power loss during the copy window, `ERASE_BOOTLOADER` (never send id 73),
or a modified bootloader that doesn't validate-before-copy (unknown until dumped). Recovery from a
brick = ST-Link over the STM32 SWD pads (open the controller).

**Feasibility verdict:**
- Flashing **tool** over BLE: **buildable now** (standard erase→write→jump; transport proven).
- "Compile our own firmware": only as a **binary patch** of `X9KV3_260714.bin` (we have
  decompilation, not source; a from-scratch VESC build lacks EBMX's hw config and is unsafe).
- **Safe to actually flash: blocked on the bootloader signature/validate-before-copy behavior**
  at `0x080E0000` — dump it (SWD) before trusting an unsigned patched image.
