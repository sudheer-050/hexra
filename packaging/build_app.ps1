# Builds packaging\dist\Hexra\ (the program) with PyInstaller. Run from the project folder.
# A WINDOWED program (--noconsole): no terminal opens next to the camera window. launcher.py opens a console only when a
# command needs one (enroll, precision, selftest, uninstall).
# Uses packaging\buildenv: a slim environment with mediapipe + plain opencv-python (no contrib, no face recogniser).
$ErrorActionPreference = "Stop"
$icon = (Resolve-Path "packaging\app.ico").Path
packaging\buildenv\Scripts\python.exe -m PyInstaller --noconfirm --clean --name Hexra --noconsole `
  --paths src --distpath packaging\dist --workpath packaging\build --specpath packaging `
  --collect-all mediapipe --collect-submodules hexra `
  --exclude-module sklearn --exclude-module pytest --exclude-module scipy --exclude-module matplotlib --exclude-module PIL `
  --exclude-module pandas --exclude-module IPython `
  --icon $icon packaging\launcher.py
if ($LASTEXITCODE -ne 0) { throw "app build failed" }
# video-FILE decoder: a webcam does not use it (30 MB)
Get-ChildItem packaging\dist\Hexra\_internal\cv2 -Filter "opencv_videoio_ffmpeg*.dll" | Remove-Item -Force
