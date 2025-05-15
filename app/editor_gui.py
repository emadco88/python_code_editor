from tkinter import ttk
from tkinter import Tk
import tkinter as tk
import sqlite3
from datetime import datetime
import time
import os


class GUI(Tk):
    def __init__(self):
        super().__init__()
        self.sel_anchor = None
        self.font_size = 12
        self.DB_PATH = os.path.abspath(
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app.db"))
        self.init_db()
        self.title("Code Editor")
        self.state('zoomed')

        self.start_time = time.time()
        self.char_count = 0
        self.used_paste = False
        self.active_menu = None
        self.local_scope = {}

        control_bar = tk.Frame(self)
        control_bar.pack(side='top', anchor='w', fill='x')
        tk.Label(control_bar, text="Font Size:").pack(side='left', padx=5, pady=5)
        tk.Button(control_bar, text="+", command=lambda: self.increase_font(), width=2).pack(side='left')
        tk.Button(control_bar, text="-", command=lambda: self.decrease_font(), width=2).pack(side='left')
        tk.Button(control_bar, text="Run Code", command=lambda: self.run_code()).pack(side='left', padx=10)
        tk.Button(control_bar, text="Save Code", command=lambda: self.save_current_code()).pack(side='left', padx=10)
        tk.Button(control_bar, text="Close Editor", command=lambda: self.close_editor()).pack(side='left', padx=10)
        tk.Button(control_bar, text="Open Editor", command=lambda: self.open_new_tab()).pack(side='left', padx=10)
        tk.Button(control_bar, text="Manage Codes", command=lambda: self.manage_codes()).pack(side='left', padx=10)
        tk.Button(control_bar, text="Quit App", command=lambda: self.quit_app()).pack(side='left', padx=10)
        try:
            import jedi
        except ImportError:
            tk.Button(control_bar, text="Install Jedi", command=lambda: self.install_jedi()).pack(side='right', padx=10)

        self.tab_control = ttk.Notebook(self)
        self.tab_control.pack(expand=1, fill='both')

        self.after(100, lambda: self.get_active_text().focus_set())
        self.protocol("WM_DELETE_WINDOW", lambda: self.on_close())

    def get_last_code(self):
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT code FROM codes ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        return row[0] if row else ""

    def upsert_code(self, tab_id, code):
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM codes WHERE tab_id = ? ORDER BY id DESC LIMIT 1", (tab_id,))
        existing = c.fetchone()
        if existing:
            c.execute("UPDATE codes SET timestamp = ?, code = ? WHERE id = ?",
                      (datetime.now().isoformat(), code, existing[0]))
        else:
            c.execute("INSERT INTO codes (tab_id, timestamp, code) VALUES (?, ?, ?)",
                      (tab_id, datetime.now().isoformat(), code))
        conn.commit()
        conn.close()

    def init_db(self):
        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tab_id TEXT,
                timestamp TEXT,
                code TEXT
            )
        """)
        conn.commit()
        conn.close()

    def open_new_tab(self, initial_code="", tab_id=None, animated=False):
        if not tab_id:
            # Get last code ID from database
            conn = sqlite3.connect(self.DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT MAX(id) FROM codes")
            row = cur.fetchone()
            conn.close()
            last_id = row[0] if row and row[0] is not None else 0
            next_id = last_id + 1
            tab_id = f"tab_{next_id}"
        else:
            next_id = tab_id.split("_")[-1]

        tab = tk.Frame(self.tab_control)
        self.tab_control.add(tab, text=f"Editor {next_id}")

        editor_frame = tk.Frame(tab)
        editor_frame.pack(fill='both', expand=True)
        output_frame = tk.Frame(tab, height=120)
        output_frame.pack(fill='x', side='bottom')
        output_frame.pack_propagate(False)

        text = tk.Text(editor_frame, wrap='word', font=("Courier", 16, "bold"), undo=True)
        text.bind("<Escape>", lambda e, txt=text: self.cancel_restore(txt))
        if animated:
            text.insert("1.0", "")  # Start empty
            text.full_code = initial_code
            text.char_index = 0
            text.bind("<Control-0>", lambda e, txt=text: self.restore_next_char(txt))
            text.bind("<Escape>", lambda e, txt=text: self.cancel_restore(txt))
        else:
            text.insert("1.0", initial_code)

        text.pack(fill='both', expand=True)
        text.bind("<Control-z>", lambda e: text.edit_undo())
        text.bind("<Escape>", lambda e: self.hide_autocomplete_menu(e))
        text.bind("<KeyPress>", lambda e: self.autoclose_pairs(e))
        text.bind("<Tab>", lambda e: self.show_autocomplete(e))
        text.bind("<Control-BackSpace>", lambda e: self.delete_last_word(e))

        text.bind("<Control-Right>", lambda e: self.ctrl_jump_right(e))
        text.bind("<Shift-Control-Right>", lambda e: self.shift_ctrl_jump_right(e))
        text.bind("<Control-Left>", lambda e: self.ctrl_jump_left(e))
        text.bind("<Shift-Control-Left>", lambda e: self.shift_ctrl_jump_left(e))
        text.bind("<BackSpace>", lambda e: self.handle_backspace(e))

        output = tk.Text(output_frame, bg="black", fg="lime", font=("Courier", 12))
        output.pack(fill='both', expand=True)
        output.insert("1.0", "# Output Console\n")

        tab.text = text
        tab.output = output
        tab.tab_id = tab_id
        self.tab_control.select(tab)

    def restore_next_char(self, text_widget):
        if not hasattr(text_widget, "full_code") or text_widget.char_index >= len(text_widget.full_code):
            return  # Nothing left to insert

        next_char = text_widget.full_code[text_widget.char_index]
        text_widget.insert("end", next_char)
        text_widget.char_index += 1

    def cancel_restore(self, text_widget):
        if hasattr(text_widget, "current_job") and text_widget.current_job:
            text_widget.after_cancel(text_widget.current_job)
            text_widget.current_job = None

    #############
    def increase_font(self):
        ...

    def hide_autocomplete_menu(self, e):
        ...

    def autoclose_pairs(self, e):
        ...

    def show_autocomplete(self, e):
        ...

    def decrease_font(self):
        ...

    def run_code(self):
        ...

    def save_current_code(self):
        ...

    def close_editor(self):
        ...

    def manage_codes(self):
        ...

    def quit_app(self):
        ...

    def get_active_text(self):
        ...

    def on_close(self):
        ...

    def delete_last_word(self, e):
        ...

    def ctrl_jump_right(self, e):
        ...

    def shift_ctrl_jump_right(self, e):
        ...

    def ctrl_jump_left(self, e):
        ...

    def shift_ctrl_jump_left(self, e):
        ...

    def handle_backspace(self, e):
        ...

    def install_jedi(self):
        ...
