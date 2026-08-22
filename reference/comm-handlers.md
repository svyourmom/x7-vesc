# COMM (BLE/VESC) command handlers — X9KV3_260714

TBH dispatch table @ `0x0801aed4`, indexed by command id (`cmp r8,#0xff; tbh [pc,r8,lsl #1]`).
Reject/default handler (unimplemented ids) = `0x0801b54c`.

| id | name (stock VESC unless noted) | handler | status |
|---:|---|---|---|
| 0 | FW_VERSION | `0x0801bb34` | impl |
| 1 | JUMP_TO_BOOTLOADER | `0x0801bab8` | impl |
| 2 | ERASE_NEW_APP | `0x0801bade` | impl |
| 3 | WRITE_NEW_APP_DATA | `0x0801ba4e` | impl |
| 4 | GET_VALUES | `0x0801b0d4` | impl |
| 5 | SET_DUTY | `0x0801c0ac` | impl |
| 6 | SET_CURRENT | `0x0801c0d4` | impl |
| 7 | SET_CURRENT_BRAKE | `0x0801c0fc` | impl |
| 8 | SET_RPM | `0x0801c124` | impl |
| 9 | SET_POS | `0x0801c130` | impl |
| 10 | SET_HANDBRAKE | `0x0801c13c` | impl |
| 11 | SET_DETECT | `0x0801b574` | impl |
| 12 | SET_SERVO_POS | `0x0801b54c` | **UNIMPLEMENTED** |
| 13 | SET_MCCONF | `0x0801c160` | impl |
| 14 | GET_MCCONF | `0x0801b858` | impl |
| 15 | GET_MCCONF_DEFAULT | `0x0801b858` | impl |
| 16 | SET_APPCONF | `0x0801c252` | impl |
| 17 | GET_APPCONF | `0x0801b8ca` | impl |
| 18 | GET_APPCONF_DEFAULT | `0x0801b8ca` | impl |
| 19 | SAMPLE_PRINT | `0x0801c1f2` | impl |
| 20 | TERMINAL_CMD | `0x0801b59a` | impl |
| 21 | PRINT | `0x0801b54c` | **UNIMPLEMENTED** |
| 22 | ROTOR_POSITION | `0x0801b54c` | **UNIMPLEMENTED** |
| 23 | EXPERIMENT_SAMPLE | `0x0801b54c` | **UNIMPLEMENTED** |
| 24 | DETECT_MOTOR_PARAM | `0x0801b59a` | impl |
| 25 | DETECT_MOTOR_R_L | `0x0801b59a` | impl |
| 26 | DETECT_MOTOR_FLUX_LINKAGE | `0x0801b59a` | impl |
| 27 | DETECT_ENCODER | `0x0801b59a` | impl |
| 28 | DETECT_HALL_FOC | `0x0801b59a` | impl |
| 29 | REBOOT | `0x0801bfd2` | impl |
| 30 | ALIVE | `0x0801b594` | impl |
| 31 | GET_DECODED_PPM | `0x0801b54c` | **UNIMPLEMENTED** |
| 32 | GET_DECODED_ADC | `0x0801bf44` | impl |
| 33 | GET_DECODED_CHUK | `0x0801bfbc` | impl |
| 34 | FORWARD_CAN | `0x0801befe` | impl |
| 35 | SET_CHUCK_DATA | `0x0801b54c` | **UNIMPLEMENTED** |
| 36 | CUSTOM_APP_DATA | `0x0801c4da` | impl |
| 37 | NRF_START_PAIRING | `0x0801b54c` | **UNIMPLEMENTED** |
| 38 | (id 38) | `0x0801c4f0` | impl |
| 40 | (id 40) | `0x0801bf12` | impl |
| 41 | (id 41) | `0x0801c39a` | impl |
| 42 | (id 42) | `0x0801c374` | impl |
| 43 | (id 43) | `0x0801c38c` | impl |
| 44 | (id 44) | `0x0801c3ca` | impl |
| 45 | (id 45) | `0x0801c2a4` | impl |
| 46 | (id 46) | `0x0801c23e` | impl |
| 47 | GET_VALUES_SETUP | `0x0801b8ec` | impl |
| 48 | SET_MCCONF_TEMP | `0x0801b5dc` | impl |
| 49 | SET_MCCONF_TEMP_SETUP | `0x0801b5dc` | impl |
| 50 | GET_VALUES_SELECTIVE | `0x0801b0d4` | impl |
| 51 | GET_VALUES_SETUP_SELECTIVE | `0x0801b8ec` | impl |
| 52 | EXT_NRF_PRESENT | `0x0801b54c` | **UNIMPLEMENTED** |
| 53 | EXT_NRF_ESB_RX_DATA | `0x0801b54c` | **UNIMPLEMENTED** |
| 54 | EXT_NRF_ESB_SET_CH_ADDR | `0x0801b54c` | **UNIMPLEMENTED** |
| 55 | EXT_NRF_SET_ENABLED | `0x0801b54c` | **UNIMPLEMENTED** |
| 56 | DETECT_MOTOR_FLUX_LINKAGE_OPENLOOP | `0x0801b54c` | **UNIMPLEMENTED** |
| 57 | DETECT_APPLY_ALL_FOC | `0x0801b59a` | impl |
| 58 | JUMP_TO_BOOTLOADER_ALL_CAN | `0x0801b59a` | impl |
| 59 | CAN_UPDATE_BAUD_ALL | `0x0801baa0` | impl |
| 60 | SET_BATTERY_CUT | `0x0801babe` | impl |
| 61 | SET_BLE_NAME | `0x0801b7d8` | impl |
| 62 | PING_CAN | `0x0801b59a` | impl |
| 63 | SET_CURRENT_REL | `0x0801c496` | impl |
| 64 | CAN_FWD_FRAME | `0x0801c3ea` | impl |
| 65 | GET_IMU_DATA | `0x0801c404` | impl |
| 66 | BM_CONNECT | `0x0801b59a` | impl |
| 67 | BM_ERASE_FLASH_ALL | `0x0801b59a` | impl |
| 68 | BM_WRITE_FLASH | `0x0801b59a` | impl |
| 69 | BM_REBOOT | `0x0801b59a` | impl |
| 70 | BM_DISCONNECT | `0x0801b59a` | impl |
| 71 | BM_MAP_PINS_DEFAULT | `0x0801b59a` | impl |
| 72 | BM_MAP_PINS_NRF5X | `0x0801b59a` | impl |
| 73 | ERASE_BOOTLOADER | `0x0801ba78` | impl |
| 74 | ERASE_BOOTLOADER_ALL_CAN | `0x0801ba56` | impl |
| 75 | PLOT_INIT | `0x0801b54c` | **UNIMPLEMENTED** |
| 76 | PLOT_DATA | `0x0801b54c` | **UNIMPLEMENTED** |
| 77 | PLOT_ADD_GRAPH | `0x0801b54c` | **UNIMPLEMENTED** |
| 78 | PLOT_SET_GRAPH | `0x0801b54c` | **UNIMPLEMENTED** |
| 79 | GET_DECODED_BALANCE | `0x0801b54c` | **UNIMPLEMENTED** |
| 80 | BM_MEM_READ | `0x0801b59a` | impl |
| 81 | WRITE_NEW_APP_DATA_LZO | `0x0801ba4e` | impl |
| 82 | WRITE_NEW_APP_DATA_ALL_CAN_LZO | `0x0801b7d8` | impl |
| 83 | BM_WRITE_FLASH_LZO | `0x0801b59a` | impl |
| 84 | SET_CURRENT_REL | `0x0801c226` | impl |
| 85 | CAN_FWD_FRAME | `0x0801c1c8` | impl |
| 86 | (id 86) | `0x0801c2dc` | impl |
| 89 | (id 89) | `0x0801c182` | impl |
| 90 | (id 90) | `0x0801b59a` | impl |
| 91 | (id 91) | `0x0801bfda` | impl |
| 96 | BMS_GET_VALUES | `0x0801b5d0` | impl |
| 97 | (id 97) | `0x0801b5d0` | impl |
| 98 | (id 98) | `0x0801b5d0` | impl |
| 99 | (id 99) | `0x0801b5d0` | impl |
| 100 | (id 100) | `0x0801b5d0` | impl |
| 101 | (id 101) | `0x0801b5d0` | impl |
| 110 | (id 110) | `0x0801b594` | impl |
| 111 | (id 111) | `0x0801bbec` | impl |
| 112 | (id 112) | `0x0801bbac` | impl |
| 113 | BMS_FWD_CAN_RX | `0x0801b54c` | **UNIMPLEMENTED** |
| 115 | (id 115) | `0x0801c93e` | impl |
| 118 | (id 118) | `0x0801c8b0` | impl |
| 119 | (id 119) | `0x0801c930` | impl |
| 120 | (id 120) | `0x0801c5ac` | impl |
| 121 | (id 121) | `0x0801c5ca` | impl |
| 122 | (id 122) | `0x0801c628` | impl |
| 123 | (id 123) | `0x0801c7a4` | impl |
| 124 | (id 124) | `0x0801c7d0` | impl |
| 125 | (id 125) | `0x0801b59a` | impl |
| 128 | (id 128) | `0x0801c802` | impl |
| 129 | (id 129) | `0x0801c878` | impl |
| 130 | LISP_READ_CODE | `0x0801b54c` | **UNIMPLEMENTED** |
| 131 | LISP_WRITE_CODE | `0x0801b54c` | **UNIMPLEMENTED** |
| 132 | LISP_ERASE_CODE | `0x0801b54c` | **UNIMPLEMENTED** |
| 133 | LISP_SET_RUNNING | `0x0801b54c` | **UNIMPLEMENTED** |
| 134 | LISP_GET_STATS | `0x0801b54c` | **UNIMPLEMENTED** |
| 135 | LISP_PRINT | `0x0801b54c` | **UNIMPLEMENTED** |
| 136 | LISP_REPL_CMD | `0x0801b54c` | **UNIMPLEMENTED** |
| 137 | LISP_STREAM_CODE | `0x0801b54c` | **UNIMPLEMENTED** |
| 138 | FILE_LIST | `0x0801b54c` | **UNIMPLEMENTED** |
| 139 | FILE_READ | `0x0801b54c` | **UNIMPLEMENTED** |
| 140 | FILE_WRITE | `0x0801b54c` | **UNIMPLEMENTED** |
| 255 | (id 255) | `0x0801c886` | impl |

**Notable:** LISP (130-136) and BMS_FWD_CAN_RX (113) all route to the reject handler (LispBM stripped, no CAN-RX injection). FORWARD_CAN(34), CUSTOM_APP_DATA(36) implemented but limited (see firmware map). EBMX customisation is mostly *inside* stock handlers (SET_MCCONF sentinel validation, GET_VALUES_SETUP battery-field repurposing), not new COMM ids.