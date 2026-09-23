#define MyAppName "DCS Radio Voice Control"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "insipiens"

[Setup]
AppId={{D8473B43-684E-4AA5-A3F4-1E81D4AF11D9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\DCS Radio Voice Control
DefaultGroupName=DCS Radio Voice Control
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
MinVersion=10.0.22000
CloseApplications=no
RestartApplications=no
AppMutex=Local\DCSRadioVoiceControlController
RestartIfNeededByRun=no
UsePreviousAppDir=yes
UsePreviousTasks=yes
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=DCS-Radio-Voice-Control-Setup
LicenseFile=..\LICENSE
InfoBeforeFile=BEFORE_INSTALL.txt
AppModifyPath="{app}\configuration.bat"
UninstallDisplayName=DCS Radio Voice Control

[Files]
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\INSTALLATION.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\PIPER.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\configuration.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\install.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\maintenance.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\repair.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\run.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\setup.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\setup.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\setup-stt.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\setup-stt.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\setup-tts.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\setup-tts.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dcs\*.lua"; DestDir: "{app}\dcs"; Flags: ignoreversion
Source: "..\src\dcs_radio_voice_control\*.py"; DestDir: "{app}\src\dcs_radio_voice_control"; Flags: ignoreversion
Source: "..\tools\__init__.py"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\tools\build_radio_overlay.py"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\tools\install.py"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\tools\purge-local.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion

[Icons]
Name: "{group}\DCS Radio Voice Control"; Filename: "{app}\run.bat"; WorkingDir: "{app}"
Name: "{group}\Configure DCS Radio Voice Control"; Filename: "{app}\configuration.bat"; WorkingDir: "{app}"
Name: "{group}\Repair DCS Radio Voice Control"; Filename: "{app}\repair.bat"; WorkingDir: "{app}"

[Run]
Filename: "{app}\configuration.bat"; Parameters: "--start-after-save"; Description: "Configure DCS Radio Voice Control"; WorkingDir: "{app}"; Flags: postinstall skipifsilent
Filename: "{app}\run.bat"; Description: "Start DCS Radio Voice Control"; WorkingDir: "{app}"; Flags: postinstall skipifsilent nowait

[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\stt"
Type: filesandordirs; Name: "{app}\tools\piper"
Type: filesandordirs; Name: "{app}\models\piper"
Type: filesandordirs; Name: "{localappdata}\DCSRadioVoiceControl\logs"
Type: files; Name: "{localappdata}\DCSRadioVoiceControl\installation.json"
Type: dirifempty; Name: "{localappdata}\DCSRadioVoiceControl"

[Code]
var
  RemoveUserData: Boolean;

procedure RunRequired(const Filename, Params, Description: String);
var
  ResultCode: Integer;
begin
  WizardForm.StatusLabel.Caption := Description;
  if not Exec(Filename, Params, ExpandConstant('{app}'), SW_SHOWNORMAL,
    ewWaitUntilTerminated, ResultCode) then
    RaiseException(Description + ' could not be started: ' + SysErrorMessage(ResultCode));
  if ResultCode <> 0 then
  begin
    if Filename = ExpandConstant('{app}\setup.bat') then
      RaiseException(Description + ' failed with exit code ' + IntToStr(ResultCode) + '. Details: ' +
        ExpandConstant('{localappdata}\DCSRadioVoiceControl\logs\installer-components.log'));
    RaiseException(Description + ' failed with exit code ' + IntToStr(ResultCode) + '.');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    RunRequired(ExpandConstant('{app}\setup.bat'), '',
      'Checking DCS Radio Voice Control components...');
    RunRequired(ExpandConstant('{app}\runtime\python.exe'),
      '"' + ExpandConstant('{app}\tools\install.py') + '" install',
      'Installing the DCS radio-menu integration...');
  end;
end;

function InitializeUninstall: Boolean;
var
  ResultCode: Integer;
  PythonExe, InstallTool, Params: String;
begin
  Result := False;
  PythonExe := ExpandConstant('{app}\runtime\python.exe');
  InstallTool := ExpandConstant('{app}\tools\install.py');
  if not FileExists(PythonExe) or not FileExists(InstallTool) then
  begin
    MsgBox('DCS Radio Voice Control cannot safely verify and restore the DCS integration because its maintenance files are missing. Reinstall the same version, then uninstall again.',
      mbError, MB_OK);
    exit;
  end;

  Params := '"' + InstallTool + '" uninstall --remove-state';
  if not Exec(PythonExe, Params, ExpandConstant('{app}'), SW_SHOWNORMAL,
    ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('The DCS integration removal could not be started: ' + SysErrorMessage(ResultCode),
      mbError, MB_OK);
    exit;
  end;
  if ResultCode <> 0 then
  begin
    MsgBox('DCS Radio Voice Control did not remove the DCS integration safely. The application will not be uninstalled. Review the reported error before continuing.',
      mbError, MB_OK);
    exit;
  end;

  RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run',
    'DCS Radio Voice Control');
  DeleteFile(ExpandConstant('{userdesktop}\DCS Radio Voice Control.lnk'));

  RemoveUserData :=
    MsgBox('Keep your DCS Radio Voice Control configuration and aliases for a future reinstall?'#13#10#13#10 +
      'Choose Yes to keep them, or No to delete all remaining DCS Radio Voice Control user data.',
      mbConfirmation, MB_YESNO) = IDNO;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and RemoveUserData then
    DelTree(ExpandConstant('{localappdata}\DCSRadioVoiceControl'), True, True, True);
end;
