# Media assets

这里存放已经筛选、脱敏并适合公开展示的 EdgeSentinel 实机照片和界面截图。

提交素材前请阅读 [`../media-capture-guide.md`](../media-capture-guide.md) 和[全功能素材拍摄清单](shot-checklist.md)。原片应保存在仓库外的 `H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel`。大体积原始视频不要直接写入 Git 历史；建议作为 GitHub Release 附件发布，并在项目首页用封面图链接。

当前公开图片均由真实原片确定性派生，只执行裁剪、像素化遮挡、缩放和压缩。可在 Windows 项目目录运行：

```powershell
python scripts/build_public_media.py `
  --source-root "H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel"
```

构建脚本不会修改原片，也不会调用生成式图像模型。公开前仍需人工检查人脸、LAN IP、账户标记、Task/Session ID、SSH 用户/主机名和本地路径是否已经去除。

发布视频由同样的确定性流程生成，最终 MP4 保存在仓库外：

```powershell
$env:PYTHONPATH="H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\98_tools\imageio_ffmpeg"
$ffmpeg = python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
python scripts/build_public_videos.py `
  --ffmpeg $ffmpeg `
  --source-root "H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\03_raw_videos" `
  --output-root "H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\06_final_exports\videos\v0.1.0-dev.1"
```

脚本统一输出 H.264 720p、移除音轨和元数据、生成 SHA‑256 Manifest，并将轻量封面写入 `docs/media/covers/`。公开视频只上传到 GitHub Release。

当前公开媒体结构：

```text
docs/media/
├── hardware/              # 实机系统与完整工作台
├── dashboard/             # Dashboard、Agent Workbench 与 MCP 截图
└── release/               # 测试与发布门禁证据
```

硬件图片包含 Jetson Nano、USB 摄像头、USB Wi‑Fi 适配器、HDMI 显示器与 PC 工作台。PC 通过局域网 Wi‑Fi 使用 SSH/HTTPS 连接开发板；无需为每个普通外设单独拍摄近景。

禁止提交 API Key、PAT、Cookie、TLS/SSH 私钥、备份口令、清晰设备序列号或未经授权的人员画面。
