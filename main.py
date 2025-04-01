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



logging.basicConfig(level=logging.INFO)



# Application Constants

CURRENT_VERSION = "2.3.2"

ITCH_GAME_URL = "https://laceediting.itch.io/laces-total-file-converter"

MAX_RECENT_FOLDERS = 5

SETTINGS_FILE = "app_settings.json"



bad_apple_overlay = None

recent_folders_menu = None



# Globals for Tkinter references

input_entry = None

output_folder_entry = None

youtube_link_entry = None

format_dropdown = None

convert_button = None

gpu_checkbox = None

youtube_status_label = None

gpu_var = None

format_var = None

progress_var = None

youtube_format_var = None

youtube_quality_var = None

youtube_quality_dropdown = None

app = None

progress_frame = None

regular_font = None

title_font = None





# Global variables for tracking playlist progress

playlist_current_index = 0

playlist_total_count = 0

download_started_time = None



# Other Globals

notification_player = None

notification_sound_loaded = False





if sys.version_info >= (3, 8) and os.name == 'nt':

    if hasattr(os, 'add_dll_directory'):

        if getattr(sys, 'frozen', False):

            os.add_dll_directory(os.path.dirname(sys.executable))

        else:

            os.add_dll_directory(os.path.abspath('.'))





def log_errors():

    with open("error_log.txt", "w") as f:

        f.write(traceback.format_exc())





def resource_path(relative_path):

    """Get absolute path to resource, works for dev and for PyInstaller"""

    try:

        # PyInstaller creates a temp folder and stores path in _MEIPASS

        if getattr(sys, 'frozen', False):

            base_path = sys._MEIPASS

        else:

            base_path = os.path.dirname(os.path.abspath(__file__))

    except Exception:

        base_path = os.path.dirname(os.path.abspath(__file__))



    return os.path.join(base_path, relative_path)





def get_absolute_path(relative_path):

    """Get absolute path to file that needs to be written to"""

    if getattr(sys, 'frozen', False):

        # When frozen, use the directory containing the executable.

        base_path = os.path.dirname(sys.executable)

    else:

        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)





# Defines the path for the settings file

def get_settings_path():

    """Get the path to the settings file"""

    return get_absolute_path(SETTINGS_FILE)





def get_notification_sound_path():

    """Get path to the notification sound file"""

    sound_path = resource_path(os.path.join("assets", "sounds", "notification.mp3"))



    # Check if the sound file exists

    if os.path.exists(sound_path):

        return sound_path



    # If not found in expected location, check for alternate locations

    alt_paths = [

        resource_path(os.path.join("assets", "notification.mp3")),

        resource_path(os.path.join("assets", "complete.mp3"))

    ]



    for path in alt_paths:

        if os.path.exists(path):

            return path



    logging.warning("Notification sound file not found")

    return None





def initialize_audio_player():

    """Pre-initialize VLC player during application startup"""

    global notification_player, notification_sound_loaded



    try:

        # Create a persistent VLC instance

        instance = vlc.Instance("--no-video --quiet")

        notification_player = instance.media_player_new()



        # Preload the notification sound

        sound_path = get_notification_sound_path()

        if sound_path:

            media = instance.media_new(sound_path)

            notification_player.set_media(media)

            notification_sound_loaded = True

            logging.info("Audio notification system initialized")

        return True

    except Exception as e:

        logging.error(f"Error initializing audio player: {e}")

        return False



def play_notification(audio_path, duration=3):

    """Play an audio notification when operations complete"""

    try:

        # Create a new VLC instance

        instance = vlc.Instance()

        player = instance.media_player_new()



        # Create and set media

        media = instance.media_new(audio_path)

        player.set_media(media)



        # Play the audio

        player.play()

        logging.info(f"Playing audio notification: {audio_path}")



        # Create a thread to stop playback after duration

        def stop_playback():

            time.sleep(duration)

            player.stop()

            logging.info("Audio notification playback ended")



        threading.Thread(target=stop_playback, daemon=True).start()

        return True

    except Exception as e:

        logging.error(f"Error playing audio notification: {e}")

        return False



def load_settings():

    """Load application settings from JSON file"""

    settings_path = get_settings_path()

    default_settings = {

        "recent_folders": [],

        "default_format": "mp4",

        "use_gpu": True

    }



    try:

        if os.path.exists(settings_path):

            with open(settings_path, 'r') as f:

                settings = json.load(f)

                # Ensure all expected keys exist

                for key in default_settings:

                    if key not in settings:

                        settings[key] = default_settings[key]

                return settings

    except Exception as e:

        logging.error(f"Error loading settings: {e}")



    return default_settings





def save_settings(settings):

    """Save application settings to JSON file"""

    settings_path = get_settings_path()

    try:

        with open(settings_path, 'w') as f:

            json.dump(settings, f, indent=4)

        return True

    except Exception as e:

        logging.error(f"Error saving settings: {e}")

        return False





def add_recent_folder(folder_path):

    """Add a folder to the recent folders list"""

    settings = load_settings()

    recent_folders = settings.get("recent_folders", [])



    # Remove if already exists to avoid duplicates

    if folder_path in recent_folders:

        recent_folders.remove(folder_path)



    # Add to the beginning of the list

    recent_folders.insert(0, folder_path)



    # Limit to MAX_RECENT_FOLDERS

    settings["recent_folders"] = recent_folders[:MAX_RECENT_FOLDERS]



    save_settings(settings)

    update_recent_folders_menu()





def update_recent_folders_menu():

    """Update the recent folders dropdown menu"""

    global recent_folders_menu



    if recent_folders_menu is None:

        return



    # Clear existing menu items

    recent_folders_menu.delete(0, tk.END)



    # Get recent folders

    settings = load_settings()

    recent_folders = settings.get("recent_folders", [])



    if not recent_folders:

        recent_folders_menu.add_command(label="No recent folders", state=tk.DISABLED)

        return



    # Add each folder to the menu

    for folder in recent_folders:

        # Use a lambda with default argument to avoid late binding issue

        recent_folders_menu.add_command(

            label=Path(folder).name,  # Just show folder name for cleaner UI

            command=lambda f=folder: set_output_folder(f)

        )



    # Add separator and clear option

    if recent_folders:

        recent_folders_menu.add_separator()

        recent_folders_menu.add_command(

            label="Clear Recent Folders",

            command=clear_recent_folders

        )





def set_output_folder(folder):

    """Set the output folder from the recent folders menu"""

    output_folder_entry.delete(0, tk.END)

    output_folder_entry.insert(0, folder)





def clear_recent_folders():

    """Clear the list of recent folders"""

    settings = load_settings()

    settings["recent_folders"] = []

    save_settings(settings)

    update_recent_folders_menu()





def show_recent_folders_menu(button):

    """Show the recent folders menu under the button"""

    global recent_folders_menu

    # Force menu update before showing

    update_recent_folders_menu()

    # Show the menu

    try:

        recent_folders_menu.tk_popup(

            button.winfo_rootx(),

            button.winfo_rooty() + button.winfo_height()

        )

    finally:

        # Make sure to release the grab

        recent_folders_menu.grab_release()





def verify_video_setup():

    logging.info("Verifying video playback setup")

    paths_to_check = {

        'Video file': resource_path(os.path.join("assets", "BaddAscle.mp4")),

        'FFmpeg': get_ffmpeg_path(),

        'Assets directory': resource_path("assets")

    }

    for name, path in paths_to_check.items():

        exists = os.path.exists(path)

        logging.info(f"{name} path check: {path} - {'EXISTS' if exists else 'MISSING'}")





def get_ffmpeg_path():

    if getattr(sys, 'frozen', False):

        base_path = os.path.dirname(sys.executable)

        ffmpeg_path = os.path.join(base_path, 'ffmpeg.exe')

        if not os.path.exists(ffmpeg_path):

            logging.error(f"FFmpeg not found at {ffmpeg_path}")

            # Try with resource_path as fallback

            ffmpeg_path = resource_path('ffmpeg.exe')

            if not os.path.exists(ffmpeg_path):

                raise FileNotFoundError("FFmpeg executable not found in application bundle")

        return ffmpeg_path

    else:

        base_path = os.path.dirname(os.path.abspath(__file__))

        ffmpeg_path = os.path.join(base_path, 'dist', 'ffmpeg', 'bin', 'ffmpeg.exe')

        if not os.path.exists(ffmpeg_path):

            # Try direct path

            ffmpeg_path = os.path.join(base_path, 'ffmpeg.exe')

            if not os.path.exists(ffmpeg_path):

                from shutil import which

                system_ffmpeg = which('ffmpeg.exe')

                if system_ffmpeg:

                    return system_ffmpeg

                raise FileNotFoundError("FFmpeg not found in expected development location or system PATH.")

        return ffmpeg_path





try:

    FFMPEG_PATH = get_ffmpeg_path()

    subprocess.run([FFMPEG_PATH, "-version"], check=True)

except Exception as e:

    logging.error(f"Error initializing FFmpeg: {e}")

    FFMPEG_PATH = None





def safe_update_ui(func) -> None:

    if not isinstance(func, str):

        app.after(0, func)

    else:

        def update():

            eval(func)



        app.after(0, update)





def is_valid_url(input_url):

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





def analyze_playlist_url(url):

    """

    Analyzes a URL to determine its playlist characteristics



    Returns:

        tuple: (is_playlist_page, is_video_in_playlist)

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





def get_playlist_info(url):

    """

    Get information about a playlist (title and number of videos)

    Uses minimal extraction to avoid YouTube throttling

    """

    try:

        logging.info(f"Extracting minimal playlist information for: {url}")



        # Configure yt-dlp with minimal extraction options and timeouts

        ydl_opts = {

            'quiet': True,

            'extract_flat': 'in_playlist',  # Only extract minimal info for playlists

            'skip_download': True,

            'playlist_items': '1-1',  # Only look at the first item to get playlist info

            'ignoreerrors': True,

            'socket_timeout': 10,  # Set timeouts to prevent hanging

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



        # Get initial information to determine if it's a playlist

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            try:

                # First try getting basic info from the original URL

                info = ydl.extract_info(url, download=False, process=False)



                # Get playlist title

                playlist_title = info.get('title', 'Unknown Playlist')

                if is_video_in_playlist:

                    # For a video in playlist, the title will be the video title, not playlist title

                    playlist_title = info.get('playlist', 'Unknown Playlist')



                # Get playlist count - be cautious as this might be incomplete

                playlist_count = info.get('playlist_count', 0)



                # Get current index if it's a video in playlist

                current_index = info.get('playlist_index', 1)



                # Return the best information we have

                return {

                    'title': playlist_title,

                    'count': playlist_count,

                    'current_index': current_index

                }



            except Exception as e:

                logging.error(f"Error extracting playlist info: {e}")

                # Return default values if extraction fails

                return {

                    'title': 'YouTube Playlist',

                    'count': -1,  # Use -1 to indicate unknown count

                    'current_index': 1

                }

    except Exception as e:

        logging.error(f"Error in get_playlist_info: {e}")

        return {

            'title': 'YouTube Playlist',

            'count': -1,

            'current_index': 1

        }





def safe_filename(filepath):

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





def check_for_updates(app) -> bool:

    try:

        safe_update_ui(lambda: youtube_status_label.config(text="Checking for updates..."))



        # The Itch.IO game URL to check for updates

        itch_url = ITCH_GAME_URL



        try:

            # Fetch the Itch.IO page content

            response = requests.get(itch_url, timeout=10)

            if response.status_code == 200:

                page_content = response.text



                # Regular expression to find download files with version pattern

                # Looks for Laces_Total_File_Converter_v followed by version number

                version_pattern = r'Laces_Total_File_Converter_v(\d+\.\d+\.\d+)'

                matches = re.findall(version_pattern, page_content)



                if matches:

                    # Get all version numbers found on the page

                    available_versions = [version.parse(v) for v in matches]



                    # Find the highest version available

                    latest_version = max(available_versions)

                    current_ver = version.parse(CURRENT_VERSION)



                    # If there's a newer version available

                    if latest_version > current_ver:

                        update_message = f"""

A new version ({latest_version}) is available!

You're currently running version {CURRENT_VERSION}



Would you like to visit the download page?

"""

                        if messagebox.askyesno("Update Available", update_message, parent=app):

                            handle_manual_update()

                        return True



                # If we reach here, either no versions found or current is latest

                safe_update_ui(lambda: youtube_status_label.config(text="You're running the latest version! Good job! ^.-"))

                return False

            else:

                logging.error(f"Failed to fetch itch.io page: {response.status_code}")

                safe_update_ui(lambda: youtube_status_label.config(text="Update check unavailable"))

                return False



        except Exception as e:

            logging.error(f"Update check error: {e}")

            safe_update_ui(lambda: youtube_status_label.config(text="Update check failed"))

            return False



    finally:

        app.after(3000, lambda: safe_update_ui(lambda: youtube_status_label.config(text="Download Status: Idle")))





def handle_manual_update() -> None:

    """Open the Itch.io page for manual download"""

    try:

        webbrowser.open(ITCH_GAME_URL)

        messagebox.showinfo(title="Manual Update", message="Opening download page in your browser.")

    except Exception as e:

        messagebox.showerror("Update Error", f"Failed to open download page: {str(e)}")





def setup_auto_update_checker(app) -> None:

    """Schedule periodic update checks"""

    # First check after 1 second

    app.after(1000, lambda: check_for_updates(app))



    # Schedule daily checks (86400000 ms = 24 hours)

    def schedule_next_check():

        check_for_updates(app)

        app.after(86400000, schedule_next_check)



    # Also schedule check every 24 hours

    app.after(86400000, schedule_next_check)





def show_about() -> None:

    messagebox.showinfo(

        "About",

        f"Lace's Total File Converter v{CURRENT_VERSION}\n\n"

        "A friendly file converter for all your media needs!\n\n"

        "Created with ♥ by Lace"

    )





def add_update_menu(app, menubar) -> None:

    """Add update-related menu items"""

    help_menu = tk.Menu(menubar, tearoff=0)

    menubar.add_cascade(label="Help", menu=help_menu)

    help_menu.add_command(label="Check for Updates", command=lambda: check_for_updates(app))

    help_menu.add_separator()

    help_menu.add_command(label="Visit Project Page",

                          command=lambda: webbrowser.open("https://laceediting.itch.io/laces-total-file-converter"))

    help_menu.add_separator()

    help_menu.add_command(label="About", command=show_about)





# Video Playback using python-vlc

def show_vlc_overlay(video_path, duration=11):

    global bad_apple_overlay



    overlay = tk.Frame(app, bg="black")

    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

    overlay.lift()

    bad_apple_overlay = overlay



    video_frame = tk.Frame(overlay, bg="black")

    video_frame.pack(expand=True, fill="both")



    try:

        instance = vlc.Instance()

        player = instance.media_player_new()



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

        messagebox.showerror("Video Error", "Could not play video. Check error_log.txt for details.")

        if overlay:

            overlay.destroy()





def show_bad_apple_easter_egg():

    video_path = resource_path(os.path.join("assets", "BaddAscle.mp4"))

    logging.info(f"Verifying video at: {video_path}")

    if not os.path.exists(video_path):

        logging.error(f"Video file not found at expected path: {video_path}")

        messagebox.showerror("Easter Egg Error",

                             "Video file not found or inaccessible. Please verify application installation.")

        return

    try:

        logging.info(f"Preparing to play video from: {video_path}")

        show_vlc_overlay(video_path, duration=13)

    except Exception as e:

        error_msg = f"Easter egg playback failed: {str(e)}\n{traceback.format_exc()}"

        logging.error(error_msg)

        messagebox.showerror("Easter Egg Error", "The easter egg couldn't be played. Check error_log.txt for details.")





# Core Application Logic

def direct_ffmpeg_gpu_video2video(input_path: str, output_path: str, output_format: str) -> None:

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



        # Special handling for AVI

        if output_format.lower() == "avi":

            gpu_cmd = [ffmpeg_path, "-hwaccel", "cuda", "-i", input_path,

                       "-c:v", "mpeg4", "-q:v", "5", "-c:a", "mp3", "-y", output_path]

        # New special handling for FLV

        elif output_format.lower() == "flv":

            gpu_cmd = [ffmpeg_path, "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",

                       "-i", input_path, "-c:v", "h264_nvenc", "-preset", "p1",

                       "-profile:v", "main", "-level", "3.1",  # More compatible profile for FLV

                       "-b:v", "2M", "-maxrate", "2.5M", "-bufsize", "4M",

                       "-c:a", "aac", "-b:a", "128k",  # Standard audio for FLV

                       "-f", "flv",  # Force FLV format

                       "-y", output_path]

        else:

            # Default handling for MP4, MKV, and others

            gpu_cmd = [ffmpeg_path, "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",

                       "-i", input_path, "-c:v", "h264_nvenc", "-preset", "p1", "-tune", "hq",

                       "-rc", "vbr", "-cq", "23", "-b:v", "0", "-maxrate", "130M",

                       "-bufsize", "130M", "-spatial-aq", "1", "-c:a", "aac", "-b:a", "192k",

                       "-y", output_path]

        try:

            subprocess.run(gpu_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)

            return

        except subprocess.CalledProcessError:

            logging.info(f"GPU acceleration failed for {output_format}, falling back to CPU")

            pass



        # CPU fallback paths

        if output_format.lower() == "avi":

            cpu_cmd = [ffmpeg_path, "-i", input_path,

                       "-c:v", "mpeg4", "-q:v", "5", "-c:a", "mp3", "-y", output_path]

        elif output_format.lower() == "webm":

            cpu_cmd = [ffmpeg_path, "-i", input_path,

                       "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0",

                       "-c:a", "libopus", "-b:a", "128k",

                       "-y", output_path]

        elif output_format.lower() == "flv":

            # Proper CPU fallback for FLV

            cpu_cmd = [ffmpeg_path, "-i", input_path,

                       "-c:v", "libx264", "-profile:v", "main", "-level", "3.1",

                       "-preset", "medium", "-crf", "23",

                       "-c:a", "aac", "-b:a", "128k",

                       "-f", "flv",  # Force FLV format

                       "-y", output_path]

        else:

            cpu_cmd = [ffmpeg_path, "-i", input_path,

                       "-c:v", "libx264", "-preset", "medium", "-crf", "23",

                       "-c:a", "aac", "-b:a", "192k",

                       "-y", output_path]

        subprocess.run(cpu_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)

    except Exception:

        raise





def initialize_ffmpeg_paths():

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





def convert_audio(input_paths: list, output_folder: str, output_format: str,

                  progress_var: tk.IntVar, convert_button: tk.Button, use_gpu: bool) -> None:

    try:

        ffmpeg_path, ffprobe_path = initialize_ffmpeg_paths()

        os.makedirs(output_folder, exist_ok=True)

        from pydub.utils import mediainfo

        AudioSegment.converter = ffmpeg_path

        AudioSegment.ffmpeg = ffmpeg_path

        AudioSegment.ffprobe = ffprobe_path



        audio_formats = ["wav", "ogg", "flac", "mp3", "m4a"]

        video_formats = ["mp4", "avi", "mov", "mkv", "webm", "flv"]



        def update_button(text: str, bg: str = "#D8BFD8"):

            safe_update_ui(lambda: convert_button.config(text=text, bg=bg, fg="white"))



        def update_status(text: str):

            safe_update_ui(lambda: youtube_status_label.config(text=text))



        update_button("Converting...")

        total_files = len(input_paths)

        warned = False



        for idx, original_path in enumerate(input_paths, start=1):

            file_name = os.path.basename(original_path)

            try:

                input_path = safe_filename(original_path)

                file_name = os.path.basename(input_path)

                file_base, file_ext = os.path.splitext(file_name)

                input_extension = file_ext[1:].lower()

                output_file_name = f'{file_base}.{output_format}'

                output_path = os.path.join(output_folder, output_file_name)

                update_status(f"Converting file {idx}/{total_files}: {file_name}")



                if output_format not in audio_formats + video_formats:

                    raise ValueError(f"Unsupported output format: {output_format}")



                if input_extension in audio_formats and output_format in video_formats:

                    update_button("Convert", "#9370DB")

                    if not punish_user_with_maths():

                        return

                    update_button("Convert", "#9370DB")

                    return



                if input_extension in video_formats and output_format in audio_formats:

                    probe_cmd = [ffmpeg_path, "-i", input_path, "-hide_banner"]

                    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, check=False)

                    has_audio = "Stream #0" in probe_result.stderr and "Audio:" in probe_result.stderr

                    if not has_audio:

                        error_msg = (f"Cannot convert '{file_name}' to {output_format} format.\n\n"

                                     "The selected video file does not contain any audio tracks. "

                                     "Please ensure the video has audio before attempting to convert.")

                        safe_update_ui(lambda: messagebox.showwarning("No Audio Found", error_msg, parent=app))

                        return

                    ffmpeg_cmd = [ffmpeg_path, "-i", input_path, "-vn", "-y"]

                    if output_format == "mp3":

                        ffmpeg_cmd.extend(["-acodec", "libmp3lame", "-q:a", "2", "-b:a", "192k"])

                    elif output_format == "ogg":

                        ffmpeg_cmd.extend(["-acodec", "libvorbis", "-q:a", "6"])

                    elif output_format == "flac":

                        ffmpeg_cmd.extend(["-acodec", "flac"])

                    elif output_format == "wav":

                        ffmpeg_cmd.extend(["-acodec", "pcm_s16le"])

                    elif output_format == "m4a":

                        ffmpeg_cmd.extend(["-acodec", "aac", "-b:a", "192k"])

                    ffmpeg_cmd.append(output_path)

                elif input_extension in video_formats and output_format in video_formats:

                    if output_format.lower() == "webm" and not warned:

                        answer = messagebox.askyesnocancel(

                            "Warning",

                            "Converting a video to WebM using VP9 may take a very long time. Do you want to proceed?",

                            parent=app

                        )

                        if answer is None or not answer:

                            return

                        warned = True

                    direct_ffmpeg_gpu_video2video(input_path, output_path, output_format)

                    continue

                elif input_extension in audio_formats and output_format in audio_formats:

                    ffmpeg_cmd = [ffmpeg_path, "-i", input_path, "-y"]

                    if output_format == "mp3":

                        ffmpeg_cmd.extend(["-acodec", "libmp3lame", "-q:a", "2", "-b:a", "192k"])

                    elif output_format == "ogg":

                        ffmpeg_cmd.extend(["-acodec", "libvorbis", "-q:a", "6"])

                    elif output_format == "flac":

                        ffmpeg_cmd.extend(["-acodec", "flac"])

                    elif output_format == "wav":

                        ffmpeg_cmd.extend(["-acodec", "pcm_s16le"])

                    elif output_format == "m4a":

                        ffmpeg_cmd.extend(["-acodec", "aac", "-b:a", "192k"])

                    ffmpeg_cmd.append(output_path)

                else:

                    raise ValueError(f"Unrecognized conversion scenario: {input_extension} -> {output_format}")



                if "ffmpeg_cmd" in locals():

                    # For PyInstaller, ensure we use CREATE_NO_WINDOW on Windows only

                    if sys.platform == 'win32':

                        subprocess.run(ffmpeg_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW,

                                       capture_output=True, text=True, shell=False)

                    else:

                        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True, shell=False)



                progress_var.set(int((idx / total_files) * 100))

                update_button(f"Converting: {progress_var.get()}%")



            except subprocess.CalledProcessError as e:

                safe_update_ui(lambda: messagebox.showerror("Error", f"FFmpeg failed to convert {file_name}: {str(e)}",

                                                            parent=app))

                return

            except Exception as e:

                safe_update_ui(

                    lambda: messagebox.showerror("Error", f"Error converting {file_name}: {str(e)}", parent=app))

                return



        def show_completion_dialog():

            # Play notification immediately with UI update

            safe_update_ui(lambda: (

                convert_button.config(text="CONVERT", bg="#9370DB", fg="white"),

                youtube_status_label.config(text="Conversion Complete! ^.^"),

                play_notification()  # Play sound in main thread with UI update

            ))



            def prompt_open_folder():

                if messagebox.askyesnocancel("Success!", "Conversion complete! Do you want to open the output folder?",

                                             parent=app):

                    if sys.platform == 'win32':

                        os.startfile(output_folder)

                    else:

                        import subprocess

                        subprocess.Popen(['xdg-open', output_folder])

                convert_button.config(text="CONVERT", bg="#9370DB", fg="white")

                app.update_idletasks()



            global bad_apple_overlay

            if bad_apple_overlay is not None and bad_apple_overlay.winfo_exists():

                bad_apple_overlay.bind("<Destroy>", lambda event: prompt_open_folder())

            else:

                app.after(100, prompt_open_folder)  # Short delay ensures sound starts first



        safe_update_ui(show_completion_dialog)

    except Exception as e:

        safe_update_ui(lambda: messagebox.showerror("Error", f"Conversion failed: {str(e)}", parent=app))

        traceback.print_exc()





def punish_user_with_maths() -> bool:

    result = [False]



    def show_math_dialog():

        messagebox.showinfo("WOAH THERE HOLD YOUR HORSES FRIEND",

                            "Converting an audio file to a video file is literally not a thing. Ok, let's test your brain.",

                            parent=app)

        while True:

            a = random.randint(1, 10)

            b = random.randint(1, 10)

            question = f"Solve this: {a} + {b} = ?"

            user_answer = simpledialog.askinteger("The clock is ticking...", question, parent=app)

            if user_answer is None:

                messagebox.showinfo("bruh...", "lmao ok sorry it's too hard for you.", parent=app)

                app.destroy()

                return

            if user_answer == a + b:

                messagebox.showinfo("Finally.", "That was so hard? Now don't ever do that again.", parent=app)

                result[0] = True

                return

            else:

                retry = messagebox.askretrycancel("Dude....", "Seriously..? It's basic addition.", parent=app)

                if not retry:

                    messagebox.showinfo("bruh...", "ok bye", parent=app)

                    app.destroy()

                    return



    app.after(0, show_math_dialog)

    while app.winfo_exists():

        app.update()

        if result[0]:

            return True

        time.sleep(0.1)

    return False





# UI Event Handlers

def on_drop(event) -> None:

    try:

        files = app.tk.splitlist(event.data)

        input_entry.delete(0, tk.END)

        input_entry.insert(0, ";".join(files))

    except Exception as e:

        messagebox.showerror("Error", f"Failed to process dropped files: {e}", parent=app)





def select_input() -> None:

    input_selected = filedialog.askopenfilenames(

        filetypes=[("Media files", "*.mp3;*.wav;*.ogg;*.flac;*.m4a;*.mp4;*.avi;*.mov;*.mkv;*.webm;*.flv")]

    )

    if input_selected:

        input_entry.delete(0, tk.END)

        input_entry.insert(0, ";".join(input_selected))





def select_output_folder() -> None:

    folder_selected = filedialog.askdirectory()

    if folder_selected:

        output_folder_entry.delete(0, tk.END)

        output_folder_entry.insert(0, folder_selected)

        add_recent_folder(folder_selected)





def start_conversion() -> None:

    input_paths = input_entry.get().strip().split(";")

    output_folder = output_folder_entry.get().strip()

    if output_folder and os.path.isdir(output_folder):

        add_recent_folder(output_folder)

    output_format = format_dropdown.get()

    valid_formats = ["wav", "ogg", "flac", "mp3", "m4a", "mp4", "mkv", "avi", "mov", "webm", "flv"]

    if not input_paths or not input_paths[0]:

        messagebox.showerror("Error", "Please select input files.", parent=app)

        return

    if not output_folder:

        messagebox.showerror("Error", "Please select an output folder.", parent=app)

        return

    if not output_format or output_format not in valid_formats:

        messagebox.showerror("Error", "Please select a valid output format.", parent=app)

        return

    use_gpu = gpu_var.get()

    progress_var.set(0)



    def conversion_thread():

        convert_audio(input_paths, output_folder, output_format, progress_var, convert_button, use_gpu)



    thread = threading.Thread(target=conversion_thread, daemon=True)

    thread.start()





def toggle_interface(enabled: bool = True) -> None:

    widgets = [input_entry, output_folder_entry, youtube_link_entry, format_dropdown, convert_button, gpu_checkbox]

    state = 'normal' if enabled else 'disabled'

    for widget in widgets:

        widget.configure(state=state)

    for button in [b for b in app.winfo_children() if isinstance(b, tk.Button)]:

        button.configure(state=state)





# Helper function for time formatting

def format_time(seconds):

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





# Track playlist progress globally

def create_or_update_progress_bar():

    """Create or update a progress bar for playlist downloads"""

    global progress_frame, progress_var, regular_font



    # Check if progress frame exists

    if 'progress_frame' not in globals() or not progress_frame or not progress_frame.winfo_exists():

        # Create new progress frame

        progress_frame = tk.Frame(app, bg="#E6E6FA")

        progress_frame.grid(row=5, column=0, sticky="ew", pady=(10, 0), padx=20)



        # Create label for the progress bar

        # If regular_font is not available yet, use a fallback font

        font_to_use = regular_font if regular_font else tkFont.Font(family="Arial", size=14)

        progress_label = tk.Label(progress_frame, text="Playlist Progress:", bg="#E6E6FA", font=font_to_use)

        progress_label.grid(row=0, column=0, sticky="w", pady=(5, 0))



        # Create and configure the progress bar

        progress_var = tk.IntVar(value=0)

        progress_bar = ttk.Progressbar(progress_frame, variable=progress_var,

                                       length=100, mode="determinate", maximum=100)

        progress_bar.grid(row=1, column=0, sticky="ew", pady=(5, 10))



        # Make the progress bar expand to fill the width

        progress_frame.grid_columnconfigure(0, weight=1)



        app.update_idletasks()

    else:

        # Reset the progress value

        progress_var.set(0)

        app.update_idletasks()





# Download-specific functions

def on_youtube_format_change(event=None):

    audio_formats = ["mp3", "wav", "flac", "ogg", "m4a"]

    video_quality_options = ["Best", "4K", "1440p", "1080p", "720p", "480p"]

    audio_bitrates = ["128kb/s", "192kb/s", "256kb/s", "320kb/s"]

    selected_format = youtube_format_var.get()

    if selected_format in audio_formats:

        youtube_quality_dropdown['values'] = audio_bitrates

        youtube_quality_var.set("256kb/s")

    else:

        youtube_quality_dropdown['values'] = video_quality_options

        youtube_quality_var.set("1080p")





def get_format_string(quality, format_type):
    """
    Returns the format string for yt-dlp based on selected quality and format type,
    ensuring audio is always included.
    """
    audio_formats = ["mp3", "wav", "flac", "ogg", "m4a"]
    if format_type in audio_formats:
        return "bestaudio/best"

    # For video, always explicitly include audio
    if format_type == "mp4":
        # The key here is to use the + syntax to ensure video AND audio are downloaded
        quality_map = {
            "Best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "4K": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160]/best",
            "1440p": "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/best[height<=1440]/best",
            "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
            "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
            "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]/best"
        }
        return quality_map.get(quality, "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best")
    else:
        # For other formats, ensure audio is explicitly included
        quality_map = {
            "Best": "bestvideo+bestaudio/best",
            "4K": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
            "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        }
        return quality_map.get(quality, "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best")


def modify_download_options(ydl_opts, quality, format_type, playlist_action='single'):
    """
    Configures yt-dlp options based on format and playlist settings with improved format support
    and proper audio inclusion.

    Args:
        ydl_opts: The base options dictionary
        quality: Quality setting string
        format_type: Format type string
        playlist_action: One of 'single', 'playlist', or 'none'
    """
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
            # If this is a video in a playlist, update the output template to include playlist info
            if 'watch' in ydl_opts.get('webpage_url', '') and 'list=' in ydl_opts.get('webpage_url', ''):
                ydl_opts['outtmpl'] = '%(playlist_title)s/%(playlist_index)s-%(title)s.%(ext)s'
            else:
                ydl_opts['outtmpl'] = '%(playlist_title)s/%(playlist_index)s-%(title)s.%(ext)s'
        elif playlist_action == 'single':
            ydl_opts['noplaylist'] = True
            ydl_opts['outtmpl'] = '%(title)s.%(ext)s'
        else:  # 'none' - should never reach here, but just in case
            return None

        is_youtube_music = 'music.youtube.com' in ydl_opts.get('webpage_url', '')
        audio_formats = ["mp3", "wav", "flac", "ogg", "m4a"]

        parsed_url = urlparse(ydl_opts.get('webpage_url', ''))
        netloc = parsed_url.netloc.lower()

        if any(d in netloc for d in ["soundcloud.com", "snd.sc", "bandcamp.com"]):
            if format_type not in audio_formats:
                format_type = "mp3"
                youtube_format_var.set("mp3")
                messagebox.showinfo("Format Changed",
                                    "That website only supports audio files, so defaulting to mp3",
                                    parent=app)

        if format_type in audio_formats or is_youtube_music:
            # Improved audio processing
            bitrate_str = quality.replace("kb/s", "").strip()
            if not bitrate_str.isdigit():
                bitrate_str = "192"  # Default to 192kbps if invalid

            # Add appropriate postprocessors for audio formats
            audio_postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_type if format_type in audio_formats else 'mp3',
                'preferredquality': bitrate_str,
                'nopostoverwrites': False
            }]

            # Add appropriate metadata processor for music
            if is_youtube_music or any(d in netloc for d in ["soundcloud.com", "bandcamp.com"]):
                audio_postprocessors.append({
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                })

            # Add thumbnail embedding for MP3 format
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
            # Video format handling with improved audio inclusion
            format_string = get_format_string(quality, format_type)

            # Ensure we're always explicitly requesting audio
            if 'bestaudio' not in format_string:
                format_string = format_string.replace('bestvideo', 'bestvideo+bestaudio')

            video_postprocessors = [{
                'key': 'FFmpegVideoRemuxer',
                'preferedformat': format_type
            }]

            # Format-specific customizations
            if format_type == 'mp4':
                # Optimized for Premiere Pro compatibility with proper audio
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': [
                        '-c:v', 'libx264',
                        '-profile:v', 'high',
                        '-level', '4.0',
                        '-pix_fmt', 'yuv420p',  # Ensure compatible pixel format
                        '-vsync', 'cfr',  # Force constant frame rate
                        '-r', '30',  # Set to common 30fps
                        '-c:a', 'aac',
                        '-b:a', '192k',
                        '-ar', '48000',  # Standard audio sample rate
                        '-movflags', '+faststart'  # Optimize for streaming/playback
                    ],
                    'FFmpegMerger': [
                        '-c:v', 'copy',
                        '-c:a', 'aac',
                        '-b:a', '192k',
                        '-strict', 'experimental'
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
            elif format_type == 'mkv':
                # MKV with settings good for editing and proper audio
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': [
                        '-c:v', 'libx264',
                        '-profile:v', 'high',
                        '-pix_fmt', 'yuv420p',
                        '-vsync', 'cfr',
                        '-r', '30',
                        '-c:a', 'aac',
                        '-b:a', '192k',
                        '-ar', '48000'
                    ]
                }
            elif format_type == 'webm':
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': [
                        '-c:v', 'libvpx-vp9',
                        '-crf', '30',
                        '-b:v', '0',
                        '-c:a', 'libopus',
                        '-b:a', '128k'
                    ]
                }
            elif format_type == 'flv':
                # Improved FLV format support with appropriate codec settings
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': [
                        '-c:v', 'libx264',
                        '-profile:v', 'main',
                        '-level', '3.1',
                        '-preset', 'medium',
                        '-crf', '23',
                        '-c:a', 'aac',
                        '-b:a', '128k',
                        '-f', 'flv'  # Force FLV container format
                    ]
                }

            # YouTube-specific handling to ensure audio is included
            if "youtube.com" in netloc or "youtu.be" in netloc:
                # For YouTube, always force merge_output_format and ensure proper merging
                ydl_opts.update({
                    'format': format_string,
                    'merge_output_format': format_type,
                    'format_sort': ['res', 'fps', 'codec:h264', 'size'],
                    'postprocessors': video_postprocessors
                })

                # Add fallback format in case the primary format is unavailable
                ydl_opts['format_sort_force'] = False  # Don't strictly enforce format sorting
            else:
                # For non-YouTube sites
                ydl_opts.update({
                    'format': format_string,
                    'merge_output_format': format_type,
                    'postprocessors': video_postprocessors
                })

        # Add better error reporting
        ydl_opts['logger'] = logging.getLogger('yt-dlp')

        return ydl_opts
    except Exception as e:
        logging.error(f"Error in modify_download_options: {e}", exc_info=True)
        messagebox.showerror("Download Configuration Error",
                             f"Error setting up download options: {str(e)}\n\nUsing default settings instead.",
                             parent=app)
        # Return basic options as fallback
        return {
            'format': 'bestvideo+bestaudio/best',  # Always include audio
            'outtmpl': '%(title)s.%(ext)s',
            'noplaylist': True if playlist_action == 'single' else False,
            'ffmpeg_location': ffmpeg_path,
            'progress_hooks': ydl_opts.get('progress_hooks', [])
        }

def yt_dlp_progress_hook(d: dict) -> None:

    global playlist_current_index, playlist_total_count, download_started_time



    def update():

        global playlist_current_index, playlist_total_count, download_started_time



        info_dict = d.get('info_dict', {})

        video_title = info_dict.get('title', '').strip()



        # Format title for display

        display_title = ""

        if video_title:

            # Truncate title if it's too long

            if len(video_title) > 30:

                display_title = video_title[:27] + "..."

            else:

                display_title = video_title



        # Get playlist information

        playlist_index = info_dict.get('playlist_index')

        playlist_count = info_dict.get('n_entries')



        # Update our global tracking variables if we have valid playlist info

        if playlist_index and playlist_count:

            playlist_current_index = playlist_index

            playlist_total_count = playlist_count



            # Initialize start time when we begin downloading the first video

            if playlist_index == 1 and d['status'] == 'downloading' and not download_started_time:

                download_started_time = time.time()



        # Calculate elapsed time and estimate total time for playlist

        elapsed_time_str = ""

        estimated_total_str = ""

        if playlist_current_index > 1 and playlist_total_count > 0 and download_started_time:

            elapsed_time = time.time() - download_started_time

            elapsed_time_str = format_time(elapsed_time)



            # Estimate total time based on current progress

            if playlist_current_index > 1:  # Need at least one completed download to estimate

                avg_time_per_video = elapsed_time / (playlist_current_index - 1)

                remaining_videos = playlist_total_count - playlist_current_index + 1

                estimated_total = avg_time_per_video * playlist_total_count

                estimated_remaining = avg_time_per_video * remaining_videos



                estimated_total_str = f", Est. total: {format_time(estimated_total)}"

                estimated_remaining_str = f", Remaining: ~{format_time(estimated_remaining)}"

                elapsed_time_str = f" | Elapsed: {elapsed_time_str}{estimated_remaining_str}"



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



            # Create a more informative status text

            if playlist_current_index and playlist_total_count:

                progress_percent = (playlist_current_index - 1 + (d.get('downloaded_bytes', 0) /

                                                                  (d.get('total_bytes', 1) or d.get(

                                                                      'total_bytes_estimate',

                                                                      1)))) / playlist_total_count * 100



                status_text = f"Downloading {playlist_current_index}/{playlist_total_count} ({progress_percent:.1f}%)"

                if display_title:

                    status_text += f" - {display_title}"

                status_text += f"{size_str} - {p} @ {s} (ETA: {eta}){elapsed_time_str}"



                # Update the progress bar if we have one

                if 'progress_var' in globals() and progress_var is not None:

                    progress_var.set(int(progress_percent))



                button_text = f"Playlist: {int(progress_percent)}%"

            else:

                status_text = f"Downloading... {p} @ {s} (ETA: {eta})"

                button_text = "CONVERT"



            youtube_status_label.config(text=status_text)

            convert_button.config(text=button_text, fg="white", bg="#9370DB")



        elif d['status'] == 'finished':

            if playlist_current_index and playlist_total_count:

                progress_percent = playlist_current_index / playlist_total_count * 100

                status_text = f"Processed {playlist_current_index}/{playlist_total_count} ({progress_percent:.1f}%)"

                if display_title:

                    status_text += f" - {display_title}"

                status_text += elapsed_time_str



                # Update the progress bar

                if 'progress_var' in globals() and progress_var is not None:

                    progress_var.set(int(progress_percent))

            else:

                status_text = f"Big brain flex o.o: {display_title}" if display_title else "Processing complete..."



            youtube_status_label.config(text=status_text)



        elif d['status'] == 'error':

            error_msg = d.get('error', 'Unknown error')

            youtube_status_label.config(text=f"Error: {error_msg}")

            convert_button.config(text="CONVERT", fg="white")



            # Log error details

            logging.error(f"Download error: {error_msg}")



    safe_update_ui(update)





def download_video():

    global youtube_format_var, youtube_quality_var, youtube_quality_dropdown, playlist_current_index, playlist_total_count, download_started_time



    # Reset playlist tracking variables

    playlist_current_index = 0

    playlist_total_count = 0

    download_started_time = None



    input_url = youtube_link_entry.get().strip()

    if not input_url:

        messagebox.showerror("Lunatic Alert", "This is clearly not a valid video URL lol")

        return

    if not is_valid_url(input_url):

        supported_platforms = [

            'YouTube', 'YouTube Music', 'Twitch VOD', 'Twitter', 'TikTok', 'Dailymotion', 'Vimeo', 'Instagram Reels',

            'Facebook', 'SoundCloud', 'Bandcamp', 'Reddit', 'OK.ru', 'Rumble'

        ]

        messagebox.showerror("Error",

                             f"Please provide a valid URL from a supported platform:\n\n{', '.join(supported_platforms)}.")

        return

    output_folder = output_folder_entry.get().strip()

    if output_folder and os.path.isdir(output_folder):

        add_recent_folder(output_folder)

    if not output_folder:

        messagebox.showerror("Error", "Please select an output folder.")

        return



    # Analyze the URL to determine if it's a playlist page or a video that's part of a playlist

    is_playlist_page, is_video_in_playlist = analyze_playlist_url(input_url)



    # Set default playlist action

    playlist_action = 'single'  # Default to just downloading the current video



    # Handle playlist scenarios

    if is_playlist_page or is_video_in_playlist:

        safe_update_ui(lambda: youtube_status_label.config(text="Analyzing playlist..."))

        app.update_idletasks()



        # Get information about the playlist with a timeout to prevent hanging

        playlist_info = get_playlist_info(input_url)

        playlist_count = playlist_info.get('count', 0)

        playlist_title = playlist_info.get('title', 'Unknown Playlist')

        current_index = playlist_info.get('current_index', 1)



        # Format the count display text appropriately

        count_text = f"with {playlist_count} videos" if playlist_count > 0 else "with multiple videos"

        if playlist_count == -1:  # Unknown count

            count_text = "(YouTube limited playlist information)"



        if is_playlist_page:

            # This is a full playlist URL

            playlist_choice = messagebox.askyesno(

                "Hey look a playlist!",

                f"This is a playlist: \"{playlist_title}\" {count_text}.\n\n"

                f"Do you wanna download the entire playlist?",

                parent=app

            )



            if playlist_choice:

                playlist_action = 'playlist'  # Download the entire playlist

            else:

                # User said no, do nothing

                safe_update_ui(lambda: youtube_status_label.config(text="Download Status: Idle"))

                return



        elif is_video_in_playlist:

            # This is a video that's part of a playlist

            # Prepare message with playlist info

            message = (f"This video is part of a playlist: \"{playlist_title}\" {count_text}.\n\n")



            if current_index > 0:

                message += f"This is video #{current_index} in the playlist.\n\n"



            message += "What are we gonna do?"



            # Create custom dialog for the three options

            dialog = tk.Toplevel(app)

            dialog.title("Video in Playlist")

            dialog.geometry("400x200")

            dialog.transient(app)

            dialog.grab_set()

            dialog.resizable(False, False)



            # Center on parent window

            x = app.winfo_x() + (app.winfo_width() // 2) - 200

            y = app.winfo_y() + (app.winfo_height() // 2) - 100

            dialog.geometry(f"+{x}+{y}")



            # Message label

            tk.Label(dialog, text=message, wraplength=380, justify="left", padx=10, pady=10).pack()



            # Define a variable to store the result

            result = [None]  # Use a list to make it mutable in inner functions



            # Button functions

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



            # Handle dialog closing via window manager

            dialog.protocol("WM_DELETE_WINDOW", lambda: set_result("none"))



            # Wait for the dialog to be closed

            app.wait_window(dialog)



            # Process the result

            if result[0] == "none" or result[0] is None:

                # User canceled, do nothing

                safe_update_ui(lambda: youtube_status_label.config(text="Download Status: Idle"))

                return



            playlist_action = result[0]



    try:

        format_type = youtube_format_var.get()

        quality = youtube_quality_var.get()

        if 'music.youtube.com' in input_url and format_type not in ['mp3', 'wav', 'flac', 'ogg', 'm4a']:

            safe_update_ui(

                lambda: youtube_status_label.config(text="Extracting Playlist Data - This may take a while..."))

            format_type = 'mp3'

            youtube_format_var.set('mp3')

            messagebox.showinfo("Format Changed",

                                'YouTube Music detected - defaulting to mp3. This may take a while, the program is not crashing even if it says "not responding" lol')

    except Exception:

        messagebox.showerror("Error", "Failed to get format or quality settings. Please try again.")

        return



    # Pass necessary variables to the thread function

    def download_thread():

        global playlist_current_index, playlist_total_count, download_started_time



        # Store local copies of variables from outer scope

        thread_format_type = format_type

        thread_quality = quality

        thread_playlist_action = playlist_action

        thread_input_url = input_url

        thread_output_folder = output_folder



        # Reset global tracking variables

        playlist_current_index = 0

        playlist_total_count = 0

        download_started_time = None



        try:

            ffmpeg_path = get_ffmpeg_path()

            os.environ['PATH'] = os.path.dirname(ffmpeg_path) + os.pathsep + os.environ['PATH']



            # Create a progress bar frame if it doesn't exist

            if thread_playlist_action == 'playlist':

                safe_update_ui(lambda: create_or_update_progress_bar())



            # Parse the URL for site-specific optimizations

            parsed_url = urlparse(thread_input_url)

            netloc = parsed_url.netloc.lower()



            # Determine if this is a special site that needs custom handling

            is_youtube = any(domain in netloc for domain in ['youtube.com', 'youtu.be', 'music.youtube.com'])

            is_twitter = any(domain in netloc for domain in ['twitter.com', 'x.com'])

            is_tiktok = 'tiktok.com' in netloc

            is_instagram = 'instagram.com' in netloc

            is_audio_only = any(domain in netloc for domain in ['soundcloud.com', 'snd.sc', 'bandcamp.com'])



            # Base yt-dlp options with improved error handling

            ydl_opts = {

                'paths': {'home': thread_output_folder, 'temp': thread_output_folder},

                'progress_hooks': [yt_dlp_progress_hook],

                'ignoreerrors': True,

                'overwrites': True,

                'max_sleep_interval': 1,

                'min_sleep_interval': 1,

                'extractor_retries': 5,

                'webpage_url': thread_input_url,

                'verbose': False,

                'socket_timeout': 15,  # Reasonable timeout

                'retries': 3,  # Number of retries for HTTP requests

                'fragment_retries': 3,  # Number of retries for fragments

            }



            # Show initial status message

            safe_update_ui(lambda: youtube_status_label.config(

                text="Analyzing video information..."))



            # Apply site-specific optimizations

            if is_audio_only:

                # Force audio format for audio-only sites

                if thread_format_type not in ['mp3', 'wav', 'flac', 'ogg', 'm4a']:

                    thread_format_type = 'mp3'

                    safe_update_ui(lambda: youtube_format_var.set('mp3'))

                    safe_update_ui(lambda: youtube_status_label.config(

                        text="Alert! Audio-only site detected - using mp3 format"))

                    safe_update_ui(lambda: messagebox.showinfo("Format Changed",

                                                               "This site only supports audio files silly. Defaulting to mp3",

                                                               parent=app))



            elif is_youtube:

                # YouTube-specific options

                ydl_opts.update({

                    'retries': 10,  # YouTube needs more retries

                    'fragment_retries': 10,

                    'external_downloader_args': {'ffmpeg_i': ['-timeout', '60000000', '-thread_queue_size', '10000']},

                })



            elif is_twitter or is_instagram:

                # Twitter/Instagram specific options (they often have issues)

                ydl_opts.update({

                    'retries': 5,

                    'fragment_retries': 10,

                    'external_downloader_args': {'ffmpeg_i': ['-timeout', '30000000']},

                })



            elif is_tiktok:

                # TikTok specific options

                ydl_opts.update({

                    'retries': 8,

                    'fragment_retries': 8,

                    'external_downloader_args': {'ffmpeg_i': ['-timeout', '30000000']},

                })



            # First try to get basic information without downloading

            try:

                with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl_pre:

                    info = ydl_pre.extract_info(thread_input_url, download=False, process=False)



                # Check for Easter Egg

                title = info.get('title', '').lower()

                if "bad apple" in title:

                    show_bad_apple_easter_egg()



                # Set download status message based on playlist_action

                if thread_playlist_action == 'playlist':

                    # Handle playlist information

                    if info.get('_type') == 'playlist':

                        playlist_count = info.get('playlist_count') or len(info.get('entries', []))

                        playlist_title = info.get('title', 'playlist')



                        if playlist_count > 0:

                            safe_update_ui(lambda: youtube_status_label.config(

                                text=f"Preparing to download {playlist_count} videos from \"{playlist_title}\"..."))

                            # Set the global count for progress tracking

                            playlist_total_count = playlist_count

                        else:

                            safe_update_ui(lambda: youtube_status_label.config(

                                text=f"Preparing to download playlist videos... This might take a while."))

                    else:

                        safe_update_ui(lambda: youtube_status_label.config(

                            text=f"Preparing to download playlist videos... This might take a while."))



                    # Add specific options for playlist downloads to make them more reliable

                    ydl_opts.update({

                        'socket_timeout': 30,

                        'retries': 10,

                        'fragment_retries': 10,

                        'retry_sleep_functions': {'fragment': lambda n: 5},

                        'concurrent_fragment_downloads': 1,  # Reduce concurrent downloads to avoid throttling

                        'logger': logging.getLogger('yt-dlp'),

                        'progress_with_newline': True,

                        'noprogress': False

                    })

            except Exception as e:

                logging.error(f"Error extracting info: {e}")

                safe_update_ui(lambda: youtube_status_label.config(

                    text=f"Proceeding with limited information... (Error: {str(e)[:50]}...)"))



            # Configure the download options based on format and playlist settings

            ydl_opts = modify_download_options(ydl_opts, thread_quality, thread_format_type, thread_playlist_action)



            # Initialize download start time

            download_started_time = time.time()



            # Function to periodically update UI during long operations

            def update_ui_periodically():

                if thread_playlist_action == 'playlist' and not download_started_time:

                    # Only show this message if we haven't started downloading yet

                    safe_update_ui(lambda: youtube_status_label.config(

                        text=f"Still extracting playlist information... Please wait."))

                    # Schedule another update

                    app.after(2000, update_ui_periodically)



            # Start periodic updates

            if thread_playlist_action == 'playlist':

                update_ui_periodically()



            # Start the download with enhanced error handling

            try:

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:

                    ydl.download([thread_input_url])

            except yt_dlp.utils.DownloadError as e:

                # Process the error to determine if it's a site-specific issue

                error_str = str(e).lower()



                if "youtube" in error_str and "throttling" in error_str:

                    safe_update_ui(lambda: messagebox.showerror("YouTube Error",

                                                                "YouTube is rate limiting downloads. Please try again later.",

                                                                parent=app))

                elif "copyright" in error_str:

                    safe_update_ui(lambda: messagebox.showerror("Copyright Restriction",

                                                                "This content is restricted due to copyright. It cannot be downloaded.",

                                                                parent=app))

                elif "private" in error_str or "unavailable" in error_str:

                    safe_update_ui(lambda: messagebox.showerror("Content Unavailable",

                                                                "This content is private or unavailable for download.",

                                                                parent=app))

                elif "network" in error_str or "connection" in error_str or "timeout" in error_str:

                    safe_update_ui(lambda: messagebox.showerror("Network Error",

                                                                "Connection failed. Please check your internet connection and try again.",

                                                                parent=app))

                else:

                    # Generic error with full details

                    safe_update_ui(lambda: messagebox.showerror("Download Error",

                                                                f"Failed to download: {str(e)}\n\nPlease try again or check for application updates.",

                                                                parent=app))

                raise  # Re-raise to be caught by the outer exception handler



            def prompt_user():

                safe_update_ui(lambda: youtube_status_label.config(text="Download Complete! ^.^"))



                # Play notification sound

                notification_sound = get_notification_sound_path()

                if notification_sound:

                    play_notification()



                if messagebox.askyesnocancel("Yippee!", "Do you wanna open the output folder?", parent=app):

                    if sys.platform == 'win32':

                        os.startfile(thread_output_folder)

                    else:

                        import subprocess

                        subprocess.Popen(['xdg-open', thread_output_folder])

                safe_update_ui(lambda: toggle_interface(True))

                safe_update_ui(lambda: convert_button.config(text="CONVERT", fg="white"))



            global bad_apple_overlay

            if bad_apple_overlay is not None and bad_apple_overlay.winfo_exists():

                bad_apple_overlay.bind("<Destroy>", lambda event: prompt_user())

            else:

                prompt_user()

        except yt_dlp.utils.DownloadError as download_error:

            # This block will only be reached if the inner exception handler didn't handle it

            safe_update_ui(lambda: youtube_status_label.config(text="Download failed!"))

            safe_update_ui(

                lambda: messagebox.showerror("Download Error",

                                             "Unable to download video. The service may have changed its API or the video may be unavailable."))

        except Exception as general_error:

            safe_update_ui(lambda: youtube_status_label.config(text="Error occurred!"))

            safe_update_ui(lambda: messagebox.showerror("Error",

                                                        f"An unexpected error occurred: {str(general_error)}\n\nPlease check logs for details."))

            logging.error(f"Unexpected error in download_thread: {general_error}", exc_info=True)

        finally:

            safe_update_ui(lambda: toggle_interface(True))

            safe_update_ui(lambda: convert_button.config(text="CONVERT", fg="white"))



    toggle_interface(False)

    if 'list=' not in input_url:

        safe_update_ui(lambda: youtube_status_label.config(text="Processing URL..."))

    app.update_idletasks()

    thread = threading.Thread(target=download_thread, daemon=True)

    thread.start()





# Main Application Setup

def setup_fonts() -> tuple:

    global title_font, regular_font

    try:

        import ctypes

        import ctypes.wintypes

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

    try:

        if getattr(sys, 'frozen', False):

            # Use the directory where the executable is located to find tcl_dnd.

            base_path = os.path.dirname(sys.executable)

            tcl_dnd_path = os.path.join(base_path, "tkinterdnd2", "tkdnd", "win-x64")

            os.environ["TCLLIBPATH"] = tcl_dnd_path



        # Load icon using resource_path

        icon_path = resource_path(os.path.join('assets', 'icons', 'icon.png'))

        if os.path.exists(icon_path):

            icon_img = PhotoImage(file=icon_path)

            app.iconphoto(False, icon_img)

            app.call('wm', 'iconphoto', app._w, '-default', icon_img)

        else:

            logging.error(f"Icon not found at: {icon_path}")



        app.title(f"Hey besties let's convert those files (v{CURRENT_VERSION})")

        app.configure(bg="#E6E6FA")

        app.geometry("700x550")

        app.minsize(900, 875)

        app.resizable(True, True)



        app.drop_target_register(DND_FILES)

        app.dnd_bind("<<Drop>>", on_drop)

    except Exception as e:

        logging.error(f"Error setting up main window: {e}")

        # Continue without customizations if there are errors





def create_ui_components() -> None:

    global title_font, regular_font

    global input_entry, output_folder_entry, youtube_link_entry, format_dropdown

    global convert_button, gpu_checkbox, youtube_status_label, progress_var

    global youtube_format_var, youtube_quality_var, youtube_quality_dropdown

    global gpu_var, format_var  # Ensure gpu_var is included in globals



    title_font, regular_font = setup_fonts()

    menubar = tk.Menu(app)

    app.config(menu=menubar)

    add_update_menu(app, menubar)

    setup_auto_update_checker(app)



    # Define the create_recent_folders_button function here, after regular_font is available

    def create_recent_folders_button(parent, row, column):

        """Create a button that shows recent folders in a dropdown"""

        global recent_folders_menu



        # Create menu

        recent_folders_menu = tk.Menu(app, tearoff=0)

        update_recent_folders_menu()



        # Create button that shows menu on click

        button = tk.Button(

            parent,

            text="Recent",

            bg="#DDA0DD",

            fg="white",

            font=regular_font,

            command=lambda: show_recent_folders_menu(button)

        )

        button.grid(row=row, column=column, padx=5, pady=10)

        return button



    youtube_format_var = tk.StringVar(value="mp4")

    youtube_quality_var = tk.StringVar(value="1080p")



    main_frame = tk.Frame(app, bg="#E6E6FA")

    main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    main_frame.grid_columnconfigure(0, weight=1)



    header_label = tk.Label(main_frame, text="Lace's Total File Converter", font=title_font, bg="#E6E6FA", fg="#6A0DAD")

    header_label.grid(row=0, column=0, columnspan=3, pady=(0, 20), sticky="ew")



    # REARRANGED ORDER: Video Download is now first (row 1)

    video_frame = tk.LabelFrame(main_frame, text="Video Download", bg="#E6E6FA", font=regular_font, fg="#6A0DAD",

                                pady=10)

    video_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 20))

    video_frame.grid_columnconfigure(1, weight=1)



    tk.Label(video_frame, text="Video URL:", bg="#E6E6FA", font=regular_font).grid(row=0, column=0, padx=10, pady=5,

                                                                                   sticky="w")

    youtube_link_entry = tk.Entry(video_frame, width=50, font=regular_font)

    youtube_link_entry.grid(row=0, column=1, columnspan=2, padx=10, pady=5, sticky="ew")



    supported_platforms = tk.Label(video_frame,

                                   text="Supports nearly every major video and audio platform",

                                   bg="#E6E6FA", font=regular_font, fg="#666666")

    supported_platforms.grid(row=1, column=0, columnspan=3, pady=(0, 5), sticky="w", padx=10)



    options_frame = tk.Frame(video_frame, bg="#E6E6FA")

    options_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)

    options_frame.grid_columnconfigure(1, weight=1)

    options_frame.grid_columnconfigure(3, weight=1)



    tk.Label(options_frame, text="Format:", bg="#E6E6FA", font=regular_font).grid(row=0, column=0, padx=10, sticky="w")

    youtube_format_dropdown = ttk.Combobox(options_frame, textvariable=youtube_format_var,

                                           values=["mp4", "mkv", "webm", "avi", "flv", "mp3", "wav", "flac", "ogg",

                                                   "m4a"],

                                           font=regular_font, state="readonly")

    youtube_format_dropdown.grid(row=0, column=1, padx=10, sticky="ew")

    youtube_format_dropdown.bind("<<ComboboxSelected>>", on_youtube_format_change)



    tk.Label(options_frame, text="Quality:", bg="#E6E6FA", font=regular_font).grid(row=0, column=2, padx=10, sticky="w")

    youtube_quality_dropdown = ttk.Combobox(options_frame, textvariable=youtube_quality_var,

                                            values=["Best", "4K", "1440p", "1080p", "720p", "480p"],

                                            font=regular_font, state="readonly")

    youtube_quality_dropdown.grid(row=0, column=3, padx=10, sticky="ew")

    on_youtube_format_change()



    tk.Button(video_frame, text="DOWNLOAD", command=download_video, bg="#9370DB", fg="white", font=regular_font).grid(

        row=3, column=0, columnspan=3, pady=10, sticky="ew")



    # REARRANGED ORDER: File Conversion is now second (row 2)

    conversion_frame = tk.LabelFrame(main_frame, text="File Conversion", bg="#E6E6FA", font=regular_font, fg="#6A0DAD",

                                     pady=10)

    conversion_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 20))

    conversion_frame.grid_columnconfigure(1, weight=1)



    tk.Label(conversion_frame, text="Input Files:", bg="#E6E6FA", font=regular_font).grid(row=0, column=0, padx=10,

                                                                                          pady=5, sticky="w")

    input_entry = tk.Entry(conversion_frame, width=50, font=regular_font)

    input_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

    tk.Button(conversion_frame, text="Browse", command=select_input, bg="#DDA0DD", fg="white", font=regular_font).grid(

        row=0, column=2, padx=10, pady=5)



    tk.Label(conversion_frame, text="Output Format:", bg="#E6E6FA", font=regular_font).grid(row=1, column=0, padx=10,

                                                                                            pady=5, sticky="w")

    format_dropdown = ttk.Combobox(conversion_frame, textvariable=format_var,

                                   values=["wav", "ogg", "flac", "mp3", "m4a", "mp4", "mkv", "avi", "mov", "webm",

                                           "flv"],

                                   font=regular_font, state="readonly")

    format_dropdown.grid(row=1, column=1, padx=10, pady=5, sticky="ew")



    convert_button = tk.Button(conversion_frame, text="CONVERT", command=start_conversion, bg="#9370DB", fg="white",

                               font=regular_font)

    convert_button.grid(row=2, column=0, columnspan=3, pady=10, sticky="ew")



    # REARRANGED ORDER: Output Location is now third (row 3)

    output_frame = tk.LabelFrame(main_frame, text="Output Location", bg="#E6E6FA", font=regular_font, fg="#6A0DAD",

                                 pady=10)

    output_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 20))

    output_frame.grid_columnconfigure(1, weight=1)



    tk.Label(output_frame, text="Output Folder:", bg="#E6E6FA", font=regular_font).grid(row=0, column=0, padx=10,

                                                                                        pady=10, sticky="w")

    output_folder_entry = tk.Entry(output_frame, width=50, font=regular_font)

    output_folder_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

    tk.Button(output_frame, text="Browse", command=select_output_folder, bg="#DDA0DD", fg="white",

              font=regular_font).grid(row=0, column=2, padx=10, pady=10)



    # Create Recent Folders button

    create_recent_folders_button(output_frame, 0, 3)



    # Bottom frame stays at the bottom (row 4)

    bottom_frame = tk.Frame(main_frame, bg="#E6E6FA")

    bottom_frame.grid(row=4, column=0, sticky="ew", pady=(0, 10))

    bottom_frame.grid_columnconfigure(0, weight=1)



    # Don't create a new gpu_var, use the existing one

    gpu_checkbox = tk.Checkbutton(bottom_frame, text="GPU Encode (Significantly Faster)", bg="#E6E6FA",

                                  font=regular_font, variable=gpu_var)

    gpu_checkbox.grid(row=0, column=0, pady=5, sticky="ew")



    youtube_status_label = tk.Label(bottom_frame, text="Download Status: Idle", bg="#E6E6FA", font=regular_font)

    youtube_status_label.grid(row=1, column=0, pady=5, sticky="ew")



    app.grid_rowconfigure(0, weight=1)

    app.grid_columnconfigure(0, weight=1)





def initialize_output_folder():

    """Set the output folder entry to the most recent folder, if available"""

    settings = load_settings()

    recent_folders = settings.get("recent_folders", [])



    if recent_folders:

        most_recent_folder = recent_folders[0]

        output_folder_entry.delete(0, tk.END)

        output_folder_entry.insert(0, most_recent_folder)





def play_notification():

    """Play the pre-loaded notification sound"""

    global notification_player, notification_sound_loaded



    if notification_sound_loaded and notification_player:

        try:

            notification_player.stop()  # Stop any currently playing sound

            notification_player.play()  # Start playback

            return True

        except Exception as e:

            logging.error(f"Error playing notification: {e}")

    return False





if __name__ == "__main__":

    try:

        app = TkinterDnD.Tk()



        # Load application settings

        app_settings = load_settings()



        # Initialize variables with values from settings

        format_var = tk.StringVar(value=app_settings.get("default_format", "mp4"))

        gpu_var = tk.BooleanVar(value=app_settings.get("use_gpu", True))

        progress_var = tk.IntVar()



        # Initialize fonts early

        title_font, regular_font = setup_fonts()



        # Initialize the audio player after UI is ready

        app.after(500, initialize_audio_player)



        verify_video_setup()

        try:

            ffmpeg_path, ffprobe_path = initialize_ffmpeg_paths()

        except FileNotFoundError as e:

            messagebox.showerror("FFmpeg Error", str(e))

            sys.exit(1)

        setup_main_window()

        create_ui_components()

        update_recent_folders_menu()  # Initialize the menu after UI is created



        # Set the output folder to the most recent folder

        initialize_output_folder()



        app.mainloop()

    except Exception:

        log_errors()

        messagebox.showerror("Error", "Something went wrong. Check error_log.txt")