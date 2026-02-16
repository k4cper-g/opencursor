"""
Screen-capture-hidden GUI overlay for the agent.

Uses Windows SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) so the overlay
is visible to the user but invisible to PIL ImageGrab.grab().
"""

import ctypes
import queue
import sys
import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

WDA_EXCLUDEFROMCAPTURE = 0x00000011
WDA_MONITOR = 0x00000001
MAX_LINES = 5000


class QueueWriter:
    """File-like object that redirects writes to a queue (and optionally stdout)."""

    def __init__(self, log_queue: queue.Queue, original=None, dual=True):
        self.queue = log_queue
        self.original = original or sys.__stdout__
        self.dual = dual

    def write(self, text):
        if text:
            self.queue.put(("LOG", text))
            if self.dual:
                self.original.write(text)
                self.original.flush()

    def flush(self):
        if self.dual:
            self.original.flush()


def _hide_from_capture(hwnd: int) -> bool:
    """Call SetWindowDisplayAffinity to hide a window from screen capture."""
    user32 = ctypes.windll.user32
    # Try WDA_EXCLUDEFROMCAPTURE first (Win10 2004+)
    if user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
        return True
    # Fallback to WDA_MONITOR (Win7+) — shows black instead of invisible
    if user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR):
        print("WARNING: Using WDA_MONITOR fallback (overlay will appear black in captures)")
        return True
    print(f"WARNING: SetWindowDisplayAffinity failed (error {ctypes.GetLastError()})")
    return False


class AgentOverlay:
    """Tkinter overlay window that is hidden from screen capture."""

    POLL_MS = 50

    def __init__(self, title="OpenCursor Agent", width=480, dual_output=True):
        self.log_queue: queue.Queue = queue.Queue()
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self.dual_output = dual_output

        # Build root window
        self.root = tk.Tk()
        self.root.title(title)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg="#1e1e1e")

        # Position at right edge of primary monitor
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = screen_w - width
        self.root.geometry(f"{width}x{screen_h}+{x}+0")

        self._build_ui()

        # Render the window so wm_frame() returns a valid HWND
        self.root.update_idletasks()
        self.root.update()

        # Hide from screen capture
        hwnd = int(self.root.wm_frame(), 16)
        _hide_from_capture(hwnd)

        # Start polling the queue
        self._poll_queue()

    def _build_ui(self):
        # Status bar
        status_frame = tk.Frame(self.root, bg="#2d2d2d", height=30)
        status_frame.pack(fill=tk.X, side=tk.TOP)
        status_frame.pack_propagate(False)

        self.status_label = tk.Label(
            status_frame,
            text="Initializing...",
            fg="#00ff88",
            bg="#2d2d2d",
            font=("Consolas", 10),
            anchor="w",
            padx=8,
        )
        self.status_label.pack(fill=tk.X, expand=True)

        # Scrollable log area
        self.text = ScrolledText(
            self.root,
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
            font=("Consolas", 9),
            insertbackground="#d4d4d4",
            selectbackground="#264f78",
            borderwidth=0,
            padx=8,
            pady=4,
            state=tk.DISABLED,
        )
        self.text.pack(fill=tk.BOTH, expand=True)

        # Text tags for color coding
        self.text.tag_configure("error", foreground="#f44747")
        self.text.tag_configure("success", foreground="#00ff88")
        self.text.tag_configure("step", foreground="#569cd6")
        self.text.tag_configure("think", foreground="#ce9178")
        self.text.tag_configure("debug", foreground="#808080")

    def _poll_queue(self):
        """Drain the queue and append messages to the text widget."""
        while True:
            try:
                msg_type, text = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if msg_type == "LOG":
                self._append_text(text)
            elif msg_type == "STATUS":
                self.status_label.config(text=text)
            elif msg_type == "FATAL":
                self._append_text(f"\n[FATAL] {text}\n", tag="error")
                self.status_label.config(text=f"Stopped: {text}", fg="#f44747")

        self.root.after(self.POLL_MS, self._poll_queue)

    def _append_text(self, text, tag=None):
        self.text.configure(state=tk.NORMAL)
        if tag:
            self.text.insert(tk.END, text, tag)
        else:
            self._insert_auto_tagged(text)
        # Trim if too long
        line_count = int(self.text.index("end-1c").split(".")[0])
        if line_count > MAX_LINES:
            self.text.delete("1.0", f"{line_count - MAX_LINES}.0")
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def _insert_auto_tagged(self, text):
        if "ERROR" in text or "WARNING" in text:
            self.text.insert(tk.END, text, "error")
        elif "=====" in text or text.lstrip().startswith("Step "):
            self.text.insert(tk.END, text, "step")
        elif text.lstrip().startswith("Think:"):
            self.text.insert(tk.END, text, "think")
        elif "--- DEBUG ---" in text or "--- END DEBUG ---" in text:
            self.text.insert(tk.END, text, "debug")
        elif "*** DONE" in text:
            self.text.insert(tk.END, text, "success")
        else:
            self.text.insert(tk.END, text)

    def redirect_output(self):
        """Replace sys.stdout/stderr with queue writers."""
        sys.stdout = QueueWriter(self.log_queue, self._original_stdout, self.dual_output)
        sys.stderr = QueueWriter(self.log_queue, self._original_stderr, self.dual_output)

    def set_status(self, text):
        """Thread-safe status bar update."""
        self.log_queue.put(("STATUS", text))

    def run_in_background(self, target, *args, **kwargs):
        """Start target in a daemon thread, catching exits and exceptions."""
        def wrapper():
            try:
                target(*args, **kwargs)
                self.log_queue.put(("STATUS", "Agent finished"))
            except SystemExit as e:
                self.log_queue.put(("FATAL", str(e)))
            except Exception as e:
                self.log_queue.put(("FATAL", f"{type(e).__name__}: {e}"))

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
        return thread

    def mainloop(self):
        self.root.mainloop()
