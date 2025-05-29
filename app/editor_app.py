import os
import subprocess
import tempfile
import threading
import tkinter as tk
import sqlite3
import traceback
from tkinter import messagebox
from datetime import datetime
import sys
import ast
from . import editor_gui
from .name_checker import NameChecker
import re

MAX_OUTPUT_CHARS = 2000
MODIFIER_MASK = 0x1 | 0x4 | 0x8


class App(editor_gui.GUI):
    def __init__(self):
        super(App, self).__init__()
        self.process = None
        self.thread = None
        self.open_new_tab(initial_code=self.get_last_code())
        self.should_stop = threading.Event()

    def get_active_tab(self):
        return self.tab_control.nametowidget(self.tab_control.select())

    def get_active_text(self):
        return self.get_active_tab().text

    def get_active_output(self):
        return self.get_active_tab().output

    def get_active_tab_id(self):
        return self.get_active_tab().tab_id

    def on_close(self):
        self.save_current_code()
        self.destroy()

    def quit_app(self):
        try:
            self.save_current_code()
        except Exception as ex:
            print("Quit App Error:", repr(ex))
            pass
        finally:
            self.destroy()

    def close_editor(self):
        tab_id = self.tab_control.select()
        if tab_id:
            self.tab_control.forget(tab_id)

    def save_current_code(self):
        code = self.get_active_text().get("1.0", tk.END).strip()
        tab_id = self.get_active_tab_id()
        if code:
            self.upsert_code(tab_id, code)

    def manage_codes(self):
        win = tk.Toplevel(self)
        win.title("Manage Saved Codes")
        win.geometry("700x400")

        frame = tk.Frame(win)
        frame.pack(fill='both', expand=True)

        canvas = tk.Canvas(frame)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        conn = sqlite3.connect(self.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, tab_id, timestamp, code FROM codes ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()

        for row in rows:
            code_id, tab_id, timestamp, code = row
            first_lines = "\n".join(code.splitlines()[:3])

            box = tk.LabelFrame(scrollable_frame, text=f"Tab ID: {tab_id} | ID: {code_id} | {timestamp}", padx=10,
                                pady=5, font=("Arial", 10, "bold"))
            box.pack(fill='x', padx=10, pady=5)

            preview = tk.Label(box, text=first_lines.strip(), justify='left', anchor='w', font=("Courier", 10),
                               bg="white", relief="sunken")
            preview.pack(fill='x', padx=5, pady=5)

            btn_restore = tk.Button(box, text="Restore",
                                    command=lambda init_code=code: self.open_new_tab(initial_code=init_code))
            btn_restore.pack(side='left', padx=5)
            btn_restore_by_char = tk.Button(box, text="Restore By Char",
                                            command=lambda init_code=code: self.open_new_tab(
                                                initial_code=init_code, animated=True))

            btn_restore_by_char.pack(side='left', padx=5)

            def make_editor(e_code_id=code_id, e_code=code):
                def edit_code():
                    editor_win = tk.Toplevel(win)
                    editor_win.title(f"Edit Code ID {e_code_id}")
                    text = tk.Text(editor_win, wrap='word', font=("Courier", 12))
                    text.insert("1.0", e_code)
                    text.pack(fill='both', expand=True)

                    def save_edit():
                        new_code = text.get("1.0", "end-1c")
                        extra_conn = sqlite3.connect(self.DB_PATH)
                        cur = extra_conn.cursor()
                        cur.execute("UPDATE codes SET code = ?, timestamp = ? WHERE id = ?",
                                    (new_code, datetime.now().isoformat(), e_code_id))
                        extra_conn.commit()
                        extra_conn.close()
                        editor_win.destroy()
                        win.destroy()
                        self.manage_codes()

                    tk.Button(editor_win, text="Save", command=save_edit).pack(pady=5)

                return edit_code

            btn_edit = tk.Button(box, text="Edit", command=make_editor())
            btn_edit.pack(side='left', padx=5)

            def delete_code(del_code_id=code_id):
                if messagebox.askyesno("Confirm Delete", f"Delete code ID {del_code_id}?"):
                    extra_conn = sqlite3.connect(self.DB_PATH)
                    cur = extra_conn.cursor()
                    cur.execute("DELETE FROM codes WHERE id = ?", (del_code_id,))
                    extra_conn.commit()
                    extra_conn.close()
                    win.destroy()
                    self.manage_codes()

            btn_delete = tk.Button(box, text="Delete", command=delete_code)
            btn_delete.pack(side='left', padx=5)

    ###################################
    def increase_font(self):
        self.font_size += 2
        self.get_active_text().config(font=("Courier", self.font_size, "bold"))

    def decrease_font(self):
        if self.font_size > 6:
            self.font_size -= 2
            self.get_active_text().config(font=("Courier", self.font_size, "bold"))

    def run_code(self):
        self.run_button.config(state="disabled")
        self.save_current_code()
        text = self.get_active_text()
        output = self.get_active_output()
        code = text.get("1.0", "end")
        if '\t' in code:
            code = code.replace('\t', '    ')
            text.delete("1.0", "end")  # Clear the widget
            text.insert("1.0", code)
            text.colrify()

        if re.search(r'\binput\s*\(', code) and not re.search(r'def input\(', code):
            input_override = (
                "# ### Auto generated code. #######\n"
                "# ### Do not remove! #############\n"
                "from tkinter.simpledialog import askstring\n"
                "def input(prompt=''):\n"
                "    return askstring('Input', prompt or 'Enter value:')\n"
                "##################################\n"
            )
            text.insert("1.0", input_override)
            code = text.get("1.0", "end")

        # Clear output and error marks
        output.delete("1.0", "end")
        text.tag_remove("exec_error", "1.0", "end")
        text.tag_configure("exec_error", underline=True, foreground="red")

        # Write code to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode="w", encoding="utf-8") as tmp:
            tmp.write(code)
            script_path = tmp.name

        def mark_error_line():
            try:
                compiled = compile(code, script_path, "exec")
                exec(compiled, {})
            except Exception as e:
                tb = traceback.extract_tb(e.__traceback__)
                for entry in reversed(tb):
                    if entry.filename == script_path:
                        lineno = entry.lineno
                        start = f"{lineno}.0"
                        end = f"{lineno}.end"
                        text.tag_add("exec_error", start, end)
                        break

                if isinstance(e, ModuleNotFoundError):
                    module_name = e.name
                    confirm = messagebox.askokcancel("Missing Module",
                                                     f"Module '{module_name}' is missing.\nInstall it?")
                    if confirm:
                        try:
                            subprocess.run([sys.executable, "-m", "pip", "install", module_name], check=True)
                            messagebox.showinfo("Installed",
                                                f"Module '{module_name}' installed.\nPlease re-run your code.")
                        except subprocess.CalledProcessError as install_error:
                            messagebox.showerror("Install Failed",
                                                 f"Could not install '{module_name}':\n{install_error}")
                    else:
                        output.insert("end", f"Missing module: {module_name}\n")
                else:
                    output.insert("end", f"Execution error: {str(e)}\n")

        def execute():
            try:
                self.process = subprocess.Popen(
                    [sys.executable, script_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    # encoding='utf-8'
                )
                stdout, stderr = self.process.communicate()

                output_text = stdout + stderr
                trimmed = output_text[:MAX_OUTPUT_CHARS]
                if len(output_text) > MAX_OUTPUT_CHARS:
                    trimmed += "\n... (output truncated)"

                output.insert("end", trimmed)

                output.see("end")
                output.update_idletasks()

                if self.process.returncode != 0:
                    mark_error_line()

            except Exception as e:
                output.insert("end", f"Execution error: {str(e)}\n")
            finally:
                if os.path.exists(script_path):
                    os.remove(script_path)
                self.process = None
                self.run_button.config(state="normal")

        self.thread = threading.Thread(target=execute)
        self.thread.start()

    def stop_code(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.get_active_output().insert("end", "\n[!] Code execution forcibly stopped.\n")
            self.process = None
        self.run_button.config(state='normal')

    @staticmethod
    def restart_app():
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def check_errors(self):
        text = self.get_active_text()
        if not text:
            return

        text.tag_delete("syntax_error")
        text.tag_configure("syntax_error", underline=True, foreground="red")

        code = text.get("1.0", "end-1c")
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            lineno, offset = e.lineno, e.offset
            start = f"{lineno}.{max(offset - 1, 0)}"
            end = f"{lineno}.{offset}"
            text.tag_add("syntax_error", start, end)
            messagebox.showerror("Syntax Error", f"{e.msg} on line {lineno}")
            return

        checker = NameChecker()
        checker.visit(tree)
        for name, lineno, col in checker.errors:
            start = f"{lineno}.{col}"
            end = f"{lineno}.{col + len(name)}"
            text.tag_add("syntax_error", start, end)

        if checker.errors:
            msg_lines = [f"Possibly undefined name '{n}' at line {l}" for n, l, _ in checker.errors]
            messagebox.showwarning("Name Errors", "\n".join(msg_lines))
        else:
            text.tag_remove("syntax_error", "1.0", "end")
            text.tag_remove("exec_error", "1.0", "end")
            messagebox.showinfo("Check Complete", "No syntax or name errors detected.")
