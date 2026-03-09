import os
import sys
import subprocess
import re
import threading
import queue
import tkinter as tk
from tkinter import filedialog, ttk, StringVar, IntVar, BooleanVar
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

VERSION = "v1.0"

class TranscodeStatus(Enum):
    PENDING = "等待中"
    TRANSCODING = "转码中"
    COMPLETED = "已完成"
    FAILED = "失败"
    CANCELLED = "已取消"

@dataclass
class TranscodeTask:
    file_path: str
    status: TranscodeStatus = TranscodeStatus.PENDING
    progress: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    elapsed_time: str = "00:00:00"
    error_message: str = ""
    output_path: str = ""
    process = None

class VideoTranscoder:
    def __init__(self, root):
        self.root = root
        self.root.title("视频转码工具 v1.0")
        self.root.geometry("900x700")
        self.root.minsize(800, 650)
        
        self.ffmpeg_path = StringVar(value=os.path.join(os.getcwd(), "bin", "ffmpeg.exe"))
        self.output_folder = StringVar(value=os.getcwd())
        
        self.encoder = StringVar(value="libx264")
        self.resolution = StringVar(value="1920x1080")
        self.bitrate = StringVar(value="5000k")
        self.fps = StringVar(value="30")
        self.audio_encoder = StringVar(value="aac")
        self.audio_bitrate = StringVar(value="128k")
        self.audio_channels = StringVar(value="2")
        
        self.concurrent_count = IntVar(value=2)
        
        self.tasks: Dict[str, TranscodeTask] = {}
        self.task_list: List[str] = []
        self.is_transcoding = BooleanVar(value=False)
        self.executor: Optional[ThreadPoolExecutor] = None
        self.cancel_flag = threading.Event()
        
        self.progress_queue = queue.Queue()
        self.log_queue = queue.Queue()
        
        self.total_start_time: Optional[float] = None
        self.total_elapsed_time = StringVar(value="00:00:00")
        self.completed_count = IntVar(value=0)
        self.total_count = IntVar(value=0)
        
        self.create_widgets()
        
        self.update_timer_thread = None
        self._start_log_consumer()

    def create_widgets(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)
        
        about_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="关于", menu=about_menu)
        about_menu.add_command(label="关于软件", command=self.show_about)
        
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        self._create_input_frame(main_frame)
        self._create_params_frame(main_frame)
        self._create_control_frame(main_frame)
        self._create_progress_frame(main_frame)
        self._create_log_frame(main_frame)
        
        self._configure_styles()

    def _create_input_frame(self, parent):
        input_frame = ttk.LabelFrame(parent, text="输入设置", padding="5")
        input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=2)
        input_frame.columnconfigure(1, weight=1)
        
        ttk.Label(input_frame, text="视频文件:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.file_count_label = ttk.Label(input_frame, text="未选择文件", foreground="gray")
        self.file_count_label.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        
        btn_frame = ttk.Frame(input_frame)
        btn_frame.grid(row=0, column=2, padx=5, pady=2)
        ttk.Button(btn_frame, text="选择文件", command=self.select_input_files).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="选择文件夹", command=self.select_input_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="清空", command=self.clear_files).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(input_frame, text="输出文件夹:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(input_frame, textvariable=self.output_folder).grid(row=1, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(input_frame, text="浏览", command=self.select_output_folder).grid(row=1, column=2, padx=5, pady=2)

    def _create_params_frame(self, parent):
        params_frame = ttk.LabelFrame(parent, text="转码参数", padding="5")
        params_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=2)
        
        video_frame = ttk.Frame(params_frame)
        video_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(video_frame, text="视频编码器:").pack(side=tk.LEFT, padx=5)
        encoders = ttk.Combobox(video_frame, textvariable=self.encoder, width=12,
                               values=["libx264", "libx265", "mpeg4", "libvpx-vp9", 
                                       "h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "copy"])
        encoders.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(video_frame, text="分辨率:").pack(side=tk.LEFT, padx=5)
        resolutions = ttk.Combobox(video_frame, textvariable=self.resolution, width=10,
                                 values=["1920x1080", "1280x720", "720x480", "640x360", "copy"])
        resolutions.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(video_frame, text="比特率:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(video_frame, textvariable=self.bitrate, width=8).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(video_frame, text="帧率:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(video_frame, textvariable=self.fps, width=5).pack(side=tk.LEFT, padx=5)
        
        audio_frame = ttk.Frame(params_frame)
        audio_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(audio_frame, text="音频编码器:").pack(side=tk.LEFT, padx=5)
        audio_encoders = ttk.Combobox(audio_frame, textvariable=self.audio_encoder, width=8,
                                     values=["aac", "mp3", "libopus", "libvorbis", "copy"])
        audio_encoders.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(audio_frame, text="比特率:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(audio_frame, textvariable=self.audio_bitrate, width=8).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(audio_frame, text="声道:").pack(side=tk.LEFT, padx=5)
        channels = ttk.Combobox(audio_frame, textvariable=self.audio_channels, width=3, values=["1", "2", "6"])
        channels.pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(audio_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Label(audio_frame, text="并发数:").pack(side=tk.LEFT, padx=5)
        concurrent_spin = ttk.Spinbox(audio_frame, from_=1, to=8, textvariable=self.concurrent_count, width=3)
        concurrent_spin.pack(side=tk.LEFT, padx=5)
        ttk.Label(audio_frame, text="(1-8个线程)", foreground="gray").pack(side=tk.LEFT, padx=5)

    def _create_control_frame(self, parent):
        control_frame = ttk.Frame(parent, padding="5")
        control_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)
        
        self.start_button = ttk.Button(control_frame, text="开始转码", command=self.start_transcoding, style="Accent.TButton")
        self.start_button.grid(row=0, column=0, padx=5, pady=2, sticky=(tk.W, tk.E))
        
        self.cancel_button = ttk.Button(control_frame, text="取消转码", command=self.cancel_transcoding, state=tk.DISABLED, style="Cancel.TButton")
        self.cancel_button.grid(row=0, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))

    def _create_progress_frame(self, parent):
        progress_frame = ttk.LabelFrame(parent, text="转码进度", padding="5")
        progress_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=2)
        progress_frame.columnconfigure(0, weight=1)
        progress_frame.rowconfigure(1, weight=1)
        
        summary_frame = ttk.Frame(progress_frame)
        summary_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=2)
        summary_frame.columnconfigure(1, weight=1)
        
        ttk.Label(summary_frame, text="总体进度:", font=('Arial', 9, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=5)
        self.summary_label = ttk.Label(summary_frame, text="0/0 文件完成", font=('Arial', 9))
        self.summary_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(summary_frame, text="总耗时:", font=('Arial', 9, 'bold')).grid(row=0, column=2, sticky=tk.W, padx=15)
        ttk.Label(summary_frame, textvariable=self.total_elapsed_time, font=('Arial', 9, 'bold'), foreground='#0066cc').grid(row=0, column=3, sticky=tk.W, padx=5)
        
        columns = ("filename", "status", "progress", "elapsed", "output")
        self.task_tree = ttk.Treeview(progress_frame, columns=columns, show="headings", height=8)
        
        self.task_tree.heading("filename", text="文件名")
        self.task_tree.heading("status", text="状态")
        self.task_tree.heading("progress", text="进度")
        self.task_tree.heading("elapsed", text="耗时")
        self.task_tree.heading("output", text="输出文件")
        
        self.task_tree.column("filename", width=200, minwidth=150)
        self.task_tree.column("status", width=80, minwidth=60)
        self.task_tree.column("progress", width=80, minwidth=60)
        self.task_tree.column("elapsed", width=80, minwidth=60)
        self.task_tree.column("output", width=200, minwidth=150)
        
        self.task_tree.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=2)
        
        scrollbar = ttk.Scrollbar(progress_frame, command=self.task_tree.yview)
        scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S), pady=2)
        self.task_tree.config(yscrollcommand=scrollbar.set)
        
        self.task_tree.tag_configure("pending", foreground="gray")
        self.task_tree.tag_configure("transcoding", foreground="#0066cc")
        self.task_tree.tag_configure("completed", foreground="green")
        self.task_tree.tag_configure("failed", foreground="red")
        self.task_tree.tag_configure("cancelled", foreground="orange")

    def _create_log_frame(self, parent):
        log_frame = ttk.LabelFrame(parent, text="转码日志", padding="5")
        log_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=2)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.error_log = tk.Text(log_frame, height=6, wrap=tk.WORD, font=('Consolas', 8))
        self.error_log.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=2)
        self.error_log.config(bg='#f0f0f0', fg='#333333', borderwidth=1, relief=tk.SUNKEN)
        
        scrollbar = ttk.Scrollbar(log_frame, command=self.error_log.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S), pady=2)
        self.error_log.config(yscrollcommand=scrollbar.set)

    def _configure_styles(self):
        self.style.configure("Accent.TButton", 
                           background="#4CAF50", 
                           foreground="white",
                           font=('Arial', 12, 'bold'),
                           padding=12)
        
        self.style.configure("Cancel.TButton", 
                           background="#f44336", 
                           foreground="white",
                           font=('Arial', 10),
                           padding=8)

    def _start_log_consumer(self):
        def consume_logs():
            while True:
                try:
                    msg = self.log_queue.get(timeout=0.5)
                    if msg == "__STOP__":
                        break
                    self.root.after(0, lambda m=msg: self._append_log(m))
                except queue.Empty:
                    continue
        
        self.log_consumer_thread = threading.Thread(target=consume_logs, daemon=True)
        self.log_consumer_thread.start()

    def _append_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.error_log.insert(tk.END, f"[{timestamp}] {message}\n")
        self.error_log.see(tk.END)

    def select_input_files(self):
        file_paths = filedialog.askopenfilenames(
            filetypes=[("视频文件", "*.mp4;*.avi;*.mkv;*.flv;*.mov;*.wmv;*.mpg;*.mpeg;*.m4v;*.webm")]
        )
        if file_paths:
            self._add_files(file_paths)

    def select_input_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            video_extensions = ('.mp4', '.avi', '.mkv', '.flv', '.mov', '.wmv', '.mpg', '.mpeg', '.m4v', '.webm')
            video_files = []
            for file in os.listdir(folder_path):
                if file.lower().endswith(video_extensions):
                    video_files.append(os.path.join(folder_path, file))
            if video_files:
                self._add_files(video_files)
            else:
                self.log_queue.put("所选文件夹中没有找到视频文件")

    def _add_files(self, file_paths):
        for path in file_paths:
            if path not in self.tasks:
                self.tasks[path] = TranscodeTask(file_path=path)
                self.task_list.append(path)
        
        self._update_file_count()
        self._refresh_task_tree()

    def clear_files(self):
        if self.is_transcoding.get():
            self.log_queue.put("转码进行中，无法清空文件列表")
            return
        
        self.tasks.clear()
        self.task_list.clear()
        self._update_file_count()
        self._refresh_task_tree()

    def _update_file_count(self):
        count = len(self.task_list)
        if count == 0:
            self.file_count_label.config(text="未选择文件", foreground="gray")
        else:
            self.file_count_label.config(text=f"已选择 {count} 个视频文件", foreground="green")

    def _refresh_task_tree(self):
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)
        
        for file_path in self.task_list:
            task = self.tasks[file_path]
            filename = os.path.basename(file_path)
            if len(filename) > 30:
                filename = filename[:27] + "..."
            
            progress_str = f"{task.progress}%"
            output_name = os.path.basename(task.output_path) if task.output_path else "-"
            if len(output_name) > 25:
                output_name = output_name[:22] + "..."
            
            tag = task.status.value.lower()
            self.task_tree.insert("", tk.END, iid=file_path, values=(
                filename,
                task.status.value,
                progress_str,
                task.elapsed_time,
                output_name
            ), tags=(tag,))

    def select_output_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.output_folder.set(folder_path)

    def start_transcoding(self):
        if self.is_transcoding.get():
            return
        
        if not self.task_list:
            self.log_queue.put("错误: 请先选择要转码的视频文件")
            return
        
        if not os.path.exists(self.ffmpeg_path.get()):
            self.log_queue.put(f"错误: FFMPEG路径不存在: {self.ffmpeg_path.get()}")
            return
        
        self.cancel_flag.clear()
        self.is_transcoding.set(True)
        self.start_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        
        self.total_start_time = time.time()
        self.completed_count.set(0)
        self.total_count.set(len(self.task_list))
        
        for file_path in self.task_list:
            task = self.tasks[file_path]
            task.status = TranscodeStatus.PENDING
            task.progress = 0
            task.start_time = None
            task.end_time = None
            task.elapsed_time = "00:00:00"
            task.error_message = ""
            task.output_path = self._get_output_file_path(file_path)
        
        self._refresh_task_tree()
        self.clear_log()
        
        self._start_update_timer()
        
        concurrent = min(self.concurrent_count.get(), len(self.task_list))
        self.executor = ThreadPoolExecutor(max_workers=concurrent)
        
        self.log_queue.put(f"开始并发转码，并发数: {concurrent}，总文件数: {len(self.task_list)}")
        
        threading.Thread(target=self._run_transcoding, daemon=True).start()
        threading.Thread(target=self._update_progress, daemon=True).start()

    def _start_update_timer(self):
        def update_timer():
            while self.is_transcoding.get():
                if self.total_start_time:
                    elapsed = int(time.time() - self.total_start_time)
                    hours, remainder = divmod(elapsed, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    self.root.after(0, lambda: self.total_elapsed_time.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}"))
                time.sleep(1)
        
        self.update_timer_thread = threading.Thread(target=update_timer, daemon=True)
        self.update_timer_thread.start()

    def _run_transcoding(self):
        futures = {}
        for file_path in self.task_list:
            if self.cancel_flag.is_set():
                break
            future = self.executor.submit(self._transcode_single_file, file_path)
            futures[future] = file_path
        
        for future in as_completed(futures):
            if self.cancel_flag.is_set():
                break
            file_path = futures[future]
            try:
                future.result()
            except Exception as e:
                self.log_queue.put(f"任务异常: {os.path.basename(file_path)} - {str(e)}")
        
        self.root.after(0, self._finish_transcoding)

    def _transcode_single_file(self, file_path: str) -> bool:
        task = self.tasks[file_path]
        
        if self.cancel_flag.is_set():
            task.status = TranscodeStatus.CANCELLED
            self.progress_queue.put(("status", file_path, TranscodeStatus.CANCELLED))
            return False
        
        task.status = TranscodeStatus.TRANSCODING
        task.start_time = time.time()
        self.progress_queue.put(("status", file_path, TranscodeStatus.TRANSCODING))
        
        self.log_queue.put(f"开始转码: {os.path.basename(file_path)}")
        
        try:
            total_duration = self._get_video_duration(file_path)
            command = self._build_ffmpeg_command(file_path, task.output_path)
            
            if not command:
                task.status = TranscodeStatus.FAILED
                task.error_message = "构建命令失败"
                self.progress_queue.put(("status", file_path, TranscodeStatus.FAILED))
                return False
            
            cmd_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command)
            self.log_queue.put(f"执行命令: {cmd_str}")
            
            if sys.platform.startswith('win'):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
                process = subprocess.Popen(
                    cmd_str,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    shell=True,
                    startupinfo=startupinfo,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
            else:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    text=True
                )
            
            task.process = process
            
            self._read_ffmpeg_output(process, file_path, total_duration)
            
            process.wait()
            
            if self.cancel_flag.is_set():
                try:
                    process.terminate()
                except:
                    pass
                task.status = TranscodeStatus.CANCELLED
                self.progress_queue.put(("status", file_path, TranscodeStatus.CANCELLED))
                return False
            
            if process.returncode == 0:
                task.end_time = time.time()
                task.status = TranscodeStatus.COMPLETED
                task.progress = 100
                self.progress_queue.put(("complete", file_path))
                self.log_queue.put(f"转码完成: {os.path.basename(file_path)}")
                return True
            else:
                task.status = TranscodeStatus.FAILED
                task.error_message = f"返回码: {process.returncode}"
                self.progress_queue.put(("status", file_path, TranscodeStatus.FAILED))
                self.log_queue.put(f"转码失败: {os.path.basename(file_path)} - 返回码 {process.returncode}")
                return False
                
        except Exception as e:
            task.status = TranscodeStatus.FAILED
            task.error_message = str(e)
            self.progress_queue.put(("status", file_path, TranscodeStatus.FAILED))
            self.log_queue.put(f"转码错误: {os.path.basename(file_path)} - {str(e)}")
            return False

    def _read_ffmpeg_output(self, process, file_path: str, total_duration: float):
        try:
            while True:
                if self.cancel_flag.is_set():
                    break
                
                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    continue
                
                line = line.strip()
                if not line:
                    continue
                
                if 'error' in line.lower() or 'failed' in line.lower():
                    self.log_queue.put(f"[{os.path.basename(file_path)}] {line}")
                
                match = re.search(r'out_time=(\d{2}:\d{2}:\d{2}\.\d{6})', line)
                if match:
                    time_str = match.group(1)
                    parts = time_str.split(':')
                    try:
                        progress_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                        
                        if total_duration and total_duration > 0:
                            percent = min(int((progress_seconds / total_duration) * 100), 99)
                        else:
                            percent = min(int((progress_seconds / 3600) * 100), 99)
                        
                        self.progress_queue.put(("progress", file_path, percent))
                    except (ValueError, IndexError):
                        pass
                        
        except Exception as e:
            self.log_queue.put(f"读取输出错误: {str(e)}")

    def _update_progress(self):
        while self.is_transcoding.get():
            try:
                msg = self.progress_queue.get(timeout=0.5)
                
                if msg[0] == "progress":
                    _, file_path, percent = msg
                    if file_path in self.tasks:
                        task = self.tasks[file_path]
                        task.progress = percent
                        if task.start_time:
                            elapsed = int(time.time() - task.start_time)
                            hours, remainder = divmod(elapsed, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            task.elapsed_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        self.root.after(0, self._refresh_task_tree)
                
                elif msg[0] == "status":
                    _, file_path, status = msg
                    if file_path in self.tasks:
                        self.tasks[file_path].status = status
                        self.root.after(0, self._refresh_task_tree)
                
                elif msg[0] == "complete":
                    _, file_path = msg
                    if file_path in self.tasks:
                        task = self.tasks[file_path]
                        if task.start_time and task.end_time:
                            elapsed = int(task.end_time - task.start_time)
                            hours, remainder = divmod(elapsed, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            task.elapsed_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        self.root.after(0, self._refresh_task_tree)
                        self.root.after(0, self._update_summary)
                
            except queue.Empty:
                continue

    def _update_summary(self):
        completed = sum(1 for t in self.tasks.values() if t.status == TranscodeStatus.COMPLETED)
        failed = sum(1 for t in self.tasks.values() if t.status == TranscodeStatus.FAILED)
        cancelled = sum(1 for t in self.tasks.values() if t.status == TranscodeStatus.CANCELLED)
        total = len(self.task_list)
        
        self.completed_count.set(completed)
        self.summary_label.config(text=f"{completed + failed + cancelled}/{total} 文件处理完成 (成功:{completed} 失败:{failed} 取消:{cancelled})")

    def _finish_transcoding(self):
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
        
        self.is_transcoding.set(False)
        self.start_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.DISABLED)
        
        self._update_summary()
        self._refresh_task_tree()
        
        completed = sum(1 for t in self.tasks.values() if t.status == TranscodeStatus.COMPLETED)
        failed = sum(1 for t in self.tasks.values() if t.status == TranscodeStatus.FAILED)
        cancelled = sum(1 for t in self.tasks.values() if t.status == TranscodeStatus.CANCELLED)
        
        self.log_queue.put(f"转码任务全部完成! 成功:{completed} 失败:{failed} 取消:{cancelled}")

    def cancel_transcoding(self):
        self.cancel_flag.set()
        self.log_queue.put("正在取消所有转码任务...")
        
        for file_path, task in self.tasks.items():
            if task.status == TranscodeStatus.PENDING or task.status == TranscodeStatus.TRANSCODING:
                task.status = TranscodeStatus.CANCELLED
                if task.process:
                    try:
                        task.process.terminate()
                    except:
                        pass
        
        self._refresh_task_tree()

    def _build_ffmpeg_command(self, input_path: str, output_path: str) -> List[str]:
        if not input_path or not output_path:
            return []
        
        command = [self.ffmpeg_path.get()]
        
        command.extend(["-progress", "pipe:1"])
        command.extend(["-nostats"])
        
        encoder = self.encoder.get()
        
        if encoder in ["h264_nvenc", "hevc_nvenc"] and encoder != "copy":
            command.extend(["-hwaccel", "cuda"])
        elif encoder in ["h264_qsv", "hevc_qsv"] and encoder != "copy":
            command.extend(["-hwaccel", "qsv"])
        
        command.extend(["-i", input_path, "-y"])
        
        if encoder != "copy":
            command.extend(["-c:v", encoder])
            
            resolution = self.resolution.get()
            if resolution != "copy":
                command.extend(["-s", resolution])
            
            command.extend([
                "-b:v", self.bitrate.get(),
                "-r", self.fps.get(),
                "-pix_fmt", "yuv420p"
            ])
        else:
            command.extend(["-c:v", "copy"])
        
        audio_encoder = self.audio_encoder.get()
        if audio_encoder != "copy":
            command.extend([
                "-c:a", audio_encoder,
                "-b:a", self.audio_bitrate.get(),
                "-ac", self.audio_channels.get()
            ])
        else:
            command.extend(["-c:a", "copy"])
        
        command.append(output_path)
        return command

    def _get_video_duration(self, file_path: str) -> float:
        try:
            cmd = [
                self.ffmpeg_path.get().replace('ffmpeg.exe', 'ffprobe.exe'),
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            
            if sys.platform.startswith('win'):
                cmd_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in cmd)
                result = subprocess.check_output(cmd_str, shell=True, universal_newlines=True)
            else:
                result = subprocess.check_output(cmd, universal_newlines=True)
            
            duration = float(result.strip())
            return duration if duration > 0 else 3600
        except Exception as e:
            self.log_queue.put(f"获取视频时长失败: {os.path.basename(file_path)} - {str(e)}")
            return 3600

    def _get_output_file_path(self, input_path: str) -> str:
        input_name = os.path.basename(input_path)
        name, ext = os.path.splitext(input_name)
        
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        encoder = self.encoder.get()
        resolution = self.resolution.get()
        bitrate = self.bitrate.get()
        
        output_name = f"{name}_{current_time}_{encoder}_{resolution}_{bitrate}_transcoded.mp4"
        return os.path.join(self.output_folder.get(), output_name)

    def show_about(self):
        about_window = tk.Toplevel(self.root)
        about_window.title("关于软件")
        about_window.geometry("400x200")
        about_window.resizable(False, False)
        about_window.attributes("-topmost", True)
        
        about_window.transient(self.root)
        about_window.grab_set()
        
        about_window.update_idletasks()
        x = (about_window.winfo_screenwidth() // 2) - (400 // 2)
        y = (about_window.winfo_screenheight() // 2) - (200 // 2)
        about_window.geometry(f"400x200+{x}+{y}")
        
        content_frame = ttk.Frame(about_window, padding="20")
        content_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        title_label = ttk.Label(content_frame, text="视频转码工具 v1.0", font=('Arial', 14, 'bold'))
        title_label.grid(row=0, column=0, pady=5)
        
        author_label = ttk.Label(content_frame, text="作者: 北小菜", font=('Arial', 10))
        author_label.grid(row=1, column=0, pady=3)
        
        github_label = ttk.Label(content_frame, text="开源地址: github.com/beixiaocai/BXC_VideoTranscode", 
                             foreground="blue", cursor="hand2", font=('Arial', 10))
        github_label.grid(row=2, column=0, pady=3)
        
        def open_github(event):
            import webbrowser
            webbrowser.open("https://github.com/beixiaocai/BXC_VideoTranscode")
        
        github_label.bind("<Button-1>", open_github)
        
        bilibili_label = ttk.Label(content_frame, text="B站主页: space.bilibili.com/487906612", 
                             foreground="blue", cursor="hand2", font=('Arial', 10))
        bilibili_label.grid(row=3, column=0, pady=3)
        
        def open_bilibili(event):
            import webbrowser
            webbrowser.open("https://space.bilibili.com/487906612")
        
        bilibili_label.bind("<Button-1>", open_bilibili)
        
        def on_escape(event):
            about_window.destroy()
        
        about_window.bind("<Escape>", on_escape)
        
        about_window.columnconfigure(0, weight=1)

    def log_message(self, message):
        self.log_queue.put(message)

    def clear_log(self):
        self.error_log.delete(1.0, tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoTranscoder(root)
    root.mainloop()
