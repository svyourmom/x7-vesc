# Custom terminal commands

VESC exposes a terminal over `COMM_TERMINAL_CMD` (id 20); replies come back as `COMM_PRINT`
(id 21). Beyond the stock VESC commands (`ping`, `mem`, `threads`, `fault`, `volt`, `measure_*`,
`foc_*`, …), the EBMX/Ultrabee layer registers its own. Run `help` to list them; the custom ones:

| command | what it does |
|---|---|
| `tcstrength [<pct>] \| [<mode 1-2> <pct>]` | sensorless traction-control strength, per bike mode (1=Street, 2=Race). No args → prints current state incl. `mode=N`. |
| `tcerpm …` | traction-control ERPM tuning (base/gain/off/duty/rpm/current/…) |
| `tcdiag` | one-shot TC diagnostic (RPM, duty, current, rise-rate, state) |
| `tc_monitor [on\|off]` | enable/disable TC diagnostic prints |
| `jump [status\|freefall\|land\|minair\|lockout\|monitor\|reset] [value]` | jump / airtime detection |
| `hold_diag [reset \| cap A]` | hold-mode state; `cap N` sets hold phase-current cap |
| `vwheelie_diag [on\|off\|start D\|end D\|kd K\|defaults\|spid …]` | pitch-controlled wheel-lift (wheelie) limiter; `spid` tunes the speed PID |
| `UltrabeeDisplayStatus` | Ultrabee display-thread status |
| `BMI270_Start \| BMI270_Stop \| BMI270_ResetHorizon` | BMI270 IMU controls |
| user management: `register_user`, `login`, `logout`, `update_user`, `delete_user`, `delete_all_user`, `user_list`, `sizeof_user[s]`, `*_user_count`, `uuid` | a terminal credential store; `uuid` prints the STM32 UUID |

## Examples (over BLE)

```
# read traction-control state
tcstrength
#   tcstrength: mode=2  active=0%
#               Street=0%(en=0 slip=1)  Race=0%(en=0 slip=1)  ...

# set Race traction-control strength to 50%
tcstrength 2 50

# read the wheel-lift limiter state
vwheelie_diag
#   vwheelie_diag #1  running=1  enabled=0  active=0
#     params: start=20.00 end=43.00 kd=0.005  ...

# enable the wheel-lift limiter
vwheelie_diag on
```

> These are the real control surface for traction control and the wheel-lift limiter — they are
> configured here, **not** via handlebar CAN — and they all work over Bluetooth today with no
> firmware modification.

⚠️ Changing traction-control strength or enabling the wheel-lift limiter changes how the bike
behaves under power. Test with the wheel off the ground.
