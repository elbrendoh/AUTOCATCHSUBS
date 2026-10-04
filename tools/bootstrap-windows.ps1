param([string]$Root=(Split-Path $PSScriptRoot -Parent))
$ErrorActionPreference='Stop'
$acsTools=Join-Path $Root 'AUTOCATCHSUBS-build-tools'
New-Item -ItemType Directory -Path $acsTools -Force | Out-Null
$acsLock=Get-Content (Join-Path $PSScriptRoot 'ci-dependencies.json') -Raw | ConvertFrom-Json
$acsProvenance=@()
foreach($acsName in 'vulkan','ffmpeg','inno','webview2','vulkanLicense') {
  $acsItem=$acsLock.$acsName
  $acsExtension=if($acsName -eq 'ffmpeg'){'.zip'}elseif($acsName -eq 'vulkanLicense'){'.txt'}else{'.exe'}
  $acsFile=Join-Path $acsTools ($acsName+$acsExtension)
  if(!(Test-Path -LiteralPath $acsFile)) {Invoke-WebRequest -Uri $acsItem.url -OutFile $acsFile}
  $acsHash=(Get-FileHash -LiteralPath $acsFile -Algorithm SHA256).Hash.ToLowerInvariant()
  if($acsItem.sha256 -and $acsHash -ne $acsItem.sha256){throw "Dependency hash mismatch: $acsName"}
  if($acsExtension -eq '.exe') {
    $acsSig=Get-AuthenticodeSignature -LiteralPath $acsFile
    if($acsSig.Status -ne 'Valid'){throw "Invalid vendor signature: $acsName"}
    if($acsItem.publisher -and $acsSig.SignerCertificate.Subject -notlike ('*'+$acsItem.publisher+'*')){throw 'Unexpected WebView2 publisher'}
  }
  $acsProvenance += @{name=$acsName;url=$acsItem.url;sha256=$acsHash}
}
$acsSdk=Join-Path $acsTools 'VulkanSDK'
if(!(Test-Path -LiteralPath (Join-Path $acsSdk 'Lib/vulkan-1.lib'))) {
  $acsProcess=Start-Process -FilePath (Join-Path $acsTools 'vulkan.exe') -ArgumentList @('--root',('"'+$acsSdk+'"'),'--accept-licenses','--default-answer','--confirm-command','install') -WindowStyle Hidden -Wait -PassThru
  if($acsProcess.ExitCode -ne 0){throw 'Vulkan SDK installation failed'}
}
$acsInno=Join-Path $acsTools 'Inno'
if(!(Test-Path -LiteralPath (Join-Path $acsInno 'ISCC.exe'))) {
  $acsProcess=Start-Process -FilePath (Join-Path $acsTools 'inno.exe') -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="'+$acsInno+'"')) -WindowStyle Hidden -Wait -PassThru
  if($acsProcess.ExitCode -ne 0){throw 'Inno Setup installation failed'}
}
$acsFF=Join-Path $acsTools 'ffmpeg'
if(!(Test-Path -LiteralPath $acsFF)){Expand-Archive -LiteralPath (Join-Path $acsTools 'ffmpeg.zip') -DestinationPath $acsFF}
$acsFFBin=@(Get-ChildItem -LiteralPath $acsFF -Recurse -Filter ffmpeg.exe -File)
if($acsFFBin.Count -ne 1){throw 'Expected exactly one FFmpeg executable'}
$acsSidecars=Join-Path $Root 'AUTOCATCHSUBS-release-source/binaries'
New-Item -ItemType Directory -Path $acsSidecars -Force | Out-Null
Copy-Item -LiteralPath $acsFFBin[0].FullName -Destination (Join-Path $acsSidecars 'ffmpeg-x86_64-pc-windows-msvc.exe') -Force
Copy-Item -LiteralPath (Join-Path $acsTools 'webview2.exe') -Destination (Join-Path $acsTools 'MicrosoftEdgeWebview2Setup.exe') -Force
$acsLoaderLicense=Join-Path $acsTools 'vulkanLicense.txt'
Copy-Item -LiteralPath $acsLoaderLicense -Destination (Join-Path $acsTools 'LICENSE-Vulkan-Loader.txt') -Force
$env:VULKAN_SDK=$acsSdk
$acsClangCandidates=@('C:/Program Files/LLVM/bin',(Join-Path $env:VSINSTALLDIR 'VC/Tools/Llvm/x64/bin'))
$acsClang=$acsClangCandidates | Where-Object {Test-Path (Join-Path $_ 'libclang.dll')} | Select-Object -First 1
if(!$acsClang){throw 'LIBCLANG_PATH could not be resolved'}
$env:LIBCLANG_PATH=$acsClang
$env:PATH=(Join-Path $acsSdk 'Bin')+';'+$env:PATH
$env:CMAKE_ARGS='-DCMAKE_POLICY_VERSION_MINIMUM=3.5'
$acsProvenance | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $acsTools 'dependency-provenance.json') -Encoding utf8
if($env:GITHUB_ENV) {
  @("VULKAN_SDK=$acsSdk","LIBCLANG_PATH=$acsClang",'CMAKE_ARGS=-DCMAKE_POLICY_VERSION_MINIMUM=3.5') | Add-Content -LiteralPath $env:GITHUB_ENV
  (Join-Path $acsSdk 'Bin') | Add-Content -LiteralPath $env:GITHUB_PATH
}
Write-Output 'Verified build dependencies prepared; no production license data used.'
