"""
蓝奏云账号操作（登录 / 文件夹 / 上传）—— 只用标准库

接口（对照 lanzou-api 的实现，并做了简化）：
  登录      POST https://pc.woozooo.com/mydisk.php   task=3 & uid & pwd & formhash
  列文件夹  POST https://pc.woozooo.com/doupload.php  task=47 & folder_id
  建文件夹  POST https://pc.woozooo.com/doupload.php  task=2  & folder_id & folder_name & folder_description
  列文件    POST https://pc.woozooo.com/doupload.php  task=5  & folder_id
  上传      POST https://pc.woozooo.com/fileup.php    multipart（task=1 …）
  取分享    POST https://pc.woozooo.com/doupload.php  task=18 & folder_id（文件夹分享）

登录只需要账号 + 密码，没有验证码。
"""
from __future__ import annotations

import http.cookiejar
import json
import mimetypes
import re
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

BASE = "https://pc.woozooo.com"
MYDISK = f"{BASE}/mydisk.php"
DOUPLOAD = f"{BASE}/doupload.php"
FILEUP = f"{BASE}/fileup.php"
ACCOUNT = f"{BASE}/account.php"


class LanzouAccountError(Exception):
    pass


class LanzouAccount:
    """一个蓝奏账号（用于自动上传）。"""

    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.uid = ""
        self._cj = http.cookiejar.CookieJar()
        self._op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj))
        self._logged_in = False

    # ---------- 基础 ----------
    def _headers(self, extra=None):
        h = {"User-Agent": UA, "Referer": f"{BASE}/mydisk.php",
             "Origin": BASE, "Accept": "*/*"}
        if extra:
            h.update(extra)
        return h

    def _get(self, url):
        return self._op.open(urllib.request.Request(
            url, headers=self._headers()), timeout=self.timeout
        ).read().decode("utf-8", "replace")

    def _post(self, url, data: dict):
        return self._op.open(urllib.request.Request(
            url, data=urllib.parse.urlencode(data).encode(),
            headers=self._headers({
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest"})),
            timeout=self.timeout).read().decode("utf-8", "replace")

    def _json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            raise LanzouAccountError(f"返回不是 JSON: {text[:120]}")

    # ---------- 登录 ----------
    def login(self, username: str, password: str) -> None:
        """账号 + 密码登录（无验证码）。成功后 cookie 留在 self._op 里。"""
        page = self._get(ACCOUNT)
        m = re.search(r'name="formhash"\s+value="([^"]+)"', page)
        formhash = m.group(1) if m else ""
        payload = {"task": "3", "setSessionId": "", "setToken": "",
                   "setSig": "", "setScene": "", "uid": username,
                   "pwd": password}
        if formhash:
            payload["formhash"] = formhash
        raw = self._post_no_redirect(MYDISK, payload)
        msg = self._login_message(raw)
        if "成功" not in msg:
            # 有些账号的密码字段要 md5，失败后自动重试一次
            import hashlib
            payload["pwd"] = hashlib.md5(password.encode()).hexdigest()
            msg2 = self._login_message(self._post_no_redirect(MYDISK, payload))
            if "成功" not in msg2:
                raise LanzouAccountError(f"登录失败: {msg2 or msg}")
        # 从 cookie 里取 uid（上传要用）
        for c in self._cj:
            if c.name == "ylogin":
                self.uid = c.value
                break
        if not self.uid:
            m = re.search(r"ylogin=(\d+)", str(self._cj))
            self.uid = m.group(1) if m else ""
        self._logged_in = True

    def _post_no_redirect(self, url: str, data: dict) -> str:
        """不跟随 302：登录失败时提示就写在 302 的响应体里。"""
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None

        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj), _NoRedirect)
        try:
            resp = opener.open(urllib.request.Request(
                url, data=urllib.parse.urlencode(data).encode(),
                headers=self._headers({
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest"})), timeout=self.timeout)
            return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.read().decode("utf-8", "replace")

    @staticmethod
    def _login_message(raw: str) -> str:
        """登录接口可能返回 JSON，也可能返回 <script>alert("…")</script>。"""
        try:
            data = json.loads(raw)
            return str(data.get("info") or data)
        except Exception:
            pass
        m = re.search(r'alert\("([^"]*)"\)', raw)
        if m:
            return m.group(1)
        m = re.search(r"alert\('([^']*)'\)", raw)
        return m.group(1) if m else raw[:120]

    @property
    def logged_in(self) -> bool:
        return self._logged_in

    # ---------- 文件夹 ----------
    def list_folders(self, folder_id: int = -1) -> list[dict]:
        raw = self._post(DOUPLOAD, {"task": 47, "folder_id": folder_id})
        data = self._json(raw)
        out = []
        for f in data.get("text") or []:
            out.append({"id": int(f["fol_id"]), "name": f["name"]})
        return out

    def ensure_folder(self, name: str, parent: int = -1) -> int:
        """按名字找文件夹，没有就建，返回 folder_id。"""
        for f in self.list_folders(parent):
            if f["name"] == name:
                return f["id"]
        raw = self._post(DOUPLOAD, {
            "task": 2, "parent_id": parent, "folder_name": name,
            "folder_description": ""})
        data = self._json(raw)
        if data.get("zt") != 1:
            raise LanzouAccountError(f"建文件夹失败: {data}")
        # 返回 {"text": "<新 folder id>"} 或 {"info": ...}
        txt = str(data.get("text") or "")
        m = re.search(r"(\d+)", txt)
        if m:
            return int(m.group(1))
        for f in self.list_folders(parent):
            if f["name"] == name:
                return f["id"]
        raise LanzouAccountError(f"建文件夹后找不到: {data}")

    def list_files(self, folder_id: int = -1) -> list[dict]:
        raw = self._post(DOUPLOAD, {"task": 5, "folder_id": folder_id})
        data = self._json(raw)
        out = []
        for f in data.get("text") or []:
            out.append({"id": int(f["id"]), "name": f["name_all"],
                        "size": f.get("size"), "downs": f.get("downs")})
        return out

    # ---------- 上传 ----------
    def upload(self, file_path: str, folder_id: int = -1,
               progress=None) -> dict:
        """上传一个文件（multipart）。返回 {"id": 文件id, "name": ...}。"""
        import os
        path = str(file_path)
        if not os.path.isfile(path):
            raise LanzouAccountError(f"文件不存在: {path}")
        name = os.path.basename(path)
        size = os.path.getsize(path)
        boundary = "----PulsesSwap" + str(int(time.time() * 1000))
        parts = []

        def field(k, v):
            parts.append(
                (f"--{boundary}\r\n"
                 f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
                 f"{v}\r\n").encode())

        field("task", "1")
        field("vie", "2")
        field("ve", "2")
        field("id", "WU_FILE_0")
        field("folder_id_bb_n", str(folder_id))
        field("name", name)
        field("type", mimetypes.guess_type(name)[0] or "application/octet-stream")
        field("lastModifiedDate", time.strftime(
            "%a %b %d %Y %H:%M:%S GMT+0800", time.localtime()))
        field("size", str(size))
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        parts.append(
            (f"--{boundary}\r\n"
             f'Content-Disposition: form-data; name="upload_file"; '
             f'filename="{name}"\r\n'
             f"Content-Type: {ctype}\r\n\r\n").encode())
        with open(path, "rb") as fh:
            parts.append(fh.read())
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        body = b"".join(parts)

        url = f"{FILEUP}?uid={self.uid}" if self.uid else FILEUP
        req = urllib.request.Request(
            url, data=body,
            headers=self._headers({
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body))}), method="POST")
        raw = self._op.open(req, timeout=max(self.timeout, 3600)).read().decode(
            "utf-8", "replace")
        data = self._json(raw)
        if data.get("zt") != 1:
            raise LanzouAccountError(f"上传失败: {data}")
        info = (data.get("text") or [{}])[0]
        return {"id": info.get("id"), "name": info.get("name_all") or name,
                "raw": data}

    # ---------- 分享 ----------
    def folder_share(self, folder_id: int) -> dict:
        """取文件夹的分享链接（task=18）。"""
        raw = self._post(DOUPLOAD, {"task": 18, "folder_id": folder_id})
        return self._json(raw)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python -m online.provider_lanzou_account <账号> <密码>")
        raise SystemExit(1)
    acc = LanzouAccount()
    acc.login(sys.argv[1], sys.argv[2])
    print("登录成功，uid =", acc.uid)
    print("根目录文件夹:", acc.list_folders(-1))
