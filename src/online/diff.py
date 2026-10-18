"""
差异引擎：本地 manifest × 云端 manifest，两方比对。

不做三方比对、不做玩家回滚。同一份差异，角色不同动作不同：

| 本地 | 云端 | 玩家 | 开发者 |
|------|------|------|--------|
| 无   | 有   | 下载 | 删除云端 |
| 有   | 有，摘要相同 | 跳过 | 跳过 |
| 有   | 有，摘要不同 | 下载覆盖 | 上传覆盖 |
| 有   | 无   | 询问是否删除（默认保留） | 上传 |
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .manifest import is_newer

# ---- 动作词表 ----
DOWNLOAD = "download"
UPLOAD = "upload"
SKIP = "skip"
DELETE_CLOUD = "delete_cloud"
DELETE_LOCAL = "delete_local"
ASK_DELETE_LOCAL = "ask_delete_local"
REPAIR = "repair"
BLOCKED = "blocked"

PLAYER_ACTIONS = (DOWNLOAD, REPAIR, SKIP, ASK_DELETE_LOCAL, DELETE_LOCAL, BLOCKED)
DEVELOPER_ACTIONS = (UPLOAD, SKIP, DELETE_CLOUD, BLOCKED)

# 网盘单文件上限（蓝奏免费账号 100MB）
DEFAULT_MAX_FILE = 100 * 1024 * 1024

ACTION_LABELS = {
    DOWNLOAD: "下载",
    UPLOAD: "上传",
    SKIP: "一致",
    DELETE_CLOUD: "删除云端",
    DELETE_LOCAL: "删除本地",
    ASK_DELETE_LOCAL: "本地多余",
    REPAIR: "修复",
    BLOCKED: "无法处理",
}


@dataclass(frozen=True)
class DiffItem:
    """一条差异。local / cloud 是 manifest 里的条目（可能只有一边）。"""

    path: str
    action: str
    local: dict | None = None
    cloud: dict | None = None
    reason: str = ""
    size: int = 0

    @property
    def display_name(self) -> str:
        """给人看的名字：文件夹型显示目录名，其余显示文件名。"""
        entry = self.cloud or self.local or {}
        if entry.get("type") == "folder":
            return str(entry.get("target") or entry.get("path") or self.path)
        return str(entry.get("path") or self.path)

    @property
    def is_folder(self) -> bool:
        entry = self.cloud or self.local or {}
        return entry.get("type") == "folder"

    @property
    def default_checked(self) -> bool:
        """确认框里默认勾不勾。删云端 / 删本地默认不勾。"""
        return self.action in (DOWNLOAD, UPLOAD, REPAIR)

    @property
    def is_transfer(self) -> bool:
        return self.action in (DOWNLOAD, UPLOAD, REPAIR)


@dataclass
class Plan:
    role: str
    items: list[DiffItem] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    cloud_name: str = ""
    cloud_version: str = ""
    cloud_generation: int = 0
    cloud_notes: str = ""
    cloud_generated_at: str = ""
    local_version: str = ""
    offline: bool = False
    source_error: str = ""

    # ---------- 统计 ----------
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for item in self.items:
            out[item.action] = out.get(item.action, 0) + 1
        return out

    def count_of(self, action: str) -> int:
        return sum(1 for item in self.items if item.action == action)

    @property
    def transfer_items(self) -> list[DiffItem]:
        return [i for i in self.items if i.is_transfer]

    @property
    def download_bytes(self) -> int:
        return sum(i.size for i in self.items if i.action in (DOWNLOAD, REPAIR))

    @property
    def upload_bytes(self) -> int:
        return sum(i.size for i in self.items if i.action == UPLOAD)

    @property
    def has_changes(self) -> bool:
        return any(i.action != SKIP for i in self.items)

    @property
    def is_clean(self) -> bool:
        """没有任何差异（全是 skip）。"""
        return not self.has_changes

    def summary(self) -> str:
        """一行摘要，给卡片和日志用。"""
        c = self.counts()
        bits = []
        for action, label in ((DOWNLOAD, "待下载"), (UPLOAD, "待上传"),
                              (ASK_DELETE_LOCAL, "本地多余"),
                              (DELETE_CLOUD, "云端多余"),
                              (SKIP, "一致")):
            if c.get(action):
                bits.append(f"{label} {c[action]}")
        return " · ".join(bits) or "无差异"

    def cloud_entries(self, selection=None) -> list[dict]:
        """挑出要下载的云端条目（可直接喂给 Downloader）。

        selection 为 None 时取全部 download/repair 项。
        """
        keys = None if selection is None else {str(s).lower() for s in selection}
        out = []
        for item in self.items:
            if item.action not in (DOWNLOAD, REPAIR) or not item.cloud:
                continue
            if keys is not None and item.path.lower() not in keys:
                continue
            out.append(item.cloud)
        return out

    def selected_items(self, selection) -> list[DiffItem]:
        """按勾选集合挑出要执行的条目。selection 为 path 集合（大小写不敏感）。"""
        keys = {str(s).lower() for s in selection}
        return [i for i in self.items
                if i.action not in (SKIP, BLOCKED) and i.path.lower() in keys]


def _same_content(local: dict, cloud: dict) -> bool:
    if (local.get("type") or "") != (cloud.get("type") or ""):
        return False
    if (local.get("target") or "") != (cloud.get("target") or ""):
        return False
    if not local.get("sha256") or not cloud.get("sha256"):
        return False
    return local["sha256"] == cloud["sha256"]


def _transfer_size(entry: dict) -> int:
    return int(entry.get("packed_size") or entry.get("size") or 0)


def compare(local_files, cloud_manifest: dict, *, role: str = "player",
            app_version: str = "", max_file_size: int = DEFAULT_MAX_FILE,
            allow_delete_cloud: bool = True) -> Plan:
    """比对本地条目与云端 manifest，产出计划。

    local_files 可以是 ``scan_local`` 的结果，也可以是上次存下的本地 manifest
    的 files 数组。
    """
    role = "developer" if str(role).lower().startswith("dev") else "player"
    cloud_files = cloud_manifest.get("files") or []
    plan = Plan(role=role,
                cloud_name=str(cloud_manifest.get("name") or ""),
                cloud_version=str(cloud_manifest.get("version") or ""),
                cloud_generation=int(cloud_manifest.get("generation") or 0),
                cloud_notes=str(cloud_manifest.get("notes") or ""),
                cloud_generated_at=str(cloud_manifest.get("generated_at") or ""))

    # 程序版本过低：整份计划作废，别让用户下到装不上的东西
    min_app = str(cloud_manifest.get("min_app") or "")
    if role == "player" and min_app and app_version and is_newer(min_app, app_version):
        plan.blocked.append(
            f"云端要求 Pulses Swap {min_app} 或更高版本，当前是 {app_version}")

    local_map = {str(e.get("path", "")).lower(): e for e in local_files}
    cloud_map = {str(e.get("path", "")).lower(): e for e in cloud_files}

    for key in sorted(set(local_map) | set(cloud_map)):
        local = local_map.get(key)
        cloud = cloud_map.get(key)
        path = str((cloud or local or {}).get("path") or key)

        if local and cloud:
            if _same_content(local, cloud):
                plan.items.append(DiffItem(path, SKIP, local, cloud, "内容一致", 0))
                continue
            size = _transfer_size(cloud if role == "player" else local)
            if role == "player":
                reason = ("云端类型变了" if local.get("type") != cloud.get("type")
                          else "云端有新版本")
                action = DOWNLOAD
            else:
                reason = ("类型变了" if local.get("type") != cloud.get("type")
                          else "本地已更新")
                action = UPLOAD
        elif cloud and not local:
            size = _transfer_size(cloud)
            action = DOWNLOAD if role == "player" else DELETE_CLOUD
            reason = "云端新增" if role == "player" else "云端多出来的文件"
        else:
            size = _transfer_size(local)
            action = ASK_DELETE_LOCAL if role == "player" else UPLOAD
            reason = "本地多出来的文件" if role == "player" else "本地新增"

        # 单文件超限：蓝奏传不上去也下不来
        if size > max_file_size and action in (DOWNLOAD, UPLOAD, REPAIR):
            plan.items.append(DiffItem(
                path, BLOCKED, local, cloud,
                f"超过网盘单文件上限（{size / 1048576:.0f}MB > "
                f"{max_file_size / 1048576:.0f}MB）", size))
            continue

        if action == DELETE_CLOUD and not allow_delete_cloud:
            plan.items.append(DiffItem(path, SKIP, local, cloud,
                                       "保留云端文件", size))
            continue

        plan.items.append(DiffItem(path, action, local, cloud, reason, size))

    return plan


def selection_of(plan: Plan, *, include_deletes: bool = False) -> set[str]:
    """默认勾选集合。include_deletes=True 时把"删除"类也勾上。"""
    out = set()
    for item in plan.items:
        if item.is_transfer or (include_deletes and item.action in
                                (DELETE_CLOUD, ASK_DELETE_LOCAL)):
            out.add(item.path)
    return out
