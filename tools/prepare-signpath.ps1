$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$package=Join-Path $root 'AUTOCATCHSUBS-packages/jr'
$stage=Join-Path $root 'AUTOCATCHSUBS-build-tools/signpath-unsigned-own'
$report=Join-Path $root 'AUTOCATCHSUBS-build-tools/signpath-preparation.json'
$version=(Get-Content (Join-Path $root 'AUTOCATCHSUBS-release-source/tauri.jr.json') -Raw | ConvertFrom-Json).version
foreach($name in @('AUTOCATCHSUBS.exe','AUTOCATCHSUBSBackend.exe')){
  $file=Get-Item -LiteralPath (Join-Path $package $name)
  if($file.VersionInfo.ProductName -cne 'AUTOCATCHSUBS JR' -or $file.VersionInfo.ProductVersion -cne $version){
    throw "Project metadata must be AUTOCATCHSUBS JR / $version : $name"
  }
  if((Get-AuthenticodeSignature -LiteralPath $file.FullName).Status.ToString() -ne 'NotSigned'){
    throw "Expected newly compiled unsigned project file: $name"
  }
}
python (Join-Path $PSScriptRoot 'signing_artifact.py') prepare $package $stage --report $report
if($LASTEXITCODE -ne 0){throw 'Signing stage validation failed'}
"version=$version" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
Write-Host 'Two project executables staged; no third-party file, installer or license is submitted.'
