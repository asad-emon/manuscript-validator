; Inno Setup script for ManuscriptValidator (Task 15).
;
; Compiles the PyInstaller onedir build at dist\ManuscriptValidator\ into a
; single Setup.exe: Program Files install, Start Menu shortcut, uninstall
; entry, optional desktop shortcut. Run packaging\build.ps1 first (or at
; least `pyinstaller packaging\build.spec`) so dist\ManuscriptValidator\
; exists before compiling this.
;
; Compile with the Inno Setup IDE, or from the command line:
;   ISCC packaging\installer.iss

#define MyAppName "Manuscript Validator"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Manuscript Validator"
#define MyAppExeName "ManuscriptValidator.exe"

[Setup]
; Fixed GUID identifying this application across versions -- generated once;
; keep it stable so upgrades install over the previous version rather than
; side-by-side.
AppId={{744BE2C9-540B-4786-9603-B6232977F35B}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=ManuscriptValidatorSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Per-user install by default -- no admin prompt, no UAC elevation needed.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; The entire PyInstaller onedir output -- exe, its bundled Python runtime,
; Qt plugins, and the datas from build.spec (journal_v1.json, prompts/*.txt).
Source: "..\dist\ManuscriptValidator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
