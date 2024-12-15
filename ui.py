# ui.py
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import scrolledtext
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import os
from extract import extract_book
from generate_audiobook import generate_audiobooks
import sys
import threading
import time
import json

class LogRedirector:
    def __init__(self, write_callback):
        self.write_callback = write_callback
        self.is_logging = False  # Prevent recursion

    def write(self, message):
        if self.is_logging:  # Avoid recursive logging
            return

        self.is_logging = True
        try:
            if message.strip():  # Avoid empty messages
                self.write_callback(message)
        finally:
            self.is_logging = False  # Reset flag

    def flush(self):
        pass  # No need to flush for tkinter text widgets


class SourceFrame(tb.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)

        # Variables
        self.project_dir = os.path.dirname(os.path.abspath(__file__))  # Project directory
        self.pdf_path = tk.StringVar()
        self.extracted_text_dir = tk.StringVar()  # Directory for extracted text
        self.use_toc = tk.BooleanVar(value=True)
        self.extract_mode = tk.StringVar(value="chapters")  # "chapters" or "whole"

        # Title
        source_label = tb.Label(self, text="PDF Source & Extraction", style="Secondary.TLabel", font="-size 14 -weight bold")
        source_label.pack(pady=10)

        # PDF File Selection
        file_frame = tb.Frame(self)
        file_frame.pack(pady=5, fill=X)
        
        tb.Label(file_frame, text="Select PDF File:").pack(side=LEFT, padx=5)
        tb.Entry(file_frame, textvariable=self.pdf_path, state=READONLY).pack(side=LEFT, fill=X, expand=True, padx=5)
        tb.Button(file_frame, text="Browse", command=self._browse_pdf).pack(side=LEFT, padx=5)

        # TOC & Extraction Mode
        options_frame = tb.Labelframe(self, text="Extraction Options")
        options_frame.pack(fill=X, pady=10, padx=5)

        toc_check = tb.Checkbutton(options_frame, text="Use TOC (if available)", variable=self.use_toc)
        toc_check.pack(anchor=W, padx=5, pady=5)
        
        mode_frame = tb.Frame(options_frame)
        mode_frame.pack(anchor=W, padx=5, pady=5)
        tb.Radiobutton(mode_frame, text="Extract by Chapters", variable=self.extract_mode, value="chapters").pack(side=LEFT)
        tb.Radiobutton(mode_frame, text="Extract Whole Book", variable=self.extract_mode, value="whole").pack(side=LEFT, padx=10)

        # Extracted Text Directory
        out_frame = tb.Frame(self)
        out_frame.pack(pady=5, fill=X)
        
        tb.Label(out_frame, text="Extracted Text Directory:").pack(side=LEFT, padx=5)
        tb.Entry(out_frame, textvariable=self.extracted_text_dir, state=READONLY).pack(side=LEFT, fill=X, expand=True, padx=5)


    def _browse_pdf(self):
        # Use the directory of the current PDF path if set; otherwise, default to the project directory
        initial_dir = os.path.dirname(self.pdf_path.get()) if self.pdf_path.get() else self.project_dir

        # Open the file dialog with the initial directory set
        path = filedialog.askopenfilename(
            title="Select PDF File",
            initialdir=initial_dir,
            filetypes=[("PDF Files", "*.pdf")]
        )

        if path:
            self.pdf_path.set(path)
            # Update extracted text directory dynamically based on the book name
            book_name = os.path.splitext(os.path.basename(path))[0]
            extracted_text_dir = os.path.join(self.project_dir, "extracted_pdf", book_name)
            self.extracted_text_dir.set(extracted_text_dir)
            os.makedirs(extracted_text_dir, exist_ok=True)

            # Notify the parent app to update the audio output directory as well
            if self.master.master:  # self.master is the Notebook; self.master.master is the main app
                app = self.master.master
                if hasattr(app, 'update_audio_output_dir'):
                    app.update_audio_output_dir(book_name)




    # Methods to get user selections
    def get_pdf_path(self):
        return self.pdf_path.get()

    def get_extracted_text_dir(self):
        return self.extracted_text_dir.get()

    def get_use_toc(self):
        return self.use_toc.get()

    def get_extract_mode(self):
        return self.extract_mode.get()


class AudioFrame(tb.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        
        # Variables
        self.project_dir = os.path.dirname(os.path.abspath(__file__))  # Project directory
        self.model_path = tk.StringVar(value="models/en/en_US-libritts-high.onnx")  # Default model
        self.speaker_ids = tk.StringVar(value="8")  # Default speaker ID
        self.chunk_size = tk.IntVar(value=2500)  # Default chunk size
        self.audio_format = tk.StringVar(value=".wav")  # Default audio format
        self.audio_output_dir = tk.StringVar()  # Directory for audiobook files
        self.device = tk.StringVar(value="cuda")  # Default to GPU

        # Title
        audio_label = tb.Label(self, text="Audio Settings", style="Secondary.TLabel", font="-size 14 -weight bold")
        audio_label.pack(pady=10)


        # Model Selection
        model_frame = tb.Frame(self)
        model_frame.pack(fill=X, pady=5, padx=5)

        tb.Label(model_frame, text="Model:").pack(side=LEFT, padx=5)
        models = self._get_model_files()
        model_combo = tb.Combobox(
            model_frame, textvariable=self.model_path, 
            values=models, state="readonly"
        )
        model_combo.pack(side=LEFT, fill=X, expand=True, padx=5)

        # Speaker IDs
        speaker_frame = tb.Frame(self)
        speaker_frame.pack(fill=X, pady=5, padx=5)

        tb.Label(speaker_frame, text="Speaker IDs (comma-separated, leave blank if single-speaker):").pack(side=LEFT, padx=5)
        tb.Entry(speaker_frame, textvariable=self.speaker_ids).pack(side=LEFT, fill=X, expand=True, padx=5)

        # Chunk Size
        chunk_frame = tb.Frame(self)
        chunk_frame.pack(fill=X, pady=5, padx=5)

        tb.Label(chunk_frame, text="Chunk Size (chars, default ~2500 for 6GB VRAM):").pack(side=LEFT, padx=5)
        tb.Spinbox(chunk_frame, from_=500, to=5000, increment=500, textvariable=self.chunk_size, width=7).pack(side=LEFT, padx=5)

        # Output Directory
        output_frame = tb.Frame(self)
        output_frame.pack(fill=X, pady=5, padx=5)

        tb.Label(output_frame, text="Audio Output Folder:").pack(side=LEFT, padx=5)
        tb.Entry(output_frame, textvariable=self.audio_output_dir, state=READONLY).pack(side=LEFT, fill=X, expand=True, padx=5)


        # Audio Format
        format_frame = tb.Frame(self)
        format_frame.pack(fill=X, pady=5, padx=5)

        tb.Label(format_frame, text="Output Format:").pack(side=LEFT, padx=5)
        formats = [".wav", ".mp3"]
        format_combo = tb.Combobox(
            format_frame, textvariable=self.audio_format, 
            values=formats, state="readonly"
        )
        format_combo.pack(side=LEFT, fill=X, expand=True, padx=5)

        # Device Selection
        device_frame = tb.Frame(self)
        device_frame.pack(fill=X, pady=5, padx=5)

        tb.Label(device_frame, text="Device:").pack(side=LEFT, padx=5)
        tb.Radiobutton(device_frame, text="GPU (CUDA)", variable=self.device, value="cuda").pack(side=LEFT, padx=5)
        tb.Radiobutton(device_frame, text="CPU", variable=self.device, value="cpu").pack(side=LEFT, padx=5)


    def _get_model_files(self):
        """
        Scan the 'models' directory in the project root for .onnx files.
        Returns a list of paths to the found models.
        """
        models_dir = os.path.join(self.project_dir, "models")
        model_files = []

        # Walk through the models directory and subdirectories
        for root, dirs, files in os.walk(models_dir):
            for file in files:
                if file.endswith(".onnx"):  # Check for .onnx files
                    # Use relative paths for cleaner display
                    relative_path = os.path.relpath(os.path.join(root, file), self.project_dir)
                    model_files.append(relative_path)

        return model_files

    def get_device(self):
        return self.device.get()

    def update_audio_output_dir(self, book_name):
        """
        Dynamically update the audiobook output folder based on the book name.
        """
        if book_name:
            audio_output_dir = os.path.join(self.project_dir, "audiobooks", book_name)
            os.makedirs(audio_output_dir, exist_ok=True)
            self.audio_output_dir.set(audio_output_dir)
        else:
            # Reset to empty if no valid book name
            self.audio_output_dir.set("")


    def get_audio_output_dir(self):
        return self.audio_output_dir.get()

    def get_model_path(self):
        # Return absolute path to the selected model
        selected_model = self.model_path.get()
        return os.path.join(self.project_dir, selected_model) if selected_model else ""

    def get_speaker_ids(self):
        # Return a list of speaker IDs if provided, else None or empty list
        val = self.speaker_ids.get().strip()
        if val:
            # Parse comma-separated IDs
            return [v.strip() for v in val.split(",") if v.strip()]
        return []

    def get_chunk_size(self):
        return self.chunk_size.get()

    def get_audio_format(self):
        return self.audio_format.get()



class ProgressFrame(tb.Frame):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app  # Reference to main AudiobookApp
        self.pause_event = threading.Event()
        self.pause_event.set()
        # Extraction progress
        self.extract_progress = tk.DoubleVar(value=0.0)
        # Generation progress
        self.audio_progress = tk.DoubleVar(value=0.0)
        self.status_text = tk.StringVar(value="Waiting...")
        
        # Add a variable and label for estimated time
        self.estimated_time_text = tk.StringVar(value="Estimated time remaining: N/A")
        
        # Title
        prog_label = tb.Label(self, text="Progress & Logs", style="Secondary.TLabel", font="-size 14 -weight bold")
        prog_label.pack(pady=10)

        # Status
        status_frame = tb.Frame(self)
        status_frame.pack(fill=X, pady=5, padx=5)
        
        tb.Label(status_frame, text="Status:").pack(side=LEFT, padx=5)
        tb.Label(status_frame, textvariable=self.status_text).pack(side=LEFT, padx=5)
        
        # Add the estimated time label below the status
        tb.Label(status_frame, textvariable=self.estimated_time_text).pack(side=LEFT, padx=15)

        # Progress Bars
        pb_frame = tb.Frame(self)
        pb_frame.pack(fill=X, pady=5, padx=5)
        
        tb.Label(pb_frame, text="Text Extraction:").pack(anchor=W)
        tb.Progressbar(pb_frame, variable=self.extract_progress, maximum=100).pack(fill=X, pady=2)

        tb.Label(pb_frame, text="Audio Generation:").pack(anchor=W, pady=(10, 0))
        tb.Progressbar(pb_frame, variable=self.audio_progress, maximum=100).pack(fill=X, pady=2)
        self.percentage_text = tk.StringVar(value="0% complete")
        tb.Label(pb_frame, textvariable=self.percentage_text).pack(anchor=W, pady=(5, 0))

        # Logs
        log_frame = tb.Labelframe(self, text="Logs")
        log_frame.pack(fill=BOTH, expand=True, pady=5, padx=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8)
        self.log_text.pack(fill=BOTH, expand=True)

        # Redirect stdout and stderr to the UI
        sys.stdout = LogRedirector(self.log_message)
        sys.stderr = LogRedirector(self.log_message)

        # Action Buttons
        btn_frame = tb.Frame(self)
        btn_frame.pack(pady=10)
        
        self.start_button = tb.Button(btn_frame, text="Start Process", bootstyle=SUCCESS, command=self._start_process_thread)
        self.start_button.pack(side=LEFT, padx=5)

        self.cancel_button = tb.Button(btn_frame, text="Cancel", bootstyle=DANGER, command=self._cancel_process, state=DISABLED)
        self.cancel_button.pack(side=LEFT, padx=5)
        
        self.pause_button = tb.Button(btn_frame, text="Pause", bootstyle=WARNING, command=self._pause_process)
        self.pause_button.pack(side=LEFT, padx=5)

        self.resume_button = tb.Button(btn_frame, text="Resume", bootstyle=INFO, command=self._resume_process, state=DISABLED)
        self.resume_button.pack(side=LEFT, padx=5)
        
        self.cancellation_flag = False
        self.process_thread = None
        self.running = False

    def _start_process_thread(self):
        # Start the process in a background thread
        if self.process_thread and self.process_thread.is_alive():
            self.log_message("A process is already running.")
            return

        self.running = True
        self.cancel_button.config(state=NORMAL)
        self.start_button.config(state=DISABLED)
        self.process_thread = threading.Thread(target=self._start_process, daemon=True)
        self.process_thread.start()

    def _start_process(self):
        self.log_message("Starting process...")
        self.set_status("Extracting text...")
        self.update_extract_progress(10)
        self.cancellation_flag = False  # Reset cancellation flag

        try:
            # Extract text
            pdf_path = self.app.source_frame.get_pdf_path()
            use_toc = self.app.source_frame.get_use_toc()
            extract_mode = self.app.source_frame.get_extract_mode()

            def extraction_progress_callback(progress):
                if self.cancellation_flag:
                    raise Exception("Process canceled by user.")
                self.update_extract_progress(progress)
            
            output_dir = extract_book(
                pdf_path, use_toc=use_toc, extract_mode=extract_mode, progress_callback=extraction_progress_callback
            )

            self.log_message(f"Text extraction completed. Files saved to: {output_dir}")
            self.update_extract_progress(100)

            # Generate audiobook
            self.set_status("Generating audiobook...")
            self.update_audio_progress(10)

            model_path = self.app.audio_frame.get_model_path()
            speaker_ids = self.app.audio_frame.get_speaker_ids()
            chunk_size = self.app.audio_frame.get_chunk_size()
            audio_format = self.app.audio_frame.get_audio_format()
            audio_output_dir = self.app.audio_frame.get_audio_output_dir()
            device = self.app.audio_frame.get_device()

            def generation_progress_callback(progress):
                if self.cancellation_flag:
                    raise Exception("Process canceled by user.")
                self.update_audio_progress(progress)
                self.percentage_text.set(f"{progress}% complete")
            def time_estimate_callback(seconds_left):
                # Ensure thread-safe call to UI
                self.after(0, self.set_estimated_time, seconds_left)
                        
            generate_audiobooks(
                input_dir=output_dir,
                model_path=model_path,
                speaker_ids=speaker_ids,
                chunk_size=chunk_size,
                audio_format=audio_format,
                output_dir=audio_output_dir,
                progress_callback=generation_progress_callback,
                device=device,
                cancellation_flag=self.cancellation_flag,
                update_estimate_callback=time_estimate_callback,
                pause_event=self.pause_event
            )

            self.log_message(f"Audiobook generation completed. Files saved to: {audio_output_dir}")
            self.update_audio_progress(100)
            self.set_status("Process completed successfully.")
        except Exception as e:
            self.log_message(f"Error occurred: {e}")
            self.set_status("Process failed.")
        finally:
            self.running = False
            self.cancel_button.config(state=DISABLED)
            self.start_button.config(state=NORMAL)

    def _pause_process(self):
        self.pause_event.clear()  # Pause the process
        self.pause_button.config(state=DISABLED)
        self.resume_button.config(state=NORMAL)
        self.log_message("Process paused.")

    def _resume_process(self):
        self.pause_event.set()  # Resume the process
        self.resume_button.config(state=DISABLED)
        self.pause_button.config(state=NORMAL)
        self.log_message("Process resumed.")
    def _cancel_process(self):
        self.log_message("Canceling process...")
        self.cancellation_flag = True
        self.set_status("Process canceling...")

        if self.process_thread and self.process_thread.is_alive():
            self.process_thread.join(timeout=1)  # Wait briefly to ensure the thread exits
            self.running = False
            self.start_button.config(state=NORMAL)
            self.cancel_button.config(state=DISABLED)


    def log_message(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def set_status(self, status):
        self.status_text.set(status)

    def update_extract_progress(self, value):
        self.extract_progress.set(value)

    def update_audio_progress(self, value):
        self.audio_progress.set(value)
    def set_estimated_time(self, seconds_left):
        # Convert seconds to a more readable format (H:M:S)
        if seconds_left < 0:
            # If for some reason it's negative (rounding), just show 0
            seconds_left = 0

        m, s = divmod(int(seconds_left), 60)
        h, m = divmod(m, 60)
        if h > 0:
            time_str = f"{h}h {m}m {s}s"
        elif m > 0:
            time_str = f"{m}m {s}s"
        else:
            time_str = f"{s}s"

        self.estimated_time_text.set(f"Estimated time remaining: {time_str}")


class AudiobookApp(tb.Window):
    CONFIG_FILE = "config.json"
    def __init__(self, *args, **kwargs):
        self.selected_theme = self._load_theme_from_config()

        super().__init__(*args, themename=self.selected_theme, **kwargs)
        self.title("PDF Narrator")
        self.geometry("1000x800")

        # Set up WM_DELETE_WINDOW protocol
        self.protocol("WM_DELETE_WINDOW", self.on_close)  # Attach the close event handler       
        # Header
        header_frame = tb.Frame(self)
        header_frame.pack(fill=X, pady=10)
        
        title_label = tb.Label(header_frame, text="PDF Narrator", font="-size 16 -weight bold")
        title_label.pack()
        
        subtitle_label = tb.Label(header_frame, text="Convert your PDFs into narrated audiobooks with ease")
        subtitle_label.pack(pady=(5, 0))

        # Notebook
        self.notebook = tb.Notebook(self)
        self.notebook.pack(fill=BOTH, expand=True, pady=10, padx=10)

        self.source_frame = SourceFrame(self.notebook)
        self.audio_frame = AudioFrame(self.notebook)
        self.progress_frame = ProgressFrame(self.notebook, app=self)  # Pass self as app reference

        self.notebook.add(self.source_frame, text="Source")
        self.notebook.add(self.audio_frame, text="Audio")
        self.notebook.add(self.progress_frame, text="Progress & Logs")

        # Footer Frame
        footer_frame = tb.Frame(self)
        footer_frame.pack(fill=X, pady=5)
        
        self.open_output_button = tb.Button(footer_frame, text="Open Output Folder", command=self._open_output_folder)
        self.open_output_button.pack(side=LEFT, padx=10)

        self.open_audio_output_button = tb.Button(
            footer_frame, text="Open Audiobook Folder", command=self._open_audiobook_folder
        )
        self.open_audio_output_button.pack(side=LEFT, padx=10)
        # Theme Selector
        theme_selector_frame = tb.Frame(footer_frame)
        theme_selector_frame.pack(side=RIGHT, padx=10)

        tb.Label(theme_selector_frame, text="Theme:").pack(side=LEFT)
        self.theme_var = tk.StringVar(value=self.selected_theme)
        themes = tb.Style().theme_names()
        self.theme_combo = tb.Combobox(
            theme_selector_frame, textvariable=self.theme_var, values=themes, state="readonly", width=15
        )
        self.theme_combo.pack(side=LEFT, padx=5)
        self.theme_combo.bind("<<ComboboxSelected>>", self._change_theme)

        exit_button = tb.Button(footer_frame, text="Exit", command=self.progress_frame.app.on_close)
        exit_button.pack(side=RIGHT, padx=10)

        self.load_config()
        
    def _open_output_folder(self):
        output_dir = self.source_frame.get_extracted_text_dir()  # Use correct method
        if output_dir and os.path.isdir(output_dir):
            # Open folder in file explorer
            if os.name == 'nt':
                os.startfile(output_dir)
            elif os.name == 'posix':
                os.system(f'xdg-open "{output_dir}"')
        else:
            messagebox.showwarning("Warning", "No valid output directory selected.")

    def _open_audiobook_folder(self):
        audio_dir = self.audio_frame.get_audio_output_dir()
        if audio_dir and os.path.isdir(audio_dir):
            # Open folder in file explorer
            if os.name == 'nt':
                os.startfile(audio_dir)
            elif os.name == 'posix':
                os.system(f'xdg-open "{audio_dir}"')
        else:
            messagebox.showwarning("Warning", "No valid audiobook output directory selected.")

    def _change_theme(self, event):
        # Update the app theme dynamically using ttkbootstrap's set_theme method
        new_theme = self.theme_var.get()
        tb.Style().theme_use(new_theme)  # Change the theme dynamically
        self.selected_theme = new_theme  # Save the new theme for config saving

    def _load_theme_from_config(self):
        # Load theme from config
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    return config.get("theme", "flatly")  # Default to "flatly" if no theme is saved
            except Exception as e:
                print(f"Failed to load theme from config: {e}")
        return "flatly"  # Default theme
    
    def load_config(self):
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    config = json.load(f)

                    # Load PDF path
                    pdf_path = config.get("pdf_path", "")
                    self.source_frame.pdf_path.set(pdf_path)

                    # Dynamically calculate extracted text directory
                    if pdf_path:
                        book_name = os.path.splitext(os.path.basename(pdf_path))[0]
                        extracted_text_dir = os.path.join(self.source_frame.project_dir, "extracted_pdf", book_name)
                        self.source_frame.extracted_text_dir.set(extracted_text_dir)

                        # Dynamically calculate audio output directory
                        self.update_audio_output_dir(book_name)

                    # Load audio settings
                    self.audio_frame.model_path.set(config.get("model_path", "models/en/en_US-libritts-high.onnx"))
                    self.audio_frame.speaker_ids.set(",".join(config.get("speaker_ids", [])))  # Rejoin as string
                    self.audio_frame.chunk_size.set(config.get("chunk_size", 2500))
                    self.audio_frame.audio_format.set(config.get("audio_format", ".wav"))
            except Exception as e:
                print(f"Failed to load config: {e}")

    def save_config(self):
        config = {
            "pdf_path": self.source_frame.get_pdf_path(),
            "model_path": self.audio_frame.get_model_path(),
            "speaker_ids": ",".join(self.audio_frame.get_speaker_ids()),
            "chunk_size": self.audio_frame.get_chunk_size(),
            "audio_format": self.audio_frame.get_audio_format(),
            "theme": self.selected_theme,
        }
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def update_audio_output_dir(self, book_name):
        self.audio_frame.update_audio_output_dir(book_name)

    def on_close(self):
        print("Application is closing.")  # Debug print
        self.save_config()  # Save the current configuration
        self.destroy()  # Ensure the app closes