import ctypes
import json
import platform
import queue
import random
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


APP_TITLE = "自动鞠躬骑乘"
# Author marker: @f
AUTHOR_TEXT = "@f"
GITHUB_TEXT = "github: https://github.com/futuer-szd"
DISCLAIMER_TEXT = "免责声明：本脚本仅供研究学习，使用后果自负。"

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MAPVK_VK_TO_VSC = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

VK_CODE_MAP = {
    "TAB": 0x09,
    "ESC": 0x1B,
    "R": 0x52,
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
}

EXTENDED_KEY_VKS = set()

DEFAULT_CONFIG = {
    "first_loop_delay": 2.0,
    "tab_delay": 1.0,
    "bow_key_delay": 1.0,
    "before_mount_delay": 2.0,
    "ride_duration": 12.0,
    "between_small_cycles_delay": 3.0,
    "between_big_cycles_wait": 2.0,
    "jitter_min_ms": 1000,
    "jitter_max_ms": 2500,
    "salute_key": "2",
    "small_cycle_count": 10,
    "enable_daily_skip": False,
}

ENTRY_BG = "#ffffff"
ENTRY_BORDER = "#26a269"
WINDOW_BG = "#f7f5ef"
PANEL_BG = "#fdfcf8"
ACCENT = "#8d1f12"
BEIJING_TZ = timezone(timedelta(hours=8))

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else wintypes.DWORD


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUTUNION),
    ]


@dataclass
class ScriptConfig:
    first_loop_delay: float
    tab_delay: float
    bow_key_delay: float
    before_mount_delay: float
    ride_duration: float
    between_small_cycles_delay: float
    between_big_cycles_wait: float
    jitter_min_ms: int
    jitter_max_ms: int
    salute_key: str
    small_cycle_count: int
    enable_daily_skip: bool

    @classmethod
    def from_dict(cls, data: dict) -> "ScriptConfig":
        merged = DEFAULT_CONFIG | data
        config = cls(
            first_loop_delay=max(0.0, float(merged["first_loop_delay"])),
            tab_delay=max(0.0, float(merged["tab_delay"])),
            bow_key_delay=max(0.0, float(merged["bow_key_delay"])),
            before_mount_delay=max(0.0, float(merged["before_mount_delay"])),
            ride_duration=max(0.0, float(merged["ride_duration"])),
            between_small_cycles_delay=max(0.0, float(merged["between_small_cycles_delay"])),
            between_big_cycles_wait=max(0.0, float(merged["between_big_cycles_wait"])),
            jitter_min_ms=max(0, int(merged["jitter_min_ms"])),
            jitter_max_ms=max(0, int(merged["jitter_max_ms"])),
            salute_key=str(merged["salute_key"]),
            small_cycle_count=max(1, int(merged["small_cycle_count"])),
            enable_daily_skip=bool(merged["enable_daily_skip"]),
        )
        if config.salute_key not in "0123456789":
            config.salute_key = "2"
        if config.jitter_min_ms > config.jitter_max_ms:
            config.jitter_min_ms, config.jitter_max_ms = config.jitter_max_ms, config.jitter_min_ms
        return config

    def to_dict(self) -> dict:
        return {
            "first_loop_delay": self.first_loop_delay,
            "tab_delay": self.tab_delay,
            "bow_key_delay": self.bow_key_delay,
            "before_mount_delay": self.before_mount_delay,
            "ride_duration": self.ride_duration,
            "between_small_cycles_delay": self.between_small_cycles_delay,
            "between_big_cycles_wait": self.between_big_cycles_wait,
            "jitter_min_ms": self.jitter_min_ms,
            "jitter_max_ms": self.jitter_max_ms,
            "salute_key": self.salute_key,
            "small_cycle_count": self.small_cycle_count,
            "enable_daily_skip": self.enable_daily_skip,
        }


def set_dpi_awareness() -> None:
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def is_user_admin() -> bool:
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_PATH = get_app_dir() / "auto_bow_mount_config.json"


def format_number(value: float | int) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def load_config() -> ScriptConfig:
    if not CONFIG_PATH.exists():
        return ScriptConfig.from_dict({})
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return ScriptConfig.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return ScriptConfig.from_dict({})


def save_config(config: ScriptConfig) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _send_input(input_struct: INPUT) -> None:
    sent = user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def press_virtual_key(vk_code: int) -> None:
    scan_code = user32.MapVirtualKeyW(vk_code, MAPVK_VK_TO_VSC)
    flags = KEYEVENTF_SCANCODE
    if vk_code in EXTENDED_KEY_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    key_down = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUTUNION(ki=KEYBDINPUT(wVk=0, wScan=scan_code, dwFlags=flags)),
    )
    key_up = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUTUNION(ki=KEYBDINPUT(wVk=0, wScan=scan_code, dwFlags=flags | KEYEVENTF_KEYUP)),
    )
    _send_input(key_down)
    time.sleep(0.03)
    _send_input(key_up)


def left_click() -> None:
    mouse_down = INPUT(type=INPUT_MOUSE, union=INPUTUNION(mi=MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTDOWN)))
    mouse_up = INPUT(type=INPUT_MOUSE, union=INPUTUNION(mi=MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTUP)))
    _send_input(mouse_down)
    time.sleep(0.03)
    _send_input(mouse_up)


class AutomationRunner:
    def __init__(self, config: ScriptConfig, log_callback, finish_callback, state_callback):
        self.config = config
        self.log = log_callback
        self.finish_callback = finish_callback
        self.state_callback = state_callback
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.last_daily_skip_date = ""

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.pause_event.set()

    def pause(self) -> None:
        if not self.stop_event.is_set():
            self.pause_event.clear()
            self.state_callback("paused")

    def resume(self) -> None:
        if not self.stop_event.is_set():
            self.pause_event.set()
            self.state_callback("running")

    def toggle_pause(self) -> None:
        if self.pause_event.is_set():
            self.pause()
        else:
            self.resume()

    def is_alive(self) -> bool:
        return self.thread.is_alive()

    def is_paused(self) -> bool:
        return not self.pause_event.is_set()

    def _wait_if_paused(self) -> bool:
        while not self.stop_event.is_set() and not self.pause_event.is_set():
            time.sleep(0.1)
        return not self.stop_event.is_set()

    def _sleep(self, seconds: float) -> bool:
        end_time = time.monotonic() + max(0.0, seconds)
        while not self.stop_event.is_set():
            if not self._wait_if_paused():
                return False
            remaining = end_time - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(0.1, remaining))
        return False

    def _delay_with_jitter(self, base_seconds: float) -> bool:
        jitter_ms = random.randint(self.config.jitter_min_ms, self.config.jitter_max_ms)
        return self._sleep(max(0.0, base_seconds) + jitter_ms / 1000.0)

    def _press(self, key_name: str) -> bool:
        if not self._wait_if_paused():
            return False
        press_virtual_key(VK_CODE_MAP[key_name])
        return True

    def _run_small_cycle(self) -> bool:
        if not self._press("TAB"):
            return False
        if not self._delay_with_jitter(self.config.tab_delay):
            return False

        if not self._press(self.config.salute_key):
            return False
        if not self._delay_with_jitter(self.config.bow_key_delay):
            return False

        if not self._press("ESC"):
            return False
        if not self._delay_with_jitter(self.config.before_mount_delay):
            return False

        if not self._press("R"):
            return False
        if not self._delay_with_jitter(self.config.ride_duration):
            return False

        if not self._wait_if_paused():
            return False
        left_click()
        return True

    def _handle_daily_skip(self) -> bool:
        if not self.config.enable_daily_skip:
            return True

        now = datetime.now(BEIJING_TZ)
        today = now.date().isoformat()
        if self.last_daily_skip_date == today:
            return True

        window_start = datetime.combine(now.date(), dt_time(3, 58, 0), tzinfo=BEIJING_TZ)
        window_end = datetime.combine(now.date(), dt_time(4, 0, 0), tzinfo=BEIJING_TZ)
        trigger_time = datetime.combine(now.date(), dt_time(4, 0, 10), tzinfo=BEIJING_TZ)
        if now < window_start or now > window_end:
            return True

        self.log("进入北京时间月卡跳过时间窗，等待到 04:00:10 后自动点击一次。")
        while not self.stop_event.is_set():
            if not self._wait_if_paused():
                return False
            now = datetime.now(BEIJING_TZ)
            if now >= trigger_time:
                left_click()
                self.last_daily_skip_date = today
                self.log("已执行 04:00:10 月卡跳过点击，并额外等待 10 秒。")
                return self._sleep(10.0)
            time.sleep(0.5)
        return False

    def _run(self) -> None:
        try:
            self.state_callback("running")
            self.log("脚本已启动，请保持目标窗口在前台。")
            self.log(f"月卡跳过：{'已开启' if self.config.enable_daily_skip else '未开启'}。")
            if not self._delay_with_jitter(self.config.first_loop_delay):
                return

            big_cycle_index = 0
            while not self.stop_event.is_set():
                big_cycle_index += 1
                self.log(f"开始第 {big_cycle_index} 轮大循环。")

                for small_index in range(1, self.config.small_cycle_count + 1):
                    if not self._handle_daily_skip():
                        return
                    self.log(f"执行第 {small_index}/{self.config.small_cycle_count} 次小循环。")
                    if not self._run_small_cycle():
                        return
                    if small_index < self.config.small_cycle_count:
                        if not self._delay_with_jitter(self.config.between_small_cycles_delay):
                            return

                if not self._delay_with_jitter(self.config.between_big_cycles_wait):
                    return
        except Exception as exc:
            self.log(f"运行出错: {exc}")
        finally:
            self.finish_callback()


class LabeledEntry:
    def __init__(self, master, caption: str, variable: tk.StringVar, width: int = 7):
        self.frame = tk.Frame(master, bg=PANEL_BG)
        self.caption = tk.Label(
            self.frame,
            text=caption,
            bg=PANEL_BG,
            fg="#4a4036",
            font=("Microsoft YaHei UI", 9),
        )
        self.caption.pack(pady=(0, 4))
        self.entry = tk.Entry(
            self.frame,
            textvariable=variable,
            width=width,
            justify="center",
            bg=ENTRY_BG,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=ENTRY_BORDER,
            highlightcolor=ENTRY_BORDER,
            font=("Consolas", 12),
        )
        self.entry.pack(ipady=4)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("860x640")
        self.root.minsize(800, 600)
        self.root.configure(bg=WINDOW_BG)

        self.ui_queue = queue.Queue()
        self._closing = False
        self.runner = None
        self.status_var = tk.StringVar(value="未运行")

        config = load_config()
        self.first_loop_delay_var = tk.StringVar()
        self.tab_delay_var = tk.StringVar()
        self.bow_key_delay_var = tk.StringVar()
        self.before_mount_delay_var = tk.StringVar()
        self.ride_duration_var = tk.StringVar()
        self.between_small_cycles_delay_var = tk.StringVar()
        self.between_big_cycles_wait_var = tk.StringVar()
        self.jitter_min_ms_var = tk.StringVar()
        self.jitter_max_ms_var = tk.StringVar()
        self.salute_key_var = tk.StringVar()
        self.small_cycle_count_var = tk.StringVar()
        self.enable_daily_skip_var = tk.BooleanVar(value=False)
        self._set_form_from_config(config)

        self._build_styles()
        self._build_ui()
        self.root.after(50, self._process_ui_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_styles(self) -> None:
        style = ttk.Style()
        for theme_name in ("vista", "xpnative", "clam", "default"):
            if theme_name in style.theme_names():
                style.theme_use(theme_name)
                break

    def _build_ui(self) -> None:
        container = tk.Frame(self.root, bg=WINDOW_BG, padx=14, pady=12)
        container.pack(fill="both", expand=True)

        flow_panel = tk.Frame(container, bg=PANEL_BG, bd=1, relief="solid")
        flow_panel.pack(fill="x")

        title = tk.Label(
            flow_panel,
            text="---> 鞠躬(Tab ---> 鞠躬 ---> ESC) ---> 骑乘R ---> 退出骑乘左键 ---> 下一次鞠躬",
            bg=PANEL_BG,
            fg="#1f1f1f",
            font=("Microsoft YaHei UI", 14, "bold"),
        )
        title.pack(pady=(10, 8))

        delay_row = tk.Frame(flow_panel, bg=PANEL_BG)
        delay_row.pack(fill="x", padx=12, pady=(0, 10))

        tk.Label(
            delay_row,
            text="延迟(秒)：",
            bg=PANEL_BG,
            fg=ACCENT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(side="left", padx=(0, 10))

        flow_fields = [
            ("启动前", self.first_loop_delay_var),
            ("Tab后", self.tab_delay_var),
            ("动作后", self.bow_key_delay_var),
            ("骑乘前", self.before_mount_delay_var),
            ("骑乘中", self.ride_duration_var),
            ("下次前", self.between_small_cycles_delay_var),
        ]
        for index, (caption, variable) in enumerate(flow_fields):
            field = LabeledEntry(delay_row, caption, variable, width=6)
            field.frame.pack(side="left", padx=(0, 56 if index < len(flow_fields) - 1 else 0))

        info_panel = tk.Frame(container, bg=PANEL_BG, bd=1, relief="solid", padx=14, pady=14)
        info_panel.pack(fill="x", pady=(12, 0))

        top_info = tk.Frame(info_panel, bg=PANEL_BG)
        top_info.pack(fill="x")

        tk.Label(
            top_info,
            text="动作序号：",
            bg=PANEL_BG,
            fg=ACCENT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        action_combo = ttk.Combobox(
            top_info,
            textvariable=self.salute_key_var,
            values=[str(i) for i in range(10)],
            width=5,
            state="readonly",
        )
        action_combo.grid(row=0, column=1, sticky="w", padx=(6, 20))

        tk.Label(
            top_info,
            text="单次小循环鞠躬次数：",
            bg=PANEL_BG,
            fg=ACCENT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(16, 0))
        self._make_compact_entry(top_info, self.small_cycle_count_var, 6).grid(row=1, column=1, sticky="w", padx=(6, 20), pady=(16, 0))

        tk.Label(
            top_info,
            text="两次大循环间等待(秒)：",
            bg=PANEL_BG,
            fg=ACCENT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).grid(row=2, column=0, sticky="w", pady=(16, 0))
        self._make_compact_entry(top_info, self.between_big_cycles_wait_var, 6).grid(row=2, column=1, sticky="w", padx=(6, 20), pady=(16, 0))

        skip = tk.Checkbutton(
            top_info,
            text="启动4点月卡跳过",
            variable=self.enable_daily_skip_var,
            bg=PANEL_BG,
            activebackground=PANEL_BG,
            font=("Microsoft YaHei UI", 10),
        )
        skip.grid(row=0, column=2, rowspan=2, sticky="w", padx=(40, 0))

        jitter_panel = tk.Frame(info_panel, bg=PANEL_BG)
        jitter_panel.pack(fill="x", pady=(22, 0))

        tk.Label(
            jitter_panel,
            text="全局随机出现小延迟范围：",
            bg=PANEL_BG,
            fg="#111111",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(side="left")
        self._make_compact_entry(jitter_panel, self.jitter_min_ms_var, 7).pack(side="left", padx=(10, 8))
        tk.Label(
            jitter_panel,
            text="毫秒到",
            bg=PANEL_BG,
            fg="#111111",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(side="left")
        self._make_compact_entry(jitter_panel, self.jitter_max_ms_var, 7).pack(side="left", padx=(8, 8))
        tk.Label(
            jitter_panel,
            text="毫秒",
            bg=PANEL_BG,
            fg="#111111",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(side="left")

        note_row = tk.Frame(info_panel, bg=PANEL_BG)
        note_row.pack(anchor="w", pady=(18, 0))
        tk.Label(
            note_row,
            text="开源免费",
            bg=PANEL_BG,
            fg="#2563eb",
            justify="left",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left")
        tk.Label(
            note_row,
            text=" 说明：每个“延迟(秒)”字段都会额外叠加上方的随机毫秒范围。",
            bg=PANEL_BG,
            fg="#666666",
            justify="left",
            wraplength=780,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")
        tk.Label(
            info_panel,
            text="请使用管理员模式运行此程序",
            bg=PANEL_BG,
            fg="#c1121f",
            justify="left",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w", pady=(6, 0))

        bottom_bar = tk.Frame(container, bg=WINDOW_BG)
        bottom_bar.pack(fill="x", pady=(12, 0))

        left_buttons = tk.Frame(bottom_bar, bg=WINDOW_BG)
        left_buttons.pack(side="left")
        self.start_button = ttk.Button(left_buttons, text="启动", command=self.start_or_resume)
        self.start_button.pack(side="left")
        self.pause_button = ttk.Button(left_buttons, text="暂停/继续", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side="left", padx=(8, 0))
        self.stop_button = ttk.Button(left_buttons, text="中止", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))

        right_buttons = tk.Frame(bottom_bar, bg=WINDOW_BG)
        right_buttons.pack(side="right")
        self.save_button = ttk.Button(right_buttons, text="保存设置", command=self.save_current_settings)
        self.save_button.pack(side="left")
        self.restore_button = ttk.Button(right_buttons, text="还原默认设置", command=self.restore_defaults)
        self.restore_button.pack(side="left", padx=(8, 0))

        status_bar = tk.Frame(container, bg=WINDOW_BG)
        status_bar.pack(fill="x", pady=(10, 0))
        tk.Label(status_bar, text="状态：", bg=WINDOW_BG, font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        tk.Label(status_bar, textvariable=self.status_var, bg=WINDOW_BG, font=("Microsoft YaHei UI", 10)).pack(side="left")

        admin_state = "管理员" if is_user_admin() else "普通权限"
        env_text = f"兼容目标：Windows 11 x64，当前环境：{platform.release()} / {platform.machine()} / {admin_state}"
        tk.Label(
            status_bar,
            text=env_text,
            bg=WINDOW_BG,
            fg="#666666",
            font=("Microsoft YaHei UI", 9),
        ).pack(side="right")

        credit_bar = tk.Frame(container, bg=WINDOW_BG)
        credit_bar.pack(fill="x", pady=(6, 0))
        tk.Label(
            credit_bar,
            text=f"作者 {AUTHOR_TEXT}    {GITHUB_TEXT}    {DISCLAIMER_TEXT}",
            bg=WINDOW_BG,
            fg="#8a8a8a",
            font=("Consolas", 8),
        ).pack(side="right")

        log_frame = ttk.LabelFrame(container, text="运行日志")
        log_frame.pack(fill="both", expand=True, pady=(12, 0))
        self.log_text = tk.Text(log_frame, height=12, wrap="word", state="disabled", font=("Consolas", 10))
        self.log_text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)
        self.log_text.configure(yscrollcommand=scroll.set)

        self.log("已加载配置。")

    def _make_compact_entry(self, master, variable: tk.StringVar, width: int):
        entry = tk.Entry(
            master,
            textvariable=variable,
            width=width,
            justify="center",
            bg=ENTRY_BG,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=ENTRY_BORDER,
            highlightcolor=ENTRY_BORDER,
            font=("Consolas", 12),
        )
        return entry

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def log(self, message: str) -> None:
        self.ui_queue.put(("log", message))

    def _set_form_from_config(self, config: ScriptConfig) -> None:
        self.first_loop_delay_var.set(format_number(config.first_loop_delay))
        self.tab_delay_var.set(format_number(config.tab_delay))
        self.bow_key_delay_var.set(format_number(config.bow_key_delay))
        self.before_mount_delay_var.set(format_number(config.before_mount_delay))
        self.ride_duration_var.set(format_number(config.ride_duration))
        self.between_small_cycles_delay_var.set(format_number(config.between_small_cycles_delay))
        self.between_big_cycles_wait_var.set(format_number(config.between_big_cycles_wait))
        self.jitter_min_ms_var.set(str(config.jitter_min_ms))
        self.jitter_max_ms_var.set(str(config.jitter_max_ms))
        self.salute_key_var.set(config.salute_key)
        self.small_cycle_count_var.set(str(config.small_cycle_count))
        self.enable_daily_skip_var.set(config.enable_daily_skip)

    def _read_config_from_form(self) -> ScriptConfig:
        data = {
            "first_loop_delay": self.first_loop_delay_var.get().strip(),
            "tab_delay": self.tab_delay_var.get().strip(),
            "bow_key_delay": self.bow_key_delay_var.get().strip(),
            "before_mount_delay": self.before_mount_delay_var.get().strip(),
            "ride_duration": self.ride_duration_var.get().strip(),
            "between_small_cycles_delay": self.between_small_cycles_delay_var.get().strip(),
            "between_big_cycles_wait": self.between_big_cycles_wait_var.get().strip(),
            "jitter_min_ms": self.jitter_min_ms_var.get().strip(),
            "jitter_max_ms": self.jitter_max_ms_var.get().strip(),
            "salute_key": self.salute_key_var.get().strip(),
            "small_cycle_count": self.small_cycle_count_var.get().strip(),
            "enable_daily_skip": self.enable_daily_skip_var.get(),
        }
        return ScriptConfig.from_dict(data)

    def _on_runner_state_change(self, state: str) -> None:
        self.ui_queue.put(("state", state))

    def _apply_runner_state(self, state: str) -> None:
        if state == "running":
            self.status_var.set("运行中")
            self.start_button.configure(text="启动", state="disabled")
            self.pause_button.configure(text="暂停/继续", state="normal")
            self.stop_button.configure(state="normal")
        elif state == "paused":
            self.status_var.set("已暂停")
            self.start_button.configure(text="继续", state="normal")
            self.pause_button.configure(text="暂停/继续", state="normal")
            self.stop_button.configure(state="normal")

    def save_current_settings(self) -> None:
        try:
            config = self._read_config_from_form()
            save_config(config)
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"参数格式不正确：{exc}")
            return
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"保存失败：{exc}")
            return
        self.log(f"设置已保存到 {CONFIG_PATH.name}。")

    def restore_defaults(self) -> None:
        config = ScriptConfig.from_dict({})
        self._set_form_from_config(config)
        try:
            save_config(config)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"默认值已恢复，但写入配置失败：{exc}")
            return
        self.log("已恢复自动鞠躬骑乘.Q 的默认设置，并写入配置文件。")

    def start_or_resume(self) -> None:
        if self.runner and self.runner.is_alive():
            if self.runner.is_paused():
                self.runner.resume()
                self.log("已继续运行。")
            return

        try:
            config = self._read_config_from_form()
            save_config(config)
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"参数格式不正确：{exc}")
            return
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"保存配置失败：{exc}")
            return

        self.runner = AutomationRunner(
            config=config,
            log_callback=self.log,
            finish_callback=self._on_runner_finished,
            state_callback=self._on_runner_state_change,
        )
        self.runner.start()

    def toggle_pause(self) -> None:
        if not (self.runner and self.runner.is_alive()):
            return
        self.runner.toggle_pause()
        if self.runner.is_paused():
            self.log("已暂停。点击继续可恢复。")
        else:
            self.log("已继续运行。")

    def stop(self) -> None:
        if self.runner and self.runner.is_alive():
            self.runner.stop()
            self.status_var.set("停止中")
            self.log("已发送中止指令，等待当前步骤结束。")

    def _on_runner_finished(self) -> None:
        self.ui_queue.put(("finished", None))

    def _process_ui_queue(self) -> None:
        while True:
            try:
                action, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if action == "log":
                self._append_log(payload)
            elif action == "state":
                self._apply_runner_state(payload)
            elif action == "finished":
                self._set_idle_state()

        if not self._closing:
            self.root.after(50, self._process_ui_queue)

    def _set_idle_state(self) -> None:
        self.status_var.set("未运行")
        self.start_button.configure(text="启动", state="normal")
        self.pause_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")
        self.log("脚本已停止。")

    def on_close(self) -> None:
        if self.runner and self.runner.is_alive():
            if not messagebox.askyesno(APP_TITLE, "脚本仍在运行，确定要退出吗？"):
                return
            self.runner.stop()
        try:
            save_config(self._read_config_from_form())
        except (ValueError, OSError):
            pass
        self._closing = True
        self.root.destroy()


def main() -> None:
    set_dpi_awareness()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
