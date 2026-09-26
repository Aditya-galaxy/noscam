; Inno Setup script for the Windows installer.
;   iscc /DAppVersion=1.1.0 scripts\noscam.iss   ->  dist\NoScam-Setup.exe
; Per-user install: no administrator prompt, nothing written outside the
; user's profile, and start-at-login is a checkbox the person can untick.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F2C8D0A-5B7E-4C1A-9E3D-4A1B2C3D4E5F}
AppName=NoScam
AppVersion={#AppVersion}
AppPublisher=NoScam
AppPublisherURL=https://aditya-galaxy.github.io/noscam/
AppSupportURL=https://github.com/Aditya-galaxy/noscam/issues
DefaultDirName={localappdata}\Programs\NoScam
DefaultGroupName=NoScam
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=NoScam-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\NoScam.exe
LicenseFile=..\LICENSE

[Tasks]
Name: "autostart"; Description: "Start NoScam when I log in (recommended — it can only protect you while it is running)"; GroupDescription: "Protection:"

[Files]
Source: "..\dist\NoScam\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\NoScam"; Filename: "{app}\NoScam.exe"
Name: "{group}\Uninstall NoScam"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "NoScam"; ValueData: """{app}\NoScam.exe"" --no-open"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\NoScam.exe"; Description: "Start NoScam and set it up"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM NoScam.exe /F"; Flags: runhidden; RunOnceId: "StopNoScam"
