# Make sure we don't fail silently.
$ErrorActionPreference = 'Stop'
# Fail on uninitialized variables and non-existing properties.
Set-StrictMode -Version Latest

copy-item homedisplay.py ..\HomeServerConfig\files\homedisplay

Write-Output "Next steps:"
Write-Output "1: start bash in the HomeServiceConfig directory"
Write-Output "2: ./deploy-homedisplay.sh"
