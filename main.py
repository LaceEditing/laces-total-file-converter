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
CURRENT_VERSION = "2.0.0"
ITCH_GAME_URL = "https://laceediting.itch.io/laces-total-file-converter"
ITCH_API_KEY = "TLSrZ5K4iHauDMTTqS9xfpBAx1Tsc6NPgTFrvcgj"
ITCH_GAME_ID = "3268562"

bad_apple_overlay = None

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

if sys.version_info >= (3, 8) and os.name == 'nt':
    os.add_dll_directory(os.path.abspath('.'))

def log_errors():
    with open("error_log.txt", "w") as f:
        f.write(traceback.format_exc())

def get_absolute_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def resource_path(relative_path: str) -> str:
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)

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
        base_path = sys._MEIPASS
        ffmpeg_path = os.path.join(base_path, 'ffmpeg.exe')
        if not os.path.exists(ffmpeg_path):
            raise FileNotFoundError("FFmpeg executable not found in application bundle")
        return ffmpeg_path
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        ffmpeg_path = os.path.join(base_path, 'dist', 'ffmpeg', 'bin', 'ffmpeg.exe')
        if not os.path.exists(ffmpeg_path):
            from shutil import which
            system_ffmpeg = which('ffmpeg.exe')
            if system_ffmpeg:
                return system_ffmpeg
            raise FileNotFoundError("FFmpeg not found in expected development location or system PATH.")
        return ffmpeg_path

FFMPEG_PATH = get_ffmpeg_path()
subprocess.run([FFMPEG_PATH, "-version"], check=True)

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

# Update System Functions
def handle_auto_update(latest_version: str) -> None:
    try:
        webbrowser.open(ITCH_GAME_URL)
        messagebox.showinfo(title="brb", message="This application will now close lol")
        app.quit()
        sys.exit(0)
    except Exception as e:
        messagebox.showerror("Update Error", f"Failed to initialize update: {str(e)}")

def check_for_updates(app) -> bool:
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
                    if messagebox.askyesnocancel("Update Available", update_message, parent=app):
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

# Video Playback using python-vlc
def show_vlc_overlay(video_path, duration=11):
    global bad_apple_overlay

    overlay = tk.Frame(app, bg="black")
    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
    overlay.lift()
    bad_apple_overlay = overlay

    video_frame = tk.Frame(overlay, bg="black")
    video_frame.pack(expand=True, fill="both")

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

def show_bad_apple_easter_egg():
    video_path = resource_path(os.path.join("assets", "BaddAscle.mp4"))
    logging.info(f"Verifying video at: {video_path}")
    if not os.path.exists(video_path):
        logging.error(f"Video file not found at expected path: {video_path}")
        messagebox.showerror("Easter Egg Error", "Video file not found or inaccessible. Please verify application installation.")
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
        if output_format.lower() == "webm":
            cpu_cmd = [ffmpeg_path, "-i", input_path,
                       "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0",
                       "-c:a", "libopus", "-b:a", "128k",
                       "-y", output_path]
            subprocess.run(cpu_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return
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
            pass
        if output_format.lower() == "avi":
            cpu_cmd = [ffmpeg_path, "-i", input_path,
                       "-c:v", "mpeg4", "-q:v", "5", "-c:a", "mp3", "-y", output_path]
        elif output_format.lower() == "webm":
            cpu_cmd = [ffmpeg_path, "-i", input_path,
                       "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0",
                       "-c:a", "libopus", "-b:a", "128k",
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
                    subprocess.run(ffmpeg_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
                                   capture_output=True, text=True, shell=False)

                progress_var.set(int((idx / total_files) * 100))
                update_button(f"Converting: {progress_var.get()}%")

            except subprocess.CalledProcessError as e:
                safe_update_ui(lambda: messagebox.showerror("Error", f"FFmpeg failed to convert {file_name}: {str(e)}", parent=app))
                return
            except Exception as e:
                safe_update_ui(lambda: messagebox.showerror("Error", f"Error converting {file_name}: {str(e)}", parent=app))
                return

        def show_completion_dialog():
            convert_button.config(text="CONVERT", bg="#9370DB", fg="white")
            youtube_status_label.config(text="Conversion Complete! ^.^")
            def prompt_open_folder():
                if messagebox.askyesnocancel("Success!", "Conversion complete! Do you wanna open the output folder?", parent=app):
                    os.startfile(output_folder)
                convert_button.config(text="CONVERT", bg="#9370DB", fg="white")
                app.update_idletasks()
            global bad_apple_overlay
            if bad_apple_overlay is not None and bad_apple_overlay.winfo_exists():
                bad_apple_overlay.bind("<Destroy>", lambda event: prompt_open_folder())
            else:
                prompt_open_folder()

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
    output_folder_entry.delete(0, tk.END)
    output_folder_entry.insert(0, folder_selected)

def start_conversion() -> None:
    input_paths = input_entry.get().strip().split(";")
    output_folder = output_folder_entry.get().strip()
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
    audio_formats = ["mp3", "wav", "flac", "ogg", "m4a"]
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
            bitrate_str = quality.replace("kb/s", "").strip()
            if not bitrate_str.isdigit():
                bitrate_str = "192"
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': format_type if format_type in audio_formats else 'mp3',
                    'preferredquality': bitrate_str,
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
            elif format_type == 'mkv':
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': ['-c:v', 'libx264', '-c:a', 'aac', '-b:a', '192k']
                }
            elif format_type == 'webm':
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': ['-c:v', 'libvpx-vp9', '-crf', '30', '-b:v', '0', '-c:a', 'libopus']
                }
            elif format_type == 'flv':
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': ['-c:v', 'libx264', '-c:a', 'aac', '-b:a', '192k']
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
    global youtube_format_var, youtube_quality_var, youtube_quality_dropdown
    input_url = youtube_link_entry.get().strip()
    if not input_url:
        messagebox.showerror("Lunatic Alert", "This is clearly not a valid video URL lol")
        return
    if not is_valid_url(input_url):
        supported_platforms = [
            'YouTube', 'YouTube Music', 'Twitch VOD', 'Twitter', 'TikTok', 'Dailymotion', 'Vimeo', 'Instagram Reels',
            'Facebook', 'SoundCloud', 'Bandcamp', 'Reddit', 'OK.ru', 'Rumble'
        ]
        messagebox.showerror("Error", f"Please provide a valid URL from a supported platform:\n\n{', '.join(supported_platforms)}.")
        return
    output_folder = output_folder_entry.get().strip()
    if not output_folder:
        messagebox.showerror("Error", "Please select an output folder.")
        return
    try:
        format_type = youtube_format_var.get()
        quality = youtube_quality_var.get()
        if 'music.youtube.com' in input_url and format_type not in ['mp3', 'wav', 'flac', 'ogg', 'm4a']:
            safe_update_ui(lambda: youtube_status_label.config(text="Extracting Playlist Data - This may take a while..."))
            format_type = 'mp3'
            youtube_format_var.set('mp3')
            messagebox.showinfo("Format Changed",
                                'YouTube Music detected - defaulting to mp3. This may take a while, the program is not crashing even if it says "not responding" lol')
    except Exception:
        messagebox.showerror("Error", "Failed to get format or quality settings. Please try again.")
        return

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
            with yt_dlp.YoutubeDL() as ydl_pre:
                info = ydl_pre.extract_info(input_url, download=False)
            title = info.get('title', '').lower()
            if "bad apple" in title:
                show_bad_apple_easter_egg()
            ydl_opts = modify_download_options(ydl_opts, quality, format_type)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([input_url])
            def prompt_user():
                safe_update_ui(lambda: youtube_status_label.config(text="Download Complete! ^.^"))
                if messagebox.askyesnocancel("Success!", "Do you wanna open the output folder?", parent=app):
                    os.startfile(output_folder)
                safe_update_ui(lambda: toggle_interface(True))
                safe_update_ui(lambda: convert_button.config(text="CONVERT", fg="white"))
            global bad_apple_overlay
            if bad_apple_overlay is not None and bad_apple_overlay.winfo_exists():
                bad_apple_overlay.bind("<Destroy>", lambda event: prompt_user())
            else:
                prompt_user()
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
        safe_update_ui(lambda: youtube_status_label.config(text="Processing URL..."))
    app.update_idletasks()
    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()

# Main Application Setup
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
    global youtube_format_var, youtube_quality_var, youtube_quality_dropdown

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
                                   text="Supports nearly every major video and audio platform",
                                   bg="#E6E6FA", font=regular_font, fg="#666666")
    supported_platforms.grid(row=1, column=0, columnspan=3, pady=(0, 5), sticky="w", padx=10)

    options_frame = tk.Frame(video_frame, bg="#E6E6FA")
    options_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)
    options_frame.grid_columnconfigure(1, weight=1)
    options_frame.grid_columnconfigure(3, weight=1)

    tk.Label(options_frame, text="Format:", bg="#E6E6FA", font=regular_font).grid(row=0, column=0, padx=10, sticky="w")
    youtube_format_dropdown = ttk.Combobox(options_frame, textvariable=youtube_format_var,
                                           values=["mp4", "mkv", "webm", "avi", "flv", "mp3", "wav", "flac", "ogg", "m4a"],
                                           font=regular_font, state="readonly")
    youtube_format_dropdown.grid(row=0, column=1, padx=10, sticky="ew")
    youtube_format_dropdown.bind("<<ComboboxSelected>>", on_youtube_format_change)

    tk.Label(options_frame, text="Quality:", bg="#E6E6FA", font=regular_font).grid(row=0, column=2, padx=10, sticky="w")
    youtube_quality_dropdown = ttk.Combobox(options_frame, textvariable=youtube_quality_var,
                                            values=["Best", "4K", "1440p", "1080p", "720p", "480p"],
                                            font=regular_font, state="readonly")
    youtube_quality_dropdown.grid(row=0, column=3, padx=10, sticky="ew")
    on_youtube_format_change()

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
    format_dropdown = ttk.Combobox(conversion_frame, textvariable=format_var,
                                   values=["wav", "ogg", "flac", "mp3", "m4a", "mp4", "mkv", "avi", "mov", "webm", "flv"],
                                   font=regular_font, state="readonly")
    format_dropdown.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

    convert_button = tk.Button(conversion_frame, text="CONVERT", command=start_conversion, bg="#9370DB", fg="white", font=regular_font)
    convert_button.grid(row=2, column=0, columnspan=3, pady=10, sticky="ew")

    bottom_frame = tk.Frame(main_frame, bg="#E6E6FA")
    bottom_frame.grid(row=4, column=0, sticky="ew", pady=(0, 10))
    bottom_frame.grid_columnconfigure(0, weight=1)

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
        verify_video_setup()
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
