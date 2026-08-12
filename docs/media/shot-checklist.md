# EdgeSentinel 全功能素材拍摄清单

本清单用于制作 GitHub README、作品集、答辩演示和发布视频所需的真实性素材。目标不仅是证明“能运行”，还要证明硬件、视觉流水线、Agent Harness、MCP、安全治理、运维恢复和发布工程均真实可用。

执行约定：每次开始一个拍摄项前，都应先给出与 H10 相同粒度的“详细拍摄卡”，至少包括目标、准备、构图、操作步骤、文件名、禁拍内容和验收标准。表格只是总目录，不能代替逐项指导。

## 1. 原片与公开素材分开存放

原片不要直接放入 Git 仓库。请在 Windows 建立：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\
├─ 00_inbox\
├─ 01_raw_photos\YYYY-MM-DD\
├─ 02_raw_screens\YYYY-MM-DD\
├─ 03_raw_videos\YYYY-MM-DD\
├─ 04_audio\YYYY-MM-DD\
├─ 05_editing_projects\
├─ 06_final_exports\images\
├─ 06_final_exports\videos\
└─ 99_rejected_private\
```

经过筛选、裁剪和脱敏的公开图片再复制到：

```text
edgesentinel-visionops\docs\media\
├─ hardware\
├─ dashboard\
├─ vision\
├─ events\
├─ agent\
├─ mcp\
├─ security\
├─ operations\
├─ recovery\
├─ release\
└─ video-thumbnails\
```

最终 MP4 保存在 `06_final_exports\videos\`，以后上传 GitHub Release。仓库只放封面图、短 GIF/WebP 和视频链接，避免 Git 历史无限增大。

## 2. 命名和质量标准

原始文件：

```text
YYYYMMDD_HHMMSS_<素材编号>_<内容>_takeNN.<扩展名>
```

例如：

```text
20260811_143015_H02_jetson-closeup_take01.jpg
20260811_150233_D10_agent-workbench_take01.png
20260811_161120_V01_end-to-end_take02.mp4
```

公开图片使用下表中的稳定文件名，不含用户名、IP、日期、Event ID 或 Task ID。视频命名为：

```text
edgesentinel-demo-<序号>-<主题>-zh-cn-1080p.mp4
```

- 照片：保留原始最高质量；发布 JPG 长边 2400 px、质量 85–90。
- 截图：PNG，建议 1920×1080，最低 1600×900。
- 视频：1920×1080、30 FPS、H.264、AAC 48 kHz。
- 浏览器使用统一主题、90% 或 100% 缩放；终端宽度至少 140 列。
- 每个镜头至少拍 `take01`、`take02` 两次。

## 3. 风险标记

| 标记 | 含义 | 规则 |
|---|---|---|
| P | 普通拍摄 | 不改变系统状态 |
| L0 | 只读查询 | 可以直接执行 |
| L1 | 有限写操作 | 必须经界面确认；优先拍等待确认和取消 |
| L2 | 高影响操作 | 只在维护窗口执行并明确确认 |
| PHY | 物理操作 | 涉及人员走动、物品移动、摄像头拔插 |
| SEC | 安全敏感 | 重点检查密码、Token、Cookie、私钥、路径和身份信息 |

## 4. 拍摄前布置

1. 固定 USB 摄像头，画面准备一名测试人员、两个瓶子、一个盒子和一件可遗留小物品。
2. 设置 `左侧区域`、`右侧区域`，不要使用真实地点名称。
3. 关闭桌面通知、聊天窗口、书签栏和无关标签页。
4. 登录页只拍空密码框；输入密码时暂停录屏或剪掉该段。
5. 实物照片旁可放“EdgeSentinel + 拍摄日期”纸卡，加强真实性。
6. 终端截图只保留命令和 acceptance summary，不拍 `sudo` 密码输入过程。
7. 拍摄摄像头离线、重启、清理等场景前，先确认当前不是正在使用的生产环境。

## 5. 硬件实物照片

硬件不是项目展示重点，保留两张照片即可：现有 H01 证明完整实机，新增 H10 用一个画面证明“PC 远程 Dashboard 访问入口 + Jetson 边缘运行”的真实关系。不需要逐个拍摄其他硬件模块。

| 编号 | 公开文件名 | 必须拍到 | 验收标准 |
|---|---|---|---|
| H01 | `hardware/rig-overview.jpg` | Jetson、风扇、摄像头、Wi‑Fi、显示器 | **必需，已有**；README 首图 |
| H10 | `hardware/pc-jetson-workstation.jpg` | PC Dashboard 登录页、Jetson 和本地 HDMI 显示器同框 | **必拍，原片已完成**；一张图解释 PC 远程访问 + Jetson 边缘运行 |

不再要求 Jetson、摄像头、网卡、键鼠、电源和存储介质的独立近照。录制 V01 或 V20 时，可顺手拍一段 5–10 秒横向硬件 B-roll，无需单独组织硬件拍摄批次。

### H10 详细拍摄卡：PC Dashboard 与 Jetson 同框

**目标**

让第一次看到项目的人无需阅读说明，就能理解：视觉服务运行在 Jetson Nano 上，PC 通过局域网进入 Dashboard。登录页适合这张实物关系图；登录后的功能由后续高清系统截图展示，不必在 H10 重复。

**拍摄前准备**

1. Jetson Nano、USB 摄像头、USB Wi‑Fi 和 HDMI 显示器正常连接并运行。
2. PC 浏览器打开 Dashboard 登录页，用户名和密码框保持空白，不执行登录。
3. 登录后的实时画面、运行状态和检测结果留给 D02–D11 的系统截图展示。
4. 浏览器只保留 Dashboard 标签页，关闭书签栏、通知、邮箱和聊天软件。
5. 如果地址栏显示真实 LAN IP，可以保留原片，公开版由 Codex 统一模糊；不要在照片中出现密码或 API Key。
6. 擦拭 PC 屏幕和摄像头镜头，整理桌面线缆，但不要为了整齐改变真实连接关系。

**机位和构图**

1. 使用手机或相机横向拍摄，优先使用主摄 1×，不要使用超广角。
2. 站在工作台正前方稍偏左或偏右约 30°，镜头高度与 PC 屏幕中心大致一致。
3. PC 屏幕占画面约 45%–55%，保证 EdgeSentinel 登录卡片能够辨认。
4. Jetson Nano和 HDMI 显示器放在 PC 屏幕旁边或下方，占画面约 30%–40%；USB 摄像头已经由 H01 证明，在 H10 中可以不入镜。
5. PC 屏幕与 Jetson 之间不要被手臂、线缆卷或其他物品遮挡。
6. 画面边缘留出约 5% 空间，方便后续裁剪成 16:9 或 3:2。

**实际拍摄步骤**

1. 先确认服务正常，再让浏览器停在空白凭据的 Dashboard 登录页。
2. 降低 PC 屏幕亮度到环境光可兼顾的程度，避免屏幕一片白；手机点击屏幕区域测光。
3. 拍一张全景 `take01`，完整包含 PC 屏幕、Jetson、摄像头和 HDMI 显示器。
4. 向前移动半步拍 `take02`，优先保证 Dashboard 文字可读，同时不裁掉 Jetson。
5. 改变左右角度拍 `take03`，选择屏幕反光最小的一张。
6. 放大检查照片：Dashboard 不能糊、Jetson 不能被裁掉、屏幕不能出现摩尔纹或严重反光。

**原片文件名**

```text
YYYYMMDD_HHMMSS_H10_pc-jetson-workstation_take01.jpg
YYYYMMDD_HHMMSS_H10_pc-jetson-workstation_take02.jpg
YYYYMMDD_HHMMSS_H10_pc-jetson-workstation_take03.jpg
```

原片保存到：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\01_raw_photos\YYYY-MM-DD\
```

**不要这样拍**

- 不要竖屏拍摄。
- 不要只拍 PC 屏幕而看不到 Jetson。
- 不要只拍硬件而无法辨认 Dashboard。
- 不要用手机拍得距离过远，导致页面文字完全不可读。
- 不要显示密码框内容、Token、恢复口令、私人通知或浏览器账户头像菜单。
- 不要让屏幕反光暴露拍摄者面部或房间私人信息。

**验收标准**

- [x] 一张照片中同时看到 PC Dashboard 登录页、Jetson Nano 和本地 HDMI 显示器。
- [x] EdgeSentinel 登录卡片能够辨认，用户名和密码框没有内容。
- [ ] 能从物理位置关系理解 PC 是远程操作端、Jetson 是边缘运行端。
- [ ] 没有密码、Token、Cookie、私人消息或清晰设备序列号。
- [ ] 横向构图清晰，公开版可裁成 16:9。

## 6. Dashboard 核心截图

最终文件放 `docs/media/dashboard/`。

| 编号 | 公开文件名 | 操作/问题 | 必须显示 | 标记 |
|---|---|---|---|---|
| D01 | `dashboard/01-login.png` | 打开 `/dashboard` | HTTPS 登录页、空密码框 | SEC |
| D02 | `dashboard/02-overview-live.png` | 登录后的整页长截图 | **原片已完成**；实时画面、指标、运行状态、事件中心和 Copilot 全貌 | L0 |
| D03 | `dashboard/03-live-person-detection.png` | 一人进入 Left Zone | **原片已完成，公开前默认打码人脸**；person 82.1%、Left=1、当前人员=1、LIVE | PHY/L0 |
| D04 | `dashboard/04-live-object-detection.png` | 放两个瓶子和一个盒子 | 类别、检测框、对象计数 | PHY/L0 |
| D05 | `dashboard/05-device-health.png` | 打开设备状态 | 负载、温度、内存、磁盘、摄像头 | L0 |
| D06 | `dashboard/06-event-center.png` | 事件中心局部截图 | **原片已完成**；七项筛选、107 条汇总、趋势、6 条事件和分页 | L0 |
| D07 | `dashboard/07-event-evidence.png` | 打开带证据事件 | 详情、证据图、校验状态 | L0/SEC |
| D08 | `dashboard/08-zone-editor.png` | 打开区域配置 | 多边形、保存状态、只读/可写提示 | L0/L1 |
| D09 | `dashboard/09-agent-chat-tool-call.png` | 问“摄像头里面现在站着几位？” | 自然语言、工具名、结果、step | L0 |
| D10 | `dashboard/10-agent-workbench.png` | 展开 Workbench | MODEL_DECISION → TOOL_RESULT → TASK_RESULT | L0 |
| D11 | `dashboard/11-mcp-catalog.png` | 展开 MCP 目录 | 工具数、风险、Schema、external 标记 | L0 |
| D12 | `dashboard/12-model-switch.png` | 打开模型切换 | remote/offline 和当前选择 | L0 |
| D13 | `dashboard/13-weather-tool.png` | 问“武汉今天天气怎样？” | DeepSeek、weather.get_current、外部请求 | L0 |
| D14 | `dashboard/14-confirmation-l1.png` | “生成今日报告”或“拍摄快照” | AWAITING_CONFIRMATION、L1、确认/取消 | L1 |
| D15 | `dashboard/15-confirmation-l2.png` | “重启摄像头推理” | L2、确认短语、影响说明 | L2 |
| D16 | `dashboard/16-session-memory.png` | 说暗号后追问 | Session ID、记忆、清除入口 | L0/L1 |
| D17 | `dashboard/17-long-term-memory.png` | 记住无敏感偏好 | memory.remember、L1、provenance | L1 |
| D18 | `dashboard/18-job-stream.png` | 提交异步人员查询 | QUEUED/RUNNING/COMPLETED 或 SSE | L0 |
| D19 | `dashboard/19-execution-budget.png` | 展开预算 | 模型/工具/外部工具次数、deadline | L0 |
| D20 | `dashboard/20-token-governance.png` | 展开 Token 使用 | prompt/completion/总预算/成本状态 | L0 |
| D21 | `dashboard/21-tool-routing.png` | 问候后再问人员数量 | NO_MATCH 与 DETERMINISTIC 对比 | L0 |
| D22 | `dashboard/22-model-resilience.png` | 展开韧性状态 | retries、fallbacks、circuit、served mode | L0 |
| D23 | `dashboard/23-skill-selected.png` | “调查最近移走的物品” | Skill 名、版本、哈希、多步工具 | L0 |
| D24 | `dashboard/24-hook-timeline.png` | 展开 Hook 时间线 | 生命周期点、fail-closed | L0 |
| D25 | `dashboard/25-evaluation.png` | 打开 Evaluation | 数据集版本、cases、准确率、默认拒绝 | L0 |
| D26 | `dashboard/26-storage-retention.png` | 查询占用并预览清理 | 候选文件、Delete performed=False | L0 |
| D27 | `dashboard/27-disaster-recovery.png` | 查询灾备/创建备份 | 状态、凭据排除、L1 创建确认 | L0/L1 |
| D28 | `dashboard/28-daily-report.png` | 生成并确认今日报告 | 报告结果/下载入口 | L1 |
| D29 | `dashboard/29-event-acknowledgement.png` | 确认测试事件 | 确认前后状态与审计 | L1 |
| D30 | `dashboard/30-camera-restart.png` | 维护窗口确认重启 | L2、重启结果、恢复帧 | L2 |

### D02 详细截图卡：Dashboard 运行总览

**目标**

用一张高清整页长截图证明 Dashboard 已通过 HTTPS 登录、API 在线、摄像头画面持续更新，并完整展示指标、Edge Runtime、事件中心和 Vision Copilot 的页面结构。后续仍会用独立截图展示事件、Agent 和 MCP 细节；D02 主要作为整体预览及局部裁图来源。

**截图前准备**

1. 在 PC 上使用 Chrome 或 Edge 打开 `https://192.168.1.101:8443/dashboard`，正常登录。
2. 关闭其他标签页、下载栏、开发者工具、书签栏和系统通知；不要使用无痕窗口提示条。
3. 浏览器窗口最大化，Windows 显示缩放建议 100%，浏览器缩放先设为 80%。如果文字明显过小，再改为 90%。
4. 保持 Agent Workbench、MCP 工具目录和事件详情关闭。
5. 不进入区域绘制状态，草稿点数保持 0，密码和管理员口令字段必须为空。
6. 摄像头画面保持简单，不安排人脸入镜；等待 5–10 秒，让状态稳定。

**页面应处于以下状态**

- 右上角显示 `API 在线`。
- “摄像头最新标注画面”显示真实画面而不是 `NO LIVE FRAME`。
- 画面状态显示 `画面持续更新` 和 `LIVE`，不能显示 `STALE`。
- 四张指标卡均有实际值：当前人员、当前物品、历史事件、视觉状态。
- “视觉状态”显示 `实时`，状态年龄尽量小于 2 秒。
- 页面没有黄色/红色错误通知条。
- 整页长截图应继续包含库存、Edge Runtime、事件中心和 Vision Copilot。

**具体操作步骤**

1. 登录后点击右上角“立即刷新”。
2. 等待按钮恢复可用，再确认右上角为 `API 在线`。
3. 检查实时画面中的区域线和目标框没有遮住关键对象；若瓶子没有稳定识别，保持不动再等 5 秒。
4. 浏览器缩放设为 90%，确保实时画面与页面文字保持可读。
5. 将页面滚动到最顶部。
6. Edge 使用 `Ctrl+Shift+S` 后选择“捕获整页”；Chrome 使用开发者命令 `Capture full size screenshot`。
7. 等待整页合成完成并保存 PNG，不要用手机拍屏。
8. 后续由 Codex 从长截图派生 README 横版图和各功能局部图，原片不覆盖。

**原始文件名**

```text
20260812_D02_dashboard-overview_full-page_take01.png
```

保存到：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\02_raw_screens\2026-08-12\
```

**不要这样截**

- 不要使用手机拍显示器，D02 必须是 PC 系统截图。
- 不要截图登录页；登录页已经由 H10 证明。
- 不要让地址栏显示用户名、查询参数、Token 或浏览器密码提示。
- 不要把页面缩小到文字不可读；整页截图工具会自动捕获事件中心和 Agent。
- 不要在画面中出现私人面孔、聊天通知、文件路径或其他浏览器标签页。
- 不要在 `NO LIVE FRAME`、`STALE`、`API 连接失败` 或刷新中的状态截图。

**验收标准**

- [ ] EdgeSentinel 标题、`API 在线` 和“摄像头最新标注画面”同时可见。
- [ ] 实时画面清晰，状态为 `LIVE`/`画面持续更新`。
- [ ] 当前人员、当前物品、历史事件、视觉状态四张卡片完整可读。
- [ ] 视觉状态为“实时”，页面无错误通知。
- [x] 库存、Edge Runtime、事件中心和 Vision Copilot 均完整出现。
- [ ] 没有密码、Token、Cookie、私人通知、绝对路径或未授权人脸。
- [x] 原片为 1205×6530 PNG，页面连续且没有拼接断层。

### D03 详细截图卡：实时人员检测

**目标**

用一张局部高清截图证明真实人员进入摄像头画面后，系统能够画出人员检测框、更新区域人数和“当前人员”指标，并保持视觉状态实时。D03 不使用长截图，重点是让检测结果足够大、足够清楚。

**场景准备**

1. 摄像头保持与 D02 相同位置，不修改区域配置。
2. 由一名测试人员进入摄像头画面，优先站在 `Left Zone` 中央。
3. 为保护隐私，建议背对摄像头、侧身、戴口罩，或让头部处于画面上边缘之外；不要公开未经授权的清晰人脸。
4. 尽量让身体从肩部到脚部完整入镜。区域判断使用脚底中心，脚部不要被桌子或画面底边遮住。
5. 测试人员与背景形成明显明暗对比，避免逆光、纯黑衣服贴近暗背景或多人同时入镜。

**页面应达到的状态**

- 右上角为 `API 在线`。
- 实时画面显示 `画面持续更新` 和 `LIVE`。
- 人员周围出现检测框或可辨认的人员标注。
- `Left Zone` 计数为 1，`Right Zone` 为 0；若实际站在右区则反过来，但只能有一个区域为 1。
- “当前人员”卡片显示 1，详细信息显示 `可见 1`。
- “视觉状态”显示“实时”，状态年龄尽量小于 2 秒。

**具体操作步骤**

1. 登录 Dashboard 并回到页面顶部，浏览器缩放设为 90% 或 100%。
2. 点击“立即刷新”。
3. 测试人员从画面外走入 `Left Zone`，在区域中央静止站立 5–10 秒。
4. 观察人员检测框、区域计数和“当前人员”卡片；三处都稳定为 1 后再截图。
5. 按 `Win+Shift+S` 选择矩形截图，范围从 EdgeSentinel 页头开始，到四张指标卡底部结束。
6. 截图必须包含完整实时画面、区域计数和四张指标卡；不需要包含库存、Edge Runtime、事件中心或 Agent。
7. 拍两张候选：一张人员站在左区正中，一张人员稍微侧身但仍在左区，选择检测框最稳定的一张。

**原始文件名**

```text
20260812_D03_live-person-detection_left-zone_take01.png
20260812_D03_live-person-detection_left-zone_take02.png
```

保存到：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\02_raw_screens\2026-08-12\
```

**如果识别不到人员**

1. 先确认摄像头能看到测试人员全身，特别是脚部。
2. 增加正面照明，避免人物成为黑色剪影。
3. 离摄像头稍远，使人物占画面高度约 40%–75%。
4. 保持静止 5 秒，不要快速挥手或频繁走动。
5. 仍无法识别时，不要伪造结果，先保留现场照片并告诉 Codex排查。

**不要这样截**

- 不要截取没有检测框、当前人员仍为 0 的瞬间。
- 不要只截摄像头画面而漏掉四张指标卡。
- 不要让两个人或镜面反射进入画面。
- 不要公开清晰人脸、工牌、姓名牌、文件或私人环境。
- 不要在 `STALE`、刷新中或区域计数互相矛盾时截图。

**验收标准**

- [ ] 真实人员和检测框清楚可见。
- [ ] 左/右区域中恰好一个区域计数为 1。
- [ ] 当前人员为 1，详细信息为“可见 1”。
- [ ] 视觉状态为“实时”，画面为 `LIVE`。
- [ ] 页头、完整实时画面和四张指标卡同时入图。
- [x] 未发现凭据信息；原片含部分可辨认人脸，公开版必须先打码。

### D06 详细截图卡：事件中心总览

**目标**

用一张清晰截图证明事件中心具备多条件过滤、事件汇总、时间趋势、严重度/处置状态标记、事件列表和有界分页能力。D06 只展示列表总览，不打开单条事件详情；证据图片和 SHA-256 校验由 D07/E12/E13 展示。

**截图前准备**

1. 使用 D02 同一浏览器会话，保持 Dashboard 已登录。
2. 先退出实时人员拍摄场景，避免个人画面继续出现在页面顶部；D06 截图本身不包含摄像头画面。
3. 右上角确认仍为 `API 在线`，页面没有错误通知。
4. 收起 MCP Catalog、Agent Workbench 和事件详情。
5. 不点击“确认处理”，不改变任何事件处置状态。

**推荐筛选条件**

第一张使用默认总览，信息最丰富：

```text
事件类型：全部类型
处置状态：待处理
严重级别：全部级别
目标类别：留空
摄像头：留空
显示数量：6条
时间范围：全部历史
```

如果“待处理”结果少于 3 条，则把处置状态改为“全部状态”。不要为了截图伪造事件或批量确认历史事件。

**页面应达到的状态**

- “事件中心”标题与只读结果计数可见。
- 七个筛选字段和“应用筛选/重置”按钮完整可见。
- 汇总条不是“正在汇总”或“不可用”。
- 时间趋势图完整显示。
- 至少显示 3 条真实事件；尽量同时包含 INFO、MEDIUM/HIGH 中的两种严重度。
- 每条事件的类型、摄像头/区域或对象、时间、状态和“详情”按钮能够辨认。
- 底部“加载更早事件”可以出现，但 D06 不点击；分页操作留给 E16。

**具体操作步骤**

1. 在长页面中滚动到 `EVENT TIMELINE / 事件中心` 顶部。
2. 按推荐条件设置筛选器，点击“应用筛选”。
3. 等待结果计数、汇总、趋势和事件列表全部稳定。
4. 浏览器缩放设为 90% 或 100%；选择能让事件中心标题、全部筛选器、趋势和至少 3 条事件同时可见的比例。
5. 按 `Win+Shift+S` 使用矩形截图，从“EVENT TIMELINE”标题上方少量留白开始，截到第 3–6 条事件或分页按钮。
6. 不要把 Vision Copilot 截进来；D06 的视觉中心只有事件面板。
7. 如果单屏无法包含全部内容，使用 Edge“捕获区域”或浏览器局部长截图，只捕获事件中心面板，不要再次截整站全页。

**原始文件名**

```text
20260812_D06_event-center_open-all-severity_take01.png
```

如果改用全部处置状态：

```text
20260812_D06_event-center_all-status_take02.png
```

保存到：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\02_raw_screens\2026-08-12\
```

**隐私与脱敏**

- Event ID 如果未展开通常不会显示；若截图中出现完整 Event ID，公开版统一截断或模糊。
- `camera_01`、`Left Zone`、`Right Zone` 可以公开。
- 不显示证据绝对路径、Task ID、用户名、IP 或事件确认表单。
- 历史事件日期可以保留，它证明 SQLite 中存在真实记录；不要手工修改日期。

**不要这样截**

- 不要在“正在读取事件记录”或“最近事件汇总不可用”时截图。
- 不要打开事件详情抽屉。
- 不要为了出现 HIGH 事件而拔摄像头或制造故障。
- 不要点击“加载更早事件”导致列表过长；该功能由 E16 单独展示。
- 不要把整个 6530 px 全站长图再次作为 D06。

**验收标准**

- [ ] 事件中心标题、结果计数和七个筛选项完整。
- [ ] 汇总条与趋势图已加载。
- [ ] 至少 3 条真实事件清晰可读。
- [ ] 事件类型、严重度、状态、时间和详情按钮可辨认。
- [ ] 没有展开事件详情或执行写操作。
- [ ] 没有绝对路径、凭据、用户/IP 或未授权人员画面。

### D09 详细截图卡：自然语言工具调用

**目标**

证明用户不需要点击固定问题按钮，也不需要完整输入“当前有几个人？”。手动输入一种自然口语表达后，在线 Agent 能理解意图、自动选择 `vision.get_people_count`、读取实时视觉状态并返回答案。D09 只展示问题、回答和工具结果，HARNESS RUN 的详细元数据与 Trace 留给 D10。

**截图前准备**

1. 摄像头画面保持无人，或者安排一人稳定站在左区；截图答案必须与真实现场一致。
2. 右上角确认 `API 在线`，视觉状态为实时。
3. 滚动到 `VISION COPILOT / 询问 EdgeSentinel`。
4. “回答模型”选择 `在线 DeepSeek`，等待状态稳定显示在线/remote；不要在离线模式拍 D09。
5. 不点击“当前有几个人？”预设按钮；必须在文本框里手动输入。
6. 长期记忆列表如包含私人内容，先保持收起/移出截图范围，不要为了截图删除真实记忆。

**本次必须输入的问题**

```text
现在摄像头画面里站着几位？
```

这句话有意不同于预设按钮的“当前有几个人？”，用于证明 Agent 能处理自然语言改写，而不是精确模板匹配。

**具体操作步骤**

1. 在“自然语言问题”文本框中手动输入上述问题。
2. 点击“发送问题”，等待 `AGENT RUNNING/JOB RUNNING` 结束。
3. 只有出现 `TASK COMPLETED` 后再截图。
4. 核对回答中的人数与真实画面一致，并明确说明数据是否实时/陈旧。
5. 核对绿色工具结果标签必须包含：

   ```text
   vision.get_people_count · SUCCEEDED
   ```

6. 核对任务元信息显示正常模型名和 step 数，不能是 `undefined step`。
7. 结果返回后，点击自动展开的 `HARNESS RUN` 标题将其收起；D09 不展示 Task ID、路由、预算或 Trace。
8. 保留输入框中的原始问题，不要清空，因为它是“用户确实输入了自然语言”的证据。
9. 使用 Edge 区域截图或 `Win+Shift+S` 矩形截图，只截 Vision Copilot 模块：从 `VISION COPILOT` 标题开始，到工具成功标签及收起的 `HARNESS RUN` 行结束。
10. 如果回答较长导致一屏放不下，使用“区域长截图”，仍然只捕获 Vision Copilot 模块，不截事件中心或整站。

**截图中必须出现**

- `VISION COPILOT / 询问 EdgeSentinel`。
- 当前回答模型为在线 DeepSeek/remote。
- 文本框中的“现在摄像头画面里站着几位？”。
- `TASK COMPLETED`。
- 正常模型名和明确 step 数。
- 完整中文回答，人数与现场一致。
- `vision.get_people_count · SUCCEEDED`。
- 收起状态的 `HARNESS RUN` 标题可以保留，但不能展开详细信息。

**原始文件名**

无人场景：

```text
20260812_D09_agent-natural-language-people-count_zero_take01.png
```

一人场景：

```text
20260812_D09_agent-natural-language-people-count_one_take01.png
```

保存到：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\02_raw_screens\2026-08-12\
```

**不要这样截**

- 不要点击预设的“当前有几个人？”按钮代替手动输入。
- 不要在 TASK RUNNING、JOB QUEUED、REQUEST FAILED 或工具 FAILED 时截图。
- 不要出现 `undefined step`。
- 不要让回答人数与当前画面/指标矛盾。
- 不要展开 HARNESS RUN；D10 会单独展示。
- 不要把 Task ID、Session ID、长期私人记忆、用户名或 IP 纳入 D09。
- 不要为了获得特定答案修改数据库或伪造工具结果。

**验收标准**

- [ ] 手动输入的口语化问题完整可见。
- [ ] 任务状态为 `TASK COMPLETED`，模型名和 step 数正常。
- [ ] 回答人数与摄像头真实现场一致，并标明数据新鲜度。
- [ ] `vision.get_people_count · SUCCEEDED` 清晰可见。
- [ ] HARNESS RUN 已收起，截图主题集中在自然语言和工具结果。
- [ ] 没有 Task/Session ID、私人记忆、凭据、IP 或用户名。

## 7. 视觉与事件闭环截图

最终文件放 `docs/media/vision/` 或 `docs/media/events/`。E05–E10 各保存一张发生前原图和一张发生后原图，最后制作拼图。

| 编号 | 公开文件名 | 触发动作 | 验收点 |
|---|---|---|---|
| E01 | `vision/01-people-count.png` | 0、1、2 人各停留 3 秒 | 人数与实际一致 |
| E02 | `vision/02-object-count.png` | 两瓶一盒入画 | 类别和数量清晰 |
| E03 | `vision/03-bottle-inventory.png` | 两瓶稳定放置 | 稳定对象与库存状态 |
| E04 | `vision/04-person-track.png` | 人从左向右走 | Track ID/轨迹连续 |
| E05 | `events/01-zone-enter.png` | 人进入左侧区域 | ZONE_ENTER、区域、时间 |
| E06 | `events/02-zone-exit.png` | 人离开左侧区域 | ZONE_EXIT、正确 Track |
| E07 | `events/03-zone-dwell.png` | 区域内停留超过阈值 | ZONE_DWELL、停留时长 |
| E08 | `events/04-object-appeared.png` | 放入瓶子并静止 | OBJECT_APPEARED、证据 |
| E09 | `events/05-object-removed.png` | 拿走稳定瓶子 | OBJECT_REMOVED、前后证据 |
| E10 | `events/06-object-left-behind.png` | 放下物品后人员离开 | LEFT_BEHIND 与计时 |
| E11 | `events/07-camera-offline-recovered.png` | 维护窗口短暂拔插摄像头 | OFFLINE/RECOVERED 成对，只做一次 |
| E12 | `events/08-evidence-integrity.png` | 检查最近事件证据 | PASS、checked、valid、issues=0 |
| E13 | `events/09-exact-evidence-hash.png` | 验证指定事件证据 | JPEG 字节与 SHA-256 match |
| E14 | `events/10-disposition-filter.png` | 过滤 OPEN | 条件、条数、非法状态拒绝 |
| E15 | `events/11-severity-filter.png` | 过滤 INFO/HIGH | 条件与结果条数 |
| E16 | `events/12-cursor-pagination.png` | 加载更早再返回最新 | 无重叠、返回最新按钮 |
| E17 | `events/13-event-trend.png` | 24 小时/60 分钟桶 | 趋势、总数、峰值 |
| E18 | `events/14-period-comparison.png` | 当前对比前一窗口 | absolute、percent、direction |
| E19 | `events/15-change-contributors.png` | 展开贡献者 | 最大事件类型与贡献 |
| E20 | `events/16-change-assessment.png` | 阈值评估 | SIGNIFICANT_CHANGE 与 reason |
| E21 | `events/17-group-change-signals.png` | 查看分组信号 | 信号均满足阈值 |
| E22 | `events/18-change-cancellation.png` | 查看相反方向变化 | gross、net、masked share |
| E23 | `events/19-aligned-baseline.png` | 60 分钟窗口前移 24 小时 | OFFSET、等长、不重叠 |
| E24 | `events/20-reference-baselines.png` | 昨日和上周同时间 | 两条基线与平均值 |
| E25 | `events/21-reference-assessment.png` | 查看参考评估 | 零基线安全/显著变化原因 |
| E26 | `events/22-reference-consistency.png` | 比较两条参考 | spread、阈值、reliable 状态 |

## 8. Agent Harness、MCP 与安全证明

| 编号 | 公开文件名 | 推荐操作 | 必须证明 |
|---|---|---|---|
| A01 | `agent/01-general-question.png` | 问“你好，你是谁？” | 普通问题零工具、step 正常 |
| A02 | `agent/02-paraphrase-routing.png` | 问“现在摄像头里站着几位？” | 非固定模板仍路由人员工具 |
| A03 | `agent/03-multistep-investigation.png` | 调查最近移走的瓶子 | 版本固定 Skill、多步工具 |
| A04 | `agent/04-session-memory.png` | 暗号记忆与追问 | 有界会话记忆、可清除 |
| A05 | `agent/05-long-term-memory.png` | 记住偏好并确认 | L1、revision、provenance |
| A06 | `agent/06-job-sse.png` | 异步任务 | 队列、幂等、SSE、取消 |
| A07 | `agent/07-budgets.png` | Workbench 预算区 | 模型/工具/外部/时间预算 |
| A08 | `agent/08-token-cost.png` | Token 治理区 | 真实 usage，成本不伪造 |
| A09 | `agent/09-routing-reduction.png` | 工具路由检查 | Schema 缩减、最大可见工具数 |
| A10 | `agent/10-resilience.png` | 韧性区 | retry、circuit、offline fallback |
| A11 | `agent/11-hooks.png` | Hook 时间线 | 生命周期、超时、fail-closed |
| A12 | `agent/12-evaluation.png` | Evaluation | 数据集哈希、准确率、默认拒绝 |
| M01 | `mcp/01-tool-catalog.png` | Dashboard Catalog | 工具名、Schema、风险、分类 |
| M02 | `mcp/02-stdio-acceptance.png` | `bash scripts/run_mcp_server_test.sh` | 协议版本、tools/resources/prompts |
| M03 | `mcp/03-resource-read.png` | 读取视觉资源 | 有界 frame、stale、性能 |
| M04 | `mcp/04-default-deny.png` | 测试 gated/未知工具 | POLICY_DENIED、JSON-RPC 拒绝 |
| S01 | `security/01-auth-rbac.png` | `check_auth_rbac_dashboard.ps1` | 401、CSRF 403、admin、logout |
| S02 | `security/02-tls-dashboard.png` | `check_tls_dashboard.ps1` | pinned cert、Secure Cookie、HSTS/CSP |
| S03 | `security/03-risk-gates.png` | L0/L1/L2 拼图 | 风险分级、确认门、默认拒绝 |
| S04 | `security/04-secret-exclusion.png` | 发布/灾备摘要 | credentials=False、paths=False |
| S05 | `security/05-audit-trace.png` | Workbench Trace | 不泄露模型内容、Payload、凭据 |

## 9. 运维、恢复与发布截图

终端只截 acceptance summary。最终文件放 `operations/`、`recovery/`、`release/`。

| 编号 | 公开文件名 | 命令/页面 | 截图重点 |
|---|---|---|---|
| O01 | `operations/01-systemd-runtime.png` | `bash scripts/check_systemd_runtime.sh` | enabled/active、API ok、vision fresh、TLS/Auth |
| O02 | `operations/02-boot-service.png` | `bash scripts/check_boot_service.sh` | systemd、依赖、fail-closed |
| O03 | `operations/03-full-tests.png` | 全量 unittest | 用例数与 OK |
| O04 | `operations/04-deepseek-runtime.png` | DeepSeek systemd 验收 | persistent remote、API key hidden |
| O05 | `operations/05-model-manifest.png` | 模型清单验收 | 版本、哈希、完整性 |
| O06 | `operations/06-vision-performance.png` | 视觉性能验收 | FPS、延迟、stale |
| O07 | `operations/07-runtime-benchmark.png` | 基准验收 | PASS、samples、阈值 |
| O08 | `operations/08-storage-usage.png` | 存储查询 | 有界扫描、路径不暴露、只读 |
| R01 | `recovery/01-reboot-recovery.png` | `check_reboot_recovery.sh` | Boot ID changed、TLS recovered、frame resumed |
| R02 | `recovery/02-tls-rotation.png` | `check_tls_rotation.sh` | old/new、权限、runtime match |
| R03 | `recovery/03-dr-backup-preview.png` | 灾备测试 | SQLite consistent、manifest、preview only |
| R04 | `recovery/04-scheduled-export.png` | 定时导出检查 | DEMO_WEEKLY、timer active、SUCCEEDED |
| R05 | `recovery/05-offdevice-sync.png` | Windows 限权同步 | RESTRICTED_SSH、verified、无明文 |
| R06 | `recovery/06-recovery-health.png` | 异机恢复健康检查 | age、count、bytes、drill、PASS |
| R07 | `recovery/07-isolated-drill.png` | 隔离恢复演练 | isolated、SQLite、production=False |
| R08 | `recovery/08-capacity-preview.png` | 容量预览 | 本地候选、加密导出受保护、未删除 |
| R09 | `recovery/09-capacity-cleanup.png` | 确认式容量清理 | 仅删除本地旧备份、导出删除=0 |
| P01 | `release/01-publication-gate.png` | `check_github_publication.sh` | 测试、隐私、发布门 PASS |
| P02 | `release/02-release-provenance.png` | provenance test | manifest、CycloneDX、MATCH |
| P03 | `release/03-release-artifacts.png` | build + integrity | release ID、文件数、凭据=False |
| P04 | `release/04-github-actions.png` | GitHub Actions | workflow、commit、绿色通过 |
| P05 | `release/05-repository-home.png` | GitHub 首页 | 标题、硬件图、徽章、目录 |

## 10. 全功能视频清单

| 编号 | 最终文件名 | 时长 | 演示顺序 | 标记 |
|---|---|---:|---|---|
| V01 | `edgesentinel-demo-01-end-to-end-zh-cn-1080p.mp4` | 2–3 分钟 | 实物 → HTTPS → 检测 → 事件 → Agent → Workbench | L0/PHY |
| V02 | `edgesentinel-demo-02-live-vision-zh-cn-1080p.mp4` | 60–90 秒 | 0/1/2 人 → 两瓶一盒 → 轨迹 | PHY |
| V03 | `edgesentinel-demo-03-zone-events-zh-cn-1080p.mp4` | 60–90 秒 | 进入 → 停留 → 离开 → 三类证据 | PHY |
| V04 | `edgesentinel-demo-04-object-lifecycle-zh-cn-1080p.mp4` | 90 秒 | 放瓶 → 稳定库存 → 拿走 → 前后证据 | PHY |
| V05 | `edgesentinel-demo-05-left-behind-zh-cn-1080p.mp4` | 60–90 秒 | 人携物进入 → 放下 → 离开 → 遗留事件 | PHY |
| V06 | `edgesentinel-demo-06-agent-harness-zh-cn-1080p.mp4` | 2 分钟 | 改写问题 → Route → Skill → Hooks → Trace → Budget | L0 |
| V07 | `edgesentinel-demo-07-online-offline-tools-zh-cn-1080p.mp4` | 90 秒 | remote 问星期/天气 → offline 视觉 → 切回 | L0 |
| V08 | `edgesentinel-demo-08-mcp-server-zh-cn-1080p.mp4` | 90 秒 | Catalog → Schema → stdio → resources → deny | L0 |
| V09 | `edgesentinel-demo-09-risk-confirmation-rbac-zh-cn-1080p.mp4` | 2 分钟 | L0 → L1 取消/确认 → L2 提示 → RBAC/CSRF | L1/L2/SEC |
| V10 | `edgesentinel-demo-10-event-analytics-zh-cn-1080p.mp4` | 2 分钟 | 过滤 → 分页 → 趋势 → 环比 → 贡献 → 基线 | L0 |
| V11 | `edgesentinel-demo-11-memory-jobs-governance-zh-cn-1080p.mp4` | 2 分钟 | 会话记忆 → 长期记忆 → SSE → Token/预算 | L0/L1 |
| V12 | `edgesentinel-demo-12-camera-recovery-zh-cn-1080p.mp4` | 90 秒 | 正常 → 短暂拔摄像头 → OFFLINE → RECOVERED | L2/PHY |
| V13 | `edgesentinel-demo-13-model-resilience-zh-cn-1080p.mp4` | 90 秒 | retry/circuit → 测试失败 → fallback → 恢复 | L0 |
| V14 | `edgesentinel-demo-14-retention-safety-zh-cn-1080p.mp4` | 90 秒 | 占用 → 预览 → 错误确认拒绝 → 取消 → 历史 | L0/L2 |
| V15 | `edgesentinel-demo-15-reboot-tls-auth-zh-cn-1080p.mp4` | 2 分钟 | HTTPS/RBAC → reboot → systemd 恢复 → TLS 有效 | L2/SEC |
| V16 | `edgesentinel-demo-16-disaster-recovery-zh-cn-1080p.mp4` | 2–3 分钟 | 备份 → 加密 → 限权同步 → 健康 → 隔离演练 | L1/SEC |
| V17 | `edgesentinel-demo-17-capacity-control-zh-cn-1080p.mp4` | 90 秒 | DEMO_WEEKLY → 预览 → 固定计划 → 本地清理 | L2 |
| V18 | `edgesentinel-demo-18-release-engineering-zh-cn-1080p.mp4` | 90 秒 | 全量测试 → publication gate → SBOM → CI PASS | L0 |
| V19 | `edgesentinel-demo-19-full-uncut-proof-zh-cn-1080p.mp4` | 5–8 分钟 | 实物、浏览器、关键终端连续无剪辑 | L0/PHY |
| V20 | `edgesentinel-demo-20-project-trailer-zh-cn-1080p.mp4` | 45–60 秒 | 硬件、检测、事件、Agent、MCP、安全、恢复、CI | 发布片 |

### V01 一镜到底旁白

1. “这是运行在 Jetson Nano 上的 EdgeSentinel 边缘视觉系统。”
2. 展示 USB 摄像头、Wi‑Fi、HDMI 和 PC 远程 Dashboard。
3. 登录 HTTPS Dashboard，说明认证与 TLS 已开启。
4. 人进入画面，展示检测框、人员计数和最新帧。
5. 人进入区域并拿走瓶子，展示事件和证据。
6. 问“摄像头里面现在站着几位？”，展示自动工具路由。
7. 展开 Workbench，展示决策、工具、Trace、预算和 Hook。
8. 展开 MCP Catalog，说明 Schema、风险和默认拒绝。
9. 用 systemd 验收与 GitHub Actions 通过页面收尾。

## 11. 推荐分批执行

| 批次 | 内容 | 预计时间 |
|---|---|---:|
| Batch 1 | H10 工作台同框照 + D02、D03、D06、D09、D10、D11 核心 Dashboard | 40 分钟 |
| Batch 2 | E01–E13 视觉事件闭环 | 60–90 分钟 |
| Batch 3 | D14–D30、A01–A12、M01–M04、S01–S05 | 60–90 分钟 |
| Batch 4 | O01–O08、R01–R09、P01–P05 | 60–90 分钟 |
| Batch 5 | V01、V02、V03、V06、V08、V18 | 半天 |
| Batch 6 | 其余专项视频 | 1–2 天 |
| Batch 7 | V20 宣传片 | 1–2 小时 |

现有 H01 已完成硬件总览。下一批拍 H10 和 D02/D03/D06/D09/D10/D11，然后再拍 E09、V01/V06/V18。

## 12. 公开前脱敏检查

- [ ] 没有 DeepSeek API Key、GitHub Token、密码或恢复口令。
- [ ] 没有 `/etc/edgesentinel-visionops/*.env` 内容。
- [ ] 没有 Cookie、CSRF Token、Authorization Header 或 TLS/SSH 私钥。
- [ ] 没有私人邮箱、聊天消息、浏览器通知、Wi‑Fi 名称或地址。
- [ ] 没有序列号、二维码、MAC 地址或无需公开的证书指纹。
- [ ] LAN IP、用户名、主机名、Task/Event/Memory ID 已按需模糊。
- [ ] Evidence 绝对路径已裁剪；人脸已获授权或打码。
- [ ] 视频音轨没有读出任何秘密。

## 13. 交付给 Codex

每完成一个 Batch，把原片放进对应日期目录，然后提供准确路径，例如：

```text
Batch 2 已完成：
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\02_raw_screens\2026-08-11
```

Codex 会检查清晰度、隐私、重复镜头与命名，再挑选、裁剪并复制到 `docs/media/`。不要把原片目录整体复制进仓库；不确定的素材先放 `99_rejected_private`。

## 14. 最小可发布组合

- [x] H01 整机总览（已有）
- [x] H10 PC Dashboard 与 Jetson 同框（原片已验收；公开前遮挡 IP、用户名和二维码）
- [x] D02 Dashboard 总览（原始长截图已验收）
- [x] D03 人员检测（原片已验收；公开前默认打码人脸）
- [x] D06 事件中心（局部截图已验收）
- [ ] D09 Agent 工具调用
- [ ] D10 Agent Workbench
- [ ] D11 MCP Catalog
- [ ] E09 物品移走事件与证据
- [ ] V01 端到端演示

现有硬件总览加上这些核心界面、事件和视频，就能显著提升 GitHub 首页可信度；无需用大量器材特写稀释项目重点。
