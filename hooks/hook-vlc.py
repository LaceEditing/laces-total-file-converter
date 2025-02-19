from PyInstaller.utils.hooks import collect_dynamic_libs
import os
import sys

binaries = []
vlc_path = r"C:\Program Files\VideoLAN\VLC"

# Core VLC DLLs
core_dlls = ['libvlc.dll', 'libvlccore.dll', 'npvlc.dll', 'axvlc.dll']
for dll in core_dlls:
    dll_path = os.path.join(vlc_path, dll)
    if os.path.exists(dll_path):
        binaries.append((dll_path, '.'))

# Plugin directories to include
plugin_dirs = ['plugins', 'lua']
for plugin_dir in plugin_dirs:
    dir_path = os.path.join(vlc_path, plugin_dir)
    if os.path.exists(dir_path):
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                if file.endswith('.dll'):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(root, vlc_path)
                    binaries.append((full_path, rel_path))

datas = []
# Include VLC data directories
data_dirs = ['locale', 'skins']
for data_dir in data_dirs:
    dir_path = os.path.join(vlc_path, data_dir)
    if os.path.exists(dir_path):
        datas.append((dir_path, data_dir))