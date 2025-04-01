import os
import sys
import time
import requests
import tempfile
import zipfile
import shutil
import subprocess
import logging
import re
import json
from pathlib import Path
import packaging.version as version
import tkinter as tk
from tkinter import messagebox, ttk

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', None)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('updater')


class AutoUpdater:
    def __init__(self, current_version, github_repo, github_token=None, app_root=None):
        self.current_version = current_version
        self.github_repo = "LaceEditing/laces-total-file-converter"
        try:
            from embed_token import GITHUB_TOKEN as embedded_token
            self.github_token = github_token or embedded_token
        except ImportError:
            self.github_token = github_token
        self.app_root = app_root or (os.path.dirname(sys.executable)
                                     if getattr(sys, 'frozen', False)
                                     else os.path.dirname(os.path.abspath(__file__)))
        self.temp_dir = None
        self.download_url = None
        self.latest_version = None
        self.update_ready = False
        self.progress_dialog = None
        self.progress_bar = None
        self.cancel_update = False

    def check_for_updates(self):
        logger.info(f"Checking for updates. Current version: {self.current_version}")
        try:
            owner_repo = self.github_repo  # "LaceEditing/laces-total-file-converter"
            api_url = f"https://api.github.com/repos/{owner_repo}/releases/latest"
            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": f"LacesUpdater/{self.current_version}"
            }
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"

            logger.info(f"Requesting latest release from: {api_url}")

            response = requests.get(api_url, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.error(f"GitHub API returned status code {response.status_code}: {response.text}")
                return False, None, None

            response.raise_for_status()
            release_data = response.json()

            tag = release_data.get("tag_name", "") or release_data.get("name", "")
            if not tag:
                logger.error("No tag_name or name found in release data")
                return False, None, None

            # Remove a leading "v" if present
            if tag.lower().startswith("v"):
                tag = tag[1:]
            latest_version = tag.strip()
            logger.info(f"Latest version on GitHub: {latest_version}")

            current_ver = version.parse(self.current_version)
            latest_ver = version.parse(latest_version) if latest_version else version.parse("0")

            if latest_version and latest_ver > current_ver:
                assets = release_data.get("assets", [])
                if assets:
                    logger.info(f"Found {len(assets)} assets in release:")
                    for asset in assets:
                        logger.info(f"  - {asset.get('name', 'unnamed')}: {asset.get('browser_download_url', 'no URL')}")
                else:
                    logger.error("No assets found in release data")
                    return False, latest_version, None

                zip_asset = None
                for asset in assets:
                    name = asset.get("name", "")
                    if name.lower().endswith(".zip"):
                        zip_asset = asset
                        break

                if zip_asset:
                    self.download_url = zip_asset.get("browser_download_url")
                    logger.info(f"Found update ZIP: {zip_asset.get('name')}")
                    logger.info(f"Download URL: {self.download_url}")
                    self.latest_version = latest_version
                    return True, latest_version, zip_asset.get("name", None)
                else:
                    logger.error("No ZIP asset found in release assets")
                    return False, latest_version, None
            else:
                logger.info(f"No update needed. Current: {current_ver}, Latest: {latest_ver}")
                return False, latest_version, None
        except requests.RequestException as e:
            logger.error(f"Error checking for updates: {e}")
            return False, None, None
        except Exception as e:
            logger.error(f"Unexpected error checking for updates: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, None, None

    def _download_file(self, url, target_path, progress_callback=None):
        try:
            logger.info(f"Attempting to download from: {url}")
            import re
            url_pattern = r"https://github.com/([^/]+)/([^/]+)/releases/download/([^/]+)/(.+)"
            match = re.match(url_pattern, url)

            if not match:
                logger.error(f"Could not parse URL: {url}")
                return self._try_direct_download(url, target_path, progress_callback)

            owner, repo, tag, filename = match.groups()
            logger.info(f"Parsed URL components: owner={owner}, repo={repo}, tag={tag}, filename={filename}")

            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": f"LacesUpdater/{self.current_version}"
            }

            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"
                logger.info("Using authentication token for API access")
            else:
                logger.warning("No GitHub token provided - this will fail for private repositories")
                return False

            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
            logger.info(f"Requesting release info from API: {api_url}")

            response = requests.get(api_url, headers=headers, timeout=30)
            if response.status_code != 200:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return self._try_direct_download(url, target_path, progress_callback)

            release_data = response.json()

            asset_id = None
            browser_download_url = None

            for asset in release_data.get("assets", []):
                asset_name = asset.get("name", "")
                logger.info(f"Found asset: {asset_name}")
                if asset_name == filename:
                    asset_id = asset.get("id")
                    browser_download_url = asset.get("browser_download_url")
                    logger.info(f"Found matching asset with ID: {asset_id}")
                    break

            if not asset_id:
                logger.error(f"Could not find asset matching {filename} in release {tag}")
                return False

            download_url = f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}"
            logger.info(f"Using API endpoint for download: {download_url}")

            download_headers = headers.copy()
            download_headers["Accept"] = "application/octet-stream"

            logger.info("Initiating download...")
            response = requests.get(download_url, headers=download_headers, stream=True, timeout=60)

            if response.status_code != 200:
                logger.error(f"Download request failed: {response.status_code} - {response.text}")
                if browser_download_url:
                    logger.info(f"Trying browser_download_url as fallback: {browser_download_url}")
                    direct_response = requests.get(browser_download_url, headers=headers, stream=True, timeout=60)
                    if direct_response.status_code == 200:
                        return self._save_download_stream(direct_response, target_path, progress_callback)
                return False

            return self._save_download_stream(response, target_path, progress_callback)

        except Exception as e:
            logger.error(f"Error in download process: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _save_download_stream(self, response, target_path, progress_callback=None):
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        downloaded = 0

        try:
            with open(target_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=block_size):
                    if self.cancel_update:
                        logger.info("Update cancelled by user")
                        return False
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size:
                            progress = (downloaded / total_size) * 100
                            progress_callback(progress)
            return True
        except Exception as e:
            logger.error(f"Error saving download: {e}")
            return False

    def _try_direct_download(self, url, target_path, progress_callback=None):
        logger.info(f"Attempting direct download from: {url}")
        try:
            headers = {}
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"
                headers["User-Agent"] = f"LacesUpdater/{self.current_version}"

            response = requests.get(url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            return self._save_download_stream(response, target_path, progress_callback)
        except Exception as e:
            logger.error(f"Direct download failed: {e}")
            return False

    def _create_updater_script(self, update_zip_path):
        updater_path = os.path.join(self.temp_dir, "run_updater.py")

        app_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        app_dir = os.path.dirname(app_path)
        app_name = os.path.basename(app_path)

        user_temp = tempfile.gettempdir()
        log_file = os.path.join(user_temp, "laces_updater_log.txt")

        updater_code = f'''
import os
import sys
import time
import zipfile
import shutil
import subprocess
import logging
import traceback

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=r"{log_file}",
    filemode='w'
)

UPDATE_ZIP = r"{update_zip_path}"
APP_DIR = r"{app_dir}"
APP_PATH = r"{app_path}"
APP_NAME = r"{app_name}"

def main():
    logging.info("Executable replacement updater starting")
    logging.info(f"Current executable: {{APP_PATH}}")
    logging.info(f"Update ZIP: {{UPDATE_ZIP}}")

    time.sleep(3)

    try:
        import tempfile
        extract_dir = tempfile.mkdtemp(prefix="laces_update_")
        logging.info(f"Extracting update to: {{extract_dir}}")

        with zipfile.ZipFile(UPDATE_ZIP, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                logging.info(f"ZIP contains: {{file_info.filename}}")
            zip_ref.extractall(extract_dir)

        new_exe = None
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower().endswith(".exe"):
                    new_exe = os.path.join(root, file)
                    logging.info(f"Found new executable: {{new_exe}}")
                    break
            if new_exe:
                break

        if not new_exe:
            logging.error("No executable found in the update package!")
            return

        backup_path = os.path.join(APP_DIR, f"{{APP_NAME}}.backup")
        logging.info(f"Creating backup: {{backup_path}}")
        try:
            shutil.copy2(APP_PATH, backup_path)
            logging.info("Backup created successfully")
        except Exception as e:
            logging.error(f"Failed to create backup: {{e}}")

        logging.info(f"Replacing {{APP_PATH}} with {{new_exe}}")
        try:
            if os.path.exists(APP_PATH):
                os.remove(APP_PATH)
                logging.info(f"Deleted old executable: {{APP_PATH}}")
            shutil.copy2(new_exe, APP_PATH)
            logging.info("Executable replaced successfully")
        except PermissionError:
            if sys.platform == 'win32':
                logging.info("Permission error encountered - falling back to batch file approach")
                bat_path = os.path.join(extract_dir, "update.bat")
                windows_new_exe = new_exe.replace('/', '\\\\')
                windows_app_path = APP_PATH.replace('/', '\\\\')
                windows_extract_dir = extract_dir.replace('/', '\\\\')
                batch_content = (
                    '@echo off\\n'
                    'echo Waiting for file handles to be released...\\n'
                    'timeout /t 2 /nobreak > nul\\n'
                    'echo Deleting old executable...\\n'
                    f'del /F /Q "{{windows_app_path}}"\\n'
                    'echo Copying new executable...\\n'
                    f'copy /Y "{{windows_new_exe}}" "{{windows_app_path}}"\\n'
                    'echo Starting application...\\n'
                    f'start "" "{{windows_app_path}}"\\n'
                    'echo Cleaning up...\\n'
                    f'rmdir /S /Q "{{windows_extract_dir}}"\\n'
                    'del "%~f0"\\n'
                )
                with open(bat_path, 'w') as bat:
                    bat.write(batch_content)
                logging.info(f"Executing batch file: {{bat_path}}")
                subprocess.Popen(["cmd.exe", "/c", bat_path],
                                 shell=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
                return
            else:
                raise
        logging.info("Starting updated application")
        subprocess.Popen([APP_PATH])
        logging.info("Cleaning up temporary files")
        try:
            shutil.rmtree(extract_dir, ignore_errors=True)
        except Exception as cleanup_error:
            logging.error(f"Cleanup error: {{cleanup_error}}")
        logging.info("Update completed successfully")
    except Exception as e:
        logging.error(f"Error during update: {{e}}")
        logging.error(traceback.format_exc())
        if os.path.exists(backup_path):
            logging.info("Attempting to restore from backup")
            try:
                shutil.copy2(backup_path, APP_PATH)
                logging.info("Restoration completed")
                subprocess.Popen([APP_PATH])
            except Exception as restore_error:
                logging.error(f"Restoration failed: {{restore_error}}")

if __name__ == "__main__":
    main()
'''
        with open(updater_path, 'w') as f:
            f.write(updater_code)
        return updater_path

    def download_update(self, parent_window=None):
        try:
            if not self.download_url:
                logger.error("No download URL available")
                return False

            self.temp_dir = tempfile.mkdtemp(prefix="app_update_")
            download_path = os.path.join(self.temp_dir, f"update_v{self.latest_version}.zip")

            if parent_window:
                self.progress_dialog = tk.Toplevel(parent_window)
                self.progress_dialog.title("Downloading Update")
                self.progress_dialog.geometry("400x150")
                self.progress_dialog.resizable(False, False)
                self.progress_dialog.transient(parent_window)
                self.progress_dialog.grab_set()

                parent_window.update_idletasks()
                x = parent_window.winfo_x() + (parent_window.winfo_width() // 2) - 200
                y = parent_window.winfo_y() + (parent_window.winfo_height() // 2) - 75
                self.progress_dialog.geometry(f"+{x}+{y}")

                tk.Label(self.progress_dialog,
                         text=f"Downloading update v{self.latest_version}...").pack(pady=(20, 10))
                self.progress_bar = ttk.Progressbar(self.progress_dialog,
                                                    length=350, mode="determinate")
                self.progress_bar.pack(pady=10, padx=20)

                cancel_button = tk.Button(self.progress_dialog, text="Cancel",
                                          command=self._cancel_download)
                cancel_button.pack(pady=10)

                def update_progress(progress):
                    if self.progress_bar:
                        self.progress_bar["value"] = progress
                        self.progress_dialog.update_idletasks()

                import threading
                download_thread = threading.Thread(
                    target=self._threaded_download,
                    args=(self.download_url, download_path, update_progress, parent_window)
                )
                download_thread.daemon = True
                download_thread.start()

                self.progress_dialog.wait_window()
                return self.update_ready
            else:
                logger.info(f"Downloading update to {download_path}")
                success = self._download_file(self.download_url, download_path)
                if success:
                    self.update_ready = True
                    self.updater_script_path = self._create_updater_script(download_path)
                    return True
                return False

        except Exception as e:
            logger.error(f"Error downloading update: {e}")
            if self.progress_dialog and self.progress_dialog.winfo_exists():
                self.progress_dialog.destroy()
            return False

    def _threaded_download(self, url, target_path, progress_callback, parent_window):
        logger.info(f"Starting download from: {url}")
        success = self._download_file(url, target_path, progress_callback)
        logger.info(f"Download completed with success={success}")

        if self.cancel_update:
            if self.progress_dialog and self.progress_dialog.winfo_exists():
                self.progress_dialog.destroy()
            return

        if success:
            self.update_ready = True
            self.updater_script_path = self._create_updater_script(target_path)

            if self.progress_dialog and self.progress_dialog.winfo_exists():
                self.progress_dialog.destroy()
                if messagebox.askyesno("Update Ready",
                                       f"Update v{self.latest_version} has been downloaded. Do you want to install it now? The application will restart.",
                                       parent=parent_window):
                    self.install_update(parent_window)
        else:
            if self.progress_dialog and self.progress_dialog.winfo_exists():
                self.progress_dialog.destroy()
            messagebox.showerror("Download Failed",
                                 "Failed to download the update. Please try again later.",
                                 parent=parent_window)

    def _cancel_download(self):
        self.cancel_update = True
        if self.progress_dialog:
            self.progress_dialog.title("Cancelling...")

    def install_update(self, parent_window=None):
        if not self.update_ready or not hasattr(self, 'updater_script_path'):
            logger.error("No update ready to install")
            return False

        try:
            logger.info("Starting the updater script")
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.Popen(self.updater_script_path,
                                 shell=True,
                                 startupinfo=startupinfo)
            else:
                subprocess.Popen(["bash", self.updater_script_path])
            if parent_window:
                parent_window.destroy()
            sys.exit(0)

        except Exception as e:
            logger.error(f"Error installing update: {e}")
            if parent_window:
                messagebox.showerror("Update Failed",
                                     f"Failed to install the update: {str(e)}",
                                     parent=parent_window)
            return False
