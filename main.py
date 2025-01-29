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
import pydub
from pydub import AudioSegment

# Tkinter imports
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter import font as tkFont, PhotoImage, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

# Log imports
import traceback

# Application Constants
CURRENT_VERSION = "1.4.1"
ITCH_GAME_URL = "https://laceediting.itch.io/laces-total-file-converter"
ITCH_API_KEY = "TLSrZ5K4iHauDMTTqS9xfpBAx1Tsc6NPgTFrvcgj"
ITCH_GAME_ID = "3268562"

#=================================
# Globals
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
    """
    Get the correct path to the FFmpeg executable, handling both development
    and packaged environments.
    """
    if getattr(sys, 'frozen', False):
        # We're in a PyInstaller bundle
        base_path = sys._MEIPASS
        possible_paths = [
            os.path.join(base_path, 'ffmpeg', 'ffmpeg.exe'),
            os.path.join(base_path, 'ffmpeg.exe'),
            os.path.join(os.path.dirname(sys.executable), 'ffmpeg.exe')
        ]

        # Print all paths we're checking (helps with debugging)
        print("Checking FFmpeg paths:")
        for path in possible_paths:
            print(f"- {path}")
            if os.path.exists(path):
                print(f"Found FFmpeg at: {path}")
                return path

        # If we get here, we couldn't find FFmpeg
        raise FileNotFoundError(
            "FFmpeg not found in any expected location:\n" +
            "\n".join(f"- {p}" for p in possible_paths)
        )
    else:
        # Development environment - check if FFmpeg is in PATH
        if sys.platform == 'win32':
            # For Windows, explicitly look for ffmpeg.exe
            from shutil import which
            ffmpeg_path = which('ffmpeg.exe')
            if ffmpeg_path:
                return ffmpeg_path
            raise FileNotFoundError(
                "FFmpeg not found in PATH. Please ensure FFmpeg is installed "
                "and added to your system PATH."
            )
        return "ffmpeg"  # For non-Windows development environments


FFMPEG_PATH = get_ffmpeg_path()

# Use the FFMPEG_PATH in your subprocess command
subprocess.run([FFMPEG_PATH, "-version"], check=True)

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

def is_valid_url(input_url):
    """Validate if a given URL is from a supported platform."""
    supported_domains = [
        'youtube.com', 'youtu.be',
        'music.youtube.com',
        'twitter.com', 'x.com',
        'tiktok.com',
        'dailymotion.com', 'dai.ly',
        'vimeo.com',
        'instagram.com/reels', 'instagram.com/reel'
    ]
    try:
        parsed_url = urlparse(input_url)
        cleaned_path = parsed_url.path.split('?')[0]  # Remove query parameters
        return any(domain in parsed_url.netloc + cleaned_path for domain in supported_domains)
    except Exception as e:
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
        safe_update_ui(lambda: youtube_status_label.config(text="Hmmm..."))

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

            safe_update_ui(lambda: youtube_status_label.config(text="You're running the latest version! Good job!"))
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
            lambda: youtube_status_label.config(text="Download Status: Idle")
        ))


def setup_auto_update_checker(app) -> None:
    # Setup automatic update checking
    app.after(1000, lambda: check_for_updates(app))

    def schedule_next_check():
        check_for_updates(app)
        app.after(86400000, schedule_next_check)

    app.after(86400000, schedule_next_check)

def show_about() -> None:
    # Show the about dialog
    messagebox.showinfo(
        "About",
        f"Lace's Total File Converter v{CURRENT_VERSION}\n\n"
        "A friendly file converter for all your media needs!\n\n"
        "Created with ♥ by Lace"
    )

def add_update_menu(app, menubar) -> None:
    # Add the update menu to the menubar
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
    # execute ffmpeg command to convert video to video
    try:
        ffmpeg_path = get_ffmpeg_path()
        print(f"Using FFmpeg from: {ffmpeg_path}")

        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # First attempt - with GPU acceleration
        if output_format.lower() == "avi":
            gpu_cmd = [
                ffmpeg_path,
                "-hwaccel", "cuda",
                "-i", input_path,
                "-c:v", "mpeg4",
                "-q:v", "5",
                "-c:a", "mp3",
                "-y",
                output_path
            ]
        else:  # mp4 and other formats
            gpu_cmd = [
                ffmpeg_path,
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

        try:
            print("Attempting GPU conversion:", " ".join(gpu_cmd))
            subprocess.run(gpu_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return
        except subprocess.CalledProcessError:
            print("GPU conversion failed, falling back to CPU encoding")

        # Fallback CPU encoding settings
        if output_format.lower() == "avi":
            cpu_cmd = [
                ffmpeg_path,
                "-i", input_path,
                "-c:v", "mpeg4",
                "-q:v", "5",
                "-c:a", "mp3",
                "-y",
                output_path
            ]
        else:  # mp4 and other formats
            cpu_cmd = [
                ffmpeg_path,
                "-i", input_path,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k",
                "-y",
                output_path
            ]

        print("Using CPU fallback:", " ".join(cpu_cmd))
        subprocess.run(cpu_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)

    except FileNotFoundError as e:
        print(f"FFmpeg error (FileNotFoundError): {e}")
        raise
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg conversion failed: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error during video conversion: {e}")
        raise


def initialize_ffmpeg_paths():
    """
    Initialize FFmpeg paths for both direct FFmpeg calls and pydub.
    Returns tuple of (ffmpeg_path, ffprobe_path).
    """
    try:
        ffmpeg_path = get_ffmpeg_path()
        # Determine ffprobe path based on ffmpeg path
        if getattr(sys, 'frozen', False):
            ffprobe_path = os.path.join(
                os.path.dirname(ffmpeg_path),
                'ffprobe.exe'
            )
        else:
            # In development, if ffmpeg is in PATH, ffprobe should be too
            if sys.platform == 'win32':
                from shutil import which
                ffprobe_path = which('ffprobe.exe')
                if not ffprobe_path:
                    raise FileNotFoundError("FFprobe not found in PATH")
            else:
                ffprobe_path = "ffprobe"

        # Verify both executables exist
        if not os.path.exists(ffmpeg_path):
            raise FileNotFoundError(f"FFmpeg not found at: {ffmpeg_path}")
        if sys.platform == 'win32' and not os.path.exists(ffprobe_path):
            raise FileNotFoundError(f"FFprobe not found at: {ffprobe_path}")

        # Set up pydub paths
        AudioSegment.converter = ffmpeg_path
        AudioSegment.ffmpeg = ffmpeg_path
        AudioSegment.ffprobe = ffprobe_path

        print(f"Successfully initialized FFmpeg at: {ffmpeg_path}")
        print(f"Successfully initialized FFprobe at: {ffprobe_path}")

        return ffmpeg_path, ffprobe_path

    except Exception as e:
        print(f"Error initializing FFmpeg: {str(e)}")
        raise


def convert_audio(input_paths: list, output_folder: str, output_format: str,
                  progress_var: tk.IntVar, convert_button: tk.Button, use_gpu: bool) -> None:
    """
    Convert audio/video files to the specified format with comprehensive error handling
    and progress tracking.

    Args:
        input_paths (list): List of paths to input files
        output_folder (str): Destination folder for converted files
        output_format (str): Target format for conversion
        progress_var (tk.IntVar): Progress bar variable
        convert_button (tk.Button): Convert button widget for UI updates
        use_gpu (bool): Whether to use GPU acceleration when available
    """
    try:
        ffmpeg_path, ffprobe_path = initialize_ffmpeg_paths()
        print(f"Using FFmpeg from: {ffmpeg_path}")
        print(f"Using FFprobe from: {ffprobe_path}")

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
                    # Simple direct probe for audio streams
                    probe_cmd = [
                        ffmpeg_path,
                        "-i", input_path,
                        "-hide_banner"
                    ]

                    probe_result = subprocess.run(
                        probe_cmd,
                        capture_output=True,
                        text=True,
                        check=False
                    )

                    # Check for audio stream in FFmpeg's stderr output
                    has_audio = "Stream #0" in probe_result.stderr and "Audio:" in probe_result.stderr

                    if not has_audio:
                        error_msg = (
                            f"Cannot convert '{file_name}' to {output_format} format.\n\n"
                            f"The selected video file does not contain any audio tracks. "
                            f"Please ensure the video has audio before attempting to convert to an audio format."
                        )
                        print(f"Conversion warning: No audio streams found in {file_name}")
                        safe_update_ui(lambda: messagebox.showwarning(
                            "No Audio Found",
                            error_msg,
                            parent=app
                        ))
                        return

                    ffmpeg_cmd = [
                        ffmpeg_path,
                        "-i", input_path,
                        "-vn",
                        "-y"
                    ]

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
                    ffmpeg_cmd = [
                        ffmpeg_path,
                        "-i", input_path,
                        "-y"
                    ]

                    if output_format == "mp3":
                        ffmpeg_cmd.extend(["-acodec", "libmp3lame", "-q:a", "2", "-b:a", "192k"])
                    elif output_format == "ogg":
                        ffmpeg_cmd.extend(["-acodec", "libvorbis", "-q:a", "6"])
                    elif output_format == "flac":
                        ffmpeg_cmd.extend(["-acodec", "flac"])
                    elif output_format == "wav":
                        ffmpeg_cmd.extend(["-acodec", "pcm_s16le"])

                    ffmpeg_cmd.append(output_path)

                print(f"Executing FFmpeg command: {' '.join(ffmpeg_cmd)}")

                try:
                    result = subprocess.run(
                        ffmpeg_cmd,
                        check=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        capture_output=True,
                        text=True,
                        shell=False
                    )
                except subprocess.CalledProcessError as e:
                    print(f"FFmpeg stderr output: {e.stderr}")
                    raise

                progress_var.set(int((idx / total_files) * 100))
                update_button(f"Converting: {progress_var.get()}%")
                print(f"Successfully converted: {file_name} -> {output_file_name}")

            except subprocess.CalledProcessError as e:
                error_msg = f"FFmpeg failed to convert {file_name}: {str(e)}"
                print(f"FFmpeg error: {error_msg}")
                safe_update_ui(lambda: messagebox.showerror("Error", error_msg, parent=app))
                return
            except Exception as e:
                error_msg = f"Error converting {file_name}: {str(e)}"
                print(f"Conversion error: {error_msg}")
                safe_update_ui(lambda: messagebox.showerror("Error", error_msg, parent=app))
                return

        def show_completion_dialog():
            convert_button.config(text="CONVERT", bg="#9370DB", fg="white")
            youtube_status_label.config(text="Conversion Complete! ^.^")

            if messagebox.askyesno(
                    "Success!",
                    "Conversion complete! Do you wanna open the output folder?",
                    parent=app
            ):
                os.startfile(output_folder)

            convert_button.config(text="CONVERT", bg="#9370DB", fg="white")
            app.update_idletasks()

        safe_update_ui(show_completion_dialog)

    except Exception as e:
        error_msg = f"Conversion failed: {str(e)}"
        print(f"Fatal error: {error_msg}")
        traceback.print_exc()
        safe_update_ui(lambda: messagebox.showerror("Error", error_msg, parent=app))



def punish_user_with_maths() -> bool:
    # Funny math problems if the user does a bad action such as trying to convert an audio file to a video file
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

    # Input validation
    if not input_paths or not input_paths[0]:
        messagebox.showerror(
            "Error",
            "Please select input files.",
            parent=app
        )
        return

    if not output_folder:
        messagebox.showerror(
            "Error",
            "Please select an output folder.",
            parent=app
        )
        return

    # Format validation
    valid_formats = ["wav", "ogg", "flac", "mp3", "mp4", "avi", "mov"]
    if not output_format or output_format not in valid_formats:
        messagebox.showerror(
            "Error",
            "Please select a valid output format.",
            parent=app
        )
        return

    use_gpu = gpu_var.get()
    progress_var.set(0)

    print(f"Starting conversion with format: {output_format}")  # Debug output

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
# YouTube Functions
#=================================
def get_format_string(quality, format_type):
    """Generate the yt-dlp format string based on quality and format selection."""
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
    """Modify yt-dlp options based on quality and format selections."""
    try:
        # Get FFmpeg path using our existing function
        ffmpeg_path = get_ffmpeg_path()
        ffprobe_path = ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe')

        # Essential base configuration
        ydl_opts.update({
            'ffmpeg_location': ffmpeg_path,
            'prefer_ffmpeg': True,
            'external_downloader_args': {'ffmpeg_i': ['-threads', '4']},
        })

        # Check if it's a YouTube Music URL
        is_youtube_music = 'music.youtube.com' in ydl_opts.get('webpage_url', '')

        audio_formats = ["mp3", "wav", "flac", "ogg"]

        if format_type in audio_formats or is_youtube_music:
            # For YouTube Music, always use high-quality audio extraction
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': format_type if format_type in audio_formats else 'mp3',
                    'preferredquality': '192',
                    'nopostoverwrites': False
                }]
            })

            # Add metadata extraction for YouTube Music
            if is_youtube_music:
                ydl_opts['postprocessors'].append({
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                })

                # Add thumbnail embedding if it's an MP3
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

            # Post-processor arguments for video formats
            if format_type == 'mp4':
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': [
                        '-c:v', 'libx264',
                        '-c:a', 'aac',
                        '-b:a', '192k'
                    ]
                }
            elif format_type == 'avi':
                ydl_opts['postprocessor_args'] = {
                    'FFmpegVideoRemuxer': [
                        '-c:v', 'mpeg4',
                        '-c:a', 'mp3',
                        '-q:v', '6'
                    ]
                }

        print(f"Using FFmpeg from: {ffmpeg_path}")
        print(f"Download options configured: {ydl_opts}")

        return ydl_opts

    except Exception as e:
        print(f"Error configuring download options: {str(e)}")
        raise




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
            youtube_status_label.config(text="Big brain flex...")
        elif d['status'] == 'error':
            youtube_status_label.config(text="AAAAAH!")
            convert_button.config(text="CONVERT", fg="white")

    safe_update_ui(update)


def download_video():
    """Handle video downloads from various platforms."""
    global youtube_format_var, youtube_quality_var

    input_url = youtube_link_entry.get().strip()
    if not input_url:
        messagebox.showerror("Lunatic Alert", "This is clearly not a valid video URL lol")
        return

    if not is_valid_url(input_url):
        supported_platforms = ['YouTube', 'YouTube Music', 'Twitter', 'TikTok', 'Dailymotion', 'Vimeo', 'Instagram Reels']
        messagebox.showerror("Error", f"Please provide a valid video URL from a supported platform: {', '.join(supported_platforms)}.")
        return

    output_folder = output_folder_entry.get().strip()
    if not output_folder:
        messagebox.showerror("Error", "Please select an output folder.")
        return

    try:
        format_type = youtube_format_var.get()
        quality = youtube_quality_var.get()

        # For YouTube Music, default to MP3 if a video format is selected
        if 'music.youtube.com' in input_url and format_type not in ['mp3', 'wav', 'flac', 'ogg']:
            safe_update_ui(lambda: youtube_status_label.config(
                text="Extracting Playlist Data - This may take a while..."
            ))
            format_type = 'mp3'
            youtube_format_var.set('mp3')
            messagebox.showinfo("Format Changed",
                              'YouTube Music detected - defaulting to mp3. This may take a while, the program is not crashing even if it says "not responding" lol')

    except Exception as e:
        messagebox.showerror("Error", "Failed to get format or quality settings. Please try again.")
        return

    # Check if URL is a playlist
    if 'list=' in input_url:
        # Update status for playlist extraction
        safe_update_ui(lambda: youtube_status_label.config(
            text="Extracting Playlist Data - This may take a while..."
        ))
        app.update_idletasks()

        # First get playlist info
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
                        return  # User selected cancel
                    elif response:
                        download_url = input_url  # Download entire playlist
                    else:
                        download_url = input_url.split('&list=')[0]  # Download only the video
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
                'webpage_url': input_url  # Add the original URL for format detection
            }

            ydl_opts = modify_download_options(ydl_opts, quality, format_type)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([download_url])

            safe_update_ui(lambda: youtube_status_label.config(text="Download Complete! ^.^"))
            if messagebox.askyesno("Success!", "Do you wanna open the output folder?"):
                os.startfile(output_folder)

        except yt_dlp.utils.DownloadError as download_error:
            safe_update_ui(lambda: youtube_status_label.config(text="Download failed!"))
            safe_update_ui(lambda error=download_error: messagebox.showerror(
                "Download Error",
                f"Failed to download video: {str(error)}"
            ))
        except Exception as general_error:
            safe_update_ui(lambda: youtube_status_label.config(text="Error occurred!"))
            safe_update_ui(lambda error=general_error: messagebox.showerror(
                "Error",
                f"An unexpected error occurred: {str(error)}"
            ))
        finally:
            safe_update_ui(lambda: toggle_interface(True))
            safe_update_ui(lambda: convert_button.config(text="CONVERT", fg="white"))

    toggle_interface(False)
    if 'list=' not in input_url:  # Only show "Processing URL" for non-playlist downloads
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

        # Load fonts using Windows API
        FONT_ADDED = 0x10
        bubblegum_path = resource_path(os.path.join('assets', 'fonts', 'BubblegumSans-Regular.ttf'))
        bartino_path = resource_path(os.path.join('assets', 'fonts', 'Bartino.ttf'))

        # Add fonts to Windows
        ctypes.windll.gdi32.AddFontResourceW(bubblegum_path)
        ctypes.windll.gdi32.AddFontResourceW(bartino_path)

        # Create font objects with the actual font family names
        title_font = tkFont.Font(family="Bubblegum Sans", size=32)
        regular_font = tkFont.Font(family="Bartino", size=14)

        return (title_font, regular_font)
    except Exception as e:
        print(f"Font loading error: {e}")
        return (
            tkFont.Font(family="Arial", size=32, weight="bold"),
            tkFont.Font(family="Arial", size=14)
        )


def setup_main_window() -> None:
    if hasattr(sys, "_MEIPASS"):
        tcl_dnd_path = os.path.join(sys._MEIPASS, "tkinterdnd2", "tkdnd", "win-x64")
        os.environ["TCLLIBPATH"] = tcl_dnd_path
        print("Set TCLLIBPATH to", tcl_dnd_path)

    icon_path = resource_path(os.path.join('assets', 'icons', 'icon.png'))
    icon_img = PhotoImage(file=icon_path)
    app.iconphoto(False, icon_img)
    app.title(f"Hey besties let's convert those files (v{CURRENT_VERSION})")
    app.configure(bg="#E6E6FA")
    app.geometry("700x550")  # Increased height to accommodate new options
    app.minsize(900, 875)
    app.resizable(True, True)

    app.call('wm', 'iconphoto', app._w, '-default', icon_img)
    app.drop_target_register(DND_FILES)
    app.dnd_bind("<<Drop>>", on_drop)


def create_ui_components() -> None:
    title_font, regular_font = setup_fonts()

    # Create menu bar
    menubar = tk.Menu(app)
    app.config(menu=menubar)
    add_update_menu(app, menubar)
    setup_auto_update_checker(app)

    # Assign to global variables
    global input_entry, output_folder_entry, youtube_link_entry, format_dropdown
    global convert_button, gpu_checkbox, youtube_status_label, progress_var
    global youtube_format_var, youtube_quality_var  # Add these global declarations

    # Initialize the variables before creating the UI elements
    youtube_format_var = tk.StringVar(value="mp4")
    youtube_quality_var = tk.StringVar(value="1080p")

    # Main Container Frame
    main_frame = tk.Frame(app, bg="#E6E6FA")
    main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
    main_frame.grid_columnconfigure(0, weight=1)

    # Header Section
    header_label = tk.Label(main_frame, text="Lace's Total File Converter",
                            font=title_font, bg="#E6E6FA", fg="#6A0DAD")
    header_label.grid(row=0, column=0, columnspan=3, pady=(0, 20), sticky="ew")

    # Output Folder Section (Shared)
    output_frame = tk.LabelFrame(main_frame, text="Output Location", bg="#E6E6FA",
                                 font=regular_font, fg="#6A0DAD", pady=10)
    output_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 20))
    output_frame.grid_columnconfigure(1, weight=1)

    tk.Label(output_frame, text="Output Folder:", bg="#E6E6FA", font=regular_font).grid(
        row=0, column=0, padx=10, pady=10, sticky="w")
    output_folder_entry = tk.Entry(output_frame, width=50, font=regular_font)
    output_folder_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
    tk.Button(output_frame, text="Browse", command=select_output_folder,
              bg="#DDA0DD", fg="white", font=regular_font).grid(
        row=0, column=2, padx=10, pady=10)

    # Video Download Section (formerly YouTube Download Section)
    video_frame = tk.LabelFrame(main_frame, text="Video Download", bg="#E6E6FA",
                                font=regular_font, fg="#6A0DAD", pady=10)
    video_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 20))
    video_frame.grid_columnconfigure(1, weight=1)

    # Video Link Row
    tk.Label(video_frame, text="Video URL:", bg="#E6E6FA", font=regular_font).grid(
        row=0, column=0, padx=10, pady=5, sticky="w")
    youtube_link_entry = tk.Entry(video_frame, width=50, font=regular_font)
    youtube_link_entry.grid(row=0, column=1, columnspan=2, padx=10, pady=5, sticky="ew")

    # Add supported platforms label
    supported_platforms = tk.Label(video_frame,
                                   text="Supported: YouTube, Twitter, TikTok, Instagram, Dailymotion, Vimeo",
                                   bg="#E6E6FA", font=regular_font, fg="#666666")
    supported_platforms.grid(row=1, column=0, columnspan=3, pady=(0, 5), sticky="w", padx=10)

    # Video Options Row
    options_frame = tk.Frame(video_frame, bg="#E6E6FA")
    options_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)
    options_frame.grid_columnconfigure(1, weight=1)
    options_frame.grid_columnconfigure(3, weight=1)

    tk.Label(options_frame, text="Format:", bg="#E6E6FA", font=regular_font).grid(
        row=0, column=0, padx=10, sticky="w")
    youtube_format_var = tk.StringVar(value="mp4")
    youtube_format_dropdown = ttk.Combobox(
        options_frame,
        textvariable=youtube_format_var,
        values=["mp4", "avi", "mp3", "wav", "flac", "ogg"],
        font=regular_font,
        state="readonly"
    )
    youtube_format_dropdown.grid(row=0, column=1, padx=10, sticky="ew")

    tk.Label(options_frame, text="Quality:", bg="#E6E6FA", font=regular_font).grid(
        row=0, column=2, padx=10, sticky="w")
    youtube_quality_var = tk.StringVar(value="1080p")
    youtube_quality_dropdown = ttk.Combobox(
        options_frame,
        textvariable=youtube_quality_var,
        values=["Best", "4K", "1440p", "1080p", "720p", "480p"],
        font=regular_font,
        state="readonly"
    )
    youtube_quality_dropdown.grid(row=0, column=3, padx=10, sticky="ew")

    # Download Button
    tk.Button(video_frame, text="DOWNLOAD", command=download_video,
              bg="#9370DB", fg="white", font=regular_font).grid(
        row=3, column=0, columnspan=3, pady=10, sticky="ew")

    # File Conversion Section
    conversion_frame = tk.LabelFrame(main_frame, text="File Conversion", bg="#E6E6FA",
                                     font=regular_font, fg="#6A0DAD", pady=10)
    conversion_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 20))
    conversion_frame.grid_columnconfigure(1, weight=1)

    # Input File Row
    tk.Label(conversion_frame, text="Input Files:", bg="#E6E6FA", font=regular_font).grid(
        row=0, column=0, padx=10, pady=5, sticky="w")
    input_entry = tk.Entry(conversion_frame, width=50, font=regular_font)
    input_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
    tk.Button(conversion_frame, text="Browse", command=select_input,
              bg="#DDA0DD", fg="white", font=regular_font).grid(
        row=0, column=2, padx=10, pady=5)

    # Conversion Format Row
    tk.Label(conversion_frame, text="Output Format:", bg="#E6E6FA", font=regular_font).grid(
        row=1, column=0, padx=10, pady=5, sticky="w")
    format_var = tk.StringVar(value="mp4")
    format_dropdown = ttk.Combobox(
        conversion_frame,
        textvariable=format_var,
        values=["wav", "ogg", "flac", "mp3", "mp4", "avi", "mov"],
        font=regular_font,
        state="readonly"
    )
    format_dropdown.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

    # Convert Button Section
    convert_button = tk.Button(conversion_frame, text="CONVERT", command=start_conversion,
                               bg="#9370DB", fg="white", font=regular_font)
    convert_button.grid(row=2, column=0, columnspan=3, pady=10, sticky="ew")

    # GPU Checkbox and Status Section
    bottom_frame = tk.Frame(main_frame, bg="#E6E6FA")
    bottom_frame.grid(row=4, column=0, sticky="ew", pady=(0, 10))
    bottom_frame.grid_columnconfigure(0, weight=1)

    global gpu_var
    gpu_var = tk.BooleanVar(value=True)
    gpu_checkbox = tk.Checkbutton(
        bottom_frame, text="GPU Encode (Significantly Faster)", bg="#E6E6FA",
        font=regular_font, variable=gpu_var
    )
    gpu_checkbox.grid(row=0, column=0, pady=5, sticky="ew")

    youtube_status_label = tk.Label(bottom_frame, text="Download Status: Idle",
                                    bg="#E6E6FA", font=regular_font)
    youtube_status_label.grid(row=1, column=0, pady=5, sticky="ew")

    # Configure main window grid weights
    app.grid_rowconfigure(0, weight=1)
    app.grid_columnconfigure(0, weight=1)


# =================================
# Application Entry Point
# =================================
if __name__ == "__main__":
    try:
        # Initialize main window
        app = TkinterDnD.Tk()

        # Initialize variables
        format_var = tk.StringVar()
        gpu_var = tk.BooleanVar(value=True)
        progress_var = tk.IntVar()

        # Verify FFmpeg availability early
        try:
            ffmpeg_path, ffprobe_path = initialize_ffmpeg_paths()
            print(f"Successfully initialized FFmpeg at: {ffmpeg_path}")
            print(f"Successfully initialized FFprobe at: {ffprobe_path}")
        except FileNotFoundError as e:
            messagebox.showerror("FFmpeg Error", str(e))
            sys.exit(1)

        setup_main_window()
        create_ui_components()

        app.mainloop()
    except Exception:
        log_errors()
        messagebox.showerror("Error", "Something went wrong. Check error_log.txt")