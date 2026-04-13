$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$LaunchBat = Join-Path $AppDir "launch.bat"
$Desktop = [System.Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Real-time Translation.lnk"

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($ShortcutPath)
$sc.TargetPath = $LaunchBat
$sc.WorkingDirectory = $AppDir
$sc.Description = "Real-time Translation App"
$sc.Save()

Write-Host "Shortcut created: $ShortcutPath"
pause
