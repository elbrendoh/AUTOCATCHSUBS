"""Independent Windows diagnostic: no app executable, license or secrets read."""
from pathlib import Path
import sys

CODE=r"""
$ErrorActionPreference='Continue'
$acsRoot=$env:ACS_DIAG_ROOT
if(-not $acsRoot -or -not (Test-Path -LiteralPath (Join-Path $acsRoot 'AUTOCATCHSUBSBackend.exe'))) { $acsRoot=Join-Path $env:LOCALAPPDATA '@FOLDER@' }
$acsOut=Join-Path $env:TEMP 'AUTOCATCHSUBS-Diagnostico.txt'
$acsLines=New-Object 'System.Collections.Generic.List[string]'
$acsLines.Add('AUTOCATCHSUBS - Diagnostico de distribucion r11')
$acsLines.Add('Fecha: '+(Get-Date).ToString('s'))
$acsLines.Add('Instalacion: '+$acsRoot)
$acsLines.Add('Windows: '+[Environment]::OSVersion.VersionString+'; x64='+[Environment]::Is64BitOperatingSystem)
$acsPolicy=Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' -ErrorAction SilentlyContinue
$acsLines.Add('Smart App Control VerifiedAndReputablePolicyState: '+$acsPolicy.VerifiedAndReputablePolicyState)
foreach($acsName in @('AUTOCATCHSUBS.exe','AUTOCATCHSUBSBackend.exe','_internal\_cffi_backend.cp312-win_amd64.pyd','_internal\backports\zstd\_zstd.cp312-win_amd64.pyd','_internal\cryptography\hazmat\bindings\_rust.pyd')) { $acsFile=Join-Path $acsRoot $acsName; if(Test-Path -LiteralPath $acsFile -PathType Leaf) { try { $acsSig=Get-AuthenticodeSignature -LiteralPath $acsFile; $acsHash=Get-FileHash -LiteralPath $acsFile -Algorithm SHA256; $acsLines.Add($acsName+' | Firma='+$acsSig.Status+' | SHA256='+$acsHash.Hash); if($acsSig.SignerCertificate) { $acsLines.Add('Editor: '+$acsSig.SignerCertificate.Subject) } } catch { $acsLines.Add($acsName+' | Error='+$_.Exception.Message) } } else { $acsLines.Add($acsName+' | NO EXISTE en esta cuenta de Windows') } }
$acsLines.Add('Eventos recientes de CodeIntegrity SOLO para AUTOCATCHSUBS:')
try { $acsEvents=Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-CodeIntegrity/Operational';StartTime=(Get-Date).AddDays(-2)} -MaxEvents 300 -ErrorAction Stop | Where-Object {$_.Message -match 'AUTOCATCHSUBS'} | Select-Object -First 8; foreach($acsEvent in $acsEvents) { $acsLines.Add($acsEvent.TimeCreated.ToString('s')+' | Evento '+$acsEvent.Id+' | '+$acsEvent.Message) }; if(-not $acsEvents) { $acsLines.Add('Sin eventos coincidentes') } } catch { $acsLines.Add('No se pudieron leer los eventos: '+$_.Exception.Message) }
$acsLines.Add('Este informe no contiene claves de activacion ni HWID y no cambia la seguridad de Windows.')
[IO.File]::WriteAllLines($acsOut,$acsLines,(New-Object Text.UTF8Encoding($false)))
Write-Host ('Informe guardado: '+$acsOut)
if($env:ACS_DIAG_NO_UI -ne '1') { Start-Process notepad.exe -ArgumentList (([char]34)+$acsOut+([char]34)) }
"""

def write(destination,edition):
    code='; '.join(line.strip() for line in CODE.replace('@FOLDER@','AUTOCATCHSUBS' if edition=='admin' else 'AUTOCATCHSUBSJR').strip().splitlines())
    assert '"' not in code and '%' not in code
    text='@echo off\r\nsetlocal\r\nset "ACS_DIAG_ROOT=%~dp0"\r\npowershell.exe -NoLogo -NoProfile -Command "'+code+'"\r\nif errorlevel 1 pause\r\n'
    assert len(text)<7900
    Path(destination).write_bytes(text.encode('ascii'))

if __name__=='__main__':write(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else 'jr')
