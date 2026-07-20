; Wraps the PyInstaller onedir bundle (dist/job-hunter/, from job-hunter.spec) into a
; Windows installer with a Start Menu entry. Authored against Inno Setup 6's documented
; syntax but not compiled in this environment (no Inno Setup toolchain installed here) —
; validate with `iscc` on a Windows machine with Inno Setup 6 before shipping.
;
; Build order:
;   1. uv run --with pyinstaller pyinstaller --noconfirm --clean packaging/windows/job-hunter.spec
;   2. iscc packaging/windows/job-hunter.iss /DAppVersion=0.25
;
; AppVersion is passed via /D from CI (release.yml reads it from pyproject.toml) so this
; file never needs hand-editing to release a new version.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{9F6E9B7A-5C2E-4B8E-9B0E-6A1E7C3E9B7A}
AppName=Job Hunter
AppVersion={#AppVersion}
AppPublisher=Abdul Basit
AppPublisherURL=https://github.com/abdulrbasit/job-hunter
DefaultDirName={autopf}\Job Hunter
DefaultGroupName=Job Hunter
DisableProgramGroupPage=yes
OutputDir=..\..\dist-installer
OutputBaseFilename=Job-Hunter-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
; Unsigned build — no SignTool directive here. Windows SmartScreen will warn on first
; run until a code-signing certificate is available; see docs/windows-packaging.md.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\job-hunter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Job Hunter"; Filename: "{app}\job-hunter.exe"; Parameters: "dash"; WorkingDir: "{app}"
Name: "{group}\Uninstall Job Hunter"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Job Hunter"; Filename: "{app}\job-hunter.exe"; Parameters: "dash"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\job-hunter.exe"; Parameters: "dash"; Description: "Launch Job Hunter"; Flags: nowait postinstall skipifsilent
