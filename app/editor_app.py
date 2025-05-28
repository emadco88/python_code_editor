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
        try:
            import jedi
            self.jedi = jedi
        except ImportError:
            jedi = None
            self.jedi = None
            print("Jedi is not installed")

        self.open_new_tab(initial_code=self.get_last_code())
        self.should_stop = threading.Event()

    def ctrl_jump_right(self, event=None):
        self._jump_word(direction="right")
        return "break"

    def ctrl_jump_left(self, event=None):
        self._jump_word(direction="left")
        return "break"

    def shift_ctrl_jump_right(self, event=None):
        text = self.get_active_text()
        if self.sel_anchor is None:
            self.sel_anchor = text.index("insert")  # ✅ Capture BEFORE jumping
        self._jump_word("right", select=True)
        return "break"

    def shift_ctrl_jump_left(self, event=None):
        text = self.get_active_text()
        if self.sel_anchor is None:
            self.sel_anchor = text.index("insert")  # ✅ Capture BEFORE jumping
        self._jump_word("left", select=True)
        return "break"

    def _jump_word(self, direction="right", select=None):
        text = self.get_active_text()
        cur = text.index("insert")

        if direction == "right":
            line, col = map(int, cur.split("."))
            end = text.index(f"{line}.end")
            chunk = text.get(cur, end)

            i = 0
            while i < len(chunk) and chunk[i].isspace():
                i += 1
            while i < len(chunk) and (chunk[i].isalnum() or chunk[i] == "_"):
                i += 1

            new_index = text.index(f"{cur}+{i or 1}c")

        else:
            line, col = map(int, cur.split("."))
            start = f"{line}.0"
            chunk = text.get(start, cur)

            i = len(chunk)
            while i > 0 and chunk[i - 1].isspace():
                i -= 1
            while i > 0 and (chunk[i - 1].isalnum() or chunk[i - 1] == "_"):
                i -= 1

            new_index = text.index(f"{start}+{i}c") if i != len(chunk) else text.index(f"{cur}-1c")

        if select:
            # ✅ Always move the cursor first
            text.mark_set("insert", new_index)
            text.see(new_index)

            # ✅ Only set anchor the first time
            if self.sel_anchor is None:
                self.sel_anchor = cur

            # ✅ Normalize selection range
            start = self.sel_anchor
            end = new_index
            if text.compare(start, ">", end):
                start, end = end, start

            text.tag_remove("sel", "1.0", "end")
            text.tag_add("sel", start, end)
        else:
            text.tag_remove("sel", "1.0", "end")
            text.mark_set("insert", new_index)
            text.see(new_index)
            self.sel_anchor = None

    def delete_last_word(self, event=None):
        text = self.get_active_text()
        index = text.index("insert")
        line_start = f"{index.split('.')[0]}.0"
        current_line = text.get(line_start, index)

        # Walk backward to find word start
        word_end = len(current_line)
        word_start = word_end
        while word_start > 0 and (current_line[word_start - 1].isalnum() or current_line[word_start - 1] == "_"):
            word_start -= 1

        if word_start < word_end:
            text.delete(f"insert-{word_end - word_start}c", "insert")
        # return "break"

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

    def autoclose_pairs(self, event):
        text = self.get_active_text()
        pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
        # open_chars = pairs.keys()
        close_chars = pairs.values()

        start = end = None
        try:
            start = text.index("sel.first")
            end = text.index("sel.last")
            selected = True
        except tk.TclError:
            selected = False

        index = text.index("insert")
        next_char = text.get(index)
        if event.char in close_chars:
            if next_char == event.char:
                text.mark_set("insert", f"{index}+1c")
                return "break"

        if event.char in pairs:
            if selected:
                selected_text = text.get(start, end)
                text.delete(start, end)
                text.insert(start, event.char + selected_text + pairs[event.char])
                text.mark_set("insert", f"{start}+{len(event.char + selected_text) + 1}c")
                return "break"

            text.insert(index, event.char + pairs[event.char])
            text.mark_set("insert", f"{index}+1c")
            return "break"

        return None

    def hide_autocomplete_menu(self, event=None):
        if self.active_menu:
            self.active_menu.unpost()
            self.active_menu = None
        return "break"

    def show_autocomplete(self, event=None, str_complete=None):
        text = self.get_active_text()

        if self.active_menu:
            self.active_menu.unpost()
            self.active_menu = None

        try:
            if str_complete:
                completions = str_complete
            elif workbooks := self._get_opened_workbooks():
                completions = workbooks
            else:
                prefix = ''
                code = text.get("1.0", "end")
                line, column = map(int, text.index("insert").split("."))
                if event:
                    current_line = text.get(f"{line}.0", f"{line}.{column}")
                    prefix = ''
                    for char in reversed(current_line):
                        if not (char.isalnum() or char == '_'):
                            break
                        prefix = char + prefix

                    if len(prefix) < 1:
                        if current_line.strip() == '':
                            text.insert("insert", " " * 4)
                        return "break"
                if not self.jedi:
                    print("jedi not installed, cancel autocompletion ...")
                    return "break"
                script = self.jedi.Script(code=code, path="script.py")
                completions = script.complete(line, column)
                completions = [x.name for x in completions if not x.name.startswith("__") and x.name.startswith(prefix)]

            if not completions:
                return "break"

            completions.sort(key=lambda x: x.lower())

            if len(completions) == 1:
                name = completions[0]
                return self.insert_completion(name, text=text)

            menu = tk.Menu(self, tearoff=0)
            self.active_menu = menu
            for comp in completions:
                menu.add_command(
                    label=comp,
                    command=lambda complete_name=comp, m=menu: self.insert_completion(complete_name, m))

            x, y, _, _ = text.bbox("insert")
            if x is None or y is None:
                return "break"
            x += text.winfo_rootx()
            y += text.winfo_rooty() + 20
            menu.post(x, y)
            return "break"
        except Exception as e:
            print("Autocomplete error:", e)
            return "break"

    def insert_completion(self, name, menu=None, text=None):
        text = text or self.get_active_text()
        index = text.index("insert")
        line_start = f"{index.split('.')[0]}.0"
        current_line = text.get(line_start, index)
        prefix = ''
        for char in reversed(current_line):
            if not (char.isalnum() or char == '_'):
                break
            prefix = char + prefix
        if prefix:
            text.delete(f"insert-{len(prefix)}c", "insert")
        text.insert("insert", name)
        if menu:
            menu.unpost()
        return "break"

    def handle_backspace(self, event=None):
        text = self.get_active_text()
        cursor_index = text.index("insert")
        try:
            sel_start = text.index("sel.first")
            sel_end = text.index("sel.last")
            if sel_start != sel_end:
                return  # do nothing, allow default behavior
        except tk.TclError:
            pass  # no selection
        pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
        open_chars = pairs.keys()
        index = text.index("insert")
        next_char = text.get(index)

        if event.keysym == "BackSpace":
            prev_char = text.get(f"{index}-1c")
            if prev_char in open_chars and next_char == pairs[prev_char]:
                text.delete(f"{index}-1c", f"{index}+1c")
                return "break"

        # Get current line start to cursor
        line_start = f"{cursor_index.split('.')[0]}.0"
        before_cursor = text.get(line_start, cursor_index)

        # If last 4 characters before cursor are spaces
        if before_cursor.endswith(" " * 4):
            text.delete(f"{cursor_index}-4c", cursor_index)
            return "break"

    def run_code(self):
        self.run_button.config(state="disabled")
        self.save_current_code()
        text = self.get_active_text()
        output = self.get_active_output()
        code = text.get("1.0", "end")
        code = code.replace('\t', '    ')
        text.delete("1.0", "end")  # Clear the widget
        text.insert("1.0", code)

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

    def install_jedi(self):
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "jedi"], check=True)
            # messagebox.showinfo("Success", "Jedi installed successfully. Restarting app...")
            import jedi
            self.jedi = jedi
            # self.restart_app()
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"Failed to install Jedi:\n{e}")

    @staticmethod
    def restart_app():
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def _get_opened_workbooks(self):
        text = self.get_active_text()

        # Get the current line text
        line_index = text.index("insert").split(".")[0]
        line_text = text.get(f"{line_index}.0", f"{line_index}.end")

        match = re.search(r"\.books\(\s*['\"](.*?)['\"]\s*\)", line_text)
        if not match:
            return  # No match, skip autocomplete

        old_name = match.group(1)

        # Remove old_name inside .books('old_name') → leave .books('')
        cursor_index = text.search(old_name, f"{line_index}.0", stopindex=f"{line_index}.end")
        if cursor_index:
            end_index = text.index(f"{cursor_index}+{len(old_name)}c")
            text.delete(cursor_index, end_index)

        # Get open workbooks
        try:
            import xlwings as xw
            workbooks = [b.name for b in xw.books]
        except Exception as e:
            print(repr(e))
            workbooks = []

        if workbooks:
            return workbooks

    def show_workbooks_autocomplete(self, event=None):
        workbooks = self._get_opened_workbooks()
        if workbooks:
            self.show_autocomplete(event=event, str_complete=workbooks)

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

    def ctrl_plus(self, event):
        if (event.state & 0x4) and not (event.state & 0x1):
            if event.keycode == 65:
                event.widget.tag_add("sel", "1.0", "end-1c")
                event.widget.mark_set("insert", "end-1c")
                event.widget.see("insert")
                return 'break'
            elif event.keycode == 83:
                self.save_current_code()
            elif event.keycode == 86:
                try:
                    # Get clipboard content
                    clipboard = event.widget.clipboard_get()
                    # Replace tabs with 4 spaces
                    clipboard = clipboard.replace('\t', '    ')
                    # Insert the modified content at the cursor
                    event.widget.insert(tk.INSERT, clipboard)
                except tk.TclError:
                    pass  # Handle cases when clipboard is empty or unsupported
                return "break"  # Prevent the default paste behavior
