# Rebuilds PyInstaller's bootloader (the small launcher inside Hexra.exe) from source and puts it into the build environment.
#
# Why: the stock bootloader that ships with PyInstaller is the same file inside thousands of programs, and antivirus
# machine-learning engines sometimes flag it (Windows Security removed Hexra.exe as Trojan:Win32/Bearfoos.A!ml). A bootloader
# compiled here is a different binary. It is not a guarantee, only a common and cheap mitigation.
#
# One-time setup (a C compiler; nothing is installed system-wide):
#   1. download w64devkit-x64-<version>.7z.exe from https://github.com/skeeto/w64devkit/releases and check its sha256
#      against the digest GitHub shows for the file
#   2. run it with:  w64devkit-x64-<version>.7z.exe -o"packaging\toolchain" -y     (this creates packaging\toolchain\w64devkit)
# Then run, from the project folder:  powershell -ExecutionPolicy Bypass -File packaging\build_bootloader.ps1
# The original bootloaders are backed up to packaging\toolchain\original-bootloaders the first time.
$ErrorActionPreference = "Stop"
$pk = Resolve-Path "packaging"
$tc = Join-Path $pk "toolchain"
$py = Join-Path $pk "buildenv\Scripts\python.exe"
if (-not (Test-Path "$tc\w64devkit\bin\gcc.exe")) { throw "packaging\toolchain\w64devkit\bin\gcc.exe not found: see the setup steps at the top of this file" }
$env:PATH = "$tc\w64devkit\bin;" + $env:PATH

# the PyInstaller source for the SAME version that is installed in the build environment
$ver = (& $py -m PyInstaller --version).Trim()
$src = Join-Path $tc "pyinstaller-src"
$tree = Join-Path $src "pyinstaller-$ver"
if (-not (Test-Path $tree)) {
    New-Item -ItemType Directory -Force $src | Out-Null
    $meta = Invoke-RestMethod "https://pypi.org/pypi/pyinstaller/$ver/json"
    $sd = $meta.urls | Where-Object { $_.packagetype -eq "sdist" } | Select-Object -First 1
    $tar = Join-Path $src $sd.filename
    Invoke-WebRequest $sd.url -OutFile $tar
    if ((Get-FileHash $tar -Algorithm SHA256).Hash.ToLower() -ne $sd.digests.sha256) { throw "the downloaded PyInstaller source does not match PyPI's sha256" }
    tar -xzf $tar -C $src
}

# build it (64-bit, MinGW-w64 gcc)
Push-Location (Join-Path $tree "bootloader")
& $py waf all --gcc --target-arch=64bit
if ($LASTEXITCODE -ne 0) { throw "bootloader build failed" }
Pop-Location

# install it into the build environment, keeping the originals
$built = Join-Path $tree "PyInstaller\bootloader\Windows-64bit-intel"
$stock = Join-Path $pk "buildenv\Lib\site-packages\PyInstaller\bootloader\Windows-64bit-intel"
$backup = Join-Path $tc "original-bootloaders"
New-Item -ItemType Directory -Force $backup | Out-Null
foreach ($f in "run.exe", "runw.exe", "run_d.exe", "runw_d.exe") {
    if (-not (Test-Path "$backup\$f")) { Copy-Item "$stock\$f" "$backup\$f" }
    Copy-Item "$built\$f" "$stock\$f" -Force
}
Write-Host "Custom bootloader installed into packaging\buildenv. Now run packaging\build_all.ps1."
