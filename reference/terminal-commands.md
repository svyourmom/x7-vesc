# EBMX/Ultrabee custom terminal commands → handler map

Registered via `terminal_register_command_callback` = **`FUN_080182f0`** (name, help, args, callback).
Reachable over BLE through `COMM_TERMINAL_CMD` (id 20). Stock VESC terminal commands
(`ping`, `mem`, `threads`, `fault`, `volt`, `measure_*`, `foc_*`, …) are omitted here.

| command | handler | module (registrar) | notes |
|---|---|---|---|
| `tcerpm` | `FUN_08038fe0` | TC init `FUN_08039780` | sensorless traction-control ERPM tuning |
| `tcdiag` | `FUN_08038a30` | TC init | one-shot TC diagnostic |
| `tcstrength` | `FUN_08038d00` | TC init | TC strength slider **per bike mode** (1=Street,2=Race); prints live `mode=N` |
| `tc_monitor` | `LAB_080396d0` | TC init | enable/disable TC diagnostic prints |
| `jump` | `FUN_0802fdb0` | `FUN_08030170` | jump/airtime detection (freefall/land/minair/lockout/monitor/reset) |
| `hold_diag` | `FUN_08032bb0` | `FUN_080337b0` | hold-mode state/inputs/timers; `cap N` sets hold phase-current cap |
| `vwheelie_diag` | `FUN_08033a40` | `FUN_08034650` | pitch-controlled wheelie limiter (IMU); spid PID tuning |
| `UltrabeeDisplayStatus` | `LAB_080369a0` | `FUN_080364a0` | "Ultrabee Display Thread" status |
| `BMI270_Start` | `LAB_08035ef0` | `FUN_08036230` | start BMI270 IMU print |
| `BMI270_Stop` | `LAB_08035ee0` | `FUN_08036230` | stop BMI270 IMU print |
| `BMI270_ResetHorizon` | `LAB_080369a0` | `FUN_08036230` | reset IMU horizon |
| `life_test` | `LAB_08035e90` | `FUN_08036230` | test stub (prints number) |
| `io_test` | `LAB_08035ea0` | `FUN_08036230` | test stub |
| `encoder-test` | `LAB_08035eb0` | `FUN_08036230` | test stub |
| user mgmt (`register_user`,`login`,`logout`,`update_user`,`delete_user`,`delete_all_user`,`user_list`,`sizeof_user[s]`,`*_user_count`,`uuid`) | `FUN_0803c6b0` (dispatch) | `FUN_0803ca40` (help) | terminal-string user/credential store; reads STM32 UUID via `FUN_08034980` |

**"set displays_mode %i"** is only a printf echo inside `set_displays_mode` (`FUN_08023a20`); it is
NOT a terminal command.
