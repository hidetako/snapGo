; SnipNote - Inno Setup 6 script
; build.ps1 から  ISCC.exe /DAppVersion=x.y.z installer\snipnote.iss  で呼ばれる
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "SnipNote"
#define AppExe "SnipNote.exe"
#define AppPublisher "SnipNote"
#define AppURL "https://github.com/あなたのGitHubユーザー名/snipnote"

[Setup]
AppId={{6F1B7C1E-6D1B-4E7A-9C2B-5D2F3A8B9E01}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
; ユーザー単位インストール (UAC 不要 → 自動更新をサイレントで実行できる)
PrivilegesRequired=lowest
DefaultDirName={userpf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
SetupIconFile=..\assets\snipnote.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
MinVersion=10.0

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "サインイン時に自動起動する（PrintScreen キーでキャプチャ）"; GroupDescription: "起動:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\SnipNote\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--tray"; WorkingDir: "{app}"
Name: "{group}\{#AppName} を1回だけ起動"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--tray"; WorkingDir: "{app}"; Tasks: startup
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--tray"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; 通常インストール: 完了画面のチェックボックスで起動
Filename: "{app}\{#AppExe}"; Parameters: "--tray"; Description: "{#AppName} を起動する"; Flags: nowait postinstall skipifsilent
; サイレント(自動更新)時: 無条件で再起動
Filename: "{app}\{#AppExe}"; Parameters: "--tray"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "KillSnipNote"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// 更新・再インストール時に常駐中の SnipNote を終了させる
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
  Sleep(800);
  Result := '';
end;


