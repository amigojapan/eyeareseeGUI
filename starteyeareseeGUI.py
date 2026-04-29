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
from qt_material import apply_stylesheet


try:
    from PySide6.QtCore import Qt, QEvent, QTimer, QThread, QStringListModel
    from PySide6.QtGui import QColor, QFont, QTextCursor, QTextOption
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
    )
    BINDING = "PySide6"
except Exception:
    try:
        from PyQt6.QtCore import Qt, QEvent, QTimer, QThread, QStringListModel
        from PyQt6.QtGui import QColor, QFont, QTextCursor, QTextOption
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
        )
        from PyQt6.QtCore import QStringListModel
        BINDING = "PyQt6"
    except Exception:
        try:
            from PyQt5.QtCore import Qt, QEvent, QTimer, QThread, QStringListModel
            from PyQt5.QtGui import QColor, QFont, QTextCursor, QTextOption
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
            )
            BINDING = "PyQt5"
        except Exception:
            BINDING = None

DEFAULT_SERVER = "irc.libera.chat"
DEFAULT_PORT = 6697
DEFAULT_NICK = ""
DEFAULT_CHANNEL = "#eyearesee"

SCRIPT_DIR = Path(__file__).resolve().parent
HISTORY_PATH = SCRIPT_DIR / "connection_history.json"

IRC_CTLS_RE = re.compile(r"\x03(?:\d{1,2}(?:,\d{1,2})?)?|[\x02\x0F\x16\x1D\x1F]")


def make_urls_clickable(text: str) -> str:
    def repl(match):
        url = match.group(0)
        return f'<a href="{url}">{url}</a>'
    return IRC_URL_RE.sub(repl, text)

IRC_URL_RE = re.compile(r'https?://[^\s\x00-\x1f\x7f<>"\']+')


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
    }
    style = styles.get(cls, "")
    if style:
        return f'<span style="{style}">{escaped}</span>'
    return f'<span>{escaped}</span>'


def irc_inline_to_html(text: str) -> str:
    text = html.escape(text)
    text = text.replace("\x02", "<b>")
    # Escape helper for color / reset / italic / underline / reverse is intentionally simple:
    # the display focus here is on channel-level highlighting, not perfect IRC rendering.
    text = text.replace("\x0F", "</b></i></u><span>")
    text = text.replace("\x1D", "<i>")
    text = text.replace("\x1F", "<u>")
    text = text.replace("\x16", "")
    text = re.sub(r"\x03(?:\d{1,2}(?:,\d{1,2})?)?", "", text)
    return text


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

    def __init__(self, server: str, port: int, nick: str, password: str, use_ssl: bool, outq: queue.Queue, eventq: queue.Queue):
        super().__init__(daemon=True)
        self.server = server
        self.port = port
        self.nick = nick
        self.password = password
        self.use_ssl = use_ssl
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

    def _is_chan(self, name: str) -> bool:
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
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            self.sock = ctx.wrap_socket(raw, server_hostname=self.server)
            self.sock.settimeout(self._reader_timeout)
        else:
            self.sock = raw
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
                if line.startswith("CAP ") or line.startswith("AUTHENTICATE ") or line.startswith("NICK ") or line.startswith("USER "):
                    pass
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


class IRCMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # MUST call parent __init__ FIRST
        self.setWindowTitle("eye are see GUI")
        self.resize(1100, 720)
        self.eventq: queue.Queue = queue.Queue()
        self.outq: queue.Queue = queue.Queue()
        self.worker: Optional[IRCClientThread] = None
        self.connected = False
        self.current_target = DEFAULT_CHANNEL
        self.channels_users: Dict[str, set] = {DEFAULT_CHANNEL: set()}
        self.channel_logs: Dict[str, list] = {}
        self.current_target = DEFAULT_CHANNEL
        self.open_windows: List[str] = ["*status*", DEFAULT_CHANNEL]
        self._history = load_history()
        self._completion_state: Optional[Dict] = None  # Track completion cycling
        self._build_ui()
        self._load_history_combo()
        self._append_status("Ready.")
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self.poll_events)
        self._poll_timer.start(50)

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
        self.btnConnect = QPushButton("Connect")
        self.cmbConnectionHistory = QComboBox()
        self.cmbConnectionHistory.setToolTip("Connection History")
        self.cmbConnectionHistory.currentIndexChanged.connect(self._apply_history_item)
        self.btnConnect.clicked.connect(self.toggle_connection)

        for w in (self.txtServer, self.txtPort, self.txtNick, self.txtPW, self.btnConnect, self.cmbConnectionHistory):
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
        self.textBrowser.setStyleSheet(
            "QTextBrowser { background: #111318; color: #f4f7fb; border: 1px solid #2b2f3a; font-family: monospace; font-size: 12pt; }"
            ".ts { color: #8aa0b8; }"
            ".nick { color: #8fd3ff; font-weight: 700; }"
            ".selfmsg { background: #063b23; color: #7dffb2; font-weight: 800; padding: 0 4px; border-radius: 4px; }"
            ".directmsg { background: #3a0b56; color: #ff77ff; font-weight: 800; padding: 0 4px; border-radius: 4px; }"
            ".mentionmsg { background: #463b00; color: #ffe86a; font-weight: 800; padding: 0 4px; border-radius: 4px; }"
            ".actionmsg { color: #64f0ff; font-style: italic; }"
            ".statusmsg { color: #c6d0e2; }"
            ".noticemsg { color: #ff9ee8; }"
            ".topicmsg { color: #65d6ff; }"
        )

        self.frmUserslist = QFrame()
        self.frmUserslist.setFrameShape(QFrame.Shape.StyledPanel if hasattr(QFrame, "Shape") else QFrame.StyledPanel)
        side = QVBoxLayout(self.frmUserslist)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(4)
        self.lstChannels = QListView()
        self.lstUsers = QListView()
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
        self.txtInput.setFocus()
        ch.addWidget(self.txtInput)

        root.addWidget(self.frmChatarea, 1)

        self.lblStatus = QLabel("Status: Ready")
        root.addWidget(self.lblStatus)

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
                no_mods = Qt.KeyboardModifier.NoModifier if hasattr(Qt, "KeyboardModifier") else Qt.NoModifier
            except AttributeError:
                return_keys = (Qt.Key_Return, Qt.Key_Enter)
                tab_key = Qt.Key_Tab
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
        return super().eventFilter(obj, event)

    def _append_status(self, text: str):
        self.lblStatus.setText(f"Status: {text}")
        self._append_channel_line('*status*', f'<div class="statusmsg">{_html_span("ts", _ts())} {html.escape(text)}</div>')
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End if hasattr(QTextCursor, "MoveOperation") else QTextCursor.End)

    
    def _append_channel_line(self, channel: str, html_line: str):
        if not channel:
            channel = "*status*"
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
        """Autocomplete nickname with cycling support. Press Tab multiple times to cycle through matches."""
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

        # Find all matches for this token
        matches = [nick for nick in candidates if nick.lower().startswith(token.lower())]
        if not matches:
            self._completion_state = None
            return False

        # Determine if we should cycle to the next match
        if (self._completion_state is not None and 
            self._completion_state.get('token') == token and
            self._completion_state.get('start') == start):
            # Same token, same position — cycle to next match
            self._completion_state['index'] = (self._completion_state['index'] + 1) % len(matches)
        else:
            # New token or position — start fresh
            self._completion_state = {
                'token': token,
                'start': start,
                'matches': matches,
                'index': 0
            }

        match = self._completion_state['matches'][self._completion_state['index']]
        
        # Add colon after first word (common IRC convention)
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
            
            # Show hint about available matches
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
        use_ssl = port == 6697 or port == 6697
        self.worker = IRCClientThread(server, port, nick, pw, use_ssl, self.outq, self.eventq)
        self.worker.start()
        self.connected = True
        self.btnConnect.setText("Disconnect")
        self._append_status(f"Connecting to {server}:{port} as {nick}")
        self._history = [h for h in self._history if not (h.get('server') == server and str(h.get('port')) == str(port) and h.get('nick') == nick)]
        self._history.insert(0, {"server": server, "port": port, "nick": nick})
        save_history(self._history)
        self._load_history_combo()

    def _ensure_channel(self, name: str):
        if name not in self.open_windows:
            self.open_windows.append(name)
            self._refresh_channel_list()

    def _refresh_channel_list(self):
        model = QStringListModel(self.open_windows)
        self.lstChannels.setModel(model)
        try:
            self.lstChannels.clicked.disconnect()
        except Exception:
            pass
        self.lstChannels.clicked.connect(lambda idx: self._select_channel(model.data(idx)))
        self._channels_model = model

    def _refresh_user_list(self, users: List[str]):
        model = QStringListModel(users)
        self.lstUsers.setModel(model)
        self._users_model = model

    def _select_channel(self, name: str):
        if not name:
            return
        self.current_target = name
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
        self.txtInput.clear()
        self._completion_state = None  # Reset completion state on send
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
                self._select_channel(arg)
        elif cmd == "part":
            chan = arg or self.current_target or DEFAULT_CHANNEL
            if self.worker:
                self.worker.cmd_part(chan)
        elif cmd == "me":
            if self.worker:
                self._append_local_message(self.current_target or DEFAULT_CHANNEL, self._ui_nick(), arg, self_msg=True, action=True)
                self.worker.cmd_me(self.current_target or DEFAULT_CHANNEL, arg)
        elif cmd == "msg":
            if self.worker and arg:
                tparts = arg.split(None, 1)
                if len(tparts) == 2:
                    target, body = tparts
                    self._append_local_message(target, self._ui_nick(), body, self_msg=True)
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
        else:
            self._append_status(f"Unknown command: /{cmd}")

    def _append_local_message(self, target: str, nick: str, text: str, self_msg: bool = False, action: bool = False):
        ts = _ts()
        clean = make_urls_clickable(html.escape(strip_irc_formatting(text)))
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
        self._append_channel_line(target if 'target' in locals() else ev.get('channel', self.current_target), line)

    def poll_events(self):
        while True:
            try:
                ev = self.eventq.get_nowait()
            except queue.Empty:
                break
            kind = ev.get("type")
            if kind == "status":
                self._append_status(ev.get("text", ""))
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
                self.channels_users.setdefault(channel, set()).add(nick)
                self._ensure_channel(channel)
                if ev.get("self_join"):
                    self.current_target = channel
                    self._select_channel(channel)
                    self._append_status(f"Joined {channel}")
                else:
                    self._append_channel_line(ev.get('channel', self.current_target), f'<div>{_html_span("ts", ev.get("ts", _ts()))} <span class="nick">{html.escape(nick)}</span> joined {html.escape(channel)}</div>')
                    if channel == self.current_target:
                        self._refresh_user_list(sorted(self.channels_users[channel], key=str.lower))
            elif kind == "part":
                channel = ev.get("channel", "")
                nick = ev.get("nick", "")
                self.channels_users.get(channel, set()).discard(nick)
                self._append_channel_line(ev.get('channel', self.current_target), f'<div>{_html_span("ts", ev.get("ts", _ts()))} <span class="nick">{html.escape(nick)}</span> left {html.escape(channel)} {html.escape(ev.get("reason", ""))}</div>')
                if channel == self.current_target:
                    self._refresh_user_list(sorted(self.channels_users.get(channel, set()), key=str.lower))
            elif kind == "quit":
                nick = ev.get("nick", "")
                for users in self.channels_users.values():
                    users.discard(nick)
                if self.current_target:
                    self._refresh_user_list(sorted(self.channels_users.get(self.current_target, set()), key=str.lower))
                self._append_channel_line(ev.get('channel', self.current_target), f'<div>{_html_span("ts", ev.get("ts", _ts()))} <span class="nick">{html.escape(nick)}</span> quit {html.escape(ev.get("reason", ""))}</div>')
            elif kind == "kick":
                self._append_channel_line(ev.get('channel', self.current_target), f'<div>{_html_span("ts", ev.get("ts", _ts()))} <span class="nick">{html.escape(ev.get("target", ""))}</span> was kicked from {html.escape(ev.get("channel", ""))}: {html.escape(ev.get("reason", ""))}</div>')
            elif kind == "topic":
                self._append_channel_line(ev.get('channel', self.current_target), f'<div>{_html_span("ts", ev.get("ts", _ts()))} <span class="topicmsg">Topic for {html.escape(ev.get("channel", ""))}: {html.escape(ev.get("topic", ""))}</span></div>')
            elif kind == "nick":
                old = ev.get("old", "")
                new = ev.get("new", "")
                for users in self.channels_users.values():
                    if old in users:
                        users.discard(old)
                        users.add(new)
                self._completion_state = None
                if self.current_target:
                    self._refresh_user_list(sorted(self.channels_users.get(self.current_target, set()), key=str.lower))
                self._append_channel_line(ev.get('channel', self.current_target), f'<div>{_html_span("ts", ev.get("ts", _ts()))} {html.escape(old)} is now known as {html.escape(new)}</div>')
            elif kind == "notice":
                target = ev.get("target", "")
                text = make_urls_clickable(html.escape(strip_irc_formatting(ev.get("text", ""))))
                cls = "directmsg" if ev.get("direct") else "noticemsg"
                self._append_channel_line(ev.get('channel', self.current_target), f'<div>{_html_span("ts", ev.get("ts", _ts()))} <span class="{cls}">NOTICE {html.escape(ev.get("nick", ""))} → {html.escape(target)}: {text}</span></div>')
            elif kind == "message":
                nick = html.escape(ev.get("nick", ""))
                target = ev.get("target", "")
                text = make_urls_clickable(html.escape(strip_irc_formatting(ev.get("text", ""))))
                ts = _html_span("ts", ev.get("ts", _ts()))
                if ev.get("action"):
                    line = f'<div>{ts} <span class="actionmsg">* {nick} {text}</span></div>'
                elif ev.get("self_msg"):
                    line = f'<div>{ts} <span class="selfmsg">{nick}: {text}</span></div>'
                elif ev.get("direct"):
                    line = f'<div>{ts} <span class="directmsg">{nick}: {text}</span></div>'
                elif ev.get("mention"):
                    line = f'<div>{ts} <span class="mentionmsg">{nick}: {text}</span></div>'
                else:
                    line = f'<div>{ts} <span class="statusmsg">{nick}: {text}</span></div>'
                self._append_channel_line(target if 'target' in locals() else ev.get('channel', self.current_target), line)
            elif kind == "disconnected":
                self.connected = False
                self.btnConnect.setText("Connect")
                self._append_status(ev.get("text", "Disconnected"))


if BINDING is None:
    raise SystemExit("PySide6 / PyQt6 / PyQt5 is not installed. Install one of them to run this GUI.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme='dark_teal.xml')
    win = IRCMainWindow()
    win.show()
    sys.exit(app.exec())


"""
todo
handle reciving a PM by adding the person who sent it to the channels window
store the channels I have already joined in the connnection, load whne clicking on recently connected button, per network
highlight user with sounds and colorful text, sound only whne it is not the current channel
make channel appear red until clicked when i am highlighted in that channel
fix it so that status appears in channel list at the beginning
"""