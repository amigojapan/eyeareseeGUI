
[Setup]
AppName=EyeAreSee IRC Client
AppVersion=1.0
DefaultDirName={pf}\EyeAreSee
DefaultGroupName=EyeAreSee
OutputBaseFilename=setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\starteyeareseeGUI_urls.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\EyeAreSee IRC Client"; Filename: "{app}\starteyeareseeGUI_urls.exe"
Name: "{commondesktop}\EyeAreSee IRC Client"; Filename: "{app}\starteyeareseeGUI_urls.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:";

[Run]
Filename: "{app}\starteyeareseeGUI_urls.exe"; Description: "Launch EyeAreSee"; Flags: nowait postinstall skipifsilent
