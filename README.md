# HomeDisplay

Python source to display home stuff, like live usage, local time.
Requires a Raspberry Pi 2 or higher connected to the official 7" touchscreen.

## How to run locally (Linux)

Uses the `homedisplay` Miniconda environment (`~/miniconda3/envs/homedisplay`).

Run:

```bash
~/miniconda3/envs/homedisplay/bin/python homedisplay.py
```

This opens an 800×480 window. Weather data is fetched from Open-Meteo (no API key needed).
Indoor temperature and live power usage require the home network (will show blank/`?W` otherwise).

Logs are written to `/tmp/homedisplay.log`.

## How to deploy

The repo should be next to the homeserverconfig repo.

Within the homedisplay repo:

```bash
./publish.sh.
```

## Depends on

- meterkastpi for the live usage

Plans

- figure out why the text on Linux desktop does not display the same as on the Pi touchscreen
- retrieve current solar generation and show both live generation and live actual usage
- show inside and outside temperature
- show feather forecast
- turn display off during the night (22:30-6:00)
- show alert when on hot days the temperature outside is lower than the temperature inside
