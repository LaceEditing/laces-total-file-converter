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

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('updater')


class AutoUpdater:
    def __init__(self, current_version, itch_api_key, itch_game_id, itch_game_url, app_root=None):
        self.current_version = current_version
        self.itch_api_key = itch_api_key
        self.itch_game_id = itch_game_id
        self.itch_game_url = itch_game_url
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
        """Check if an update is available"""
        logger.info(f"Checking for updates. Current version: {self.current_version}")

        try:
            api_url = f"https://itch.io/api/1/{self.itch_api_key}/game/{self.itch_game_id}/uploads"
            response = requests.get(api_url, headers={"Content-Type": "application/json"}, timeout=10)
            response.raise_for_status()
            uploads_data = response.json()

            if 'uploads' not in uploads_data:
                logger.warning("No uploads found in API response")
                return False, None, None

            latest_upload = max(uploads_data['uploads'], key=lambda x: x.get('created_at', ''))
            filename = latest_upload.get('filename', '')
            version_match = re.search(r'v(\d+\.\d+(?:\.\d+)?)', filename)

            if not version_match:
                logger.warning(f"Couldn't extract version from filename: {filename}")
                return False, None, None

            latest_version = version_match.group(1)
            logger.info(f"Latest version available: {latest_version}")

            current_ver = version.parse(self.current_version)
            latest_ver = version.parse(latest_version)

            # Check if the upload has a direct download URL or we need to auth
            self.download_url = latest_upload.get('download_url')

            if latest_ver > current_ver:
                self.latest_version = latest_version
                return True, latest_version, filename
            return False, latest_version, None

        except requests.RequestException as e:
            logger.error(f"Error checking for updates: {e}")
            return False, None, None
        except Exception as e:
            logger.error(f"Unexpected error checking for updates: {e}")
            return False, None, None

    def _download_file(self, url, target_path, progress_callback=None):
        """Download a file with progress tracking"""
        try:
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            block_size = 8192
            downloaded = 0

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
            logger.error(f"Error downloading file: {e}")
            return False

    def _create_updater_script(self, update_zip_path):
        """Create a Python script that will replace the current executable with the new one"""
        updater_path = os.path.join(self.temp_dir, "run_updater.py")

        app_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        app_dir = os.path.dirname(app_path)

        # Wait for the main app to exit and then extract files
        updater_code = f'''
import os
import sys
import time
import shutil
import zipfile
import subprocess
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='{os.path.join(self.temp_dir, "updater_log.txt")}',
    filemode='w'
)

UPDATE_ZIP = r"{update_zip_path}"
APP_DIR = r"{app_dir}"
APP_PATH = r"{app_path}"

def main():
    logging.info("Updater script starting")

    # Wait for the main process to exit
    time.sleep(2)

    try:
        # Create backup directory
        backup_dir = os.path.join(APP_DIR, "backup_" + str(int(time.time())))
        os.makedirs(backup_dir, exist_ok=True)
        logging.info(f"Created backup directory: {{backup_dir}}")

        # Extract the update to a temp directory
        extract_dir = os.path.join(os.path.dirname(UPDATE_ZIP), "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        logging.info(f"Extracting update to: {{extract_dir}}")

        with zipfile.ZipFile(UPDATE_ZIP, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # Copy files from the extracted directory to the application directory
        logging.info("Copying new files to application directory")
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, extract_dir)
                dst_path = os.path.join(APP_DIR, rel_path)

                # If the file exists, back it up first
                if os.path.exists(dst_path):
                    backup_path = os.path.join(backup_dir, rel_path)
                    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                    shutil.copy2(dst_path, backup_path)

                # Make sure the destination directory exists
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)

                # Copy the new file
                shutil.copy2(src_path, dst_path)

        # Start the updated application
        logging.info("Starting updated application")
        subprocess.Popen([APP_PATH])

        # Clean up
        logging.info("Cleaning up temporary files")
        shutil.rmtree(extract_dir, ignore_errors=True)

        logging.info("Update completed successfully")
    except Exception as e:
        logging.error(f"Error during update: {{e}}")
        # Try to restore from backup in case of failure
        try:
            if 'backup_dir' in locals():
                logging.info("Attempting to restore from backup")
                for root, dirs, files in os.walk(backup_dir):
                    for file in files:
                        src_path = os.path.join(root, file)
                        rel_path = os.path.relpath(src_path, backup_dir)
                        dst_path = os.path.join(APP_DIR, rel_path)
                        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                        shutil.copy2(src_path, dst_path)
                logging.info("Restoration from backup completed")
                subprocess.Popen([APP_PATH])
        except Exception as restore_error:
            logging.error(f"Error restoring from backup: {{restore_error}}")

if __name__ == "__main__":
    main()
'''

        with open(updater_path, 'w') as f:
            f.write(updater_code)

        return updater_path

    def download_update(self, parent_window=None):
        """Download the update package"""
        try:
            if not self.download_url:
                logger.error("No download URL available")
                return False

            # Create a temporary directory for the download
            self.temp_dir = tempfile.mkdtemp(prefix="app_update_")
            download_path = os.path.join(self.temp_dir, f"update_v{self.latest_version}.zip")

            # Show a progress dialog
            if parent_window:
                self.progress_dialog = tk.Toplevel(parent_window)
                self.progress_dialog.title("Downloading Update")
                self.progress_dialog.geometry("400x150")
                self.progress_dialog.resizable(False, False)
                self.progress_dialog.transient(parent_window)
                self.progress_dialog.grab_set()

                # Center the dialog
                parent_window.update_idletasks()
                x = parent_window.winfo_x() + (parent_window.winfo_width() // 2) - 200
                y = parent_window.winfo_y() + (parent_window.winfo_height() // 2) - 75
                self.progress_dialog.geometry(f"+{x}+{y}")

                # Add progress elements
                tk.Label(self.progress_dialog,
                         text=f"Downloading update v{self.latest_version}...").pack(pady=(20, 10))
                self.progress_bar = ttk.Progressbar(self.progress_dialog,
                                                    length=350, mode="determinate")
                self.progress_bar.pack(pady=10, padx=20)

                # Add cancel button
                cancel_button = tk.Button(self.progress_dialog, text="Cancel",
                                          command=self._cancel_download)
                cancel_button.pack(pady=10)

                def update_progress(progress):
                    if self.progress_bar:
                        self.progress_bar["value"] = progress
                        self.progress_dialog.update_idletasks()

                # Start download in a separate thread
                import threading
                download_thread = threading.Thread(
                    target=self._threaded_download,
                    args=(self.download_url, download_path, update_progress, parent_window)
                )
                download_thread.daemon = True
                download_thread.start()

                # Wait for the download to complete or be cancelled
                self.progress_dialog.wait_window()
                return self.update_ready
            else:
                # No GUI mode
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
        """Handle downloading in a separate thread"""
        success = self._download_file(url, target_path, progress_callback)

        if self.cancel_update:
            if self.progress_dialog and self.progress_dialog.winfo_exists():
                self.progress_dialog.destroy()
            return

        if success:
            self.update_ready = True
            self.updater_script_path = self._create_updater_script(target_path)

            if self.progress_dialog and self.progress_dialog.winfo_exists():
                self.progress_dialog.destroy()

                # Ask the user if they want to install now
                if messagebox.askyesno("Update Ready",
                                       f"Update v{self.latest_version} has been downloaded. "
                                       f"Do you want to install it now? "
                                       f"The application will restart.",
                                       parent=parent_window):
                    self.install_update(parent_window)
        else:
            if self.progress_dialog and self.progress_dialog.winfo_exists():
                self.progress_dialog.destroy()
            messagebox.showerror("Download Failed",
                                 "Failed to download the update. Please try again later.",
                                 parent=parent_window)

    def _cancel_download(self):
        """Cancel the download process"""
        self.cancel_update = True
        if self.progress_dialog:
            self.progress_dialog.title("Cancelling...")

    def install_update(self, parent_window=None):
        """Install the downloaded update"""
        if not self.update_ready or not hasattr(self, 'updater_script_path'):
            logger.error("No update ready to install")
            return False

        try:
            # Run the updater script
            logger.info("Starting the updater script")
            if sys.platform == 'win32':
                # Hide console window
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.Popen([sys.executable, self.updater_script_path],
                                 startupinfo=startupinfo)
            else:
                subprocess.Popen([sys.executable, self.updater_script_path])

            # Close the application to allow the updater to replace files
            if parent_window:
                parent_window.destroy()

            # Exit the application
            sys.exit(0)

        except Exception as e:
            logger.error(f"Error installing update: {e}")
            if parent_window:
                messagebox.showerror("Update Failed",
                                     f"Failed to install the update: {str(e)}",
                                     parent=parent_window)
            return False