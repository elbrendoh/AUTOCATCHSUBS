#ifndef Edition
  #define Edition "jr"
#endif
#if Edition == "admin"
  #define DisplayName "AUTOCATCHSUBS"
  #define DirectoryName "AUTOCATCHSUBS"
  #define InstallerName "AUTOCATCHSUBS-Admin-Setup"
  #define AppGuid "38DFB310-C847-4401-9292-3529C687648B"
#else
  #define DisplayName "AUTOCATCHSUBS JR"
  #define DirectoryName "AUTOCATCHSUBSJR"
  #define InstallerName "AUTOCATCHSUBSJR-Setup"
  #define AppGuid "A79CBEF2-CF33-4510-9EDC-46D899E6051D"
#endif
#define ReleaseRoot SourcePath + "\.."
#define PackageRoot ReleaseRoot + "\AUTOCATCHSUBS-packages\" + Edition
#if !FileExists(PackageRoot + "\AUTOCATCHSUBS.exe")
  #error "Primero compila, verifica y ensambla el ejecutable de esta edición."
#endif
#if !FileExists(PackageRoot + "\manifest.json")
  #error "Falta el manifiesto del paquete ensamblado."
#endif

[Setup]
AppId={{{#AppGuid}}
AppName={#DisplayName}
AppVersion=3.8.11
AppPublisher=AUTOCATCH
DefaultDirName={localappdata}\{#DirectoryName}
DefaultGroupName={#DisplayName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir={#ReleaseRoot}\AUTOCATCHSUBS-installers
OutputBaseFilename={#InstallerName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#ReleaseRoot}\AUTOCATCHSUBS-release-source\icons\icon.ico
UninstallDisplayIcon={app}\AUTOCATCHSUBS.exe
CloseApplications=no
RestartApplications=no
ChangesAssociations=no
LicenseFile={#PackageRoot}\LICENSE-AutoSubs
InfoAfterFile={#PackageRoot}\LEEME.txt

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "{#PackageRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ReleaseRoot}\AUTOCATCHSUBS-build-tools\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy
Source: "menu-template.lua"; Flags: dontcopy

[Icons]
Name: "{group}\Cómo abrir {#DisplayName}"; Filename: "{app}\LEEME.txt"
Name: "{group}\Desinstalar {#DisplayName}"; Filename: "{uninstallexe}"

[UninstallDelete]
Type: files; Name: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\{#DisplayName}.lua"

[Code]
function CreateFileW(Name: String; Access, Share: Cardinal; Security: LongWord; Creation, Flags: Cardinal; Template: THandle): THandle;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';
function HasWebView2: Boolean;
var Version: String;
begin
  Result := (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function OwnFilesBusy: Boolean;
var Handle: THandle; Name: String;
begin
  Result := False;
  Name := ExpandConstant('{app}\AUTOCATCHSUBS.exe');
  if FileExists(Name) then begin
    Handle := CreateFileW(Name, $C0000000, 0, 0, 3, $80, 0);
    if Handle = THandle(-1) then Result := True else CloseHandle(Handle);
  end;
  Name := ExpandConstant('{app}\AUTOCATCHSUBSBackend.exe');
  if FileExists(Name) then begin
    Handle := CreateFileW(Name, $C0000000, 0, 0, 3, $80, 0);
    if Handle = THandle(-1) then Result := True else CloseHandle(Handle);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ResultCode: Integer;
begin
  Result := '';
  if OwnFilesBusy then begin
    Result := 'Guarda las ediciones y cierra {#DisplayName}. Si su puente sigue activo, cierra Resolve y vuelve a intentar. No se cerró ninguna aplicación automáticamente.';
    exit;
  end;
  if not HasWebView2 then begin
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    if (not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (not HasWebView2) then
      Result := 'No se pudo preparar Microsoft WebView2. Conéctate a Internet y vuelve a ejecutar el instalador.';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Template: AnsiString; Script: String; MenuDir: String; ResultCode: Integer;
begin
  if CurStep = ssPostInstall then begin
    { Offline test: JR is allowed to be unactivated. No license is consumed. }
    if (not Exec(ExpandConstant('{app}\AUTOCATCHSUBSBackend.exe'),
      '--installation-check "'+ExpandConstant('{app}\installation-check.json')+'"',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      RaiseException('Windows no pudo iniciar {#DisplayName}. Codigo='+IntToStr(ResultCode)+'. Revisa el aviso de Seguridad de Windows y ejecuta DIAGNOSTICO AUTOCATCHSUBS.cmd desde la carpeta de instalacion. Si indica editor no verificado, hace falta una version firmada. No se debe considerar esta instalacion lista para usar.');
    ExtractTemporaryFile('menu-template.lua');
    if not LoadStringFromFile(ExpandConstant('{tmp}\menu-template.lua'), Template) then RaiseException('No se pudo leer el registro de Resolve');
    Script := String(Template);
    StringChangeEx(Script, '@INSTALL_ROOT@', ExpandConstant('{app}'), True);
    MenuDir := ExpandConstant('{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility');
    if not ForceDirectories(MenuDir) then RaiseException('No se pudo crear la carpeta de scripts de Resolve');
    if not SaveStringToFile(MenuDir+'\{#DisplayName}.lua', UTF8Encode(Script), False) then RaiseException('No se pudo registrar {#DisplayName} en Resolve');
  end;
end;
