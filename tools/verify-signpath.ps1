param(
  [Parameter(Mandatory=$true)][string]$Original,
  [Parameter(Mandatory=$true)][string]$Returned,
  [Parameter(Mandatory=$true)][string]$Report,
  [Parameter(Mandatory=$true)][string]$Version
)
$ErrorActionPreference='Stop'
if($env:SIGNPATH_CERTIFICATE_THUMBPRINT -notmatch '^[A-Fa-f0-9]{40}$'){
  throw 'Configure the approved public signing certificate SHA1 thumbprint before accepting results'
}
python (Join-Path $PSScriptRoot 'signing_artifact.py') compare $Original $Returned --report $Report
if($LASTEXITCODE -ne 0){throw 'Signed artifact changed executable payloads or contained unexpected files'}
$rows=@()
foreach($name in @('AUTOCATCHSUBS.exe','AUTOCATCHSUBSBackend.exe')){
  $file=Get-Item -LiteralPath (Join-Path $Returned $name)
  $sig=Get-AuthenticodeSignature -LiteralPath $file.FullName
  if($sig.Status.ToString() -ne 'Valid' -or $sig.SignerCertificate.Thumbprint -ine $env:SIGNPATH_CERTIFICATE_THUMBPRINT){
    throw "Missing trusted approved publisher signature: $name"
  }
  if($null -eq $sig.TimeStamperCertificate){throw "Missing signing timestamp: $name"}
  if($sig.SignerCertificate.PublicKey.Oid.Value -ne '1.2.840.113549.1.1.1'){
    throw "Expected RSA certificate for Smart App Control: $name"
  }
  if($file.VersionInfo.ProductName -cne 'AUTOCATCHSUBS JR' -or $file.VersionInfo.ProductVersion -cne $Version){
    throw "Unexpected product metadata after signing: $name"
  }
  $rows+=@{file=$name;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash;
    signature='Valid';publisher=$sig.SignerCertificate.Subject;thumbprint=$sig.SignerCertificate.Thumbprint}
}
@{project_files_verified=$true;files=$rows;complete_installer=$false;smart_app_control_tested=$false;
  production_licenses_consumed=0} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Report -Encoding utf8
Write-Host 'Own-file signatures, timestamps, publisher, metadata and unchanged payloads verified. Installer/dependencies remain separate.'
