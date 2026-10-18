"""
在线功能的统一异常。

所有对外抛出的异常都继承 OnlineError，带三个给人看的东西：
  message  一句话说清发生了什么
  detail   技术细节（进日志 / 诊断面板）
  hint     用户接下来该做什么

界面层只需要 ``str(exc)`` 和 ``exc.hint``，不必认识具体子类。
"""
from __future__ import annotations


class OnlineError(Exception):
    """在线功能所有异常的基类。"""

    code = "online_error"
    default_hint = ""

    def __init__(self, message: str = "", *, detail: str = "", hint: str = "",
                 retryable: bool = False):
        self.message = message or self.__class__.__name__
        self.detail = detail
        self.hint = hint or self.default_hint
        self.retryable = retryable
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

    def user_text(self) -> str:
        """给弹窗用的一行字。"""
        if self.hint:
            return f"{self.message}\n\n{self.hint}"
        return self.message

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message,
                "detail": self.detail, "hint": self.hint,
                "retryable": self.retryable}


class NetworkError(OnlineError):
    """连不上 / 超时 / 服务端 5xx。"""

    code = "network"
    default_hint = "检查网络后重试；公司或校园网可能拦截了网盘域名。"


class AuthError(OnlineError):
    """蓝奏账号登录失败。"""

    code = "auth"
    default_hint = "确认账号密码正确；账号未激活时需先去蓝奏官网激活。"


class SourceError(OnlineError):
    """分享链接失效 / 密码错误 / 解析不出来。"""

    code = "source"
    default_hint = "在预设的「来源」里检查分享链接和密码。"


class CaptchaError(OnlineError):
    """网盘风控要求人机验证（机房 IP 常见）。"""

    code = "captcha"
    default_hint = "换一个网络（手机热点）后重试，或稍等几分钟再来。"


class IntegrityError(OnlineError):
    """下载/解压后校验不通过。"""

    code = "integrity"
    default_hint = "重新同步该枪包；多次失败说明云端文件已损坏，请联系发布者。"


class DiskSpaceError(OnlineError):
    """磁盘剩余空间不够。"""

    code = "disk"
    default_hint = "清理磁盘后重试。"


class ManifestError(OnlineError):
    """manifest 结构异常 / 版本过高。"""

    code = "manifest"
    default_hint = ""


class PackError(OnlineError):
    """打包 / 解包失败。"""

    code = "pack"
    default_hint = ""


class CancelledError(OnlineError):
    """用户主动取消（不算错误，界面单独处理）。"""

    code = "cancelled"
    default_hint = ""

    def __init__(self, message: str = "已取消"):
        super().__init__(message)


class UnsupportedError(OnlineError):
    """当前环境不支持（缺组件 / 平台限制）。"""

    code = "unsupported"
    default_hint = ""
