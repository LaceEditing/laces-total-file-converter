import sys, os
import random
import subprocess
import time
import threading
from tkinterdnd2 import DND_FILES, TkinterDnD
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter import font as tkFont, PhotoImage, ttk

import yt_dlp
from pydub import AudioSegment
from moviepy.editor import VideoFileClip

from urllib.parse import urlparse

def is_valid_youtube_url(url):
    try:
        parsed_url = urlparse(url)
        return bool(
            parsed_url.scheme and
            parsed_url.netloc and
            ('youtube.com' in parsed_url.netloc or 'youtu.be' in parsed_url.netloc)
        )
    except:
        return False

if hasattr(sys, "_MEIPASS"):
    tcl_dnd_path = os.path.join(sys._MEIPASS, "tkinterdnd2", "tkdnd", "win-x64")
    os.environ["TCLLIBPATH"] = tcl_dnd_path
    print("Set TCLLIBPATH to", tcl_dnd_path)

def safe_update_ui(func):
    if not isinstance(func, str):
        app.after(0, func)
    else:
        def update():
            eval(func)

        app.after(0, update)

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)

def on_drop(event):
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


def punish_user_with_maths():
    """Present the user with math problems as a consequence of invalid operations."""
    result = [False]  # Use a list to store the result since it needs to be mutable

    def show_math_dialog():
        def show_initial_warning():
            messagebox.showinfo(
                "WOAH THERE HOLD YOUR HORSES FRIEND",
                "Converting an audio file to a video file is literally not a thing. Like... Ok actually I gotta test your brain now.",
                parent=app
            )
            return True

        if not show_initial_warning():
            messagebox.showinfo(
                "Lol bye",
                "Application will now close!",
                parent=app
            )
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
                    messagebox.showinfo(
                        "bruh...",
                        "ok bye",
                        parent=app
                    )
                    app.destroy()
                    return

    # Execute the dialog in the main thread
    app.after(0, show_math_dialog)

    # Wait for the dialog to complete
    while app.winfo_exists():  # Check if window still exists
        app.update()  # Keep the GUI responsive
        if result[0]:  # Check if math problem was solved successfully
            return True
        time.sleep(0.1)  # Prevent CPU overuse

    return False

def direct_ffmpeg_gpu_video2video(input_path, output_path):
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


def convert_audio(input_paths, output_folder, output_format, progress_var, convert_button, use_gpu):
    """Convert audio/video files to the specified format with thread-safe UI updates."""
    os.makedirs(output_folder, exist_ok=True)

    audio_formats = ["wav", "ogg", "flac", "mp3"]
    video_formats = ["mp4", "avi", "mov"]

    def update_button(text, bg="#D8BFD8"):
        safe_update_ui(lambda: convert_button.config(text=text, bg=bg, fg="white"))

    def update_status(text):
        safe_update_ui(lambda: youtube_status_label.config(text=text))

    update_button("Converting...")

    total_files = len(input_paths)

    for idx, input_path in enumerate(input_paths, start=1):
        file_name = os.path.basename(input_path)
        input_extension = os.path.splitext(file_name)[1][1:].lower()
        output_file_name = os.path.splitext(file_name)[0] + f'.{output_format}'
        output_path = os.path.join(output_folder, output_file_name)

        update_status(f"Converting file {idx}/{total_files}: {file_name}")

        if input_extension in audio_formats and output_format in video_formats:
            update_button("Convert", "#9370DB")
            success = app.after(0, punish_user_with_maths)
            if not success:
                return
            update_button("Convert", "#9370DB")
            return

        try:
            if input_extension in video_formats and output_format in audio_formats:
                # Updated FFmpeg command for video to audio conversion
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", input_path,
                    "-vn"  # Remove video stream
                ]

                # Format-specific settings
                if output_format == "mp3":
                    ffmpeg_cmd.extend([
                        "-acodec", "libmp3lame",
                        "-q:a", "2",  # Variable bitrate quality (0-9, 2 is high quality)
                        "-b:a", "192k"
                    ])
                elif output_format == "ogg":
                    ffmpeg_cmd.extend([
                        "-acodec", "libvorbis",
                        "-q:a", "6",  # Quality scale for Vorbis (0-10)
                        "-b:a", "192k"
                    ])
                elif output_format == "wav":
                    ffmpeg_cmd.extend([
                        "-acodec", "pcm_s16le",  # Standard WAV format
                        "-ar", "44100"  # Standard sample rate
                    ])
                elif output_format == "flac":
                    ffmpeg_cmd.extend([
                        "-acodec", "flac",
                        "-compression_level", "8"  # FLAC compression level (0-12)
                    ])

                # Add output file and overwrite flag
                ffmpeg_cmd.extend([
                    "-y",
                    output_path
                ])

                print("Running command:", " ".join(ffmpeg_cmd))
                subprocess.run(ffmpeg_cmd, check=True)

            elif input_extension in video_formats and output_format in video_formats:
                # Rest of the video-to-video conversion code remains the same
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

def select_input():
    input_selected = filedialog.askopenfilenames(
        filetypes=[("Media files", "*.mp3;*.wav;*.ogg;*.flac;*.mp4;*.avi;*.mov")]
    )
    if input_selected:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, ";".join(input_selected))

def select_output_folder():
    folder_selected = filedialog.askdirectory()
    output_folder_entry.delete(0, tk.END)
    output_folder_entry.insert(0, folder_selected)

def start_conversion():
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

def yt_dlp_progress_hook(d):
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

def toggle_interface(enabled=True):
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

def download_youtube():
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
            download_url = input_url  # Create a local reference
            is_direct_playlist = download_url.startswith('https://www.youtube.com/playlist?list=')
            playlist_id = None

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
                            download_url = playlist_url  # Use the clean playlist URL
                        else:  # User chose to download single video
                            download_url = download_url.split('&list=')[0]  # Remove playlist parameters
                except IndexError:
                    safe_update_ui(lambda: messagebox.showerror("Error", "Invalid playlist URL format"))
                    safe_update_ui(lambda: toggle_interface(True))
                    return

            # Configure download options based on whether we're downloading a playlist
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
                safe_update_ui(lambda: messagebox.showerror("Duplication Error!", f"Whatever you just tried to download is already in the folder lol"))

        finally:
            safe_update_ui(lambda: toggle_interface(True))
            safe_update_ui(lambda: convert_button.config(text="CONVERT", fg="white"))

    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()

# =============================
#     The actual code lol
# =============================

app = TkinterDnD.Tk()
icon_path = resource_path(os.path.join('assets', 'icons', 'icon.png'))
icon_img = PhotoImage(file=icon_path)
app.iconphoto(False, icon_img)
app.title("Hey besties let's convert those files")
app.configure(bg="#E6E6FA")
app.geometry("700x400")
app.minsize(900, 430)
app.resizable(True, True)

app.call('wm', 'iconphoto', app._w, '-default', icon_img)

app.drop_target_register(DND_FILES)
app.dnd_bind("<<Drop>>", on_drop)

# Font Configuration
title_font = tkFont.Font(family="Bubblegum Sans", size=32)
regular_font = tkFont.Font(family="Bartino Regular", size=14)

# Header Section
header_label = tk.Label(app, text="Lace's Total File Converter", font=title_font, bg="#E6E6FA", fg="#6A0DAD")
header_label.grid(row=0, column=0, columnspan=3, pady=20, sticky="ew")

# Input File Section
tk.Label(app, text="Input Files:", bg="#E6E6FA", font=regular_font).grid(row=1, column=0, padx=10, pady=5, sticky="ew")
input_entry = tk.Entry(app, width=50, font=regular_font)
input_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
tk.Button(app, text="Browse", command=select_input, bg="#DDA0DD", fg="white", font=regular_font).grid(
    row=1, column=2, padx=10, pady=5
)

# Output Folder Section
tk.Label(app, text="Output Folder:", bg="#E6E6FA", font=regular_font).grid(row=2, column=0, padx=10, pady=5, sticky="ew")
output_folder_entry = tk.Entry(app, width=50, font=regular_font)
output_folder_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
tk.Button(app, text="Browse", command=select_output_folder, bg="#DDA0DD", fg="white", font=regular_font).grid(
    row=2, column=2, padx=10, pady=5
)

# Output Format Section
tk.Label(app, text="Output Format:", bg="#E6E6FA", font=regular_font).grid(row=3, column=0, padx=10, pady=5, sticky="ew")
format_var = tk.StringVar()
format_dropdown = ttk.Combobox(
    app,
    textvariable=format_var,
    values=["wav", "ogg", "flac", "mp3", "mp4", "avi", "mov"],
    font=regular_font
)
format_dropdown.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

# YouTube Link Section
tk.Label(app, text="YouTube Link:", bg="#E6E6FA", font=regular_font).grid(row=4, column=0, padx=10, pady=5, sticky="ew")
youtube_link_entry = tk.Entry(app, width=50, font=regular_font)
youtube_link_entry.grid(row=4, column=1, padx=10, pady=5, sticky="ew")
tk.Button(
    app,
    text="Download",
    command=download_youtube,
    bg="#DDA0DD",
    fg="white",
    font=regular_font
).grid(row=4, column=2, padx=10, pady=5)

# Convert Button Section
progress_var = tk.IntVar()
convert_button = tk.Button(app, text="CONVERT", command=start_conversion, bg="#9370DB", fg="white", font=regular_font)
convert_button.grid(row=5, column=0, columnspan=3, pady=10, sticky="ew")

# GPU Configuration Section
gpu_var = tk.BooleanVar(value=True)
gpu_checkbox = tk.Checkbutton(
    app, text="GPU Encode (Significantly Faster)", bg="#E6E6FA",
    font=regular_font, variable=gpu_var
)
gpu_checkbox.grid(row=6, column=0, columnspan=3, pady=5, sticky="ew")

# YouTube Status Section
youtube_status_label = tk.Label(app, text="YouTube Status: Idle", bg="#E6E6FA", font=regular_font)
youtube_status_label.grid(row=7, column=0, columnspan=3, pady=5, sticky="ew")

# Grid Configuration
app.grid_columnconfigure(0, weight=1)
app.grid_columnconfigure(1, weight=1)
app.grid_columnconfigure(2, weight=1)

# Start Application
app.mainloop()