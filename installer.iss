; PKG Viewer installer — per-user, file icons, no admin needed.
#define AppVer "1.14.0"

[Setup]
AppName=PKG Viewer
AppVersion={#AppVer}
AppPublisher=Loopayeh
DefaultDirName={autopf}\PKG Viewer
DefaultGroupName=PKG Viewer
OutputDir=.
OutputBaseFilename=PKGViewer-Setup-{#AppVer}
PrivilegesRequired=lowest
Compression=lzma2/max
SolidCompression=yes
UninstallDisplayName=PKG Viewer
WizardStyle=modern

[Files]
Source: "dist\PKGViewer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icons\pkg.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "assets\icons\exfat.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "assets\icons\ffpfsc.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "assets\icons\ffpkg.ico"; DestDir: "{app}\icons"; Flags: ignoreversion

[Icons]
Name: "{group}\PKG Viewer"; Filename: "{app}\PKGViewer.exe"
Name: "{autodesktop}\PKG Viewer"; Filename: "{app}\PKGViewer.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; Flags: unchecked

[Registry]
; show in Settings -> Default apps (per-user, no admin)
Root: HKCU; Subkey: "Software\Loopayeh\PKGViewer\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "PKG Viewer"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Loopayeh\PKGViewer\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "View PS3/PS4/PS5 package contents"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Loopayeh\PKGViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pkg"; ValueData: "Loopayeh.PKGViewer.pkg"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Loopayeh\PKGViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".exfat"; ValueData: "Loopayeh.PKGViewer.exfat"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Loopayeh\PKGViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ffpfsc"; ValueData: "Loopayeh.PKGViewer.ffpfsc"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Loopayeh\PKGViewer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ffpkg"; ValueData: "Loopayeh.PKGViewer.ffpkg"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "PKG Viewer"; ValueData: "Software\Loopayeh\PKGViewer\Capabilities"; Flags: uninsdeletevalue
; show in Open With menu
Root: HKCU; Subkey: "Software\Classes\.pkg\OpenWithProgids"; ValueType: string; ValueName: "Loopayeh.PKGViewer.pkg"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.exfat\OpenWithProgids"; ValueType: string; ValueName: "Loopayeh.PKGViewer.exfat"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.ffpfsc\OpenWithProgids"; ValueType: string; ValueName: "Loopayeh.PKGViewer.ffpfsc"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.ffpkg\OpenWithProgids"; ValueType: string; ValueName: "Loopayeh.PKGViewer.ffpkg"; ValueData: ""; Flags: uninsdeletevalue
; .pkg
Root: HKCU; Subkey: "Software\Classes\.pkg"; ValueType: string; ValueName: ""; ValueData: "Loopayeh.PKGViewer.pkg"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.pkg"; ValueType: string; ValueName: ""; ValueData: "PKG Package"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.pkg\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\icons\pkg.ico,0"
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.pkg\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PKGViewer.exe"" ""%1"""
; .exfat
Root: HKCU; Subkey: "Software\Classes\.exfat"; ValueType: string; ValueName: ""; ValueData: "Loopayeh.PKGViewer.exfat"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.exfat"; ValueType: string; ValueName: ""; ValueData: "exFAT Image"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.exfat\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\icons\exfat.ico,0"
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.exfat\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PKGViewer.exe"" ""%1"""
; .ffpfsc
Root: HKCU; Subkey: "Software\Classes\.ffpfsc"; ValueType: string; ValueName: ""; ValueData: "Loopayeh.PKGViewer.ffpfsc"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.ffpfsc"; ValueType: string; ValueName: ""; ValueData: "FFPFSC Image"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.ffpfsc\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\icons\ffpfsc.ico,0"
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.ffpfsc\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PKGViewer.exe"" ""%1"""
; .ffpkg
Root: HKCU; Subkey: "Software\Classes\.ffpkg"; ValueType: string; ValueName: ""; ValueData: "Loopayeh.PKGViewer.ffpkg"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.ffpkg"; ValueType: string; ValueName: ""; ValueData: "FFPKG Image"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.ffpkg\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\icons\ffpkg.ico,0"
Root: HKCU; Subkey: "Software\Classes\Loopayeh.PKGViewer.ffpkg\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PKGViewer.exe"" ""%1"""

[Code]
procedure SHChangeNotify(wEventID: Integer; uFlags: Cardinal; dwItem1, dwItem2: Cardinal);
  external 'SHChangeNotify@shell32.dll stdcall';

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    // auto-close running app so files are not locked (silent, no prompt)
    try
      Exec('taskkill.exe', '/F /IM PKGViewer.exe', '', SW_HIDE,
           ewWaitUntilTerminated, ResultCode);
    except
    end;
  end;
  if CurStep = ssPostInstall then
  begin
    // refresh explorer icon cache so new icons show immediately
    try
      SHChangeNotify($08000000, 0, 0, 0);
    except
    end;
  end;
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}\icons"

[Run]
Filename: "{app}\PKGViewer.exe"; Parameters: "--first-install"; Description: "Launch PKG Viewer"; Flags: nowait postinstall skipifsilent
