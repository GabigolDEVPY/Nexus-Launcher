#ifndef MyAppVersion
  #define MyAppVersion "1.0.1"
#endif

#define MyAppName "NexusLauncher"
#define MyAppPublisher "NexusStudio"
#define MyAppExeName "NexusLauncher.exe"
#define MyBuildDir "..\dist\NexusLauncher"
#define MyOutputDir "..\dist-installer"

#ifexist "..\icon.ico"
  #define MyInstallerIcon "..\icon.ico"
#endif

[Setup]
AppId={{8F9E498C-55D8-4C42-BD81-0D28B9987E10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
OutputDir={#MyOutputDir}
OutputBaseFilename=NexusLauncher-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
#ifdef MyInstallerIcon
SetupIconFile={#MyInstallerIcon}
#endif

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} agora"; Flags: nowait postinstall skipifsilent
