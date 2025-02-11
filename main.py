import os
import re
import sys
import time
import random
import threading
import subprocess
from urllib.parse import urlparse

import requests
import webbrowser
import packaging.version as version
import yt_dlp
import pydub
from pydub import AudioSegment

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter import font as tkFont, PhotoImage, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

import traceback
import logging

# Sets up loging for debug purposes or scary random crashes
logging.basicConfig(level=logging.INFO)

# Application Constants
CURRENT_VERSION = "1.5.0"
ITCH_GAME_URL = "https://laceediting.itch.io/laces-total-file-converter"
ITCH_API_KEY = "TLSrZ5K4iHauDMTTqS9xfpBAx1Tsc6NPgTFrvcgj"
ITCH_GAME_ID = "3268562"

#=================================
# Globals for Tkinter references
#=================================
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
app = None

# =================================
# Utility Functions
# =================================
def log_errors():
    with open("error_log.txt", "w") as f:
        f.write(traceback.format_exc())

def get_ffmpeg_path():
    # Gets the correct ffmpeg path based on the user's OS
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        possible_paths = [
            os.path.join(base_path, 'ffmpeg', 'ffmpeg.exe'),
            os.path.join(base_path, 'ffmpeg.exe'),
            os.path.join(os.path.dirname(sys.executable), 'ffmpeg.exe')
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        raise FileNotFoundError(
            "FFmpeg not found in any expected location:\n" +
            "\n".join(f"- {p}" for p in possible_paths)
        )
    else:
        if sys.platform == 'win32':
            from shutil import which
            ffmpeg_path = which('ffmpeg.exe')
            if ffmpeg_path:
                return ffmpeg_path
            raise FileNotFoundError(
                "FFmpeg not found in PATH. Please ensure FFmpeg is installed "
                "and added to your system PATH."
            )
        return "ffmpeg"

FFMPEG_PATH = get_ffmpeg_path()
subprocess.run([FFMPEG_PATH, "-version"], check=True)

def safe_update_ui(func) -> None:
    # Safely updates UI elements from any CPU thread
    if not isinstance(func, str):
        app.after(0, func)
    else:
        def update():
            eval(func)
        app.after(0, update)

def resource_path(relative_path: str) -> str:
    # Gets the absolute path to the resource, works for dev and for PyInstaller
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)

def is_valid_url(input_url):
    # Validates URLs to ensure they're actually supported
    supported_domains = [
        'youtube.com', 'youtu.be',
        'music.youtube.com',
        'twitter.com', 'x.com',
        'tiktok.com',
        'dailymotion.com', 'dai.ly',
        'vimeo.com',
        'instagram.com/reels', 'instagram.com/reel',
        'twitch.tv'
    ]
    try:
        parsed_url = urlparse(input_url)
        cleaned_path = parsed_url.path.split('?')[0]
        return any(domain in parsed_url.netloc + cleaned_path for domain in supported_domains)
    except Exception:
        return False

def initialize_pydub():
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        pydub.AudioSegment.converter = os.path.join(base_path, 'ffmpeg.exe')
        pydub.AudioSegment.ffmpeg = os.path.join(base_path, 'ffmpeg.exe')
        pydub.AudioSegment.ffprobe = os.path.join(base_path, 'ffprobe.exe')

# =================================
# Update System Functions
# =================================
def handle_auto_update(latest_version: str) -> None:
    # Handles the update process
    try:
        webbrowser.open(ITCH_GAME_URL)
        messagebox.showinfo(title="brb", message="This application will now close lol")
        app.quit()
        sys.exit(0)
    except Exception as e:
        messagebox.showerror("Update Error", f"Failed to initialize update: {str(e)}")

def check_for_updates(app) -> bool:
    # Uses Itch.io's API to check for updates
    try:
        safe_update_ui(lambda: youtube_status_label.config(text="Hmmm..."))
        api_url = f"https://itch.io/api/1/{ITCH_API_KEY}/game/{ITCH_GAME_ID}/uploads"
        response = requests.get(api_url, headers={"Content-Type": "application/json"}, timeout=5)
        response.raise_for_status()
        uploads_data = response.json()
        if 'uploads' in uploads_data:
            latest_upload = max(uploads_data['uploads'], key=lambda x: x.get('created_at', ''))
            filename = latest_upload.get('filename', '')
            version_match = re.search(r'v(\d+\.\d+(?:\.\d+)?)', filename)
            if version_match:
                latest_version = version_match.group(1)
                current_ver = version.parse(CURRENT_VERSION)
                latest_ver = version.parse(latest_version)
                if latest_ver > current_ver:
                    update_message = f"""
A new version ({latest_version}) is available!
You're currently running version {CURRENT_VERSION}

Go to latest version's download page?
"""
                    if messagebox.askyesno("Update Available", update_message, parent=app):
                        handle_auto_update(latest_version)
                    return True
            safe_update_ui(lambda: youtube_status_label.config(text="You're running the latest version! Good job!"))
        return False
    except requests.RequestException:
        safe_update_ui(lambda: youtube_status_label.config(text="Update check failed - will try again later"))
        return False
    except Exception:
        return False
    finally:
        app.after(3000, lambda: safe_update_ui(lambda: youtube_status_label.config(text="Download Status: Idle")))

def setup_auto_update_checker(app) -> None:
    app.after(1000, lambda: check_for_updates(app))
    def schedule_next_check():
        check_for_updates(app)
        app.after(86400000, schedule_next_check)
    app.after(86400000, schedule_next_check)

def show_about() -> None:
    messagebox.showinfo(
        "About",
        f"Lace's Total File Converter v{CURRENT_VERSION}\n\n"
        "A friendly file converter for all your media needs!\n\n"
        "Created with ♥ by Lace"
    )

def add_update_menu(app, menubar) -> None:
    help_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="Help", menu=help_menu)
    help_menu.add_command(label="Check for Updates", command=lambda: check_for_updates(app))
    help_menu.add_separator()
    help_menu.add_command(label="Visit Itch.io Page", command=lambda: webbrowser.open(ITCH_GAME_URL))
    help_menu.add_separator()
    help_menu.add_command(label="About", command=show_about)

#=================================
# Core Application Logic
#=================================
def direct_ffmpeg_gpu_video2video(input_path: str, output_path: str, output_format: str) -> None:
    try:
        ffmpeg_path = get_ffmpeg_path()
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if output_format.lower() == "avi":
            gpu_cmd = [ffmpeg_path, "-hwaccel", "cuda", "-i", input_path,
                       "-c:v", "mpeg4", "-q:v", "5", "-c:a", "mp3", "-y", output_path]
        else:
            gpu_cmd = [ffmpeg_path, "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
                       "-i", input_path, "-c:v", "h264_nvenc", "-preset", "p1", "-tune", "hq",
                       "-rc", "vbr", "-cq", "23", "-b:v", "0", "-maxrate", "130M",
                       "-bufsize", "130M", "-spatial-aq", "1", "-c:a", "aac", "-b:a", "192k",
                       "-y", output_path]
        try:
            subprocess.run(gpu_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return
        except subprocess.CalledProcessError:
            # Fall back to CPU encoding
            pass
        if output_format.lower() == "avi":
            cpu_cmd = [ffmpeg_path, "-i", input_path, "-c:v", "mpeg4",
                       "-q:v", "5", "-c:a", "mp3", "-y", output_path]
        else:
            cpu_cmd = [ffmpeg_path, "-i", input_path, "-c:v", "libx264",
                       "-preset", "medium", "-crf", "23", "-c:a", "aac",
                       "-b:a", "192k", "-y", output_path]
        subprocess.run(cpu_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        raise

def initialize_ffmpeg_paths():
    try:
        ffmpeg_path = get_ffmpeg_path()
        if getattr(sys, 'frozen', False):
            ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe')
        else:
            if sys.platform == 'win32':
                from shutil import which
                ffprobe_path = which('ffprobe.exe')
                if not ffprobe_path:
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

        audio_formats = ["wav", "ogg", "flac", "mp3"]
        video_formats = ["mp4", "avi", "mov"]

        def update_button(text: str, bg: str = "#D8BFD8") -> None:
            safe_update_ui(lambda: convert_button.config(text=text, bg=bg, fg="white"))

        def update_status(text: str) -> None:
            safe_update_ui(lambda: youtube_status_label.config(text=text))

        update_button("Converting...")
        total_files = len(input_paths)

        for idx, input_path in enumerate(input_paths, start=1):
            try:
                input_path = os.path.normpath(input_path).replace('"', '')
                file_name = os.path.basename(input_path)
                file_base, file_ext = os.path.splitext(file_name)
                input_extension = file_ext[1:].lower()
                output_file_name = f'{file_base}.{output_format}'
                output_path = os.path.normpath(os.path.join(output_folder, output_file_name))
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
                        error_msg = (
                            f"Cannot convert '{file_name}' to {output_format} format.\n\n"
                            "The selected video file does not contain any audio tracks. "
                            "Please ensure the video has audio before attempting to convert."
                        )
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
                    ffmpeg_cmd.append(output_path)
                elif input_extension in video_formats and output_format in video_formats:
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
                    ffmpeg_cmd.append(output_path)
                subprocess.run(ffmpeg_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
                               capture_output=True, text=True, shell=False)
                progress_var.set(int((idx / total_files) * 100))
                update_button(f"Converting: {progress_var.get()}%")
            except subprocess.CalledProcessError as e:
                error_msg = f"FFmpeg failed to convert {file_name}: {str(e)}"
                safe_update_ui(lambda: messagebox.showerror("Error", error_msg, parent=app))
                return
            except Exception as e:
                error_msg = f"Error converting {file_name}: {str(e)}"
                safe_update_ui(lambda: messagebox.showerror("Error", error_msg, parent=app))
                return

        def show_completion_dialog():
            convert_button.config(text="CONVERT", bg="#9370DB", fg="white")
            youtube_status_label.config(text="Conversion Complete! ^.^")
            if messagebox.askyesno("Success!", "Conversion complete! Do you wanna open the output folder?", parent=app):
                os.startfile(output_folder)
            convert_button.config(text="CONVERT", bg="#9370DB", fg="white")
            app.update_idletasks()

        safe_update_ui(show_completion_dialog)
    except Exception as e:
        error_msg = f"Conversion failed: {str(e)}"
        traceback.print_exc()
        safe_update_ui(lambda: messagebox.showerror("Error", error_msg, parent=app))

def punish_user_with_maths() -> bool:
    result = [False]
    def show_math_dialog():
        def show_initial_warning():
            messagebox.showinfo(
                "WOAH THERE HOLD YOUR HORSES FRIEND",
                "Converting an audio file to a video file is literally not a thing. Like... Ok actually I gotta test your brain now.",
                parent=app
            )
            return True
        if not show_initial_warning():
            messagebox.showinfo("Lol bye", "Application will now close!", parent=app)
            app.destroy()
            return
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
                messagebox.showinfo("Finally.", "There was that so hard? Now don't ever do that again.", parent=app)
                result[0] = True
                return
            else:
                retry = messagebox.askretrycancel("Dude....", "Seriously..? Come on man it's basic addition", parent=app)
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

#=================================
# UI Event Handlers
#=================================
def on_drop(event) -> None:
    try:
        files = app.tk.splitlist(event.data)
        input_entry.delete(0, tk.END)
        input_entry.insert(0, ";".join(files))
    except Exception as e:
        messagebox.showerror("Error", f"Failed to process dropped files: {e}", parent=app)

def select_input() -> None:
    input_selected = filedialog.askopenfilenames(
        filetypes=[("Media files", "*.mp3;*.wav;*.ogg;*.flac;*.mp4;*.avi;*.mov")]
    )
    if input_selected:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, ";".join(input_selected))

def select_output_folder() -> None:
    folder_selected = filedialog.askdirectory()
    output_folder_entry.delete(0, tk.END)
    output_folder_entry.insert(0, folder_selected)

def start_conversion() -> None:
    input_paths = input_entry.get().strip().split(";")
    output_folder = output_folder_entry.get().strip()
    output_format = format_dropdown.get()
    if not input_paths or not input_paths[0]:
        messagebox.showerror("Error", "Please select input files.", parent=app)
        return
    if not output_folder:
        messagebox.showerror("Error", "Please select an output folder.", parent=app)
        return
    valid_formats = ["wav", "ogg", "flac", "mp3", "mp4", "avi", "mov"]
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
    widgets = [
        input_entry, output_folder_entry, youtube_link_entry,
        format_dropdown, convert_button, gpu_checkbox
    ]
    state = 'normal' if enabled else 'disabled'
    for widget in widgets:
        widget.configure(state=state)
    buttons = [b for b in app.winfo_children() if isinstance(b, tk.Button)]
    for button in buttons:
        button.configure(state=state)

#=================================
# Download-specific functions
#=================================
def get_format_string(quality, format_type):
    audio_formats = ["mp3", "wav", "flac", "ogg"]
    if format_type in audio_formats:
        return "bestaudio/best"
    quality_map = {
        "Best": "bestvideo",
        "4K": "bestvideo[height<=2160]",
        "1440p": "bestvideo[height<=1440]",
        "1080p": "bestvideo[height<=1080]",
        "720p": "bestvideo[height<=720]",
        "480p": "bestvideo[height<=480]"
    }
    video_format = quality_map.get(quality, "bestvideo[height<=1080]")
    return f"{video_format}[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]"

def modify_download_options(ydl_opts, quality, format_type):
    try:
        ffmpeg_path = get_ffmpeg_path()
        ffprobe_path = ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe')
        ydl_opts.update({
            'ffmpeg_location': ffmpeg_path,
            'prefer_ffmpeg': True,
            'external_downloader_args': {'ffmpeg_i': ['-threads', '4']},
        })
        is_youtube_music = 'music.youtube.com' in ydl_opts.get('webpage_url', '')
        audio_formats = ["mp3", "wav", "flac", "ogg"]
        if format_type in audio_formats or is_youtube_music:
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': format_type if format_type in audio_formats else 'mp3',
                    'preferredquality': '192',
                    'nopostoverwrites': False
                }]
            })
            if is_youtube_music:
                ydl_opts['postprocessors'].append({
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                })
                if format_type == 'mp3':
                    ydl_opts['postprocessors'].append({
                        'key': 'EmbedThumbnail',
                        'already_have_thumbnail': False,
                    })
                    ydl_opts['writethumbnail'] = True
        else:
            format_string = get_format_string(quality, format_type)
            ydl_opts.update({
                'format': format_string,
                'merge_output_format': format_type,
                'postprocessors': [{
                    'key': 'FFmpegVideoRemuxer',
                    'preferedformat': format_type
                }]
            })
            if format_type == 'mp4':
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': ['-c:v', 'libx264', '-c:a', 'aac', '-b:a', '192k']
                }
            elif format_type == 'avi':
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': ['-c:v', 'mpeg4', '-c:a', 'mp3', '-q:v', '6']
                }
        return ydl_opts
    except Exception:
        raise

def yt_dlp_progress_hook(d: dict) -> None:
    def update():
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '').strip()
            s = d.get('_speed_str', '').strip()
            eta = d.get('_eta_str', '').strip()
            playlist_index = d.get('info_dict', {}).get('playlist_index')
            playlist_count = d.get('info_dict', {}).get('n_entries')
            if playlist_index and playlist_count:
                status_text = f"Downloading {playlist_index}/{playlist_count} - {p} @ {s} (ETA: {eta})"
                button_text = f"Downloading {playlist_index}/{playlist_count}"
            else:
                status_text = f"Downloading... {p} @ {s} (ETA: {eta})"
                button_text = "CONVERT"
            youtube_status_label.config(text=status_text)
            convert_button.config(text=button_text, fg="white")
        elif d['status'] == 'finished':
            youtube_status_label.config(text="Big brain flex...")
        elif d['status'] == 'error':
            youtube_status_label.config(text="AAAAAH!")
            convert_button.config(text="CONVERT", fg="white")
    safe_update_ui(update)

def download_video():
    global youtube_format_var, youtube_quality_var
    input_url = youtube_link_entry.get().strip()
    if not input_url:
        messagebox.showerror("Lunatic Alert", "This is clearly not a valid video URL lol")
        return
    if not is_valid_url(input_url):
        supported_platforms = ['YouTube', 'YouTube Music', 'Twitch VOD', 'Twitter', 'TikTok', 'Dailymotion', 'Vimeo', 'Instagram Reels']
        messagebox.showerror("Error", f"Please provide a valid video URL from a supported platform: {', '.join(supported_platforms)}.")
        return
    output_folder = output_folder_entry.get().strip()
    if not output_folder:
        messagebox.showerror("Error", "Please select an output folder.")
        return
    try:
        format_type = youtube_format_var.get()
        quality = youtube_quality_var.get()
        if 'music.youtube.com' in input_url and format_type not in ['mp3', 'wav', 'flac', 'ogg']:
            safe_update_ui(lambda: youtube_status_label.config(text="Extracting Playlist Data - This may take a while..."))
            format_type = 'mp3'
            youtube_format_var.set('mp3')
            messagebox.showinfo("Format Changed",
                                'YouTube Music detected - defaulting to mp3. This may take a while, the program is not crashing even if it says "not responding" lol')
    except Exception:
        messagebox.showerror("Error", "Failed to get format or quality settings. Please try again.")
        return
    if 'list=' in input_url:
        safe_update_ui(lambda: youtube_status_label.config(text="Extracting Playlist Data - This may take a while..."))
        app.update_idletasks()
        try:
            with yt_dlp.YoutubeDL() as ydl:
                playlist_info = ydl.extract_info(input_url, download=False)
                video_count = len(playlist_info['entries']) if 'entries' in playlist_info else 0
                if 'watch?v=' in input_url:
                    response = messagebox.askyesnocancel(
                        "Uh oh video within a playlist alert",
                        f"So this video is part of a playlist of {video_count} videos.\n\nDo you wanna download the entire playlist or just this video?\n\n"
                        "Yes - Download entire playlist\n"
                        "No - Download only this video\n"
                        "Cancel - Run away"
                    )
                    if response is None:
                        safe_update_ui(lambda: youtube_status_label.config(text="Download Status: Idle"))
                        return
                    elif response:
                        download_url = input_url
                    else:
                        download_url = input_url.split('&list=')[0]
                else:
                    if not messagebox.askyesno("uh oh playlist alert lol",
                                               f"Hey this is a playlist link containing {video_count} videos. Do you wanna download the entire playlist?"):
                        safe_update_ui(lambda: youtube_status_label.config(text="Download Status: Idle"))
                        return
                    download_url = input_url
        except Exception as e:
            safe_update_ui(lambda: youtube_status_label.config(text="Download Status: Idle"))
            messagebox.showerror("Error", f"Failed to get playlist information: {str(e)}")
            return
    else:
        download_url = input_url
    def download_thread():
        try:
            ffmpeg_path = get_ffmpeg_path()
            os.environ['PATH'] = os.path.dirname(ffmpeg_path) + os.pathsep + os.environ['PATH']
            ydl_opts = {
                'paths': {'home': output_folder, 'temp': output_folder},
                'outtmpl': '%(title)s.%(ext)s',
                'progress_hooks': [yt_dlp_progress_hook],
                'ignoreerrors': True,
                'overwrites': True,
                'max_sleep_interval': 1,
                'min_sleep_interval': 1,
                'extractor_retries': 5,
                'webpage_url': input_url
            }
            ydl_opts = modify_download_options(ydl_opts, quality, format_type)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([download_url])
            safe_update_ui(lambda: youtube_status_label.config(text="Download Complete! ^.^"))
            if messagebox.askyesno("Success!", "Do you wanna open the output folder?"):
                os.startfile(output_folder)
        except yt_dlp.utils.DownloadError as download_error:
            safe_update_ui(lambda: youtube_status_label.config(text="Download failed!"))
            safe_update_ui(lambda: messagebox.showerror("Download Error", f"Failed to download video: {str(download_error)}"))
        except Exception as general_error:
            safe_update_ui(lambda: youtube_status_label.config(text="Error occurred!"))
            safe_update_ui(lambda: messagebox.showerror("Error", f"An unexpected error occurred: {str(general_error)}"))
        finally:
            safe_update_ui(lambda: toggle_interface(True))
            safe_update_ui(lambda: convert_button.config(text="CONVERT", fg="white"))
    toggle_interface(False)
    if 'list=' not in input_url:
        youtube_status_label.config(text="Processing URL...")
    app.update_idletasks()
    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()

# =================================
# Main Application Setup
# =================================
def setup_fonts() -> tuple:
    try:
        import ctypes
        import ctypes.wintypes
        bubblegum_path = resource_path(os.path.join('assets', 'fonts', 'BubblegumSans-Regular.ttf'))
        bartino_path = resource_path(os.path.join('assets', 'fonts', 'Bartino.ttf'))
        ctypes.windll.gdi32.AddFontResourceW(bubblegum_path)
        ctypes.windll.gdi32.AddFontResourceW(bartino_path)
        title_font = tkFont.Font(family="Bubblegum Sans", size=32)
        regular_font = tkFont.Font(family="Bartino", size=14)
        return (title_font, regular_font)
    except Exception:
        return (
            tkFont.Font(family="Arial", size=32, weight="bold"),
            tkFont.Font(family="Arial", size=14)
        )

def setup_main_window() -> None:
    if hasattr(sys, "_MEIPASS"):
        tcl_dnd_path = os.path.join(sys._MEIPASS, "tkinterdnd2", "tkdnd", "win-x64")
        os.environ["TCLLIBPATH"] = tcl_dnd_path
    icon_path = resource_path(os.path.join('assets', 'icons', 'icon.png'))
    icon_img = PhotoImage(file=icon_path)
    app.iconphoto(False, icon_img)
    app.title(f"Hey besties let's convert those files (v{CURRENT_VERSION})")
    app.configure(bg="#E6E6FA")
    app.geometry("700x550")
    app.minsize(900, 875)
    app.resizable(True, True)
    app.call('wm', 'iconphoto', app._w, '-default', icon_img)
    app.drop_target_register(DND_FILES)
    app.dnd_bind("<<Drop>>", on_drop)

def create_ui_components() -> None:
    title_font, regular_font = setup_fonts()
    menubar = tk.Menu(app)
    app.config(menu=menubar)
    add_update_menu(app, menubar)
    setup_auto_update_checker(app)
    global input_entry, output_folder_entry, youtube_link_entry, format_dropdown
    global convert_button, gpu_checkbox, youtube_status_label, progress_var
    global youtube_format_var, youtube_quality_var
    youtube_format_var = tk.StringVar(value="mp4")
    youtube_quality_var = tk.StringVar(value="1080p")
    main_frame = tk.Frame(app, bg="#E6E6FA")
    main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
    main_frame.grid_columnconfigure(0, weight=1)
    header_label = tk.Label(main_frame, text="Lace's Total File Converter", font=title_font, bg="#E6E6FA", fg="#6A0DAD")
    header_label.grid(row=0, column=0, columnspan=3, pady=(0, 20), sticky="ew")
    output_frame = tk.LabelFrame(main_frame, text="Output Location", bg="#E6E6FA", font=regular_font, fg="#6A0DAD", pady=10)
    output_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 20))
    output_frame.grid_columnconfigure(1, weight=1)
    tk.Label(output_frame, text="Output Folder:", bg="#E6E6FA", font=regular_font).grid(row=0, column=0, padx=10, pady=10, sticky="w")
    output_folder_entry = tk.Entry(output_frame, width=50, font=regular_font)
    output_folder_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
    tk.Button(output_frame, text="Browse", command=select_output_folder, bg="#DDA0DD", fg="white", font=regular_font).grid(row=0, column=2, padx=10, pady=10)
    video_frame = tk.LabelFrame(main_frame, text="Video Download", bg="#E6E6FA", font=regular_font, fg="#6A0DAD", pady=10)
    video_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 20))
    video_frame.grid_columnconfigure(1, weight=1)
    tk.Label(video_frame, text="Video URL:", bg="#E6E6FA", font=regular_font).grid(row=0, column=0, padx=10, pady=5, sticky="w")
    youtube_link_entry = tk.Entry(video_frame, width=50, font=regular_font)
    youtube_link_entry.grid(row=0, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
    supported_platforms = tk.Label(video_frame,
                                   text="Supported: YouTube, Twitch, Twitter, TikTok, Instagram, Dailymotion, Vimeo",
                                   bg="#E6E6FA", font=regular_font, fg="#666666")
    supported_platforms.grid(row=1, column=0, columnspan=3, pady=(0, 5), sticky="w", padx=10)
    options_frame = tk.Frame(video_frame, bg="#E6E6FA")
    options_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)
    options_frame.grid_columnconfigure(1, weight=1)
    options_frame.grid_columnconfigure(3, weight=1)
    tk.Label(options_frame, text="Format:", bg="#E6E6FA", font=regular_font).grid(row=0, column=0, padx=10, sticky="w")
    youtube_format_var = tk.StringVar(value="mp4")
    youtube_format_dropdown = ttk.Combobox(options_frame, textvariable=youtube_format_var, values=["mp4", "avi", "mp3", "wav", "flac", "ogg"], font=regular_font, state="readonly")
    youtube_format_dropdown.grid(row=0, column=1, padx=10, sticky="ew")
    tk.Label(options_frame, text="Quality:", bg="#E6E6FA", font=regular_font).grid(row=0, column=2, padx=10, sticky="w")
    youtube_quality_var = tk.StringVar(value="1080p")
    youtube_quality_dropdown = ttk.Combobox(options_frame, textvariable=youtube_quality_var, values=["Best", "4K", "1440p", "1080p", "720p", "480p"], font=regular_font, state="readonly")
    youtube_quality_dropdown.grid(row=0, column=3, padx=10, sticky="ew")
    tk.Button(video_frame, text="DOWNLOAD", command=download_video, bg="#9370DB", fg="white", font=regular_font).grid(row=3, column=0, columnspan=3, pady=10, sticky="ew")
    conversion_frame = tk.LabelFrame(main_frame, text="File Conversion", bg="#E6E6FA", font=regular_font, fg="#6A0DAD", pady=10)
    conversion_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 20))
    conversion_frame.grid_columnconfigure(1, weight=1)
    tk.Label(conversion_frame, text="Input Files:", bg="#E6E6FA", font=regular_font).grid(row=0, column=0, padx=10, pady=5, sticky="w")
    input_entry = tk.Entry(conversion_frame, width=50, font=regular_font)
    input_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
    tk.Button(conversion_frame, text="Browse", command=select_input, bg="#DDA0DD", fg="white", font=regular_font).grid(row=0, column=2, padx=10, pady=5)
    tk.Label(conversion_frame, text="Output Format:", bg="#E6E6FA", font=regular_font).grid(row=1, column=0, padx=10, pady=5, sticky="w")
    format_var = tk.StringVar(value="mp4")
    format_dropdown = ttk.Combobox(conversion_frame, textvariable=format_var, values=["wav", "ogg", "flac", "mp3", "mp4", "avi", "mov"], font=regular_font, state="readonly")
    format_dropdown.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
    convert_button = tk.Button(conversion_frame, text="CONVERT", command=start_conversion, bg="#9370DB", fg="white", font=regular_font)
    convert_button.grid(row=2, column=0, columnspan=3, pady=10, sticky="ew")
    bottom_frame = tk.Frame(main_frame, bg="#E6E6FA")
    bottom_frame.grid(row=4, column=0, sticky="ew", pady=(0, 10))
    bottom_frame.grid_columnconfigure(0, weight=1)
    global gpu_var
    gpu_var = tk.BooleanVar(value=True)
    gpu_checkbox = tk.Checkbutton(bottom_frame, text="GPU Encode (Significantly Faster)", bg="#E6E6FA", font=regular_font, variable=gpu_var)
    gpu_checkbox.grid(row=0, column=0, pady=5, sticky="ew")
    youtube_status_label = tk.Label(bottom_frame, text="Download Status: Idle", bg="#E6E6FA", font=regular_font)
    youtube_status_label.grid(row=1, column=0, pady=5, sticky="ew")
    app.grid_rowconfigure(0, weight=1)
    app.grid_columnconfigure(0, weight=1)

if __name__ == "__main__":
    try:
        app = TkinterDnD.Tk()
        format_var = tk.StringVar()
        gpu_var = tk.BooleanVar(value=True)
        progress_var = tk.IntVar()
        try:
            ffmpeg_path, ffprobe_path = initialize_ffmpeg_paths()
        except FileNotFoundError as e:
            messagebox.showerror("FFmpeg Error", str(e))
            sys.exit(1)
        setup_main_window()
        create_ui_components()
        app.mainloop()
    except Exception:
        log_errors()
        messagebox.showerror("Error", "Something went wrong. Check error_log.txt")
