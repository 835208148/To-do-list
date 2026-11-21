"""Windows notification-area icon and activation message."""

import ctypes as ct
from collections import deque
from ctypes import wintypes as wt
from pathlib import Path


USER = ct.WinDLL("user32", use_last_error=True)
KERNEL = ct.WinDLL("kernel32", use_last_error=True)
SHELL = ct.WinDLL("shell32", use_last_error=True)
LRESULT = ct.c_ssize_t
WNDPROC = ct.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
CLASS_NAME = "DesktopTodoPanel.NotificationWindow"
ICON_PATH = Path(__file__).with_name("one-piece.ico")
WM_TRAY = 0x8001
WM_REOPEN = 0x8002
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
NIM_ADD = 0
NIM_DELETE = 2


class WindowClass(ct.Structure):
    _fields_ = [
        ("style", wt.UINT), ("proc", WNDPROC), ("class_extra", ct.c_int),
        ("window_extra", ct.c_int), ("instance", wt.HINSTANCE),
        ("icon", wt.HICON), ("cursor", wt.HANDLE), ("background", wt.HBRUSH),
        ("menu_name", wt.LPCWSTR), ("class_name", wt.LPCWSTR),
    ]


class NotificationIcon(ct.Structure):
    _fields_ = [
        ("size", wt.DWORD), ("window", wt.HWND), ("id", wt.UINT),
        ("flags", wt.UINT), ("message", wt.UINT), ("icon", wt.HICON),
        ("tooltip", wt.WCHAR * 128), ("state", wt.DWORD), ("state_mask", wt.DWORD),
        ("info", wt.WCHAR * 256), ("version", wt.UINT), ("info_title", wt.WCHAR * 64),
        ("info_flags", wt.DWORD), ("guid", ct.c_byte * 16), ("balloon_icon", wt.HICON),
    ]


def api(library, name, result, *args):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = args
    return function


find_window = api(USER, "FindWindowW", wt.HWND, wt.LPCWSTR, wt.LPCWSTR)
post_message = api(USER, "PostMessageW", wt.BOOL, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
default_proc = api(USER, "DefWindowProcW", LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
module_handle = api(KERNEL, "GetModuleHandleW", wt.HINSTANCE, wt.LPCWSTR)
register_class = api(USER, "RegisterClassW", wt.ATOM, ct.POINTER(WindowClass))
unregister_class = api(USER, "UnregisterClassW", wt.BOOL, wt.LPCWSTR, wt.HINSTANCE)
register_message = api(USER, "RegisterWindowMessageW", wt.UINT, wt.LPCWSTR)
create_window = api(USER, "CreateWindowExW", wt.HWND, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR,
                    wt.DWORD, ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.HWND,
                    wt.HMENU, wt.HINSTANCE, wt.LPVOID)
destroy_window = api(USER, "DestroyWindow", wt.BOOL, wt.HWND)
load_icon = api(USER, "LoadIconW", wt.HICON, wt.HINSTANCE, ct.c_void_p)
notify_icon = api(SHELL, "Shell_NotifyIconW", wt.BOOL, wt.DWORD, ct.POINTER(NotificationIcon))
create_menu = api(USER, "CreatePopupMenu", wt.HMENU)
append_menu = api(USER, "AppendMenuW", wt.BOOL, wt.HMENU, wt.UINT, ct.c_size_t, wt.LPCWSTR)
destroy_menu = api(USER, "DestroyMenu", wt.BOOL, wt.HMENU)
get_cursor = api(USER, "GetCursorPos", wt.BOOL, ct.POINTER(wt.POINT))
set_foreground = api(USER, "SetForegroundWindow", wt.BOOL, wt.HWND)
track_menu = api(USER, "TrackPopupMenu", wt.UINT, wt.HMENU, wt.UINT, ct.c_int,
                 ct.c_int, ct.c_int, wt.HWND, wt.LPVOID)
move_window = api(USER, "SetWindowPos", wt.BOOL, wt.HWND, wt.HWND, ct.c_int,
                  ct.c_int, ct.c_int, ct.c_int, wt.UINT)
get_ancestor = api(USER, "GetAncestor", wt.HWND, wt.HWND, wt.UINT)
load_image = api(USER, "LoadImageW", wt.HANDLE, wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                 ct.c_int, ct.c_int, wt.UINT)
system_metric = api(USER, "GetSystemMetrics", ct.c_int, ct.c_int)
set_app_id = api(SHELL, "SetCurrentProcessExplicitAppUserModelID", ct.c_long, wt.LPCWSTR)
destroy_icon = api(USER, "DestroyIcon", wt.BOOL, wt.HICON)


def reopen_running_app():
    hwnd = find_window(CLASS_NAME, None)
    return bool(hwnd and post_message(hwnd, WM_REOPEN, 0, 0))


class MonitorInfo(ct.Structure):
    _fields_ = [("size", wt.DWORD), ("area", wt.RECT), ("work", wt.RECT), ("flags", wt.DWORD)]


monitor_from_point = api(USER, "MonitorFromPoint", wt.HANDLE, wt.POINT, wt.DWORD)
monitor_info = api(USER, "GetMonitorInfoW", wt.BOOL, wt.HANDLE, ct.POINTER(MonitorInfo))
window_rect = api(USER, "GetWindowRect", wt.BOOL, wt.HWND, ct.POINTER(wt.RECT))


def window_bounds(window):
    hwnd = get_ancestor(window.winfo_id(), 2)
    rect = wt.RECT()
    window_rect(hwnd, ct.byref(rect))
    return rect


def place_window(window, x, y):
    hwnd = get_ancestor(window.winfo_id(), 2)
    rect = window_bounds(window)
    monitor = monitor_from_point(wt.POINT(x, y), 2)
    info = MonitorInfo(size=ct.sizeof(MonitorInfo))
    if monitor_info(monitor, ct.byref(info)):
        x = max(info.work.left, min(x, info.work.right - (rect.right - rect.left)))
        y = max(info.work.top, min(y, info.work.bottom - (rect.bottom - rect.top)))
    move_window(hwnd, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)



class WindowsTray:
    def __init__(self, root, reopen, quit_app, toggle_topmost, is_topmost, open_settings=None):
        self.root = root
        self.reopen = reopen
        self.quit_app = quit_app
        self.toggle_topmost = toggle_topmost
        self.is_topmost = is_topmost
        self.open_settings = open_settings
        self.visible = False
        self.events = deque()
        self.taskbar_created = register_message("TaskbarCreated")
        self.instance = module_handle(None)
        self.callback = WNDPROC(self.window_proc)
        kind = WindowClass(proc=self.callback, instance=self.instance, class_name=CLASS_NAME)
        if not register_class(ct.byref(kind)):
            raise ct.WinError(ct.get_last_error())
        self.hwnd = create_window(0, CLASS_NAME, None, 0, 0, 0, 0, 0, None,
                                  None, self.instance, None)
        if not self.hwnd:
            error = ct.WinError(ct.get_last_error())
            unregister_class(CLASS_NAME, self.instance)
            raise error
        self.custom_icon = load_image(
            None, str(ICON_PATH), 1, system_metric(49), system_metric(50), 0x0010
        )
        self.icon = NotificationIcon(
            size=ct.sizeof(NotificationIcon), window=self.hwnd, id=1, flags=0x07,
            message=WM_TRAY, icon=self.custom_icon or load_icon(None, 32512),
            tooltip="To-do list",
        )
        self.root.after(70, self.dispatch_events)

    def dispatch_events(self):
        # Win32 can dispatch a window message while Tcl is already processing events.
        self.root.after(70, self.dispatch_events)
        while self.events:
            self.events.popleft()()

    def show(self):
        if not self.visible:
            self.visible = bool(notify_icon(NIM_ADD, ct.byref(self.icon)))
        return self.visible

    def hide(self):
        if self.visible:
            notify_icon(NIM_DELETE, ct.byref(self.icon))
            self.visible = False

    def dispose(self):
        self.hide()
        destroy_window(self.hwnd)
        unregister_class(CLASS_NAME, self.instance)
        if self.custom_icon:
            destroy_icon(self.custom_icon)

    def window_proc(self, hwnd, message, wparam, lparam):
        if message == WM_REOPEN:
            self.events.append(self.reopen)
            return 0
        if self.taskbar_created and message == self.taskbar_created:
            self.events.append(self.restore_icon_after_shell_restart)
            return 0
        if message == WM_TRAY:
            if lparam == WM_LBUTTONUP:
                self.events.append(self.reopen)
            elif lparam == WM_RBUTTONUP:
                self.events.append(self.open_menu)
            return 0
        return default_proc(hwnd, message, wparam, lparam)

    def restore_icon_after_shell_restart(self):
        if self.visible:
            self.visible = False
            self.show()

    def open_menu(self):
        menu = create_menu()
        if not menu:
            return
        try:
            append_menu(menu, 0, 1, "打开 To-do list")
            append_menu(menu, 0x0008 if self.is_topmost() else 0, 3, "窗口置顶")
            if self.open_settings is not None:
                append_menu(menu, 0, 4, "设置")
            append_menu(menu, 0, 2, "退出")
            point = wt.POINT()
            get_cursor(ct.byref(point))
            set_foreground(self.hwnd)
            choice = track_menu(menu, 0x0102, point.x, point.y, 0, self.hwnd, None)
            post_message(self.hwnd, 0, 0, 0)
            if choice == 1:
                self.reopen()
            elif choice == 2:
                self.quit_app()
            elif choice == 3:
                self.toggle_topmost()
            elif choice == 4 and self.open_settings is not None:
                self.reopen()
                self.open_settings()
        finally:
            destroy_menu(menu)
