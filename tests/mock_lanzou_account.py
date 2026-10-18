"""
最小蓝奏"账号接口"复刻（本地 HTTP 服务），用来测发布端。

覆盖：登录（302 + alert 文本）、列/建文件夹、列/删文件、分享、流式上传。
上传会真的解析 multipart，并按真实行为处理同名文件（自动改名成 name(1).ext）。
"""
from __future__ import annotations

import http.server
import json
import re
import sys
import threading
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_lanzou import MockLanzou


class _AccountState:
    def __init__(self, uid: str, password: str):
        self.uid = uid
        self.password = password
        self.next_folder = 1000
        self.next_file = 5000
        self.folders: dict[int, dict] = {}
        self.files: dict[int, dict] = {}
        self.uploads: list[str] = []
        self.deleted: list[str] = []
        self.fail_uploads: set[str] = set()
        self.rename_uploads: set[str] = set()
        self.share_factory = None
        self.lock = threading.Lock()

    def create_folder(self, name: str, parent: int) -> int:
        folder_id = self.next_folder
        self.next_folder += 1
        self.folders[folder_id] = {"name": name, "parent": parent}
        return folder_id

    def create_file(self, name: str, folder: int, data: bytes) -> dict:
        file_id = self.next_file
        self.next_file += 1
        self.files[file_id] = {"name": name, "folder": folder, "data": data}
        return {"id": file_id, "name": name, "size": len(data)}


class _Handler(http.server.BaseHTTPRequestHandler):
    state: _AccountState = None      # type: ignore[assignment]
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    # ---------- 基础 ----------
    def _send(self, status: int, body, ctype="text/html; charset=utf-8",
              headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200):
        self._send(status, json.dumps(payload, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _form(self) -> dict:
        raw = self._body().decode("utf-8", "replace")
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}

    def _cookie(self, name: str) -> str:
        raw = self.headers.get("Cookie") or ""
        for chunk in raw.split(";"):
            if "=" in chunk:
                key, value = chunk.split("=", 1)
                if key.strip() == name:
                    return value.strip()
        return ""

    def _logged_in(self) -> bool:
        return self._cookie("ylogin") == self.state.uid

    # ---------- 路由 ----------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/accounts.php":
            # 新版登录页：JS 里带 task / ref，页面上还有 acw 校验（这里从简）
            return self._send(200, "<html><script>var task ='uselogin';"
                                   "var ref ='test';</script></html>")
        if path == "/auth":
            # 中转鉴权：种下 ylogin cookie 再跳回网盘
            return self._send(302, "ok", headers={
                "Location": "/mydisk.php",
                "Set-Cookie": f"ylogin={self.state.uid}; Path=/"})
        if path == "/mydisk.php":
            return self._send(200, "ok")
        return self._send(404, "not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/accounts.php":
            return self._login_new()
        if path == "/mydisk.php":
            return self._login()
        if path == "/doupload.php":
            return self._doupload(self._form())
        if path in ("/html5up.php", "/fileup.php"):
            return self._upload()
        return self._send(404, "not found")

    # ---------- 登录 ----------
    def _login_new(self):
        """新版登录：POST accounts.php → {"zt":"1","msgs":"<中转地址>"}。"""
        form = self._form()
        user = str(form.get("username") or "")
        pwd = str(form.get("password") or "")
        if user != self.state.uid or pwd != self.state.password:
            return self._json({"zt": "0", "msgs": "账号或密码错误"})
        base = f"http://{self.headers.get('Host')}"
        return self._json({"zt": "1", "msgs": f"{base}/auth",
                           "usename": user})

    def _login(self):
        form = self._form()
        if form.get("uid") != self.state.uid or form.get("pwd") != self.state.password:
            body = '<script>alert("密码错误");</script>'
            return self._send(302, body, headers={"Location": "/mydisk.php"})
        body = '<script>alert("登录成功");</script>'
        return self._send(302, body, headers={
            "Location": "/mydisk.php?item=files&action=index",
            "Set-Cookie": f"ylogin={self.state.uid}; Path=/"})

    # ---------- 文件夹 / 文件 ----------
    def _doupload(self, form: dict):
        if not self._logged_in():
            return self._json({"zt": 0, "info": "未登录"})
        state = self.state
        task = str(form.get("task") or "")
        if task == "47":
            parent = int(form.get("folder_id") or -1)
            rows = [{"fol_id": str(fid), "name": info["name"]}
                    for fid, info in sorted(state.folders.items())
                    if info["parent"] == parent]
            return self._json({"zt": 1, "text": rows})
        if task == "2":
            parent = int(form.get("parent_id") or -1)
            name = form.get("folder_name") or ""
            for fid, info in state.folders.items():
                if info["parent"] == parent and info["name"] == name:
                    return self._json({"zt": 1, "text": str(fid)})
            fid = state.create_folder(name, parent)
            return self._json({"zt": 1, "text": str(fid)})
        if task == "5":
            folder = int(form.get("folder_id") or -1)
            rows = [{"id": str(fid), "name_all": info["name"],
                     "size": f"{len(info['data']) / 1024:.1f} K"}
                    for fid, info in sorted(state.files.items())
                    if info["folder"] == folder]
            return self._json({"zt": 1, "text": rows})
        if task == "6":
            file_id = int(form.get("file_id") or 0)
            info = state.files.pop(file_id, None)
            if info is None:
                return self._json({"zt": 0, "info": "文件不存在"})
            state.deleted.append(info["name"])
            return self._json({"zt": 1, "info": "已删除"})
        if task == "3":
            folder_id = int(form.get("folder_id") or 0)
            state.folders.pop(folder_id, None)
            return self._json({"zt": 1, "info": "已删除"})
        if task == "18":
            folder_id = int(form.get("folder_id") or -1)
            if state.share_factory is not None:
                url, pwd = state.share_factory(folder_id)
            else:
                base = f"http://{self.headers.get('Host')}"
                url, pwd = f"{base}/share/{folder_id}", "share"
            return self._json({"zt": 1, "info": {"is_newd": url, "pwd": pwd}})
        if task == "1":
            used = sum(len(f["data"]) for f in state.files.values())
            return self._json({"zt": 1, "text": {"used": used,
                                                 "total": 10 * 1024 ** 3}})
        return self._json({"zt": 0, "info": f"未知 task {task}"})

    # ---------- 上传 ----------
    def _upload(self):
        if not self._logged_in():
            return self._json({"zt": 0, "info": "未登录"})
        raw = self._body()
        content_type = self.headers.get("Content-Type") or ""
        match = re.search(r"boundary=(.+)$", content_type)
        if not match:
            return self._json({"zt": 0, "info": "缺少 boundary"})
        fields, filename, data = _parse_multipart(raw, match.group(1).strip())
        name = fields.get("name") or filename
        folder = int(fields.get("folder_id_bb_n") or -1)
        state = self.state
        if name in state.fail_uploads:
            return self._json({"zt": 0, "info": "上传失败（模拟）"})
        if name in state.rename_uploads:
            stored = _renamed(name)
            state.rename_uploads.discard(name)
        else:
            stored = name
        # 真实行为：同名自动改名
        if any(f["name"] == stored and f["folder"] == folder
               for f in state.files.values()):
            stored = _renamed(stored)
        info = state.create_file(stored, folder, data)
        state.uploads.append(stored)
        return self._json({"zt": 1, "text": [{"id": str(info["id"]),
                                              "name_all": stored}]})


def _renamed(name: str) -> str:
    if "." in name:
        stem, suffix = name.rsplit(".", 1)
        return f"{stem}(1).{suffix}"
    return f"{name}(1)"


def _parse_multipart(raw: bytes, boundary: str):
    """极简 multipart 解析：够测试用。"""
    delimiter = ("--" + boundary).encode()
    fields: dict[str, str] = {}
    filename = ""
    payload = b""
    for chunk in raw.split(delimiter):
        if not chunk or chunk in (b"--\r\n", b"--"):
            continue
        chunk = chunk.strip(b"\r\n")
        if b"\r\n\r\n" not in chunk:
            continue
        head, body = chunk.split(b"\r\n\r\n", 1)
        head_text = head.decode("utf-8", "replace")
        name_match = re.search(r'name="([^"]+)"', head_text)
        file_match = re.search(r'filename="([^"]*)"', head_text)
        body = body.rstrip(b"\r\n")
        if file_match:
            filename = file_match.group(1)
            payload = body
        elif name_match:
            fields[name_match.group(1)] = body.decode("utf-8", "replace")
    return fields, filename, payload


class MockLanzouAccount:
    def __init__(self, uid: str = "123456", password: str = "secret"):
        self.state = _AccountState(uid, password)
        self._server = None
        self._shares: dict[int, MockLanzou] = {}

    def start(self) -> str:
        handler = type("_BoundHandler", (_Handler,), {"state": self.state})
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        self.state.share_factory = self.share_url
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self.base

    def stop(self) -> None:
        for share in self._shares.values():
            share.stop()
        self._shares.clear()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def share_server(self, folder_id: int):
        """拿到某个文件夹背后的分享服务（测试注入故障用）。"""
        return self._shares.get(folder_id)

    def share_url(self, folder_id: int) -> tuple[str, str]:
        """把某个文件夹"分享"出去：返回 (分享链接, 密码)。"""
        files = {info["name"]: info["data"]
                 for info in self.state.files.values()
                 if info["folder"] == folder_id}
        share = self._shares.get(folder_id)
        if share is None:
            share = MockLanzou(files, password="share",
                               share_id=f"b{folder_id}")
            share.start()
            self._shares[folder_id] = share
        else:
            share.set_files(files)
        return share.url, "share"

    @property
    def base(self) -> str:
        port = self._server.server_address[1] if self._server else 0
        return f"http://127.0.0.1:{port}"

    # ---------- 测试辅助 ----------
    def files_in(self, folder_id: int) -> dict[str, bytes]:
        return {info["name"]: info["data"]
                for info in self.state.files.values()
                if info["folder"] == folder_id}

    def folder_id(self, name: str, parent: int = -1) -> int | None:
        for fid, info in self.state.folders.items():
            if info["parent"] == parent and info["name"] == name:
                return fid
        return None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False
