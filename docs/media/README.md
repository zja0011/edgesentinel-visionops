# Media assets

这里存放 EdgeSentinel 真实实验照片、Dashboard 原始截图与视频封面。

当前 Demo 采用“保持原貌”策略：公开图片直接复制原片，不执行裁剪、像素化、缩放或压缩；8 段视频也不做转码、静音或遮挡。原始 MP4 不写入 Git 历史，而是作为 GitHub Release 附件发布，并由 [`../video-gallery.html`](../video-gallery.html) 提供在线播放。

`dashboard/overview.png` 必须与拍摄目录中的 `界面全局截图.png` 字节一致。封面只从对应原始视频抽取单帧，用于 README 和播放器加载前预览，不替代原始视频。

> 当前选择适合公开 Demo，不代表生产隐私规范。产品化时应重新执行人物授权、账户与设备标识脱敏、最小披露和安全复核。

当前公开媒体结构：

```text
docs/media/
├── hardware/              # 实机系统与完整工作台
├── dashboard/             # Dashboard、Agent Workbench 与 MCP 截图
├── covers/                # 从原始视频抽取的完整画面封面
└── release/               # 测试与发布门禁证据
```

硬件图片包含 Jetson Nano、USB 摄像头、USB Wi‑Fi 适配器、HDMI 显示器与 PC 工作台。PC 通过局域网 Wi‑Fi 使用 SSH/HTTPS 连接开发板；无需为每个普通外设单独拍摄近景。

即使采用原貌展示，也绝不提交 API Key、PAT、Cookie、TLS/SSH 私钥或备份口令。素材清单与历史拍摄说明见 [`../media-capture-guide.md`](../media-capture-guide.md) 和[全功能素材拍摄清单](shot-checklist.md)。
