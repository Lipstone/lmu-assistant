; Installateur Windows de LMU Assistant (Inno Setup 6).
;   python packaging/build_exe.py --onedir
;   iscc /DAppVersion=0.1.0 packaging\installer.iss
; Résultat : dist\LMU-Assistant-Setup.exe
;
; Installation pour l'utilisateur seul (pas de droits administrateur) dans
; %LOCALAPPDATA%\Programs\LMU Assistant, avec raccourcis menu Démarrer / Bureau.
; Les fichiers posés par l'installateur ne portent pas la marque « téléchargé d'Internet » :
; Windows ne demande plus d'autorisation au lancement de l'application (seulement à l'installation).
; Les réglages (dossier data\ à côté de l'exe) sont conservés lors d'une mise à jour.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E0B2C1D-4F5A-4C3B-9A51-2D8C7B1E4A90}
AppName=LMU Assistant
AppVersion={#AppVersion}
AppPublisher=Lipstone
DefaultDirName={localappdata}\Programs\LMU Assistant
DefaultGroupName=LMU Assistant
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=LMU-Assistant-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\LMU-Assistant.exe
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\dist\LMU-Assistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Mise à jour : retire les bibliothèques de l'ancienne version (les réglages data\ sont gardés).
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\LMU Assistant"; Filename: "{app}\LMU-Assistant.exe"
Name: "{group}\Désinstaller LMU Assistant"; Filename: "{uninstallexe}"
Name: "{userdesktop}\LMU Assistant"; Filename: "{app}\LMU-Assistant.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LMU-Assistant.exe"; Description: "Lancer LMU Assistant"; Flags: nowait postinstall skipifsilent
