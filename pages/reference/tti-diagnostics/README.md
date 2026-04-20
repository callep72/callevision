# TTI Diagnostics

These pages are hardware/reference fixtures for validating the
`runtime/pages -> vbit2 -> raspi-teletext -> TV` pipeline.

They live outside `pages/examples/` on purpose:

- `pages/examples/` contains example content for the bridge/templates flow.
- `pages/reference/tti-diagnostics/` contains low-level TTI test fixtures for
  direct copy/testing on the Raspberry Pi.

Page map:

- `P701` baseline ASCII only
- `P702` double-height title
- `P703` foreground colours
- `P704` background colours
- `P705` mosaic/graphics blocks
- `P706` mixed attribute changes
- `P707` carousel with 2 subpages
- `P708` FastText/`FL` links
- `P709` width and alignment ruler
- `P710` combined smoke test

Regenerate with:

```bash
python3 scripts/generate_tti_diagnostics.py
```
