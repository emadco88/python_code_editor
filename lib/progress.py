import tkinter as tk
from tkinter import ttk


class ProgressWindow:
    inst = None

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self.top = tk.Toplevel()
        self.top.title("Progress")
        self.progress = ttk.Progressbar(self.top, length=300, mode='determinate')
        self.label = tk.Label(self.top, text="Processing...")
        self.button = tk.Button(self.top, text="Close", command=self.close)
        self.label.pack(pady=5)
        self.progress.pack(padx=20, pady=10)
        self.button.pack(pady=5)
        self.top.protocol("WM_DELETE_WINDOW", lambda: None)  # Disable window close
        self.max_value = 100  # Default

    def __new__(cls):
        if cls.inst is None:
            cls.inst = super().__new__(cls)
        return cls.inst

    def update_progress(self, val, max_val=None, msg="Progress:"):
        try:
            if max_val is not None and max_val != self.max_value:
                self.max_value = max_val
                self.progress['maximum'] = max_val

            self.progress['value'] = val
            self.label.config(text=f"{msg} {val}/{self.max_value}")
            self.top.update()
        except Exception:
            raise Exception("Progressbar closed, ending code.")

    def close(self):
        self.top.destroy()
        ProgressWindow.inst = None


progressbar = tk.Tk()
progressbar.withdraw()
