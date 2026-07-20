#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif
#ifndef AppNumericVersion
  #define AppNumericVersion "1.2.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\tmp\installer-1.2.0\pyinstaller"
#endif
#ifndef OutputDir
  #define OutputDir "..\release\v1.2.0"
#endif
#ifndef PackageSuffix
  #define PackageSuffix ""
#endif

[Setup]
AppId={{D8231018-D13E-4B0B-82D4-460FA177D93F}
AppName=ECU Map Studio
AppVersion={#AppVersion}
AppVerName=ECU Map Studio {#AppVersion}
AppPublisher=CAATZ
VersionInfoVersion={#AppNumericVersion}
VersionInfoCompany=CAATZ
VersionInfoDescription=ECU Map Studio Installer
VersionInfoProductName=ECU Map Studio
VersionInfoProductVersion={#AppNumericVersion}
DefaultDirName={localappdata}\Programs\ECU Map Studio
DefaultGroupName=ECU Map Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=ECU-Map-Studio-{#AppVersion}-Windows-x64{#PackageSuffix}-Setup
SetupIconFile=..\assets\ECUMapStudio.ico
UninstallDisplayIcon={app}\ECUMapStudio.exe
LicenseFile={#SourceDir}\LICENSE.txt
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ECU Map Studio"; Filename: "{app}\ECUMapStudio.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\ECU Map Studio"; Filename: "{app}\ECUMapStudio.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ECUMapStudio.exe"; Description: "Launch ECU Map Studio"; Flags: nowait postinstall skipifsilent
