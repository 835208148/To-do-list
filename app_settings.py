"""Per-user startup preference and task database location."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ToDoListDesktop"


def startup_command():
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([str(executable)])
    windowed = executable.with_name("pythonw.exe")
    if windowed.is_file():
        executable = windowed
    return subprocess.list2cmdline([
        str(executable), "-B", str(Path(__file__).with_name("Todo.pyw")),
    ])


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, RUN_NAME)
        return kind == winreg.REG_SZ and value == startup_command()
    except FileNotFoundError:
        return False


def set_startup(enabled):
    if enabled:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command())
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, RUN_NAME)
        except FileNotFoundError:
            pass


class DataLocation:
    def __init__(self, config_dir=None, legacy_path=None):
        self.config_dir = Path(config_dir) if config_dir else Path(os.environ["APPDATA"]) / "To-do list"
        self.config_file = self.config_dir / "preferences.json"
        legacy = Path(legacy_path) if legacy_path else Path(__file__).with_name("tasks.sqlite3")
        if self.config_file.exists():
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            self.path = Path(data["database"]).resolve()
            if not self.path.is_file():
                raise FileNotFoundError(f"找不到事项数据文件，请恢复该文件后重试\n{self.path}")
        else:
            self.path = legacy.resolve() if legacy.is_file() else self.config_dir / "tasks.sqlite3"

    def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)

    def save(self, path):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix="preferences-", suffix=".json", dir=self.config_dir)
        staged = Path(name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                json.dump({"database": str(path)}, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(staged, self.config_file)
        finally:
            staged.unlink(missing_ok=True)

    def relocate(self, connection, folder):
        target = Path(folder).resolve() / "tasks.sqlite3"
        if target == self.path.resolve():
            return connection
        # Exclusive creation keeps existing task data safe, including on a retry.
        with target.open("xb"):
            pass
        copied = None
        try:
            copied = sqlite3.connect(target)
            connection.backup(copied)
            if copied.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise sqlite3.DatabaseError("数据校验失败")
            self.save(target)
        except Exception:
            if copied is not None:
                copied.close()
            target.unlink(missing_ok=True)
            raise
        self.path = target
        return copied
