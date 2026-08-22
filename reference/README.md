# Firmware analysis artifacts (logic & maps — not code)

Firmware-derived **analysis** backing the write-ups in [`../docs/`](../docs/): the function
inventory, the dispatch/command maps, and the decoded protocol tables. Read alongside
[`../docs/07-firmware-map-full.md`](../docs/07-firmware-map-full.md).

**This is derived *logic and structure*, not code.** The decompiled source itself is **not**
included in this repository. What's here are addresses, function names/sizes, command→handler maps,
and protocol decodes — the kind of interoperability documentation you'd write to talk to the device.

| file | contents |
|---|---|
| `functions.csv` | inventory of 1126 recovered functions (entry address, name, size, custom-set tag) |
| `comm-handlers.md` | BLE `COMM` command id → handler address, with implemented/reject status |
| `terminal-commands.md` | custom terminal command → handler map |
| `can-ebmx-protocol.md` | decoded EBMX CAN: mode / assist / accessory telemetry |
| `comm_table.json` | the 256-entry `COMM` jump-table decode (command id → handler) |
| `callgraph.json` | call graph (caller/callee relationships) for analysis-reached functions |
| `strings.txt` | ASCII strings with their addresses |

Names like `FUN_08034e00` are auto-names at that flash address; identified functions are annotated
in the map.

## Provenance & copyright

This is firmware-derived analysis produced with Ghidra, for **interoperability and security-research
documentation**. The **decompiled code is deliberately not redistributed**; neither is any firmware
binary (see `.gitignore`). The underlying firmware remains the copyright of its authors — the VESC
firmware (© its authors, GPL) and the EBMX / "Ultrabee" application layer (© EBMX). Trademarks
belong to their owners. This project is independent and not affiliated with or endorsed by EBMX,
VESC, Greenway, or Talaria. Provided as-is, for reference.
