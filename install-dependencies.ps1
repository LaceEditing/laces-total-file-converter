# install-dependencies.ps1
# This script installs all necessary libraries for main.py.

# Upgrade pip to ensure the latest version is used
Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

# List of required packages
$packages = @(
    "requests",      # For HTTP requests
    "packaging",     # For version parsing
    "yt-dlp",        # For downloading videos
    "pydub",         # For audio processing
    "tkinterdnd2",   # For drag-and-drop support in Tkinter
    "python-vlc"     # For video playback using VLC
)

# Install each package
foreach ($pkg in $packages) {
    Write-Host "Installing $pkg..."
    python -m pip install $pkg
}

Write-Host "All dependencies have been installed successfully."
