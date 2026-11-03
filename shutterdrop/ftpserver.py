"""一个对索尼相机（以及 FileZilla / lftp 等客户端）友好的最小 FTP 服务器。

设计要点
--------
* 相机上传 = 客户端 STOR / APPE（上传），因此每个数据连接在 RECV 时按上传任务跟踪进度。
* 同时支持被动模式（PASV / EPSV）与主动模式（PORT / EPDM），且两种方式都允许
  “先打开数据连接再发命令”（PORT 方式已被广泛使用，PASV 方式对部分设备也兼容）。
* ASCII 模式（TYPC A）上传时，按 FTP 规范把 CRLF 还原为 LF 再写盘，
  避免行尾被改写导致文件损坏。
* 目录操作（MKD / CWD / STOR 到不存在的目录 / RNTO 改名）都会映射到照片保存目录之下，
  并且不能越界到保存目录以外。

只使用标准库，线程模型为“每连接一线程 + 每传输一线程”。
"""
from __future__ import annotations

import logging
import os
import re
import select
import shutil
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from .core import (IMAGE_EXTS, IMAGE_EXTS_EXTRA, IMAGE_EXTS_PLAIN, Settings,
                   human_size, safe_filename, unique_path)

log = logging.getLogger("shutterdrop.ftp")
# 用 NullHandler 保证作为库导入时不会因为没有 handler 而打印警告；
# 桌面程序启动时会挂上文件 handler。
if not log.handlers:
    log.addHandler(logging.NullHandler())


# --------------------------------------------------------------------------- 事件类型

@dataclass
class TransferStarted:
    id: str
    remote: str
    filename: str
    size: int
    dest: str
    peer: str
    started: float = field(default_factory=time.time)


@dataclass
class TransferProgress:
    id: str
    received: int
    size: int


@dataclass
class TransferFinished:
    id: str
    remote: str
    filename: str
    path: str            # 最终落盘路径（失败时为 None）
    size: int            # 字节数
    duration: float
    peer: str
    error: Optional[str] = None
    started: float = 0.0
    finished: float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return self.error is None and self.path is not None

    @property
    def speed(self) -> float:
        return self.size / self.duration if self.duration > 0.05 else 0.0


@dataclass
class ClientEvent:
    kind: str            # connected / disconnected / command
    peer: str
    at: float = field(default_factory=time.time)
    text: str = ""


@dataclass
class ServerInfo:
    running: bool
    port: int
    bind: str
    error: str = ""


# --------------------------------------------------------------------------- 工具

def _norm_remote(path: str) -> str:
    """规范化客户端给出的路径，禁止 .. / 盘符 / 反斜杠越界。"""
    path = (path or "").replace("\\", "/")
    path = re.sub(r"^[A-Za-z]:", "", path)
    segs = [s for s in path.split("/") if s and s not in (".", "..")]
    return "/".join(segs)


def _shell_reply(verb: str, path: str) -> str:
    if path.startswith("/"):
        return f'257 "{path}" is current directory.'
    return f'257 "{verb}": command successful.'


class _Session:
    """一个客户端控制连接。"""

    def __init__(self, server: "FtpServer", conn: socket.socket, peer: str):
        self.server = server
        self.cfg = server.cfg
        self.conn = conn
        self.peer_ip = peer
        self.peer = peer
        self.peer_str = peer
        self.buf = b""
        self.cwd = "/"
        self.cwd_abs = cfg_photo_dir(server.cfg)
        self.type = "I"
        self.pasv: Optional[socket.socket] = None
        self.port_addr: Optional[tuple[str, int]] = None
        self.guarded: Optional[socket.socket] = None
        self.epsv = False
        self.rename_from: Optional[str] = None
        self.rest_offset = 0
        self.closed = False
        self.lock = threading.Lock()
        self.started = time.time()
        self.commands = 0
        self.upload_started = False

    # -- 发送 -----------------------------------------------------------
    def accept_loop(self, server: "FtpServer") -> None:
        """主循环：逐字节读命令。

        不用 recv(65536) 缓冲多条命令：有些环境会把多条命令合并成一个 TCP 段，
        逐字节读取可以保证“处理完一条、回复一条”的严格顺序。
        """
        self.send("220 ShutterDrop FTP ready\r\n")
        while not self.closed and not server._stop.is_set():
            try:
                ch = self.conn.recv(1)
            except socket.timeout:
                continue
            except OSError:
                break
            if not ch:
                break
            if ch in b"\r\n":
                if not self.buf:
                    continue
                line, self.buf = self.buf, b""
                try:
                    text = line.decode("utf-8")
                except UnicodeDecodeError:
                    text = line.decode("gbk", "replace")
                if not server._handle(self, text):
                    return
            else:
                self.buf += ch
                if len(self.buf) > 8192:     # 防御异常长的命令
                    self.buf = b""

    def send(self, text: str) -> bool:
        if self.closed:
            return False
        try:
            with self.lock:
                self.conn.sendall(text.encode("utf-8", "replace"))
            return True
        except OSError:
            self.closed = True
            return False

    def close_pasv(self) -> None:
        if self.pasv is not None:
            try:
                self.pasv.close()
            except OSError:
                pass
            self.pasv = None

    def close(self) -> None:
        self.closed = True
        self.close_pasv()
        self.close_guarded()
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.conn.close()
        except OSError:
            pass

    # -- 数据连接 -------------------------------------------------------
    def accept_pasv(self) -> Optional[socket.socket]:
        sock = self.pasv
        self.pasv = None
        if sock is None:
            return None
        try:
            sock.settimeout(20.0)
            conn, _ = sock.accept()
            conn.settimeout(30.0)
            return conn
        except OSError:
            return None
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def open_data(self, timeout: float = 20.0) -> Optional[socket.socket]:
        if self.pasv is not None:
            return self.accept_pasv()
        if self.guarded is not None:
            # PORT 之后已经接住的相机连接：直接交给数据线程，之后不再由其他线程碰它
            sock, self.guarded = self.guarded, None
            self.port_addr = None
            sock.settimeout(30.0)
            return sock
        addr = self.port_addr
        self.port_addr = None
        if addr is not None:
            # 重试：相机也可能在收到 150 之后才去连接
            deadline = time.time() + 8.0
            while time.time() < deadline and not self.closed:
                try:
                    conn = socket.create_connection(addr, timeout=timeout)
                    conn.settimeout(30.0)
                    return conn
                except OSError as exc:
                    log.info("主动模式连接 %s 失败：%s", addr, exc)
                    time.sleep(0.2)
            return None
        return None
        return None

    # -- 主动模式：PORT 之后立即预连接 --------------------------------
    def guard_preconnect(self, quick_window: float = 0.35) -> None:
        """在回复 200 之前，尽量把相机刚打开的数据连接接住。

        相机 / 客户端有时在收到 200 之前就去连 PORT 指定的端口；这里在后台线程里
        最多等 quick_window 秒，把接到的连接留到 STOR / RETR 时交给数据线程。
        """
        self.close_guarded()
        addr = self.port_addr
        if addr is None:
            return
        holder: dict = {}
        done = threading.Event()

        def grab():
            try:
                deadline = time.time() + 6.0
                while time.time() < deadline and not self.closed:
                    try:
                        sock = socket.create_connection(addr, timeout=0.8)
                    except OSError:
                        time.sleep(0.03)
                        continue
                    holder["sock"] = sock
                    return
            finally:
                done.set()

        threading.Thread(target=grab, name="ftp-guard", daemon=True).start()
        done.wait(max(0.0, quick_window))
        sock = holder.get("sock")
        if sock is not None and not self.closed:
            self.guarded = sock
            log.info("主动模式预连接成功：%s", addr)

    def close_guarded(self) -> None:
        if self.guarded is not None:
            try:
                self.guarded.close()
            except OSError:
                pass
            self.guarded = None

    def close_pasv(self) -> None:
        if self.pasv is not None:
            try:
                self.pasv.close()
            except OSError:
                pass
            self.pasv = None

    def close(self) -> None:
        self.closed = True
        self.close_pasv()
        self.close_guarded()
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.conn.close()
        except OSError:
            pass

    # -- 数据连接 -------------------------------------------------------
    def accept_pasv(self) -> Optional[socket.socket]:
        sock = self.pasv
        self.pasv = None
        if sock is None:
            return None
        try:
            sock.settimeout(20.0)
            conn, _ = sock.accept()
            conn.settimeout(30.0)
            return conn
        except OSError:
            return None
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def open_data(self, timeout: float = 20.0) -> Optional[socket.socket]:
        if self.pasv is not None:
            return self.accept_pasv()
        if self.guarded is not None:
            # PORT 之后已经接住的相机连接：直接交给数据线程，之后不再由其他线程碰它
            sock, self.guarded = self.guarded, None
            self.port_addr = None
            sock.settimeout(30.0)
            return sock
        addr = self.port_addr
        self.port_addr = None
        if addr is not None:
            # 重试：相机可能在收到 150 之后才去连接
            deadline = time.time() + 8.0
            while time.time() < deadline and not self.closed:
                try:
                    conn = socket.create_connection(addr, timeout=timeout)
                    conn.settimeout(30.0)
                    return conn
                except OSError as exc:
                    log.info("主动模式连接 %s 失败：%s", addr, exc)
                    time.sleep(0.2)
            return None
        return None

    # -- 主动模式：PORT 之后立即预连接 --------------------------------
    def guard_preconnect(self, quick_window: float = 0.35) -> None:
        """尝试在回复 200 之前把相机刚打开的数据连接接住。

        相机 / 客户端有时在收到 200 之前就去连 PORT 指定的端口，
        所以这里在后台线程里等一会儿，控制线程最多等 quick_window 秒，
        然后把接到的连接留到 STOR / RETR 时使用。
        """
        self.close_guarded()
        addr = self.port_addr
        if addr is None:
            return
        holder: dict = {}
        done = threading.Event()

        def grab():
            try:
                deadline = time.time() + 6.0
                while time.time() < deadline and not self.closed:
                    try:
                        sock = socket.create_connection(addr, timeout=0.8)
                    except OSError:
                        time.sleep(0.03)
                        continue
                    sock.settimeout(0.0)
                    holder["sock"] = sock
                    return
            finally:
                done.set()

        threading.Thread(target=grab, name="ftp-guard", daemon=True).start()
        done.wait(max(0.0, quick_window))
        sock = holder.get("sock")
        if sock is not None and not self.closed:
            self.guarded = sock


def cfg_photo_dir(cfg: Settings) -> str:
    return os.path.abspath(cfg.photo_dir)


# --------------------------------------------------------------------------- 上传任务

class _Upload:
    def __init__(self, server: "FtpServer", sess: _Session, remote: str, dest: str,
                 base_path: str, resume_at: int, size: int, keep_local_partial: bool):
        self.server = server
        self.id = uuid.uuid4().hex[:12]
        self.remote = remote
        self.dest = dest
        self.base_path = base_path      # 续传/追加时是已存在的目标文件
        self.resume_at = resume_at
        self.size = size
        self.keep_local_partial = keep_local_partial
        self.peer = sess.peer_ip
        self.received = 0
        self.started = time.time()
        self.finished = 0.0
        self.error: Optional[str] = None
        if base_path:
            # APPE / REST：在已有文件上继续写（复制到临时文件，成功后一次性替换）
            try:
                shutil.copyfile(base_path, dest)
            except OSError:
                pass
            self.f = open(dest, "r+b")
            self.f.truncate(resume_at)
            self.f.seek(resume_at)
        else:
            self.f = open(dest, "wb")
        self.filename = os.path.basename(base_path or dest.replace(".shutterdrop-part", ""))
        self.done = threading.Event()

    @property
    def total(self) -> int:
        return max(self.size, self.resume_at + self.received)

    def run(self, data_sock: socket.socket, ascii_mode: bool) -> None:
        server = self.server
        last_emit = 0.0
        try:
            pending_cr = False
            data_sock.settimeout(30.0)
            idle_since = time.time()
            while True:
                try:
                    chunk = data_sock.recv(256 * 1024)
                except socket.timeout:
                    if time.time() - idle_since > 120:
                        self.error = "传输超时（120 秒没有收到数据）"
                        break
                    continue
                if not chunk:
                    break
                idle_since = time.time()
                if ascii_mode:
                    if pending_cr:
                        chunk = b"\r" + chunk
                    pending_cr = chunk.endswith(b"\r")
                    if pending_cr:
                        chunk = chunk[:-1]
                    chunk = chunk.replace(b"\r\n", b"\n")
                self.f.write(chunk)
                self.received += len(chunk)
                server.total_bytes += len(chunk)
                now = time.time()
                if now - last_emit >= 0.1:
                    last_emit = now
                    server.emit(TransferProgress(self.id, self.resume_at + self.received, self.total))
        except OSError as exc:
            self.error = f"传输中断：{exc}"
            log.warning("上传 %s 中断：%s", self.remote, exc)
        finally:
            self.finished = time.time()
            try:
                self.f.close()
            except OSError:
                pass
            try:
                data_sock.close()
            except OSError:
                pass
            self._finalize()

    def _finalize(self) -> None:
        server = self.server
        final_path: Optional[str] = None
        target = self.base_path or self.dest.replace(".shutterdrop-part", "")
        if self.error is None:
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if os.path.exists(target) and not self.server.cfg.overwrite and not self.base_path:
                    target = unique_path(os.path.dirname(target), os.path.basename(target))
                os.replace(self.dest, target)
                final_path = target
            except OSError as exc:
                # 目标被其他程序占用时，退回到唯一文件名
                try:
                    alt = unique_path(os.path.dirname(target), os.path.basename(target))
                    os.replace(self.dest, alt)
                    final_path = alt
                except OSError as exc2:
                    self.error = f"保存失败：{exc2}"
                    log.error("保存失败 %s：%s", target, exc2)
        if final_path is None and not self.keep_local_partial:
            try:
                os.remove(self.dest)
            except OSError:
                pass
        size = self.resume_at + self.received
        ev = TransferFinished(
            id=self.id, remote=self.remote, filename=os.path.basename(final_path or target),
            path=final_path, size=size, duration=max(self.finished - self.started, 0.0),
            peer=self.peer, error=self.error, started=self.started, finished=self.finished,
        )
        server.emit(ev)
        self.done.set()


# --------------------------------------------------------------------------- 服务器

class FtpServer:
    """线程式 FTP 服务器（被动 + 主动模式）。"""

    def __init__(self, cfg: Settings, on_event: Optional[Callable[[object], None]] = None):
        self.cfg = cfg
        self.on_event = on_event
        self.listener: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self._sessions: list[_Session] = []
        self._sessions_lock = threading.Lock()
        self._stop = threading.Event()
        self.info = ServerInfo(False, cfg.ftp_port, "")
        self.port = cfg.ftp_port
        self.error = ""
        self.started_at = 0.0
        # 统计
        self.total_bytes = 0
        self.total_files = 0
        self.bytes_this_run = 0
        self.total_bytes_this_run = 0
        self.connected_at: dict[str, float] = {}
        self.last_upload_at = 0.0

    # -- 状态 -----------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.listener is not None

    def connected_clients(self) -> list[str]:
        with self._sessions_lock:
            return sorted({s.peer_ip for s in self._sessions if not s.closed})

    # -- 事件 -----------------------------------------------------------
    def emit(self, event: object) -> None:
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:  # 回调不能影响服务器
                log.exception("事件回调出错")

    # -- 生命周期 -------------------------------------------------------
    def start(self) -> bool:
        self.stop()
        self.error = ""
        port = int(self.cfg.ftp_port)
        sock = None
        for family, addr in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
            try:
                s = socket.socket(family, socket.SOCK_STREAM)
                if family == socket.AF_INET6:
                    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                else:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((addr, port))
                s.listen(16)
                s.settimeout(0.5)
                sock, self.port = s, port
                break
            except OSError as exc:
                self.error = (f"端口 {port} 无法监听：{exc}" +
                              ("（可能被其他 FTP 服务器占用，请在设置里换一个端口）"
                               if getattr(exc, "errno", 0) in (48, 98, 10048) or "in use" in str(exc) else ""))
                if family == socket.AF_INET6:
                    break
        if sock is None:
            log.error(self.error)
            self.info = ServerInfo(False, port, "", self.error)
            self.emit(ServerInfo(False, port, "", self.error))
            return False
        self.listener = sock
        self._stop.clear()
        self.started_at = time.time()
        self.bytes_this_run = 0
        self.total_bytes_this_run = 0
        self.thread = threading.Thread(target=self._accept_loop, name="ftp-accept", daemon=True)
        self.thread.start()
        self.info = ServerInfo(True, self.port, "0.0.0.0")
        self.emit(self.info)
        log.info("FTP 服务已启动，端口 %s", self.port)
        return True

    def stop(self) -> None:
        self._stop.set()
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass
            self.listener = None
        with self._sessions_lock:
            sessions = list(self._sessions)
            self._sessions.clear()
        for s in sessions:
            s.close()
        if self.thread is not None and self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
        self.thread = None
        self.info = ServerInfo(False, self.cfg.ftp_port, "", self.error)

    def restart(self, cfg: Settings) -> bool:
        self.cfg = cfg
        return self.start()

    # -- 接收循环 -------------------------------------------------------
    def _accept_loop(self) -> None:
        while not self._stop.is_set() and self.listener is not None:
            try:
                conn, addr = self.listener.accept()
            except socket.timeout:
                continue
            except ConnectionAbortedError:
                # Windows 上关闭监听后 accept 抛出此错误
                if self._stop.is_set() or self.listener is None:
                    break
                continue
            except OSError as exc:
                if self._stop.is_set():
                    break
                log.info("accept 出错：%s", exc)
                time.sleep(0.2)
                continue
            try:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                # 局域网：加大接收缓冲，提高小文件连续上传的吞吐
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
            except OSError:
                pass
            sess = _Session(self, conn, addr[0])
            with self._sessions_lock:
                self._sessions.append(sess)
            self.connected_at[addr[0]] = time.time()
            threading.Thread(target=self._serve, args=(sess,), name=f"ftp-{addr[0]}", daemon=True).start()

    def _serve(self, sess: _Session) -> None:
        log.info("客户端连接：%s", sess.peer_ip)
        self.emit(ClientEvent("connected", sess.peer_ip, text="相机已连接"))
        try:
            sess.conn.settimeout(0.5)
        except OSError:
            pass
        try:
            sess.accept_loop(self)
        finally:
            sess.close()
            with self._sessions_lock:
                if sess in self._sessions:
                    self._sessions.remove(sess)
            log.info("客户端断开：%s（共 %d 条命令）", sess.peer_ip, sess.commands)
            self.emit(ClientEvent("disconnected", sess.peer_ip, text="相机断开"))

    # -- 命令解析 -------------------------------------------------------
    def _handle(self, sess: _Session, line: str) -> bool:
        sess.commands += 1
        cmd, _, arg = line.partition(" ")
        cmd = cmd.upper().strip()
        arg = arg.strip()
        if cmd not in ("PASS",):  # 不记录密码
            log.debug("< %s", line if cmd != "PASS" else "PASS ***")
        handler = getattr(self, "_cmd_" + cmd, None)
        if handler is None:
            sess.send("502 Command not implemented.\r\n")
            return True
        try:
            keep = handler(sess, arg)
        except Exception:
            log.exception("处理命令 %s 失败", cmd)
            sess.send("451 Local error in processing.\r\n")
            keep = True
        return keep is not False

    # -- 认证与基础命令 -------------------------------------------------
    def _cmd_USER(self, sess: _Session, arg: str) -> None:
        sess.username = arg
        sess.send("331 Please specify the password.\r\n")

    def _cmd_PASS(self, sess: _Session, arg: str) -> None:
        user = getattr(sess, "username", "")
        if self.cfg.ftp_user and user != self.cfg.ftp_user:
            sess.send("530 Login incorrect.\r\n")
            return
        if arg != self.cfg.ftp_password:
            sess.send("530 Login incorrect.\r\n")
            return
        if not os.path.isdir(self.cfg.photo_dir):
            try:
                os.makedirs(self.cfg.photo_dir, exist_ok=True)
            except OSError as exc:
                sess.send(f"550 Storage directory unavailable ({exc}).\r\n")
                return
        sess.authenticated = True
        sess.send("230 Login successful.\r\n")

    def _require_login(self, sess: _Session) -> bool:
        if not getattr(sess, "authenticated", False):
            sess.send("530 Please login with USER and PASS.\r\n")
            return False
        return True

    def _cmd_ACCT(self, sess, arg):
        sess.send("230 Account ok.\r\n")

    def _cmd_SYST(self, sess, arg):
        sess.send("215 UNIX Type: L8\r\n")

    def _cmd_FEAT(self, sess, arg):
        sess.send("211-Features:\r\n EPSV\r\n PASV\r\n UTF8\r\n REST STREAM\r\n SIZE\r\n MDTM\r\n TVFS\r\n"
                  "211 End\r\n")

    def _cmd_OPTS(self, sess, arg):
        sess.send("200 Always in UTF8 mode.\r\n")

    def _cmd_NOOP(self, sess, arg):
        sess.send("200 OK.\r\n")

    def _cmd_QUIT(self, sess, arg):
        sess.send("221 Goodbye.\r\n")
        return False

    def _cmd_AUTH(self, sess, arg):
        sess.send("534 No TLS on this server. In the camera set [Secure Protocol] to [Off].\r\n")

    def _cmd_PBSZ(self, sess, arg):
        sess.send("502 PBSZ not supported (TLS disabled).\r\n")

    def _cmd_PROT(self, sess, arg):
        sess.send("502 PROT not supported (TLS disabled).\r\n")

    # -- 模式 / 参数 ----------------------------------------------------
    def _cmd_TYPE(self, sess: _Session, arg: str):
        arg = (arg or "I").upper()
        if arg.startswith("A"):
            sess.type = "A"
            sess.send("200 Switching to ASCII mode.\r\n")
        elif arg.startswith("I") or arg.startswith("L"):
            sess.type = "I"
            sess.send("200 Switching to Binary mode.\r\n")
        else:
            sess.send("504 Unsupported type.\r\n")

    def _cmd_MODE(self, sess, arg):
        if (arg or "S").upper() == "S":
            sess.send("200 Mode set to S.\r\n")
        else:
            sess.send("504 Only stream mode is supported.\r\n")

    def _cmd_STRU(self, sess, arg):
        if (arg or "F").upper() == "F":
            sess.send("200 Structure set to F.\r\n")
        else:
            sess.send("504 Only file structure is supported.\r\n")

    def _cmd_ALLO(self, sess, arg):
        sess.send("202 ALLO not needed.\r\n")

    def _cmd_REST(self, sess: _Session, arg: str):
        try:
            sess.rest_offset = max(0, int(arg))
            sess.send(f"350 Restarting at {sess.rest_offset}. Send STORE or RETRIEVE.\r\n")
        except ValueError:
            sess.send("501 Bad REST argument.\r\n")

    def _cmd_ABOR(self, sess: _Session, arg: str):
        sess.close_pasv()
        sess.port_addr = None
        sess.send("226 ABOR successful.\r\n")

    def _cmd_SITE(self, sess: _Session, arg: str):
        cmd = (arg or "").split(" ")[0].upper()
        if cmd == "CHMOD":
            sess.send("200 CHMOD ignored.\r\n")
        else:
            sess.send("500 SITE command unknown.\r\n")

    def _cmd_MLSD(self, sess, arg):
        sess.send("500 MLSD not supported (use LIST).\r\n")

    def _cmd_MLST(self, sess, arg):
        sess.send("500 MLST not supported.\r\n")

    # -- 路径 -----------------------------------------------------------
    def _resolve(self, sess: _Session, arg: str, allow_missing: bool = True) -> Optional[str]:
        """把客户端路径解析成保存目录下的绝对路径。"""
        arg = (arg or "").strip()
        if not arg or arg in (".", "/"):
            rel = _norm_remote(sess.cwd)
        elif arg.startswith("/"):
            rel = _norm_remote(arg)
        else:
            rel = _norm_remote(sess.cwd + "/" + arg)
        base = os.path.abspath(self.cfg.photo_dir)
        target = os.path.abspath(os.path.join(base, *rel.split("/"))) if rel else base
        if target != base and not target.startswith(base + os.sep):
            return None
        return target

    def _remote_of(self, sess: _Session, arg: str) -> str:
        arg = (arg or "").strip()
        if not arg or arg in (".", "/"):
            return sess.cwd
        if arg.startswith("/"):
            return "/" + _norm_remote(arg)
        return "/" + _norm_remote(sess.cwd + "/" + arg)

    def _cmd_PWD(self, sess: _Session, arg: str):
        sess.send(f'257 "{sess.cwd}" is current directory.\r\n')

    _cmd_XPWD = _cmd_PWD

    def _cmd_CWD(self, sess: _Session, arg: str):
        target = self._resolve(sess, arg)
        if target is None or not os.path.isdir(target):
            sess.send("550 Failed to change directory.\r\n")
            return
        sess.cwd = self._remote_of(sess, arg)
        sess.send("250 Directory successfully changed.\r\n")

    _cmd_XCWD = _cmd_CWD

    def _cmd_CDUP(self, sess: _Session, arg: str):
        if sess.cwd not in ("", "/"):
            parts = sess.cwd.strip("/").split("/")
            sess.cwd = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
        sess.send("250 Directory successfully changed.\r\n")

    _cmd_XCUP = _cmd_CDUP

    def _cmd_MKD(self, sess: _Session, arg: str):
        target = self._resolve(sess, arg)
        if target is None:
            sess.send("550 Invalid path.\r\n")
            return
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as exc:
            log.info("MKD 失败：%s", exc)
            sess.send("550 Create directory operation failed.\r\n")
            return
        sess.send(_shell_reply("MKD", self._remote_of(sess, arg)) + "\r\n")

    _cmd_XMKD = _cmd_MKD

    def _cmd_RMD(self, sess: _Session, arg: str):
        target = self._resolve(sess, arg)
        base = os.path.abspath(self.cfg.photo_dir)
        if target is None or target == base or not os.path.isdir(target):
            sess.send("550 Remove directory operation failed.\r\n")
            return
        try:
            os.rmdir(target)
            sess.send("250 Remove directory operation successful.\r\n")
        except OSError:
            sess.send("550 Remove directory operation failed.\r\n")

    _cmd_XRMD = _cmd_RMD

    def _cmd_DELE(self, sess: _Session, arg: str):
        target = self._resolve(sess, arg)
        if target is None or not os.path.isfile(target):
            sess.send("550 Delete operation failed.\r\n")
            return
        try:
            os.remove(target)
            sess.send("250 Delete operation successful.\r\n")
        except OSError:
            sess.send("550 Delete operation failed.\r\n")

    def _cmd_RNFR(self, sess: _Session, arg: str):
        target = self._resolve(sess, arg)
        if target is None or not os.path.exists(target):
            sess.send("550 RNFR command failed.\r\n")
            return
        sess.rename_from = arg
        sess.send("350 Ready for RNTO.\r\n")

    def _cmd_RNTO(self, sess: _Session, arg: str):
        if not sess.rename_from:
            sess.send("503 RNFR required first.\r\n")
            return
        src = self._resolve(sess, sess.rename_from)
        dst = self._resolve(sess, arg)
        sess.rename_from = None
        if src is None or dst is None:
            sess.send("550 Rename failed.\r\n")
            return
        try:
            if os.path.exists(dst) and not self.cfg.overwrite:
                dst = unique_path(os.path.dirname(dst), os.path.basename(dst))
            os.replace(src, dst)
            sess.send("250 Rename successful.\r\n")
        except OSError:
            sess.send("550 Rename failed.\r\n")

    def _cmd_SIZE(self, sess: _Session, arg: str):
        target = self._resolve(sess, arg)
        if target is None or not os.path.isfile(target):
            sess.send("550 Could not get file size.\r\n")
            return
        sess.send(f"213 {os.path.getsize(target)}\r\n")

    def _cmd_MDTM(self, sess: _Session, arg: str):
        target = self._resolve(sess, arg)
        if target is None or not os.path.isfile(target):
            sess.send("550 Could not get modification time.\r\n")
            return
        t = datetime.utcfromtimestamp(os.path.getmtime(target))
        sess.send(t.strftime("213 %Y%m%d%H%M%S\r\n"))

    def _cmd_STAT(self, sess: _Session, arg: str):
        if arg:
            target = self._resolve(sess, arg)
            if target is None or not os.path.exists(target):
                sess.send("550 File not found.\r\n")
                return
            try:
                st = os.stat(target)
            except OSError:
                sess.send("550 File not found.\r\n")
                return
            sess.send(f"213-Status follows:\r\n{self._list_line(target, st)}\r\n213 End.\r\n")
        else:
            sess.send("211 Connected to ShutterDrop FTP.\r\n")

    def _cmd_HELP(self, sess, arg):
        sess.send("214 ShutterDrop FTP server\r\n")

    def _cmd_SITE_HELP(self, sess, arg):
        sess.send("214 No SITE commands.\r\n")

    # -- 列表 -----------------------------------------------------------
    @staticmethod
    def _list_line(path: str, st: os.stat_result) -> str:
        name = os.path.basename(path)
        is_dir = os.path.isdir(path)
        mode = "drwxr-xr-x" if is_dir else "-rw-r--r--"
        size = 4096 if is_dir else st.st_size
        mt = time.localtime(st.st_mtime)
        return (f"{mode} 1 owner group {size:>12} "
                f"{time.strftime('%b %d %H:%M', mt)} {name}")

    def _do_list(self, sess: _Session, arg: str, names_only: bool) -> bool:
        target = self._resolve(sess, arg)
        if target is None or not os.path.exists(target):
            sess.send("550 File not found.\r\n")
            return True
        sess.send("150 Opening data connection for directory list.\r\n")
        conn = sess.open_data()
        if conn is None:
            sess.send("425 Can't open data connection.\r\n")
            return True
        lines: list[str] = []
        try:
            if os.path.isdir(target):
                for entry in sorted(os.listdir(target)):
                    full = os.path.join(target, entry)
                    try:
                        st = os.stat(full)
                    except OSError:
                        continue
                    lines.append(entry if names_only else self._list_line(full, st))
            else:
                st = os.stat(target)
                name = os.path.basename(target)
                lines.append(name if names_only else self._list_line(target, st))
            payload = ("\r\n".join(lines) + ("\r\n" if lines else "")).encode("utf-8")
            conn.sendall(payload)
            conn.close()
            sess.send("226 Directory send OK.\r\n")
        except OSError:
            sess.send("426 Data connection error.\r\n")
        return True

    def _cmd_LIST(self, sess: _Session, arg: str):
        return self._do_list(sess, arg, names_only=False)

    def _cmd_NLST(self, sess: _Session, arg: str):
        return self._do_list(sess, arg, names_only=True)

    # -- 数据通道 -------------------------------------------------------
    def _bound_ip_for(self, sess: _Session) -> str:
        """被动模式监听使用的本机地址（与客户端同网段）。"""
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.settimeout(0.2)
            probe.connect((sess.peer_ip, 9))
            ip = probe.getsockname()[0]
            probe.close()
            return ip
        except OSError:
            return "0.0.0.0"

    def _open_pasv(self, sess: _Session, epsv: bool) -> None:
        sess.close_pasv()
        sess.port_addr = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self._bound_ip_for(sess), 0))
            s.listen(4)
        except OSError as exc:
            log.info("打开被动端口失败：%s", exc)
            sess.send("425 Can't open passive connection.\r\n")
            return
        sess.pasv = s
        port = s.getsockname()[1]
        if epsv:
            sess.send(f"229 Entering Extended Passive Mode (|||{port}|)\r\n")
        else:
            # 注意：这里用“控制连接的本地地址”汇报，保证多网卡时相机连到对的网卡
            try:
                local_ip = sess.conn.getsockname()[0]
            except OSError:
                local_ip = "127.0.0.1"
            if local_ip.startswith("::"):
                local_ip = "127.0.0.1"
            a, b, c, d = local_ip.split(".")
            sess.send(f"227 Entering Passive Mode ({a},{b},{c},{d},{port >> 8},{port & 0xFF}).\r\n")

    def _cmd_PASV(self, sess: _Session, arg: str):
        self._open_pasv(sess, epsv=False)

    def _cmd_EPSV(self, sess: _Session, arg: str):
        self._open_pasv(sess, epsv=True)

    def _cmd_PORT(self, sess: _Session, arg: str) -> None:
        nums = arg.replace(" ", "").split(",")
        if len(nums) != 6 or not all(n.isdigit() for n in nums):
            sess.send("501 Illegal PORT command.\r\n")
            return
        h = ".".join(nums[:4])
        port = int(nums[4]) * 256 + int(nums[5])
        # 防止打洞到第三方主机；若相机报 0.0.0.0 或其它地址，则用控制连接对端地址
        if h in ("0.0.0.0", "127.0.0.1") or h != sess.peer_ip:
            h = sess.peer_ip
        sess.close_pasv()
        sess.port_addr = (h, port)
        sess.epsv = False
        log.info("PORT %s:%s", h, port)
        # 部分相机（A7 系列实测如此）会在收到 200 之前就去连 PORT 指定的端口；
        # 先帮它把连接接住，然后才回 200，两种顺序都能正常工作。
        sess.guard_preconnect()
        sess.send("200 PORT command successful.\r\n")

    def _cmd_EPRT(self, sess: _Session, arg: str) -> None:
        # 格式：|1|addr|port|
        parts = arg.split("|")
        if len(parts) < 4:
            sess.send("501 Illegal EPRT command.\r\n")
            return
        h, port_s = parts[2], parts[3]
        try:
            port = int(port_s)
        except ValueError:
            sess.send("501 Illegal EPRT command.\r\n")
            return
        if h in ("0.0.0.0", "127.0.0.1") or h != sess.peer_ip:
            h = sess.peer_ip
        sess.close_pasv()
        sess.port_addr = (h, port)
        sess.epsv = True
        log.info("EPRT %s:%s", h, port)
        sess.guard_preconnect()
        sess.send("200 EPRT command successful.\r\n")

    # -- 上传 -----------------------------------------------------------
    def _upload_path(self, sess: _Session, arg: str) -> Optional[str]:
        remote = self._remote_of(sess, arg)
        if not remote or remote.endswith("/"):
            return None
        name = remote.split("/")[-1]
        if not name or name in (".", ".."):
            return None
        base = os.path.abspath(self.cfg.photo_dir)
        rel = remote.strip("/").rsplit("/", 1)[0] if "/" in remote.strip("/") else ""
        try:
            folder = os.path.abspath(os.path.join(base, *[p for p in rel.split("/") if p]))
        except (OSError, ValueError):
            return None
        if folder != base and not folder.startswith(base + os.sep):
            return None
        return os.path.join(folder, safe_filename(name))

    def _cmd_STOR(self, sess: _Session, arg: str):
        return self._do_store(sess, arg, append=False)

    def _cmd_APPE(self, sess: _Session, arg: str):
        return self._do_store(sess, arg, append=True)

    def _do_store(self, sess: _Session, arg: str, append: bool) -> bool:
        if not self._require_login(sess):
            return True
        dest = self._upload_path(sess, arg)
        if dest is None:
            sess.send("550 Invalid file name.\r\n")
            return True
        remote = self._remote_of(sess, arg)
        ext = os.path.splitext(dest)[1].lower()
        # 只接受图片/视频类文件，避免任何意外内容写入磁盘
        if ext and ext not in IMAGE_EXTS:
            sess.send("553 File type not accepted by ShutterDrop.\r\n")
            log.info("拒绝非图片文件：%s", remote)
            return True
        folder = os.path.dirname(dest)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            log.info("创建目录失败 %s：%s", folder, exc)
            sess.send("550 Could not create destination directory.\r\n")
            return True

        # 服务器会自己清理临时文件；用户级设置中的“同名覆盖”决定落盘文件名
        resume_at = 0
        base_path = ""
        if (append or sess.rest_offset) and os.path.exists(dest) and not self.cfg.overwrite:
            base_path = dest
            resume_at = os.path.getsize(dest) if append else min(sess.rest_offset, os.path.getsize(dest))
        sess.rest_offset = 0
        tmp = dest + ".shutterdrop-part"
        size = 0
        try:
            upload = _Upload(self, sess, remote, tmp, base_path, resume_at, size,
                             keep_local_partial=False)
        except OSError as exc:
            sess.send(f"550 Cannot create file: {exc}\r\n")
            return True

        sess.send("150 Ok to send data.\r\n")
        self.emit(TransferStarted(upload.id, remote, upload.filename,
                                  size, base_path or dest, sess.peer_ip))
        sock = sess.open_data()
        if sock is None:
            upload.error = "无法建立数据连接（相机与电脑可能不在同一网段，或防火墙拦截）"
            upload.finished = time.time()
            try:
                upload.f.close()
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            upload.server.emit(TransferFinished(
                id=upload.id, remote=remote, filename=upload.filename, path=None,
                size=0, duration=0.0, peer=sess.peer_ip, error=upload.error))
            sess.send("425 Can't open data connection.\r\n")
            log.warning("数据连接失败：%s -> %s", arg, upload.error)
            return True

        def worker():
            upload.run(sock, sess.type == "A")
            self.total_files += 1
            self.last_upload_at = time.time()
            if upload.error is None:
                sess.send("226 Transfer complete.\r\n")
            else:
                sess.send("451 Transfer aborted.\r\n")

        threading.Thread(target=worker, name=f"ftp-up-{upload.id}", daemon=True).start()
        return True

    # -- 下载（PlayStation 式工具可能需要；相机不需要）--------------------
    def _cmd_RETR(self, sess: _Session, arg: str):
        if not self._require_login(sess):
            return True
        target = self._resolve(sess, arg)
        if target is None or not os.path.isfile(target):
            sess.send("550 File not found.\r\n")
            return True
        sess.send("150 Opening data connection.\r\n")
        conn = sess.open_data()
        if conn is None:
            sess.send("425 Can't open data connection.\r\n")
            return True

        def worker():
            try:
                with open(target, "rb") as f:
                    while True:
                        chunk = f.read(256 * 1024)
                        if not chunk:
                            break
                        conn.sendall(chunk)
                conn.close()
                sess.send("226 Transfer complete.\r\n")
            except OSError:
                sess.send("426 Transfer aborted.\r\n")

        threading.Thread(target=worker, daemon=True).start()
        return True
