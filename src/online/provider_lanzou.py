"""
蓝奏云分享解析（匿名，无需登录）。

已对真实分享验证过的完整链路：

    ① GET  /<share_id>                    → fid / uid / puid / t / k
    ② POST /filemoreajax.php?file=<fid>   → 带密码 → 文件列表
    ③ GET  /<file_id>                     → 页面里的 <iframe src="/fn?token">
    ④ GET  /fn?token                      → wp_sign / ajaxdata / domain1 / down_3
    ⑤ POST <domain1> (apifile)            → {"zt":1,"dom":…,"url":…}
    ⑥ GET  <dom>/file/<url>&toolsdown     → 下载页（先过一次 acw 人机校验）
    ⑦ POST <下载页>/file/ajax.php          → {"zt":1,"url":"?…"}
    ⑧ GET  <dom>/file/?…                  → 文件本体

其中 ⑥⑦ 是 2026 年新加的一层，链接都是一次性的，所以失败只能整条重来。
只依赖标准库。
"""
from __future__ import annotations

import gzip
import http.cookiejar
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlsplit

from . import acw
from .errors import (CancelledError, CaptchaError, NetworkError, OnlineError,
                     SourceError)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 蓝奏域名会轮换，按顺序尝试
DOMAIN_POOL = ("lanzoul.com", "lanzou.com", "lanzoux.com", "lanzoui.com",
               "lanzoub.com", "lanzoue.com", "lanzoup.com", "lanzouj.com",
               "lanzouy.com", "lanzouw.com")

# 蓝奏对扩展名有白名单。真实账号实测：.json / .yaml / .toml / .ini /
# .xml 都会被拒绝，.cfg 可以上传。manifest 因此用 .cfg 后缀、JSON 内容，
# 读取时同时兼容旧版的 _pulses_manifest.txt（同样是 JSON）。
MANIFEST_NAME = "_pulses_manifest.cfg"
LEGACY_MANIFEST_NAMES = ("_pulses_manifest.txt",)
MANIFEST_NAMES = (MANIFEST_NAME,) + LEGACY_MANIFEST_NAMES


def is_manifest_name(name: str) -> bool:
    """这个名字是不是云端 manifest（新版 .cfg 或旧版 .txt）。"""
    lowered = str(name or "").lower()
    return any(lowered == item.lower() for item in MANIFEST_NAMES)


DOWNLOAD_CHUNK = 256 * 1024


class Response:
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
            ctype = self.headers.get("Content-Type") or ""
            match = re.search(r"charset=([\w-]+)", ctype, re.I)
            if match:
                charset = match.group(1)
        except Exception:
            pass
        return self.body.decode(charset, "replace")


def _var(text: str, name: str) -> str:
    """取 ``var <name> = '…'`` / ``var <name> = 123`` 的值。"""
    pattern = (rf"var\s+{re.escape(name)}\s*=\s*"
               r"(?:'([^']*)'|\"([^\"]*)\"|([^;]+));")
    match = re.search(pattern, text)
    if not match:
        return ""
    for group in match.groups():
        if group is not None:
            return group.strip()
    return ""


def _unescape(text: str) -> str:
    """处理 ``\\/`` 这类 JS 转义。"""
    return str(text or "").replace("\\/", "/")


class LanzouShare:
    """一个蓝奏文件夹分享（``/bXXXX``）。"""

    def __init__(self, share_url: str, password: str = "", *,
                 timeout: int = 30, retries: int = 3, sleep=None, log=None):
        self.share_url = str(share_url or "").strip().rstrip("/")
        self.password = str(password or "")
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self._sleep = sleep or time.sleep
        self.log = log
        match = re.search(r"https?://([^/]+)/([A-Za-z0-9]+)", self.share_url)
        if not match:
            raise SourceError(f"无法解析分享链接: {share_url}",
                              hint="链接形如 https://xxx.lanzoul.com/b0123456")
        self.host_name = match.group(1)
        self.share_id = match.group(2)
        self.scheme = "http" if self.share_url.lower().startswith("http://") else "https"
        self.host = f"{self.scheme}://{self.host_name}"
        self._cj = http.cookiejar.CookieJar()
        self._op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj))
        self._params: dict | None = None
        self._files: list[dict] | None = None
        self._acw_done: set[str] = set()

    def clone(self):
        """复制一个独立会话，给并发下载的每个线程用。

        LanzouShare 内部有 cookie / 一次性令牌 / _acw_done 状态，不能跨线程
        共用；每个下载线程拿自己的 clone，避免令牌互相覆盖。
        """
        return LanzouShare(
            self.share_url, self.password, timeout=self.timeout,
            retries=self.retries, sleep=self._sleep, log=self.log)

    # ------------------------------------------------------------------
    # 基础请求
    # ------------------------------------------------------------------
    def _headers(self, referer: str | None = None, extra: dict | None = None):
        headers = {
            "User-Agent": UA,
            "Referer": referer or f"{self.host}/{self.share_id}",
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip",
        }
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _decode(resp) -> tuple[bytes, object]:
        raw = resp.read()
        encoding = (resp.headers.get("Content-Encoding") or "").lower()
        if "gzip" in encoding and raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        return raw, resp.headers

    def _request(self, url: str, *, data: dict | None = None,
                 referer: str | None = None, timeout: float | None = None,
                 extra_headers: dict | None = None) -> Response:
        body = None
        headers = self._headers(referer, extra_headers)
        if data is not None:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["X-Requested-With"] = "XMLHttpRequest"
        req = urllib.request.Request(url, data=body, headers=headers)
        try:
            with self._op.open(req, timeout=timeout or self.timeout) as resp:
                raw, resp_headers = self._decode(resp)
                return Response(resp.status, resp_headers, raw, url)
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
                raise NetworkError(f"网盘服务异常（HTTP {exc.code}）",
                                   detail=url, retryable=True) from exc
            return Response(exc.code, exc.headers, raw, url)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise NetworkError(f"连接网盘失败: {reason}", detail=url,
                               retryable=True) from exc

    def _solve_challenge(self, url: str, body: bytes) -> bool:
        """响应是 acw 校验页就解出来写进 cookie，返回是否处理过。"""
        arg1 = acw.challenge_arg1(body)
        if not arg1:
            return False
        value = acw.solve(arg1)
        if not value:
            return False
        host = urlsplit(url).hostname or self.host_name
        cookie = http.cookiejar.Cookie(
            0, acw.COOKIE_NAME, value, None, False, host, False, False,
            "/", True, False, int(time.time()) + 3500, False, None, None, {})
        self._cj.set_cookie(cookie)
        self._acw_done.add(host)
        if self.log:
            self.log(f"通过网盘人机校验（{host}）", verbose=True)
        return True

    def _get(self, url: str, *, referer: str | None = None,
             allow_challenge: bool = True) -> Response:
        for attempt in range(2):
            resp = self._request(url, referer=referer)
            if allow_challenge and attempt == 0 \
                    and self._solve_challenge(url, resp.body):
                continue
            if resp.status >= 500:
                raise NetworkError(f"网盘服务异常（HTTP {resp.status}）",
                                   retryable=True)
            if resp.status >= 400:
                raise SourceError(f"网盘返回 HTTP {resp.status}",
                                  detail=url,
                                  hint="分享可能已失效。")
            return resp
        raise SourceError("网盘人机校验未通过", detail=url)

    def _get_html(self, url: str, *, referer: str | None = None) -> str:
        return self._get(url, referer=referer).text

    def _post_json(self, url: str, data: dict, *,
                   referer: str | None = None) -> dict:
        resp = self._request(url, data=data, referer=referer)
        text = resp.text.strip()
        try:
            return json.loads(text)
        except ValueError:
            if "请刷新" in text:
                raise _StaleToken("token 过期")
            if "acw_sc__v2" in text or "arg1=" in text:
                if self._solve_challenge(url, resp.body):
                    resp = self._request(url, data=data, referer=referer)
                    try:
                        return json.loads(resp.text.strip())
                    except ValueError:
                        pass
            raise SourceError("网盘返回的不是 JSON", detail=text[:160],
                              hint="网盘接口可能改版了。")

    # ------------------------------------------------------------------
    # ① 分享页参数
    # ------------------------------------------------------------------
    def _candidate_hosts(self) -> list[str]:
        """域名轮换只在"这确实是蓝奏域名"时才启用。

        否则本地测试服务（127.0.0.1）连不上时会跑去连真实的 lanzoul.com，
        拿到一个 404 再报"分享失效"，错误原因就全错了。
        """
        bare = self.host_name.split(":")[0].lower()
        if not any(bare == domain or bare.endswith("." + domain)
                   for domain in DOMAIN_POOL):
            return [self.host_name]
        hosts = [self.host_name]
        for domain in DOMAIN_POOL:
            if domain != bare:
                hosts.append(domain)
        return hosts

    @staticmethod
    def _parse_share_page(html: str) -> dict:
        fid = (re.search(r"'fid'\s*:\s*'?(\d+)'?", html)
               or re.search(r"file=(\d+)", html))
        uid = re.search(r"'uid'\s*:\s*'?(\d+)'?", html)
        puid = re.search(r"'puid'\s*:\s*'([^']+)'", html)
        if not (fid and uid and puid):
            raise SourceError("分享页结构异常",
                              hint="分享可能已失效，或网盘改版了。")

        # t / k 的变量名每次刷新都变，必须先拿到名字再取值
        t_name = re.search(r"'t'\s*:\s*(\w+)", html)
        k_name = re.search(r"'k'\s*:\s*(\w+)", html)
        token_t = _var(html, t_name.group(1)) if t_name else ""
        token_k = _var(html, k_name.group(1)) if k_name else ""
        if not token_t or not token_k:
            # 兜底：按值的形状认（t 是 10 位时间戳，k 是 32 位十六进制）
            for name, value in re.findall(r"var\s+(\w+)\s*=\s*'?([^';\s]+)'?\s*;",
                                          html):
                if not token_k and re.fullmatch(r"[0-9a-f]{32}", value):
                    token_k = value
                elif not token_t and re.fullmatch(r"\d{9,11}", value):
                    token_t = value
        if not token_t or not token_k:
            raise SourceError("分享页缺少访问令牌",
                              hint="刷新重试；仍失败说明网盘改版了。")
        return {"fid": fid.group(1), "uid": uid.group(1),
                "puid": puid.group(1), "t": token_t, "k": token_k}

    def _load_params(self, force: bool = False) -> dict:
        if self._params and not force:
            return self._params
        last: Exception | None = None
        for host in self._candidate_hosts():
            try:
                html = self._get_html(f"{self.scheme}://{host}/{self.share_id}")
            except NetworkError as exc:
                last = exc
                continue
            params = self._parse_share_page(html)
            self.host_name = host
            self.host = f"{self.scheme}://{host}"
            self._params = params
            return params
        if isinstance(last, OnlineError):
            raise last
        raise NetworkError("所有蓝奏域名都连不上", retryable=True)

    # ------------------------------------------------------------------
    # ② 文件列表
    # ------------------------------------------------------------------
    def list_files(self, refresh: bool = False) -> list[dict]:
        """返回 ``[{name, size, size_bytes, file_id, raw_id}]``，按名字排序。"""
        if self._files is not None and not refresh:
            return list(self._files)
        params = self._load_params(force=refresh)
        collected: list[dict] = []
        page = 1
        retried = False
        while page <= 50:
            payload = {"lx": 2, "fid": params["fid"], "uid": params["uid"],
                       "puid": params["puid"], "pg": page, "rep": 0,
                       "t": params["t"], "k": params["k"],
                       "up": 1, "ls": 1, "pwd": self.password}
            try:
                data = self._post_json(
                    f"{self.host}/filemoreajax.php?file={params['fid']}",
                    payload)
            except _StaleToken:
                if retried:
                    raise SourceError("网盘令牌反复失效", retryable=True,
                                      hint="稍后再试。")
                retried = True
                params = self._load_params(force=True)
                page = 1
                collected.clear()
                continue

            zt = data.get("zt")
            if zt == 2:
                break
            if zt != 1:
                raise self._error_from(data)
            items = data.get("text") or []
            for item in items:
                raw_id = str(item.get("id") or "")
                collected.append({
                    "name": str(item.get("name_all") or ""),
                    "size": str(item.get("size") or ""),
                    "size_bytes": parse_size(item.get("size")),
                    "file_id": raw_id.split("?")[0],
                    "raw_id": raw_id,
                })
            if len(items) < 50:
                break
            page += 1
        self._files = sorted(collected, key=lambda x: x["name"].lower())
        return list(self._files)

    @staticmethod
    def _error_from(data: dict) -> OnlineError:
        info = str(data.get("info") or data.get("inf") or "").strip()
        if "密码" in info:
            return SourceError("分享密码错误", hint="在预设的「来源」里改正密码。")
        if any(word in info for word in ("不存在", "已删除", "取消", "失效", "违规")):
            return SourceError(f"分享已失效：{info or '文件不存在'}")
        return SourceError(f"网盘返回：{info or data}", retryable=True)

    def find_file(self, name: str) -> dict | None:
        lowered = name.lower()
        for item in self.list_files():
            if item["name"].lower() == lowered:
                return item
        return None

    def find_manifest(self) -> dict | None:
        """按优先级找 manifest：新版 .cfg 优先，旧版 .txt 兜底。"""
        by_name = {item["name"].lower(): item for item in self.list_files()}
        for name in MANIFEST_NAMES:
            found = by_name.get(name.lower())
            if found is not None:
                return found
        return None

    # ------------------------------------------------------------------
    # ③④⑤ 直链解析
    # ------------------------------------------------------------------
    def _resolve_via_iframe(self, file_id: str, raw_id: str | None) -> str:
        page_url = f"{self.host}/{raw_id or file_id}"
        page = self._get_html(page_url)
        match = re.search(r'<iframe[^>]*src="([^"]+)"', page)
        if not match:
            if "down_r(" in page or "'sign'" in page:
                return page_url          # 文件页本身就是下载页
            raise SourceError("文件页没有下载入口",
                              hint="可能是「文件带网页」类型，重新上传为普通文件即可。")
        frame_url = urllib.parse.urljoin(page_url, match.group(1))
        frame = self._get_html(frame_url, referer=page_url)
        wp_sign = _var(frame, "wp_sign")
        ajaxdata = _var(frame, "ajaxdata")
        down_suffix = _unescape(_var(frame, "down_3"))
        apis = [_unescape(_var(frame, "domain1")), _unescape(_var(frame, "domain2"))]
        if not (wp_sign and ajaxdata):
            raise SourceError("下载参数缺失", hint="网盘接口可能改版了。")
        last = ""
        for api in apis:
            if not api:
                continue
            try:
                info = self._post_json(api, {
                    "action": "downprocess", "websignkey": ajaxdata,
                    "signs": ajaxdata, "sign": wp_sign, "websign": "2",
                    "kd": 1, "ves": 1}, referer=page_url)
            except OnlineError as exc:
                last = str(exc)
                continue
            if str(info.get("zt")) == "1" and info.get("url"):
                dom = str(info.get("dom") or "").rstrip("/")
                if not dom:
                    continue
                return f"{dom}/file/{info['url']}{down_suffix}"
            last = str(info.get("inf") or info.get("info") or info)
        if "密码错误" in str(last):
            raise SourceError(
                "网盘拒绝了下载请求（签名校验未通过）",
                detail=last,
                hint="重新同步一次；仍失败说明网盘接口又改了。")
        raise SourceError(f"取直链失败：{last}", retryable=True)

    def _resolve_via_share_page(self, file_id: str, raw_id: str | None) -> str:
        """兜底：文件页直接给出 downprocess 参数时自己拼。"""
        page_url = f"{self.host}/{raw_id or file_id}"
        page = self._get_html(page_url)
        if "down_r(" in page:
            return page_url
        wp_sign = _var(page, "wp_sign")
        ajaxdata = _var(page, "ajaxdata")
        if not (wp_sign and ajaxdata):
            raise SourceError("文件页无法解析")
        api = _unescape(_var(page, "domain1")) or "https://apifile.woozooo.com/ajaxfile.php"
        info = self._post_json(api, {"action": "downprocess",
                                     "websignkey": ajaxdata, "signs": ajaxdata,
                                     "sign": wp_sign, "websign": "2",
                                     "kd": 1, "ves": 1}, referer=page_url)
        if str(info.get("zt")) == "1" and info.get("url"):
            dom = str(info.get("dom") or "").rstrip("/")
            return f"{dom}/file/{info['url']}"
        raise SourceError("取直链失败", retryable=True)

    def resolve(self, file_id: str, raw_id: str | None = None) -> str:
        """把文件 id 解析成"可以取到文件"的 URL（可能是下载页，也可能直接是文件）。"""
        errors = []
        for strategy in (self._resolve_via_iframe, self._resolve_via_share_page):
            try:
                return strategy(file_id, raw_id)
            except (SourceError, NetworkError) as exc:
                errors.append(exc)
        raise errors[0] if errors else SourceError("无法解析下载地址")

    # ------------------------------------------------------------------
    # ⑥⑦ 下载页 → 文件地址
    # ------------------------------------------------------------------
    def _file_url_from_page(self, page_url: str) -> str:
        """下载页里再点一次「验证并下载」，拿到真正的文件地址。"""
        resp = self._get(page_url, referer=self.host + "/")
        text = resp.text
        if "验证码" in text and "错误" in text:
            raise CaptchaError("网盘要求人机验证", detail=page_url)
        if "down_r(" not in text and "'sign'" not in text:
            return page_url                       # 已经是文件本体

        file_token = re.search(r"'file'\s*:\s*'([^']+)'", text)
        sign_token = re.search(r"'sign'\s*:\s*'([^']+)'", text)
        element = re.search(r"down_r\((\d+)\)", text)
        if not (file_token and sign_token):
            raise SourceError("下载页缺少参数", hint="网盘接口可能改版了。")
        ajax_url = urllib.parse.urljoin(page_url, "ajax.php")
        info = self._post_json(ajax_url, {
            "file": file_token.group(1),
            "el": element.group(1) if element else "1",
            "sign": sign_token.group(1)}, referer=page_url)
        if str(info.get("zt")) == "1" and info.get("url"):
            target = _unescape(str(info["url"]))
            return urllib.parse.urljoin(page_url, target)
        message = str(info.get("url") or info.get("info") or info)
        if "验证码" in message:
            raise CaptchaError("网盘要求人机验证", detail=page_url)
        raise SourceError(f"网盘拒绝下载：{message}", retryable=True)

    # ------------------------------------------------------------------
    # ⑧ 取文件
    # ------------------------------------------------------------------
    def _stream(self, url: str, dest: str, *, progress=None, cancel=None,
                expected_size: int = 0, referer: str | None = None) -> int:
        tmp = f"{dest}.part"
        os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
        for attempt in range(2):
            headers = self._headers(referer or self.host + "/",
                                    {"Accept": "*/*",
                                     "Accept-Encoding": "identity"})
            req = urllib.request.Request(url, headers=headers)
            try:
                resp = self._op.open(req, timeout=max(self.timeout, 120))
            except urllib.error.HTTPError as exc:
                body = b""
                try:
                    body = exc.read()
                except Exception:
                    pass
                if exc.code >= 500:
                    raise NetworkError(f"下载失败（HTTP {exc.code}）",
                                       retryable=True) from exc
                if self._solve_challenge(url, body):
                    continue
                raise SourceError(f"下载失败（HTTP {exc.code}）",
                                  detail=url) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise NetworkError(f"下载中断: {getattr(exc, 'reason', exc)}",
                                   retryable=True) from exc

            with resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                encoding = (resp.headers.get("Content-Encoding") or "").lower()
                if "text/html" in ctype and "gzip" not in encoding:
                    body = resp.read()
                    if self._solve_challenge(url, body):
                        continue
                    text = body.decode("utf-8", "replace")
                    if "验证码" in text:
                        raise CaptchaError("网盘要求人机验证", detail=url)
                    raise SourceError("网盘返回网页而不是文件",
                                      detail=text[:120])
                total = int(resp.headers.get("Content-Length") or 0) \
                    or int(expected_size or 0)
                source = resp
                if "gzip" in encoding:
                    source = gzip.GzipFile(fileobj=resp)
                done = 0
                try:
                    with open(tmp, "wb") as out:
                        while True:
                            if cancel is not None and cancel():
                                raise CancelledError("下载已取消")
                            block = source.read(DOWNLOAD_CHUNK)
                            if not block:
                                break
                            out.write(block)
                            done += len(block)
                            if progress is not None:
                                progress(done, total)
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    raise NetworkError(f"下载中断: {exc}", retryable=True) from exc
                if total and done and done < total * 0.99:
                    raise NetworkError(f"下载不完整（{done}/{total}）",
                                       retryable=True)
                os.replace(tmp, dest)
                return done
        raise SourceError("网盘人机校验未通过", detail=url)

    def download(self, file_id: str, dest: str, *, raw_id: str | None = None,
                 progress=None, cancel=None, expected_size: int = 0) -> int:
        """下载一个文件到 dest，返回字节数。失败自动换一条链路重试。"""
        errors: list[OnlineError] = []
        for attempt in range(self.retries):
            try:
                page_url = self.resolve(file_id, raw_id)
                final_url = self._file_url_from_page(page_url)
                return self._stream(final_url, dest, progress=progress,
                                    cancel=cancel, expected_size=expected_size,
                                    referer=page_url)
            except (CancelledError, CaptchaError):
                raise
            except (NetworkError, SourceError) as exc:
                errors.append(exc)
                if self.log:
                    self.log(f"下载重试（{attempt + 1}/{self.retries}）：{exc}",
                             verbose=True)
                if attempt + 1 < self.retries:
                    self._sleep(min(8.0, 1.2 ** attempt))
        if errors:
            raise errors[-1]
        raise SourceError("下载失败")

    def fetch_bytes(self, file_id: str, *, raw_id: str | None = None,
                    limit: int = 8 * 1024 * 1024) -> bytes:
        """取一个小文件的内容（manifest 之类）。"""
        import tempfile
        handle, temp_path = tempfile.mkstemp(prefix="pulses_fetch_")
        os.close(handle)
        try:
            size = self.download(file_id, temp_path, raw_id=raw_id,
                                 expected_size=0)
            if size > limit:
                raise SourceError("文件过大", detail=f"{size} > {limit}")
            with open(temp_path, "rb") as fh:
                return fh.read()
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # 诊断
    # ------------------------------------------------------------------
    def probe(self) -> dict:
        """测试连接：返回文件数 / 总体积 / 是否带 manifest。"""
        files = self.list_files(refresh=True)
        manifest_file = self.find_manifest()
        return {
            "host": self.host_name,
            "count": len(files),
            "total_bytes": sum(f["size_bytes"] for f in files),
            "has_manifest": manifest_file is not None,
            "manifest_name": manifest_file["name"] if manifest_file else "",
            "manifest_legacy": bool(
                manifest_file and
                manifest_file["name"].lower() != MANIFEST_NAME.lower()),
            "files": files,
        }


class _StaleToken(Exception):
    """内部信号：分享页令牌过期，需要重新取。"""


_SIZE_UNITS = {"B": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}


def parse_size(text) -> int:
    """把 ``131.8 K`` / ``1.2M`` 这类字符串变成字节数。"""
    if isinstance(text, (int, float)):
        return int(text)
    match = re.search(r"([\d.]+)\s*([KMGTB]?)", str(text or "").upper())
    if not match:
        return 0
    try:
        number = float(match.group(1))
    except ValueError:
        return 0
    return int(number * _SIZE_UNITS.get(match.group(2) or "B", 1))


def format_size(num) -> str:
    """字节数 → ``131.8 KB``。"""
    try:
        value = float(num)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


if __name__ == "__main__":       # 手工冒烟：python -m online.provider_lanzou <url> <pwd>
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else ""
    secret = sys.argv[2] if len(sys.argv) > 2 else ""
    share = LanzouShare(target, secret)
    listing = share.list_files()
    print(f"共 {len(listing)} 个文件：")
    for row in listing:
        print(f"  {row['size']:>8}  {row['name']}  ({row['file_id']})")
