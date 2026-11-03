"""严格的 FTP 控制连接客户端：每次只读一行回复。

模拟较老的相机 / 客户端在“主动模式（PORT）”下的行为：
PORT 之后立刻建立数据连接，然后才发送 STOR。
"""
import socket


class LineFTP:
    def __init__(self, host, port, timeout=15):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.f = self.s.makefile("rb")

    def readline(self):
        return self.f.readline().decode("utf-8", "replace").strip()

    def cmd(self, line):
        self.s.sendall((line + "\r\n").encode("utf-8"))
        resp = self.readline()
        if len(resp) > 3 and resp[3] == "-":        # 多行回复
            code = resp[:3]
            while True:
                nxt = self.readline()
                if nxt.startswith(code + " "):
                    return nxt
        return resp

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


def port_mode_upload(host, port, local_file, remote_name, user="sony", password="sony1234",
                     strict_order=True):
    """模拟相机主动模式上传。

    strict_order=True：PORT 之后立刻建数据连接（老相机常见做法）
    strict_order=False：收到 150 之后才建数据连接（标准做法）
    """
    s = socket.create_connection((host, port), timeout=15)
    buf = b""

    def readline():
        nonlocal buf
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                raise ConnectionError("控制连接已关闭")
            buf += chunk
        line, buf = buf.split(b"\n", 1)
        return line.strip().decode("utf-8", "replace")

    def cmd(line):
        s.sendall((line + "\r\n").encode("utf-8"))
        return readline()

    log = [readline(), cmd("USER " + user), cmd("PASS " + password), cmd("TYPE I")]
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    p = listener.getsockname()[1]
    log.append(cmd(f"PORT 127,0,0,1,{p >> 8},{p & 0xFF}"))
    # 服务器会在回复 200 之前尝试回连；这里先把连接接住，两种顺序都覆盖到
    listener.settimeout(3.0)
    try:
        data, _peer = listener.accept()
    except socket.timeout:
        data = None
    if strict_order:
        if data is None:
            data = socket.create_connection((host, p), timeout=10)
        listener.close()
        r = cmd(f"STOR {remote_name}")
        log.append(r)
        assert r.startswith("150"), (r, log)
    else:
        listener.close()
        r = cmd(f"STOR {remote_name}")
        log.append(r)
        assert r.startswith("150"), (r, log)
        if data is None:
            data = socket.create_connection((host, p), timeout=10)
    with open(local_file, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            data.sendall(chunk)
    data.close()
    log.append(readline())        # 226
    s.close()
    return log
