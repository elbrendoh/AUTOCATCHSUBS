param([ValidateSet('jr','admin')][string]$Edition='jr')
$ErrorActionPreference='Stop'
$acsRoot=Split-Path $PSScriptRoot -Parent
$acsPublic=Get-Content (Join-Path $acsRoot 'AUTOCATCHSUBS-licensing/public-config.json') -Raw | ConvertFrom-Json
$env:AUTOCATCHSUBS_LICENSE_PUBLIC_KEY=$acsPublic.public_key
$env:AUTOCATCHSUBS_LICENSE_ENDPOINT=$acsPublic.endpoint
$acsSource=Join-Path $acsRoot 'AUTOCATCHSUBS-release-source'
$env:TAURI_CONFIG=Get-Content (Join-Path $acsSource ('tauri.'+$Edition+'.json')) -Raw
$acsFeatures='windows,custom-protocol'
if($Edition -eq 'admin'){$acsFeatures+=',acs-admin'}
Push-Location $acsSource
try { cargo build --locked --release --bin autosubs --no-default-features --features $acsFeatures; if($LASTEXITCODE -ne 0){throw 'Fallo la compilacion'} } finally {Pop-Location}
