; Inno Setup script - builds GunshotSetup-<version>.exe from dist\Gunshot.exe.
; Build:  iscc /DAppVersion=1.0.0 installer\gunshot.iss
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6E4B7C2A-3F1D-4C8E-9A5B-2D7F0E1C9B3A}
AppName=Gunshot
AppVersion={#AppVersion}
AppPublisher=Gunshot
DefaultDirName={autopf}\Gunshot
DefaultGroupName=Gunshot
DisableProgramGroupPage=yes
; Per-user install: no admin prompt needed.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=GunshotSetup-{#AppVersion}
SetupIconFile=..\packaging\icons\gunshot.ico
UninstallDisplayIcon={app}\Gunshot.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start Gunshot automatically when I sign in"; Flags: unchecked

[Files]
Source: "..\dist\Gunshot.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Gunshot"; Filename: "{app}\Gunshot.exe"
Name: "{group}\Uninstall Gunshot"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Gunshot"; Filename: "{app}\Gunshot.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "Gunshot"; ValueData: """{app}\Gunshot.exe"""; Tasks: startup

[Run]
Filename: "{app}\Gunshot.exe"; Description: "Launch Gunshot now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the app and remove start-at-login even if it was turned on from the tray menu.
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Gunshot.exe /F"; Flags: runhidden; RunOnceId: "KillGunshot"
Filename: "{sys}\reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v Gunshot /f"; Flags: runhidden; RunOnceId: "RemoveRunKey"

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\Gunshot"
