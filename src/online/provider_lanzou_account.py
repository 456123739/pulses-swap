"""
蓝奏云账号操作（登录 / 文件夹 / 上传 / 删除 / 分享）—— 只用标准库。

2026 年起登录搬到了独立域名，流程变成：

    ① GET  https://accounts.woozooo.com/accounts.php?action=login&ref=lanzoui.com
           （前面挂着 acw_sc__v2 人机校验，先解出来）
    ② POST https://accounts.woozooo.com/accounts.php
           task=uselogin & username & password & ref
           → {"zt":"1","msgs":"<中转鉴权地址>"} / {"zt":"0","msgs":"错误信息"}
    ③ GET  中转地址 → 落到 pc.woozooo.com，种下 ylogin / ylogins cookie
    ④ 之后所有接口都用 pc.woozooo.com + 这组 cookie

老接口（pc.woozooo.com/mydisk.php task=3）现在只会返回
「账号未激活，请先激活后使用云存储」，已经不能用了。

其余接口（都是 form 表单）：

    列文件夹  POST doupload.php  task=47 & folder_id
    建文件夹  POST doupload.php  task=2  & parent_id & folder_name
    列文件    POST doupload.php  task=5  & folder_id
    删文件    POST doupload.php  task=6  & file_id
    删文件夹  POST doupload.php  task=3  & folder_id
    分享文件夹 POST doupload.php  task=18 & folder_id
    上传      POST html5up.php   multipart（流式，不占内存），folder_id_bb_n 指定目录
"""
from __future__ import annotations

import gzip
import http.cookiejar
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlsplit

from . import acw
from .errors import AuthError, NetworkError, OnlineError, SourceError

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

BASE = "https://pc.woozooo.com"
ACCOUNTS_BASE = "https://accounts.woozooo.com"
LOGIN_REF = "lanzoui.com"

UPLOAD_BLOCK = 256 * 1024

# 蓝奏网页上传框里写死的扩展名白名单（.json 不在里面，所以 manifest 用 .txt）
ALLOWED_EXTENSIONS = frozenset("""
apk zip rar txt 7z z e ct doc docx exe ke db tar pdf epub mobi azw azw3 w3x osk
osz jar xpk cpk lua dmg ppt pptx xls xlsx mp3 gz psd ipa iso ttf txf ttc dwg bat
dll deb rp rpm rplib mobileconfig appimage img imazingapp lolgezi bin xapk flac
conf crx gho patch cad hwt accdb ce xmind enc bds bdi ssf it pkg cfg mp4 avi png
gif jpeg jpg webp brushset
""".split())


def is_allowed_upload(name: str) -> bool:
    """网盘收不收这个文件名（按扩展名）。"""
    suffix = str(name).rsplit(".", 1)[-1].lower() if "." in str(name) else ""
    return suffix in ALLOWED_EXTENSIONS


class LanzouAccountError(OnlineError):
    """兼容旧名字。"""

    code = "auth"


class _Response:
    """一次完整请求的结果。"""

    __slots__ = ("status", "headers", "body", "url")

    def __init__(self, status: int, headers, body: bytes, url: str):
        self.status = status
        self.headers = headers
        self.body = body
        self.url = url

    @property
    def text(self) -> str:
        charset = "utf-8"
        try:
            match = re.search(r"charset=([\w-]+)",
                              self.headers.get("Content-Type") or "", re.I)
            if match:
                charset = match.group(1)
        except Exception:
            pass
        return self.body.decode(charset, "replace")


def _var(text: str, name: str) -> str:
    """取 ``var <name> = '…'`` 的值。"""
    match = re.search(rf"var\s+{re.escape(name)}\s*=\s*'([^']*)'", text)
    return match.group(1) if match else ""


class _UploadBody:
    """流式 multipart 请求体：prefix + 文件 + suffix，带进度回调。"""

    def __init__(self, prefix: bytes, file_path: str, suffix: bytes,
                 progress=None):
        self.prefix = prefix
        self.suffix = suffix
        self.path = file_path
        self.file_size = os.path.getsize(file_path)
        self.length = len(prefix) + self.file_size + len(suffix)
        self.progress = progress
        self._stage = 0
        self._offset = 0
        self._handle = None
        self._sent = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = UPLOAD_BLOCK
        while True:
            if self._stage == 0:
                chunk = self.prefix[self._offset:self._offset + size]
                if chunk:
                    self._offset += len(chunk)
                    self._tick(len(chunk))
                    return chunk
                self._stage = 1
                self._offset = 0
                self._handle = open(self.path, "rb")
            elif self._stage == 1:
                chunk = self._handle.read(size)
                if chunk:
                    self._offset += len(chunk)
                    self._tick(len(chunk))
                    return chunk
                self._handle.close()
                self._handle = None
                self._stage = 2
                self._offset = 0
            elif self._stage == 2:
                chunk = self.suffix[self._offset:self._offset + size]
                if chunk:
                    self._offset += len(chunk)
                    self._tick(len(chunk))
                    return chunk
                self._stage = 3
            else:
                return b""

    def _tick(self, count: int) -> None:
        self._sent += count
        if self.progress is not None:
            self.progress(self._sent, self.length)

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None


class LanzouAccount:
    """一个蓝奏账号（用于自动上传）。"""

    def __init__(self, timeout: int = 60, base: str | None = None,
                 accounts_base: str | None = None):
        self.timeout = timeout
        self.base = (base or BASE).rstrip("/")
        self.accounts_base = (accounts_base or base
                              or ACCOUNTS_BASE).rstrip("/")
        self.uid = ""
        self.nickname = ""
        self._cj = http.cookiejar.CookieJar()
        self._op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj))
        self._logged_in = False

    # ------------------------------------------------------------------
    # 基础请求
    # ------------------------------------------------------------------
    def _headers(self, referer=None, extra=None):
        headers = {"User-Agent": UA,
                   "Referer": referer or f"{self.base}/mydisk.php",
                   "Origin": self.base, "Accept": "*/*",
                   "Accept-Language": "zh-CN,zh;q=0.9",
                   "Accept-Encoding": "gzip"}
        if extra:
            headers.update(extra)
        return headers

    def _request(self, url: str, *, data: dict | None = None,
                 referer: str | None = None,
                 timeout: float | None = None) -> _Response:
        body = None
        headers = self._headers(referer)
        if data is not None:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["X-Requested-With"] = "XMLHttpRequest"
        request = urllib.request.Request(url, data=body, headers=headers)
        try:
            with self._op.open(request, timeout=timeout or self.timeout) as resp:
                raw = resp.read()
                if (resp.headers.get("Content-Encoding") or "").lower() == "gzip" \
                        and raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return _Response(resp.status, resp.headers, raw, resp.geturl())
        except urllib.error.HTTPError as exc:
            raw = b""
            try:
                raw = exc.read()
                if (exc.headers.get("Content-Encoding") or "").lower() == "gzip" \
                        and raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
            except Exception:
                pass
            if exc.code >= 500:
                raise NetworkError(f"蓝奏服务异常（HTTP {exc.code}）",
                                   detail=url, retryable=True) from exc
            return _Response(exc.code, exc.headers, raw, url)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise NetworkError(f"连接蓝奏失败: {reason}", detail=url,
                               retryable=True) from exc

    def _solve_challenge(self, url: str, body: bytes) -> bool:
        """响应是 acw_sc__v2 校验页就解出来写进 cookie。"""
        arg1 = acw.challenge_arg1(body)
        if not arg1:
            return False
        value = acw.solve(arg1)
        if not value:
            return False
        host = urlsplit(url).hostname or ""
        self._cj.set_cookie(http.cookiejar.Cookie(
            0, acw.COOKIE_NAME, value, None, False, host, False, False,
            "/", True, False, int(time.time()) + 3500, False, None, None, {}))
        return True

    def _send(self, url: str, *, data: dict | None = None,
              referer: str | None = None) -> _Response:
        """发一次请求；遇到人机校验页就解完再发一次。"""
        response = None
        for attempt in range(2):
            response = self._request(url, data=data, referer=referer)
            if attempt == 0 and self._solve_challenge(url, response.body):
                continue
            break
        return response

    def _get_text(self, url: str, referer: str | None = None) -> str:
        return self._send(url, referer=referer).text

    def _post_text(self, url: str, data: dict,
                   referer: str | None = None) -> str:
        return self._send(url, data=data, referer=referer).text

    @staticmethod
    def _json(text: str) -> dict:
        try:
            data = json.loads(text)
        except ValueError:
            raise SourceError("蓝奏返回的不是 JSON", detail=text[:160],
                              hint="接口可能改版了。") from None
        if not isinstance(data, dict):
            raise SourceError("蓝奏返回格式异常", detail=str(data)[:160])
        return data

    @staticmethod
    def _ok(data: dict) -> bool:
        return str(data.get("zt")) == "1"

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------
    def login(self, username: str, password: str) -> None:
        """账号 + 密码登录（无验证码，但要过 acw 人机校验）。"""
        username = str(username or "").strip()
        password = str(password or "")
        if not username or not password:
            raise AuthError("账号或密码为空")

        login_url = f"{self.accounts_base}/accounts.php?action=login&ref={LOGIN_REF}"
        page = self._send(login_url)
        if page.status >= 400:
            raise NetworkError(f"登录页打不开（HTTP {page.status}）",
                               detail=login_url, retryable=True)
        html = page.text
        task = _var(html, "task") or "uselogin"
        ref = _var(html, "ref") or LOGIN_REF

        response = self._send(
            f"{self.accounts_base}/accounts.php",
            data={"task": task, "username": username,
                  "password": password, "ref": ref},
            referer=login_url)
        text = response.text.strip()
        try:
            data = json.loads(text)
        except ValueError:
            raise AuthError(f"登录失败：{self._login_message(text)}",
                            detail=text[:160]) from None
        if not isinstance(data, dict) or str(data.get("zt")) != "1":
            message = (data.get("msgs") if isinstance(data, dict) else "") \
                or self._login_message(text)
            raise AuthError(f"登录失败：{message}",
                            hint="确认账号密码；账号未激活时先去蓝奏官网激活。")

        # 中转鉴权：这一跳才会种下 pc.woozooo.com 的会话 cookie
        redirect = str(data.get("msgs") or "")
        if redirect:
            try:
                self._send(redirect, referer=login_url)
            except OnlineError:
                pass

        for cookie in self._cj:
            if cookie.name == "ylogin":
                self.uid = cookie.value
                break
        if not self.uid:
            raise AuthError("登录成功但没拿到会话",
                            hint="稍后重试；仍失败说明网盘改版了。")
        self._logged_in = True

    @staticmethod
    def _login_message(raw: str) -> str:
        """有些接口仍然返回 <script>alert("…")</script>。"""
        match = re.search(r'alert\("([^"]*)"\)', raw)
        if match:
            return match.group(1)
        match = re.search(r"alert\('([^']*)'\)", raw)
        return match.group(1) if match else raw[:120].strip()

    @property
    def logged_in(self) -> bool:
        return self._logged_in

    def _require_login(self) -> None:
        if not self._logged_in:
            raise AuthError("还没有登录蓝奏账号")

    # ------------------------------------------------------------------
    # 文件夹
    # ------------------------------------------------------------------
    def list_folders(self, folder_id: int = -1) -> list[dict]:
        self._require_login()
        data = self._json(self._post_text(
            f"{self.base}/doupload.php", {"task": 47, "folder_id": folder_id}))
        out = []
        for row in data.get("text") or []:
            try:
                out.append({"id": int(row["fol_id"]),
                            "name": str(row.get("name") or "")})
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def ensure_folder(self, name: str, parent: int = -1) -> int:
        """按名字找文件夹，没有就建，返回 folder_id。"""
        self._require_login()
        name = str(name or "").strip()
        if not name:
            raise SourceError("文件夹名为空")
        for folder in self.list_folders(parent):
            if folder["name"] == name:
                return folder["id"]
        data = self._json(self._post_text(f"{self.base}/doupload.php", {
            "task": 2, "parent_id": parent, "folder_name": name,
            "folder_description": ""}))
        if self._ok(data):
            text = str(data.get("text") or "")
            match = re.search(r"(\d+)", text)
            if match:
                return int(match.group(1))
        for folder in self.list_folders(parent):
            if folder["name"] == name:
                return folder["id"]
        raise SourceError(f"创建文件夹失败：{data.get('info') or data}")

    def ensure_path(self, path: str, root: int = -1) -> int:
        """``/A/B/C`` → 逐级建好，返回最深一级的 folder_id。"""
        parts = [p for p in str(path or "").replace("\\", "/").split("/") if p]
        folder = root
        for part in parts:
            folder = self.ensure_folder(part, folder)
        return folder

    def find_path(self, path: str, root: int = -1):
        """按路径查找文件夹，不创建。找不到返回 None。

        浏览云端目录时必须用这个：ensure_path 会顺手建目录，
        用户只是点进一个写错的路径，不该在网盘里留下空文件夹。
        """
        folder = root
        parts = [p for p in str(path or "").replace("\\", "/").split("/") if p]
        for part in parts:
            found = None
            for item in self.list_folders(folder):
                if item["name"] == part:
                    found = item["id"]
                    break
            if found is None:
                return None
            folder = found
        return folder

    def folder_path(self, folder_id: int, root: int = -1) -> str:
        """尽量反查出文件夹路径（用于展示）。失败返回空串。"""
        chain: list[str] = []
        current = folder_id
        guard = 0
        while current != root and guard < 20:
            guard += 1
            found = None
            for parent in [root] + [f["id"] for f in self.list_folders(root)]:
                for folder in self.list_folders(parent):
                    if folder["id"] == current:
                        found = (folder["name"], parent)
                        break
                if found:
                    break
            if not found:
                break
            chain.append(found[0])
            current = found[1]
        return "/" + "/".join(reversed(chain)) if chain else ""

    # ------------------------------------------------------------------
    # 文件
    # ------------------------------------------------------------------
    def list_files(self, folder_id: int = -1) -> list[dict]:
        self._require_login()
        data = self._json(self._post_text(
            f"{self.base}/doupload.php", {"task": 5, "folder_id": folder_id}))
        out = []
        for row in data.get("text") or []:
            try:
                file_id = int(row["id"])
            except (KeyError, TypeError, ValueError):
                continue
            out.append({"id": file_id,
                        "name": str(row.get("name_all") or ""),
                        "size": str(row.get("size") or ""),
                        "downs": row.get("downs")})
        return out

    def delete_file(self, file_id) -> bool:
        self._require_login()
        data = self._json(self._post_text(
            f"{self.base}/doupload.php", {"task": 6, "file_id": int(file_id)}))
        return self._ok(data)

    def delete_folder(self, folder_id) -> bool:
        self._require_login()
        data = self._json(self._post_text(
            f"{self.base}/doupload.php", {"task": 3,
                                          "folder_id": int(folder_id)}))
        return self._ok(data)

    # ------------------------------------------------------------------
    # 上传
    # ------------------------------------------------------------------
    def upload(self, file_path: str, folder_id: int = -1, *,
               progress=None, cancel=None) -> dict:
        """流式上传一个文件。返回 ``{"id", "name", "size"}``。"""
        self._require_login()
        path = str(file_path)
        if not os.path.isfile(path):
            raise SourceError(f"文件不存在: {path}")
        name = os.path.basename(path)
        if not is_allowed_upload(name):
            raise SourceError(
                f"网盘不接受 .{name.rsplit('.', 1)[-1]} 扩展名：{name}",
                hint="把这类文件放进 .zip，或改成 .txt 再发布。")
        size = os.path.getsize(path)
        boundary = "----PulsesSwap" + str(int(time.time() * 1000))

        def field(key: str, value) -> bytes:
            return (f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                    f"{value}\r\n").encode("utf-8")

        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        prefix = b"".join([
            field("task", "1"), field("vie", "2"), field("ve", "2"),
            field("id", "WU_FILE_0"), field("folder_id_bb_n", folder_id),
            field("name", name), field("type", ctype),
            field("lastModifiedDate", time.strftime(
                "%a %b %d %Y %H:%M:%S GMT+0800", time.localtime())),
            field("size", size),
            (f"--{boundary}\r\n"
             f'Content-Disposition: form-data; name="upload_file"; '
             f'filename="{name}"\r\n'
             f"Content-Type: {ctype}\r\n\r\n").encode("utf-8"),
        ])
        suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = _UploadBody(prefix, path, suffix, progress)

        # 2026 起上传接口是 /html5up.php（老的 /fileup.php 已经 404），
        # 目标文件夹靠表单字段 folder_id_bb_n 指定
        url = f"{self.base}/html5up.php"
        request = urllib.request.Request(
            url, data=body,
            headers=self._headers(f"{self.base}/mydisk.php", {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(body.length)}),
            method="POST")
        try:
            with self._op.open(request, timeout=max(self.timeout, 3600)) as resp:
                raw = resp.read()
                if (resp.headers.get("Content-Encoding") or "").lower() == "gzip" \
                        and raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                text = raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise NetworkError(f"上传失败（HTTP {exc.code}）",
                               retryable=True) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise NetworkError(f"上传中断: {exc}", retryable=True) from exc
        finally:
            body.close()

        data = self._json(text)
        if not self._ok(data):
            message = str(data.get("info") or data)
            if "格式" in message or "扩展名" in message:
                raise SourceError(
                    f"网盘不接受这个扩展名：{name}",
                    detail=message,
                    hint="蓝奏对扩展名有白名单，改成 .zip 再上传。")
            raise SourceError(f"上传失败：{message}")
        rows = data.get("text") or []
        info = rows[0] if rows else {}
        return {"id": info.get("id"), "name": info.get("name_all") or name,
                "size": size}

    # ------------------------------------------------------------------
    # 分享
    # ------------------------------------------------------------------
    def folder_share(self, folder_id: int) -> dict:
        """取文件夹的分享信息，返回 ``{"url", "password", "raw"}``。"""
        self._require_login()
        data = self._json(self._post_text(
            f"{self.base}/doupload.php", {"task": 18,
                                          "folder_id": int(folder_id)}))
        info = data.get("info")
        if isinstance(info, dict):
            # new_url 才是完整分享地址；is_newd 只是域名（https://xxx.lanzoul.com）
            url = str(info.get("new_url") or info.get("url") or "")
            if not url or "/" not in url.split("//")[-1]:
                url = str(info.get("is_newd") or "")
            password = str(info.get("pwd") or info.get("password") or "")
        elif isinstance(info, str):
            url, password = info, ""
        else:
            url = str(data.get("url") or "")
            password = str(data.get("pwd") or "")
        if not url or "/" not in url.split("//")[-1]:
            raise SourceError("取分享链接失败",
                              detail=str(data)[:160],
                              hint="确认文件夹存在且账号有分享权限。")
        return {"url": url, "password": password, "raw": data}

    # ------------------------------------------------------------------
    def quota(self) -> dict:
        """账号容量（尽力而为，失败返回空）。"""
        try:
            data = self._json(self._post_text(
                f"{self.base}/doupload.php", {"task": 1}))
        except OnlineError:
            return {}
        text = data.get("text") or {}
        if isinstance(text, dict):
            return {"used": text.get("used"), "total": text.get("total")}
        return {}


if __name__ == "__main__":        # 手工冒烟
    import sys

    if len(sys.argv) < 3:
        print("用法: python -m online.provider_lanzou_account <账号> <密码>")
        raise SystemExit(1)
    account = LanzouAccount()
    account.login(sys.argv[1], sys.argv[2])
    print("登录成功，uid =", account.uid)
    print("根目录文件夹:", account.list_folders(-1))
