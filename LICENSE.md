# License & attribution

## Documentation
The prose, tables, and protocol descriptions in this repository are released under
**CC BY 4.0** — use, adapt, and share with attribution.

## Tools
The Python tools and the assembly stub under `tools/` are original work, released under the
**MIT License**.

## Not included / not covered
- **No firmware binary** and **no decompiled source code** of the controller are distributed here
  (see `.gitignore`).
- `reference/` and the firmware map contain firmware-derived **analysis** (addresses, function
  inventory, command/dispatch maps, decoded protocol) — interoperability documentation, not code.
  The underlying firmware facts belong to their original authors and are documented here, not
  relicensed: VESC firmware (© its authors, GPL) and the EBMX / "Ultrabee" application layer
  (© EBMX). See `reference/README.md`.
- Trademarks belong to their owners. This project is independent and not affiliated with or endorsed
  by EBMX, VESC, Greenway, or Talaria.

## Disclaimer
Everything here is provided **as-is, without warranty**. Interacting with or modifying a motor
controller can be dangerous and can destroy hardware. You are solely responsible for what you do
with this information. Only work on hardware you own.
