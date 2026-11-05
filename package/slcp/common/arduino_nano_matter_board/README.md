# arduino_nano_matter_board

Local SLC extension for **Arduino Nano Matter** (`brd2707a`). Passed to SLC via
`--sdk-package-path` by `generate_gsdk.py` whenever `board_opn` is `brd2707a`.

## Why

BRD2707A is not part of Simplicity SDK. Previously the board/config `.slcc` files
were copied into the SDK tree via `additional_files`. Direct `slc generate`
(`-cpsdk`) never applies that copy, so `--with brd2707a` fails.

This extension exposes the same components without modifying the SDK install.

## Config headers

`brd2707a_config` reuses `brd4318a_brd4001a` / `brd4318a_brd4002a` headers from
the SiSDK (`boards/hardware/board/config/…`). `generate_gsdk.py` copies those
directories under `hardware/board/config/` in this extension before generate
(matching `root_path` in `brd2707a_config.slcc`). Do not commit the copies.

Nano Matter generates also pass `--with brd2707a,brd4002a` so the
`hardware_board_mainboard` requirement is satisfied and the brd4002a-conditioned
overrides apply.
