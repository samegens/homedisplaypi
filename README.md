# HomeDisplay

Python source to display home stuff, like live usage, local time.
Requires a Raspberry Pi 2 or higher connected to the official 7" touchscreen.

## How to run locally (Linux)

Requires SDL2 dev libraries and Python dev headers to build pygame:

```bash
sudo dnf install SDL2-devel SDL2_mixer-devel SDL2_image-devel SDL2_ttf-devel python3-devel
```

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run:

```bash
.venv/bin/python homedisplay.py
```

This opens an 800×480 window. Weather data is fetched from Open-Meteo (no API key needed).
Indoor temperature and live power usage require the home network (will show blank/`?W` otherwise).

Logs are written to `/tmp/homedisplay.log`.

## How to deploy

The repo should be next to the HomeServerConfig repo.

1. In this repo, run publish.sh.
2. Go to the HomeServicerConfig repo.
3. Run ./deploy-homedisplay.sh

## Depends on

- meterkastpi for the live usage

Plans

- retrieve current solar generation and show both live generation and live actual usage
- show inside and outside temperature
- show feather forecast
- turn display off during the night (22:30-6:00)
- show alert when on hot days the temperature outside is lower than the temperature inside
