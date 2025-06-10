import re
import subprocess
import sys
import tkinter as tk

# Save original Text class
from tkinter import messagebox
import builtins
import inspect
from keyword import kwlist

builtin_functions = [name for name, obj in vars(builtins).items()
                     if inspect.isbuiltin(obj) or inspect.isfunction(obj)]

BUILTIN_FUNCTIONS = set(builtin_functions)

KEYWORDS = set(kwlist)

# Prepare regex
KEYWORD_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(w) for w in KEYWORDS) + r')\b')
BUILTIN_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(w) for w in BUILTIN_FUNCTIONS) + r')\b')

OriginalText = tk.Text


# Override tk.Text with auto-customization
class PatchedText(OriginalText):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._colorify_after_id = None
        self.customize_text_widget()
        self.char_count = 0
        self.used_paste = False
        self.active_menu = None
        self.local_scope = {}
        try:
            import jedi
            self.jedi = jedi
        except ImportError:
            jedi = None
            self.jedi = None
            print("Jedi is not installed")

    def insert(self, index, chars, *args):
        result = super().insert(index, chars, *args)
        self.after_colorify()  # or self.colorify() if you want immediate
        return result

    def customize_text_widget(self):
        # Set visual tab width to 4 characters
        self.config(tabs="4c")
        # Make Tab key insert four spaces
        self.bind("<Control-z>", lambda e: self.edit_undo())
        self.bind("<Escape>", lambda e: self.hide_autocomplete_menu(e))
        self.bind("<KeyPress>", lambda e: self.autoclose_pairs(e))
        self.bind("<Tab>", lambda e: self.show_autocomplete(e))
        self.bind("<Control-BackSpace>", lambda e: self.delete_last_word(e))
        self.bind("<Control-space>", lambda e: self.show_workbooks_autocomplete(e))
        self.bind("<Control-Right>", lambda e: self.ctrl_jump_right(e))
        self.bind("<Shift-Control-Right>", lambda e: self.shift_ctrl_jump_right(e))
        self.bind("<Control-Left>", lambda e: self.ctrl_jump_left(e))
        self.bind("<Shift-Control-Left>", lambda e: self.shift_ctrl_jump_left(e))
        self.bind("<BackSpace>", lambda e: self.handle_backspace(e))
        self.bind("<Control-KeyPress>", lambda e: self.ctrl_plus(e))

        # trigger colorify
        self.bind("<MouseWheel>", lambda e: self.after_colorify())
        self.bind("<Button-4>", lambda e: self.after_colorify())  # For Linux scroll up
        self.bind("<Button-5>", lambda e: self.after_colorify())  # For Linux scroll down
        self.bind("<Visibility>", lambda e: self.after_colorify())
        self.bind("<<Modified>>", lambda e: self.after_colorify())  # optional, on edit
        self.bind("<KeyRelease>", lambda e: self.after_colorify())

        # Tags
        self.tag_configure("comment", foreground="#808080")  # PyCharm-style blueish
        self.tag_configure("keyword", foreground="#0000BB")  # PyCharm-style blueish
        self.tag_configure("string", foreground="green")
        self.tag_configure("builtin", foreground="#B58900")  # Yellowish or orange

    def install_jedi(self):
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "jedi"], check=True)
            # messagebox.showinfo("Success", "Jedi installed successfully. Restarting app...")
            import jedi
            self.jedi = jedi
            # self.restart_app()
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"Failed to install Jedi:\n{e}")

    def get_active_text(self):
        widget = self.focus_get()
        if isinstance(widget, tk.Text):
            return widget
        return None

    import re

    def _get_opened_workbooks(self):
        text = self.get_active_text()

        # Get the current line and index
        cursor_index = text.index("insert")
        line_no = cursor_index.split(".")[0]
        line_text = text.get(f"{line_no}.0", f"{line_no}.end")
        cursor_col = int(cursor_index.split(".")[1])

        # Search for `.books('...')` pattern
        for match in re.finditer(r"\.books\(\s*(['\"])(.*?)\1\s*\)", line_text):
            quote_start = match.start(2)
            quote_end = match.end(2)

            # If cursor is between quotes, continue
            if quote_start <= cursor_col <= quote_end:
                old_name = match.group(2)

                # Delete the old name in the widget
                start_idx = f"{line_no}.{quote_start}"
                end_idx = f"{line_no}.{quote_end}"
                text.delete(start_idx, end_idx)

                # Get open workbooks
                try:
                    import xlwings as xw
                    workbooks = [b.name for b in xw.books]
                except Exception as e:
                    print(repr(e))
                    workbooks = []

                return workbooks  # Only return if matched and inside quotes

        return  # Cursor not inside any match, do nothing

    def ctrl_plus(self, event):
        # print(event.keycode)

        self.after_colorify()
        if (event.state & 0x4) and not (event.state & 0x1):
            if event.keycode == 65:
                event.widget.tag_add("sel", "1.0", "end-1c")
                event.widget.mark_set("insert", "end-1c")
                event.widget.see("insert")
                return 'break'
            if event.keycode in (191, 51):  # Ctrl+/ or Ctrl+3
                text = self.get_active_text()

                try:
                    sel_start = text.index("sel.first")
                    sel_end = text.index("sel.last")
                    start_line = int(sel_start.split('.')[0])
                    end_line = int(sel_end.split('.')[0])
                except tk.TclError:
                    # No selection → use current line
                    line = int(text.index("insert").split('.')[0])
                    start_line = end_line = line

                # First check: do all lines start with '#'
                all_commented = True
                for line in range(start_line, end_line + 1):
                    line_text = text.get(f"{line}.0", f"{line}.end")
                    if not line_text.lstrip().startswith("#"):
                        all_commented = False
                        break

                for line in range(start_line, end_line + 1):
                    line_start = f"{line}.0"
                    if all_commented:
                        # Uncomment: remove first #
                        idx = text.search(r'#', line_start, f"{line}.end", regexp=True)
                        if idx:
                            text.delete(idx)
                    else:
                        # Comment: insert #
                        text.insert(line_start, "#")

                return 'break'

    def show_workbooks_autocomplete(self, event=None):
        workbooks = self._get_opened_workbooks()
        if workbooks:
            self.show_autocomplete(event=event, str_complete=workbooks)

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
                # Check if there is a selection
                try:
                    sel_start = text.index("sel.first")
                    sel_end = text.index("sel.last")
                    start_line = int(sel_start.split('.')[0])
                    end_line = int(sel_end.split('.')[0])
                    for line in range(start_line, end_line + 1):
                        text.insert(f"{line}.0", "    ")
                    return "break"  # ← Don't try autocomplete if indenting block
                except tk.TclError:
                    pass  # No selection, continue with normal autocomplete

                # Get full code
                code = text.get("1.0", "end")
                line_str, col_str = text.index("insert").split(".")
                line = int(line_str)
                column = int(col_str)

                # Get text from start of the line to cursor
                current_line = text.get(f"{line}.0", f"{line}.{column}")
                prefix = ''
                for char in reversed(current_line):
                    if not (char.isalnum() or char == '_'):
                        break
                    prefix = char + prefix

                # If nothing before cursor or line is empty → insert four spaces
                if not prefix.strip():
                    text.insert("insert", "    ")
                    return "break"

                # Jedi autocomplete
                if not self.jedi:
                    print("jedi not installed, cancel autocompletion ...")
                    return "break"
                script = self.jedi.Script(code=code, path="script.py")
                completions = script.complete(line, column)
                completions = [
                    x.name for x in completions
                    if not x.name.startswith("__") and x.name.startswith(prefix)
                ]

            if not completions:
                return "break"

            completions.sort(key=lambda x: x.lower())

            if len(completions) == 1:
                return self.insert_completion(completions[0], text=text)

            menu = tk.Menu(self, tearoff=0)
            self.active_menu = menu
            for comp in completions:
                menu.add_command(
                    label=comp,
                    command=lambda complete_name=comp, m=menu: self.insert_completion(complete_name, m))

            bbox = text.bbox("insert")
            if not bbox:
                return "break"
            x, y, _, _ = bbox
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

    def colorify(self):
        # Cancel any pending reschedules
        if self._colorify_after_id:
            self.after_cancel(self._colorify_after_id)
            self._colorify_after_id = None

        text = self.get_active_text()
        if not text or getattr(text, 'disable_colorify', False):
            return

        code = text.get("1.0", "end")
        # Clear old tags
        text.tag_remove("comment", "1.0", "end")
        text.tag_remove("keyword", "1.0", "end")
        text.tag_remove("string", "1.0", "end")
        text.tag_remove("builtin", "1.0", "end")

        # Determine visible area
        try:
            first_visible = text.index("@0,0")
            last_visible = text.index(f"@0,{text.winfo_height()}")
            start_line = int(first_visible.split('.')[0])
            end_line = int(last_visible.split('.')[0])
        except Exception:
            # Fallback to all lines
            start_line = 1
            end_line = int(text.index("end-1c").split('.')[0])

        # Highlight only visible lines
        for i in range(start_line, end_line + 1):
            line = text.get(f"{i}.0", f"{i}.end")
            stripped = line.lstrip()

            # Highlight comment
            if stripped.startswith("#"):
                start_index = f"{i}.0+{len(line) - len(stripped)}c"
                end_index = f"{i}.end"
                text.tag_add("comment", start_index, end_index)

            # Highlight KEYWORDS (skip content after #)
            comment_pos = line.find("#")
            scan_line = line if comment_pos == -1 else line[:comment_pos]

            for match in KEYWORD_PATTERN.finditer(scan_line):
                start_col = match.start()
                end_col = match.end()
                start_idx = f"{i}.{start_col}"
                end_idx = f"{i}.{end_col}"
                text.tag_add("keyword", start_idx, end_idx)

            for match in BUILTIN_PATTERN.finditer(scan_line):
                start_col = match.start()
                end_col = match.end()
                start_idx = f"{i}.{start_col}"
                end_idx = f"{i}.{end_col}"
                text.tag_add("builtin", start_idx, end_idx)

            for match in re.finditer(r'(\'(?:\\.|[^\\\'])*?\'|"(?:\\.|[^\\"])*?")', scan_line):
                start_col = match.start()
                end_col = match.end()
                start_idx = f"{i}.{start_col}"
                end_idx = f"{i}.{end_col}"
                text.tag_add("string", start_idx, end_idx)

            pattern = r"('''(?:\\.|[^\\])*?'''|\"\"\"(?:\\.|[^\\])*?\"\"\")"
            for match in re.finditer(pattern, code, re.DOTALL):
                start = match.start()
                end = match.end()
                start_index = text.index(f"1.0 + {start} chars")
                end_index = text.index(f"1.0 + {end} chars")
                text.tag_add("string", start_index, end_index)

    def after_colorify(self, delay=100):
        if self._colorify_after_id:
            self.after_cancel(self._colorify_after_id)
        self._colorify_after_id = self.after(delay, self.colorify)


# Monkey-patch tk.Text globally
tk.Text = PatchedText
