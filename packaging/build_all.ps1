# Builds packaging\Hexra-Setup.exe (one file, nothing else needed) and packaging\Hexra-Guide.pdf.
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File packaging\build_all.ps1
$ErrorActionPreference = "Stop"
$py = ".venv\Scripts\python.exe"
$pk = "packaging"

# 1. the program
& powershell -NoProfile -File "$pk\build_app.ps1"
if ($LASTEXITCODE -ne 0) { throw "app build failed" }
$stage = "$pk\dist\Hexra"
New-Item -ItemType Directory -Force "$stage\models" | Out-Null
Copy-Item models\hand_landmarker.task "$stage\models" -Force      # the face models are left out of this release
# a clean config with the face lock switched OFF for this release; data\ (your face, your logs) is never copied
$cfg = [IO.File]::ReadAllText((Resolve-Path config.yaml).Path)
$cfg = [regex]::Replace($cfg, "(face_lock:\s*\r?\n\s*enabled:) true", '$1 false')
[IO.File]::WriteAllText((Join-Path (Resolve-Path $stage).Path "config.yaml"), $cfg.TrimStart([char]0xFEFF), (New-Object Text.UTF8Encoding $false))

Copy-Item "$pk\app.ico" "$stage\Hexra.ico" -Force      # the windows' icon (OpenCV and the console do not inherit the exe's)

# 2. the guide
& $py "$pk\make_pdf.py" "$pk\Hexra-Guide.pdf"
Copy-Item "$pk\Hexra-Guide.pdf" "$stage\User Guide.pdf" -Force

# 3. payload.zip -> single-file installer
if (Test-Path "$pk\payload.zip") { Remove-Item "$pk\payload.zip" }
& $py -c "import shutil; shutil.make_archive(r'$pk\payload', 'zip', r'$stage')"
$zip = (Resolve-Path "$pk\payload.zip").Path
$icon = (Resolve-Path "$pk\app.ico").Path
& "$pk\buildenv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name Hexra-Setup --icon $icon `
  --distpath $pk --workpath "$pk\build_setup" --specpath $pk --add-data "${zip};." --add-data "${icon};." `
  --exclude-module numpy --exclude-module cv2 --exclude-module mediapipe --exclude-module matplotlib --exclude-module PIL `
  "$pk\installer.py"
if ($LASTEXITCODE -ne 0) { throw "installer build failed" }
Write-Host "Done: $pk\Hexra-Setup.exe"
