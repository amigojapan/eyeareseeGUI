#!/usr/bin/env python3
from __future__ import annotations

import base64
import html
import json
import os
import queue
import re
import select
import socket
import ssl
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


try:
    from PySide6.QtCore import Qt, QEvent, QTimer, QThread, QStringListModel, QAbstractListModel, QModelIndex
    from PySide6.QtGui import QColor, QFont, QTextCursor, QTextOption, QBrush, QTextCharFormat, QTextDocument
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListView,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QPlainTextEdit,
        QSplitter,
        QTextBrowser,
        QTextEdit,
        QVBoxLayout,
        QWidget,
        QInputDialog,
        QFontComboBox,
        QSpinBox,
        QDialog,
        QDialogButtonBox,
        QCheckBox
    )
    BINDING = "PySide6"
except Exception:
    try:
        from PyQt6.QtCore import Qt, QEvent, QTimer, QThread, QStringListModel, QAbstractListModel, QModelIndex
        from PyQt6.QtGui import QColor, QFont, QTextCursor, QTextOption, QBrush, QTextCharFormat, QTextDocument
        from PyQt6.QtWidgets import (
            QApplication,
            QComboBox,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListView,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QPlainTextEdit,
            QSplitter,
            QTextBrowser,
            QTextEdit,
            QVBoxLayout,
            QWidget,
            QInputDialog,
            QFontComboBox,
            QSpinBox,
            QDialog,
            QDialogButtonBox,
            QCheckBox
        )
        from PyQt6.QtCore import QStringListModel
        BINDING = "PyQt6"
    except Exception:
        try:
            from PyQt5.QtCore import Qt, QEvent, QTimer, QThread, QStringListModel, QAbstractListModel, QModelIndex
            from PyQt5.QtGui import QColor, QFont, QTextCursor, QTextOption, QBrush, QTextCharFormat, QTextDocument
            from PyQt5.QtWidgets import (
                QApplication,
                QComboBox,
                QFrame,
                QHBoxLayout,
                QLabel,
                QLineEdit,
                QListView,
                QMainWindow,
                QMessageBox,
                QPushButton,
                QPlainTextEdit,
                QSplitter,
                QTextBrowser,
                QTextEdit,
                QVBoxLayout,
                QWidget,
                QInputDialog,
                QFontComboBox,
                QSpinBox,
                QDialog,
                QDialogButtonBox,
                QCheckBox
            )
            BINDING = "PyQt5"
        except Exception:
            BINDING = None
from qt_material import apply_stylesheet


DEFAULT_SERVER = "irc.libera.chat"
DEFAULT_PORT = 6697
DEFAULT_NICK = ""
DEFAULT_CHANNEL = "#eyearesee"

SCRIPT_DIR = Path(__file__).resolve().parent
HISTORY_PATH = SCRIPT_DIR / "connection_history.json"
SETTINGS_PATH = SCRIPT_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "font_family": "monospace",
    "font_size": 12,
    "theme": "dark_teal.xml",
    "highlight_on_mention": True,
    "trust_all_ssl": False,
    "server_password": ""
}

def load_settings() -> dict:
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return {**DEFAULT_SETTINGS, **data}
    except Exception:
        pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass

# mIRC color support
IRC_COLOR_RE = re.compile(r'\x03(\d{1,2})(?:,(\d{1,2}))?')
IRC_CTLS_RE = re.compile(r"\x03(?:\d{1,2}(?:,\d{1,2})?)?|[\x02\x0F\x16\x1D\x1F]")

IRC_URL_RE = re.compile(r'https?://[^\s\x00-\x1f\x7f<>"\']+')

MIRC_COLOR_MAP = {
    0: "#FFFFFF", 1: "#000000", 2: "#00007F", 3: "#009300", 4: "#FF0000",
    5: "#7F0000", 6: "#9C009C", 7: "#FC7F00", 8: "#FFFF00", 9: "#00FC00",
    10: "#009393", 11: "#00FFFF", 12: "#0000FC", 13: "#FF00FF", 14: "#7F7F7F",
    15: "#D2D2D2", 16: "#470000", 17: "#472100", 18: "#474700", 19: "#004700",
    20: "#00474F", 21: "#000047", 22: "#472147", 23: "#472F00", 24: "#004F00",
    25: "#004F4F", 26: "#00004F", 27: "#4F004F", 28: "#4F4F00", 29: "#004F4F",
}

def mirc_to_html(text: str) -> str:
    def repl(match):
        fg = int(match.group(1)) if match.group(1) else None
        bg = int(match.group(2)) if match.group(2) else None
        style = ""
        if fg is not None and fg in MIRC_COLOR_MAP:
            style += f"color:{MIRC_COLOR_MAP[fg]};"
        if bg is not None and bg in MIRC_COLOR_MAP:
            style += f"background-color:{MIRC_COLOR_MAP[bg]};"
        if style:
            return f'<span style="{style}">'
        return ''
    text = IRC_COLOR_RE.sub(repl, text)
    text = text.replace("\x02", "<b>").replace("\x0F", "</b></i></u><span>")
    text = text.replace("\x1D", "<i>").replace("\x1F", "<u>")
    text = text.replace("\x16", "")
    text = re.sub(r'\x03', '</span>', text)
    return text

def make_urls_clickable(text: str) -> str:
    def repl(match):
        url = match.group(0)
        return f'<a href="{url}">{url}</a>'
    return IRC_URL_RE.sub(repl, text)

def _ts() -> str:
    return time.strftime("[%H:%M]")

def load_history() -> List[dict]:
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception:
        pass
    return []

def save_history(items: List[dict]) -> None:
    try:
        HISTORY_PATH.write_text(json.dumps(items[-20:], indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def parse_server_time(ts: str) -> str:
    try:
        from datetime import datetime, timezone
        s = ts.rstrip("Z")
        fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in s else "%Y-%m-%dT%H:%M:%S"
        dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).astimezone(tz=None)
        return dt.strftime("[%H:%M]")
    except Exception:
        return _ts()

def strip_irc_formatting(text: str) -> str:
    return IRC_CTLS_RE.sub("", text)

def _parse_irc_line(raw: str):
    if not raw:
        return None
    tags: dict = {}
    if raw.startswith("@"):
        try:
            tag_str, raw = raw[1:].split(" ", 1)
        except ValueError:
            return None
        for t in tag_str.split(";"):
            if not t:
                continue
            if "=" in t:
                k, v = t.split("=", 1)
                out = []
                it = iter(v)
                for c in it:
                    if c == "\\":
                        n = next(it, "")
                        if n == ":":
                            out.append(";")
                        elif n == "s":
                            out.append(" ")
                        elif n == "r":
                            out.append("\r")
                        elif n == "n":
                            out.append("\n")
                        elif n == "\\":
                            out.append("\\")
                        else:
                            out.append(n)
                    else:
                        out.append(c)
                tags[k.lower()] = "".join(out)
            else:
                tags[t.lower()] = True
    prefix = ""
    if raw.startswith(":"):
        try:
            prefix, raw = raw[1:].split(" ", 1)
        except ValueError:
            return None
    if " :" in raw:
        head, tail = raw.split(" :", 1)
        parts = head.split()
        if tail:
            parts.append(tail)
    else:
        parts = raw.split()
    if not parts:
        return None
    cmd = parts[0].upper()
    params = parts[1:]
    nick = prefix.split("!", 1)[0] if prefix else ""
    return cmd, nick, params, prefix, tags

def _html_span(cls: str, text: str) -> str:
    escaped = html.escape(text)
    styles = {
        "ts": "color:#8aa0b8;",
        "nick": "color:#8fd3ff; font-weight:700;",
        "selfmsg": "background-color:#063b23; color:#7dffb2; font-weight:800; padding:0 5px; border-radius:4px;",
        "directmsg": "background-color:#3a0b56; color:#ff77ff; font-weight:800; padding:0 5px; border-radius:4px;",
        "mentionmsg": "background-color:#463b00; color:#ffe86a; font-weight:800; padding:0 5px; border-radius:4px;",
        "actionmsg": "color:#64f0ff; font-style:italic;",
        "statusmsg": "color:#c6d0e2;",
        "noticemsg": "color:#ff9ee8;",
        "topicmsg": "color:#65d6ff;",
        "highlight": "color:#ff4444; font-weight:bold;",
    }
    style = styles.get(cls, "")
    if style:
        return f'<span style="{style}">{escaped}</span>'
    return f'<span>{escaped}</span>'

def irc_inline_to_html(text: str) -> str:
    text = mirc_to_html(text)
    text = html.escape(text)  
    return text

def _network_key(server: str, port: int) -> str:
    return f"{server}:{port}"

def _normalize_windows(items: List[str]) -> List[str]:
    ordered: List[str] = ["*status*"]
    seen = {"*status*"}
    for name in items:
        if not name:
            continue
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered

class ChannelListModel(QAbstractListModel):
    def __init__(self, items: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self._items: List[str] = _normalize_windows(items or [])
        self._current: str = "*status*"
        self._highlighted: set[str] = set()

    def set_items(self, items: List[str]) -> None:
        self.beginResetModel()
        self._items = _normalize_windows(items)
        self.endResetModel()

    def set_current(self, current: str) -> None:
        self._current = current or "*status*"
        if self._items:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._items) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.ForegroundRole])

    def set_highlighted(self, highlighted: set[str]) -> None:
        self._highlighted = set(highlighted or set())
        if self._items:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._items) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.ForegroundRole])

    def add_or_move(self, name: str) -> None:
        if not name or name == "*status*" or name in self._items:
            return
        self.beginResetModel()
        self._items = _normalize_windows(self._items + [name])
        self.endResetModel()

    def remove(self, name: str) -> None:
        if not name or name == "*status*" or name not in self._items:
            return
        self.beginResetModel()
        self._items = [x for x in self._items if x != name]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index or not index.isValid():
            return None

        row = index.row()
        if row < 0 or row >= len(self._items):
            return None

        name = self._items[row]

        if role == Qt.DisplayRole:
            return name

        if role == Qt.ForegroundRole:
            if name in self._highlighted:
                return QBrush(QColor("red"))  
            if name == "*status*":
                return QBrush(QColor("#8aa0b8"))
            if name == self._current:
                return QBrush(QColor("#8fd3ff"))

        return None


class IRCClientThread(threading.Thread):

    WANT_CAPS = (
        "away-notify",
        "multi-prefix",
        "account-notify",
        "extended-join",
        "chghost",
        "server-time",
        "echo-message",
        "userhost-in-names",
        "message-tags",
        "batch",
        "labeled-response",
        "invite-notify",
        "account-tag",
        "standard-replies",
        "setname",
        "chathistory",
        "draft/chathistory",
        "monitor",
        "cap-notify",
        "draft/typing",
        "draft/event-playback",
        "draft/read-marker",
        "knock",
    )

    def __init__(self, server: str, port: int, nick: str, password: str, use_ssl: bool, outq: queue.Queue, eventq: queue.Queue, trust_all_ssl: bool = False, server_pass: str = ""):
        super().__init__(daemon=True)
        self.server = server
        self.port = port
        self.nick = nick
        self.password = password # This is SASL / NickServ password[cite: 4]
        self.server_pass = server_pass # This is IRC PASS for ZNC[cite: 4]
        self.use_ssl = use_ssl
        self.trust_all_ssl = trust_all_ssl
        self.outq = outq
        self.eventq = eventq
        self.stop_event = threading.Event()
        self.sock: Optional[socket.socket] = None
        self.buffer = b""
        self.current_target: Optional[str] = None
        self.server_name = server
        self._identified = False
        self._desired_nick = nick
        self._label_seq = 0
        self._sent_labels: set[str] = set()
        self._active_caps: set[str] = set()
        self._cap_ls_caps: set[str] = set()
        self._cap_ls_values: dict[str, str] = {}
        self._cap_req_queue: List[str] = []
        self._batch_buffer: dict[str, list] = {}
        self._batch_types: dict[str, str] = {}
        self._current_batch_is_replay = False
        self._chathistory_cap = ""
        self._isupport: dict[str, object] = {}
        self._current_msg_tags: dict = {}
        self._pending_names: Dict[str, set] = {}
        self._last_pong = time.monotonic()
        self._reader_timeout = 500
        self._typing_last_sent: Dict[str, float] = {}

    def emit(self, kind: str, **payload):
        payload["type"] = kind
        self.eventq.put(payload)

    def send_raw(self, line: str) -> None:
        line = line.replace("\r", "").replace("\n", "").replace("\x00", "")
        if line:
            self.outq.put(line)

    def send_tagged(self, tags: dict, line: str) -> None:
        if tags and "message-tags" in self._active_caps:
            def esc(v: str) -> str:
                return (
                    str(v)
                    .replace("\\", "\\\\")
                    .replace(";", "\\:")
                    .replace(" ", "\\s")
                    .replace("\r", "\\r")
                    .replace("\n", "\\n")
                )

            tag_str = ";".join(f"{k}={esc(v)}" if v else k for k, v in tags.items())
            self.send_raw(f"@{tag_str} {line}")
        else:
            self.send_raw(line)

    def _next_label(self) -> str:
        self._label_seq += 1
        return f"eyrc-{self._label_seq}"

    def _ts_from_tags(self) -> str:
        t = self._current_msg_tags.get("time")
        return parse_server_time(t) if t else _ts()

    def _irc_lower(self, s: str) -> str:
        mapping = str(self._isupport.get("CASEMAPPING", "rfc1459")).lower()
        s = s.lower()
        if mapping == "ascii":
            return s
        if mapping == "strict-rfc1459":
            return s.translate(str.maketrans(r"\[]", r"|{}"))
        return s.translate(str.maketrans(r"[\\]^", r"{|}~"))

    def _is_chan(self, name: str) -> str:
        chantypes = str(self._isupport.get("CHANTYPES", "#&"))
        return bool(name) and name[0] in chantypes

    def _prefix_chars(self) -> str:
        prefix = str(self._isupport.get("PREFIX", "(qaohv)~&@%+"))
        m = re.match(r"^\(([^)]+)\)(.+)$", prefix)
        return m.group(2) if m else "~&@%+"

    def _request_caps(self):
        want = [c for c in self.WANT_CAPS if c in self._cap_ls_caps]
        if "sasl" in self._cap_ls_caps and self.password:
            sasl_val = self._cap_ls_values.get("sasl", "")
            if not sasl_val or "PLAIN" in sasl_val.upper().split(","):
                want.append("sasl")
        self.send_raw(f"CAP REQ :{' '.join(want)}" if want else "CAP END")
        self._cap_ls_caps.clear()

    def _flush_cap_req_queue(self):
        if self._cap_req_queue:
            self.send_raw(f"CAP REQ :{self._cap_req_queue.pop(0)}")
        else:
            self.send_raw("CAP END")

    def connect(self) -> None:
        raw = socket.create_connection((self.server, self.port), timeout=30)
        raw.settimeout(self._reader_timeout)
        if self.use_ssl:
            ctx = ssl.create_default_context()
            if self.trust_all_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            self.sock = ctx.wrap_socket(raw, server_hostname=self.server)
            self.sock.settimeout(self._reader_timeout)
        else:
            self.sock = raw
        
        # SEND IRC PASS FOR ZNC BEFORE ANYTHING ELSE[cite: 4]
        if self.server_pass:
            self.send_raw(f"PASS {self.server_pass}")
            
        self.send_raw("CAP LS 302")
        self.send_raw(f"NICK {self.nick}")
        self.send_raw(f"USER {self.nick} 0 * :{self.nick}")
        self.emit("status", text=f"Connected socket opened to {self.server}:{self.port} ({'SSL' if self.use_ssl else 'plain'})")

    def disconnect(self, reason: str = "Client exiting") -> None:
        try:
            self.send_raw(f"QUIT :{reason}")
        except Exception:
            pass
        self.stop_event.set()

    def run(self) -> None:
        try:
            self.connect()
            while not self.stop_event.is_set():
                self._drain_outgoing()
                self._read_incoming()
        except Exception as exc:
            self.emit("status", text=f"Connection error: {exc}")
        finally:
            try:
                if self.sock:
                    self.sock.close()
            except Exception:
                pass
            self.emit("disconnected", text="Disconnected")

    def _drain_outgoing(self) -> None:
        while True:
            try:
                line = self.outq.get_nowait()
            except queue.Empty:
                return
            if self.sock is None:
                continue
            try:
                self.sock.sendall((line + "\r\n").encode("utf-8", errors="replace"))
            except Exception as exc:
                self.emit("status", text=f"Send failed: {exc}")

    def _read_incoming(self) -> None:
        if self.sock is None:
            return
        try:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("server closed the connection")
            self.buffer += chunk
        except socket.timeout:
            return
        except Exception as exc:
            raise exc
        while b"\r\n" in self.buffer:
            raw, self.buffer = self.buffer.split(b"\r\n", 1)
            line = raw.decode("utf-8", errors="replace")
            self._handle_line(line)

    def _handle_line(self, raw: str) -> None:
        parsed = _parse_irc_line(raw)
        if parsed is None:
            return
        cmd, nick, params, prefix, tags = parsed
        self._current_msg_tags = tags
        batch_ref = tags.get("batch") if isinstance(tags.get("batch"), str) else ""
        if batch_ref and batch_ref in self._batch_buffer:
            self._batch_buffer[batch_ref].append((cmd, nick, params, prefix, tags))
            return
        handler = getattr(self, f"_irc_{cmd.lower()}", None)
        if handler:
            handler(nick, params, prefix)
        elif cmd in {"002", "003", "004", "005", "375", "372", "376"}:
            self.emit("status", text=f"{cmd} {' '.join(params)}")

    def _irc_ping(self, nick, params, prefix):
        self.send_raw(f"PONG :{params[0] if params else 'keepalive'}")

    def _irc_pong(self, nick, params, prefix):
        self._last_pong = time.monotonic()

    def _irc_cap(self, nick, params, prefix):
        subcmd = params[1].upper() if len(params) > 1 else ""
        if subcmd == "LS":
            more = len(params) > 2 and params[2] == "*"
            for raw_cap in (params[-1] if params else "").split():
                if "=" in raw_cap:
                    cname, cval = raw_cap.split("=", 1)
                else:
                    cname, cval = raw_cap, ""
                cname = cname.lower()
                self._cap_ls_caps.add(cname)
                if cval:
                    self._cap_ls_values[cname] = cval
            if not more:
                if "chathistory" in self._cap_ls_caps:
                    self._chathistory_cap = "chathistory"
                elif "draft/chathistory" in self._cap_ls_caps:
                    self._chathistory_cap = "draft/chathistory"
                self._request_caps()
        elif subcmd == "ACK":
            acked = set((params[-1] if params else "").lower().split())
            self._active_caps |= acked
            if "sasl" in acked:
                self.send_raw("AUTHENTICATE PLAIN")
            else:
                self._flush_cap_req_queue()
        elif subcmd == "NAK":
            nak_caps = (params[-1] if params else "").lower().split()
            if len(nak_caps) > 1:
                self._cap_req_queue.extend(nak_caps)
            self._flush_cap_req_queue()
        elif subcmd == "NEW":
            new_avail: dict[str, str] = {}
            for raw_cap in (params[-1] if params else "").split():
                if "=" in raw_cap:
                    cname, cval = raw_cap.split("=", 1)
                else:
                    cname, cval = raw_cap, ""
                new_avail[cname.lower()] = cval
                if cval:
                    self._cap_ls_values[cname.lower()] = cval
            if "sts" in new_avail and not self.use_ssl:
                self.emit("status", text=f"[STS] {self.server} advertised TLS-only policy")
            want = [c for c in self.WANT_CAPS if c in new_avail and c not in self._active_caps]
            if want:
                self.send_raw(f"CAP REQ :{' '.join(want)}")
        elif subcmd == "DEL":
            removed = {c.lower() for c in (params[-1] if params else "").split()}
            self._active_caps -= removed
            self.emit("status", text=f"[cap] server withdrew: {' '.join(sorted(removed))}")

    def _irc_authenticate(self, nick, params, prefix):
        if params and params[0] == "+":
            raw = f"{self.nick}\0{self.nick}\0{self.password}".encode()
            payload = base64.b64encode(raw).decode()
            for i in range(0, len(payload), 400):
                self.send_raw(f"AUTHENTICATE {payload[i:i+400]}")
            if len(payload) % 400 == 0:
                self.send_raw("AUTHENTICATE +")

    def _irc_903(self, nick, params, prefix):
        self._identified = True
        self.emit("status", text="SASL authentication successful")
        self.send_raw("CAP END")

    def _irc_904(self, nick, params, prefix):
        self.emit("status", text="SASL authentication failed, falling back to NickServ")
        self.send_raw("AUTHENTICATE *")
        self.send_raw("CAP END")

    def _irc_902(self, nick, params, prefix):
        self.emit("status", text="SASL failed: nick locked or registered")
        self.send_raw("AUTHENTICATE *")
        self.send_raw("CAP END")

    def _irc_906(self, nick, params, prefix):
        self.emit("status", text="SASL authentication aborted")
        self.send_raw("CAP END")

    def _irc_907(self, nick, params, prefix):
        self.emit("status", text="Already authenticated via SASL")
        self.send_raw("CAP END")

    def _irc_908(self, nick, params, prefix):
        mechs = params[-1] if params else ""
        self.emit("status", text=f"SASL mechanisms available: {mechs}")
        if "PLAIN" not in mechs.upper().split(","):
            self.send_raw("AUTHENTICATE *")
            self.send_raw("CAP END")

    def _irc_001(self, nick, params, prefix):
        self.emit("status", text="Registration complete")
        self.emit("connected", nick=self.nick)
        if self.password and not self._identified:
            self.send_raw(f"PRIVMSG NickServ :IDENTIFY {self.password}")
        if DEFAULT_CHANNEL:
            self.send_raw(f"JOIN {DEFAULT_CHANNEL}")

    def _irc_005(self, nick, params, prefix):
        for token in params[1:-1]:
            if not token:
                continue
            if token.startswith("-"):
                self._isupport.pop(token[1:], None)
            elif "=" in token:
                k, v = token.split("=", 1)
                self._isupport[k] = v
            else:
                self._isupport[token] = True
        if "NETWORK" in self._isupport:
            self.emit("status", text=f"Network: {self._isupport['NETWORK']}")

    def _irc_353(self, nick, params, prefix):
        if len(params) < 4:
            return
        channel = params[2]
        users = []
        for entry in params[3].split():
            entry = entry.lstrip(self._prefix_chars())
            if "!" in entry:
                entry = entry.split("!", 1)[0]
            if entry:
                users.append(entry)
        if not users:
            return
        self._pending_names.setdefault(channel, set()).update(users)
        self.emit("names", channel=channel, users=users)

    def _irc_366(self, nick, params, prefix):
        if not params:
            return
        channel = params[1] if len(params) > 1 else params[0]
        all_users = sorted(self._pending_names.pop(channel, set()), key=str.lower)
        if all_users:
            self.emit("names", channel=channel, users=all_users, final=True)
        self.emit("status", text=f"End of NAMES for {channel}")

    def _irc_433(self, nick, params, prefix):
        self.nick = f"{self.nick}_"
        self.emit("status", text=f"Nick in use; trying {self.nick}")
        self.send_raw(f"NICK {self.nick}")

    def _irc_join(self, nick, params, prefix):
        if not params:
            return
        channel = params[0]
        account = params[1] if len(params) > 1 else ""
        realname = params[2] if len(params) > 2 else ""
        if account == "*":
            account = ""
        self.emit("join", nick=nick, channel=channel, account=account, realname=realname, self_join=(nick == self.nick), ts=_ts())

    def _irc_part(self, nick, params, prefix):
        if params:
            self.emit("part", nick=nick, channel=params[0], reason=params[1] if len(params) > 1 else "", ts=_ts())

    def _irc_quit(self, nick, params, prefix):
        self.emit("quit", nick=nick, reason=params[-1] if params else "", ts=_ts())

    def _irc_kick(self, nick, params, prefix):
        if params:
            self.emit("kick", channel=params[0], target=params[1] if len(params) > 1 else "", reason=params[2] if len(params) > 2 else "", ts=_ts())

    def _irc_topic(self, nick, params, prefix):
        if params:
            self.emit("topic", channel=params[0], topic=params[-1] if len(params) > 1 else "", nick=nick, ts=_ts())

    def _irc_332(self, nick, params, prefix):
        if len(params) >= 3:
            self.emit("topic", channel=params[1], topic=params[2], nick="server", ts=_ts())

    def _irc_333(self, nick, params, prefix):
        if len(params) >= 4:
            self.emit("status", text=f"Topic set by {params[2]} at {params[3]}")

    def _irc_nick(self, nick, params, prefix):
        if params:
            newnick = params[0]
            self.emit("nick", old=nick, new=newnick, ts=_ts())
            if nick == self.nick:
                self.nick = newnick

    def _irc_mode(self, nick, params, prefix):
        self.emit("status", text=f"MODE {' '.join(params)}")

    def _irc_notice(self, nick, params, prefix):
        if not params:
            return
        target = params[0]
        text = params[-1]
        self.emit("notice", nick=nick, target=target, text=text, ts=_ts(), direct=(target == self.nick or target == nick))

    def _irc_privmsg(self, nick, params, prefix):
        if len(params) < 2:
            return
        target = params[0]
        text = params[1]
        if nick == self.nick and not self._current_batch_is_replay:
            if "labeled-response" in self._active_caps:
                label = self._current_msg_tags.get("label", "")
                if label in self._sent_labels:
                    self._sent_labels.discard(label)
                    return
            elif "echo-message" in self._active_caps:
                return
        is_action = text.startswith("\x01ACTION ") and text.endswith("\x01")
        if is_action:
            text = text[len("\x01ACTION "):-1]
        direct = target == self.nick
        mention = self.nick.lower() in text.lower() and not direct
        self.emit(
            "message",
            nick=nick,
            target=target,
            text=text,
            ts=self._ts_from_tags(),
            action=is_action,
            self_msg=(nick == self.nick),
            direct=direct,
            mention=mention,
        )

    def _irc_batch(self, nick, params, prefix):
        if not params:
            return
        ref_dir = params[0]
        if ref_dir.startswith("+"):
            ref = ref_dir[1:]
            self._batch_buffer[ref] = []
            self._batch_types[ref] = params[1] if len(params) > 1 else ""
        elif ref_dir.startswith("-"):
            ref = ref_dir[1:]
            buffered = self._batch_buffer.pop(ref, [])
            batch_type = self._batch_types.pop(ref, "")
            if batch_type == "draft/multiline" and buffered:
                first_pm = next((x for x in buffered if x[0] == "PRIVMSG"), None)
                if first_pm:
                    _, bnick, bparams, _, btags = first_pm
                    target = bparams[0] if len(bparams) > 0 else ""
                    merged = "\n".join(x[2][1] for x in buffered if x[0] == "PRIVMSG" and len(x[2]) > 1)
                    self.emit("message", nick=bnick, target=target, text=merged, ts=_ts(), action=False, self_msg=(bnick == self.nick), direct=(target == self.nick), mention=(self.nick.lower() in merged.lower()))

    def _irc_tagmsg(self, nick, params, prefix):
        if not params:
            return
        target = params[0]
        state = self._current_msg_tags.get("+typing") or self._current_msg_tags.get("typing") or self._current_msg_tags.get("+typing".lower())
        if isinstance(state, str) and state:
            self.emit("typing", channel=target, nick=nick, state=state, ts=_ts())

    def _irc_301(self, nick, params, prefix):
        if len(params) >= 2:
            self.emit("status", text=f"Away: {' '.join(params[1:])}")

    def _irc_305(self, nick, params, prefix):
        self.emit("status", text="You are no longer marked as away")

    def _irc_306(self, nick, params, prefix):
        self.emit("status", text="You have been marked as away")

    def _irc_error(self, nick, params, prefix):
        self.emit("status", text=f"ERROR {' '.join(params)}")

    def cmd_join(self, channel: str):
        self.send_raw(f"JOIN {channel}")

    def cmd_part(self, channel: str):
        self.send_raw(f"PART {channel}")

    def cmd_msg(self, target: str, text: str):
        if "labeled-response" in self._active_caps:
            label = self._next_label()
            self._sent_labels.add(label)
            self.send_tagged({"label": label}, f"PRIVMSG {target} :{text}")
        else:
            self.send_raw(f"PRIVMSG {target} :{text}")

    def cmd_me(self, target: str, text: str):
        self.cmd_msg(target, f"\x01ACTION {text}\x01")

    def cmd_notice(self, target: str, text: str):
        self.send_raw(f"NOTICE {target} :{text}")

    def cmd_raw(self, line: str):
        self.send_raw(line)

    def cmd_nick(self, nick: str):
        self.send_raw(f"NICK {nick}")

    def cmd_quit(self, reason: str = "Leaving"):
        self.disconnect(reason)

    def send_typing(self, target: str, state: str = "active"):
        if "message-tags" not in self._active_caps:
            return
            
        now = time.monotonic()
        last = self._typing_last_sent.get(target, 0.0)
        
        if now - last < 3.0 and state != "done":
            return
            
        self._typing_last_sent[target] = now
        
        try:
            self.send_tagged({"+typing": state}, f"TAGMSG {target}")
        except Exception:
            pass

class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = current_settings.copy()

        layout = QVBoxLayout(self)

        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Font:"))
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(self.settings.get("font_family", "monospace")))
        font_layout.addWidget(self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 72)
        self.size_spin.setValue(self.settings.get("font_size", 12))
        font_layout.addWidget(self.size_spin)
        layout.addLayout(font_layout)

        self.preview_label = QLabel("Font Preview: The quick brown fox jumps over the lazy dog.")
        layout.addWidget(self.preview_label)

        self.font_combo.currentFontChanged.connect(self.update_preview)
        self.size_spin.valueChanged.connect(self.update_preview)
        self.update_preview()

        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Mode", "Light Mode"])
        self.theme_combo.setCurrentIndex(0 if "dark" in self.settings.get("theme", "dark_teal.xml") else 1)
        theme_layout.addWidget(self.theme_combo)
        layout.addLayout(theme_layout)

        self.chk_highlight = QCheckBox("Highlight list box on mention when window is inactive")
        self.chk_highlight.setChecked(self.settings.get("highlight_on_mention", True))
        layout.addWidget(self.chk_highlight)

        self.chk_trust_ssl = QCheckBox("Trust invalid/self-signed SSL certificates")
        self.chk_trust_ssl.setChecked(self.settings.get("trust_all_ssl", False))
        layout.addWidget(self.chk_trust_ssl)

        # SERVER PASSWORD FIELD FOR ZNC[cite: 4]
        server_pass_layout = QHBoxLayout()
        server_pass_layout.addWidget(QLabel("Server Password (IRC PASS):"))
        self.txtServerPass = QLineEdit(self.settings.get("server_password", ""))
        self.txtServerPass.setPlaceholderText("username:password")
        self.txtServerPass.setEchoMode(QLineEdit.EchoMode.Password if hasattr(QLineEdit, "EchoMode") else QLineEdit.Password)
        server_pass_layout.addWidget(self.txtServerPass)
        layout.addLayout(server_pass_layout)

        try:
            btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        except AttributeError:
            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def update_preview(self):
        font = self.font_combo.currentFont()
        font.setPointSize(self.size_spin.value())
        self.preview_label.setFont(font)

    def get_settings(self):
        self.settings["font_family"] = self.font_combo.currentFont().family()
        self.settings["font_size"] = self.size_spin.value()
        self.settings["theme"] = "dark_teal.xml" if self.theme_combo.currentIndex() == 0 else "light_teal.xml"
        self.settings["highlight_on_mention"] = self.chk_highlight.isChecked()
        self.settings["trust_all_ssl"] = self.chk_trust_ssl.isChecked()
        self.settings["server_password"] = self.txtServerPass.text().strip() # Save IRC PASS[cite: 4]
        return self.settings

class IRCMainWindow(QMainWindow):
    _instances: List["IRCMainWindow"] = []
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.setWindowTitle("eye are see GUI")
        self.resize(1100, 720)
        self.eventq: queue.Queue = queue.Queue()
        self.outq: queue.Queue = queue.Queue()
        self.worker: Optional[IRCClientThread] = None
        self.connected = False
        self.current_target = "*status*"
        self.channels_users: Dict[str, set] = {DEFAULT_CHANNEL: set()}
        self.channel_logs: Dict[str, list] = {}
        self.open_windows: List[str] = ["*status*"]
        self._highlighted_windows: set[str] = set()
        self._joined_channels: set[str] = set()
        self._pending_autojoin: List[str] = []
        self._history = load_history()
        self._completion_state: Optional[Dict] = None
        self._presence_summaries: Dict[str, Dict[str, object]] = {}
        self._typing_state: Dict[str, set] = {}
        self._typing_last_sent: Dict[str, float] = {}
        self._typing_timer: Optional[QTimer] = None
        self._pending_self_parts: set[str] = set()
        
        # Input History State
        self._input_history: List[str] = []
        self._input_history_index: int = 0
        self._current_typing_buffer: str = ""

        self._build_ui()
        self._apply_settings_ui()
        self._load_history_combo()
        self._append_status("Ready.")
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self.poll_events)
        self._poll_timer.start(50)

        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(self._typing_pause_tick)

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.frmLogin = QFrame(central)
        self.frmLogin.setFrameShape(QFrame.Shape.StyledPanel if hasattr(QFrame, "Shape") else QFrame.StyledPanel)
        top = QHBoxLayout(self.frmLogin)
        top.setContentsMargins(8, 8, 8, 8)
        top.setSpacing(6)

        self.txtServer = QPlainTextEdit(DEFAULT_SERVER)
        self.txtServer.setStyleSheet('font-size: 8px')
        self.txtServer.setFixedHeight(34)
        self.txtServer.setToolTip("Server")
        self.txtPort = QPlainTextEdit(str(DEFAULT_PORT))
        self.txtPort.setStyleSheet('font-size: 8px')
        self.txtPort.setFixedHeight(34)
        self.txtPort.setToolTip("Port")
        self.txtNick = QTextEdit(DEFAULT_NICK)
        self.txtNick.setFixedHeight(34)
        self.txtNick.setToolTip("Nick")
        self.txtNick.setPlaceholderText("Nick")
        
        self.txtPW = QLineEdit("")
        self.txtPW.setPlaceholderText("password / NickServ")
        self.txtPW.setEchoMode(QLineEdit.EchoMode.Password if hasattr(QLineEdit, "EchoMode") else QLineEdit.Password)
        
        self.chkSSL = QCheckBox("SSL")
        self.chkSSL.setChecked(True)
        
        self.btnConnect = QPushButton("Connect")
        self.btnNewWindow = QPushButton("New Window")
        self.btnSettings = QPushButton("Settings")
        self.cmbConnectionHistory = QComboBox()
        self.cmbConnectionHistory.setToolTip("Connection History")
        self.cmbConnectionHistory.currentIndexChanged.connect(self._apply_history_item)
        self.btnConnect.clicked.connect(self.toggle_connection)
        self.btnNewWindow.clicked.connect(self._spawn_new_window)
        self.btnSettings.clicked.connect(self._open_settings)

        for w in (self.txtServer, self.txtPort, self.txtNick, self.txtPW, self.chkSSL, self.btnConnect, self.cmbConnectionHistory):
            top.addWidget(w)

        root.addWidget(self.frmLogin)

        self.frmChatarea = QFrame(central)
        self.frmChatarea.setFrameShape(QFrame.Shape.StyledPanel if hasattr(QFrame, "Shape") else QFrame.StyledPanel)
        ch = QVBoxLayout(self.frmChatarea)
        ch.setContentsMargins(8, 8, 8, 8)
        ch.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal if hasattr(Qt, "Orientation") else Qt.Horizontal)
        self.textBrowser = QTextBrowser()
        self.textBrowser.setReadOnly(True)
        self.textBrowser.setOpenExternalLinks(True)
        self.textBrowser.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere if hasattr(QTextOption, "WrapMode") else QTextOption.WrapAtWordBoundaryOrAnywhere)

        self.frmUserslist = QFrame()
        self.frmUserslist.setFrameShape(QFrame.Shape.StyledPanel if hasattr(QFrame, "Shape") else QFrame.StyledPanel)
        side = QVBoxLayout(self.frmUserslist)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(4)
        self.lstChannels = QListView()
        self.lstUsers = QListView()
        self._channels_model = ChannelListModel(self.open_windows, self)
        self.lstChannels.setModel(self._channels_model)
        side.addWidget(self.lstChannels, 2)
        side.addWidget(self.lstUsers, 1)

        splitter.addWidget(self.textBrowser)
        splitter.addWidget(self.frmUserslist)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)
        ch.addWidget(splitter)

        self.txtInput = QPlainTextEdit()
        self.txtInput.setPlaceholderText("Type a message or /command and press Enter or start typing a nick and press [TAB] to autocomplete")
        self.txtInput.setFixedHeight(74)
        self.txtInput.installEventFilter(self)
        self.txtInput.textChanged.connect(self._on_input_changed)
        ch.addWidget(self.txtInput)

        root.addWidget(self.frmChatarea, 1)

        bottom_bar = QHBoxLayout()
        self.lblStatus = QLabel("Status: Ready")
        bottom_bar.addWidget(self.lblStatus, 1)
        bottom_bar.addWidget(self.btnSettings)
        bottom_bar.addWidget(self.btnNewWindow)
        bottom_widget = QWidget()
        bottom_widget.setLayout(bottom_bar)
        root.addWidget(bottom_widget)

        self._refresh_channel_list()
        self._refresh_channel_list()

    def _apply_settings_ui(self):
        ff = self.settings.get("font_family", "monospace")
        fs = self.settings.get("font_size", 12)
        self.textBrowser.setStyleSheet(
            f"QTextBrowser {{ background: #111318; color: #f4f7fb; border: 1px solid #2b2f3a; font-family: '{ff}'; font-size: {fs}pt; }}"
            ".ts { color: #8aa0b8; }"
            ".nick { color: #8fd3ff; font-weight: 700; }"
            ".selfmsg { background: #063b23; color: #7dffb2; font-weight: 800; padding: 0 4px; border-radius: 4px; }"
            ".directmsg { background: #3a0b56; color: #ff77ff; font-weight: 800; padding: 0 4px; border-radius: 4px; }"
            ".mentionmsg { background: #463b00; color: #ffe86a; font-weight: 800; padding: 0 4px; border-radius: 4px; }"
            ".actionmsg { color: #64f0ff; font-style: italic; }"
            ".statusmsg { color: #c6d0e2; }"
            ".noticemsg { color: #ff9ee8; }"
            ".topicmsg { color: #65d6ff; }"
            ".highlight { color: #ff4444; font-weight: bold; }"
        )
        font = QFont(ff, fs)
        self.txtInput.setFont(font)

    def _open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            new_settings = dlg.get_settings()
            theme_changed = self.settings.get("theme") != new_settings.get("theme")
            self.settings = new_settings
            save_settings(self.settings)
            self._apply_settings_ui()
            if theme_changed:
                apply_stylesheet(QApplication.instance(), theme=self.settings.get("theme", "dark_teal.xml"))

    def changeEvent(self, event):
        try:
            if event.type() == QEvent.Type.ActivationChange:
                if self.isActiveWindow():
                    self._clear_highlight(self.current_target)
        except AttributeError:
            if event.type() == QEvent.ActivationChange:
                if self.isActiveWindow():
                    self._clear_highlight(self.current_target)
        super().changeEvent(event)

    def _spawn_new_window(self):
        try:
            win = IRCMainWindow()
            win.show()
            IRCMainWindow._instances.append(win)
            try:
                def _cleanup(*_):
                    IRCMainWindow._instances[:] = [w for w in IRCMainWindow._instances if w is not win]
                win.destroyed.connect(_cleanup)
            except Exception:
                pass
        except Exception as exc:
            self._append_status(f"Could not open new window: {exc}")

    def _typing_target(self) -> str:
        return self.current_target or DEFAULT_CHANNEL

    def _on_input_changed(self):
        target = self._typing_target()
        text = self._current_input_text()
        if not self.worker or not target or text.startswith("/"):
            if self.worker:
                self.worker.send_typing(target, "done")
            return
        if not text:
            if self.worker:
                self.worker.send_typing(target, "done")
            return
        if self.worker:
            self.worker.send_typing(target, "active")
        if self._typing_timer is not None:
            self._typing_timer.start(3000)

    def _typing_pause_tick(self):
        text = self._current_input_text()
        target = self._typing_target()
        if self.worker:
            if not text or text.startswith("/"):
                self.worker.send_typing(target, "done")
            else:
                self.worker.send_typing(target, "paused")

    def _invalidate_presence_summary(self, channel: str):
        self._presence_summaries.pop(channel, None)

    def _render_presence_summary(self, kind: str, items: List[str]) -> str:
        ts = _html_span("ts", _ts())
        verbs = {
            "join": "joined",
            "part": "parted",
            "quit": "quit",
        }
        verb = verbs.get(kind, kind)
        body = ", ".join(html.escape(x) for x in items)
        return f'<div>{ts} <span class="statusmsg">{body} {verb}</span></div>'

    def _append_presence_summary(self, channel: str, kind: str, text: str):
        if not channel:
            channel = "*status*"
        self.channel_logs.setdefault(channel, [])
        state = self._presence_summaries.get(channel)
        if state and state.get("kind") == kind:
            items = state.setdefault("items", [])
            if text not in items:
                items.append(text)
            line = self._render_presence_summary(kind, items)
            idx = int(state["index"])
            self.channel_logs[channel][idx] = line
            if channel == self.current_target:
                self._refresh_channel_view()
            return

        line = self._render_presence_summary(kind, [text])
        self.channel_logs[channel].append(line)
        self._presence_summaries[channel] = {"kind": kind, "index": len(self.channel_logs[channel]) - 1, "items": [text]}
        if channel == self.current_target:
            self.textBrowser.append(line)
            self.textBrowser.moveCursor(QTextCursor.MoveOperation.End if hasattr(QTextCursor, "MoveOperation") else QTextCursor.End)

    def _close_window(self, name: str, remove_saved: bool = False):
        if not name or name == "*status*":
            return
        self._invalidate_presence_summary(name)
        self._highlighted_windows.discard(name)
        self.channel_logs.pop(name, None)
        self.channels_users.pop(name, None)
        if name in self.open_windows:
            self.open_windows = [x for x in self.open_windows if x != name]
        if remove_saved and name in self._joined_channels:
            self._joined_channels.discard(name)
            self._persist_history_state()
        if self.current_target == name:
            self.current_target = "*status*"
            if self.worker:
                self.worker.current_target = "*status*"
            self._refresh_channel_view()
            self._refresh_user_list([])
        self._refresh_channel_list()

    def _load_history_combo(self):
        self.cmbConnectionHistory.clear()
        self.cmbConnectionHistory.addItem("Recent connections…")
        for item in self._history:
            label = f"{item.get('server', DEFAULT_SERVER)}:{item.get('port', DEFAULT_PORT)}  {item.get('nick', DEFAULT_NICK)}"
            self.cmbConnectionHistory.addItem(label, item)

    def _apply_history_item(self, idx: int):
        if idx <= 0:
            return
        item = self.cmbConnectionHistory.itemData(idx)
        if not isinstance(item, dict):
            return
        self.txtServer.setPlainText(str(item.get("server", DEFAULT_SERVER)))
        self.txtPort.setPlainText(str(item.get("port", DEFAULT_PORT)))
        self.txtNick.setPlainText(str(item.get("nick", DEFAULT_NICK)))
        
        fallback_ssl = (item.get("port", DEFAULT_PORT) == 6697)
        self.chkSSL.setChecked(item.get("use_ssl", fallback_ssl))

        channels = [c for c in item.get("channels", []) if isinstance(c, str) and c]
        self._pending_autojoin = channels[:]
        self._joined_channels = set(channels)
        self.open_windows = _normalize_windows(["*status*"] + channels)
        if channels:
            self.current_target = channels[0]
        else:
            self.current_target = DEFAULT_CHANNEL
        self._refresh_channel_list()

    def _is_keypress(self, event) -> bool:
        try:
            return event.type() == QEvent.Type.KeyPress
        except AttributeError:
            return event.type() == QEvent.KeyPress

    def eventFilter(self, obj, event):
        if obj is self.txtInput and self._is_keypress(event):
            key = event.key()
            try:
                return_keys = (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                tab_key = Qt.Key.Key_Tab
                up_key = Qt.Key.Key_Up
                down_key = Qt.Key.Key_Down
                no_mods = Qt.KeyboardModifier.NoModifier if hasattr(Qt, "KeyboardModifier") else Qt.NoModifier
            except AttributeError:
                return_keys = (Qt.Key_Return, Qt.Key_Enter)
                tab_key = Qt.Key_Tab
                up_key = Qt.Key_Up
                down_key = Qt.Key_Down
                no_mods = Qt.NoModifier

            if key in return_keys:
                self._send_input()
                return True

            if key == tab_key:
                try:
                    if event.modifiers() == no_mods:
                        if self._autocomplete_nick():
                            return True
                except Exception:
                    if self._autocomplete_nick():
                        return True
                        
            if key == up_key:
                if self._input_history:
                    if self._input_history_index == len(self._input_history):
                        self._current_typing_buffer = self.txtInput.toPlainText()
                    if self._input_history_index > 0:
                        self._input_history_index -= 1
                        self.txtInput.setPlainText(self._input_history[self._input_history_index])
                        cursor = self.txtInput.textCursor()
                        cursor.movePosition(QTextCursor.MoveOperation.End if hasattr(QTextCursor, "MoveOperation") else QTextCursor.End)
                        self.txtInput.setTextCursor(cursor)
                return True

            if key == down_key:
                if self._input_history_index < len(self._input_history):
                    self._input_history_index += 1
                    if self._input_history_index == len(self._input_history):
                        self.txtInput.setPlainText(self._current_typing_buffer)
                    else:
                        self.txtInput.setPlainText(self._input_history[self._input_history_index])
                    cursor = self.txtInput.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End if hasattr(QTextCursor, "MoveOperation") else QTextCursor.End)
                    self.txtInput.setTextCursor(cursor)
                return True
                
        return super().eventFilter(obj, event)

    def _append_status(self, text: str):
        self.lblStatus.setText(f"Status: {text}")
        self._append_channel_line('*status*', f'<div class="statusmsg">{_html_span("ts", _ts())} {html.escape(text)}</div>')
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End if hasattr(QTextCursor, "MoveOperation") else QTextCursor.End)

    def _ordered_windows(self) -> List[str]:
        return _normalize_windows(self.open_windows)

    def _persist_history_state(self) -> None:
        server = self._ui_server()
        port = self._ui_port()
        nick = self._ui_nick()
        use_ssl = self.chkSSL.isChecked()
        channels = sorted(ch for ch in self._joined_channels if ch)
        key = _network_key(server, port)
        updated = False
        for item in self._history:
            try:
                if _network_key(str(item.get("server", "")), int(item.get("port", 0) or 0)) == key:
                    item["server"] = server
                    item["port"] = port
                    item["nick"] = nick
                    item["channels"] = channels
                    item["use_ssl"] = use_ssl
                    updated = True
                    break
            except Exception:
                continue
        if not updated:
            self._history.insert(0, {"server": server, "port": port, "nick": nick, "channels": channels, "use_ssl": use_ssl})
        save_history(self._history)
        self._load_history_combo()

    def _refresh_channel_list(self):
        self._channels_model.set_items(self._ordered_windows())
        self._channels_model.set_current(self.current_target)
        self._channels_model.set_highlighted(self._highlighted_windows)
        self.lstChannels.setModel(self._channels_model)
        try:
            self.lstChannels.clicked.disconnect()
        except Exception:
            pass
        self.lstChannels.clicked.connect(lambda idx: self._select_channel(self._channels_model.data(idx, Qt.DisplayRole)))
        self._channels_model.add_or_move("*status*")

    def _append_channel_line(self, channel: str, html_line: str):
        if not channel:
            channel = "*status*"
        self._invalidate_presence_summary(channel)
        self.channel_logs.setdefault(channel, []).append(html_line)
        if channel == self.current_target:
            self.textBrowser.append(html_line)
            self.textBrowser.moveCursor(QTextCursor.MoveOperation.End if hasattr(QTextCursor, "MoveOperation") else QTextCursor.End)

    def _refresh_channel_view(self):
        self.textBrowser.clear()
        for line in self.channel_logs.get(self.current_target, []):
            self.textBrowser.append(line)
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End if hasattr(QTextCursor, "MoveOperation") else QTextCursor.End)

    def _append_html_line(self, html_line: str):
        self.textBrowser.append(html_line)
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End if hasattr(QTextCursor, "MoveOperation") else QTextCursor.End)

    def _current_input_text(self) -> str:
        return self.txtInput.toPlainText().strip()

    def _current_input_cursor(self):
        try:
            return self.txtInput.textCursor()
        except Exception:
            return None

    def _nick_candidates(self) -> List[str]:
        current = self.current_target or DEFAULT_CHANNEL
        users = set(self.channels_users.get(current, set()))
        if not users:
            for group in self.channels_users.values():
                users.update(group)
        users.discard(self._ui_nick())
        return sorted((u for u in users if u), key=str.lower)

    def _autocomplete_nick(self) -> bool:
        cursor = self._current_input_cursor()
        if cursor is None or cursor.hasSelection():
            self._completion_state = None
            return False

        text = self.txtInput.toPlainText()
        pos = cursor.position()
        if pos <= 0:
            self._completion_state = None
            return False

        separators = " \t\r\n,.:;!?()[]{}<>"
        start = pos
        while start > 0 and text[start - 1] not in separators:
            start -= 1

        token = text[start:pos]
        if not token:
            self._completion_state = None
            return False

        candidates = self._nick_candidates()
        if not candidates:
            self._completion_state = None
            return False

        matches = [nick for nick in candidates if nick.lower().startswith(token.lower())]
        if not matches:
            self._completion_state = None
            return False

        if (self._completion_state is not None and 
            self._completion_state.get('token') == token and
            self._completion_state.get('start') == start):
            self._completion_state['index'] = (self._completion_state['index'] + 1) % len(matches)
        else:
            self._completion_state = {
                'token': token,
                'start': start,
                'matches': matches,
                'index': 0
            }

        match = self._completion_state['matches'][self._completion_state['index']]
        
        if start == 0:
            replacement = match + ": "
        else:
            replacement = match
        
        new_text = text[:start] + replacement + text[pos:]
        self.txtInput.blockSignals(True)
        try:
            self.txtInput.setPlainText(new_text)
            new_cursor = self.txtInput.textCursor()
            new_cursor.setPosition(start + len(replacement))
            self.txtInput.setTextCursor(new_cursor)
            
            if len(matches) > 1:
                remaining = [m for i, m in enumerate(matches) if i != self._completion_state['index']]
                hint = f"{match} [{self._completion_state['index'] + 1}/{len(matches)}]"
                if remaining:
                    hint += f" • {', '.join(remaining[:3])}"
                    if len(remaining) > 3:
                        hint += f" +{len(remaining) - 3} more"
                self.lblStatus.setText(f"Tab to cycle: {hint}")
            else:
                self.lblStatus.setText(f"Status: Completed: {match}")
        finally:
            self.txtInput.blockSignals(False)
        return True

    def _ui_server(self) -> str:
        return self.txtServer.toPlainText().strip() or DEFAULT_SERVER

    def _ui_port(self) -> int:
        try:
            return int(self.txtPort.toPlainText().strip() or DEFAULT_PORT)
        except Exception:
            return DEFAULT_PORT

    def _ui_nick(self) -> str:
        return self.txtNick.toPlainText().strip() or DEFAULT_NICK

    def _ui_password(self) -> str:
        return self.txtPW.text().strip()

    def toggle_connection(self):
        if self.worker and self.worker.is_alive():
            self._persist_history_state()
            self.worker.disconnect("Leaving")
            self.worker = None
            self.connected = False
            self.btnConnect.setText("Connect")
            self._append_status("Disconnect requested")
            return

        server = self._ui_server()
        port = self._ui_port()
        nick = self._ui_nick()
        pw = self._ui_password()
        use_ssl = self.chkSSL.isChecked()
        trust_ssl = self.settings.get("trust_all_ssl", False)
        server_pass = self.settings.get("server_password", "") # IRC PASS[cite: 4]
        
        self._pending_autojoin = list(dict.fromkeys(self._pending_autojoin))
        self.worker = IRCClientThread(server, port, nick, pw, use_ssl, self.outq, self.eventq, trust_all_ssl=trust_ssl, server_pass=server_pass)
        self.worker.start()
        self.connected = True
        self.btnConnect.setText("Disconnect")
        self._append_status(f"Connecting to {server}:{port} as {nick} (SSL: {use_ssl}, Trust Invalid: {trust_ssl})")
        self._persist_history_state()

    def _ensure_channel(self, name: str):
        if not name or name == "*status*":
            return
        if name not in self.open_windows:
            self.open_windows.append(name)
            self._refresh_channel_list()

    def _refresh_user_list(self, users: List[str]):
        model = QStringListModel(users)
        self.lstUsers.setModel(model)
        self._users_model = model

    def _mark_highlight(self, channel: str, play_sound: bool = True) -> None:
        if not channel or channel == "*status*":
            return
            
        if channel == self.current_target and self.isActiveWindow():
            return
            
        self._highlighted_windows.add(channel)
        if play_sound:
            try:
                QApplication.beep()
            except Exception:
                pass
        self._refresh_channel_list()

    def _clear_highlight(self, channel: str) -> None:
        if channel in self._highlighted_windows:
            self._highlighted_windows.discard(channel)
            self._refresh_channel_list()

    def _history_channels_for_save(self) -> List[str]:
        return sorted(ch for ch in self._joined_channels if ch)

    def _select_channel(self, name: str):
        if not name:
            return
        self.current_target = name
        self._clear_highlight(name)
        self._typing_state.pop(name, None)
        self._append_status(f"Switched to {name}")
        self._refresh_channel_view()
        if self.worker:
            self.worker.current_target = name
        users = sorted(self.channels_users.get(name, set()), key=str.lower)
        self._refresh_user_list(users)

    def _send_input(self):
        text = self._current_input_text()
        if not text:
            return
            
        if not self._input_history or self._input_history[-1] != text:
            self._input_history.append(text)
        self._input_history_index = len(self._input_history)
        self._current_typing_buffer = ""
        
        self.txtInput.clear()
        self._completion_state = None
        self._send_typing_state("done")
        target = self.current_target or DEFAULT_CHANNEL
        if text.startswith("/"):
            self._handle_command(text[1:])
            return
        self._append_local_message(target, self._ui_nick(), text, self_msg=True)
        if self.worker:
            self.worker.cmd_msg(target, text)
        else:
            self._append_status("Not connected")

    def _handle_command(self, line: str):
        parts = line.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        if cmd in ("join", "j"):
            if self.worker and arg:
                self.worker.cmd_join(arg)
                self._ensure_channel(arg)
                self._joined_channels.add(arg)
                self._persist_history_state()
                self._select_channel(arg)
        elif cmd == "part":
            chan = arg or self.current_target or DEFAULT_CHANNEL
            if self.worker:
                self.worker.cmd_part(chan)
            if chan and chan[0] in "#&!+":
                self._pending_self_parts.add(chan)
            self._close_window(chan, remove_saved=True)
        elif cmd in ("me", "action", "describe"):
            if self.worker:
                self._append_local_message(self.current_target or DEFAULT_CHANNEL, self._ui_nick(), arg, self_msg=True, action=True)
                self.worker.cmd_me(self.current_target or DEFAULT_CHANNEL, arg)
        elif cmd == "msg":
            if self.worker and arg:
                tparts = arg.split(None, 1)
                if len(tparts) == 2:
                    target, body = tparts
                    self._append_local_message(target, self._ui_nick(), body, self_msg=True)
                    self._ensure_channel(target)
                    self.worker.cmd_msg(target, body)
        elif cmd == "notice":
            if self.worker and arg:
                tparts = arg.split(None, 1)
                if len(tparts) == 2:
                    target, body = tparts
                    self.worker.cmd_notice(target, body)
        elif cmd == "nick":
            if self.worker and arg:
                self.worker.cmd_nick(arg)
        elif cmd == "who":
            if self.worker and arg:
                self.worker.cmd_raw(f"WHO {arg}")
        elif cmd == "whois":
            if self.worker and arg:
                self.worker.cmd_raw(f"WHOIS {arg}")
        elif cmd == "whowas":
            if self.worker and arg:
                self.worker.cmd_raw(f"WHOWAS {arg}")
        elif cmd == "kick":
            if self.worker and arg:
                kparts = arg.split(None, 1)
                if len(kparts) == 1:
                    chan = self.current_target or DEFAULT_CHANNEL
                    self.worker.cmd_raw(f"KICK {chan} {kparts[0]}")
                else:
                    target = kparts[0]
                    if target.startswith(('#', '&', '!', '+')):
                        self.worker.cmd_raw(f"KICK {target} {kparts[1]}")
                    else:
                        chan = self.current_target or DEFAULT_CHANNEL
                        self.worker.cmd_raw(f"KICK {chan} {target} :{kparts[1]}")
        elif cmd == "mode":
            if self.worker and arg:
                mparts = arg.split(None, 1)
                first = mparts[0]
                if first.startswith(('#', '&', '!', '+')) or (len(mparts) > 1 and first[0] not in '+-'):
                    self.worker.cmd_raw(f"MODE {arg}")
                else:
                    self.worker.cmd_raw(f"MODE {self.current_target or DEFAULT_CHANNEL} {arg}")
            elif self.worker:
                self.worker.cmd_raw(f"MODE {self.current_target or DEFAULT_CHANNEL}")
        elif cmd == "invite":
            if self.worker and arg:
                iparts = arg.split(None, 1)
                if len(iparts) == 1:
                    self.worker.cmd_raw(f"INVITE {iparts[0]} {self.current_target or DEFAULT_CHANNEL}")
                else:
                    self.worker.cmd_raw(f"INVITE {iparts[0]} {iparts[1]}")
        elif cmd == "away":
            if self.worker:
                if arg:
                    self.worker.cmd_raw(f"AWAY :{arg}")
                else:
                    self.worker.cmd_raw("AWAY")
        elif cmd == "list":
            if self.worker:
                self.worker.cmd_raw(f"LIST {arg}" if arg else "LIST")
        elif cmd == "names":
            if self.worker:
                self.worker.cmd_raw(f"NAMES {arg}" if arg else f"NAMES {self.current_target or DEFAULT_CHANNEL}")
        elif cmd == "raw":
            if self.worker and arg:
                self.worker.cmd_raw(arg)
        elif cmd == "quit":
            if self.worker:
                self.worker.cmd_quit(arg or "Leaving")
                self.worker = None
                self.connected = False
                self.btnConnect.setText("Connect")
        elif cmd == "clear":
            self.textBrowser.clear()
        elif cmd == "topic":
            if self.worker and arg:
                self.worker.cmd_raw(f"TOPIC {self.current_target or DEFAULT_CHANNEL} :{arg}")
        elif cmd == "knock":
            if self.worker and arg:
                kparts = arg.split(None, 1)
                if len(kparts) == 1:
                    self.worker.cmd_raw(f"KNOCK {kparts[0]}")
                else:
                    self.worker.cmd_raw(f"KNOCK {kparts[0]} :{kparts[1]}")
        elif cmd == "setname":
            if self.worker and arg:
                self.worker.cmd_raw(f"SETNAME :{arg}")
        else:
            self._append_status(f"Unknown command: /{cmd}")

    def _update_remote_typing(self, channel: str, nick: str, state: str):
        if not channel or not nick or nick == self._ui_nick():
            return
        current = self._typing_state.setdefault(channel, set())
        if state == "done":
            current.discard(nick)
            return
        if state in ("active", "paused"):
            if nick not in current:
                current.add(nick)
                if channel == self.current_target:
                    self.lblStatus.setText(f"Status: {nick} is typing...")
                else:
                    self._mark_highlight(channel, play_sound=False)
            return

    def _append_message_to_channel(self, channel: str, html_line: str):
        self._append_channel_line(channel, html_line)

    def _append_local_message(self, target: str, nick: str, text: str, self_msg: bool = False, action: bool = False):
        ts = _ts()
        clean = make_urls_clickable(html.escape(strip_irc_formatting(mirc_to_html(text))))
        nick_html = _html_span("nick", nick)
        if action:
            line = f'<div>{_html_span("ts", ts)} <span class="actionmsg">* {nick_html} {clean}</span></div>'
        else:
            if self_msg:
                cls = "selfmsg"
            elif self._ui_nick().lower() in text.lower() or target == self._ui_nick():
                cls = "directmsg"
            else:
                cls = "statusmsg"
            line = f'<div>{_html_span("ts", ts)} <span class="{cls}">{nick_html}: {clean}</span></div>'
        self._ensure_channel(target)
        self._append_channel_line(target, line)

    def poll_events(self):
        while True:
            try:
                ev = self.eventq.get_nowait()
            except queue.Empty:
                break
            kind = ev.get("type")
            if kind == "status":
                self._append_status(ev.get("text", ""))
            elif kind == "connected":
                if self._pending_autojoin and self.worker:
                    for chan in list(dict.fromkeys(self._pending_autojoin)):
                        if chan and chan != "*status*":
                            self.worker.cmd_join(chan)
                            self._ensure_channel(chan)
                            self._joined_channels.add(chan)
                    self._pending_autojoin = []
                    self._persist_history_state()
            elif kind == "names":
                channel = ev.get("channel", "")
                users = ev.get("users", [])
                bucket = self.channels_users.setdefault(channel, set())
                bucket.update(users)
                self._ensure_channel(channel)
                if channel == self.current_target:
                    self._refresh_user_list(sorted(bucket, key=str.lower))
            elif kind == "join":
                channel = ev.get("channel", "")
                nick = ev.get("nick", "")
                self._pending_self_parts.discard(channel)
                self.channels_users.setdefault(channel, set()).add(nick)
                self._ensure_channel(channel)
                self._append_presence_summary(channel, "join", nick)
                if ev.get("self_join"):
                    self._joined_channels.add(channel)
                    self.current_target = channel
                    self._select_channel(channel)
                    self._append_status(f"Joined {channel}")
                    self._persist_history_state()
                elif channel == self.current_target:
                    self._refresh_user_list(sorted(self.channels_users[channel], key=str.lower))
            elif kind == "part":
                channel = ev.get("channel", "")
                nick = ev.get("nick", "")
                if channel in self._pending_self_parts and nick == self._ui_nick():
                    self._pending_self_parts.discard(channel)
                    self._joined_channels.discard(channel)
                    self._persist_history_state()
                    self.channels_users.pop(channel, None)
                    self.channel_logs.pop(channel, None)
                    if channel in self.open_windows:
                        self.open_windows = [x for x in self.open_windows if x != channel]
                        self._refresh_channel_list()
                    if self.current_target == channel:
                        self.current_target = "*status*"
                        self._refresh_channel_view()
                    continue
                self.channels_users.get(channel, set()).discard(nick)
                self._append_presence_summary(channel, "part", nick)
                if channel == self.current_target:
                    self._refresh_user_list(sorted(self.channels_users.get(channel, set()), key=str.lower))
                if channel in self._joined_channels and (nick == self._ui_nick() or ev.get("self_part")):
                    self._joined_channels.discard(channel)
                    self._persist_history_state()
            elif kind == "quit":
                nick = ev.get("nick", "")
                relevant_channels = [ch for ch, users in self.channels_users.items() if nick in users and ch != "*status*"]
                for ch in relevant_channels:
                    self.channels_users.get(ch, set()).discard(nick)
                    self._append_presence_summary(ch, "quit", nick)
                    self._typing_state.get(ch, set()).discard(nick)
                if self.current_target in relevant_channels:
                    self._refresh_user_list(sorted(self.channels_users.get(self.current_target, set()), key=str.lower))
                for ch in relevant_channels:
                    self._highlighted_windows.discard(ch)
                self._refresh_channel_list()
            elif kind == "kick":
                channel = ev.get("channel", self.current_target)
                self._append_channel_line(channel, f'<div>{_html_span("ts", ev.get("ts", _ts()))} <span class="nick">{html.escape(ev.get("target", ""))}</span> was kicked from {html.escape(ev.get("channel", ""))}: {html.escape(ev.get("reason", ""))}</div>')
            elif kind == "topic":
                channel = ev.get("channel", self.current_target)
                self._append_channel_line(channel, f'<div>{_html_span("ts", ev.get("ts", _ts()))} <span class="topicmsg">Topic for {html.escape(ev.get("channel", ""))}: {html.escape(ev.get("topic", ""))}</span></div>')
            elif kind == "nick":
                old = ev.get("old", "")
                new = ev.get("new", "")
                for users in self.channels_users.values():
                    if old in users:
                        users.discard(old)
                        users.add(new)
                if old in self._joined_channels:
                    self._joined_channels.discard(old)
                    self._joined_channels.add(new)
                    self._persist_history_state()
                self._completion_state = None
                if self.current_target:
                    self._refresh_user_list(sorted(self.channels_users.get(self.current_target, set()), key=str.lower))
                self._append_channel_line(ev.get('channel', self.current_target), f'<div>{_html_span("ts", ev.get("ts", _ts()))} {html.escape(old)} is now known as {html.escape(new)}</div>')
            elif kind == "notice":
                target = ev.get("target", "")
                text = make_urls_clickable(mirc_to_html(html.escape(strip_irc_formatting(ev.get("text", "")))))
                cls = "directmsg" if ev.get("direct") else "noticemsg"
                channel = target if target != self._ui_nick() else ev.get('nick', self.current_target)
                self._ensure_channel(channel)
                self._append_channel_line(channel, f'<div>{_html_span("ts", ev.get("ts", _ts()))} <span class="{cls}">NOTICE {html.escape(ev.get("nick", ""))} → {html.escape(target)}: {text}</span></div>')
                if (ev.get("direct") or ev.get("nick") == self._ui_nick()) and channel != self.current_target:
                    self._mark_highlight(channel, play_sound=True)
            elif kind == "message":
                nick = html.escape(ev.get("nick", ""))
                target = ev.get("target", "")
                is_direct = bool(ev.get("direct"))
                display_target = ev.get("nick", target) if is_direct else target
                
                raw_text = ev.get("text", "")
                text = make_urls_clickable(mirc_to_html(html.escape(strip_irc_formatting(raw_text))))
                ts = _html_span("ts", ev.get("ts", _ts()))
                if ev.get("action"):
                    line = f'<div>{ts} <span class="actionmsg">* {nick} {text}</span></div>'
                elif ev.get("self_msg"):
                    line = f'<div>{ts} <span class="selfmsg">{nick}: {text}</span></div>'
                elif is_direct:
                    line = f'<div>{ts} <span class="directmsg">{nick}: {text}</span></div>'
                elif ev.get("mention"):
                    line = f'<div>{ts} <span class="mentionmsg">{nick}: {text}</span></div>'
                else:
                    line = f'<div>{ts} <span class="statusmsg">{nick}: {text}</span></div>'
                self._ensure_channel(display_target)
                self._append_channel_line(display_target, line)
                self._typing_state.get(display_target, set()).discard(ev.get("nick", ""))
                
                is_active = self.isActiveWindow()
                hl_on_mention = self.settings.get("highlight_on_mention", True)

                if (ev.get("mention") or is_direct):
                    if display_target != self.current_target or (not is_active and hl_on_mention):
                        self._mark_highlight(display_target, play_sound=True)
            elif kind == "typing":
                channel = ev.get("channel", "")
                nick = ev.get("nick", "")
                state = ev.get("state", "")
                if channel and nick:
                    self._update_remote_typing(channel, nick, state)
            elif kind == "disconnected":
                self.connected = False
                self.btnConnect.setText("Connect")
                self._append_status(ev.get("text", "Disconnected"))

    def _send_typing_state(self, state: str):
        if not self.worker:
            return
        target = self._typing_target()
        if self.worker:
            self.worker.send_typing(target, state)

if BINDING is None:
    raise SystemExit("PySide6 / PyQt6 / PyQt5 is not installed. Install one of them to run this GUI.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    initial_theme = load_settings().get("theme", "dark_teal.xml")
    apply_stylesheet(app, theme=initial_theme)
    win = IRCMainWindow()
    win.show()
    sys.exit(app.exec())