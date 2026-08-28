# Display-less operation: driving the X-9000 from Bluetooth alone

On this bike the **only** gear/mode control is the SW102T display module — there is no separate
handlebar dial. Its up/down buttons pick the level (Reverse / 0 / gear 1–3) and a long-press of
DOWN toggles Street/Race. The display is not a dumb screen: it keeps the level counter itself and
broadcasts the resulting **absolute level** to the controller as a CAN frame.

This document shows that the controller does not *require* the display — you can remove it and drive
the bike entirely over Bluetooth, using the CAN-RX injector from
[06-mods-mode-over-ble.md](06-mods-mode-over-ble.md).

**This is a combined hardware + software mod:**
1. **Software** — the CAN-RX injector firmware patch ([06](06-mods-mode-over-ble.md)), so a BLE
   packet becomes a synthetic CAN frame the controller processes.
2. **Hardware** — physically disconnect the SW102T display from the handlebar bus, so nothing
   competes with your injected level frames (see "why it fights you" below).

**The display can be reconnected as a backup.** The two states are cleanly exclusive:
- **Display disconnected** → the app is the sole level source; it fully controls gear + mode.
- **Display reconnected** → the display wins the level race again (it re-broadcasts every ~20–35 ms),
  so it retakes gear + mode and the app falls back to *reading* level/mode (still settable: mode
  injection sticks; level injection is transient). Nothing needs re-flashing to switch — the
  injector firmware is inert unless you send it frames, so a reconnected display just works.

So the practical rig is: injector firmware flashed permanently, display on a connector you can pull.
Pulled = app cockpit; plugged = stock handlebar control as a hardwired fallback if Bluetooth fails.

> ⚠️ Firmware-mod territory and a **moving vehicle**. Read [05](05-flashing-over-ble.md) and
> [06](06-mods-mode-over-ble.md) first. Keep the wheel off the ground for every test here. Own the
> hardware you do this to.

## What the level frame is

The level is carried by an EBMX CAN frame the display sends:

```
ext id 0x5E4EB0,  data[0] = level
    0xFF -> Reverse
    0x00 -> neutral / 0   (OFF — see "level 0 does not drive")
    0x01 -> gear 1
    0x02 -> gear 2
    0x03 -> gear 3
```

The controller maps `data[0]` to an internal "level float", and everything downstream (drive
enable, current envelope) reads that float. Mode is the separate `0x03003203 data[0] = 1/2` frame
from [06](06-mods-mode-over-ble.md).

## Reading level and mode over Bluetooth (no patch)

Both are exposed in the **`GET_VALUES_SELECTIVE`** reply (COMM id 50). The controller widened the
stock VESC field set with two custom fields:

| selective mask bit | field | values |
|---|---|---|
| **25** | level / gear | `-1`=Reverse, `0`=neutral, `3`=gear 1, `6`=gear 2, `9`=gear 3 |
| **24** | ride mode | `0`=Street, `1`=Race |

```
# request just those two fields (mask = (1<<24)|(1<<25) = 0x03000000)
#   payload: [50][03 00 00 00]
#   reply:   [50][03 00 00 00][mode:u8][level:s8]
```

So a phone can always *read* the current gear and mode, display present or not.

## Setting the level: why it fights you with the display attached

With the display connected, injecting `0x5E4EB0 data[0]=N` does change the level — but the display
re-broadcasts the true button state every ~20–35 ms, so your value is overwritten within a few
hundred milliseconds. You win the write and then immediately lose it. (The controller also has its
own button-cycle path — COMM id 9 — but it is held disabled whenever a display is sending its
frames.) Net: **with the display present, the level is effectively read-only over BLE.**

## Removing the display makes the injector authoritative

Disconnect the display and the picture inverts — nothing else sends level frames, so **your
injected frame is the only source and it holds indefinitely.** Observed on an X-9000 V3, display
physically disconnected, key on:

- **No fault.** `fault` = `FAULT_CODE_NONE`; nothing registered since startup. The controller does
  not require a display to run.
- **Boot level is 0** (nothing feeding it), and **level 0 does not drive** — throttle input is seen
  by the controller (`hold_diag` shows `thr` rising) but the motor stays at zero. Level ≥ 1 drives.
- **Inject once, it sticks.** `0x5E4EB0 data[0]=3` → the level reads `gear 3` and stays with no
  decay. Reverse (`0xFF`) and back to `3` are instant and equally sticky.
- **The bike drives** at the injected level, throttle behaving exactly as it would at that gear.
- The injected `0x5E4Exx` frame also starts the controller's SW102T display thread, so the firmware
  is in the same state a real display would produce — you are simply sourcing its frames.

That is the whole result: **remove the display, inject `0x5E4EB0` for the level and `0x03003203`
for the mode, and the bike is fully controlled from Bluetooth.**

## Current limit is independent of the level

The level only selects the **max motor current** the controller will allow (gear 1/2/3 →
300/350/450 A on this bike). Effective current is

```
effective_max = l_current_max  ×  l_current_max_scale
```

The level sets `l_current_max`; `l_current_max_scale` is a **separate** limits field that the
display never touches. You can set it over BLE with `SET_MCCONF_TEMP` (COMM id 48/0x30, `store=0`
so it is RAM-only and a power cycle restores it), and thereby hold any effective current *below*
the level's envelope, regardless of which gear is selected. Read the level back on selective bit 25,
compute `scale = desired_A / envelope_A`, and re-apply whenever the level changes.

`SET_MCCONF_TEMP` payload (VESC-standard, `float32_auto` values, minimum 8 floats — send the full
set, echoing the others from a live `GET_MCCONF`, or the handler reads past the packet):

```
[0x30][store][forward_can][ack][divide_by_controllers]
  l_current_min_scale, l_current_max_scale,
  l_min_erpm, l_max_erpm, l_min_duty, l_max_duty, l_watt_min, l_watt_max
  [optional: l_in_current_min, l_in_current_max]
```

Keep `store = 0`. Clamp the scale to `(0, 1]` so this can only *reduce* current, never raise it
above the controller's own setting.

## Fallback when Bluetooth is not present

The injected level lives in RAM, so if the phone disconnects the last level holds — but a power
cycle boots back to level 0 (OFF) with no way up. If you want the bike drivable without a phone,
put a small always-on CAN node where the display was, broadcasting `0x5E4EB0 data[0]=3` on a timer.
That boots the bike to a known gear over the wire; the app then injects to override the level and
mode when it is connected. Hardware sets a safe default, software takes over on demand.

The **simplest** fallback needs no new hardware at all: leave the SW102T display on a connector and
plug it back in. A reconnected display re-takes gear + mode over the wire, so a dead phone or
BLE stack still leaves you a fully functional bike. The trade-off vs. a dedicated CAN node is that
the display re-imposes its own boot level (0/OFF) and button behaviour; the CAN node lets you pick
the boot gear.

## Safety notes specific to this

- **Reverse is one DOWN press below neutral**, and neutral is the boot state — worth remembering
  when the display is present. With the app as the sole source you choose the level explicitly.
- Level 0 not driving is a useful safe default: a bare, un-commanded controller will not move.
- Everything here changes real ride state on a real vehicle. Bench it wheel-up first, every time.
