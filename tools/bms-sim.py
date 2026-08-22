#!/usr/bin/env python3
"""VESC-protocol BMS simulator -- broadcasts a fake pack at a fixed SOC.

Emits the VESC BMS CAN frames a real VESC-type BMS sends, so a VESC/Ultrabee
controller on the same bus ingests them into its bms_values (SOC, voltage, etc.).
Default: a healthy 16S pack sitting at 50 % SOC.

    ./src/bms-sim.py --print                 # dry run: show the frames, no hardware
    ./src/bms-sim.py --iface can0            # broadcast on can0 at 2 Hz forever
    ./src/bms-sim.py --iface can0 --soc 50 --id 10 --hz 2

BUS BRING-UP (needs privilege; do it once before running):
    ip link set can0 up type can bitrate 500000     # VESC default is 500k
    # First-contact measured the Greenway pack at 250k -- if the X-9000 bus is
    # 250k, use bitrate 250000. Confirm the controller's CAN_BAUD first.

THE GATE (why nothing may happen): the controller only decodes these frames if its
config bms.type == BMS_TYPE_VESC. If it's NONE (likely, since the real pack is a
Greenway, not a VESC BMS), the frames are ignored. Setting bms.type = VESC over BLE
(SET_MCCONF) is the separate step that arms this test. The controller also drops the
BMS as stale after 2.0 s, so we resend at --hz (default 2).

PROTOCOL (verified against vedderb/bldc bms.c + datatypes.h):
  ext id      = bms_id | (packet_id << 8)
  float32_auto= IEEE754 big-endian (bit-identical for normal values)
  float16     = int16 big-endian of round(value * scale)
  SOC byte    = round(soc_fraction * 255);  decoder does data[4]/255
"""
import argparse, socket, struct, sys, time

# CAN_PACKET_ID values (datatypes.h)
P_BMS_V_TOT            = 38
P_BMS_I                = 39
P_BMS_AH_WH            = 40
P_BMS_SOC_SOH_TEMP_STAT= 45
CAN_EFF_FLAG = 0x80000000

def f32a(x):            # float32_auto == IEEE754 BE
    return struct.pack(">f", x)
def f16(x, scale):      # buffer_append_float16
    return struct.pack(">h", max(-32768, min(32767, round(x * scale))))

def build_frames(soc_pct, cells, v_cell, soh_pct, t_cell, charge_allowed):
    """Return list of (packet_id, data bytes) for one full broadcast round."""
    v_tot = v_cell * cells
    soc = soc_pct / 100.0
    frames = []

    # 38 BMS_V_TOT: v_tot, v_charge  (float32_auto, float32_auto)
    frames.append((P_BMS_V_TOT, f32a(v_tot) + f32a(0.0)))

    # 39 BMS_I: i_in, i_in_ic
    frames.append((P_BMS_I, f32a(0.0) + f32a(0.0)))

    # 40 BMS_AH_WH: ah_cnt, wh_cnt
    frames.append((P_BMS_AH_WH, f32a(0.0) + f32a(0.0)))

    # 45 BMS_SOC_SOH_TEMP_STAT:
    #   [0:2] v_cell_min f16*1e3  [2:4] v_cell_max f16*1e3
    #   [4] soc*255  [5] soh*255  [6] int8 t_cell_max  [7] status bitfield
    stat = 0
    if charge_allowed:
        stat |= (1 << 2)                    # is_charge_allowed
    data = (f16(v_cell - 0.01, 1e3) + f16(v_cell + 0.01, 1e3)
            + bytes([round(soc * 255), round(soh_pct / 100.0 * 255),
                     struct.pack(">b", int(t_cell))[0], stat]))
    frames.append((P_BMS_SOC_SOH_TEMP_STAT, data))
    return frames

def can_frame(packet_id, bms_id, data):
    can_id = (bms_id | (packet_id << 8)) | CAN_EFF_FLAG
    data = data[:8]
    return struct.pack("=IB3x8s", can_id, len(data), data.ljust(8, b"\x00"))

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="can0")
    ap.add_argument("--id", type=int, default=10, help="simulated BMS CAN id (low byte)")
    ap.add_argument("--soc", type=float, default=50.0, help="state of charge %%")
    ap.add_argument("--cells", type=int, default=16)
    ap.add_argument("--vcell", type=float, default=3.80, help="per-cell voltage")
    ap.add_argument("--soh", type=float, default=100.0)
    ap.add_argument("--temp", type=float, default=25.0, help="max cell temp degC")
    ap.add_argument("--hz", type=float, default=2.0)
    ap.add_argument("--no-charge", action="store_true", help="clear is_charge_allowed")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--print", dest="dry", action="store_true",
                    help="dry run: print frames, open no socket")
    a = ap.parse_args()

    frames = build_frames(a.soc, a.cells, a.vcell, a.soh, a.temp, not a.no_charge)

    print(f"# simulated BMS: id={a.id} soc={a.soc}% soh={a.soh}% "
          f"{a.cells}S@{a.vcell}V=({a.vcell*a.cells:.1f}V) temp={a.temp}C "
          f"soc_byte={round(a.soc/100*255)}", file=sys.stderr)
    for pid, data in frames:
        eid = (a.id | (pid << 8))
        print(f"  pkt {pid:2d}  ext_id 0x{eid:08x}  data {data.hex()}", file=sys.stderr)

    if a.dry:
        return

    s = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    try:
        s.bind((a.iface,))
    except OSError as e:
        sys.exit(f"cannot bind {a.iface}: {e}\n"
                 f"bring it up first: ip link set {a.iface} up type can bitrate 500000")
    period = 1.0 / a.hz
    n = 0
    try:
        while True:
            for pid, data in frames:
                s.send(can_frame(pid, a.id, data))
            n += 1
            if n % max(1, int(a.hz)) == 0:
                print(f"\r  broadcast rounds: {n}", end="", file=sys.stderr, flush=True)
            if a.once:
                break
            time.sleep(period)
    except KeyboardInterrupt:
        pass
    finally:
        s.close()
        print(f"\n# sent {n} rounds", file=sys.stderr)

if __name__ == "__main__":
    main()
