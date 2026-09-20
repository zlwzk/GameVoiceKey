"""GameVoiceKey · 游戏语音按键自定义助手.

一款全局游戏语音按键映射工具：
- 自动识别当前前台游戏进程，无感切换语音指令配置
- 100% 自定义语音指令 -> 键盘 / 鼠标按键映射
- 多游戏独立存档 + 悬浮窗实时反馈 + 完整日志统计
"""
from __future__ import annotations

__version__ = "0.1.0"
__app_name__ = "GameVoiceKey"
__app_display_name__ = "游戏语音按键自定义助手"
__github_owner__ = "zlwzk"
__github_repo__ = "GameVoiceKey"

# 协议版本：与 .gvprofile / .gvsettings / .gvscene 一起做向后兼容
SCHEMA_VERSION = 1

__all__ = [
    "__version__",
    "__app_name__",
    "__app_display_name__",
    "__github_owner__",
    "__github_repo__",
    "SCHEMA_VERSION",
]
