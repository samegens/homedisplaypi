# Make sure we don't fail silently.
$ErrorActionPreference = 'Stop'
# Fail on uninitialized variables and non-existing properties.
Set-StrictMode -Version Latest

Write-Output "Copying new homedisplay.py to HomeServerConfig..."
copy-item homedisplay.py ..\HomeServerConfig\files\homedisplay

Write-Output "Deploying HomeDisplay to homedisplaypi..."
bash -c "cd ../HomeServerConfig && ./deploy-homedisplay.sh"
