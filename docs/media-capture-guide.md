# EdgeSentinel 实机素材拍摄与录屏清单

> 本指南记录真实演示素材的采集与发布规范。当前仓库展示原始媒体，以保留实验过程；生产项目应启用人物授权、标识脱敏和最小披露审查。API Key、PAT、Cookie 和私钥在任何场景下均不得入镜或入库。

这份清单用于补齐 GitHub 项目的真实性证据。素材必须来自实际 Jetson Nano、摄像头、Dashboard 和运行日志；不要使用生成图片替代实拍，也不要为了画面效果伪造检测结果。

逐项执行时请使用[全功能素材拍摄清单](media/shot-checklist.md)。它给出了每张照片、截图和视频的编号、稳定文件名、触发动作、风险等级与验收标准。

当前已经入库一张实机系统总览：[`media/hardware/rig-overview.jpg`](media/hardware/rig-overview.jpg)。照片包含 Jetson Nano、USB 摄像头、USB Wi‑Fi 适配器与 HDMI 显示器；PC 和键鼠未入镜，PC 实际通过局域网 Wi‑Fi 使用 SSH/HTTPS 连接开发板。

## 1. 交付目标

最终 README 建议包含：

1. 一张能同时看见 Jetson、摄像头和实验场景的封面实拍（现有总览已满足，不要求逐个拍硬件模块）；
2. 三张 Dashboard 核心截图；
3. 一组“物品出现 → 移除/遗留 → 事件证据”的闭环截图；
4. 一段 90–150 秒的一镜到底实机演示；
5. 一段在线/离线切换和一段安全确认演示。

## 2. 优先级清单

### P0：发布首页前必须有

| 编号 | 素材 | 拍摄内容 | 建议文件名 |
| --- | --- | --- | --- |
| P0-1 | 实验装置总览照 | **已入库**；包含 Jetson Nano、USB 摄像头、USB Wi‑Fi 与 HDMI 显示器 | `hardware/rig-overview.jpg` |
| P0-2 | PC 与 Jetson 同框照 | PC Dashboard 登录页与 Jetson、HDMI 显示器同框，证明远程访问与边缘运行关系；登录后功能由高清系统截图展示 | `hardware/pc-jetson-workstation.jpg` |
| P0-3 | Dashboard 总览 | 实时画面、检测结果、设备状态、事件列表同屏 | `dashboard/overview.png` |
| P0-4 | Agent Workbench | 用户问题、工具选择、风险等级、执行步骤和脱敏 Trace | `dashboard/agent-workbench.png` |
| P0-5 | 事件证据闭环 | 事件详情、before/after 证据和 SHA-256 校验结果 | `events/evidence-chain.png` |
| P0-6 | 一镜到底演示 | 从实机装置移动到 Dashboard，完成一次真实事件与 Agent 查询 | GitHub Release 视频附件 |

### P1：显著增强技术可信度

| 编号 | 素材 | 拍摄内容 | 建议文件名 |
| --- | --- | --- | --- |
| P1-1 | MCP 工具目录 | 工具名称、Schema、只读/外部标签和风险级别 | `dashboard/mcp-catalog.png` |
| P1-2 | 在线/离线切换 | DeepSeek 在线模式、离线规则模式及当前服务路径 | `dashboard/model-switch.png` |
| P1-3 | L1/L2 确认门 | 快照或重启任务暂停、确认、完成的全过程 | `dashboard/confirmation-gate.png` |
| P1-4 | systemd 健康状态 | 服务 active、API ok、Vision fresh、TLS enabled | `operations/systemd-health.png` |
| P1-5 | GitHub CI | 最新主分支 CI 全绿及 Commit SHA | `operations/github-ci.png` |
| P1-6 | 灾备演练 | 加密异机备份与隔离恢复演练 PASS | `operations/recovery-drill.png` |

### P2：用于项目答辩或长视频

- 摄像头断开、离线事件、自动恢复和恢复事件；
- Jetson 重启后 systemd、HTTPS、认证和视觉流自动恢复；
- 事件趋势、前后时段对比和变化贡献分析；
- 工具预算、Token 使用、模型熔断和离线降级；
- TLS 证书轮换和证书固定验收；
- 数据清理预览、确认执行与审计历史。

## 3. 一镜到底视频脚本（90–150 秒）

推荐横屏 1080p、30 FPS，全程连续录制：

1. **0–10 秒：装置证明**
   镜头扫过 Jetson Nano、摄像头、供电和实验区域；在旁边放一张纸写上 `EdgeSentinel VisionOps` 和拍摄日期。
2. **10–25 秒：服务状态**
   展示 `systemctl status` 或运行验收摘要，重点看 active、API ok、Vision fresh、TLS enabled。
3. **25–45 秒：实时视觉**
   打开 Dashboard，展示实时画面与检测框；人物或瓶子进入画面。
4. **45–75 秒：制造真实事件**
   放入瓶子，等待稳定识别；再移走或留下瓶子，等待事件产生。
5. **75–105 秒：Agent 查询**
   输入“最近移走了哪些瓶子？”或“核对瓶子库存”，展示工具选择与回答。
6. **105–130 秒：证据链**
   打开事件详情，展示 before/after 图片、事件 ID 和证据完整性状态。
7. **130–150 秒：安全边界**
   发起“重启摄像头推理”，展示 L2 任务停在确认门，不必真的执行。

视频中需要同时出现真实装置和网页时，可用手机拍摄显示器，或后期采用“实机主画面 + 屏幕录制画中画”。剪辑只能压缩等待时间，不应改变事件先后关系。

## 4. 分项短视频脚本

### 在线/离线模式切换（30–60 秒）

1. 在线模式询问一个通用问题；
2. 切换离线模式；
3. 用同义表达询问“摄像头里面现在几个人”；
4. 展示离线模型仍调用 `vision.get_people_count`；
5. 切回在线模式。

### 确认门与权限（45–60 秒）

1. viewer 执行 L0 查询；
2. 发起 L1 快照，任务进入 `AWAITING_CONFIRMATION`；
3. 输入错误确认短语，展示拒绝；
4. 取消或正确确认；
5. 发起 L2 重启，仅展示管理员确认要求。

### 摄像头恢复（45–90 秒）

1. 展示正常实时画面；
2. 拔下摄像头；
3. 展示 `CAMERA_OFFLINE` 与 supervisor 状态；
4. 插回摄像头；
5. 展示 `CAMERA_RECOVERED`、generation 增加和画面恢复。

## 5. 截图要求

- 浏览器缩放建议 90%–100%，保留完整标题与状态栏；
- 统一使用深色或浅色主题，不要在同一组三联图中混用；
- 截图必须能读清任务状态、工具名、风险等级和关键结果；
- 避免只截一小块成功提示，应保留足够界面上下文；
- 事件截图优先选择具有真实 before/after 证据的记录；
- 终端截图只保留必要输出，隐藏命令历史中的密码输入与个人路径。

## 6. 隐私与安全检查

发布前逐项检查：

- [ ] 没有 DeepSeek API Key、PAT、Cookie、CSRF Token 或备份口令；
- [ ] 没有 `/etc/edgesentinel-visionops/*.env` 文件内容；
- [ ] 没有 TLS 私钥、SSH 私钥或二维码；
- [ ] 没有清晰可读的设备序列号、家庭地址或无线网络密码；
- [ ] 没有无关人员面部，必要时先征得同意或打码；
- [ ] Dashboard 中的用户名、局域网 IP 是否需要打码已明确决定；
- [ ] 事件证据使用专门搭建的实验场景，不包含真实敏感监控内容；
- [ ] 视频没有录到密码输入、通知弹窗或个人聊天内容。

## 7. 文件规格

### 图片

- 实拍：JPEG，长边 1600–2400 px，单张建议小于 2 MB；
- Dashboard：PNG 或 WebP，建议 1600×900；
- 不要反复保存 JPEG，避免文字区域产生压缩噪声；
- README 首屏封面建议使用 16:9 横图。

### 视频

- MP4 / H.264 / AAC，1080p，30 FPS；
- 一镜到底演示建议控制在 150 秒内；
- 不建议把大视频直接提交进 Git 历史；优先上传到 GitHub Release，再用封面图链接；
- 如需 README 内直接预览，可额外制作小于 10 MB 的短 GIF/WebP，但它不能替代原始 MP4。

## 8. 目录与命名

原始照片、截图和视频统一保存在 Git 仓库外：

```text
<PRIVATE_MEDIA_ROOT>\edgesentinel\
├─ 01_raw_photos\YYYY-MM-DD\
├─ 02_raw_screens\YYYY-MM-DD\
├─ 03_raw_videos\YYYY-MM-DD\
├─ 05_editing_projects\
└─ 06_final_exports\
```

只有完成筛选和脱敏的公开素材进入以下目录：

```text
docs/media/
├─ shot-checklist.md
├─ hardware/
│  ├─ rig-overview.jpg
│  └─ module-closeup.jpg
├─ dashboard/
│  ├─ overview.png
│  ├─ agent-workbench.png
│  ├─ mcp-catalog.png
│  └─ confirmation-gate.png
├─ events/
│  └─ evidence-chain.png
├─ agent/
├─ mcp/
├─ security/
├─ operations/
├─ recovery/
├─ release/
└─ video-thumbnails/
```

文件名使用小写英文和连字符，不写日期、用户名、IP 或随机事件 ID。原始素材可以在仓库外按日期归档，仓库只提交经过筛选和脱敏的版本。

## 9. 完成后的 README 编排

素材齐全后按以下顺序插入首页：

1. 标题与徽章；
2. 16:9 实机封面图；
3. 一句话定位；
4. Dashboard 三联图；
5. 一镜到底视频封面链接；
6. 架构图与技术能力；
7. 安全、测试与发布证据。
