"""
在线同步的门面（Service）。

把"解析网盘 / 比对 / 下载 / 安装 / 记账"串成两件事：

    check(ref)   检查更新 → Plan
    sync(ref, plan, selection) → SyncResult

界面层只跟这两个方法打交道，不需要知道蓝奏怎么解析、暂存怎么换。
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass, field

from . import diff, hashing, manifest as manifest_mod, paths, trash, updater
from .downloader import Downloader
from .errors import (AuthError, CancelledError, ManifestError, NetworkError,
                     OnlineError, SourceError)
from .provider_lanzou import MANIFEST_NAME, LanzouShare
from .provider_lanzou_account import LanzouAccount
from .publisher import PublishResult, Publisher

# 与主程序 PresetManager 的排除规则保持一致，否则「有改动」会误报
PROTECTED_FILES = {"tacz-pre.toml", ".export-state.json", "blacklist.txt"}
PROTECTED_DIRS = {"tacz_default_gun"}
META_FILES = {"index.json", "version.txt", "description.txt"}

MANIFEST_LIMIT = 8 * 1024 * 1024


@dataclass
class PresetRef:
    """一个预设：名字、元数据目录、内容目录。

    预设"已应用"时，枪包被移到 TACZ 目录里，内容目录和元数据目录不是一个地方。
    """

    name: str
    path: str
    root: str
    applied: bool = False


@dataclass
class SyncResult:
    preset: str = ""
    installed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    bytes_downloaded: int = 0
    version: str = ""
    generation: int = 0
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return not self.failed and not self.cancelled

    def summary(self) -> str:
        bits = []
        if self.installed:
            bits.append(f"安装 {len(self.installed)}")
        if self.removed:
            bits.append(f"删除 {len(self.removed)}")
        if self.failed:
            bits.append(f"失败 {len(self.failed)}")
        return " · ".join(bits) or "没有变化"


_OBFUSCATE_KEY = b"pulses-swap-online"


def _mask(text: str) -> str:
    """本地凭据的"打码"——只是别让明文躺在配置文件里，不是加密。"""
    raw = str(text or "").encode("utf-8")
    mixed = bytes(byte ^ _OBFUSCATE_KEY[i % len(_OBFUSCATE_KEY)]
                  for i, byte in enumerate(raw))
    return base64.b64encode(mixed).decode("ascii")


def _unmask(text: str) -> str:
    try:
        raw = base64.b64decode(str(text or "").encode("ascii"))
    except Exception:
        return ""
    mixed = bytes(byte ^ _OBFUSCATE_KEY[i % len(_OBFUSCATE_KEY)]
                  for i, byte in enumerate(raw))
    try:
        return mixed.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def mask_account(name: str) -> str:
    """给界面看的账号：中间打码，够认人又不用把完整账号写在屏幕上。"""
    text = str(name or "").strip()
    if not text:
        return ""
    if "@" in text:
        user, _, domain = text.partition("@")
        keep = user[:2] if len(user) > 3 else user[:1]
        return f"{keep}***@{domain}"
    if text.isdigit() and len(text) >= 7:
        return f"{text[:3]}****{text[-4:]}"
    if len(text) <= 4:
        return text[0] + "***"
    return f"{text[:2]}***{text[-2:]}"


class AccountStore:
    """account.json：开发者认证信息（只在本机）。

    ``uid`` 是蓝奏的会话 ID（ylogin cookie），不是账号，别拿去登录或显示；
    ``username`` 才是登录用的手机号 / 邮箱。
    """

    VERSION = 1

    def __init__(self, path):
        self.path = str(path)
        self.data: dict = {}
        self.load()

    def load(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if isinstance(data, dict) and data.get("version") == self.VERSION:
            self.data = data
            self._migrate()

    def _migrate(self) -> None:
        """旧版本把会话 ID 当成昵称存了下来 —— 那不是账号，清掉。"""
        uid = str(self.data.get("uid") or "")
        nickname = str(self.data.get("nickname") or "")
        if nickname and nickname == uid:
            self.data.pop("nickname", None)
        if not str(self.data.get("username") or "").strip():
            self.data.pop("username", None)
        if not str(self.data.get("nickname") or "").strip():
            self.data.pop("nickname", None)

    def save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".",
                    exist_ok=True)
        temp = self.path + ".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=1)
        os.replace(temp, self.path)

    @property
    def uid(self) -> str:
        return str(self.data.get("uid") or "")

    @property
    def username(self) -> str:
        """登录用的账号（手机号 / 邮箱）。旧版本没有这一项。"""
        return str(self.data.get("username") or "")

    @property
    def nickname(self) -> str:
        return str(self.data.get("nickname") or "")

    @property
    def label(self) -> str:
        """界面上显示的账号：有登录名就用打码后的登录名。"""
        for value in (self.username, self.nickname):
            if str(value or "").strip():
                return mask_account(value)
        return ""

    def password(self) -> str:
        return _unmask(self.data.get("secret") or "")

    def set(self, uid: str, password: str, nickname: str = "",
            username: str = "") -> None:
        self.data = {"version": self.VERSION, "uid": str(uid),
                     "username": str(username or ""),
                     "nickname": str(nickname or ""),
                     "secret": _mask(password)}
        self.save()

    def clear(self) -> None:
        self.data = {}
        try:
            os.unlink(self.path)
        except OSError:
            pass


class SourceStore:
    """sources.json 的读写。"""

    VERSION = 1

    def __init__(self, path):
        self.path = str(path)
        self.items: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            self.items = {}
            return
        if not isinstance(data, dict) or data.get("version") != self.VERSION:
            return
        sources = data.get("sources")
        if isinstance(sources, dict):
            self.items = {k: v for k, v in sources.items() if isinstance(v, dict)}

    def save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".",
                    exist_ok=True)
        temp = self.path + ".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump({"version": self.VERSION, "sources": self.items},
                      fh, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(temp, self.path)

    def get(self, name: str) -> dict:
        return dict(self.items.get(name) or {})

    def put(self, name: str, data: dict) -> None:
        self.items[name] = dict(data)
        self.save()

    def remove(self, name: str) -> None:
        if name in self.items:
            self.items.pop(name)
            self.save()

    def names(self) -> list[str]:
        return sorted(self.items)


class OnlineService:
    """在线同步门面。所有方法都是同步的，界面层放到工作线程里跑。"""

    def __init__(self, db_path, *, log=None, app_version: str = "",
                 sleep=None, account_base: str | None = None):
        self.db_path = str(db_path)
        self.log = log
        self.app_version = app_version
        self.sleep = sleep
        self.account_base = account_base
        paths.ensure_dirs(self.db_path)
        self.sources = SourceStore(paths.sources_path(self.db_path))
        self.accounts = AccountStore(
            os.path.join(self.db_path, paths.ONLINE_DIRNAME, "account.json"))
        self._account: LanzouAccount | None = None

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------
    def _log(self, message: str, level: str = "INFO", **kwargs) -> None:
        if not self.log:
            return
        try:
            self.log(message, level, **kwargs)
            return
        except TypeError:
            pass
        try:
            self.log(message, level)
            return
        except TypeError:
            pass
        try:
            self.log(message)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 源配置
    # ------------------------------------------------------------------
    def source_of(self, preset: str) -> dict:
        return self.sources.get(preset)

    def bind(self, preset: str, url: str, password: str = "",
             *, cloud_path: str = "", auto_check: bool = True,
             fallback_url: str = "", fallback_password: str = "") -> dict:
        data = self.sources.get(preset)
        data.setdefault("lanzou", {})
        data["lanzou"]["url"] = str(url or "").strip()
        data["lanzou"]["password"] = str(password or "")
        fallback_url = str(fallback_url or "").strip()
        if fallback_url:
            data["lanzou"]["fallback"] = {"url": fallback_url,
                                          "password": str(fallback_password or "")}
        else:
            data["lanzou"].pop("fallback", None)
        data["lanzou"].pop("active_url", None)
        if cloud_path:
            data["cloud_path"] = str(cloud_path).strip()
        data["auto_check"] = bool(auto_check)
        self.sources.put(preset, data)
        self._log(f"预设「{preset}」已绑定源", "SUCCESS")
        return data

    def unbind(self, preset: str) -> None:
        self.sources.remove(preset)

    def is_bound(self, preset: str) -> bool:
        return bool((self.sources.get(preset).get("lanzou") or {}).get("url"))

    def _share_candidates(self, preset: str) -> list[LanzouShare]:
        """主链接 + 备用链接；上次成功的排最前（多源降级）。"""
        lanzou = self.sources.get(preset).get("lanzou") or {}
        active = str(lanzou.get("active_url") or "")
        pairs = [(str(lanzou.get("url") or "").strip(),
                  str(lanzou.get("password") or ""))]
        fallback = lanzou.get("fallback") or {}
        if isinstance(fallback, dict) and fallback.get("url"):
            pairs.append((str(fallback["url"]).strip(),
                          str(fallback.get("password") or "")))
        pairs = [(url, pwd) for url, pwd in pairs if url]
        if not pairs:
            raise SourceError("这个预设还没有绑定云端源",
                              hint="在预设的「来源」里填分享链接和密码。")
        pairs.sort(key=lambda item: 0 if item[0] == active else 1)
        return [LanzouShare(url, pwd, log=self.log, sleep=self.sleep)
                for url, pwd in pairs]

    def _make_share(self, preset: str) -> LanzouShare:
        return self._share_candidates(preset)[0]

    def _mark_active(self, preset: str, url: str) -> None:
        record = self.sources.get(preset)
        lanzou = record.setdefault("lanzou", {})
        if str(lanzou.get("active_url") or "") != url:
            lanzou["active_url"] = url
            self.sources.put(preset, record)

    def test_source(self, url: str, password: str = "") -> dict:
        """测试连接：不写任何状态，只回报能不能用。"""
        share = LanzouShare(url, password, log=self.log, sleep=self.sleep)
        info = share.probe()
        info["manifest_ok"] = False
        if info["has_manifest"]:
            try:
                self._fetch_manifest(share)
                info["manifest_ok"] = True
            except OnlineError as exc:
                info["manifest_error"] = str(exc)
        return info

    # ------------------------------------------------------------------
    # manifest 缓存
    # ------------------------------------------------------------------
    def _fetch_manifest(self, share: LanzouShare) -> dict:
        found = share.find_file(MANIFEST_NAME)
        if not found:
            raise SourceError(
                "云端还没有发布内容",
                hint="让发布者先发布一次；或检查分享链接是不是这个预设的。")
        raw = share.fetch_bytes(found["file_id"], raw_id=found["raw_id"],
                                limit=MANIFEST_LIMIT)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ManifestError("云端 manifest 不是合法 JSON",
                                detail=str(exc)) from exc
        return manifest_mod.normalize(data)

    def _fetch_manifest_bounded(self, share: LanzouShare,
                                timeout: float = 25.0) -> dict:
        """读分享里的 manifest，最多等 timeout 秒。

        网盘抽风时「解析分享页 → 轮询直链」这条重试链能卡好几分钟，
        界面上就是「一直在检查、连不上」。到点直接放弃，让调用方退回缓存。
        """
        box: dict = {}

        def work():
            try:
                box["data"] = self._fetch_manifest(share)
            except OnlineError as exc:
                box["error"] = exc
            except Exception as exc:                    # noqa: BLE001
                box["error"] = exc

        worker = threading.Thread(target=work, daemon=True,
                                  name="manifest-read")
        worker.start()
        worker.join(max(3.0, float(timeout)))
        if worker.is_alive():
            raise NetworkError(f"读取云端内容超过 {int(timeout)} 秒",
                               hint="网络不太顺，稍后再试。", retryable=True)
        if "data" in box:
            return box["data"]
        error = box.get("error")
        if isinstance(error, OnlineError):
            raise error
        if error is not None:
            raise NetworkError(f"读取云端内容失败：{error}")
        raise NetworkError("读取云端内容失败")

    def _save_cloud_manifest(self, preset: str, data: dict) -> None:
        try:
            manifest_mod.save(data, paths.cloud_manifest_path(self.db_path, preset))
        except OSError as exc:
            self._log(f"保存云端 manifest 失败: {exc}", "WARNING")

    def load_cloud_manifest(self, preset: str) -> dict | None:
        path = paths.cloud_manifest_path(self.db_path, preset)
        if not os.path.isfile(path):
            return None
        try:
            return manifest_mod.load(path)
        except (ManifestError, OSError):
            return None

    def save_local_manifest(self, preset: str, entries: list[dict]) -> None:
        path = paths.local_manifest_path(self.db_path, preset)
        data = {"schema": manifest_mod.SCHEMA, "name": preset,
                "files": entries}
        try:
            manifest_mod.save(data, path)
        except (ManifestError, OSError):
            pass

    def load_local_manifest(self, preset: str) -> list[dict]:
        path = paths.local_manifest_path(self.db_path, preset)
        if not os.path.isfile(path):
            return []
        try:
            return manifest_mod.load(path).get("files", [])
        except (ManifestError, OSError):
            return []

    def _touch_source(self, preset: str, data: dict) -> None:
        record = self.sources.get(preset)
        record["last_version"] = str(data.get("version") or "")
        record["last_generation"] = int(data.get("generation") or 0)
        record["last_check"] = int(time.time())
        self.sources.put(preset, record)

    def _sanitize_cloud(self, cloud: dict) -> dict:
        """丢掉 manifest 里那些"永远不会出现在本地"的元数据条目。

        扫描时被排除的文件（index.json / description.txt / .DS_Store …）如果
        出现在 manifest 里，会变成"云端有、本地没有"→ 每次检查都提示更新，
        用户点同步又装不进去，死循环。这里直接过滤掉。
        """
        files = cloud.get("files") or []
        kept, dropped = [], []
        for entry in files:
            head = str(entry.get("path") or "").split("/")[0]
            if hashing.is_metadata_name(head):
                dropped.append(entry.get("path"))
            else:
                kept.append(entry)
        if dropped:
            self._log(f"manifest 含 {len(dropped)} 个元数据文件，已忽略："
                      f"{dropped[:3]}", "WARNING")
            cloud = dict(cloud)
            cloud["files"] = kept
        return cloud

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------
    def scan(self, ref: PresetRef, *, should_stop=None) -> list[dict]:
        cache = hashing.HashCache(paths.cache_path(self.db_path, ref.root),
                                  root=ref.root)
        entries = hashing.scan_local(ref.root, cache, should_stop=should_stop)
        self.save_local_manifest(ref.name, entries)
        return entries

    def inspect_share(self, url: str, password: str = "") -> dict:
        """只读地看一眼分享里有什么（用于"从云端添加预设"）。"""
        share = LanzouShare(url, password, log=self.log, sleep=self.sleep)
        manifest = self._fetch_manifest(share)
        total = sum(int(entry.get("packed_size") or entry.get("size") or 0)
                    for entry in manifest.get("files") or [])
        return {"name": str(manifest.get("name") or ""),
                "version": str(manifest.get("version") or ""),
                "files": len(manifest.get("files") or []),
                "total_bytes": total,
                "notes": str(manifest.get("notes") or ""),
                "manifest": manifest}

    # ------------------------------------------------------------------
    # 检查更新
    # ------------------------------------------------------------------
    def check(self, ref: PresetRef, *, role: str = "player",
              allow_cache: bool = True,
              max_file_size: int = diff.DEFAULT_MAX_FILE,
              on_phase=None) -> diff.Plan:
        def phase(text: str) -> None:
            if on_phase is not None:
                try:
                    on_phase(text)
                except Exception:                       # noqa: BLE001
                    pass

        cloud = None
        offline = False
        source_error = ""
        last_error: OnlineError | None = None
        phase("连接云端…")
        # 主链接 + 备用链接一共只给 45 秒：别在一个源上吊死
        deadline = time.monotonic() + 45.0
        for share in self._share_candidates(ref.name):
            remaining = deadline - time.monotonic()
            if remaining < 4:
                break
            try:
                cloud = self._fetch_manifest_bounded(
                    share, timeout=min(25.0, remaining))
                self._mark_active(ref.name, share.share_url)
                self._save_cloud_manifest(ref.name, cloud)
                self._touch_source(ref.name, cloud)
                break
            except OnlineError as exc:
                last_error = exc
                self._log(f"源不可用（{share.share_url}）：{exc}", "WARNING")
        if cloud is None:
            source_error = str(last_error or "没有可用的源")
            if allow_cache:
                cloud = self.load_cloud_manifest(ref.name)
                offline = cloud is not None
            if cloud is None:
                raise last_error or SourceError(source_error)
            self._log(f"云端不可用，改用上次缓存：{source_error}", "WARNING")

        cloud = self._sanitize_cloud(cloud)
        phase("扫描本地文件…")
        local = self.scan(ref)
        plan = diff.compare(local, cloud, role=role,
                            app_version=self.app_version,
                            max_file_size=max_file_size)
        plan.offline = offline
        plan.source_error = source_error
        return plan

    # ------------------------------------------------------------------
    # 同步
    # ------------------------------------------------------------------
    def sync(self, ref: PresetRef, plan: diff.Plan, selection,
             *, on_item=None, on_progress=None, cancel=None) -> SyncResult:
        items = plan.selected_items(selection)
        downloads = [i for i in items if i.action in (diff.DOWNLOAD, diff.REPAIR)]
        removals = [i for i in items
                    if i.action in (diff.DELETE_LOCAL, diff.ASK_DELETE_LOCAL)]
        result = SyncResult(preset=ref.name,
                            version=plan.cloud_version,
                            generation=plan.cloud_generation)

        staging = paths.staging_dir(self.db_path, ref.name)
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        installer = updater.Installer(ref.root, str(staging), log=self.log)

        try:
            if downloads:
                share = self._make_share(ref.name)
                downloader = Downloader(share, str(staging), log=self.log,
                                        cancel=cancel)
                results = downloader.run(
                    [i.cloud for i in downloads],
                    on_item=on_item, on_progress=on_progress)
                for item, outcome in zip(downloads, results):
                    if not outcome.ok:
                        result.failed.append((item.path, outcome.error))
                        continue
                    try:
                        installer.install(outcome.entry, outcome.staged)
                        result.installed.append(item.path)
                        result.bytes_downloaded += outcome.bytes
                    except (OSError, OnlineError) as exc:
                        result.failed.append((item.path, str(exc)))
                        self._log(f"安装失败 {item.path}: {exc}", "ERROR")

            for item in removals:
                if cancel is not None and cancel():
                    raise CancelledError("同步已取消")
                entry = item.local or {}
                if installer.remove_local(entry):
                    result.removed.append(item.path)

            self._finish(ref, plan, result, all_ok=not result.failed)
            return result
        except CancelledError:
            # 取消不是失败：把已经装好的部分如实报出去，让界面能显示进度
            result.cancelled = True
            return result
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _finish(self, ref: PresetRef, plan: diff.Plan,
                result: SyncResult, *, all_ok: bool) -> None:
        """同步成功后更新 index.json / version.txt / 本地 manifest。"""
        cloud = self.load_cloud_manifest(ref.name) or {}
        if all_ok and cloud.get("files"):
            self.save_local_manifest(ref.name, cloud["files"])
        else:
            self.scan(ref)

        try:
            self.update_index(ref, version=plan.cloud_version)
        except OSError as exc:
            self._log(f"更新 index.json 失败: {exc}", "WARNING")

        record = self.sources.get(ref.name)
        record["last_sync"] = int(time.time())
        record["last_version"] = plan.cloud_version or record.get("last_version", "")
        record["last_generation"] = plan.cloud_generation
        self.sources.put(ref.name, record)

    # ------------------------------------------------------------------
    # index.json / version.txt
    # ------------------------------------------------------------------
    def fingerprints_of(self, root: str) -> dict:
        """按主程序的口径，列出 root 下的枪包指纹。"""
        out: dict[str, dict] = {}
        if not os.path.isdir(root):
            return out
        try:
            names = sorted(os.listdir(root))
        except OSError:
            return out
        for name in names:
            if name in META_FILES or name in PROTECTED_FILES \
                    or name in PROTECTED_DIRS or name.startswith("."):
                continue
            fingerprint = hashing.item_fingerprint(os.path.join(root, name))
            if fingerprint:
                out[name] = fingerprint
        return out

    def update_index(self, ref: PresetRef, *, version: str = "") -> dict:
        """把 index.json 与 version.txt 对齐到当前内容。"""
        index_file = os.path.join(ref.path, "index.json")
        data: dict = {}
        if os.path.isfile(index_file):
            try:
                with open(index_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                data = {}
        data["name"] = ref.name
        if version:
            data["version"] = version
        data.setdefault("version", "v1.0.0")
        data["gunpacks"] = self.fingerprints_of(ref.root)
        data["applied"] = bool(data.get("applied", ref.applied))
        data.setdefault("incremental_count", 0)
        os.makedirs(ref.path, exist_ok=True)
        with open(index_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        try:
            with open(os.path.join(ref.path, "version.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(str(data.get("version") or ""))
        except OSError:
            pass
        return data

    # ------------------------------------------------------------------
    # 诊断
    # ------------------------------------------------------------------
    def diagnose(self, ref: PresetRef, *, role: str = "player",
                 deep: bool = True) -> dict:
        """自检：把"能不能同步"拆成一条条能看懂的结果。

        deep=False 只查本地（不碰网络），deep=True 会真的去读一次云端 manifest。
        """
        checks: list[dict] = []

        def add(name: str, ok: bool, detail: str = "") -> None:
            checks.append({"name": name, "ok": bool(ok),
                           "detail": str(detail or "")})

        # ① 状态目录
        try:
            paths.ensure_dirs(self.db_path)
            probe = os.path.join(self.db_path, paths.ONLINE_DIRNAME,
                                 ".write_probe")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.unlink(probe)
            add("状态目录可写", True, str(paths.online_dir(self.db_path)))
        except OSError as exc:
            add("状态目录可写", False, exc)

        # ② 本地内容目录
        try:
            root = os.path.abspath(ref.root)
            exists = os.path.isdir(root)
            add("预设目录存在", exists, root)
            if exists:
                free = self._free_space(root)
                add("磁盘剩余空间", free > 64 * 1024 * 1024,
                    f"{free / 1048576:.0f} MB")
        except OSError as exc:
            add("预设目录存在", False, exc)

        # ③ 源配置
        source = self.sources.get(ref.name)
        lanzou = source.get("lanzou") or {}
        if role == "developer":
            cloud_path = str(source.get("cloud_path") or "")
            add("已填云端路径", bool(cloud_path), cloud_path or "未填")
            add("账号已认证", self.has_account(),
                self.accounts.uid or "未登录")
        else:
            url = str(lanzou.get("url") or "")
            add("已绑定分享链接", bool(url), url or "未绑定")
            if url:
                add("分享密码", True,
                    "已填写" if lanzou.get("password") else "未填（公开分享）")

        # ④ 云端可达性（可选）
        if deep:
            if role == "developer":
                try:
                    account = self._require_account()
                    folder = self._folder_of(ref.name, account)
                    add("云端目录可用", True, f"folder #{folder}")
                except OnlineError as exc:
                    add("云端目录可用", False, exc)
            elif lanzou.get("url"):
                try:
                    share = LanzouShare(lanzou.get("url"), lanzou.get("password") or "",
                                        log=self.log, sleep=self.sleep)
                    listing = share.list_files(refresh=True)
                    add("分享链接可访问", True, f"{len(listing)} 个文件")
                    try:
                        cloud = self._fetch_manifest(share)
                        add("云端 manifest 可读", True,
                            f"v{cloud.get('version') or '?'} · "
                            f"generation {cloud.get('generation')}")
                        min_app = str(cloud.get("min_app") or "")
                        if min_app and self.app_version:
                            from .manifest import is_newer
                            add("程序版本满足要求",
                                not is_newer(min_app, self.app_version),
                                f"需要 {min_app}，当前 {self.app_version}")
                    except OnlineError as exc:
                        add("云端 manifest 可读", False, exc)
                except OnlineError as exc:
                    add("分享链接可访问", False, exc)

        return {"preset": ref.name, "role": role,
                "ok": all(item["ok"] for item in checks),
                "checks": checks}

    @staticmethod
    def _free_space(path: str) -> int:
        try:
            import shutil as _shutil
            return _shutil.disk_usage(path).free
        except OSError:
            return 0

    # ------------------------------------------------------------------
    # 启动维护
    # ------------------------------------------------------------------
    def recover_all(self) -> list[str]:
        """处理上次中断的安装（程序被强杀时留下的半成品）。"""
        notes: list[str] = []
        root_dir = paths.staging_root(self.db_path)
        if not root_dir.is_dir():
            return notes
        for child in sorted(root_dir.iterdir()):
            if not child.is_dir():
                continue
            journal = child / "journal.json"
            target = ""
            if journal.is_file():
                try:
                    with open(journal, "r", encoding="utf-8") as fh:
                        target = str(json.load(fh).get("root") or "")
                except (OSError, ValueError):
                    target = ""
            if target:
                installer = updater.Installer(target, str(child), log=self.log)
                notes.extend(installer.recover())
            else:
                shutil.rmtree(child, ignore_errors=True)
        return notes

    def cache_size(self) -> int:
        """在线缓存（manifest 存档 + 哈希缓存 + 暂存）占了多少字节。"""
        total = 0
        for base in (paths.cloud_dir(self.db_path), paths.cache_dir(self.db_path),
                     paths.local_dir(self.db_path),
                     paths.staging_root(self.db_path)):
            if not os.path.isdir(base):
                continue
            for dirpath, _dirnames, filenames in os.walk(base):
                for name in filenames:
                    try:
                        total += os.path.getsize(os.path.join(dirpath, name))
                    except OSError:
                        pass
        return total

    def clear_caches(self) -> int:
        """清掉哈希缓存与暂存（保留 sources.json 与云端 manifest 存档）。"""
        freed = 0
        for base in (paths.cache_dir(self.db_path),
                     paths.staging_root(self.db_path)):
            if not os.path.isdir(base):
                continue
            for dirpath, _dirnames, filenames in os.walk(base):
                for name in filenames:
                    try:
                        freed += os.path.getsize(os.path.join(dirpath, name))
                    except OSError:
                        pass
            shutil.rmtree(base, ignore_errors=True)
        paths.ensure_dirs(self.db_path)
        return freed

    def cleanup_staging(self) -> None:
        shutil.rmtree(paths.staging_root(self.db_path), ignore_errors=True)
        paths.ensure_dirs(self.db_path)

    # ------------------------------------------------------------------
    # 开发者认证
    # ------------------------------------------------------------------
    def account_info(self) -> dict:
        return {"uid": self.accounts.uid,
                "username": self.accounts.username,
                "nickname": self.accounts.nickname,
                "label": self.accounts.label,
                "saved": bool(self.accounts.uid)}

    def has_account(self) -> bool:
        return bool(self.accounts.uid)

    def login(self, username: str, password: str, *,
              remember: bool = True) -> dict:
        """登录并验证会话可用；成功后按需记住。"""
        account = LanzouAccount(base=self.account_base)
        account.login(username, password)
        folders = account.list_folders(-1)          # 顺手验证 cookie 真的能用
        self._account = account
        if remember:
            # 记住的是登录名（手机号/邮箱）：会话 ID 没法用来重新登录
            self.accounts.set(account.uid or "", password,
                              nickname=account.nickname or "",
                              username=username)
        self._log(f"蓝奏账号已登录（{mask_account(username) or '已认证'}，"
                  f"{len(folders)} 个根目录）", "SUCCESS")
        return {"uid": account.uid or "",
                "username": username,
                "label": self.accounts.label,
                "folders": len(folders)}

    def logout(self, *, forget: bool = True) -> None:
        self._account = None
        if forget:
            self.accounts.clear()
        self._log("已退出蓝奏账号", "INFO")

    def restore_account(self) -> bool:
        """启动时用记住的凭据静默登录。失败不抛异常，只是返回 False。"""
        if not self.accounts.uid:
            return False
        password = self.accounts.password()
        if not password:
            return False
        # 新格式用登录名（手机号/邮箱）。旧格式只有会话 ID —— 那不是账号，
        # 但有些网盘也认，就当兜底试一次，失败了再让人重新登录。
        candidates = [self.accounts.username] if self.accounts.username \
            else [self.accounts.uid]
        for username in candidates:
            try:
                account = LanzouAccount(base=self.account_base)
                account.login(username, password)
                self._account = account
                return True
            except OnlineError as exc:
                self._log(f"自动登录失败：{exc}", "WARNING")
        return False

    def _require_account(self) -> LanzouAccount:
        if self._account is None or not self._account.logged_in:
            if not self.restore_account():
                raise AuthError("需要先登录蓝奏账号",
                                hint="在「身份」里切换到开发者并完成认证。")
        return self._account

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------
    def cloud_path_of(self, preset: str) -> str:
        return str(self.sources.get(preset).get("cloud_path") or "")

    def set_cloud_path(self, preset: str, cloud_path: str) -> None:
        record = self.sources.get(preset)
        record["cloud_path"] = str(cloud_path or "").strip()
        record.pop("folder_id", None)
        self.sources.put(preset, record)

    def _remember_share(self, preset: str, share_url: str,
                        share_password: str = "") -> None:
        """把发布后拿到的分享链接同时记进 lanzou.url —— 来源页要显示它。

        只写 top-level 的 share_url 的话，发布完成卡片一关，开发者就再也
        找不到分享链接了（来源页读的是 lanzou.url）。
        """
        if not share_url:
            return
        record = self.sources.get(preset)
        record["share_url"] = str(share_url)
        record["share_password"] = str(share_password or "")
        lanzou = record.setdefault("lanzou", {})
        lanzou["url"] = str(share_url)
        lanzou["password"] = str(share_password or "")
        self.sources.put(preset, record)

    def _folder_of(self, preset: str, account: LanzouAccount) -> int:
        record = self.sources.get(preset)
        cloud_path = str(record.get("cloud_path") or "").strip()
        if not cloud_path:
            raise SourceError("还没有填云端路径",
                              hint="例如 /PulsesSwap/SSR预设包")
        folder = account.ensure_path(cloud_path)
        if record.get("folder_id") != folder:
            record["folder_id"] = folder
            self.sources.put(preset, record)
        return folder

    def _cloud_manifest_for_publish(self, preset: str, account: LanzouAccount,
                                    folder: int) -> dict:
        """开发者侧读云端 manifest：用自己文件夹的分享链接去取。

        取不到就退回上次缓存——发布器会先删同名文件，所以即使缓存旧了也不会
        传重复文件，只是多做几次删除。
        """
        cached = self.load_cloud_manifest(preset)

        # 先看文件夹里到底有没有东西：新建的空文件夹根本不需要去抓分享页，
        # 抓了会走一遍「解析分享页 + 轮询直链」的重试链，表现就是一直"检查中"。
        try:
            files = account.list_files(folder)
        except OnlineError as exc:
            # 账号接口都不通的时候，分享页那条路只会更慢（分钟级）。
            # 有缓存就用缓存；连缓存都没有就明确报错 —— 不能假装「云端是空的」，
            # 否则界面会显示「有 N 项待发布」，用户一发布就是整包重传。
            self._log(f"列云端文件失败：{exc}", "WARNING")
            if cached is not None:
                self._log("改用上次缓存的云端 manifest 进行比对", "WARNING")
                return cached
            raise SourceError(f"无法读取云端文件夹：{exc}",
                              hint="检查网络，或确认云端路径还在。") from exc

        names = {str(f.get("name") or "").lower() for f in files}
        if not names or MANIFEST_NAME.lower() not in names:
            # 空目录，或只有半成品（没 manifest）→ 视为云端为空，
            # 让发布把本地全量传上去
            return manifest_mod.empty_manifest(preset)

        record = self.sources.get(preset)
        share_url = str(record.get("share_url") or "")
        share_password = str(record.get("share_password") or "")
        try:
            share = account.folder_share(folder)
            share_url = share.get("url") or share_url
            share_password = share.get("password") or share_password
            if share_url:
                self._remember_share(preset, share_url, share_password)
        except OnlineError as exc:
            self._log(f"取分享链接失败：{exc}", "WARNING")

        if share_url:
            try:
                reader = LanzouShare(share_url, share_password, log=self.log,
                                     sleep=self.sleep)
                data = self._fetch_manifest_bounded(reader)
                self._save_cloud_manifest(preset, data)
                return data
            except OnlineError as exc:
                self._log(f"读取云端 manifest 失败：{exc}", "WARNING")

        if cached is not None:
            self._log("使用上次缓存的云端 manifest 进行比对", "WARNING")
            return cached
        return manifest_mod.empty_manifest(preset)

    def test_cloud_path(self, cloud_path: str) -> dict:
        """测试云端路径：连得上、文件夹建得出来、里面有几个文件。

        开发者只填云端路径（没有分享链接）时，「测试连接」走这条。
        """
        account = self._require_account()
        path = str(cloud_path or "").strip()
        if not path:
            raise SourceError("还没有填云端路径", hint="例如 test")
        folder = account.ensure_path(path)
        files = account.list_files(folder)
        names = {str(f.get("name") or "").lower() for f in files}
        self._log(f"云端路径可用：{path}（{len(files)} 个文件）", "SUCCESS")
        return {"path": path, "files": len(files),
                "has_manifest": MANIFEST_NAME.lower() in names}

    def publish_plan(self, ref: PresetRef, *, on_phase=None) -> diff.Plan:
        """开发者侧：扫描本地 + 读云端 → 差异计划。"""
        def phase(text: str) -> None:
            if on_phase is not None:
                try:
                    on_phase(text)
                except Exception:                       # noqa: BLE001
                    pass

        phase("连接云端…")
        account = self._require_account()
        folder = self._folder_of(ref.name, account)
        phase("读取云端…")
        cloud = self._cloud_manifest_for_publish(ref.name, account, folder)
        cloud = self._sanitize_cloud(cloud)
        phase("扫描本地文件…")
        local = self.scan(ref)
        plan = diff.compare(local, cloud, role="developer",
                            app_version=self.app_version)
        plan.cloud_name = plan.cloud_name or ref.name
        return plan

    def publish(self, ref: PresetRef, plan: diff.Plan, selection,
                *, version: str, notes: str = "", min_app: str = "",
                on_item=None, on_progress=None,
                cancel=None) -> PublishResult:
        account = self._require_account()
        folder = self._folder_of(ref.name, account)
        entries = self.scan(ref)
        staging = paths.staging_dir(self.db_path, ref.name)
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        publisher = Publisher(account, str(staging), ref.root,
                              log=self.log, cancel=cancel)
        try:
            result = publisher.publish(
                folder_id=folder, plan=plan, entries=entries,
                selection=selection, version=version, notes=notes,
                min_app=min_app, name=ref.name,
                previous_generation=plan.cloud_generation,
                on_item=on_item, on_progress=on_progress)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        if result.ok:
            self._record_publish(ref.name, result, plan)
        return result

    def _record_publish(self, preset: str, result: PublishResult,
                        plan: diff.Plan) -> None:
        record = self.sources.get(preset)
        record["last_version"] = result.version
        record["last_generation"] = result.generation
        record["last_publish"] = int(time.time())
        if result.share_url:
            record["share_url"] = result.share_url
            record["share_password"] = result.share_password
            lanzou = record.setdefault("lanzou", {})
            lanzou["url"] = result.share_url
            lanzou["password"] = result.share_password
        history = list(record.get("history") or [])
        history.insert(0, {"version": result.version,
                           "generation": result.generation,
                           "at": int(time.time()),
                           "uploaded": len(result.uploaded),
                           "bytes": result.bytes_uploaded,
                           "notes": plan.cloud_notes})
        record["history"] = history[:20]
        self.sources.put(preset, record)
        if result.manifest:
            self._save_cloud_manifest(preset, result.manifest)

    def publish_history(self, preset: str) -> list[dict]:
        return list(self.sources.get(preset).get("history") or [])

    # ------------------------------------------------------------------
    def delete_local_extra(self, ref: PresetRef, entry: dict) -> bool:
        """把本地多余的文件送进回收站（界面在用户确认后调用）。"""
        target = os.path.join(ref.root, entry.get("target") or entry.get("path"))
        if not os.path.exists(target):
            return True
        ok = trash.delete(target)
        self._log(f"{'已删除' if ok else '删除失败'}：{os.path.basename(target)}",
                  "INFO" if ok else "ERROR")
        if ok:
            self.scan(ref)
        return ok

