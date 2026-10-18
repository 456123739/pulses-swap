"""
最小蓝奏云复刻（本地 HTTP 服务），用来把下载链路完整跑一遍。

复刻了真实链路的每一步，包括：

  · 分享页里的 t / k 变量名随机化
  · 密码校验
  · iframe → apifile → 下载页 → ajax.php → 文件本体
  · acw_sc__v2 人机校验（第一次请求返回挑战页，解出 cookie 后才给页面）
  · 一次性令牌（下载页的 file/sign 只能用一次）

还支持故障注入：让某个文件连续失败 N 次、或返回被篡改的字节，
用来验证重试与校验逻辑。
"""
from __future__ import annotations

import http.server
import json
import os
import random
import re
import string
import sys
import threading
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online import acw  # noqa: E402


def _rand_name(prefix: str) -> str:
    return prefix + "".join(random.choice(string.ascii_lowercase) for _ in range(5))


class _State:
    def __init__(self, files: dict[str, bytes], password: str, share_id: str):
        self.files = dict(files)
        self.password = password
        self.share_id = share_id
        self.ids = {name: f"i{index:06d}" for index, name in enumerate(self.files)}
        self.fid = "13321739"
        self.uid = "4654636"
        self.puid = "BjJTMglhUjIIaAJnBmRRfVY9"
        self.token_t = ""
        self.token_k = ""
        self.token_names = ("", "")
        self.signs: dict[str, str] = {}
        self.challenges: dict[str, str] = {}
        self.page_tokens: dict[str, str] = {}
        self.final_tokens: dict[str, str] = {}
        self.requests: list[str] = []
        self.fail_next: dict[str, int] = {}
        self.corrupt: set[str] = set()
        self.webpage: set[str] = set()
        self.lock = threading.Lock()
        self.refresh_share_tokens()

    def refresh_share_tokens(self) -> None:
        self.token_t = str(int(1_760_000_000 + random.randint(0, 9999)))
        self.token_k = "".join(random.choice("0123456789abcdef") for _ in range(32))
        self.token_names = (_rand_name("ib"), _rand_name("_h"))


class _Handler(http.server.BaseHTTPRequestHandler):
    state: _State = None            # type: ignore[assignment]
    protocol_version = "HTTP/1.1"

    # ---------- 工具 ----------
    def log_message(self, *args):    # 静音
        pass

    def _send(self, status: int, body: bytes, ctype="text/html; charset=utf-8",
              extra_headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
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

    # ---------- 路由 ----------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        state = self.state
        with state.lock:
            state.requests.append(self.path)

        if path == f"/{state.share_id}":
            return self._share_page()

        if path == "/fn":
            return self._frame(query)

        if path.startswith("/file/"):
            if "f" in query:
                return self._serve_final(query["f"][0])
            return self._download_page(path.rsplit("/", 1)[-1])

        file_id = path.lstrip("/")
        if file_id in state.ids.values():
            return self._file_page(file_id)

        return self._send(404, "not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        form = self._form()
        with self.state.lock:
            self.state.requests.append(self.path)

        if path == "/filemoreajax.php":
            return self._file_list(form)
        if path == "/apifile":
            return self._apifile(form)
        if path == "/file/ajax.php":
            return self._ajax_download(form)
        return self._send(404, "not found")

    # ---------- 分享页 ----------
    def _share_page(self):
        state = self.state
        t_name, k_name = state.token_names
        html = f"""<!DOCTYPE html><html><head><title>文件列表</title></head><body>
<script>
var {t_name} = '{state.token_t}';
var {k_name} = '{state.token_k}';
var pgs = 1;
function file(){{
  $.ajax({{ type:'post', url:'/filemoreajax.php?file={state.fid}',
    data: {{'lx':2,'fid':{state.fid},'uid':'{state.uid}','puid':'{state.puid}',
            'pg':pgs,'rep':'0','t':{t_name},'k':{k_name},'up':1,'ls':1,'pwd':pwd}},
    dataType:'json' }});
}}
</script></body></html>"""
        return self._send(200, html)

    # ---------- 文件列表 ----------
    def _file_list(self, form: dict):
        state = self.state
        if form.get("pwd", "") != state.password:
            return self._json({"zt": 3, "info": "密码错误"})
        if form.get("t") != state.token_t or form.get("k") != state.token_k:
            return self._json({"zt": 0, "info": "请刷新，重试0"})
        page = int(form.get("pg") or 1)
        names = sorted(state.files)
        chunk = names[:] if page == 1 else []
        items = []
        for name in chunk:
            data = state.files[name]
            file_id = state.ids[name]
            if name in state.webpage:
                file_id += "?webpage=abc123"
            items.append({"name_all": name,
                          "size": _human_size(len(data)),
                          "id": file_id})
        return self._json({"zt": 1, "info": "sucess", "text": items})

    # ---------- 文件页 → iframe ----------
    def _file_page(self, file_id: str):
        token = file_id
        self.state.signs[token] = _rand_hex(24)
        html = (f'<html><body><iframe src="/fn?token={token}"></iframe>'
                f"</body></html>")
        return self._send(200, html)

    def _frame(self, query):
        token = (query.get("token") or [""])[0]
        sign = self.state.signs.get(token)
        if not sign:
            return self._send(404, "expired")
        base = self._base_url()
        html = f"""<script>
var wp_sign = '{sign}';
var ajaxdata = '{token}';
var down_3 = '';
var domain1 = '{base}/apifile';
var domain2 = '';
</script>"""
        return self._send(200, html)

    # ---------- apifile ----------
    def _apifile(self, form: dict):
        token = form.get("websignkey")
        if form.get("sign") != self.state.signs.get(token):
            return self._json({"zt": 0, "inf": "密码错误"})
        # 真实接口要求 websign='2'，缺了会返回"密码错误"（踩过一次）
        if str(form.get("websign") or "") != "2":
            return self._json({"zt": 0, "inf": "密码错误"})
        if self._name_of_id(token) in self.state.webpage:
            return self._json({"zt": 0, "inf": "密码错误"})
        page_token = _rand_hex(16)
        self.state.page_tokens[page_token] = token
        return self._json({"zt": 1, "dom": self._base_url(),
                           "url": page_token})

    # ---------- 下载页（含 acw 挑战） ----------
    def _download_page(self, page_token: str):
        state = self.state
        if page_token not in state.page_tokens:
            return self._send(404, "bad page token")

        expected = state.challenges.get(page_token)
        if not expected or self._cookie(acw.COOKIE_NAME) != expected:
            arg1 = "".join(random.choice("0123456789ABCDEF") for _ in range(40))
            state.challenges[page_token] = acw.solve(arg1)
            body = (f"<html><script>var arg1='{arg1}';"
                    f"/* acw_sc__v2 */</script></html>")
            return self._send(200, body)

        file_token = _rand_hex(20)
        sign = _rand_hex(12)
        state.final_tokens[file_token] = (page_token, sign)
        html = f"""<html><body>
<div id="sub"><div onclick="down_r(2);">验证并下载</div></div>
<script>
function down_r(el){{
  $.ajax({{ type:'post', url:'ajax.php',
    data: {{ 'file':'{file_token}','el':el,'sign':'{sign}' }},
    dataType:'json' }});
}}
</script></body></html>"""
        return self._send(200, html)

    def _ajax_download(self, form: dict):
        file_token = form.get("file")
        record = self.state.final_tokens.pop(file_token, None)
        if not record or record[1] != form.get("sign"):
            return self._json({"zt": 0, "url": "验证码错误"})
        page_token, _sign = record
        name = self._name_of_page(page_token)
        return self._json({"zt": 1, "url": f"?f={urllib.parse.quote(name)}"})

    def _name_of_id(self, file_id: str) -> str:
        for name, value in self.state.ids.items():
            if value == file_id:
                return name
        return ""

    def _name_of_page(self, page_token: str) -> str:
        token = self.state.page_tokens.get(page_token, "")
        for name, file_id in self.state.ids.items():
            if file_id == token:
                return name
        return ""

    # ---------- 文件本体 ----------
    def _serve_final(self, name: str):
        state = self.state
        if name not in state.files:
            return self._send(404, "no such file")
        with state.lock:
            remaining = state.fail_next.get(name, 0)
            if remaining > 0:
                state.fail_next[name] = remaining - 1
                return self._send(503, "busy")
        data = state.files[name]
        if name in state.corrupt:
            data = bytes([data[0] ^ 0xFF]) + data[1:]
        return self._send(200, data, "application/octet-stream")

    def _base_url(self) -> str:
        host = self.headers.get("Host") or "127.0.0.1"
        return f"http://{host}"


def _rand_hex(length: int) -> str:
    return "".join(random.choice("0123456789abcdef") for _ in range(length))


def _human_size(num: int) -> str:
    if num < 1024:
        return f"{num} B"
    if num < 1024 * 1024:
        return f"{num / 1024:.1f} K"
    return f"{num / 1024 / 1024:.1f} M"


class MockLanzou:
    """起一个本地"蓝奏"，用法::

        cloud = MockLanzou({"a.zip": b"…"}, password="28pm")
        cloud.start()
        share = LanzouShare(cloud.url, "28pm")
        ...
        cloud.stop()
    """

    def __init__(self, files: dict[str, bytes], password: str = "",
                 share_id: str = "btest123"):
        self.state = _State(files, password, share_id)
        self.share_id = share_id
        self._server = None
        self._thread = None

    def start(self) -> str:
        handler = type("_BoundHandler", (_Handler,), {"state": self.state})
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self.url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else 0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/{self.share_id}"

    # ---------- 测试辅助 ----------
    def set_files(self, files: dict[str, bytes]) -> None:
        """替换整个文件集（账号侧发布完成后刷新分享用）。"""
        with self.state.lock:
            self.state.files = dict(files)
            for name in files:
                if name not in self.state.ids:
                    self.state.ids[name] = f"i{len(self.state.ids):06d}"

    def add_file(self, name: str, data: bytes) -> None:
        with self.state.lock:
            self.state.files[name] = data
            self.state.ids[name] = f"i{len(self.state.ids):06d}"

    def fail_download(self, name: str, times: int) -> None:
        self.state.fail_next[name] = times

    def corrupt(self, name: str) -> None:
        self.state.corrupt.add(name)

    def mark_webpage(self, name: str) -> None:
        self.state.webpage.add(name)

    def request_count(self) -> int:
        return len(self.state.requests)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False
