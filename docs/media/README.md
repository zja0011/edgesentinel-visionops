# Media assets

这里存放 EdgeSentinel 真实实验照片、Dashboard 原始截图与视频封面。

公开媒体用于展示真实实验过程：图片保留原始画面，8 段视频保留原始分辨率、编码和音轨。原始 MP4 由 GitHub Release 承载，[`../video-gallery.html`](../video-gallery.html) 提供在线播放，避免大体积二进制进入 Git 历史。

`dashboard/overview.png` 展示完整 Dashboard 长页面；`covers/` 中的封面来自对应视频关键帧，只用于 README 和播放器加载前预览。

> 演示素材公开不等同于生产隐私规范。产品化部署应执行人物授权、账户与设备标识脱敏、最小披露和安全复核。

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
