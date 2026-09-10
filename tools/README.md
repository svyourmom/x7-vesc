# Tools

Minimal Python tools for talking to an X-9000 over its BLE VESC channel. They use
[`bleak`](https://github.com/hbldh/bleak) (`pip install bleak`).

> The scripts target a device by BLE address (`ADDR` near the top of each file — set it to your
> controller's address, or adapt to scan by the `CYCMOTOR` name). They are **read-only / safe by
> default**; anything that changes state is an explicit, deliberate call.

| tool | what it does |
|---|---|
| `vesc-ble.py` | VESC-over-BLE client: `fw`, `values`, `setup`, `sel`, `term "<cmd>"`, `listen`, `raw <hex>`. Motor-command ids are refused unless `--force`. |
| `vesc-fw-upload.py` | Firmware uploader (see [../docs/05-flashing-over-ble.md](../docs/05-flashing-over-ble.md)). `plan` (dry run, no BLE) → `preflight` (read fw) → `flash <bin> --yes`. |
| `ota-extract.py` | Rebuild your own baseline image from a captured official OTA update (btsnoop log). Needed because flash can't be read over BLE — see [../docs/09-build-custom-firmware.md](../docs/09-build-custom-firmware.md) Step 0. |
| `build-canrx-fw.py` | Build the CAN-RX injector patched image from your baseline (see [../docs/09-build-custom-firmware.md](../docs/09-build-custom-firmware.md)). `plan` (dry run) → `build`. Refuses any image that isn't the known build. |
| `canrx_stub.s` | ARM Thumb-2 source for the CAN-RX injector stub (see [../docs/06-mods-mode-over-ble.md](../docs/06-mods-mode-over-ble.md)). `build-canrx-fw.py` assembles it for you, or assemble with `arm-none-eabi-as`/`ld`. |
| `bms-sim.py` | Reference VESC-BMS CAN frame builder (SocketCAN). Note: **this X-9000 build does not decode BMS-over-CAN**, but the encoder is useful with other VESC hardware / for reference. |

## Examples

```bash
pip install bleak

python3 vesc-ble.py fw                       # handshake / firmware version
python3 vesc-ble.py term "tcstrength"        # run a terminal command
python3 vesc-ble.py setup                    # the values the display reads
python3 vesc-ble.py raw "60"                 # arbitrary payload (id 96 = BMS_GET_VALUES)

python3 vesc-fw-upload.py plan  my_dump.bin  # inspect the upload plan, NO Bluetooth
python3 vesc-fw-upload.py preflight          # read fw id over BLE

# build the injector patch from your own baseline (no BLE) -- see docs/09
python3 ota-extract.py btsnoop_hci.log -o my_baseline.bin      # rebuild baseline from a capture
python3 build-canrx-fw.py plan my_baseline.bin \
    --defsym lock=0x... --defsym unlock=0x... --defsym signal=0x... --defsym exit=0x...
```

⚠️ `vesc-fw-upload.py flash` writes controller firmware. Read the flashing doc and understand the
brick/SWD-recovery risk first. `ota-extract.py` and `build-canrx-fw.py` produce firmware images
(derivatives of the vendor firmware): they are gitignored — keep them private, never commit them.
