"""
蓝奏云分享解析（匿名，无需登录）

流程（已对真实分享验证）：
  ① GET  /bXXXX                         → fid / uid / puid / t / k
  ② POST /filemoreajax.php?file=<fid>   → 带密码 → 文件列表
  ③ GET  /<file_id>                     → 页面里 <iframe src="/fn?token">
  ④ GET  /fn?token                      → wp_sign / ajaxdata / domain1 / down_3
  ⑤ POST apifile.../ajaxfile.php?file=  → {"zt":1,"dom":…,"url":…}
  ⑥ GET  <dom>/file/<url>&toolsdown     → 文件本体

只用标准库。不依赖 requests，也不需要任何账号。
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 蓝奏域名会轮换，按顺序尝试
DOMAIN_POOL = ("lanzoul.com", "lanzou.com", "lanzoux.com", "lanzoui.com",
               "lanzoub.com", "lanzoue.com", "lanzoup.com", "lanzouj.com",
               "lanzouy.com")


class LanzouError(Exception):
    """解析失败（网络 / 密码错 / 文件带网页 / 接口变更）。"""


def _var(text: str, name: str) -> str:
    m = re.search(rf"var\s+{name}\s*=\s*'([^']*)'", text)
    return m.group(1) if m else ""


class LanzouShare:
    """一个蓝奏文件夹分享（/bXXXX）。"""

    def __init__(self, share_url: str, password: str = "", timeout: int = 30):
        self.share_url = share_url.rstrip("/")
        self.password = password
        self.timeout = timeout
        m = re.search(r"https?://([^/]+)/([A-Za-z0-9]+)", self.share_url)
        if not m:
            raise LanzouError(f"无法解析分享链接: {share_url}")
        self.host_name, self.share_id = m.group(1), m.group(2)
        self.host = f"https://{self.host_name}"
        self._cj = http.cookiejar.CookieJar()
        self._op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj))
        self._params = None

    # ---------- 基础请求 ----------
    def _get(self, url: str, referer: str | None = None) -> str:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Referer": referer or f"{self.host}/{self.share_id}",
            "Accept": "text/html,application/xhtml+xml,*/*",
        })
        return self._op.open(req, timeout=self.timeout).read().decode(
            "utf-8", "replace")

    def _post(self, url: str, data: dict, referer: str | None = None) -> str:
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode(data).encode(),
            headers={"User-Agent": UA,
                     "Referer": referer or f"{self.host}/{self.share_id}",
                     "Content-Type": "application/x-www-form-urlencoded",
                     "X-Requested-With": "XMLHttpRequest"})
        return self._op.open(req, timeout=self.timeout).read().decode(
            "utf-8", "replace")

    # ---------- ① 分享页参数 ----------
    def _load_params(self) -> dict:
        if self._params:
            return self._params
        html = self._get(f"{self.host}/{self.share_id}")
        fid = re.search(r"'fid':\s*(\d+)", html) or re.search(r"file=(\d+)", html)
        uid = re.search(r"'uid':'(\d+)'", html)
        puid = re.search(r"'puid':'([^']+)'", html)
        if not (fid and uid and puid):
            raise LanzouError("分享页结构异常（可能已失效或改版）")
        self._params = {
            "fid": fid.group(1), "uid": uid.group(1), "puid": puid.group(1),
            "t": _var(html, "ibfbhd"), "k": _var(html, "_hdnj6"),
        }
        return self._params

    # ---------- ② 文件列表 ----------
    def list_files(self) -> list[dict]:
        """返回 [{name, size, file_id, raw_id}]，按名字排序。"""
        p = self._load_params()
        out: list[dict] = []
        page = 1
        while page <= 20:
            raw = self._post(
                f"{self.host}/filemoreajax.php?file={p['fid']}",
                {"lx": 2, "fid": p["fid"], "uid": p["uid"], "puid": p["puid"],
                 "pg": page, "rep": 0, "t": p["t"], "k": p["k"],
                 "up": 1, "ls": 1, "pwd": self.password})
            try:
                data = json.loads(raw)
            except Exception:
                raise LanzouError(f"文件列表返回非 JSON: {raw[:120]}")
            zt = data.get("zt")
            if zt == 3:
                raise LanzouError("分享密码错误")
            if zt == 2:
                break
            if zt != 1:
                raise LanzouError(f"文件列表失败: {data.get('info') or data}")
            items = data.get("text") or []
            for it in items:
                out.append({
                    "name": it.get("name_all", ""),
                    "size": it.get("size", ""),
                    "file_id": it.get("id", "").split("?")[0],
                    "raw_id": it.get("id", ""),
                })
            if len(items) < 50:
                break
            page += 1
        return sorted(out, key=lambda x: x["name"])

    # ---------- ③④⑤ 直链 ----------
    def direct_url(self, file_id: str, raw_id: str | None = None) -> str:
        """文件页 → iframe → apifile → 直链（有时效，别缓存太久）。

        「带网页」文件的 raw_id 带 ?webpage=… 后缀，文件页必须用完整 id 打开；
        而接口用的是 iframe 里的内部 id，所以 file_id 只作兜底。
        """
        page = self._get(f"{self.host}/{raw_id or file_id}")
        m = re.search(r'<iframe[^>]*src="([^"]+)"', page)
        if not m:
            raise LanzouError("文件页没有下载 iframe（可能是「带网页」文件）")
        frame = self._get(f"{self.host}{m.group(1)}", referer=f"{self.host}/{file_id}")
        wp_sign = _var(frame, "wp_sign")
        ajaxdata = _var(frame, "ajaxdata")
        down3 = _var(frame, "down_3")
        dom1 = (re.search(r"var\s+domain1\s*=\s*'([^']+)'", frame) or [None, ""])[1]
        dom2 = (re.search(r"var\s+domain2\s*=\s*'([^']+)'", frame) or [None, ""])[1]
        if not (wp_sign and ajaxdata):
            raise LanzouError("iframe 里没有签名（接口可能改版）")
        last = ""
        for api in (dom1, dom2):
            if not api:
                continue
            try:
                raw = self._post(api, {"action": "downprocess",
                                       "websignkey": ajaxdata, "signs": ajaxdata,
                                       "sign": wp_sign, "websign": "",
                                       "kd": 0, "ves": 1},
                                 referer=f"{self.host}/{file_id}")
                info = json.loads(raw)
            except Exception as exc:
                last = str(exc)
                continue
            if info.get("zt") == 1:
                dom = info.get("dom") or "https://developer2oss.lanzouc.com:661"
                return f"{dom}/file/{info.get('url')}{down3}"
            last = f"zt={info.get('zt')} {info.get('inf') or ''}"
        raise LanzouError(f"取直链失败: {last}")

    # ---------- ⑥ 下载 ----------
    def download(self, file_id: str, dest: str, progress=None,
                 chunk: int = 65536, raw_id: str | None = None) -> int:
        """下载到 dest，返回字节数。蓝奏不支持 Range，失败即整包重来。"""
        url = self.direct_url(file_id, raw_id)
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Referer": f"{self.host}/", "Accept": "*/*"})
        got = 0
        with self._op.open(req, timeout=120) as resp, open(dest, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                fh.write(block)
                got += len(block)
                if progress:
                    progress(got, total)
        return got


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    pwd = sys.argv[2] if len(sys.argv) > 2 else ""
    share = LanzouShare(url, pwd)
    files = share.list_files()
    print(f"共 {len(files)} 个文件：")
    for f in files:
        print(f"  {f['size']:>8}  {f['name']}  ({f['file_id']})")
