import sys
import os
from cx_Freeze import setup, Executable

# On Windows, use Win32GUI to avoid a console window for GUI apps.
base = None
if sys.platform == "win32":
    base = "Win32GUI"

# List of packages used in your application
packages = [
    "os", "sys", "time", "random", "threading", "subprocess", "traceback",
    "logging", "re", "tkinter", "tkinterdnd2", "requests", "packaging", "yt_dlp",
    "pydub", "vlc", "webbrowser", "urllib.parse", "tempfile", "zipfile", "shutil", "json", "pathlib"
]

# Build options for the raw folder build
build_exe_options = {
    "packages": packages,  # Use the packages list defined above
    "include_files": [
        ("assets", "assets"),
        ("ffmpeg.exe", "ffmpeg.exe"),
        ("ffprobe.exe", "ffprobe.exe"),
        ("updater.py", "updater.py"),
    ],
    "include_msvcr": True
}

bdist_msi_options = {
    "upgrade_code": "{12345678-ABCD-4321-DCBA-87654321ABCD}",
    "add_to_path": False,
    "initial_target_dir": r"[ProgramFilesFolder]\LacesTotalFileConverter"
}

executables = [
    Executable("main.py", base="Win32GUI", icon="assets/icons/icon.ico")
]

setup(
    name="Laces-Total-File-Converter",
    version="2.1.1",
    description="Video downloader and file converter",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options
    },
    executables=executables
)