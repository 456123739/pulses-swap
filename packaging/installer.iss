; Inno Setup 安装器脚本 —— 由 CI 在 Windows runner 上编译
; 用法: iscc packaging\installer.iss /DMyAppVersion=3.0.3
; 输入: dist\PulsesSwap\  (PyInstaller 目录版产物)
; 输出: dist\installer\PulsesSwap-Setup-<version>.exe

#ifndef MyAppVersion
  #define MyAppVersion "3.0.1"
#endif

#define MyAppName "Pulses Swap"
#define MyAppPublisher "Pulses0 Studio"
#define MyAppExeName "PulsesSwap.exe"
#define MyAppId "{{8F3A2C41-7B5E-4D9A-9E21-5C6D4A1B7F30}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=PulsesSwap-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 安装器自身与"添加/删除程序"里显示的图标
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; 用户数据放在程序目录（应用自己的 database 机制），卸载时保留
UninstallDisplayName={#MyAppName}

[Languages]
Name: "chinese"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"


[Code]
function WebView2RuntimeInstalled: Boolean;
var
  Value: string;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Value) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Value) or
    DirExists(ExpandConstant('{commonpf}\Microsoft\EdgeWebView\Application'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not WebView2RuntimeInstalled) then
    MsgBox('Pulses Swap 需要 Microsoft Edge WebView2 Runtime。' + #13#10 +
           '请从 https://developer.microsoft.com/microsoft-edge/webview2/ 安装后重新启动程序。',
           mbInformation, MB_OK);
end;

[Files]
Source: "..\dist\PulsesSwap\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#if FileExists(AddBackslash(SourcePath) + "MicrosoftEdgeWebview2Setup.exe")
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
#endif

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
#if FileExists(AddBackslash(SourcePath) + "MicrosoftEdgeWebview2Setup.exe")
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "正在安装 WebView2 Runtime…"; Flags: waituntilterminated; Check: not WebView2RuntimeInstalled
#endif
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
