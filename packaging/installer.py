"""Hexra setup: one file, nothing else to download.

Everything the program needs (the program itself, its libraries, the hand-tracking model and the user
guide) is inside this file. Run it, press Install.

    Setup.exe                         the wizard
    Setup.exe /S                      silent install with the defaults
    Setup.exe /S /DIR=D:\\Apps\\GC     silent install into a chosen folder      (/NOSHORTCUTS skips the shortcuts)
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

APP, VERSION = "Hexra", "1.5.0"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Hexra"
KEEP_IF_EXISTS = {"config.yaml"}           # the user's own settings are never overwritten by a re-install
NO_WINDOW = 0x08000000


def resource(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / name


def default_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "Hexra"


def extract(target: Path, progress=lambda done, total: None) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(resource("payload.zip")) as z:
        infos = z.infolist()
        total = sum(i.file_size for i in infos) or 1
        done = 0
        for info in infos:
            dest = target / info.filename
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            elif not (info.filename in KEEP_IF_EXISTS and dest.exists()):
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(dest, "wb") as out:
                    while chunk := src.read(1 << 20):
                        out.write(chunk)
            done += info.file_size
            progress(done, total)
    (target / "data").mkdir(exist_ok=True)


def _ps(script: str) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                       text=True, creationflags=NO_WINDOW)
    return r.stdout.strip()


def make_shortcut(path: Path, target: Path, args: str = "", cwd: Path | None = None, description: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    q = lambda s: str(s).replace("'", "''")
    _ps("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');$s.TargetPath='%s';$s.Arguments='%s';"
        "$s.WorkingDirectory='%s';$s.IconLocation='%s';$s.Description='%s';$s.Save()"
        % (q(path), q(target), q(args), q(cwd or target.parent), q(target), q(description)))


def desktop_dir() -> Path:
    out = _ps("[Environment]::GetFolderPath('Desktop')")
    return Path(out) if out else Path.home() / "Desktop"


def register(target: Path) -> None:
    import winreg

    exe = target / "Hexra.exe"
    size_kb = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) // 1024
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        for name, val in (("DisplayName", APP), ("DisplayVersion", VERSION), ("Publisher", "Hexra"),
                          ("InstallLocation", str(target)), ("DisplayIcon", str(exe)),
                          ("UninstallString", f'"{exe}" uninstall')):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, int(size_kb))
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)


def shortcuts(target: Path, desktop: bool, start_menu: bool) -> None:
    exe = target / "Hexra.exe"
    if start_menu:
        sm = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Hexra"
        make_shortcut(sm / "Hexra.lnk", exe, cwd=target, description="Hexra: settings, live camera and hand control in one window")
        for old in ("Hexra Settings.lnk", "Hexra (try it, mouse untouched).lnk"):     # earlier versions had separate shortcuts; it is one application now
            (sm / old).unlink(missing_ok=True)
        if (target / "User Guide.pdf").exists():
            make_shortcut(sm / "User Guide.lnk", target / "User Guide.pdf", cwd=target)
        make_shortcut(sm / "Uninstall Hexra.lnk", exe, "uninstall", target)
    if desktop:
        make_shortcut(desktop_dir() / "Hexra.lnk", exe, cwd=target, description="Control your screen with hand gestures")


def install(target: Path, desktop=True, start_menu=True, progress=lambda d, t: None) -> None:
    extract(target, progress)
    shortcuts(target, desktop, start_menu)
    register(target)


def silent(argv: list[str]) -> int:
    target = default_dir()
    for a in argv:
        if a.upper().startswith("/DIR="):
            target = Path(a[5:].strip('"'))
    skip = "/NOSHORTCUTS" in [a.upper() for a in argv]
    install(target, desktop=not skip, start_menu=not skip)
    return 0


def set_window_icon(root) -> None:
    """Put the Hexra icon on the wizard's window (title bar and taskbar); tkinter's own icon call does not reach the taskbar."""
    try:
        import ctypes

        u = ctypes.windll.user32
        u.LoadImageW.restype = ctypes.c_void_p
        u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        hwnd = int(root.frame(), 16)
        for kind, metric in ((1, 11), (0, 49)):               # ICON_BIG / SM_CXICON, ICON_SMALL / SM_CXSMICON
            size = u.GetSystemMetrics(metric)
            handle = u.LoadImageW(None, str(resource("app.ico")), 1, size, size, 0x10)
            if handle:
                u.SendMessageW(hwnd, 0x80, kind, handle)
    except Exception:
        pass


def wizard() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Hexra.Setup")   # its own taskbar identity
    except Exception:
        pass
    root = tk.Tk()
    root.title(f"{APP} Setup")
    try:
        root.iconbitmap(default=str(resource("app.ico")))          # the Hexra icon in the title bar and taskbar, not tkinter's
    except Exception:
        pass
    root.update_idletasks()
    set_window_icon(root)
    root.resizable(False, False)
    pad = {"padx": 18}
    ttk.Label(root, text=f"Install {APP} {VERSION}", font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(16, 2), **pad)
    ttk.Label(root, justify="left", wraplength=500, text=(
        "Control your computer with hand gestures from a webcam: move the cursor, click, right-click, scroll in four "
        "directions and move windows. Everything is included in this file; nothing else is downloaded. Your camera "
        "picture never leaves your computer.")).pack(anchor="w", **pad)
    ttk.Label(root, text="Install into:").pack(anchor="w", pady=(14, 0), **pad)
    row = ttk.Frame(root)
    row.pack(fill="x", **pad)
    path_var = tk.StringVar(value=str(default_dir()))
    ttk.Entry(row, textvariable=path_var, width=58).pack(side="left", fill="x", expand=True)

    def browse():
        d = filedialog.askdirectory(initialdir=str(Path(path_var.get()).parent))
        if d:
            path_var.set(d if Path(d).name == "Hexra" else str(Path(d) / "Hexra"))

    ttk.Button(row, text="Browse...", command=browse).pack(side="left", padx=(6, 0))
    desk, menu, launch = tk.BooleanVar(value=True), tk.BooleanVar(value=True), tk.BooleanVar(value=True)
    ttk.Checkbutton(root, text="Desktop shortcut", variable=desk).pack(anchor="w", pady=(10, 0), **pad)
    ttk.Checkbutton(root, text="Start Menu shortcuts (including the user guide and uninstall)", variable=menu).pack(anchor="w", **pad)
    ttk.Checkbutton(root, text="Start Hexra when setup finishes", variable=launch).pack(anchor="w", **pad)
    ttk.Label(root, foreground="#555", wraplength=500, justify="left", text=(
        "This version has no face lock: anyone in front of the camera can use the gestures. "
        "It needs about 270 MB of disk space.")).pack(anchor="w", pady=(8, 0), **pad)
    bar = ttk.Progressbar(root, length=500, maximum=100)
    bar.pack(pady=(14, 2), **pad)
    status = tk.StringVar(value="Ready to install.")
    ttk.Label(root, textvariable=status).pack(anchor="w", **pad)
    buttons = ttk.Frame(root)
    buttons.pack(fill="x", pady=14, **pad)
    go = ttk.Button(buttons, text="Install")
    go.pack(side="right")
    ttk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=8)
    result: dict = {}

    def on_progress(done, total):
        root.after(0, lambda: (bar.configure(value=95 * done / total), status.set(f"Copying files... {100 * done // total}%")))

    def work(target: Path, want_desktop: bool, want_menu: bool):
        try:
            install(target, want_desktop, want_menu, on_progress)
            result["ok"] = True
        except Exception as e:                      # shown to the user, not swallowed
            result["error"] = f"{type(e).__name__}: {e}"
        root.after(0, finished)

    def finished():
        if "error" in result:
            status.set("Installation failed.")
            messagebox.showerror(APP, f"Setup could not finish:\n\n{result.pop('error')}")
            go.state(["!disabled"])
            return
        bar.configure(value=100)
        status.set("Done.")
        target = Path(path_var.get())
        messagebox.showinfo(APP, "Installed.\n\nStart it from the desktop or Start Menu. Raise an open palm for 1 second "
                                 "to wake the gestures, then press F8 to engage.")
        if launch.get():
            subprocess.Popen([str(target / "Hexra.exe")], cwd=str(target))
        root.destroy()

    def start():
        go.state(["disabled"])
        status.set("Installing...")
        threading.Thread(target=work, args=(Path(path_var.get()), desk.get(), menu.get()), daemon=True).start()

    go.configure(command=start)
    root.mainloop()


if __name__ == "__main__":
    if any(a.upper() == "/S" for a in sys.argv[1:]):
        sys.exit(silent(sys.argv[1:]))
    wizard()
