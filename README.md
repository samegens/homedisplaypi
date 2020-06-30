# HomeDisplay

Python source to display home stuff, like live usage, local time and door/window sensor status.
Requires a Raspberry Pi 2 or higher connected to the official 7" touchscreen.

# How to deploy

The repo should be next to the HomeServerConfig repo.

1. In this repo, run publish.ps1 in a PowerShell window.
2. Go to the HomeServicerConfig repo.
3. Start bash (WSL).
4. Run ./deploy-homedisplay.sh

# Depends on

- meterkastpi for the live usage
- Fibaro HC2 for the door/window sensor status

Plans

- retrieve current solar generation and show both live generation and live actual usage
- show battery status for each sensor
- show inside and outside temperature
- show feather forecast
- turn display off during the night (22:30-6:00)
- show current balance of ING account
- show sensor status of attic sensors
- show alert when on hot days the temperature outside is lower than the temperature inside
