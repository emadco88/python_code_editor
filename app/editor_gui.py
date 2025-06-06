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

        ctrl_bar = tk.Frame(self)
        self.ctrl_bar = ctrl_bar
        ctrl_bar.pack(side='top', anchor='w', fill='x')
        tk.Label(ctrl_bar, text="Font Size:").pack(side='left', padx=5, pady=5)
        tk.Button(ctrl_bar, text="+", command=lambda: self.increase_font(), width=2).pack(side='left')
        tk.Button(ctrl_bar, text="-", command=lambda: self.decrease_font(), width=2).pack(side='left')
        self.run_button = tk.Button(ctrl_bar, text="Run Code", command=lambda: self.run_code())
        self.run_button.pack(side='left', padx=10)
        tk.Button(ctrl_bar, text="Stop Code", command=lambda: self.stop_code()).pack(side='left', padx=10)
        tk.Button(ctrl_bar, text="Check Errors", command=lambda: self.check_errors()).pack(side='left', padx=10)
        tk.Button(ctrl_bar, text="Save Code", command=lambda: self.save_current_code()).pack(side='left', padx=10)
        tk.Button(ctrl_bar, text="Close Editor", command=lambda: self.close_editor()).pack(side='left', padx=10)
        tk.Button(ctrl_bar, text="Open Editor", command=lambda: self.open_new_tab()).pack(side='left', padx=10)
        tk.Button(ctrl_bar, text="Manage Codes", command=lambda: self.manage_codes()).pack(side='left', padx=10)
        tk.Button(ctrl_bar, text="Quit App", command=lambda: self.quit_app()).pack(side='left', padx=10)

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

        x_scroll_edit = tk.Scrollbar(editor_frame, orient="horizontal")
        y_scroll_edit = tk.Scrollbar(editor_frame, orient="vertical")

        text = tk.Text(editor_frame,
                       wrap='none',
                       font=("Courier", 16, "bold"),
                       undo=True,
                       xscrollcommand=x_scroll_edit.set,
                       yscrollcommand=y_scroll_edit.set)

        # Correct scrollbar config
        x_scroll_edit.config(command=text.xview)
        y_scroll_edit.config(command=lambda *args: (text.yview(*args), text.after_colorify()))

        # Packing order
        x_scroll_edit.pack(fill='x', side='bottom')
        y_scroll_edit.pack(fill='y', side='right')
        text.pack(fill='both', expand=True)

        text.bind("<Escape>", lambda e, txt=text: self.cancel_restore(txt))
        if animated:
            text.insert("1.0", "")  # Start empty
            text.full_code = initial_code
            text.char_index = 0
            text.bind("<Control-0>", lambda e, txt=text: self.restore_next_char(txt))
            text.bind("<Escape>", lambda e, txt=text: self.cancel_restore(txt))
        else:
            text.insert("1.0", initial_code)
        ###############################################################
        output_frame = tk.Frame(tab, height=120)
        output_frame.pack(fill='x', side='bottom')
        output_frame.pack_propagate(False)

        x_scroll_out = tk.Scrollbar(output_frame, orient="horizontal")
        y_scroll_out = tk.Scrollbar(output_frame, orient='vertical')

        output = tk.Text(output_frame,
                         bg="black", fg="lime", font=("Courier", 12), wrap="none",
                         xscrollcommand=x_scroll_out.set,
                         yscrollcommand=y_scroll_out.set, )
        output.disable_colorify = True
        x_scroll_out.config(command=output.xview)
        y_scroll_out.config(command=output.yview)

        x_scroll_out.pack(fill='x', side='bottom')
        y_scroll_out.pack(fill='y', side='right')

        output.pack(fill='both', expand=True)

        output.insert("1.0", "# Output Console\n")
        # Pack the scrollbar BELOW the text

        tab.text = text
        tab.output = output
        tab.tab_id = tab_id
        self.tab_control.select(tab)

    @staticmethod
    def restore_next_char(text_widget):
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

    def show_workbooks_autocomplete(self, e):
        ...

    def check_errors(self):
        ...

    def stop_code(self):
        ...

    def ctrl_plus(self, e):
        ...
