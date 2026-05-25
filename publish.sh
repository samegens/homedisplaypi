#!/bin/bash
set -euo pipefail

echo "Copying new homedisplay.py to HomeServerConfig..."
cp homedisplay.py ../homeserverconfig/ansible/files/homedisplaypi/homedisplay/homedisplay.py

echo "Deploying HomeDisplay to homedisplaypi..."
cd ../homeserverconfig && ./deploy-homedisplay.sh
