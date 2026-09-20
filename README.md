# GameVoiceKey · 游戏语音按键自定义助手

> 一款全自定的全局游戏语音按键映射工具——把"语音指令"自动变成游戏里的按键操作。
> 适配所有电脑游戏：FPS / MOBA / 模拟器 / Steam / 任何 exe，全程后台静默运行。

---

## 这是什么

- 自动识别前台游戏进程，切换到对应的语音指令库
- 每条语音规则你说了算：触发短语、要按的键、是单击 / 长按 / 连发，自己定
- 多游戏独立配置：A 游戏的快捷键和 B 游戏的快捷键完全隔离
- 游戏内悬浮窗：打游戏时也能看到当前识别游戏 / 波形 / 最近触发的指令
- 关闭即休眠：游戏关闭瞬间语音监听自动暂停，避免桌面误触发
- 全自定热键：开 / 停 / 暂停 / 重载 / 静音麦克风
- **不装游戏插件、不改游戏内存** ——绕开所有反作弊

首次启动自带「FPS / MOBA」示例配置，立刻能试。

---

## 快速开始

**玩家版**：

1. 下载 `GameVoiceKey.exe`
2. 双击运行，托盘出现青绿图标
3. 主窗口 → 语音按键编辑 → 选「示例 - FPS」看到一堆内置规则
4. 打开 CSGO / Valorant 这种游戏 → 悬浮窗自动切到这条 Profile
5. 对着耳麦说「开枪」「跳跃」→ 自动按对应键

**开发者版**：

```powershell
git clone https://github.com/zlwzk/GameVoiceKey.git
cd GameVoiceKey
pip install -r requirements.txt
python launch.py
```

打包成单 exe：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

跑自检：

```powershell
python -m scripts.selftest
```

---

## 项目状态

- 当前版本：**v0.1.0 - Alpha**
- UI：6 个页面全部可用
- 进程识别：✅ 自动扫描、可白 / 黑名单
- 全局快捷键：✅ 4 个热键全可改
- 按键模拟：✅ 单键 / 组合键 / 鼠标 / 滚轮 / 长按 / 连发 / 宏序列
- 离线语音识别：✅ Vosk（首次启动高级页一键下载模型，可选）
- 能量兜底：✅ 无模型时也能能量检测 + 占位触发
- 悬浮窗：✅ 三种尺寸 + 点击穿透 + 拖拽粘边

---

## 关键技术事实

- **用户数据目录**：`%APPDATA%\GameVoiceKey\`
  - `settings.json` 全局设置
  - `profiles\<game_id>.json` 每个游戏一份
  - `models\` Vosk 模型目录
  - `logs\gvk-YYYY-MM-DD.log` 日志
- **进程扫描**：`psutil.process_iter`，默认 1.5s 一次
- **前台窗口检测**：`ctypes` 调 `GetForegroundWindow`
- **按键注入**：`pynput` 在背后调用 `SendInput`，避免触发反作弊
- **全局热键**：`keyboard` 库
- **悬浮窗**：`PySide6` 半透明 QWidget + WS_EX_TRANSPARENT

---

## 路线图

- v0.2.0：Vosk 模型内置（避免手动下载）
- v0.3.0：在线 ASR（OpenAI Whisper / 阿里达摩院）支持
- v0.4.0：语音宏录制器
- v0.5.0：场景组 UI 完整化
- v0.6.0：配置云同步

---

## 许可

MIT
