# 🎬 Keyboard shortcuts

- **创作者**：`Dave Ebbelaar` | **发布日期**：`2026-08-30` | **原视频链接**：[YouTube 视频](https://www.youtube.com/watch?v=u6xlVRMfnyM)

---

### 📌 一句话核心主旨 (TL;DR)
本视频系统性地介绍了在现代代码编辑器（如 VS Code / Cursor）中大幅提升日常开发效率的黄金键盘快捷键，旨在帮助开发者摆脱对鼠标的依赖，实现“双手不离键盘”的高效流式编程（Flow State）。

### 🔍 核心要点精炼拆解 (Key Takeaways)

*   **文件与界面导航（极速定位）**
    *   `Ctrl + P` (Windows/Linux) / `Cmd + P` (Mac)：快速全局搜索并打开项目文件，彻底替代在侧边栏手动逐级展开文件夹的操作。
    *   `Ctrl + B` / `Cmd + B`：快速显示/隐藏侧边栏，最大化代码编辑区域的视觉空间。
    *   `Ctrl + ` ` / `Cmd + ` `：无缝切换和呼出/隐藏集成终端，无需频繁点击底部面板。

*   **文本与代码高效编辑（批量重构）**
    *   `Ctrl + D` / `Cmd + D`：选中当前词后，连续按此键可依次多选下一个相同的词，实现高效的局部“多光标同时编辑”。
    *   `Alt + Up/Down` / `Option + Up/Down`：直接将当前行（或选中多行）代码向上或向下移动，省去“剪切+粘贴”的繁琐步骤。
    *   `Shift + Alt + Up/Down` / `Shift + Option + Up/Down`：快速向上或向下复制整行代码。

*   **全局命令与高级搜索**
    *   `Ctrl + Shift + P` / `Cmd + Shift + P`：打开“命令面板”（Command Palette），这是编辑器的核心枢纽，可以通过输入拼写直接执行任何设置、插件命令或编辑器功能。
    *   `Ctrl + F` 和 `Ctrl + Shift + F`：分别用于当前文件搜索和全局跨文件搜索。

*   **AI 辅助编程快捷键（针对 Cursor/Copilot 用户）**
    *   `Ctrl + K` / `Cmd + K`：在当前代码行直接唤醒 AI 编写或修改代码（Inline Edit）。
    *   `Ctrl + L` / `Cmd + L`：将选中代码发送到侧边栏 AI 聊天窗口，进行解释、优化或答疑。

### 💡 实操建议与落地启示 (Actionable Insights)

1.  **实行“断鼠训练法”**：在接下来的 1-2 天编码中，强迫自己将鼠标移开，凡是遇到导航、跳转、复制、删除操作，优先查阅并使用快捷键完成。
2.  **自定义高频快捷键**：针对频繁执行的操作（例如“运行当前 Python 文件”、“格式化代码”），通过命令面板搜索 `Preferences: Open Keyboard Shortcuts`，绑定最顺手的组合键。
3.  **渐进式记忆法**：不要试图一次性背诵所有快捷键。每次只挑选 3 个（如：多光标编辑、行移动、文件跳转）作为当天的重点练习，形成肌肉记忆后再解锁下一组。

### ⚠️ 局限性与注意事项 (Caveats & Limitations)
*   **跨平台按键差异**：Windows/Linux 的 `Ctrl` 和 `Alt` 键在 macOS 上对应 `Cmd` 和 `Option`，在多设备切换时需要注意肌肉记忆的微调。
*   **快捷键冲突**：当安装了 Vim 插件、Jupyter 插件或特定的系统全局快捷键（如输入法、录屏软件）时，可能会产生按键冲突，需要进入 Keybindings 设置中进行手动解冲突（Resolve Conflicts）。