$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -ne 'true'){throw 'This installer test is restricted to a disposable GitHub runner'}
$acsRoot=Split-Path $PSScriptRoot -Parent
$acsTest=Join-Path $env:RUNNER_TEMP 'AUTOCATCHSUBS JR prueba'
$acsInstaller=Join-Path $acsRoot 'AUTOCATCHSUBS-installers/AUTOCATCHSUBSJR-Setup.exe'
$acsLog=Join-Path $acsRoot 'AUTOCATCHSUBS-build-tools/installer-ci.log'
$acsProcess=Start-Process -FilePath $acsInstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="'+$acsTest+'"'),('/LOG="'+$acsLog+'"')) -WindowStyle Hidden -Wait -PassThru
if($acsProcess.ExitCode -ne 0){throw "Installer failed, exit $($acsProcess.ExitCode)"}
$acsReport=Get-Content (Join-Path $acsTest 'installation-check.json') -Raw | ConvertFrom-Json
if(!$acsReport.passed -or $acsReport.activation_performed){throw 'Installed runtime check failed'}
$acsMenu=Join-Path $env:APPDATA 'Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Utility/AUTOCATCHSUBS JR.lua'
if(!(Test-Path -LiteralPath $acsMenu)){throw 'Resolve JR menu was not registered'}
$acsProcess=Start-Process -FilePath (Join-Path $acsTest 'unins000.exe') -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -WindowStyle Hidden -Wait -PassThru
if($acsProcess.ExitCode -ne 0 -or (Test-Path -LiteralPath $acsMenu)){throw 'JR uninstall failed'}
@{passed=$true;installed_runtime=$true;menu_registered_and_removed=$true;activation_performed=$false;resolve_timeline_tested=$false;smart_app_control_tested=$false} | ConvertTo-Json | Set-Content (Join-Path $acsRoot 'AUTOCATCHSUBS-build-tools/installer-ci-result.json') -Encoding utf8
Write-Output 'Installer and uninstall passed on a disposable runner. No license consumed.'
