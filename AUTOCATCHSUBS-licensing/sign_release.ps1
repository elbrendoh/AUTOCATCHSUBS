param(
  [ValidateSet('jr','admin')][string]$Edition='jr',
  [switch]$AuditOnly,
  [string]$CertificateThumbprint,
  [string]$SignTool='C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe',
  [string]$TimestampUrl='http://time.certum.pl',
  [switch]$SignInstaller
)
$ErrorActionPreference='Stop'
$acsBase=Split-Path $PSScriptRoot -Parent
$acsPackage=Join-Path $acsBase ('AUTOCATCHSUBS-packages\'+$Edition)
$acsInstallerName=if($Edition -eq 'jr'){'AUTOCATCHSUBSJR-Setup.exe'}else{'AUTOCATCHSUBS-Admin-Setup.exe'}
$acsFiles=if($SignInstaller){@(Get-Item -LiteralPath (Join-Path $acsBase ('AUTOCATCHSUBS-installers\'+$acsInstallerName)))}else{@(Get-ChildItem -LiteralPath $acsPackage -Recurse -File | Where-Object {$_.Extension -in '.exe','.dll','.pyd'})}
if(-not $AuditOnly){
  if($CertificateThumbprint -notmatch '^[0-9A-Fa-f]{40}$'){throw 'Indica el thumbprint publico del certificado Code Signing RSA emitido por una CA reconocida. No uses una clave de activacion.'}
  $acsCert=Get-Item -LiteralPath ('Cert:\CurrentUser\My\'+$CertificateThumbprint)
  if(-not $acsCert.HasPrivateKey){throw 'La clave no esta disponible mediante SimplySign/token. Inicia su aplicacion oficial.'}
  if($acsCert.PublicKey.Oid.Value -ne '1.2.840.113549.1.1.1'){throw 'Smart App Control requiere una firma RSA; no se usara ECC.'}
  if($acsCert.NotAfter -lt (Get-Date) -or $acsCert.NotBefore -gt (Get-Date)){throw 'Certificado fuera de su periodo de validez'}
  if(-not ($acsCert.EnhancedKeyUsageList | Where-Object {$_.ObjectId -eq '1.3.6.1.5.5.7.3.3'})){throw 'El certificado no autoriza firma de codigo'}
  if($acsCert.Subject -eq $acsCert.Issuer){throw 'No se aceptan certificados autofirmados para esta distribucion'}
  if(-not (Test-Path -LiteralPath $SignTool)){throw 'Falta SignTool del SDK de Windows'}
}
$acsRows=foreach($acsFile in $acsFiles){
  $acsSignature=Get-AuthenticodeSignature -LiteralPath $acsFile.FullName
  if(-not $AuditOnly -and $acsSignature.Status -ne 'Valid'){
    if($acsSignature.Status -ne 'NotSigned'){throw ('Firma invalida existente: '+$acsFile.FullName+'. Investiga antes de sustituirla.')}
    & $SignTool sign /sha1 $CertificateThumbprint /s My /fd SHA256 /tr $TimestampUrl /td SHA256 $acsFile.FullName
    if($LASTEXITCODE -ne 0){throw ('Firma fallida: '+$acsFile.FullName)}
    & $SignTool verify /pa $acsFile.FullName
    if($LASTEXITCODE -ne 0){throw ('Windows no valida la firma: '+$acsFile.FullName)}
    $acsSignature=Get-AuthenticodeSignature -LiteralPath $acsFile.FullName
  }
  [PSCustomObject]@{file=$acsFile.FullName;status=$acsSignature.Status.ToString()}
}
$acsReport=[PSCustomObject]@{edition=$Edition;audit_only=[bool]$AuditOnly;all_signatures_valid=@($acsRows | Where-Object status -ne Valid).Count -eq 0;files=$acsRows}
$acsReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ('tests\signing-'+$Edition+'-'+$(if($SignInstaller){'installer'}else{'package'})+'.json')) -Encoding utf8
if(-not $AuditOnly -and -not $acsReport.all_signatures_valid){throw 'Hay archivos que Windows no valida'}
if(-not $AuditOnly -and -not $SignInstaller){
  # Regenerate file hashes AFTER signing and BEFORE compiling the installer.
  $acsManifestFile=Join-Path $acsPackage 'manifest.json'
  $acsManifest=Get-Content -LiteralPath $acsManifestFile -Raw | ConvertFrom-Json
  foreach($acsProperty in $acsManifest.files.PSObject.Properties){
    $acsProperty.Value=(Get-FileHash -LiteralPath (Join-Path $acsPackage $acsProperty.Name) -Algorithm SHA256).Hash.ToLower()
  }
  [IO.File]::WriteAllText($acsManifestFile,($acsManifest | ConvertTo-Json -Depth 5),(New-Object Text.UTF8Encoding($false)))
}
$acsReport | Select-Object edition,audit_only,all_signatures_valid
