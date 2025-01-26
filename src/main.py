#!/usr/bin/env python3

# =================================
# Imports and Constants
# =================================

# Standard library imports
import os
import re
import sys
import time
import random
import threading
import subprocess
from urllib.parse import urlparse

# Third-party imports
import requests
import webbrowser
import packaging.version as version
import yt_dlp
from pydub import AudioSegment
from moviepy.editor import VideoFileClip

# Tkinter imports
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter import font as tkFont, PhotoImage, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

# Application Constants
CURRENT_VERSION = "1.1.5"
ITCH_GAME_URL = "https://laceediting.itch.io/laces-total-file-converter"
ITCH_API_KEY = "TLSrZ5K4iHauDMTTqS9xfpBAx1Tsc6NPgTFrvcgj"
ITCH_GAME_ID = "3268562"

#=================================
# Globals
#=================================
# Initialize global variables for UI components
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
app = None

# =================================
# Utility Functions
# =================================
def safe_update_ui(func) -> None:
    """Safely update UI elements from any thread."""
    if not isinstance(func, str):
        app.after(0, func)
    else:
        def update():
            eval(func)

        app.after(0, update)


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)

def is_valid_youtube_url(url: str) -> bool:
    """Validate if a given URL is a valid YouTube URL."""
    try:
        parsed_url = urlparse(url)
        return bool(
            parsed_url.scheme and
            parsed_url.netloc and
            ('youtube.com' in parsed_url.netloc or 'youtu.be' in parsed_url.netloc)
        )
    except:
        return False

# =================================
# Update System Functions
# =================================
def handle_auto_update(latest_version: str) -> None:
    """Handle the update process."""
    try:
        webbrowser.open(ITCH_GAME_URL)
        messagebox.showinfo(title="brb", message="This application will now close lol")
        app.quit()
        sys.exit(0)
    except Exception as e:
        messagebox.showerror("Update Error", f"Failed to initialize update: {str(e)}")

def check_for_updates(app) -> bool:
    """Check for updates using itch.io's API."""
    try:
        safe_update_ui(lambda: youtube_status_label.config(text="Checking for updates..."))

        api_url = f"https://itch.io/api/1/{ITCH_API_KEY}/game/{ITCH_GAME_ID}/uploads"
        response = requests.get(api_url, headers={"Content-Type": "application/json"}, timeout=5)
        response.raise_for_status()

        print("API Response:", response.text)
        uploads_data = response.json()
        print("Uploads Data:", uploads_data)

        if 'uploads' in uploads_data:
            latest_upload = max(
                uploads_data['uploads'],
                key=lambda x: x.get('created_at', '')
            )

            filename = latest_upload.get('filename', '')
            print("Latest filename:", filename)
            version_match = re.search(r'v(\d+\.\d+(?:\.\d+)?)', filename)

            if version_match:
                latest_version = version_match.group(1)
                current_ver = version.parse(CURRENT_VERSION)
                latest_ver = version.parse(latest_version)

                print(f"Current version: {current_ver}, Latest version: {latest_ver}")

                if latest_ver > current_ver:
                    update_message = f"""
A new version ({latest_version}) is available!
You're currently running version {CURRENT_VERSION}

Go to latest version's download page?
"""
                    if messagebox.askyesno("Update Available", update_message, parent=app):
                        handle_auto_update(latest_version)
                    return True

            safe_update_ui(lambda: youtube_status_label.config(text="You're running the latest version!"))
        return False

    except requests.RequestException as e:
        print(f"Failed to check for updates: {e}")
        safe_update_ui(lambda: youtube_status_label.config(text="Update check failed - will try again later"))
        return False
    except Exception as e:
        print(f"Unexpected error checking for updates: {e}")
        return False
    finally:
        app.after(3000, lambda: safe_update_ui(
            lambda: youtube_status_label.config(text="YouTube Status: Idle")
        ))


def setup_auto_update_checker(app) -> None:
    """Set up automatic update checking."""
    app.after(1000, lambda: check_for_updates(app))

    def schedule_next_check():
        check_for_updates(app)
        app.after(86400000, schedule_next_check)

    app.after(86400000, schedule_next_check)

def show_about() -> None:
    """Show the About dialog."""
    messagebox.showinfo(
        "About",
        f"Lace's Total File Converter v{CURRENT_VERSION}\n\n"
        "A friendly file converter for all your media needs!\n\n"
        "Created with ♥ by Lace"
    )

def add_update_menu(app, menubar) -> None:
    """Add the update menu to the menubar."""
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
def direct_ffmpeg_gpu_video2video(input_path: str, output_path: str) -> None:
    """Execute FFmpeg command for GPU-accelerated video conversion."""
    cmd = [
        "ffmpeg",
        "-hwaccel", "cuda",
        "-hwaccel_output_format", "cuda",
        "-i", input_path,
        "-c:v", "h264_nvenc",
        "-preset", "p1",
        "-tune", "hq",
        "-rc", "vbr",
        "-cq", "23",
        "-b:v", "0",
        "-maxrate", "130M",
        "-bufsize", "130M",
        "-spatial-aq", "1",
        "-c:a", "aac",
        "-b:a", "192k",
        "-y",
        output_path
    ]
    print("Running ffmpeg command:", " ".join(cmd))
    subprocess.run(cmd, check=True)

def convert_audio(input_paths: list, output_folder: str, output_format: str,
                 progress_var: tk.IntVar, convert_button: tk.Button, use_gpu: bool) -> None:
    """Convert audio/video files to the specified format."""
    os.makedirs(output_folder, exist_ok=True)

    audio_formats = ["wav", "ogg", "flac", "mp3"]
    video_formats = ["mp4", "avi", "mov"]

    def update_button(text: str, bg: str = "#D8BFD8") -> None:
        safe_update_ui(lambda: convert_button.config(text=text, bg=bg, fg="white"))

    def update_status(text: str) -> None:
        safe_update_ui(lambda: youtube_status_label.config(text=text))

    update_button("Converting...")
    total_files = len(input_paths)

    for idx, input_path in enumerate(input_paths, start=1):
        file_name = os.path.basename(input_path)
        input_extension = os.path.splitext(file_name)[1][1:].lower()
        output_file_name = os.path.splitext(file_name)[0] + f'.{output_format}'
        output_path = os.path.join(output_folder, output_file_name)

        update_status(f"Converting file {idx}/{total_files}: {file_name}")

        # Handle invalid conversion attempt (audio to video)
        if input_extension in audio_formats and output_format in video_formats:
            update_button("Convert", "#9370DB")
            success = app.after(0, punish_user_with_maths)
            if not success:
                return
            update_button("Convert", "#9370DB")
            return

        try:
            # Handle video to audio conversion
            if input_extension in video_formats and output_format in audio_formats:
                ffmpeg_cmd = ["ffmpeg", "-i", input_path, "-vn"]

                # Format-specific settings
                if output_format == "mp3":
                    ffmpeg_cmd.extend([
                        "-acodec", "libmp3lame",
                        "-q:a", "2",
                        "-b:a", "192k"
                    ])
                elif output_format == "ogg":
                    ffmpeg_cmd.extend([
                        "-acodec", "libvorbis",
                        "-q:a", "6",
                        "-b:a", "192k"
                    ])
                elif output_format == "wav":
                    ffmpeg_cmd.extend([
                        "-acodec", "pcm_s16le",
                        "-ar", "44100"
                    ])
                elif output_format == "flac":
                    ffmpeg_cmd.extend([
                        "-acodec", "flac",
                        "-compression_level", "8"
                    ])

                ffmpeg_cmd.extend(["-y", output_path])
                print("Running command:", " ".join(ffmpeg_cmd))
                subprocess.run(ffmpeg_cmd, check=True)

            # Handle video to video conversion
            elif input_extension in video_formats and output_format in video_formats:
                if use_gpu:
                    def monitor_progress():
                        output_size = 0
                        while True:
                            if os.path.exists(output_path):
                                new_size = os.path.getsize(output_path)
                                if new_size != output_size:
                                    output_size = new_size
                                    safe_update_ui(lambda: convert_button.config(
                                        text=f"Converting {idx}/{total_files} ({output_size / 1024 / 1024:.1f} MB)",
                                        fg="white"
                                    ))
                            time.sleep(0.5)

                    monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
                    monitor_thread.start()
                    direct_ffmpeg_gpu_video2video(input_path, output_path)
                else:
                    video_clip = VideoFileClip(input_path)
                    video_clip.write_videofile(
                        output_path,
                        codec='libx264',
                        fps=video_clip.fps or 30,
                        logger=None
                    )
                    video_clip.close()

            # Handle audio to audio conversion
            elif input_extension in audio_formats and output_format in audio_formats:
                audio = AudioSegment.from_file(input_path)
                audio.export(output_path, format=output_format)

            progress_var.set(int((idx / total_files) * 100))
            if not use_gpu or input_extension not in video_formats:
                update_button(f"Converting: {progress_var.get()}%")

            print(f"Processed: {file_name} -> {output_file_name}")

        except subprocess.CalledProcessError as e:
            safe_update_ui(lambda: messagebox.showerror(
                "Conversion Error",
                f"FFmpeg failed to convert {file_name}: {e}",
                parent=app
            ))
        except Exception as e:
            safe_update_ui(lambda: messagebox.showerror(
                "Error",
                f"Error converting {file_name}: {e}",
                parent=app
            ))

    def show_completion_dialog():
        convert_button.config(text="CONVERT", bg="#9370DB", fg="white")
        youtube_status_label.config(text="Conversion Complete!")

        if messagebox.askyesno(
                "Success!",
                "Conversion complete! Do you want to open the output folder?",
                parent=app
        ):
            os.startfile(output_folder)

        convert_button.config(text="CONVERT", bg="#9370DB", fg="white")
        app.update_idletasks()

    safe_update_ui(show_completion_dialog)

def punish_user_with_maths() -> bool:
    """Present the user with math problems as a consequence of invalid operations."""
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

            user_answer = simpledialog.askinteger(
                "The clock is ticking...",
                question,
                parent=app
            )

            if user_answer is None:
                messagebox.showinfo(
                    "bruh...",
                    "lmao ok sorry it's too hard for you.",
                    parent=app
                )
                app.destroy()
                return

            if user_answer == a + b:
                messagebox.showinfo(
                    "Finally.",
                    "There was that so hard? Now don't ever do that again.",
                    parent=app
                )
                result[0] = True
                return
            else:
                retry = messagebox.askretrycancel(
                    "Dude....",
                    "Seriously..? Come on man it's basic addition",
                    parent=app
                )
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
    """Handle drag and drop file events."""
    try:
        files = app.tk.splitlist(event.data)
        input_entry.delete(0, tk.END)
        input_entry.insert(0, ";".join(files))
    except Exception as e:
        messagebox.showerror(
            "Error",
            f"Failed to process dropped files: {e}",
            parent=app
        )

def select_input() -> None:
    """Handle input file selection."""
    input_selected = filedialog.askopenfilenames(
        filetypes=[("Media files", "*.mp3;*.wav;*.ogg;*.flac;*.mp4;*.avi;*.mov")]
    )
    if input_selected:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, ";".join(input_selected))

def select_output_folder() -> None:
    """Handle output folder selection."""
    folder_selected = filedialog.askdirectory()
    output_folder_entry.delete(0, tk.END)
    output_folder_entry.insert(0, folder_selected)

def start_conversion() -> None:
    """Start the conversion process."""
    input_paths = input_entry.get().strip().split(";")
    output_folder = output_folder_entry.get().strip()
    output_format = format_var.get()

    if not input_paths or not output_folder:
        messagebox.showerror(
            "Error",
            "Please select input and output paths.",
            parent=app
        )
        return

    if output_format not in ["wav", "ogg", "flac", "mp3", "mp4", "avi", "mov"]:
        messagebox.showerror(
            "Error",
            "Invalid format. Please select a valid format.",
            parent=app
        )
        return

    use_gpu = gpu_var.get()
    progress_var.set(0)

    def conversion_thread():
        convert_audio(input_paths, output_folder, output_format, progress_var, convert_button, use_gpu)

    thread = threading.Thread(target=conversion_thread, daemon=True)
    thread.start()

def toggle_interface(enabled: bool = True) -> None:
    """Enable or disable all UI elements."""
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
# YouTube Functions
#=================================
def yt_dlp_progress_hook(d: dict) -> None:
    """Progress hook for YouTube downloads."""
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
            youtube_status_label.config(text="Processing download...")
        elif d['status'] == 'error':
            youtube_status_label.config(text="Download error!")
            convert_button.config(text="CONVERT", fg="white")

    safe_update_ui(update)

def download_youtube() -> None:
    """Handle YouTube video/playlist downloads."""
    input_url = youtube_link_entry.get().strip()
    if not input_url:
        messagebox.showerror("Error", "Please provide a YouTube URL.")
        return

    if not is_valid_youtube_url(input_url):
        messagebox.showerror("Error", "Please provide a valid YouTube URL.")
        return

    output_folder = output_folder_entry.get().strip()
    if not output_folder:
        messagebox.showerror("Error", "Please select an output folder.")
        return

    toggle_interface(False)
    youtube_status_label.config(text="Analyzing video URL...")
    app.update_idletasks()

    def download_thread():
        try:
            download_url = input_url
            is_direct_playlist = download_url.startswith('https://www.youtube.com/playlist?list=')
            playlist_id = None

            # Handle direct playlist URLs
            if is_direct_playlist:
                with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    playlist_info = ydl.extract_info(download_url, download=False)
                    if not messagebox.askyesno(
                            "Playlist Download",
                            f"This playlist contains {len(playlist_info['entries'])} videos.\nDo you want to download the entire playlist?",
                            parent=app
                    ):
                        safe_update_ui(lambda: toggle_interface(True))
                        return

            # Handle URLs with playlist parameters
            elif '&list=' in download_url:
                try:
                    playlist_id = download_url.split('&list=')[1].split('&')[0]
                    playlist_url = f'https://www.youtube.com/playlist?list={playlist_id}'

                    with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                        playlist_info = ydl.extract_info(playlist_url, download=False)

                        choice = messagebox.askyesnocancel(
                            "PLAYLIST DETECTED! ALERT!",
                            f"This video is part of a playlist with {len(playlist_info['entries'])} videos.\n"
                            f"Would you like to:\n"
                            f"- Click 'Yes' to download the entire playlist\n"
                            f"- Click 'No' to download only this video\n"
                            f"- Click 'Cancel' to run away",
                            parent=app
                        )

                        if choice is None:
                            safe_update_ui(lambda: toggle_interface(True))
                            return

                        if choice:  # User chose to download playlist
                            download_url = playlist_url
                        else:  # User chose to download single video
                            download_url = download_url.split('&list=')[0]
                except IndexError:
                    safe_update_ui(lambda: messagebox.showerror("Error", "Invalid playlist URL format"))
                    safe_update_ui(lambda: toggle_interface(True))
                    return

            # Set up download options
            if download_url.startswith('https://www.youtube.com/playlist?list='):
                safe_update_ui(lambda: youtube_status_label.config(text="Downloading playlist..."))
                ydl_opts = {
                    'paths': {'home': output_folder, 'temp': output_folder},
                    'outtmpl': '%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s',
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
                    'merge_output_format': 'mp4',
                    'noplaylist': False,
                    'progress_hooks': [yt_dlp_progress_hook],
                    'postprocessors': [
                        {'key': 'FFmpegMerger'},
                        {'key': 'FFmpegMetadata'}
                    ],
                    'ignoreerrors': True,
                    'geo_bypass': True,
                    'geo_bypass_country': 'US'
                }
            else:
                safe_update_ui(lambda: youtube_status_label.config(text="Downloading single video..."))
                ydl_opts = {
                    'paths': {'home': output_folder, 'temp': output_folder},
                    'outtmpl': '%(title)s.%(ext)s',
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
                    'merge_output_format': 'mp4',
                    'noplaylist': True,
                    'progress_hooks': [yt_dlp_progress_hook],
                    'postprocessors': [
                        {'key': 'FFmpegMerger'},
                        {'key': 'FFmpegMetadata'}
                    ],
                    'geo_bypass': True,
                    'geo_bypass_country': 'US'
                }

            # Execute download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([download_url])

            safe_update_ui(lambda: youtube_status_label.config(text="Download Complete!"))
            if messagebox.askyesno("Success!", "Do you wanna open the output folder?"):
                os.startfile(output_folder)

        except Exception as e:
            error_msg = str(e)
            if "WinError 2" in error_msg:
                safe_update_ui(lambda: youtube_status_label.config(text="Download Complete! ^.^"))
                if messagebox.askyesno("Success!", "Do you want to open the output folder?"):
                    os.startfile(output_folder)
            else:
                safe_update_ui(lambda: youtube_status_label.config(text="Error occurred!"))
                safe_update_ui(lambda: messagebox.showerror("Duplication Error!",
                    f"Whatever you just tried to download is already in the folder lol"))

        finally:
            safe_update_ui(lambda: toggle_interface(True))
            safe_update_ui(lambda: convert_button.config(text="CONVERT", fg="white"))

    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()

# =================================
# Main Application Setup
# =================================
def setup_fonts() -> tuple:
    """Initialize and return the application fonts."""
    return (
        tkFont.Font(family="Bubblegum Sans", size=32),  # title_font
        tkFont.Font(family="Bartino Regular", size=14)  # regular_font
    )


def setup_main_window() -> None:
    """Initialize the main application window."""
    # Handle PyInstaller binaries
    if hasattr(sys, "_MEIPASS"):
        tcl_dnd_path = os.path.join(sys._MEIPASS, "tkinterdnd2", "tkdnd", "win-x64")
        os.environ["TCLLIBPATH"] = tcl_dnd_path
        print("Set TCLLIBPATH to", tcl_dnd_path)

    # Configure the main window
    icon_path = resource_path(os.path.join('../assets', 'icons', 'icon.png'))
    icon_img = PhotoImage(file=icon_path)
    app.iconphoto(False, icon_img)
    app.title(f"Hey besties let's convert those files (v{CURRENT_VERSION})")
    app.configure(bg="#E6E6FA")
    app.geometry("700x400")
    app.minsize(900, 450)
    app.resizable(True, True)

    # Set up drag and drop
    app.call('wm', 'iconphoto', app._w, '-default', icon_img)
    app.drop_target_register(DND_FILES)
    app.dnd_bind("<<Drop>>", on_drop)


def create_ui_components() -> None:
    """Create and layout all UI components."""
    title_font, regular_font = setup_fonts()

    # Create menu bar
    menubar = tk.Menu(app)
    app.config(menu=menubar)
    add_update_menu(app, menubar)
    setup_auto_update_checker(app)

    # Header Section
    header_label = tk.Label(app, text="Lace's Total File Converter",
                            font=title_font, bg="#E6E6FA", fg="#6A0DAD")
    header_label.grid(row=0, column=0, columnspan=3, pady=20, sticky="ew")

    # Assign to global variables
    global input_entry, output_folder_entry, youtube_link_entry, format_dropdown
    global convert_button, gpu_checkbox, youtube_status_label

    # Input File Section
    tk.Label(app, text="Input Files:", bg="#E6E6FA", font=regular_font).grid(
        row=1, column=0, padx=10, pady=5, sticky="ew")
    input_entry = tk.Entry(app, width=50, font=regular_font)
    input_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
    tk.Button(app, text="Browse", command=select_input,
              bg="#DDA0DD", fg="white", font=regular_font).grid(
        row=1, column=2, padx=10, pady=5)

    # Output Folder Section
    tk.Label(app, text="Output Folder:", bg="#E6E6FA", font=regular_font).grid(
        row=2, column=0, padx=10, pady=5, sticky="ew")
    output_folder_entry = tk.Entry(app, width=50, font=regular_font)
    output_folder_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
    tk.Button(app, text="Browse", command=select_output_folder,
              bg="#DDA0DD", fg="white", font=regular_font).grid(
        row=2, column=2, padx=10, pady=5)

    # Output Format Section
    tk.Label(app, text="Output Format:", bg="#E6E6FA", font=regular_font).grid(
        row=3, column=0, padx=10, pady=5, sticky="ew")
    format_var = tk.StringVar()
    format_dropdown = ttk.Combobox(
        app,
        textvariable=format_var,
        values=["wav", "ogg", "flac", "mp3", "mp4", "avi", "mov"],
        font=regular_font
    )
    format_dropdown.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

    # YouTube Link Section
    tk.Label(app, text="YouTube Link:", bg="#E6E6FA", font=regular_font).grid(
        row=4, column=0, padx=10, pady=5, sticky="ew")
    youtube_link_entry = tk.Entry(app, width=50, font=regular_font)
    youtube_link_entry.grid(row=4, column=1, padx=10, pady=5, sticky="ew")
    tk.Button(app, text="Download", command=download_youtube,
              bg="#DDA0DD", fg="white", font=regular_font).grid(
        row=4, column=2, padx=10, pady=5)

    # Convert Button Section
    progress_var = tk.IntVar()
    convert_button = tk.Button(app, text="CONVERT", command=start_conversion,
                               bg="#9370DB", fg="white", font=regular_font)
    convert_button.grid(row=5, column=0, columnspan=3, pady=10, sticky="ew")

    # GPU Configuration Section
    gpu_var = tk.BooleanVar(value=True)
    gpu_checkbox = tk.Checkbutton(
        app, text="GPU Encode (Significantly Faster)", bg="#E6E6FA",
        font=regular_font, variable=gpu_var
    )
    gpu_checkbox.grid(row=6, column=0, columnspan=3, pady=5, sticky="ew")

    # YouTube Status Section
    youtube_status_label = tk.Label(text="YouTube Status: Idle",
                                    bg="#E6E6FA", font=regular_font)
    youtube_status_label.grid(row=7, column=0, columnspan=3, pady=5, sticky="ew")

    # Configure grid weights
    app.grid_columnconfigure(0, weight=1)
    app.grid_columnconfigure(1, weight=1)
    app.grid_columnconfigure(2, weight=1)


# =================================
# Application Entry Point
# =================================
if __name__ == "__main__":
    # Initialize main window
    app = TkinterDnD.Tk()

    # Initialize variables
    format_var = tk.StringVar()
    gpu_var = tk.BooleanVar(value=True)
    progress_var = tk.IntVar()

    setup_main_window()
    create_ui_components()

    app.mainloop()