#!/bin/bash
set -euo pipefail

echo "Copying new homedisplay.py to HomeServerConfig..."
cp homedisplay.py ../HomeServerConfig/ansible/files/homedisplaypi/homedisplay/homedisplay.py

echo "Deploying HomeDisplay to homedisplaypi..."
cd ../HomeServerConfig && ./deploy-homedisplay.sh
