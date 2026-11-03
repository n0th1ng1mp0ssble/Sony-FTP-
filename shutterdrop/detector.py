"""相机在线状态检测。

索尼相机的 Wi-Fi / USB-LAN 网络用的是固定端口：
  * 21   —— FTP 控制连接（FTP 功能开启且已连接主机时处于监听状态）
  * 15740 —— PTP/IP（Creators' App / 遥控 / PC 遥控）
  * 64321、8080 —— 相机移动端连接服务
只要其中任一端口能建立 TCP 连接，就可以认为相机在网络上、并且已经开机。

因为我们自己的 FTP 服务可能也运行在 2121 端口，所以“端口探测”不会误判：
探测的是相机地址而不是本机，且端口固定。
"""
from __future__ import annotations

import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .core import guess_camera_subnets

CAMERA_PORTS = (21, 15740, 64321)
TYPICAL_HOSTS = (1, 2, 3, 4, 5, 10, 11, 20, 21, 30, 31, 40, 50, 100, 101, 102, 103, 104, 200)


def probe(ip: str, timeout: float = 0.35) -> bool:
    for port in CAMERA_PORTS:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


@dataclass
class DetectionResult:
    ip: str
    reachable: bool
    scan: bool                 # 是否做了网段扫描
    scanned: int               # 扫描的地址数量
    elapsed: float
    at: float


class CameraDetector:
    def __init__(self, fixed_ip: str = ""):
        self.fixed_ip = (fixed_ip or "").strip()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._busy = False
        self.result: DetectionResult | None = None
        self.subnets: list[str] = []
        self.on_result = None            # Callable[[DetectionResult], None]
        self.on_scan_state = None        # Callable[[bool, str], None]

    # ------------------------------------------------------------------
    def set_fixed_ip(self, ip: str) -> None:
        self.fixed_ip = (ip or "").strip()

    def start(self, interval: int = 4) -> None:
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(max(2, int(interval)),),
                                        name="camera-detect", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None

    def poke(self) -> None:
        """立即做一次检测（不阻塞调用方）。"""
        threading.Thread(target=self._detect_once, name="camera-detect-poke", daemon=True).start()

    # ------------------------------------------------------------------
    def _loop(self, interval: int) -> None:
        while not self._stop.is_set():
            try:
                self._detect_once()
            except Exception:
                pass
            self._stop.wait(interval)

    def _detect_once(self) -> DetectionResult | None:
        if self._busy:
            return self.result
        self._busy = True
        t0 = time.time()
        try:
            if self.fixed_ip:
                res = DetectionResult(self.fixed_ip, probe(self.fixed_ip, 0.6), False, 1,
                                      time.time() - t0, time.time())
            else:
                from .core import local_ipv4s
                own = local_ipv4s()
                self.subnets = guess_camera_subnets(own)
                ips = [f"{prefix}{h}" for prefix in self.subnets for h in TYPICAL_HOSTS]
                if self.on_scan_state:
                    try:
                        self.on_scan_state(True, f"正在扫描 {len(self.subnets)} 个网段…")
                    except Exception:
                        pass
                found = ""
                with ThreadPoolExecutor(max_workers=48) as pool:
                    futures = {pool.submit(probe, ip, 0.3): ip for ip in ips}
                    deadline = time.time() + 2.5
                    for fut, ip in futures.items():
                        if self._stop.is_set():
                            break
                        if time.time() > deadline:
                            break
                        try:
                            if fut.result(timeout=max(0.05, deadline - time.time())):
                                found = ip
                                break
                        except Exception:
                            continue
                res = DetectionResult(found, bool(found), True, len(ips),
                                      time.time() - t0, time.time())
            self.result = res
            if self.on_scan_state:
                try:
                    self.on_scan_state(False, "")
                except Exception:
                    pass
            if self.on_result:
                try:
                    self.on_result(res)
                except Exception:
                    pass
            return res
        finally:
            self._busy = False
