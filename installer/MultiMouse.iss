; MultiMouse - Windows installer (Inno Setup 6)
; Built by: python build.py --installer   (passes AppVersion and DistDir)

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\dist"
#endif

#define AppName "MultiMouse"
#define AppExe "MultiMouse.exe"
#define Assets "..\multimouse\assets"

[Setup]
AppId={{6C1F3E52-8B7A-4D2E-9F1A-4B6A2D9C7E10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=MultiMouse
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=MultiMouse-Setup-{#AppVersion}
SetupIconFile={#Assets}\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardSizePercent=100
WizardSmallImageFile={#Assets}\wizard-small-55.bmp,{#Assets}\wizard-small.bmp
Compression=lzma2/ultra64
SolidCompression=yes
AppMutex=MultiMouseSingleInstance
CloseApplications=yes
MinVersion=10.0

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
fr.StartWithWindows=Lancer MultiMouse au démarrage de Windows
en.StartWithWindows=Start MultiMouse when Windows starts
fr.OtherTasks=Options :
en.OtherTasks=Options:
fr.Launch=Lancer MultiMouse
en.Launch=Launch MultiMouse

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "{cm:StartWithWindows}"; GroupDescription: "{cm:OtherTasks}"

[InstallDelete]
; Files of the previous version (they all live in _internal)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#DistDir}\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{commonstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--minimized"; Tasks: startup

[Run]
; Open the firewall for MultiMouse (TCP 24800 control, UDP 24801 discovery) on private networks
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden; StatusMsg: "Configuration du pare-feu..."
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#AppName}"" dir=in action=allow program=""{app}\{#AppExe}"" enable=yes profile=private,domain"; Flags: runhidden
; Task that starts MultiMouse with administrator rights without a UAC prompt: otherwise Windows
; hides the mouse from it while an administrator window is in front (see app._relaunch_elevated)
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$a = New-ScheduledTaskAction -Execute '{app}\{#AppExe}' -Argument '--elevated'; $p = New-ScheduledTaskPrincipal -UserId '{username}' -LogonType Interactive -RunLevel Highest; $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -Priority 4; Register-ScheduledTask -TaskName '{#AppName}' -Action $a -Principal $p -Settings $s -Force"""; Flags: runhidden; StatusMsg: "Configuration du lancement..."
Filename: "{app}\{#AppExe}"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden; RunOnceId: "DelFirewall"
Filename: "{sys}\schtasks.exe"; Parameters: "/delete /tn ""{#AppName}"" /f"; Flags: runhidden; RunOnceId: "DelTask"
