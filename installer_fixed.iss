
[Setup]
AppName=EyeAreSee IRC Client
AppVersion=1.0
DefaultDirName={pf}\EyeAreSee
DefaultGroupName=EyeAreSee
OutputBaseFilename=setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\starteyeareseeGUI.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\EyeAreSee IRC Client"; Filename: "{app}\starteyeareseeGUI.exe"
Name: "{commondesktop}\EyeAreSee IRC Client"; Filename: "{app}\starteyeareseeGUI.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:";

[Run]
Filename: "{app}\starteyeareseeGUI.exe"; Description: "Launch EyeAreSee"; Flags: nowait postinstall skipifsilent
