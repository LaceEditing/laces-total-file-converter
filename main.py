import os
import re
import sys
import time
import random
import threading
import subprocess
from urllib.parse import urlparse
import traceback
import logging
import json
from pathlib import Path
import shutil
from contextlib import contextmanager
import tempfile
import functools
from typing import Dict, Any, List, Optional, Tuple

import requests
import webbrowser
import packaging.version as version
import yt_dlp
from pydub import AudioSegment

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter import font as tkFont, PhotoImage, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

import vlc

# Configure logging
logging.basicConfig(level=logging.INFO)

# Application Constants
CURRENT_VERSION = "2.4.2"
ITCH_GAME_URL = "https://laceediting.itch.io/laces-total-file-converter"
MAX_RECENT_FOLDERS = 5
SETTINGS_FILE = "app_settings.json"

# UI Constants
WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 875
WINDOW_DEFAULT_WIDTH = 700
WINDOW_DEFAULT_HEIGHT = 550
PROGRESS_UPDATE_INTERVAL = 2000

# Media Constants
AUDIO_FORMATS = ["wav", "ogg", "flac", "mp3", "m4a"]
VIDEO_FORMATS = ["mp4", "avi", "mov", "mkv", "webm", "flv"]
DEFAULT_BITRATE = "192k"
NOTIFICATION_DURATION = 3

# Messages
MSG_SELECT_INPUT = "Please select input files."
MSG_SELECT_OUTPUT = "Please select an output folder."
MSG_INVALID_FORMAT = "Please select a valid output format."
MSG_AUDIO_TO_VIDEO_ERROR = "Converting an audio file to a video file is literally not a thing."

# Platform-specific setup for Windows DLL loading
if sys.version_info >= (3, 8) and os.name == 'nt':
    if hasattr(os, 'add_dll_directory'):
        if getattr(sys, 'frozen', False):
            os.add_dll_directory(os.path.dirname(sys.executable))
        else:
            os.add_dll_directory(os.path.abspath('.'))


class AppState:
    """Centralized application state management"""

    def __init__(self):
        # UI Elements
        self.app = None
        self.input_entry = None
        self.output_folder_entry = None
        self.youtube_link_entry = None
        self.format_dropdown = None
        self.convert_button = None
        self.gpu_checkbox = None
        self.youtube_status_label = None
        self.youtube_quality_dropdown = None
        self.progress_frame = None
        self.recent_folders_menu = None

        # Variables
        self.gpu_var = None
        self.format_var = None
        self.progress_var = None
        self.youtube_format_var = None
        self.youtube_quality_var = None

        # Fonts
        self.regular_font = None
        self.title_font = None

        # Easter egg
        self.bad_apple_overlay = None

        # Download tracking
        self.playlist_current_index = 0
        self.playlist_total_count = 0
        self.download_started_time = None

        # Managers
        self.settings_manager = None
        self.download_manager = None

    def reset_download_tracking(self):
        """Reset download tracking variables"""
        self.playlist_current_index = 0
        self.playlist_total_count = 0
        self.download_started_time = None


class VLCManager:
    """Manages VLC instances for better performance"""
    _instance = None
    _video_player = None
    _audio_player = None

    @classmethod
    def get_instance(cls):
        """Get or create the singleton VLC instance"""
        if cls._instance is None:
            try:
                cls._instance = vlc.Instance("--no-video-ui --quiet")
                logging.info("VLC instance created")
            except Exception as e:
                logging.error(f"Failed to create VLC instance: {e}")
                cls._instance = None
        return cls._instance

    @classmethod
    def get_video_player(cls):
        """Get or create a video player"""
        instance = cls.get_instance()
        if instance and cls._video_player is None:
            cls._video_player = instance.media_player_new()
        return cls._video_player

    @classmethod
    def get_audio_player(cls):
        """Get or create an audio player"""
        instance = cls.get_instance()
        if instance and cls._audio_player is None:
            cls._audio_player = instance.media_player_new()
        return cls._audio_player

    @classmethod
    def cleanup(cls):
        """Clean up VLC resources"""
        if cls._video_player:
            cls._video_player.stop()
            cls._video_player.release()
        if cls._audio_player:
            cls._audio_player.stop()
            cls._audio_player.release()
        cls._instance = None
        cls._video_player = None
        cls._audio_player = None


class SettingsManager:
    """Manages application settings with validation and error handling"""

    DEFAULT_SETTINGS = {
        "recent_folders": [],
        "default_format": "mp4",
        "use_gpu": True,
        "max_recent_folders": 5,
        "auto_check_updates": True,
        "notification_volume": 0.7
    }

    def __init__(self, settings_file: str = SETTINGS_FILE):
        self.settings_file = Path(get_absolute_path(settings_file))
        self._settings = self.load()

    def load(self) -> Dict[str, Any]:
        """Load settings with validation"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    loaded_settings = json.load(f)

                # Validate and merge with defaults
                settings = self.DEFAULT_SETTINGS.copy()
                for key, value in loaded_settings.items():
                    if key in settings and type(value) == type(settings[key]):
                        settings[key] = value
                    else:
                        logging.warning(f"Invalid setting ignored: {key}={value}")

                return settings
        except Exception as e:
            logging.error(f"Error loading settings: {e}")

        return self.DEFAULT_SETTINGS.copy()

    def save(self) -> bool:
        """Save settings with error handling"""
        try:
            # Create backup
            if self.settings_file.exists():
                backup_file = self.settings_file.with_suffix('.json.bak')
                shutil.copy2(self.settings_file, backup_file)

            # Write settings
            with open(self.settings_file, 'w') as f:
                json.dump(self._settings, f, indent=4)

            return True
        except Exception as e:
            logging.error(f"Error saving settings: {e}")
            # Try to restore backup
            backup_file = self.settings_file.with_suffix('.json.bak')
            if backup_file.exists():
                try:
                    shutil.copy2(backup_file, self.settings_file)
                except:
                    pass
            return False

    def get(self, key: str, default=None):
        """Get a setting value"""
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        """Set a setting value with validation"""
        if key in self.DEFAULT_SETTINGS:
            expected_type = type(self.DEFAULT_SETTINGS[key])
            if type(value) == expected_type:
                self._settings[key] = value
                return self.save()
            else:
                logging.error(f"Type mismatch for setting {key}: expected {expected_type}, got {type(value)}")
        return False

    def add_recent_folder(self, folder: str) -> bool:
        """Add a folder to recent folders list"""
        if not os.path.isdir(folder):
            return False

        recent = self._settings.get("recent_folders", [])
        max_recent = self._settings.get("max_recent_folders", 5)

        # Remove if already exists
        if folder in recent:
            recent.remove(folder)

        # Add to beginning
        recent.insert(0, folder)

        # Limit size
        self._settings["recent_folders"] = recent[:max_recent]

        return self.save()

    def clear_recent_folders(self) -> bool:
        """Clear all recent folders"""
        self._settings["recent_folders"] = []
        return self.save()


class DownloadManager:
    """Thread-safe download management"""

    def __init__(self):
        self._active_downloads = {}
        self._lock = threading.Lock()

    def start_download(self, url: str, thread_id=None):
        """Register a download"""
        with self._lock:
            if thread_id is None:
                thread_id = threading.current_thread().ident
            self._active_downloads[thread_id] = {
                'url': url,
                'start_time': time.time(),
                'status': 'active'
            }

    def end_download(self, thread_id=None):
        """Mark download as complete"""
        with self._lock:
            if thread_id is None:
                thread_id = threading.current_thread().ident
            if thread_id in self._active_downloads:
                del self._active_downloads[thread_id]

    def cancel_all_downloads(self):
        """Cancel all active downloads"""
        with self._lock:
            for thread_id in self._active_downloads:
                self._active_downloads[thread_id]['status'] = 'cancelled'

    @property
    def active_count(self):
        """Get number of active downloads"""
        with self._lock:
            return len(self._active_downloads)


# Create global app state instance
app_state = AppState()


# Error handling decorator
def handle_errors(default_return=None, show_messagebox=True):
    """Decorator for consistent error handling"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = f"Error in {func.__name__}: {str(e)}"
                logging.error(error_msg)
                logging.error(traceback.format_exc())

                if show_messagebox and app_state.app:
                    safe_update_ui(lambda: messagebox.showerror(
                        "Error",
                        f"An error occurred: {str(e)}\n\nCheck error_log.txt for details.",
                        parent=app_state.app
                    ))

                return default_return

        return wrapper

    return decorator


# Utility functions
def log_errors():
    """Log errors to file"""
    with open("error_log.txt", "w") as f:
        f.write(traceback.format_exc())


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)


def get_absolute_path(relative_path: str) -> str:
    """Get absolute path to file that needs to be written to"""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def safe_update_ui(func) -> None:
    """Safely execute UI updates on the main thread"""
    if callable(func) and app_state.app:
        app_state.app.after(0, func)
    else:
        logging.error(f"safe_update_ui received non-callable: {type(func)}")


def file_exists_safe(filepath: str) -> bool:
    """Check if file exists with error handling"""
    try:
        return os.path.exists(filepath) and os.path.isfile(filepath)
    except Exception as e:
        logging.error(f"Error checking file existence: {e}")
        return False


def show_error(title: str, message: str, parent=None):
    """Show error message with logging"""
    logging.error(f"{title}: {message}")
    safe_update_ui(lambda: messagebox.showerror(title, message, parent=parent or app_state.app))


@contextmanager
def temporary_directory(prefix="laces_temp_"):
    """Context manager for temporary directories with cleanup"""
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        yield temp_dir
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                logging.error(f"Failed to clean up temp directory: {e}")


# FFmpeg handling
def get_ffmpeg_path() -> str:
    """Get the path to FFmpeg executable"""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
        ffmpeg_path = os.path.join(base_path, 'ffmpeg.exe')
        if not os.path.exists(ffmpeg_path):
            logging.error(f"FFmpeg not found at {ffmpeg_path}")
            ffmpeg_path = resource_path('ffmpeg.exe')
            if not os.path.exists(ffmpeg_path):
                raise FileNotFoundError("FFmpeg executable not found in application bundle")
        return ffmpeg_path
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        ffmpeg_path = os.path.join(base_path, 'dist', 'ffmpeg', 'bin', 'ffmpeg.exe')
        if not os.path.exists(ffmpeg_path):
            ffmpeg_path = os.path.join(base_path, 'ffmpeg.exe')
            if not os.path.exists(ffmpeg_path):
                from shutil import which
                system_ffmpeg = which('ffmpeg.exe')
                if system_ffmpeg:
                    return system_ffmpeg
                raise FileNotFoundError("FFmpeg not found in expected development location or system PATH.")
        return ffmpeg_path


def initialize_ffmpeg_paths() -> Tuple[str, str]:
    """Initialize FFmpeg and FFprobe paths"""
    try:
        ffmpeg_path = get_ffmpeg_path()
        if getattr(sys, 'frozen', False):
            ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe')
            if not os.path.exists(ffprobe_path):
                ffprobe_path = resource_path('ffprobe.exe')
        else:
            if sys.platform == 'win32':
                from shutil import which
                ffprobe_path = which('ffprobe.exe')
                if not ffprobe_path:
                    ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe')
                    if not os.path.exists(ffprobe_path):
                        raise FileNotFoundError("FFprobe not found in PATH")
            else:
                ffprobe_path = "ffprobe"

        if not os.path.exists(ffmpeg_path):
            raise FileNotFoundError(f"FFmpeg not found at: {ffmpeg_path}")
        if sys.platform == 'win32' and not os.path.exists(ffprobe_path):
            raise FileNotFoundError(f"FFprobe not found at: {ffprobe_path}")

        AudioSegment.converter = ffmpeg_path
        AudioSegment.ffmpeg = ffmpeg_path
        AudioSegment.ffprobe = ffprobe_path

        return ffmpeg_path, ffprobe_path
    except Exception:
        raise


# Initialize FFmpeg at module level
try:
    FFMPEG_PATH = get_ffmpeg_path()
    subprocess.run([FFMPEG_PATH, "-version"], check=True, capture_output=True)
except Exception as e:
    logging.error(f"Error initializing FFmpeg: {e}")
    FFMPEG_PATH = None


# Audio notification functions
def get_notification_sound_path() -> Optional[str]:
    """Get path to the notification sound file"""
    sound_path = resource_path(os.path.join("assets", "sounds", "notification.mp3"))

    if os.path.exists(sound_path):
        return sound_path

    # Check alternate locations
    alt_paths = [
        resource_path(os.path.join("assets", "notification.mp3")),
        resource_path(os.path.join("assets", "complete.mp3"))
    ]

    for path in alt_paths:
        if os.path.exists(path):
            return path

    logging.warning("Notification sound file not found")
    return None


@handle_errors(default_return=False, show_messagebox=False)
def play_notification(audio_path: Optional[str] = None, duration: int = NOTIFICATION_DURATION) -> bool:
    """Play an audio notification when operations complete"""
    try:
        # Get the VLC instance first
        instance = VLCManager.get_instance()
        if not instance:
            logging.error("Could not get VLC instance for notification")
            return False

        # Use provided path or default notification sound
        if audio_path is None:
            audio_path = get_notification_sound_path()
            if not audio_path:
                logging.error("No notification sound path found")
                return False

        # Create a new player for each notification to avoid conflicts
        player = instance.media_player_new()

        # Create and set the media
        media = instance.media_new(audio_path)
        player.set_media(media)

        # Set volume (0-100)
        player.audio_set_volume(70)

        # Play the notification
        player.play()
        logging.info(f"Playing audio notification: {audio_path}")

        # Stop after duration and clean up
        def stop_and_cleanup():
            time.sleep(duration)
            player.stop()
            player.release()
            logging.info("Audio notification playback ended")

        threading.Thread(target=stop_and_cleanup, daemon=True).start()
        return True

    except Exception as e:
        logging.error(f"Error playing audio notification: {e}")
        return False


class VLCManager:
    """Manages VLC instances for better performance"""
    _instance = None
    _video_player = None

    # Remove _audio_player = None

    @classmethod
    def get_instance(cls):
        """Get or create the singleton VLC instance"""
        if cls._instance is None:
            try:
                # Remove --no-video-ui flag as it might interfere with audio
                cls._instance = vlc.Instance("--quiet")
                logging.info("VLC instance created")
            except Exception as e:
                logging.error(f"Failed to create VLC instance: {e}")
                cls._instance = None
        return cls._instance

    @classmethod
    def get_video_player(cls):
        """Get or create a video player"""
        instance = cls.get_instance()
        if instance and cls._video_player is None:
            cls._video_player = instance.media_player_new()
        return cls._video_player

    # Remove get_audio_player method since we're creating new players for each notification

    @classmethod
    def cleanup(cls):
        """Clean up VLC resources"""
        if cls._video_player:
            cls._video_player.stop()
            cls._video_player.release()
        cls._instance = None
        cls._video_player = None

def initialize_audio_system():
    """Initialize the audio system by testing VLC"""
    try:
        # Test VLC instance creation
        instance = VLCManager.get_instance()
        if instance:
            logging.info("Audio system initialized successfully")
            # Pre-load the notification sound path to verify it exists
            sound_path = get_notification_sound_path()
            if sound_path:
                logging.info(f"Notification sound found at: {sound_path}")
            else:
                logging.warning("No notification sound file found")
        else:
            logging.error("Failed to initialize audio system")
    except Exception as e:
        logging.error(f"Error initializing audio system: {e}")


# Update checking functions
@handle_errors(default_return=False)
def check_for_updates() -> bool:
    """Check for updates from itch.io"""
    try:
        safe_update_ui(lambda: app_state.youtube_status_label.config(text="Checking for updates..."))

        response = requests.get(ITCH_GAME_URL, timeout=10)
        if response.status_code == 200:
            page_content = response.text

            # Look for version pattern in download files
            version_pattern = r'Laces_Total_File_Converter_v(\d+\.\d+\.\d+)'
            matches = re.findall(version_pattern, page_content)

            if matches:
                available_versions = [version.parse(v) for v in matches]
                latest_version = max(available_versions)
                current_ver = version.parse(CURRENT_VERSION)

                if latest_version > current_ver:
                    update_message = f"""A new version ({latest_version}) is available!
You're currently running version {CURRENT_VERSION}

Would you like to visit the download page?"""
                    if messagebox.askyesno("Update Available", update_message, parent=app_state.app):
                        handle_manual_update()
                    return True

            safe_update_ui(lambda: app_state.youtube_status_label.config(
                text="You're running the latest version! Good job! ^.-"))
            return False
        else:
            logging.error(f"Failed to fetch itch.io page: {response.status_code}")
            safe_update_ui(lambda: app_state.youtube_status_label.config(text="Update check unavailable"))
            return False

    except Exception as e:
        logging.error(f"Update check error: {e}")
        safe_update_ui(lambda: app_state.youtube_status_label.config(text="Update check failed"))
        return False
    finally:
        app_state.app.after(3000, lambda: safe_update_ui(
            lambda: app_state.youtube_status_label.config(text="Download Status: Idle")))


def handle_manual_update() -> None:
    """Open the Itch.io page for manual download"""
    try:
        webbrowser.open(ITCH_GAME_URL)
        messagebox.showinfo("Manual Update", "Opening download page in your browser.", parent=app_state.app)
    except Exception as e:
        show_error("Update Error", f"Failed to open download page: {str(e)}")


def setup_auto_update_checker() -> None:
    """Schedule periodic update checks"""
    # First check after 1 second
    app_state.app.after(1000, check_for_updates)

    # Schedule daily checks (86400000 ms = 24 hours)
    def schedule_next_check():
        check_for_updates()
        app_state.app.after(86400000, schedule_next_check)

    # Schedule check every 24 hours
    app_state.app.after(86400000, schedule_next_check)


def show_about() -> None:
    """Show about dialog"""
    messagebox.showinfo(
        "About",
        f"Lace's Total File Converter v{CURRENT_VERSION}\n\n"
        "A friendly file converter for all your media needs!\n\n"
        "Created with ♥ by Lace",
        parent=app_state.app
    )


# Video playback functions
def verify_video_setup():
    """Verify video playback setup"""
    logging.info("Verifying video playback setup")
    paths_to_check = {
        'Video file': resource_path(os.path.join("assets", "BaddAscle.mp4")),
        'FFmpeg': get_ffmpeg_path(),
        'Assets directory': resource_path("assets")
    }
    for name, path in paths_to_check.items():
        exists = os.path.exists(path)
        logging.info(f"{name} path check: {path} - {'EXISTS' if exists else 'MISSING'}")


@handle_errors(show_messagebox=True)
def show_bad_apple_easter_egg():
    """Show Bad Apple easter egg video"""
    video_path = resource_path(os.path.join("assets", "BaddAscle.mp4"))
    logging.info(f"Verifying video at: {video_path}")

    if not os.path.exists(video_path):
        logging.error(f"Video file not found at expected path: {video_path}")
        show_error("Easter Egg Error",
                   "Video file not found or inaccessible. Please verify application installation.")
        return

    logging.info(f"Preparing to play video from: {video_path}")
    show_vlc_overlay(video_path, duration=13)


def show_vlc_overlay(video_path: str, duration: int = 11):
    """Show video overlay using VLC"""
    overlay = tk.Frame(app_state.app, bg="black")
    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
    overlay.lift()
    app_state.bad_apple_overlay = overlay

    video_frame = tk.Frame(overlay, bg="black")
    video_frame.pack(expand=True, fill="both")

    try:
        player = VLCManager.get_video_player()
        if not player:
            raise Exception("Could not create video player")

        instance = VLCManager.get_instance()
        if not instance:
            raise Exception("Could not get VLC instance")

        video_frame.update_idletasks()
        hwnd = video_frame.winfo_id()
        player.set_hwnd(hwnd)

        media = instance.media_new(video_path)
        player.set_media(media)
        player.play()
        logging.info(f"Starting VLC playback for {video_path}")

        def cover_video():
            try:
                media.parse()
                tracks = media.get_tracks_info()
                if not tracks:
                    return
                container_w = video_frame.winfo_width()
                container_h = video_frame.winfo_height()
                player.video_set_scale(0)
                player.video_set_aspect_ratio(f"{container_w}:{container_h}")
                player.set_hwnd(video_frame.winfo_id())
                logging.info(f"Video container dimensions: {container_w}x{container_h}")
            except Exception as e:
                logging.error(f"Error adjusting video scaling: {e}")

        overlay.after(500, cover_video)

        def close_overlay():
            time.sleep(duration)
            player.stop()
            overlay.destroy()
            logging.info("VLC playback ended; overlay destroyed.")

        threading.Thread(target=close_overlay, daemon=True).start()
    except Exception as e:
        logging.error(f"Error in VLC playback: {e}")
        show_error("Video Error", "Could not play video. Check error_log.txt for details.")
        if overlay:
            overlay.destroy()


# File handling utilities
def safe_filename(filepath: str) -> str:
    """Ensure filename is safe for the filesystem"""
    import string
    allowed_chars = string.ascii_letters + string.digits + " ._-()"
    directory, filename = os.path.split(filepath)
    base, ext = os.path.splitext(filename)
    safe_base = ''.join(ch if ch in allowed_chars else '_' for ch in base)

    if not safe_base:
        safe_base = "file"

    safe_name = safe_base + ext
    if safe_name != filename:
        new_path = os.path.join(directory, safe_name)
        count = 1
        while os.path.exists(new_path):
            new_path = os.path.join(directory, f"{safe_base}_{count}{ext}")
            count += 1
        try:
            os.rename(filepath, new_path)
            return new_path
        except PermissionError:
            return filepath
    return filepath


# URL validation
def is_valid_url(input_url: str) -> bool:
    """Check if URL is from a supported platform"""
    supported_domains = [
        'youtube.com', 'youtu.be',
        'music.youtube.com',
        'twitter.com', 'x.com',
        'tiktok.com',
        'dailymotion.com', 'dai.ly',
        'vimeo.com',
        'instagram.com/reels', 'instagram.com/reel',
        'twitch.tv',
        'facebook.com', 'fb.watch',
        'soundcloud.com', 'snd.sc',
        'bandcamp.com',
        'reddit.com',
        'ok.ru',
        'rumble.com'
    ]
    try:
        parsed_url = urlparse(input_url)
        cleaned_path = parsed_url.path.split('?')[0].lower()
        netloc = parsed_url.netloc.lower()
        return any(domain in (netloc + cleaned_path) for domain in supported_domains)
    except Exception:
        return False


def validate_url(url: str) -> bool:
    """Validate URL format and content"""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url:
        return False
    return is_valid_url(url)


# Media conversion classes and functions
class MediaConverter:
    """Handles media file conversions"""

    def __init__(self, ffmpeg_path: str):
        self.ffmpeg_path = ffmpeg_path

    def validate_conversion(self, input_format: str, output_format: str) -> Tuple[bool, Optional[str]]:
        """Validate if conversion is allowed"""
        if input_format in AUDIO_FORMATS and output_format in VIDEO_FORMATS:
            return False, MSG_AUDIO_TO_VIDEO_ERROR
        return True, None

    def check_video_has_audio(self, input_path: str) -> bool:
        """Check if video file contains audio stream"""
        probe_cmd = [self.ffmpeg_path, "-i", input_path, "-hide_banner"]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, check=False)
        return "Stream #0" in probe_result.stderr and "Audio:" in probe_result.stderr

    def get_audio_conversion_args(self, output_format: str) -> List[str]:
        """Get FFmpeg arguments for audio conversion"""
        args_map = {
            "mp3": ["-acodec", "libmp3lame", "-q:a", "2", "-b:a", DEFAULT_BITRATE],
            "ogg": ["-acodec", "libvorbis", "-q:a", "6"],
            "flac": ["-acodec", "flac"],
            "wav": ["-acodec", "pcm_s16le"],
            "m4a": ["-acodec", "aac", "-b:a", DEFAULT_BITRATE]
        }
        return args_map.get(output_format, [])

    def convert_single_file(self, input_path: str, output_path: str,
                            input_format: str, output_format: str, use_gpu: bool) -> bool:
        """Convert a single file"""
        try:
            # Video to Video
            if input_format in VIDEO_FORMATS and output_format in VIDEO_FORMATS:
                direct_ffmpeg_gpu_video2video(input_path, output_path, output_format, use_gpu)
                return True

            # Build FFmpeg command
            ffmpeg_cmd = [self.ffmpeg_path, "-i", input_path, "-y"]

            # Video to Audio
            if input_format in VIDEO_FORMATS and output_format in AUDIO_FORMATS:
                if not self.check_video_has_audio(input_path):
                    raise ValueError("Video file has no audio track")
                ffmpeg_cmd.append("-vn")  # No video

            # Add format-specific arguments
            ffmpeg_cmd.extend(self.get_audio_conversion_args(output_format))
            ffmpeg_cmd.append(output_path)

            # Execute conversion
            if sys.platform == 'win32':
                subprocess.run(ffmpeg_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
                               capture_output=True, text=True)
            else:
                subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)

            return True

        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg conversion failed: {e}")
            raise
        except Exception as e:
            logging.error(f"Conversion error: {e}")
            raise


def direct_ffmpeg_gpu_video2video(input_path: str, output_path: str,
                                  output_format: str, use_gpu: bool) -> None:
    """Direct video to video conversion with optional GPU acceleration"""
    try:
        ffmpeg_path = get_ffmpeg_path()
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Special handling for WebM
        if output_format.lower() == "webm":
            cpu_cmd = [ffmpeg_path, "-i", input_path,
                       "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0",
                       "-c:a", "libopus", "-b:a", "128k",
                       "-y", output_path]
            subprocess.run(cpu_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return

        # Try GPU acceleration first
        if use_gpu:
            gpu_cmd = None
            if output_format.lower() == "avi":
                gpu_cmd = [ffmpeg_path, "-hwaccel", "cuda", "-i", input_path,
                           "-c:v", "mpeg4", "-q:v", "5", "-c:a", "mp3", "-y", output_path]
            elif output_format.lower() == "flv":
                gpu_cmd = [ffmpeg_path, "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
                           "-i", input_path, "-c:v", "h264_nvenc", "-preset", "p1",
                           "-profile:v", "main", "-level", "3.1",
                           "-b:v", "2M", "-maxrate", "2.5M", "-bufsize", "4M",
                           "-c:a", "aac", "-b:a", "128k",
                           "-f", "flv", "-y", output_path]
            else:
                # Default GPU handling for MP4, MKV, etc.
                gpu_cmd = [ffmpeg_path, "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
                           "-i", input_path, "-c:v", "h264_nvenc", "-preset", "p1", "-tune", "hq",
                           "-rc", "vbr", "-cq", "23", "-b:v", "0", "-maxrate", "130M",
                           "-bufsize", "130M", "-spatial-aq", "1", "-c:a", "aac", "-b:a", DEFAULT_BITRATE,
                           "-y", output_path]

            if gpu_cmd:
                try:
                    subprocess.run(gpu_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    return
                except subprocess.CalledProcessError:
                    logging.info(f"GPU acceleration failed for {output_format}, falling back to CPU")

        # CPU fallback paths
        if output_format.lower() == "avi":
            cpu_cmd = [ffmpeg_path, "-i", input_path,
                       "-c:v", "mpeg4", "-q:v", "5", "-c:a", "mp3", "-y", output_path]
        elif output_format.lower() == "flv":
            cpu_cmd = [ffmpeg_path, "-i", input_path,
                       "-c:v", "libx264", "-profile:v", "main", "-level", "3.1",
                       "-preset", "medium", "-crf", "23",
                       "-c:a", "aac", "-b:a", "128k",
                       "-f", "flv", "-y", output_path]
        else:
            cpu_cmd = [ffmpeg_path, "-i", input_path,
                       "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                       "-c:a", "aac", "-b:a", DEFAULT_BITRATE,
                       "-y", output_path]

        subprocess.run(cpu_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        raise


def punish_user_with_maths() -> bool:
    """Educational prompt for invalid conversion attempts"""
    result = [False]

    def show_math_dialog():
        messagebox.showinfo("WOAH THERE HOLD YOUR HORSES FRIEND",
                            MSG_AUDIO_TO_VIDEO_ERROR +
                            " Ok, let's test your brain.",
                            parent=app_state.app)
        while True:
            a = random.randint(1, 10)
            b = random.randint(1, 10)
            question = f"Solve this: {a} + {b} = ?"
            user_answer = simpledialog.askinteger("The clock is ticking...", question, parent=app_state.app)

            if user_answer is None:
                messagebox.showinfo("bruh...", "lmao ok sorry it's too hard for you.", parent=app_state.app)
                app_state.app.destroy()
                return

            if user_answer == a + b:
                messagebox.showinfo("Finally.", "That was so hard? Now don't ever do that again.", parent=app_state.app)
                result[0] = True
                return
            else:
                retry = messagebox.askretrycancel("Dude....", "Seriously..? It's basic addition.", parent=app_state.app)
                if not retry:
                    messagebox.showinfo("bruh...", "ok bye", parent=app_state.app)
                    app_state.app.destroy()
                    return

    app_state.app.after(0, show_math_dialog)
    while app_state.app.winfo_exists():
        app_state.app.update()
        if result[0]:
            return True
        time.sleep(0.1)
    return False


def convert_audio(input_paths: List[str], output_folder: str, output_format: str,
                  progress_var: tk.IntVar, convert_button: tk.Button, use_gpu: bool) -> None:
    """Main conversion function"""
    try:
        # Initialize converter
        ffmpeg_path, _ = initialize_ffmpeg_paths()
        converter = MediaConverter(ffmpeg_path)
        os.makedirs(output_folder, exist_ok=True)

        # Setup UI updates
        def update_button(text: str, bg: str = "#D8BFD8"):
            safe_update_ui(lambda: convert_button.config(text=text, bg=bg, fg="white"))

        def update_status(text: str):
            safe_update_ui(lambda: app_state.youtube_status_label.config(text=text))

        update_button("Converting...")
        total_files = len(input_paths)
        warned = False

        # Process each file
        for idx, original_path in enumerate(input_paths, start=1):
            try:
                input_path = safe_filename(original_path)
                file_name = os.path.basename(input_path)
                file_base, file_ext = os.path.splitext(file_name)
                input_format = file_ext[1:].lower()
                output_path = os.path.join(output_folder, f"{file_base}.{output_format}")

                update_status(f"Converting file {idx}/{total_files}: {file_name}")

                # Validate conversion
                valid, error_msg = converter.validate_conversion(input_format, output_format)
                if not valid:
                    if error_msg == MSG_AUDIO_TO_VIDEO_ERROR:
                        update_button("Convert", "#9370DB")
                        if not punish_user_with_maths():
                            return
                        update_button("Convert", "#9370DB")
                        return
                    else:
                        show_error("Conversion Error", error_msg)
                        return

                # WebM warning
                if input_format in VIDEO_FORMATS and output_format == "webm" and not warned:
                    answer = messagebox.askyesnocancel(
                        "Warning",
                        "Converting a video to WebM using VP9 may take a very long time. Do you want to proceed?",
                        parent=app_state.app
                    )
                    if answer is None or not answer:
                        return
                    warned = True

                # Convert file
                converter.convert_single_file(input_path, output_path, input_format, output_format, use_gpu)

                # Update progress
                progress_var.set(int((idx / total_files) * 100))
                update_button(f"Converting: {progress_var.get()}%")

            except Exception as e:
                show_error("Conversion Error", f"Failed to convert {file_name}: {str(e)}")
                return

        # Show completion
        show_conversion_complete(output_folder)

    except Exception:
        raise


def show_conversion_complete(output_folder: str):
    """Show conversion completion dialog"""

    def show_completion_dialog():
        # Update UI
        safe_update_ui(lambda: (
            app_state.convert_button.config(text="CONVERT", bg="#9370DB", fg="white"),
            app_state.youtube_status_label.config(text="Conversion Complete! ^.^"),
            play_notification()
        ))

        def prompt_open_folder():
            if messagebox.askyesnocancel("Success!", "Conversion complete! Do you want to open the output folder?",
                                         parent=app_state.app):
                if sys.platform == 'win32':
                    os.startfile(output_folder)
                else:
                    subprocess.Popen(['xdg-open', output_folder])
            app_state.convert_button.config(text="CONVERT", bg="#9370DB", fg="white")
            app_state.app.update_idletasks()

        if app_state.bad_apple_overlay is not None and app_state.bad_apple_overlay.winfo_exists():
            app_state.bad_apple_overlay.bind("<Destroy>", lambda event: prompt_open_folder())
        else:
            app_state.app.after(100, prompt_open_folder)

    safe_update_ui(show_completion_dialog)


# ... Previous code continues from where you left off ...

# YouTube/Video download functions
def analyze_playlist_url(url: str) -> Tuple[bool, bool]:
    """
    Analyzes a URL to determine its playlist characteristics
    Returns: (is_playlist_page, is_video_in_playlist)
    """
    # Full playlist page
    if 'youtube.com/playlist?list=' in url:
        return True, False

    # Video that's part of a playlist
    if 'youtube.com/watch' in url and 'list=' in url:
        return False, True

    # YouTube Music playlist
    if 'music.youtube.com/playlist' in url:
        return True, False

    # YouTube Music video in playlist
    if 'music.youtube.com/watch' in url and 'list=' in url:
        return False, True

    # SoundCloud set (playlist)
    if 'soundcloud.com/sets/' in url:
        return True, False

    # Generic catch-all for other potential playlist URLs
    if 'playlist' in url.lower() and 'list=' in url:
        return True, False

    return False, False


@handle_errors(default_return={'title': 'YouTube Playlist', 'count': -1, 'current_index': 1})
def get_playlist_info(url: str) -> Dict[str, Any]:
    """Get information about a playlist"""
    logging.info(f"Extracting minimal playlist information for: {url}")

    # Configure yt-dlp with minimal extraction options
    ydl_opts = {
        'quiet': True,
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'playlist_items': '1-1',
        'ignoreerrors': True,
        'socket_timeout': 10,
        'retries': 2,
        'fragment_retries': 2
    }

    # Check if this is a video in a playlist
    is_video_in_playlist = 'watch' in url and 'list=' in url

    # Extract playlist ID if present
    playlist_id = None
    playlist_id_match = re.search(r'list=([^&]+)', url)
    if playlist_id_match:
        playlist_id = playlist_id_match.group(1)

    # Create direct playlist URL if needed
    playlist_url = url
    if is_video_in_playlist and playlist_id:
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

    # Get initial information
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False, process=False)

            playlist_title = info.get('title', 'Unknown Playlist')
            if is_video_in_playlist:
                playlist_title = info.get('playlist', 'Unknown Playlist')

            playlist_count = info.get('playlist_count', 0)
            current_index = info.get('playlist_index', 1)

            return {
                'title': playlist_title,
                'count': playlist_count,
                'current_index': current_index
            }

        except Exception as e:
            logging.error(f"Error extracting playlist info: {e}")
            return {
                'title': 'YouTube Playlist',
                'count': -1,
                'current_index': 1
            }


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds // 60
        sec = seconds % 60
        return f"{minutes:.0f}m {sec:.0f}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours:.0f}h {minutes:.0f}m"


def get_format_string(quality: str, format_type: str) -> str:
    """
    Returns the format string for yt-dlp based on selected quality and format type
    """
    if format_type in AUDIO_FORMATS:
        return "bestaudio/best"

    # For video, always explicitly include audio
    if format_type == "mp4":
        # Simplified format strings that are more flexible
        quality_map = {
            "Best": "best[ext=mp4]/bestvideo+bestaudio/best",
            "4K": "best[height<=2160][ext=mp4]/bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
            "1440p": "best[height<=1440][ext=mp4]/bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
            "1080p": "best[height<=1080][ext=mp4]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "720p": "best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "480p": "best[height<=480][ext=mp4]/bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        }
        return quality_map.get(quality, "best[height<=1080][ext=mp4]/bestvideo[height<=1080]+bestaudio/best")
    else:
        # For other formats
        quality_map = {
            "Best": "bestvideo+bestaudio/best",
            "4K": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
            "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        }
        return quality_map.get(quality, "bestvideo[height<=1080]+bestaudio/best")


def modify_download_options(ydl_opts: Dict[str, Any], quality: str, format_type: str,
                            playlist_action: str = 'single') -> Dict[str, Any]:
    """Configures yt-dlp options based on format and playlist settings"""
    try:
        ffmpeg_path = get_ffmpeg_path()
        ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe')
        if not os.path.exists(ffprobe_path) and getattr(sys, 'frozen', False):
            ffprobe_path = resource_path('ffprobe.exe')

        ydl_opts.update({
            'ffmpeg_location': ffmpeg_path,
            'prefer_ffmpeg': True,
            'external_downloader_args': {'ffmpeg_i': ['-threads', '4']},
        })

        # Handle playlist configuration
        if playlist_action == 'playlist':
            ydl_opts['noplaylist'] = False
            if 'watch' in ydl_opts.get('webpage_url', '') and 'list=' in ydl_opts.get('webpage_url', ''):
                ydl_opts['outtmpl'] = '%(playlist_title)s/%(playlist_index)s-%(title)s.%(ext)s'
            else:
                ydl_opts['outtmpl'] = '%(playlist_title)s/%(playlist_index)s-%(title)s.%(ext)s'
        elif playlist_action == 'single':
            ydl_opts['noplaylist'] = True
            ydl_opts['outtmpl'] = '%(title)s.%(ext)s'
        else:
            return None

        is_youtube_music = 'music.youtube.com' in ydl_opts.get('webpage_url', '')

        parsed_url = urlparse(ydl_opts.get('webpage_url', ''))
        netloc = parsed_url.netloc.lower()

        # Check if audio-only site
        if any(d in netloc for d in ["soundcloud.com", "snd.sc", "bandcamp.com"]):
            if format_type not in AUDIO_FORMATS:
                format_type = "mp3"
                app_state.youtube_format_var.set("mp3")
                messagebox.showinfo("Format Changed",
                                    "That website only supports audio files, so defaulting to mp3",
                                    parent=app_state.app)

        if format_type in AUDIO_FORMATS or is_youtube_music:
            # Audio processing
            bitrate_str = quality.replace("kb/s", "").strip()
            if not bitrate_str.isdigit():
                bitrate_str = "192"

            audio_postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_type if format_type in AUDIO_FORMATS else 'mp3',
                'preferredquality': bitrate_str,
                'nopostoverwrites': False
            }]

            if is_youtube_music or any(d in netloc for d in ["soundcloud.com", "bandcamp.com"]):
                audio_postprocessors.append({
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                })

            if format_type == 'mp3':
                audio_postprocessors.append({
                    'key': 'EmbedThumbnail',
                    'already_have_thumbnail': False,
                })
                ydl_opts['writethumbnail'] = True

            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': audio_postprocessors
            })

        else:
            # Video format handling
            format_string = get_format_string(quality, format_type)

            # For YouTube, always set merge_output_format
            if "youtube.com" in netloc or "youtu.be" in netloc:
                ydl_opts.update({
                    'format': format_string,
                    'merge_output_format': format_type,
                    'postprocessors': []
                })

                # Only add postprocessor args if we need specific encoding
                if format_type == 'webm':
                    ydl_opts['postprocessor_args'] = {
                        'FFmpegVideoRemuxer': [
                            '-c:v', 'libvpx-vp9',
                            '-crf', '30',
                            '-b:v', '0',
                            '-c:a', 'libopus',
                            '-b:a', '128k'
                        ]
                    }
                elif format_type == 'avi':
                    ydl_opts['postprocessor_args'] = {
                        'FFmpegVideoRemuxer': [
                            '-c:v', 'mpeg4',
                            '-c:a', 'mp3',
                            '-q:v', '6',
                            '-b:a', '192k'
                        ]
                    }
            else:
                # For non-YouTube sites
                ydl_opts.update({
                    'format': format_string,
                    'merge_output_format': format_type,
                    'postprocessors': [{
                        'key': 'FFmpegVideoRemuxer',
                        'preferedformat': format_type
                    }]
                })

        # Add better error reporting
        ydl_opts['logger'] = logging.getLogger('yt-dlp')
        ydl_opts['verbose'] = True

        return ydl_opts
    except Exception as e:
        logging.error(f"Error in modify_download_options: {e}", exc_info=True)
        # Return basic options as fallback
        return {
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': format_type,
            'outtmpl': '%(title)s.%(ext)s',
            'noplaylist': True if playlist_action == 'single' else False,
            'ffmpeg_location': ffmpeg_path,
            'progress_hooks': ydl_opts.get('progress_hooks', [])
        }


def yt_dlp_progress_hook(d: Dict[str, Any]) -> None:
    """Progress hook for yt-dlp downloads"""

    def update():
        info_dict = d.get('info_dict', {})
        video_title = info_dict.get('title', '').strip()

        # Format title for display
        display_title = ""
        if video_title:
            if len(video_title) > 30:
                display_title = video_title[:27] + "..."
            else:
                display_title = video_title

        # Get playlist information
        playlist_index = info_dict.get('playlist_index')
        playlist_count = info_dict.get('n_entries')

        # Update tracking variables if we have valid playlist info
        if playlist_index and playlist_count:
            app_state.playlist_current_index = playlist_index
            app_state.playlist_total_count = playlist_count

            # Initialize start time
            if playlist_index == 1 and d['status'] == 'downloading' and not app_state.download_started_time:
                app_state.download_started_time = time.time()

        # Calculate elapsed time
        elapsed_time_str = ""
        if app_state.playlist_current_index > 1 and app_state.playlist_total_count > 0 and app_state.download_started_time:
            elapsed_time = time.time() - app_state.download_started_time
            elapsed_time_str = format_time(elapsed_time)

            # Estimate remaining time
            if app_state.playlist_current_index > 1:
                avg_time_per_video = elapsed_time / (app_state.playlist_current_index - 1)
                remaining_videos = app_state.playlist_total_count - app_state.playlist_current_index + 1
                estimated_remaining = avg_time_per_video * remaining_videos
                elapsed_time_str = f" | Elapsed: {elapsed_time_str}, Remaining: ~{format_time(estimated_remaining)}"

        if d['status'] == 'downloading':
            p = d.get('_percent_str', '').strip()
            s = d.get('_speed_str', '').strip()
            eta = d.get('_eta_str', '').strip()
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)

            # Format downloaded size
            size_str = ""
            if downloaded and total:
                downloaded_mb = downloaded / 1024 / 1024
                total_mb = total / 1024 / 1024
                size_str = f" [{downloaded_mb:.1f}MB/{total_mb:.1f}MB]"

            # Create status text
            if app_state.playlist_current_index and app_state.playlist_total_count:
                progress_percent = (app_state.playlist_current_index - 1 +
                                    (d.get('downloaded_bytes', 0) / (d.get('total_bytes', 1) or
                                                                     d.get('total_bytes_estimate',
                                                                           1)))) / app_state.playlist_total_count * 100

                status_text = f"Downloading {app_state.playlist_current_index}/{app_state.playlist_total_count} ({progress_percent:.1f}%)"
                if display_title:
                    status_text += f" - {display_title}"
                status_text += f"{size_str} - {p} @ {s} (ETA: {eta}){elapsed_time_str}"

                if app_state.progress_var:
                    app_state.progress_var.set(int(progress_percent))

                button_text = f"Playlist: {int(progress_percent)}%"
            else:
                status_text = f"Downloading... {p} @ {s} (ETA: {eta})"
                button_text = "CONVERT"

            app_state.youtube_status_label.config(text=status_text)
            app_state.convert_button.config(text=button_text, fg="white", bg="#9370DB")

        elif d['status'] == 'finished':
            if app_state.playlist_current_index and app_state.playlist_total_count:
                progress_percent = app_state.playlist_current_index / app_state.playlist_total_count * 100
                status_text = f"Processed {app_state.playlist_current_index}/{app_state.playlist_total_count} ({progress_percent:.1f}%)"
                if display_title:
                    status_text += f" - {display_title}"
                status_text += elapsed_time_str

                if app_state.progress_var:
                    app_state.progress_var.set(int(progress_percent))
            else:
                status_text = f"Big brain flex o.o: {display_title}" if display_title else "Processing complete..."

            app_state.youtube_status_label.config(text=status_text)

        elif d['status'] == 'error':
            error_msg = d.get('error', 'Unknown error')
            app_state.youtube_status_label.config(text=f"Error: {error_msg}")
            app_state.convert_button.config(text="CONVERT", fg="white")
            logging.error(f"Download error: {error_msg}")

    safe_update_ui(update)


def handle_download_error(error: Exception):
    """Centralized download error handling"""
    error_str = str(error).lower()

    error_handlers = {
        "throttling": ("YouTube Error", "YouTube is rate limiting downloads. Please try again later."),
        "copyright": ("Copyright Restriction", "This content is restricted due to copyright."),
        "private": ("Content Unavailable", "This content is private or unavailable."),
        "unavailable": ("Content Unavailable", "This content is private or unavailable."),
        "network": ("Network Error", "Connection failed. Please check your internet connection."),
        "connection": ("Network Error", "Connection failed. Please check your internet connection."),
        "timeout": ("Network Error", "Connection timed out. Please try again."),
    }

    for keyword, (title, message) in error_handlers.items():
        if keyword in error_str:
            show_error(title, message)
            return

    # Default error
    show_error("Download Error", f"Failed to download: {str(error)}\n\nPlease try again or check for updates.")


def create_or_update_progress_bar():
    """Create or update a progress bar for playlist downloads"""
    if app_state.progress_frame is None or not app_state.progress_frame.winfo_exists():
        # Create new progress frame
        app_state.progress_frame = tk.Frame(app_state.app, bg="#E6E6FA")
        app_state.progress_frame.grid(row=5, column=0, sticky="ew", pady=(10, 0), padx=20)

        # Create label
        font_to_use = app_state.regular_font if app_state.regular_font else tkFont.Font(family="Arial", size=14)
        progress_label = tk.Label(app_state.progress_frame, text="Playlist Progress:",
                                  bg="#E6E6FA", font=font_to_use)
        progress_label.grid(row=0, column=0, sticky="w", pady=(5, 0))

        # Create progress bar
        app_state.progress_var = tk.IntVar(value=0)
        progress_bar = ttk.Progressbar(app_state.progress_frame, variable=app_state.progress_var,
                                       length=100, mode="determinate", maximum=100)
        progress_bar.grid(row=1, column=0, sticky="ew", pady=(5, 10))

        # Make the progress bar expand
        app_state.progress_frame.grid_columnconfigure(0, weight=1)

        app_state.app.update_idletasks()
    else:
        # Reset the progress value
        app_state.progress_var.set(0)
        app_state.app.update_idletasks()


def download_thread(input_url: str, output_folder: str, format_type: str,
                    quality: str, playlist_action: str):
    """Thread function for downloading videos"""
    app_state.reset_download_tracking()
    app_state.download_manager.start_download(input_url)

    try:
        ffmpeg_path = get_ffmpeg_path()
        os.environ['PATH'] = os.path.dirname(ffmpeg_path) + os.pathsep + os.environ['PATH']

        # Create progress bar for playlists
        if playlist_action == 'playlist':
            safe_update_ui(lambda: create_or_update_progress_bar())

        # Parse URL for site-specific optimizations
        parsed_url = urlparse(input_url)
        netloc = parsed_url.netloc.lower()

        # Determine site type
        is_youtube = any(domain in netloc for domain in ['youtube.com', 'youtu.be', 'music.youtube.com'])
        is_twitter = any(domain in netloc for domain in ['twitter.com', 'x.com'])
        is_tiktok = 'tiktok.com' in netloc
        is_instagram = 'instagram.com' in netloc
        is_audio_only = any(domain in netloc for domain in ['soundcloud.com', 'snd.sc', 'bandcamp.com'])

        # Base yt-dlp options
        ydl_opts = {
            'paths': {'home': output_folder, 'temp': output_folder},
            'progress_hooks': [yt_dlp_progress_hook],
            'ignoreerrors': True,
            'overwrites': True,
            'max_sleep_interval': 1,
            'min_sleep_interval': 1,
            'extractor_retries': 5,
            'webpage_url': input_url,
            'verbose': False,
            'socket_timeout': 15,
            'retries': 3,
            'fragment_retries': 3,
        }

        # Show initial status
        safe_update_ui(lambda: app_state.youtube_status_label.config(text="Analyzing video information..."))

        # Apply site-specific optimizations
        if is_audio_only:
            if format_type not in AUDIO_FORMATS:
                format_type = 'mp3'
                safe_update_ui(lambda: app_state.youtube_format_var.set('mp3'))
                safe_update_ui(lambda: app_state.youtube_status_label.config(
                    text="Alert! Audio-only site detected - using mp3 format"))
                safe_update_ui(lambda: messagebox.showinfo("Format Changed",
                                                           "This site only supports audio files. Defaulting to mp3",
                                                           parent=app_state.app))
        elif is_youtube:
            ydl_opts.update({
                'retries': 10,
                'fragment_retries': 10,
                'external_downloader_args': {'ffmpeg_i': ['-timeout', '60000000', '-thread_queue_size', '10000']},
            })
        elif is_twitter or is_instagram:
            ydl_opts.update({
                'retries': 5,
                'fragment_retries': 10,
                'external_downloader_args': {'ffmpeg_i': ['-timeout', '30000000']},
            })
        elif is_tiktok:
            ydl_opts.update({
                'retries': 8,
                'fragment_retries': 8,
                'external_downloader_args': {'ffmpeg_i': ['-timeout', '30000000']},
            })

        # Get basic information
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl_pre:
                info = ydl_pre.extract_info(input_url, download=False, process=False)

                # Check for Easter Egg
                title = info.get('title', '').lower()
                if "bad apple" in title:
                    show_bad_apple_easter_egg()

                # Set download status message
                if playlist_action == 'playlist':
                    if info.get('_type') == 'playlist':
                        playlist_count = info.get('playlist_count') or len(info.get('entries', []))
                        playlist_title = info.get('title', 'playlist')

                        if playlist_count > 0:
                            safe_update_ui(lambda: app_state.youtube_status_label.config(
                                text=f"Preparing to download {playlist_count} videos from \"{playlist_title}\"..."))
                            app_state.playlist_total_count = playlist_count
                        else:
                            safe_update_ui(lambda: app_state.youtube_status_label.config(
                                text=f"Preparing to download playlist videos... This might take a while."))
                    else:
                        safe_update_ui(lambda: app_state.youtube_status_label.config(
                            text=f"Preparing to download playlist videos... This might take a while."))

                    # Add playlist-specific options
                    ydl_opts.update({
                        'socket_timeout': 30,
                        'retries': 10,
                        'fragment_retries': 10,
                        'retry_sleep_functions': {'fragment': lambda n: 5},
                        'concurrent_fragment_downloads': 1,
                        'logger': logging.getLogger('yt-dlp'),
                        'progress_with_newline': True,
                        'noprogress': False
                    })
        except Exception as e:
            logging.error(f"Error extracting info: {e}")
            safe_update_ui(lambda: app_state.youtube_status_label.config(
                text=f"Proceeding with limited information... (Error: {str(e)[:50]}...)"))

        # Configure download options
        ydl_opts = modify_download_options(ydl_opts, quality, format_type, playlist_action)

        # Initialize download start time
        app_state.download_started_time = time.time()

        # Start the download
        download_successful = False
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                download_info = ydl.download([input_url])

                # Check if download was successful
                if download_info == 0:
                    download_successful = True
                    logging.info("Download completed successfully")
                else:
                    download_successful = False
                    logging.error(f"Download failed with return code: {download_info}")

        except yt_dlp.utils.DownloadError as e:
            download_successful = False
            handle_download_error(e)
            logging.error(f"Download error: {e}", exc_info=True)

        except Exception as e:
            download_successful = False
            safe_update_ui(lambda: app_state.youtube_status_label.config(text="Error occurred!"))
            show_error("Error", f"An unexpected error occurred: {str(e)}\n\nPlease check logs for details.")
            logging.error(f"Unexpected error in download_thread: {e}", exc_info=True)

        finally:
            safe_update_ui(lambda: toggle_interface(True))
            safe_update_ui(lambda: app_state.convert_button.config(text="CONVERT", fg="white"))
            app_state.download_manager.end_download()

        # Only show success prompt if download was successful
        if download_successful:
            def prompt_user():
                safe_update_ui(lambda: app_state.youtube_status_label.config(text="Download Complete! ^.^"))

                # Play notification sound
                play_notification()

                if messagebox.askyesnocancel("Yippee!", "Do you wanna open the output folder?", parent=app_state.app):
                    if sys.platform == 'win32':
                        os.startfile(output_folder)
                    else:
                        subprocess.Popen(['xdg-open', output_folder])
                safe_update_ui(lambda: toggle_interface(True))
                safe_update_ui(lambda: app_state.convert_button.config(text="CONVERT", fg="white"))

            if app_state.bad_apple_overlay is not None and app_state.bad_apple_overlay.winfo_exists():
                app_state.bad_apple_overlay.bind("<Destroy>", lambda event: prompt_user())
            else:
                prompt_user()
        else:
            safe_update_ui(lambda: app_state.youtube_status_label.config(text="Download failed - check error messages"))
            logging.error("Download was not successful, not showing completion prompt")

    except Exception as e:
        safe_update_ui(lambda: app_state.youtube_status_label.config(text="Download failed!"))
        show_error("Download Error", f"Unable to download video. Error: {str(e)}")
        logging.error(f"Fatal error in download_thread: {e}", exc_info=True)
    finally:
        safe_update_ui(lambda: toggle_interface(True))
        safe_update_ui(lambda: app_state.convert_button.config(text="CONVERT", fg="white"))
        app_state.download_manager.end_download()


def download_video():
    """Main download function"""
    app_state.reset_download_tracking()

    input_url = app_state.youtube_link_entry.get().strip()
    if not input_url:
        show_error("Invalid URL", "This is clearly not a valid video URL lol")
        return

    if not validate_url(input_url):
        supported_platforms = [
            'YouTube', 'YouTube Music', 'Twitch VOD', 'Twitter', 'TikTok', 'Dailymotion',
            'Vimeo', 'Instagram Reels', 'Facebook', 'SoundCloud', 'Bandcamp', 'Reddit', 'OK.ru', 'Rumble'
        ]
        show_error("Error",
                   f"Please provide a valid URL from a supported platform:\n\n{', '.join(supported_platforms)}.")
        return

    output_folder = app_state.output_folder_entry.get().strip()
    if output_folder and os.path.isdir(output_folder):
        app_state.settings_manager.add_recent_folder(output_folder)

    if not output_folder:
        show_error("Error", MSG_SELECT_OUTPUT)
        return

    # Analyze URL for playlist
    is_playlist_page, is_video_in_playlist = analyze_playlist_url(input_url)
    playlist_action = 'single'  # Default

    # Handle playlist scenarios
    if is_playlist_page or is_video_in_playlist:
        safe_update_ui(lambda: app_state.youtube_status_label.config(text="Analyzing playlist..."))
        app_state.app.update_idletasks()

        # Get playlist information
        playlist_info = get_playlist_info(input_url)
        playlist_count = playlist_info.get('count', 0)
        playlist_title = playlist_info.get('title', 'Unknown Playlist')
        current_index = playlist_info.get('current_index', 1)

        # Format count text
        count_text = f"with {playlist_count} videos" if playlist_count > 0 else "with multiple videos"
        if playlist_count == -1:
            count_text = "(YouTube limited playlist information)"

        if is_playlist_page:
            # Full playlist URL
            playlist_choice = messagebox.askyesno(
                "Hey look a playlist!",
                f"This is a playlist: \"{playlist_title}\" {count_text}.\n\n"
                f"Do you wanna download the entire playlist?",
                parent=app_state.app
            )

            if playlist_choice:
                playlist_action = 'playlist'
            else:
                safe_update_ui(lambda: app_state.youtube_status_label.config(text="Download Status: Idle"))
                return

        elif is_video_in_playlist:
            # Video in playlist - create custom dialog
            dialog = tk.Toplevel(app_state.app)
            dialog.title("Video in Playlist")
            dialog.geometry("400x200")
            dialog.transient(app_state.app)
            dialog.grab_set()
            dialog.resizable(False, False)

            # Center on parent window
            x = app_state.app.winfo_x() + (app_state.app.winfo_width() // 2) - 200
            y = app_state.app.winfo_y() + (app_state.app.winfo_height() // 2) - 100
            dialog.geometry(f"+{x}+{y}")

            # Message
            message = f"This video is part of a playlist: \"{playlist_title}\" {count_text}.\n\n"
            if current_index > 0:
                message += f"This is video #{current_index} in the playlist.\n\n"
            message += "What are we gonna do?"

            tk.Label(dialog, text=message, wraplength=380, justify="left", padx=10, pady=10).pack()

            # Result variable
            result = [None]

            def set_result(value):
                result[0] = value
                dialog.destroy()

            # Buttons
            button_frame = tk.Frame(dialog)
            button_frame.pack(fill="x", padx=10, pady=10)

            tk.Button(button_frame, text="Download This Video Only",
                      command=lambda: set_result("single")).pack(side="left", fill="x", expand=True, padx=5)
            tk.Button(button_frame, text="Download Entire Playlist",
                      command=lambda: set_result("playlist")).pack(side="left", fill="x", expand=True, padx=5)
            tk.Button(button_frame, text="Cancel",
                      command=lambda: set_result("none")).pack(side="left", fill="x", expand=True, padx=5)

            dialog.protocol("WM_DELETE_WINDOW", lambda: set_result("none"))

            # Wait for dialog
            app_state.app.wait_window(dialog)

            if result[0] == "none" or result[0] is None:
                safe_update_ui(lambda: app_state.youtube_status_label.config(text="Download Status: Idle"))
                return

            playlist_action = result[0]

    try:
        format_type = app_state.youtube_format_var.get()
        quality = app_state.youtube_quality_var.get()

        if 'music.youtube.com' in input_url and format_type not in AUDIO_FORMATS:
            safe_update_ui(lambda: app_state.youtube_status_label.config(
                text="Extracting Playlist Data - This may take a while..."))
            format_type = 'mp3'
            app_state.youtube_format_var.set('mp3')
            messagebox.showinfo("Format Changed",
                                'YouTube Music detected - defaulting to mp3. This may take a while, the program is not crashing even if it says "not responding" lol')
    except Exception:
        show_error("Error", "Failed to get format or quality settings. Please try again.")
        return

    # Start download in thread
    toggle_interface(False)
    if 'list=' not in input_url:
        safe_update_ui(lambda: app_state.youtube_status_label.config(text="Processing URL..."))
    app_state.app.update_idletasks()

    thread = threading.Thread(target=download_thread,
                              args=(input_url, output_folder, format_type, quality, playlist_action),
                              daemon=True)
    thread.start()


# UI Event Handlers
def on_drop(event) -> None:
    """Handle file drop event"""
    try:
        files = app_state.app.tk.splitlist(event.data)
        app_state.input_entry.delete(0, tk.END)
        app_state.input_entry.insert(0, ";".join(files))
    except Exception as e:
        show_error("Error", f"Failed to process dropped files: {e}")


def select_input() -> None:
    """Select input files"""
    input_selected = filedialog.askopenfilenames(
        filetypes=[("Media files",
                    "*.mp3;*.wav;*.ogg;*.flac;*.m4a;*.mp4;*.avi;*.mov;*.mkv;*.webm;*.flv")]
    )
    if input_selected:
        app_state.input_entry.delete(0, tk.END)
        app_state.input_entry.insert(0, ";".join(input_selected))


def select_output_folder() -> None:
    """Select output folder"""
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        app_state.output_folder_entry.delete(0, tk.END)
        app_state.output_folder_entry.insert(0, folder_selected)
        app_state.settings_manager.add_recent_folder(folder_selected)


def start_conversion() -> None:
    """Start file conversion"""
    input_paths = app_state.input_entry.get().strip().split(";")
    output_folder = app_state.output_folder_entry.get().strip()

    if output_folder and os.path.isdir(output_folder):
        app_state.settings_manager.add_recent_folder(output_folder)

    output_format = app_state.format_dropdown.get()

    # Validate inputs
    if not input_paths or not input_paths[0]:
        show_error("Error", MSG_SELECT_INPUT)
        return
    if not output_folder:
        show_error("Error", MSG_SELECT_OUTPUT)
        return
    if not output_format or output_format not in AUDIO_FORMATS + VIDEO_FORMATS:
        show_error("Error", MSG_INVALID_FORMAT)
        return

    use_gpu = app_state.gpu_var.get()
    app_state.progress_var.set(0)

    # Start conversion in thread
    thread = threading.Thread(target=convert_audio,
                              args=(input_paths, output_folder, output_format,
                                    app_state.progress_var, app_state.convert_button, use_gpu),
                              daemon=True)
    thread.start()


def toggle_interface(enabled: bool = True) -> None:
    """Enable/disable interface elements"""
    widgets = [
        app_state.input_entry, app_state.output_folder_entry,
        app_state.youtube_link_entry, app_state.format_dropdown,
        app_state.convert_button, app_state.gpu_checkbox
    ]
    state = 'normal' if enabled else 'disabled'
    for widget in widgets:
        if widget:
            widget.configure(state=state)

    # Update all buttons
    for button in app_state.app.winfo_children():
        if isinstance(button, tk.Button):
            button.configure(state=state)


def on_youtube_format_change(event=None):
    """Handle YouTube format change"""
    video_quality_options = ["Best", "4K", "1440p", "1080p", "720p", "480p"]
    audio_bitrates = ["128kb/s", "192kb/s", "256kb/s", "320kb/s"]
    selected_format = app_state.youtube_format_var.get()

    if selected_format in AUDIO_FORMATS:
        app_state.youtube_quality_dropdown['values'] = audio_bitrates
        app_state.youtube_quality_var.set("256kb/s")
    else:
        app_state.youtube_quality_dropdown['values'] = video_quality_options
        app_state.youtube_quality_var.set("1080p")


# Recent folders menu functions
def update_recent_folders_menu():
    """Update the recent folders dropdown menu"""
    if app_state.recent_folders_menu is None:
        return

    # Clear existing menu items
    app_state.recent_folders_menu.delete(0, tk.END)

    # Get recent folders
    recent_folders = app_state.settings_manager.get("recent_folders", [])

    if not recent_folders:
        app_state.recent_folders_menu.add_command(label="No recent folders", state=tk.DISABLED)
        return

    # Add each folder to the menu
    for folder in recent_folders:
        app_state.recent_folders_menu.add_command(
            label=Path(folder).name,
            command=lambda f=folder: set_output_folder(f)
        )

    # Add separator and clear option
    if recent_folders:
        app_state.recent_folders_menu.add_separator()
        app_state.recent_folders_menu.add_command(
            label="Clear Recent Folders",
            command=clear_recent_folders
        )


def set_output_folder(folder: str):
    """Set the output folder from the recent folders menu"""
    app_state.output_folder_entry.delete(0, tk.END)
    app_state.output_folder_entry.insert(0, folder)


def clear_recent_folders():
    """Clear the list of recent folders"""
    app_state.settings_manager.clear_recent_folders()
    update_recent_folders_menu()


def show_recent_folders_menu(button):
    """Show the recent folders menu under the button"""
    update_recent_folders_menu()
    try:
        app_state.recent_folders_menu.tk_popup(
            button.winfo_rootx(),
            button.winfo_rooty() + button.winfo_height()
        )
    finally:
        app_state.recent_folders_menu.grab_release()


def create_recent_folders_button(parent, row, column):
    """Create a button that shows recent folders in a dropdown"""
    # Create menu
    app_state.recent_folders_menu = tk.Menu(app_state.app, tearoff=0)
    update_recent_folders_menu()

    # Create button
    button = tk.Button(
        parent,
        text="Recent",
        bg="#DDA0DD",
        fg="white",
        font=app_state.regular_font,
        command=lambda: show_recent_folders_menu(button)
    )
    button.grid(row=row, column=column, padx=5, pady=10)
    return button


# UI Setup functions
def setup_fonts() -> Tuple[tkFont.Font, tkFont.Font]:
    """Setup application fonts"""
    try:
        import ctypes
        bubblegum_path = resource_path(os.path.join('assets', 'fonts', 'BubblegumSans-Regular.ttf'))
        bartino_path = resource_path(os.path.join('assets', 'fonts', 'Bartino.ttf'))

        # Only load fonts on Windows
        if sys.platform == 'win32' and hasattr(ctypes.windll, 'gdi32'):
            ctypes.windll.gdi32.AddFontResourceW(bubblegum_path)
            ctypes.windll.gdi32.AddFontResourceW(bartino_path)

        title_font = tkFont.Font(family="Bubblegum Sans", size=32)
        regular_font = tkFont.Font(family="Bartino", size=14)
        return (title_font, regular_font)
    except Exception as e:
        logging.error(f"Error setting up fonts: {e}")
        title_font = tkFont.Font(family="Arial", size=32, weight="bold")
        regular_font = tkFont.Font(family="Arial", size=14)
        return (title_font, regular_font)


def setup_main_window() -> None:
    """Setup the main application window"""
    try:
        if getattr(sys, 'frozen', False):
            # Set TCL library path for frozen app
            base_path = os.path.dirname(sys.executable)
            tcl_dnd_path = os.path.join(base_path, "tkinterdnd2", "tkdnd", "win-x64")
            os.environ["TCLLIBPATH"] = tcl_dnd_path

        # Load icon
        icon_path = resource_path(os.path.join('assets', 'icons', 'icon.png'))
        if os.path.exists(icon_path):
            icon_img = PhotoImage(file=icon_path)
            app_state.app.iconphoto(False, icon_img)
            app_state.app.call('wm', 'iconphoto', app_state.app._w, '-default', icon_img)
        else:
            logging.error(f"Icon not found at: {icon_path}")

        app_state.app.title(f"Hey besties let's convert those files (v{CURRENT_VERSION})")
        app_state.app.configure(bg="#E6E6FA")
        app_state.app.geometry(f"{WINDOW_DEFAULT_WIDTH}x{WINDOW_DEFAULT_HEIGHT}")
        app_state.app.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        app_state.app.resizable(True, True)

        app_state.app.drop_target_register(DND_FILES)
        app_state.app.dnd_bind("<<Drop>>", on_drop)
    except Exception as e:
        logging.error(f"Error setting up main window: {e}")


def add_update_menu(menubar) -> None:
    """Add update-related menu items"""
    help_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="Help", menu=help_menu)
    help_menu.add_command(label="Check for Updates", command=check_for_updates)
    help_menu.add_separator()
    help_menu.add_command(label="Visit Project Page",
                          command=lambda: webbrowser.open(ITCH_GAME_URL))
    help_menu.add_separator()
    help_menu.add_command(label="About", command=show_about)


def initialize_output_folder():
    """Set the output folder entry to the most recent folder"""
    recent_folders = app_state.settings_manager.get("recent_folders", [])

    if recent_folders:
        most_recent_folder = recent_folders[0]
        app_state.output_folder_entry.delete(0, tk.END)
        app_state.output_folder_entry.insert(0, most_recent_folder)


def create_ui_components() -> None:
    """Create all UI components"""
    app_state.title_font, app_state.regular_font = setup_fonts()

    # Initialize variables
    app_state.youtube_format_var = tk.StringVar(value="mp4")
    app_state.youtube_quality_var = tk.StringVar(value="1080p")

    # Create menu
    menubar = tk.Menu(app_state.app)
    app_state.app.config(menu=menubar)
    add_update_menu(menubar)
    setup_auto_update_checker()

    # Main frame
    main_frame = tk.Frame(app_state.app, bg="#E6E6FA")
    main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
    main_frame.grid_columnconfigure(0, weight=1)

    # Header
    header_label = tk.Label(main_frame, text="Lace's Total File Converter",
                            font=app_state.title_font, bg="#E6E6FA", fg="#6A0DAD")
    header_label.grid(row=0, column=0, columnspan=3, pady=(0, 20), sticky="ew")

    # Video Download Frame (row 1)
    video_frame = tk.LabelFrame(main_frame, text="Video Download", bg="#E6E6FA",
                                font=app_state.regular_font, fg="#6A0DAD", pady=10)
    video_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 20))
    video_frame.grid_columnconfigure(1, weight=1)

    tk.Label(video_frame, text="Video URL:", bg="#E6E6FA",
             font=app_state.regular_font).grid(row=0, column=0, padx=10, pady=5, sticky="w")
    app_state.youtube_link_entry = tk.Entry(video_frame, width=50, font=app_state.regular_font)
    app_state.youtube_link_entry.grid(row=0, column=1, columnspan=2, padx=10, pady=5, sticky="ew")

    supported_platforms = tk.Label(video_frame,
                                   text="Supports nearly every major video and audio platform",
                                   bg="#E6E6FA", font=app_state.regular_font, fg="#666666")
    supported_platforms.grid(row=1, column=0, columnspan=3, pady=(0, 5), sticky="w", padx=10)

    # Video options frame
    options_frame = tk.Frame(video_frame, bg="#E6E6FA")
    options_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)
    options_frame.grid_columnconfigure(1, weight=1)
    options_frame.grid_columnconfigure(3, weight=1)

    tk.Label(options_frame, text="Format:", bg="#E6E6FA",
             font=app_state.regular_font).grid(row=0, column=0, padx=10, sticky="w")
    youtube_format_dropdown = ttk.Combobox(options_frame, textvariable=app_state.youtube_format_var,
                                           values=["mp4", "mkv", "webm", "avi", "flv", "mp3",
                                                   "wav", "flac", "ogg", "m4a"],
                                           font=app_state.regular_font, state="readonly")
    youtube_format_dropdown.grid(row=0, column=1, padx=10, sticky="ew")
    youtube_format_dropdown.bind("<<ComboboxSelected>>", on_youtube_format_change)

    tk.Label(options_frame, text="Quality:", bg="#E6E6FA",
             font=app_state.regular_font).grid(row=0, column=2, padx=10, sticky="w")
    app_state.youtube_quality_dropdown = ttk.Combobox(options_frame, textvariable=app_state.youtube_quality_var,
                                                      values=["Best", "4K", "1440p", "1080p", "720p", "480p"],
                                                      font=app_state.regular_font, state="readonly")
    app_state.youtube_quality_dropdown.grid(row=0, column=3, padx=10, sticky="ew")
    on_youtube_format_change()

    tk.Button(video_frame, text="DOWNLOAD", command=download_video, bg="#9370DB",
              fg="white", font=app_state.regular_font).grid(row=3, column=0, columnspan=3, pady=10, sticky="ew")

    # File Conversion Frame (row 2)
    conversion_frame = tk.LabelFrame(main_frame, text="File Conversion", bg="#E6E6FA",
                                     font=app_state.regular_font, fg="#6A0DAD", pady=10)
    conversion_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 20))
    conversion_frame.grid_columnconfigure(1, weight=1)

    tk.Label(conversion_frame, text="Input Files:", bg="#E6E6FA",
             font=app_state.regular_font).grid(row=0, column=0, padx=10, pady=5, sticky="w")
    app_state.input_entry = tk.Entry(conversion_frame, width=50, font=app_state.regular_font)
    app_state.input_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
    tk.Button(conversion_frame, text="Browse", command=select_input, bg="#DDA0DD",
              fg="white", font=app_state.regular_font).grid(row=0, column=2, padx=10, pady=5)

    tk.Label(conversion_frame, text="Output Format:", bg="#E6E6FA",
             font=app_state.regular_font).grid(row=1, column=0, padx=10, pady=5, sticky="w")
    app_state.format_dropdown = ttk.Combobox(conversion_frame, textvariable=app_state.format_var,
                                             values=AUDIO_FORMATS + VIDEO_FORMATS,
                                             font=app_state.regular_font, state="readonly")
    app_state.format_dropdown.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

    app_state.convert_button = tk.Button(conversion_frame, text="CONVERT", command=start_conversion,
                                         bg="#9370DB", fg="white", font=app_state.regular_font)
    app_state.convert_button.grid(row=2, column=0, columnspan=3, pady=10, sticky="ew")

    # Output Location Frame (row 3)
    output_frame = tk.LabelFrame(main_frame, text="Output Location", bg="#E6E6FA",
                                 font=app_state.regular_font, fg="#6A0DAD", pady=10)
    output_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 20))
    output_frame.grid_columnconfigure(1, weight=1)

    tk.Label(output_frame, text="Output Folder:", bg="#E6E6FA",
             font=app_state.regular_font).grid(row=0, column=0, padx=10, pady=10, sticky="w")
    app_state.output_folder_entry = tk.Entry(output_frame, width=50, font=app_state.regular_font)
    app_state.output_folder_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
    tk.Button(output_frame, text="Browse", command=select_output_folder, bg="#DDA0DD",
              fg="white", font=app_state.regular_font).grid(row=0, column=2, padx=10, pady=10)

    # Create Recent Folders button
    create_recent_folders_button(output_frame, 0, 3)

    # Bottom frame (row 4)
    bottom_frame = tk.Frame(main_frame, bg="#E6E6FA")
    bottom_frame.grid(row=4, column=0, sticky="ew", pady=(0, 10))
    bottom_frame.grid_columnconfigure(0, weight=1)

    app_state.gpu_checkbox = tk.Checkbutton(bottom_frame, text="GPU Encode (Significantly Faster)",
                                            bg="#E6E6FA", font=app_state.regular_font,
                                            variable=app_state.gpu_var)
    app_state.gpu_checkbox.grid(row=0, column=0, pady=5, sticky="ew")

    app_state.youtube_status_label = tk.Label(bottom_frame, text="Download Status: Idle",
                                              bg="#E6E6FA", font=app_state.regular_font)
    app_state.youtube_status_label.grid(row=1, column=0, pady=5, sticky="ew")

    # Configure grid weights
    app_state.app.grid_rowconfigure(0, weight=1)
    app_state.app.grid_columnconfigure(0, weight=1)

def main():
    """Main application entry point"""
    global app_state

    try:
        # Create the main window
        app_state.app = TkinterDnD.Tk()

        # Initialize settings manager
        app_state.settings_manager = SettingsManager()
        app_settings = app_state.settings_manager.load()

        # Initialize variables with values from settings
        app_state.format_var = tk.StringVar(value=app_settings.get("default_format", "mp4"))
        app_state.gpu_var = tk.BooleanVar(value=app_settings.get("use_gpu", True))
        app_state.progress_var = tk.IntVar()

        # Initialize download manager
        app_state.download_manager = DownloadManager()

        # Register cleanup on exit
        import atexit
        atexit.register(VLCManager.cleanup)

        # Verify setup
        verify_video_setup()

        # Verify FFmpeg
        try:
            ffmpeg_path, ffprobe_path = initialize_ffmpeg_paths()
        except FileNotFoundError as e:
            messagebox.showerror("FFmpeg Error", str(e))
            sys.exit(1)

        # Setup UI
        setup_main_window()
        create_ui_components()
        update_recent_folders_menu()

        # Set initial output folder
        initialize_output_folder()

        # Initialize audio system after UI is ready
        app_state.app.after(500, initialize_audio_system)

        # Start the main loop
        app_state.app.mainloop()

    except Exception as e:
        logging.error(f"Fatal error: {e}")
        logging.error(traceback.format_exc())
        log_errors()
        messagebox.showerror("Fatal Error",
                             f"Application crashed: {str(e)}\n\nCheck error_log.txt for details.")
        sys.exit(1)
    finally:
        # Ensure cleanup
        VLCManager.cleanup()
        if app_state.download_manager:
            app_state.download_manager.cancel_all_downloads()


if __name__ == "__main__":
    main()