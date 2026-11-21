#define AppName "To-do list"
#define AppVersion "1.0.0"
#define AppExe "To-do list.exe"

[Setup]
AppId={{3B7BF723-8FE9-43A7-9209-5DD10851D136}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=To-do-list-Setup-{#AppVersion}-x64
SetupIconFile=one-piece.ico
UninstallDisplayIcon={app}\{#AppExe}
VersionInfoVersion={#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: en; MessagesFile: "compiler:Default.isl"
#if FileExists(CompilerPath + "\Languages\ChineseSimplified.isl")
Name: zhcn; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif

[Tasks]
Name: desktopicon; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "build\app\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "ToDoList.Desktop"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "ToDoList.Desktop"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent unchecked

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  StartupCommand: String;
  StartupKey: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    StartupKey := 'Software\Microsoft\Windows\CurrentVersion\Run';
    if RegQueryStringValue(HKCU, StartupKey, 'ToDoListDesktop', StartupCommand) then
      if CompareText(StartupCommand, AddQuotes(ExpandConstant('{app}\{#AppExe}'))) = 0 then
        RegDeleteValue(HKCU, StartupKey, 'ToDoListDesktop');
  end;
end;
