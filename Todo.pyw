import calendar
import os
import sqlite3
import tkinter as tk
from datetime import date, datetime, time, timedelta
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk
from app_settings import DataLocation, set_startup, startup_enabled
from task_records import export_tasks, read_tasks

from windows_tray import (
    ICON_PATH, WindowsTray, place_window, reopen_running_app, set_app_id, window_bounds,
)


APP_NAME = "To-do list"
MINI_ICON = Path(__file__).with_name("zoro.png")
BACKGROUND = "#FFFFFF"
PAPER = "#FFFFFF"
INK = "#173937"
MUTED = "#59616B"
LINE = "#E5E8EC"
ACCENT = "#AD3D2E"
ACCENT_DARK = "#822C22"
ACCENT_PALE = "#FBE8E6"
ACCENT_HOVER = "#F5ECEB"
SURFACE = "#F3F5F7"
COMPLETE = "#356945"
COMPLETE_HOVER = "#285236"
FOCUS_RING = "#B36E65"
TRANSPARENT = "#FF00FE"
FONT = "Microsoft YaHei UI"
VIEWS = {-1: "当前", 0: "未完成", 1: "已完成"}


def label(parent, text, background, foreground=INK, size=9, bold=False, **options):
    return tk.Label(parent, text=text, bg=background, fg=foreground,
                    font=(FONT, size, "bold" if bold else "normal"), **options)


def button(parent, text, command, background, foreground, hover, **options):
    padding = options.pop("padx", 9)
    control = tk.Button(
        parent, text=text, command=command, bg=background, fg=foreground,
        activebackground=hover, activeforeground=foreground, relief="flat",
        borderwidth=0, highlightthickness=1, highlightbackground=background,
        highlightcolor=foreground, cursor="hand2", font=(FONT, 9),
        padx=padding, pady=4, **options
    )
    control.bind("<Enter>", lambda event: control.configure(bg=hover))
    control.bind("<Leave>", lambda event: control.configure(bg=background))
    control.bind("<Return>", lambda event: control.invoke())
    return control


def rounded_box(canvas, x0, y0, x1, y1, radius, **options):
    return canvas.create_polygon(
        x0 + radius, y0, x1 - radius, y0, x1, y0, x1, y0 + radius,
        x1, y1 - radius, x1, y1, x1 - radius, y1, x0 + radius, y1,
        x0, y1, x0, y1 - radius, x0, y0 + radius, x0, y0,
        smooth=True, splinesteps=16, **options
    )


class PillButton(tk.Canvas):
    def __init__(self, parent, caption, command, surface, fill, ink, hover,
                 *, height=28, padding=10, size=9, outline=""):
        super().__init__(parent, bg=surface, height=height, highlightthickness=0,
                         bd=0, takefocus=1, cursor="hand2")
        self.command = command
        self.height = height
        self.padding = padding
        self.outline = outline
        self.typeface = font.Font(root=self, family=FONT, size=size)
        self.hovered = False
        self.focused = False
        self.set_caption(caption, fill, ink, hover)

        self.bind("<Configure>", lambda event: self.paint())
        self.bind("<Enter>", lambda event: self.set_state("hovered", True))
        self.bind("<Leave>", lambda event: self.set_state("hovered", False))
        self.bind("<FocusIn>", lambda event: self.set_state("focused", True))
        self.bind("<FocusOut>", lambda event: self.set_state("focused", False))
        self.bind("<ButtonRelease-1>", self.click)
        self.bind("<Return>", lambda event: self.invoke())
        self.bind("<space>", lambda event: self.invoke())

    def set_caption(self, caption, fill, ink, hover):
        self.caption = caption
        self.fill = fill
        self.ink = ink
        self.hover = hover
        self.width = max(self.height, self.typeface.measure(caption) + 2 * self.padding)
        self.configure(width=self.width)
        self.paint()

    def set_state(self, state, value):
        setattr(self, state, value)
        self.paint()

    def paint(self):
        self.delete("all")
        width = self.winfo_width() if self.winfo_width() > 1 else self.width
        show_focus = self.focused and getattr(self._root(), "keyboard_focus_visible", False)
        rounded_box(self, 1, 1, width - 1, self.height - 1, self.height / 2 - 1,
                    fill=self.hover if self.hovered else self.fill,
                    outline=FOCUS_RING if show_focus else self.outline, width=1)
        self.create_text(width / 2, self.height / 2, text=self.caption,
                         font=self.typeface, fill=self.ink)

    def click(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.height:
            self.invoke()

    def invoke(self):
        self.command()


class RoundedStrip(tk.Canvas):
    def __init__(self, parent, height, fill):
        super().__init__(parent, bg=BACKGROUND, height=height, highlightthickness=0)
        self.fill = fill
        self.line = ""
        self.content = tk.Frame(self, bg=fill)
        self.slot = self.create_window(5, height / 2, window=self.content, anchor="w")
        self.bind("<Configure>", lambda event: self.paint())

    def outline(self, color):
        self.line = color
        self.paint()

    def paint(self):
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 10 or height <= 4:
            return
        self.delete("surface")
        fill = rounded_box(self, 1, 1, width - 1, height - 1, 11,
                           fill=self.fill, outline=self.line, width=1, tags="surface")
        self.tag_lower(fill)
        self.coords(self.slot, 5, height / 2)
        self.itemconfigure(self.slot, width=width - 10)


class ListScrollbar(tk.Canvas):
    def __init__(self, parent, target, *, background=BACKGROUND):
        super().__init__(parent, width=12, height=1, bg=background,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.target = target
        self.first, self.last = 0.0, 1.0
        self.thumb_offset = None
        self.hovered = False
        self.bind("<Configure>", lambda event: self.paint())
        self.bind("<Enter>", lambda event: self.set_hover(True))
        self.bind("<Leave>", lambda event: self.set_hover(False))
        self.bind("<ButtonPress-1>", self.press)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        if self.first == 0.0 and self.last == 1.0:
            self.thumb_offset = None
            self.hovered = False
            self.grid_remove()
            return
        if not self.winfo_manager():
            self.grid()
        self.paint()

    def thumb_bounds(self):
        track = max(0, self.winfo_height() - 8)
        fraction = self.last - self.first
        length = min(track, max(24, track * fraction))
        travel = track - length
        position = self.first / (1 - fraction) if fraction < 1 else 0
        top = 4 + travel * position
        return top, top + length, travel, fraction

    def paint(self):
        self.delete("thumb")
        top, bottom, _, _ = self.thumb_bounds()
        if bottom - top < 4:
            return
        center = self.winfo_width() / 2
        color = "#9CA8B4" if self.hovered or self.thumb_offset is not None else "#C6CFD9"
        rounded_box(self, center - 2, top, center + 2, bottom, 2,
                    fill=color, outline="", tags="thumb")

    def set_hover(self, hovered):
        self.hovered = hovered
        self.paint()

    def press(self, event):
        top, bottom, _, _ = self.thumb_bounds()
        if top <= event.y <= bottom:
            self.thumb_offset = event.y - top
            self.paint()
        else:
            self.target.yview_scroll(-1 if event.y < top else 1, "pages")

    def drag(self, event):
        if self.thumb_offset is None:
            return
        _, _, travel, fraction = self.thumb_bounds()
        if travel > 0:
            relative = (event.y - self.thumb_offset - 4) / travel
            self.target.yview_moveto(max(0, min(1, relative)) * (1 - fraction))

    def release(self, event):
        self.thumb_offset = None
        self.paint()


class DialogPanel(tk.Toplevel):
    def __init__(self, parent, title, width):
        super().__init__(parent, bg=TRANSPARENT)
        self.withdraw()
        self.transient(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", bool(parent.attributes("-topmost")))
        self.attributes("-transparentcolor", TRANSPARENT)
        self.title(title)
        self.width = width
        self.parent_window = parent
        self.previous_grab = parent.grab_current()
        self.previous_focus = parent.focus_get()
        self.outline_canvas = tk.Canvas(self, bg=TRANSPARENT, highlightthickness=0)
        self.outline_canvas.pack(fill="both", expand=True)
        self.panel = tk.Frame(self.outline_canvas, bg=PAPER)
        self.outline_canvas.create_window(4, 4, anchor="nw", window=self.panel, width=width - 8)

        header = tk.Frame(self.panel, bg=PAPER)
        header.pack(fill="x", padx=14, pady=(9, 5))
        label(header, title, PAPER, size=12, bold=True).pack(side="left", padx=(3, 0))
        PillButton(header, "×", self.close, PAPER, PAPER, MUTED, SURFACE,
                   height=28, padding=4, size=13).pack(side="right")

        self.body = tk.Frame(self.panel, bg=PAPER, padx=17, pady=8)
        self.body.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda event: self.close())

    def make_footer(self, primary_label, action, *, cancel=True):
        tk.Frame(self.panel, bg=LINE, height=1).pack(fill="x", padx=9)
        footer = tk.Frame(self.panel, bg=PAPER)
        footer.pack(fill="x", padx=17, pady=(10, 10))
        PillButton(footer, primary_label, action, PAPER, ACCENT, PAPER, ACCENT_DARK,
                   height=31, padding=15).pack(side="right")
        if cancel:
            PillButton(footer, "取消", self.close, PAPER, PAPER, INK, SURFACE,
                       height=31, padding=11, outline=LINE).pack(side="right", padx=(0, 6))
        return footer

    def show(self, focus=None):
        self.update_idletasks()
        height = self.panel.winfo_reqheight() + 8
        self.geometry(f"{self.width}x{height}")
        outline = rounded_box(self.outline_canvas, 1, 1, self.width - 1, height - 1,
                              14, fill=PAPER, outline="#C9D1DA", width=1)
        self.outline_canvas.tag_lower(outline)
        self.deiconify()
        self.wait_visibility()
        origin = window_bounds(self.parent_window)
        x = origin.left + (origin.right - origin.left - self.width) // 2
        y = origin.top + max(24, (origin.bottom - origin.top - height) // 2)
        place_window(self, x, y)
        self.grab_set()
        (focus or self).focus_force()

    def close(self):
        self.destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()
        if self.previous_focus is not None and self.previous_focus.winfo_exists():
            self.previous_focus.focus_force()


def form_field(form, title, height):
    label(form, title, PAPER, INK, size=9, bold=True).pack(anchor="w", pady=(0, 4))
    field = RoundedStrip(form, height, PAPER)
    field.outline(LINE)
    field.pack(fill="x", pady=(0, 11))
    return field


def focus_outline(field, control):
    control.bind("<FocusIn>", lambda event: field.outline("#B96359"), add="+")
    control.bind("<FocusOut>", lambda event: field.outline(LINE), add="+")


class DatePicker(DialogPanel):
    def __init__(self, parent, selected, on_pick, *, date_prompt=None):
        super().__init__(parent, date_prompt or "设置截止时间", width=326)
        self.on_pick = on_pick
        self.today = date.today()
        timed = isinstance(selected, datetime)
        self.selected = selected.date() if timed else selected or self.today
        self.month = self.selected.replace(day=1)

        quick = tk.Frame(self.body, bg=PAPER)
        quick.pack(fill="x", pady=(0, 9))
        self.selected_label = label(quick, "", PAPER, ACCENT_DARK, size=9, bold=True)
        self.selected_label.pack(side="left")
        for text, value in (("明天", self.today + timedelta(days=1)), ("今天", self.today)):
            PillButton(quick, text, lambda picked=value: self.select_day(picked),
                       PAPER, SURFACE, ACCENT_DARK, ACCENT_HOVER,
                       height=25, padding=8, size=8).pack(side="right", padx=(5, 0))

        heading = tk.Frame(self.body, bg=PAPER)
        heading.pack(fill="x", pady=(0, 4))
        PillButton(heading, "‹", lambda: self.shift(-1), PAPER, SURFACE,
                   INK, ACCENT_HOVER, height=27, padding=5, size=12).pack(side="left")
        PillButton(heading, "›", lambda: self.shift(1), PAPER, SURFACE,
                   INK, ACCENT_HOVER, height=27, padding=5, size=12).pack(side="right")
        self.month_label = label(heading, "", PAPER, INK, size=10, bold=True)
        self.month_label.pack(fill="x", expand=True, pady=4)

        self.days = tk.Frame(self.body, bg=PAPER)
        self.days.pack(fill="x")
        for column in range(7):
            self.days.grid_columnconfigure(column, weight=1, uniform="day")
        for row in range(1, 7):
            self.days.grid_rowconfigure(row, minsize=29)

        if date_prompt:
            self.make_footer("确定", lambda: self.choose(self.selected))
        else:
            self.make_time_controls(selected, timed)
            footer = self.make_footer("确定", self.confirm)
            PillButton(footer, "清除截止时间", lambda: self.choose(None), PAPER, PAPER,
                       MUTED, SURFACE, height=31, padding=5, size=8).pack(side="left")
        self.draw_month()
        self.show()

    def make_time_controls(self, selected, timed):
        self.use_time = timed
        self.hour = tk.StringVar(self, value=selected.strftime("%H") if timed else "09")
        self.minute = tk.StringVar(self, value=selected.strftime("%M") if timed else "00")
        tk.Frame(self.body, bg=LINE, height=1).pack(fill="x", pady=(8, 9))
        time_row = tk.Frame(self.body, bg=PAPER)
        time_row.pack(fill="x")
        self.date_only = PillButton(
            time_row, "仅日期", lambda: self.set_time_mode(False), PAPER, PAPER,
            MUTED, SURFACE, height=26, padding=8, size=8
        )
        self.date_only.pack(side="left")
        self.with_time = PillButton(
            time_row, "指定时间", lambda: self.set_time_mode(True), PAPER, PAPER,
            MUTED, SURFACE, height=26, padding=8, size=8
        )
        self.with_time.pack(side="left", padx=(3, 0))

        clock_field = RoundedStrip(time_row, 28, SURFACE)
        clock_field.configure(width=101)
        clock_field.pack(side="right")
        clock = clock_field.content
        style = ttk.Style(self)
        style.configure("Deadline.TSpinbox", arrowsize=9, padding=2, bordercolor=SURFACE,
                        background=SURFACE, arrowcolor=MUTED, lightcolor=SURFACE,
                        darkcolor=SURFACE, fieldbackground=SURFACE, foreground=INK)
        style.map("Deadline.TSpinbox", fieldbackground=[("disabled", SURFACE)],
                  foreground=[("disabled", MUTED)])
        self.hour_box = ttk.Spinbox(clock, from_=0, to=23, width=3, justify="center",
                                    style="Deadline.TSpinbox", format="%02.0f",
                                    textvariable=self.hour, wrap=True)
        self.hour_box.pack(side="left")
        label(clock, ":", SURFACE, MUTED).pack(side="left", padx=3)
        self.minute_box = ttk.Spinbox(clock, from_=0, to=59, width=3, justify="center",
                                      style="Deadline.TSpinbox", format="%02.0f",
                                      textvariable=self.minute, wrap=True)
        self.minute_box.pack(side="left")

        self.time_hint = label(self.body, "", PAPER, MUTED, size=8, anchor="w")
        self.time_hint.pack(fill="x", pady=(3, 0))
        self.set_time_mode(timed)
        self.hour_box.bind("<Return>", lambda event: self.confirm())
        self.minute_box.bind("<Return>", lambda event: self.confirm())

    def shift(self, offset):
        month_index = self.month.year * 12 + self.month.month - 1 + offset
        year, month = divmod(month_index, 12)
        if 1 <= year <= 9999:
            self.month = date(year, month + 1, 1)
            self.draw_month()

    def draw_month(self, focus_selected=False):
        year, month = self.month.year, self.month.month
        self.month_label.configure(text=f"{year} 年 {month} 月")
        self.selected_label.configure(text=self.selected.isoformat())
        for widget in self.days.winfo_children():
            widget.destroy()
        for column, weekday in enumerate("一二三四五六日"):
            label(self.days, weekday, PAPER, MUTED, size=8).grid(row=0, column=column, pady=(2, 4))
        for week, numbers in enumerate(calendar.monthcalendar(year, month), start=1):
            for column, day in enumerate(numbers):
                if not day:
                    continue
                value = date(year, month, day)
                selected = value == self.selected
                control = PillButton(
                    self.days, str(day), lambda picked=value: self.select_day(picked),
                    PAPER, ACCENT if selected else PAPER,
                    PAPER if selected else ACCENT_DARK if value == self.today else INK,
                    ACCENT_DARK if selected else ACCENT_PALE, height=27, padding=5,
                    outline=LINE if value == self.today and not selected else "",
                )
                control.grid(row=week, column=column)
                if selected and focus_selected:
                    control.focus_set()

    def select_day(self, value):
        self.selected = value
        self.month = value.replace(day=1)
        self.draw_month(focus_selected=True)

    def set_time_mode(self, enabled):
        self.use_time = enabled
        for control, caption, selected in (
            (self.date_only, "仅日期", not enabled), (self.with_time, "指定时间", enabled)
        ):
            control.set_caption(caption, ACCENT_PALE if selected else PAPER,
                                ACCENT_DARK if selected else MUTED, SURFACE)
        state = "normal" if enabled else "disabled"
        self.hour_box.configure(state=state)
        self.minute_box.configure(state=state)
        hint = "24 小时制" if enabled else "截止到所选日期结束"
        self.time_hint.configure(text=hint, fg=MUTED)

    def confirm(self):
        if not self.use_time:
            self.choose(self.selected)
            return
        try:
            at = time(int(self.hour.get()), int(self.minute.get()))
        except ValueError:
            self.time_hint.configure(text="请输入有效的 24 小时时间", fg="#A33346")
            return
        self.choose(datetime.combine(self.selected, at))

    def choose(self, value):
        self.on_pick(value)
        self.close()



def date_caption(value):
    if value is None:
        return "截止时间"
    if isinstance(value, datetime):
        prefix = f"{value.year}/" if value.year != date.today().year else ""
        return f"{prefix}{value.month}/{value.day} {value:%H:%M}"
    return value.isoformat()


def deadline_summary(value):
    stored = deadline_text(value)
    return stored.replace("T", " ") if stored else "请选择日期和时间"


def read_deadline(value):
    if value is None:
        return None
    if "T" in value:
        return datetime.fromisoformat(value)
    return date.fromisoformat(value)


def deadline_text(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    return value.isoformat() if value else None



def completion_text(done, completed_at, completed_on):
    if not done:
        return "未完成"
    if completed_at:
        return completed_at
    return f"{completed_on}（具体时间未记录）" if completed_on else "未记录"


def prepare_database(db):
    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
            "done INTEGER NOT NULL DEFAULT 0, deadline TEXT, sort_order INTEGER, "
            "completed_on TEXT, note TEXT NOT NULL DEFAULT '', created_at TEXT, completed_at TEXT)"
        )
        columns = {column[1] for column in db.execute("PRAGMA table_info(tasks)")}
        if "deadline" not in columns:
            db.execute("ALTER TABLE tasks ADD COLUMN deadline TEXT")
        if "sort_order" not in columns:
            db.execute("ALTER TABLE tasks ADD COLUMN sort_order INTEGER")
        if "completed_on" not in columns:
            db.execute("ALTER TABLE tasks ADD COLUMN completed_on TEXT")
        if "note" not in columns:
            db.execute("ALTER TABLE tasks ADD COLUMN note TEXT NOT NULL DEFAULT ''")
        for timestamp in ("created_at", "completed_at"):
            if timestamp not in columns:
                db.execute(f"ALTER TABLE tasks ADD COLUMN {timestamp} TEXT")
        db.execute("UPDATE tasks SET sort_order = -id WHERE sort_order IS NULL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS window_settings (id INTEGER PRIMARY KEY CHECK (id = 1), "
            "x INTEGER, y INTEGER, topmost INTEGER NOT NULL DEFAULT 1)"
        )
        db.execute("INSERT OR IGNORE INTO window_settings (id) VALUES (1)")


class CompletionRange(tk.Frame):
    def __init__(self, parent, all_label, *, on_change=None):
        super().__init__(parent, bg=PAPER)
        self.on_change = on_change
        self.selected_scope = 0
        self.scope_buttons = []
        if on_change is None:
            self.scope = ttk.Combobox(
                self, state="readonly", font=(FONT, 9),
                values=(all_label, "今天完成", "最近 7 天完成", "自定义完成日期"),
            )
            self.scope.current(0)
            self.scope.pack(fill="x")
            self.scope.bind("<<ComboboxSelected>>",
                            lambda event: self.select_scope(self.scope.current()))
        else:
            scopes = RoundedStrip(self, 33, SURFACE)
            scopes.pack(fill="x")
            for index, title in enumerate((all_label, "今天", "近 7 天", "自定义")):
                scopes.content.grid_columnconfigure(index, weight=1, uniform="scope")
                button = PillButton(scopes.content, title, lambda value=index: self.select_scope(value),
                                    SURFACE, SURFACE, MUTED, ACCENT_PALE, height=26, size=8)
                button.grid(row=0, column=index, sticky="ew", padx=2)
                self.scope_buttons.append(button)

        self.date_fields = tk.Frame(self, bg=PAPER)
        self.date_fields.grid_columnconfigure((0, 1), weight=1, uniform="date")
        self.dates = [date.today(), date.today()]
        self.date_buttons = []
        for column, title in enumerate(("开始日期", "结束日期")):
            command = lambda index=column, name=title: self.pick_date(index, name)
            right_padding = 6 if column == 0 else 0
            if self.on_change is None:
                label(self.date_fields, title, PAPER, MUTED, size=8).grid(
                    row=0, column=column, sticky="w", pady=(6, 2)
                )
                field = ttk.Button(self.date_fields, text=self.date_caption(column), command=command)
                field.grid(row=1, column=column, sticky="ew", padx=(0, right_padding))
            else:
                field = PillButton(self.date_fields, self.date_caption(column), command, PAPER,
                                   SURFACE, INK, ACCENT_HOVER, height=27, size=8)
                field.grid(row=0, column=column, sticky="ew", padx=(0, right_padding), pady=(5, 0))
            self.date_buttons.append(field)
        self.update_fields()

    def select_scope(self, scope):
        self.selected_scope = scope
        self.update_fields()
        if self.on_change is not None:
            self.on_change()

    def date_caption(self, index):
        prefix = ("开始", "结束")[index] + "  " if self.on_change is not None else ""
        return f"{prefix}{self.dates[index].isoformat()}  ▾"

    def pick_date(self, index, title):
        def apply(value):
            self.dates[index] = value
            field = self.date_buttons[index]
            caption = self.date_caption(index)
            if self.on_change is None:
                field.configure(text=caption)
            else:
                field.set_caption(caption, SURFACE, INK, ACCENT_HOVER)
                self.on_change()

        DatePicker(self.winfo_toplevel(), self.dates[index], apply, date_prompt=f"选择{title}")

    def update_fields(self):
        custom = self.selected_scope == 3
        if self.on_change is None:
            self.date_fields.pack(fill="x")
            for field in self.date_buttons:
                field.state(["!disabled" if custom else "disabled"])
            return

        for index, button in enumerate(self.scope_buttons):
            active = index == self.selected_scope
            button.set_caption(button.caption, PAPER if active else SURFACE,
                               ACCENT_DARK if active else MUTED, ACCENT_PALE)
        if custom:
            self.date_fields.pack(fill="x")
        else:
            self.date_fields.pack_forget()

    def read(self):
        scope = self.scope.current() if self.on_change is None else self.selected_scope
        if scope == 0:
            return None
        today = date.today()
        if scope in (1, 2):
            start = today - timedelta(days=6) if scope == 2 else today
            return start.isoformat(), today.isoformat()
        start, end = (value.isoformat() for value in self.dates)
        if start > end:
            raise ValueError("开始日期应早于或等于结束日期。")
        return start, end


class TodoApp:
    def __init__(self, root, db):
        self.root = root
        root.keyboard_focus_visible = False
        self.db = db
        self.data_location = None
        self.settings_dialog = None
        prepare_database(db)
        root.title(APP_NAME)
        root.iconbitmap(default=str(ICON_PATH))
        root.iconbitmap(str(ICON_PATH))
        root.geometry("360x450")
        root.minsize(320, 260)
        root.configure(bg=BACKGROUND)
        x, y, topmost = db.execute("SELECT x, y, topmost FROM window_settings WHERE id = 1").fetchone()
        self.topmost = bool(topmost)
        root.attributes("-topmost", self.topmost)
        self.position = (x, y) if x is not None and y is not None else None
        self.saved_position = self.position
        self.position_job = None
        self.undo_timer = self.undo_action = None

        self.filter = -1
        self.history_mode = False
        self.history_dates = None
        self.history_query = ""
        self.nav_buttons = {}
        self.task_checks = {}
        self.task_titles = []
        self.note_font = font.Font(root=root, family=FONT, size=8)
        self.timed_deadline_labels = []
        self.task_rows = {}
        self.task_handles = {}
        self.deadline = None
        self.today = date.today()
        self.drag_task = self.drop_target = self.drag_job = None
        self.mini = None
        self.make_main()
        self.refresh()
        self.update_today()
        root.bind("<Control-n>", lambda event: self.entry.focus_set())
        root.bind_all("<KeyPress-Tab>", lambda event: self.set_focus_visibility(True), add="+")
        root.bind_all("<ButtonPress>", lambda event: self.set_focus_visibility(False), add="+")

    def set_focus_visibility(self, visible):
        self.root.keyboard_focus_visible = visible
        self.update_focus_drawing(self.root.focus_get())

    def restore_task_focus(self, control):
        if self.history_mode and not control.winfo_viewable():
            control = self.history_keyword
        target = control if self.root.keyboard_focus_visible else self.root
        target.focus_set()

    def update_focus_drawing(self, control):
        if isinstance(control, PillButton):
            control.paint()
        elif getattr(control, "task_focus_label", False):
            control.configure(highlightcolor=FOCUS_RING if self.root.keyboard_focus_visible else PAPER)

    def show_startup(self):
        self.root.deiconify()
        self.root.update_idletasks()
        if self.position is not None:
            place_window(self.root, *self.position)
        self.root.bind("<Configure>", self.schedule_position_save, add="+")

    def schedule_position_save(self, event):
        if event.widget != self.root or self.root.state() != "normal":
            return
        if self.position_job is not None:
            self.root.after_cancel(self.position_job)
        self.position_job = self.root.after(250, self.capture_position)

    def capture_position(self):
        self.position_job = None
        if self.root.state() == "normal":
            rect = window_bounds(self.root)
            self.remember_position(rect.left, rect.top)

    def remember_position(self, x, y):
        self.position = (x, y)
        if self.position == self.saved_position:
            return
        try:
            with self.db:
                self.db.execute("UPDATE window_settings SET x = ?, y = ? WHERE id = 1", (x, y))
        except sqlite3.Error:
            return
        self.saved_position = self.position

    def toggle_topmost(self):
        value = not self.topmost
        try:
            with self.db:
                self.db.execute("UPDATE window_settings SET topmost = ? WHERE id = 1", (value,))
        except sqlite3.Error as error:
            messagebox.showerror("保存失败", str(error), parent=self.root)
            return
        self.topmost = value
        self.root.attributes("-topmost", value)

    def quit_app(self):
        self.capture_position()
        self.root.destroy()

    def collapse(self):
        rect = window_bounds(self.root)
        button = self.collapse_button
        photo = tk.PhotoImage(master=self.root, file=str(MINI_ICON))
        width, height = photo.width(), photo.height()
        x = button.winfo_rootx() + (button.winfo_width() - width) // 2
        y = button.winfo_rooty() + (button.winfo_height() - height) // 2
        self.remember_position(rect.left, rect.top)
        self.mini_offset = (x - rect.left, y - rect.top)
        self.root.withdraw()

        self.mini = tk.Toplevel(self.root, bg=TRANSPARENT)
        self.mini.withdraw()
        self.mini.overrideredirect(True)
        self.mini.attributes("-topmost", True)
        self.mini.attributes("-transparentcolor", TRANSPARENT)
        self.mini.geometry(f"{width}x{height}")
        icon = tk.Canvas(self.mini, bg=TRANSPARENT, highlightthickness=0, cursor="hand2")
        icon.pack(fill="both", expand=True)
        icon.photo = photo
        icon.create_image(0, 0, image=photo, anchor="nw")
        icon.bind("<ButtonPress-1>", self.begin_drag)
        icon.bind("<B1-Motion>", self.drag)
        icon.bind("<ButtonRelease-1>", self.end_drag)
        self.mini.deiconify()
        self.mini.update_idletasks()
        place_window(self.mini, x, y)

    def begin_drag(self, event):
        rect = window_bounds(self.mini)
        self.drag_origin = (event.x_root, event.y_root, rect.left, rect.top)
        self.dragging = False

    def drag(self, event):
        start_x, start_y, left, top = self.drag_origin
        dx, dy = event.x_root - start_x, event.y_root - start_y
        if self.dragging or abs(dx) + abs(dy) >= 5:
            self.dragging = True
            place_window(self.mini, left + dx, top + dy)

    def end_drag(self, event):
        if not self.dragging:
            self.reopen()
            return
        rect = window_bounds(self.mini)
        offset_x, offset_y = self.mini_offset
        self.remember_position(rect.left - offset_x, rect.top - offset_y)

    def reopen(self):
        self.tray.hide()
        if self.mini is not None:
            self.mini.destroy()
            self.mini = None
        was_hidden = self.root.state() == "withdrawn"
        self.root.deiconify()
        self.root.update_idletasks()
        if was_hidden and self.position is not None:
            place_window(self.root, *self.position)
        self.root.lift()
        self.root.focus_force()

    def hide_to_tray(self):
        if not self.tray.show():
            messagebox.showerror("无法隐藏", "Windows 通知区域暂时不可用。", parent=self.root)
            return
        rect = window_bounds(self.root)
        self.remember_position(rect.left, rect.top)
        self.root.withdraw()

    def show_settings(self):
        if self.settings_dialog is not None and self.settings_dialog.winfo_exists():
            self.settings_dialog.lift()
            return
        dialog = DialogPanel(self.root, "设置", width=366)
        self.settings_dialog = dialog
        form = dialog.body

        label(form, "开机自启", PAPER, size=10, bold=True).pack(anchor="w")
        label(form, "登录 Windows 后自动打开待办面板", PAPER, MUTED, size=8).pack(
            anchor="w", pady=(3, 7)
        )
        error = tk.StringVar(dialog)

        def update_startup():
            enabled = startup_enabled()
            auto.set_caption("已开启 · 点击关闭" if enabled else "已关闭 · 点击开启",
                             ACCENT_PALE if enabled else SURFACE,
                             ACCENT_DARK if enabled else MUTED, ACCENT_HOVER)

        def toggle_startup():
            try:
                set_startup(not startup_enabled())
                update_startup()
                error.set("")
            except OSError as failure:
                error.set(f"无法更改开机自启\n{failure}")

        auto = PillButton(form, "", toggle_startup, PAPER, SURFACE, MUTED, ACCENT_HOVER)
        auto.pack(anchor="w", pady=(0, 18))
        try:
            update_startup()
        except OSError as failure:
            auto.set_caption("重新尝试", SURFACE, MUTED, ACCENT_HOVER)
            error.set(f"无法读取开机自启状态\n{failure}")

        label(form, "事项保存位置", PAPER, size=10, bold=True).pack(anchor="w")
        path = tk.Text(form, height=3, width=32, bg=SURFACE, fg=INK, relief="flat",
                       font=(FONT, 9), wrap="char", padx=7, pady=6,
                       highlightthickness=0)
        path.pack(fill="x", pady=(6, 7))

        def update_path():
            path.configure(state="normal")
            path.delete("1.0", "end")
            path.insert("1.0", str(self.data_location.path))
            path.configure(state="disabled")

        update_path()

        def open_folder():
            try:
                os.startfile(self.data_location.path.parent)
            except OSError as failure:
                error.set(str(failure))

        def choose_folder():
            folder = filedialog.askdirectory(
                title="选择事项保存文件夹", parent=dialog,
                initialdir=self.data_location.path.parent,
            )
            if not folder:
                return
            try:
                target = Path(folder).resolve() / "tasks.sqlite3"
                if target == self.data_location.path:
                    return
                if target.exists():
                    raise FileExistsError("该文件夹已有 tasks.sqlite3，请选择另一个文件夹。")
                self.capture_position()
                previous = self.db
                copied = self.data_location.relocate(previous, folder)
                self.db = copied
                previous.close()
                self.refresh()
                update_path()
                error.set("已切换保存位置，原文件保留为迁移前备份。")
            except (OSError, sqlite3.Error) as failure:
                error.set(f"保存位置更改失败\n{failure}")

        actions = tk.Frame(form, bg=PAPER)
        actions.pack(fill="x")
        PillButton(actions, "打开文件夹", open_folder, PAPER, SURFACE,
                   MUTED, ACCENT_HOVER).pack(side="left")
        PillButton(actions, "更改位置", choose_folder, PAPER, SURFACE,
                   MUTED, ACCENT_HOVER).pack(side="left", padx=(7, 0))
        tk.Label(form, textvariable=error, bg=PAPER, fg=MUTED, font=(FONT, 8),
                 wraplength=316, anchor="w", justify="left").pack(fill="x", pady=(9, 0))
        footer = dialog.make_footer("完成", dialog.close)
        PillButton(footer, "导出事项", lambda: self.show_export(dialog), PAPER, SURFACE,
                   ACCENT_DARK, ACCENT_HOVER, height=31).pack(side="left")
        dialog.show()

    def show_history(self):
        self.history_mode = True
        self.date_line.pack_forget()
        self.history_heading.pack(side="left")
        self.composer.grid_remove()
        self.filters.grid_remove()
        self.history_link.grid_remove()
        self.history_panel.grid()
        self.refresh()
        self.canvas.yview_moveto(0)
        self.restore_task_focus(self.history_back)

    def close_history(self):
        self.history_mode = False
        self.history_panel.grid_remove()
        self.history_heading.pack_forget()
        self.date_line.pack(side="left")
        self.composer.grid()
        self.filters.grid()
        self.set_filter(1)
        self.restore_task_focus(self.nav_buttons[1])

    def search_history(self):
        try:
            date_range = self.history_range.read()
        except ValueError as error:
            self.history_status.configure(text=str(error), fg=ACCENT_DARK)
            return
        self.history_dates = date_range
        self.history_query = self.history_keyword.get()
        self.refresh()
        self.canvas.yview_moveto(0)

    def show_export(self, parent):
        dialog = DialogPanel(parent, "导出事项", width=366)
        date_range = CompletionRange(dialog.body, "全部事项")
        date_range.pack(fill="x")
        label(dialog.body, "按日期导出时，仅包含该日期范围内完成的事项。",
              PAPER, MUTED, size=8, wraplength=306, justify="left").pack(anchor="w", pady=(8, 0))

        def save():
            try:
                rows = read_tasks(self.db, date_range.read())
            except (ValueError, sqlite3.Error) as error:
                messagebox.showerror("无法导出事项", str(error), parent=dialog)
                return
            if not rows:
                messagebox.showinfo("没有可导出的事项", "请选择包含事项的范围。", parent=dialog)
                return
            path = filedialog.asksaveasfilename(
                parent=dialog, title="保存事项表格", defaultextension=".csv",
                initialfile=f"待办事项-{date.today().isoformat()}.csv",
                filetypes=[("CSV 表格", "*.csv")],
            )
            if not path:
                return
            if Path(path).suffix.lower() != ".csv":
                messagebox.showerror("无法导出事项", "请使用 .csv 文件名。", parent=dialog)
                return
            try:
                export_tasks(path, rows)
            except OSError as error:
                messagebox.showerror("无法导出事项", str(error), parent=dialog)
                return
            messagebox.showinfo("导出完成", f"已导出 {len(rows)} 条事项。\n{path}", parent=dialog)
            dialog.close()

        dialog.make_footer("导出 CSV", save)
        dialog.show(date_range.scope)

    def make_main(self):
        main = tk.Frame(self.root, bg=BACKGROUND)
        main.pack(fill="both", expand=True, padx=15, pady=(12, 11))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)

        header = tk.Frame(main, bg=BACKGROUND)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 13))
        date_line = self.date_line = tk.Frame(header, bg=BACKGROUND)
        date_line.pack(side="left")
        self.today_label = label(date_line, "", BACKGROUND, INK, size=12, bold=True)
        self.today_label.pack(side="left", anchor="s")
        self.weekday_label = label(date_line, "", BACKGROUND, MUTED, size=8)
        self.weekday_label.pack(side="left", anchor="s", padx=(5, 0), pady=(0, 1))
        self.collapse_button = PillButton(header, "收起", self.collapse, BACKGROUND,
                                          BACKGROUND, MUTED, ACCENT_HOVER, height=26, size=8)
        self.collapse_button.pack(side="right")
        PillButton(header, "⚙", self.show_settings, BACKGROUND, BACKGROUND,
                   MUTED, ACCENT_HOVER, height=26, padding=3, size=11).pack(side="right")

        self.history_heading = tk.Frame(header, bg=BACKGROUND)
        self.history_back = PillButton(self.history_heading, "‹ 返回", self.close_history, PAPER,
                                       SURFACE, MUTED, ACCENT_HOVER, height=26, size=8)
        self.history_back.pack(side="left", padx=(0, 7))
        label(self.history_heading, "完成历史", PAPER, size=11, bold=True).pack(side="left")

        filters = self.filters = RoundedStrip(main, 34, SURFACE)
        filters.grid(row=2, column=0, sticky="ew", pady=(0, 9))
        for column, (status, title) in enumerate(VIEWS.items()):
            filters.content.grid_columnconfigure(column, weight=1, uniform="filter")
            control = PillButton(filters.content, title, lambda value=status: self.set_filter(value),
                                 SURFACE, SURFACE, MUTED, ACCENT_HOVER, height=26)
            control.grid(row=0, column=column, sticky="ew", padx=2)
            self.nav_buttons[status] = control

        self.composer = RoundedStrip(main, 43, SURFACE)
        self.composer.grid(row=1, column=0, sticky="ew", pady=(0, 11))
        composer = self.composer.content
        composer.grid_columnconfigure(0, weight=1)
        self.entry_value = tk.StringVar()
        self.entry = tk.Entry(composer, textvariable=self.entry_value, bg=SURFACE, fg=INK,
                              insertbackground=INK, relief="flat", font=(FONT, 9),
                              highlightthickness=0)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(7, 3), ipady=4)
        self.entry.bind("<Return>", lambda event: self.add())
        self.entry.bind("<FocusIn>", lambda event: self.update_composer())
        self.entry.bind("<FocusOut>", lambda event: self.update_composer())
        self.entry_value.trace_add("write", lambda *_: self.update_composer())
        self.placeholder = label(composer, "输入新任务…", SURFACE, MUTED, size=9, anchor="w")
        self.placeholder.grid(row=0, column=0, sticky="ew", padx=(7, 3))
        self.placeholder.bind("<Button-1>", lambda event: self.entry.focus_set())
        self.deadline_button = PillButton(
            composer, date_caption(None), self.pick_deadline, SURFACE, SURFACE, MUTED, ACCENT_HOVER,
            height=26, padding=7, size=8
        )
        self.deadline_button.grid(row=0, column=1, padx=(0, 4))
        PillButton(composer, "添加", self.add, SURFACE, ACCENT, PAPER, ACCENT_DARK,
                   height=29, padding=12).grid(row=0, column=2)


        self.history_panel = tk.Frame(main, bg=PAPER)
        self.history_panel.grid(row=1, column=0, rowspan=2, sticky="ew", pady=(0, 8))
        search = RoundedStrip(self.history_panel, 38, SURFACE)
        search.pack(fill="x", pady=(0, 8))
        search.content.grid_columnconfigure(0, weight=1)
        keyword_value = tk.StringVar()
        self.history_keyword = tk.Entry(
            search.content, textvariable=keyword_value, bg=SURFACE, fg=INK,
            insertbackground=INK, relief="flat", highlightthickness=0, font=(FONT, 9),
        )
        self.history_keyword.grid(row=0, column=0, sticky="ew", padx=(7, 4), ipady=4)
        placeholder = label(search.content, "搜索事项或备注…", SURFACE, MUTED, size=8, anchor="w")
        placeholder.grid(row=0, column=0, sticky="ew", padx=(7, 4))
        placeholder.bind("<Button-1>", lambda event: self.history_keyword.focus_set())

        def update_search():
            focused = self.root.focus_get() == self.history_keyword
            search.outline(FOCUS_RING if focused else "")
            if keyword_value.get() or focused:
                placeholder.grid_remove()
            else:
                placeholder.grid()

        keyword_value.trace_add("write", lambda *_: update_search())
        self.history_keyword.bind("<FocusIn>", lambda event: update_search())
        self.history_keyword.bind("<FocusOut>", lambda event: update_search())
        self.history_keyword.bind("<Return>", lambda event: self.search_history())
        PillButton(search.content, "搜索", self.search_history, SURFACE, ACCENT,
                   PAPER, ACCENT_DARK, height=27).grid(row=0, column=1, padx=(0, 3))

        self.history_range = CompletionRange(self.history_panel, "全部", on_change=self.search_history)
        self.history_range.pack(fill="x")
        self.history_status = label(self.history_panel, "", PAPER, MUTED, size=8)
        self.history_status.pack(anchor="w", pady=(7, 0))
        self.history_panel.grid_remove()

        self.history_link = tk.Frame(main, bg=PAPER)
        self.history_link.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        label(self.history_link, "仅显示今天完成的事项", PAPER, MUTED, size=8).pack(side="left")
        PillButton(self.history_link, "查看历史", self.show_history, PAPER, SURFACE,
                   ACCENT_DARK, ACCENT_HOVER, height=24).pack(side="right")
        self.history_link.grid_remove()

        viewport = tk.Frame(main, bg=BACKGROUND)
        viewport.grid(row=4, column=0, sticky="nsew")
        viewport.grid_columnconfigure(0, weight=1)
        viewport.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(viewport, bg=BACKGROUND, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ttk.Style(self.root).theme_use("clam")
        self.scrollbar = ListScrollbar(viewport, self.canvas)
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(2, 0))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.tasks = tk.Frame(self.canvas, bg=BACKGROUND)
        self.task_window = self.canvas.create_window(0, 0, window=self.tasks, anchor="nw")
        self.canvas.bind("<Configure>", self.resize_list)
        self.tasks.bind("<Configure>", self.update_scroll_region)
        self.root.bind("<MouseWheel>", self.scroll_tasks)

        self.undo_bar = tk.Frame(main, bg=ACCENT_PALE, padx=8, pady=2)
        self.undo_bar.grid(row=5, column=0, sticky="ew", pady=(7, 0))
        self.undo_bar.grid_remove()
        self.undo_message = label(self.undo_bar, "", ACCENT_PALE, ACCENT_DARK)
        self.undo_message.pack(side="left")
        PillButton(self.undo_bar, "撤销", self.undo_last, ACCENT_PALE,
                   ACCENT_PALE, ACCENT_DARK, ACCENT_HOVER, height=24).pack(side="right")

    def update_today(self):
        previous = self.today
        now = datetime.now()
        self.today = now.date()
        weekday = "一二三四五六日"[self.today.weekday()]
        self.today_label.configure(
            text=f"{self.today.year}年{self.today.month}月{self.today.day}日"
        )
        self.weekday_label.configure(text=f"星期{weekday}")
        if previous != self.today:
            self.refresh()
        else:
            for badge, deadline in self.timed_deadline_labels:
                self.update_deadline_label(badge, deadline, False, now=now)
        wait = 60000 - (now.second * 1000 + now.microsecond // 1000)
        self.root.after(wait, self.update_today)

    def update_deadline_label(self, badge, deadline, done, now=None):
        now = now or datetime.now()
        today = now.date()
        timed = isinstance(deadline, datetime)
        day = deadline.date() if timed else deadline
        overdue = not done and (now >= deadline if timed else day < today)
        clock = f" {deadline:%H:%M}" if timed else ""
        if day == today and not done:
            text, color = f"今天{clock} 截止" if timed else "今天截止", ACCENT_DARK
        else:
            prefix = f"{day.year}年" if day.year != today.year else ""
            text, color = f"截止 {prefix}{day.month}月{day.day}日{clock}", MUTED
        if overdue:
            text, color = f"{text} · 已逾期", "#A33346"
        badge.configure(text=text, fg=color)


    def set_deadline(self, value):
        self.deadline = value
        self.deadline_button.set_caption(date_caption(value), ACCENT_PALE if value else SURFACE,
                                         ACCENT_DARK if value else MUTED, ACCENT_HOVER)

    def pick_deadline(self):
        DatePicker(self.root, self.deadline, self.set_deadline)

    def update_composer(self):
        focused = self.root.focus_get() == self.entry
        self.composer.outline("#C77970" if focused else "")
        if self.entry_value.get() or focused:
            self.placeholder.grid_remove()
        else:
            self.placeholder.grid()

    def resize_list(self, event):
        self.canvas.itemconfigure(self.task_window, width=event.width)
        for title in self.task_titles:
            title.configure(wraplength=max(120, event.width - 80))

    def update_scroll_region(self, event):
        self.canvas.configure(scrollregion=(0, 0, event.width, event.height))

    def scroll_tasks(self, event):
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget in (self.canvas, self.scrollbar):
                if self.canvas.yview() != (0.0, 1.0):
                    self.canvas.yview_scroll(-int(event.delta / 120), "units")
                return
            widget = widget.master

    def reveal_row(self, row):
        top = self.canvas.canvasy(0)
        bottom = top + self.canvas.winfo_height()
        y = row.winfo_y()
        height = row.winfo_height()
        if y < top:
            self.canvas.yview_moveto(y / self.tasks.winfo_height())
        elif y + height > bottom:
            self.canvas.yview_moveto((y + height - self.canvas.winfo_height())
                                     / self.tasks.winfo_height())

    def set_filter(self, status):
        self.filter = status
        if status == 1:
            self.history_link.grid()
        else:
            self.history_link.grid_remove()
        self.refresh()
        self.canvas.yview_moveto(0)

    def visible_tasks(self):
        if self.history_mode:
            results = read_tasks(self.db, self.history_dates, completed_only=True,
                                 keyword=self.history_query, include_times=True)
            self.history_status.configure(text=f"{len(results)} 条记录", fg=MUTED)
            return results
        rows = self.db.execute(
            "SELECT id, title, done, deadline, completed_on, "
            "substr(ltrim(note, char(9, 10, 13, 32)), 1, 256), created_at, completed_at FROM tasks "
            "ORDER BY done, sort_order, id DESC"
        ).fetchall()
        today = date.today().isoformat()
        pending = [row for row in rows if not row[2]]
        completed = [row for row in rows if row[2] and row[4] == today]
        current = pending + completed
        views = {-1: current, 0: pending, 1: completed}

        for status, control in self.nav_buttons.items():
            active = self.filter == status
            control.set_caption(f"{VIEWS[status]}  {len(views[status])}",
                                PAPER if active else SURFACE,
                                ACCENT_DARK if active else MUTED, ACCENT_PALE)

        return views[self.filter]

    def refresh(self):
        self.cancel_task_drag()
        rows = self.visible_tasks()
        for child in self.tasks.winfo_children():
            child.destroy()
        self.task_checks.clear()
        self.task_titles.clear()
        self.timed_deadline_labels.clear()
        self.task_rows.clear()
        self.task_handles.clear()
        previous_day = object()
        for task_id, title, done, deadline, completed_on, note, created_at, completed_at in rows:
            if self.history_mode and completed_on != previous_day:
                heading = completed_on or "完成日期未记录"
                if completed_on == self.today.isoformat():
                    heading = f"今天 · {completed_on}"
                label(self.tasks, heading, PAPER, MUTED, size=8, bold=True).pack(
                    fill="x", anchor="w", padx=4, pady=(7, 2)
                )
                previous_day = completed_on
            self.add_row(task_id, title, done, read_deadline(deadline), note,
                         completed_on, created_at, completed_at)
        if not self.task_checks:
            self.show_empty()

    def show_empty(self):
        headings = {-1: "当前没有任务", 0: "没有未完成的任务", 1: "今天还没有完成的事项"}
        text = "没有符合条件的完成记录" if self.history_mode else headings[self.filter]
        label(self.tasks, text, BACKGROUND, MUTED, size=9).pack(pady=(29, 0))

    def add_row(self, task_id, title, done, deadline, note, completed_on, created_at, completed_at):
        row = tk.Frame(self.tasks, bg=PAPER, highlightthickness=0)
        row.pack(fill="x")
        row.grid_columnconfigure(2, weight=1)
        row.divider = tk.Frame(row, height=1, bg=LINE)
        row.divider.grid(row=1, column=0, columnspan=3, sticky="ew")
        row.completed_on = completed_on
        self.task_rows[task_id] = (row, done)
        handle = label(row, "⠿", PAPER, "#707983", size=8, cursor="sb_v_double_arrow",
                       takefocus=1, highlightthickness=1, highlightbackground=PAPER,
                       highlightcolor=PAPER)
        handle.task_focus_label = True
        handle.grid(row=0, column=0, padx=(1, 0))
        handle.bind("<ButtonPress-1>", lambda event: self.begin_task_drag(event, task_id))
        handle.bind("<B1-Motion>", self.drag_task_motion)
        handle.bind("<ButtonRelease-1>", self.end_task_drag)
        handle.bind("<Up>", lambda event: self.move_task(task_id, -1))
        handle.bind("<Down>", lambda event: self.move_task(task_id, 1))
        self.task_handles[task_id] = handle

        check = PillButton(row, "✓" if done else "", lambda: self.toggle(task_id),
                           PAPER, COMPLETE if done else PAPER, PAPER if done else ACCENT_DARK,
                           COMPLETE_HOVER if done else ACCENT_PALE, height=20, padding=0,
                           outline="" if done else "#8793A0")
        check.grid(row=0, column=1, padx=(4, 9), pady=10)
        self.task_checks[task_id] = check

        details = tk.Frame(row, bg=PAPER)
        details.grid(row=0, column=2, sticky="ew", pady=8)
        title_color = MUTED if done and not self.history_mode else INK
        title_label = label(details, title, PAPER, title_color, size=9,
                            anchor="w", justify="left",
                            wraplength=max(120, self.canvas.winfo_width() - 80))
        if done and self.filter == -1 and not self.history_mode:
            completed_font = font.Font(root=self.root, font=title_label.cget("font"))
            completed_font.configure(overstrike=True)
            title_label.configure(font=completed_font)
            title_label.completed_font = completed_font
        def open_details(event=None):
            self.show_task_details(task_id)

        title_label.configure(cursor="hand2", takefocus=1, highlightthickness=1,
                              highlightbackground=PAPER, highlightcolor=PAPER)
        title_label.task_focus_label = True
        title_label.bind("<Enter>", lambda event: title_label.configure(fg=ACCENT_DARK))
        title_label.bind("<Leave>", lambda event: title_label.configure(fg=title_color))
        title_label.bind("<FocusIn>", lambda event: self.update_focus_drawing(title_label))
        title_label.bind("<FocusIn>", lambda event: self.reveal_row(row), add="+")
        for trigger in ("<Button-1>", "<Return>", "<space>"):
            title_label.bind(trigger, open_details)
        for surface in (row, details):
            surface.bind("<Button-1>", open_details)

        title_label.pack(fill="x")
        self.task_titles.append(title_label)
        if note:
            self.add_note_preview(details, row, note, open_details)
        if deadline:
            badge = label(details, "", PAPER, MUTED, size=8, anchor="w")
            badge.pack(fill="x", pady=(2, 0))
            badge.bind("<Button-1>", open_details)
            self.update_deadline_label(badge, deadline, done)
            if isinstance(deadline, datetime) and not done:
                self.timed_deadline_labels.append((badge, deadline))

        if done:
            times = (
                f"创建  {created_at or '未记录'}",
                f"完成  {completion_text(done, completed_at, completed_on)}",
            )
            for value in times:
                timestamp = label(details, value, PAPER, MUTED, size=8, anchor="w")
                timestamp.pack(fill="x")
                timestamp.bind("<Button-1>", open_details)

        handle.bind("<FocusIn>", lambda event: self.update_focus_drawing(event.widget))
        for control in (handle, check):
            control.bind("<FocusIn>", lambda event: self.reveal_row(row), add="+")

    def add_note_preview(self, details, row, note, on_open):
        lines = note.strip().splitlines()
        first = lines[0].strip() if lines else "查看备注"
        suffix = "…" if len(lines) > 1 else ""
        preview = tk.Label(details, bg=PAPER, fg=MUTED, font=self.note_font, anchor="w",
                           width=1, padx=1, pady=0, cursor="hand2", takefocus=1,
                           highlightthickness=1, highlightbackground=PAPER, highlightcolor=PAPER)
        preview.task_focus_label = True
        preview.pack(fill="x", pady=(1, 0))

        def resize(event):
            available = event.width - 4
            if self.note_font.measure(first + suffix) <= available:
                preview.configure(text=first + suffix)
                return
            low, high = 0, len(first)
            while low < high:
                middle = (low + high + 1) // 2
                if self.note_font.measure(first[:middle] + "…") <= available:
                    low = middle
                else:
                    high = middle - 1
            preview.configure(text=first[:low].rstrip() + "…")

        preview.bind("<Configure>", resize)
        preview.bind("<Enter>", lambda event: preview.configure(fg=ACCENT_DARK))
        preview.bind("<Leave>", lambda event: preview.configure(fg=MUTED))
        preview.bind("<FocusIn>", lambda event: self.update_focus_drawing(event.widget))
        preview.bind("<FocusIn>", lambda event: self.reveal_row(row), add="+")
        for trigger in ("<Button-1>", "<Return>", "<space>"):
            preview.bind(trigger, lambda event: on_open())

    def begin_task_drag(self, event, task_id):
        self.drag_task = task_id
        self.drag_origin_y = event.y_root
        self.drag_y = event.y_root
        self.drop_target = None

    def drag_task_motion(self, event):
        if self.drag_task is None:
            return
        self.drag_y = event.y_root
        if self.drag_job is None and abs(self.drag_y - self.drag_origin_y) >= 5:
            self.update_drop_target()

    def update_drop_target(self):
        if self.drop_target is not None:
            self.task_rows[self.drop_target][0].divider.configure(bg=LINE)

        y = self.drag_y - self.canvas.winfo_rooty()
        height = self.canvas.winfo_height()
        if y < 20:
            self.canvas.yview_scroll(-1, "units")
        elif y > height - 20:
            self.canvas.yview_scroll(1, "units")

        cursor = self.canvas.canvasy(y)
        target = min(
            self.reorder_group(self.drag_task),
            key=lambda task_id: abs(cursor - self.row_center(self.task_rows[task_id][0])),
        )
        self.drop_target = target if target != self.drag_task else None
        if self.drop_target is not None:
            self.task_rows[target][0].divider.configure(bg=ACCENT)
        self.drag_job = self.root.after(65, self.update_drop_target)

    @staticmethod
    def row_center(row):
        return row.winfo_y() + row.winfo_height() / 2

    def cancel_task_drag(self):
        if self.drag_job is not None:
            self.root.after_cancel(self.drag_job)
            self.drag_job = None
        if self.drop_target is not None:
            self.task_rows[self.drop_target][0].divider.configure(bg=LINE)
        self.drag_task = self.drop_target = None

    def end_task_drag(self, event):
        task_id, target = self.drag_task, self.drop_target
        self.cancel_task_drag()
        if target is not None:
            self.reorder(task_id, target)

    def reorder_group(self, task_id):
        source, done = self.task_rows[task_id]
        return [
            key for key, (row, state) in self.task_rows.items()
            if state == done and (not self.history_mode or row.completed_on == source.completed_on)
        ]

    def move_task(self, task_id, offset):
        visible = self.reorder_group(task_id)
        index = visible.index(task_id) + offset
        if 0 <= index < len(visible):
            self.reorder(task_id, visible[index])

    def reorder(self, task_id, target):
        done = self.task_rows[task_id][1]
        try:
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                rows = self.db.execute(
                    "SELECT id, sort_order FROM tasks WHERE done = ? ORDER BY sort_order, id DESC",
                    (done,),
                ).fetchall()
                if done:
                    visible = set(self.reorder_group(task_id))
                    rows = [(key, rank) for key, rank in rows if key in visible]
                order = [key for key, _ in rows]
                if task_id not in order or target not in order:
                    return
                index = order.index(target)
                order.remove(task_id)
                order.insert(index, task_id)
                self.db.executemany(
                    "UPDATE tasks SET sort_order = ? WHERE id = ?",
                    ((rank, key) for (_, rank), key in zip(rows, order)),
                )
        except sqlite3.Error as error:
            messagebox.showerror("排序失败", str(error), parent=self.root)
            return
        self.refresh()
        self.root.update_idletasks()
        self.restore_task_focus(self.task_handles[task_id])

    def change(self, sql, args, new_filter=None):
        try:
            with self.db:
                self.db.execute(sql, args)
        except sqlite3.Error as error:
            messagebox.showerror("保存失败", str(error), parent=self.root)
            return False
        if new_filter is not None:
            self.filter = new_filter
        self.refresh()
        return True

    def add(self):
        title = self.entry_value.get().strip()
        if title and self.change(
            "INSERT INTO tasks (title, deadline, created_at, sort_order) "
            "SELECT ?, ?, ?, COALESCE(MIN(sort_order), 0) - 1 FROM tasks",
            (title, deadline_text(self.deadline), datetime.now().isoformat(sep=" ", timespec="seconds")),
            new_filter=0 if self.filter == 1 else None,
        ):
            self.entry_value.set("")
            self.set_deadline(None)
            self.canvas.yview_moveto(0)
        self.entry.focus_set()

    def offer_undo(self, text, sql, args):
        self.clear_undo()
        self.undo_action = (sql, args)
        self.undo_message.configure(text=text)
        self.undo_bar.grid()
        self.undo_timer = self.root.after(8000, self.clear_undo)

    def clear_undo(self):
        if self.undo_timer is not None:
            self.root.after_cancel(self.undo_timer)
            self.undo_timer = None
        self.undo_action = None
        self.undo_bar.grid_remove()

    def undo_last(self):
        if self.undo_action is not None and self.change(*self.undo_action):
            self.clear_undo()
            self.restore_task_focus(self.nav_buttons[self.filter])

    def toggle(self, task_id):
        previous = self.db.execute(
            "SELECT done, completed_on, completed_at FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if previous is None:
            return
        now = datetime.now()
        if self.change(
            "UPDATE tasks SET done = 1 - done, "
            "completed_on = CASE WHEN done = 0 THEN ? ELSE NULL END, "
            "completed_at = CASE WHEN done = 0 THEN ? ELSE NULL END WHERE id = ?",
            (now.date().isoformat(), now.isoformat(sep=" ", timespec="seconds"), task_id),
        ):
            self.offer_undo("已移回未完成" if previous[0] else "已标记完成",
                            "UPDATE tasks SET done = ?, completed_on = ?, completed_at = ? WHERE id = ?",
                            (*previous, task_id))
            self.restore_task_focus(self.task_checks.get(task_id, self.nav_buttons[self.filter]))

    def show_task_details(self, task_id):
        record = self.db.execute(
            "SELECT title, note, done, deadline, created_at, completed_at, completed_on "
            "FROM tasks WHERE id = ?", (task_id,),
        ).fetchone()
        if record is None:
            return
        title, note, done, deadline, created_at, completed_at, completed_on = record

        dialog = DialogPanel(self.root, "事项详情", width=326)
        label(dialog.body, title if len(title) <= 180 else title[:180] + "…",
              PAPER, INK, size=11, bold=True, wraplength=280, justify="left",
              anchor="w").pack(fill="x", pady=(0, 10))
        timeline = tk.Frame(dialog.body, bg=SURFACE, padx=10, pady=8)
        timeline.pack(fill="x")
        for row, (caption, value) in enumerate((
            ("创建时间", created_at or "未记录"),
            ("完成时间", completion_text(done, completed_at, completed_on)),
        )):
            label(timeline, caption, SURFACE, MUTED, size=8).grid(
                row=row, column=0, sticky="nw", padx=(0, 12), pady=3
            )
            label(timeline, value, SURFACE, INK, size=9, wraplength=184,
                  justify="left").grid(row=row, column=1, sticky="w", pady=3)

        label(dialog.body, "备注", PAPER, INK, size=9, bold=True).pack(anchor="w", pady=(12, 4))
        if note:
            note_area = tk.Frame(dialog.body, bg=SURFACE)
            note_area.pack(fill="x")
            note_area.grid_columnconfigure(0, weight=1)
            lines = min(6, max(2, note.count("\n") + 1, (len(note) + 33) // 34))
            note_text = tk.Text(note_area, width=1, height=lines, wrap="word", bg=SURFACE,
                                fg=INK, font=(FONT, 9), relief="flat", highlightthickness=0,
                                padx=8, pady=6)
            note_text.grid(row=0, column=0, sticky="ew")
            note_text.insert("1.0", note)
            note_text.configure(state="disabled")
            scrollbar = ListScrollbar(note_area, note_text, background=SURFACE)
            scrollbar.grid(row=0, column=1, sticky="ns")
            note_text.configure(yscrollcommand=scrollbar.set)
        else:
            label(dialog.body, "无备注", PAPER, MUTED, size=9).pack(anchor="w")

        def edit_task():
            dialog.close()
            self.edit(task_id, title, read_deadline(deadline), focus_note=bool(note))

        def delete_task():
            if self.delete(task_id, parent=dialog):
                dialog.close()

        footer = dialog.make_footer("关闭", dialog.close, cancel=False)
        PillButton(footer, "编辑", edit_task, PAPER, SURFACE,
                   ACCENT_DARK, ACCENT_HOVER, height=31).pack(side="left")
        PillButton(footer, "删除", delete_task, PAPER, ACCENT_PALE,
                   ACCENT_DARK, ACCENT_HOVER, height=31).pack(side="left", padx=(6, 0))
        dialog.show()


    def edit(self, task_id, title, deadline, *, focus_note=False):
        record = self.db.execute("SELECT note FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if record is None:
            return
        note, = record
        dialog = DialogPanel(self.root, "编辑任务", width=326)
        form = dialog.body
        title_field = form_field(form, "任务名称", 35)
        entry = tk.Entry(title_field.content, bg=PAPER, fg=INK, font=(FONT, 10),
                         relief="flat", highlightthickness=0, insertbackground=INK)
        entry.pack(fill="x", padx=7, ipady=4)
        entry.insert(0, title)
        entry.select_range(0, "end")
        focus_outline(title_field, entry)

        def select_deadline(value):
            nonlocal deadline
            deadline = value
            deadline_control.configure(text=deadline_summary(value), fg=INK if value else MUTED)

        deadline_field = form_field(form, "截止时间", 35)
        deadline_control = button(
            deadline_field.content, deadline_summary(deadline),
            lambda: DatePicker(dialog, deadline, select_deadline),
            PAPER, INK if deadline else MUTED, SURFACE, padx=6, anchor="w"
        )
        deadline_control.pack(side="left", fill="x", expand=True)
        arrow = label(deadline_field.content, "›", PAPER, MUTED, size=13, cursor="hand2")
        arrow.pack(side="right", padx=(0, 7))
        arrow.bind("<Button-1>", lambda event: deadline_control.invoke())
        focus_outline(deadline_field, deadline_control)

        note_field = form_field(form, "备注（选填）", 88)
        note_entry = tk.Text(note_field.content, bg=PAPER, fg=INK, font=(FONT, 9),
                             height=4, width=27, wrap="word", relief="flat", padx=6, pady=4,
                             highlightthickness=0, insertbackground=INK)
        note_entry.pack(fill="x")
        note_entry.insert("1.0", note)
        focus_outline(note_field, note_entry)

        def save():
            updated = entry.get().strip()
            if not updated:
                entry.focus_set()
                title_field.outline("#BE5266")
                return
            note_value = note_entry.get("1.0", "end-1c")
            if self.change(
                "UPDATE tasks SET title = ?, deadline = ?, note = ? WHERE id = ?",
                (updated, deadline_text(deadline), note_value if note_value.strip() else "", task_id),
            ):
                dialog.close()
                self.restore_task_focus(self.task_checks.get(task_id, self.nav_buttons[self.filter]))

        dialog.make_footer("保存", save)
        entry.bind("<Return>", lambda event: save())
        dialog.show(note_entry if focus_note else entry)


    def delete(self, task_id, *, parent=None):
        parent = parent or self.root
        if not messagebox.askyesno("删除任务", "确定删除这条任务？", parent=parent):
            return
        try:
            with self.db:
                records = self.db.execute(
                    "DELETE FROM tasks WHERE id = ? "
                    "RETURNING title, done, deadline, sort_order, completed_on, note, created_at, completed_at",
                    (task_id,),
                ).fetchall()
        except sqlite3.Error as error:
            messagebox.showerror("删除失败", str(error), parent=parent)
            return
        if not records:
            return
        self.refresh()
        self.offer_undo(
            "已删除任务",
            "INSERT INTO tasks (id, title, done, deadline, sort_order, completed_on, note, created_at, completed_at) "
            "VALUES ((SELECT ? WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE id = ?)), ?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, task_id, *records[0]),
        )
        self.restore_task_focus(self.nav_buttons[self.filter])
        return True


def main():
    if reopen_running_app():
        return
    set_app_id("ToDoList.Desktop")
    root = tk.Tk()
    root.withdraw()
    database = Path(__file__).with_name("tasks.sqlite3")
    try:
        location = DataLocation()
        database = location.path
        db = location.open()
        try:
            app = TodoApp(root, db)
            app.data_location = location
            app.tray = WindowsTray(root, app.reopen, app.quit_app,
                                   app.toggle_topmost, lambda: app.topmost, app.show_settings)
            try:
                root.protocol("WM_DELETE_WINDOW", app.hide_to_tray)
                app.show_startup()
                root.mainloop()
            finally:
                app.tray.dispose()
        finally:
            app.db.close() if "app" in locals() else db.close()
    except (sqlite3.Error, OSError) as error:
        messagebox.showerror(f"无法打开 {APP_NAME}", f"{database}\n{error}", parent=root)
        root.destroy()


if __name__ == "__main__":
    main()
