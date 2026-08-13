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
| D09 | `dashboard/09-agent-chat-tool-call.png` | 0 人/1 人两次自然语言查询 | **原片已完成**；视觉状态、回答与 `vision.get_people_count` 相互印证 | L0 |
| D10 | `dashboard/10-agent-workbench.png` | 展开 Workbench | **原片已完成**；元数据、预算和完整脱敏生命周期 Trace | L0 |
| D11 | `dashboard/11-mcp-catalog.png` | 展开 MCP 目录 | **原片已完成**；25 工具/5资源/3提示、5个工具名、外部网络标记和天气 Schema | L0 |
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

### D09/D10 原片验收说明

已保存 `no_people.png` 和 `one_people.png` 两张 1205×8754 整页原图。两张图分别记录 0 人与 1 人场景，顶部实时视觉画面/指标与底部 Agent 回答一致，并显示 `vision.get_people_count · SUCCEEDED`。最终 D09 制作为双场景对照图，不需要重拍。

两张原图中的 HARNESS RUN 已展开，虽然不符合 D09 单图的最简构图，但提供了 D10 所需的完整来源：模型、Skill、工具路由、韧性、步骤、耗时、执行预算及脱敏 Trace。最终从 `one_people.png` 单独裁出 D10；公开版截断 Task ID，并检查 Session/用户信息。因此 D09 与 D10 均标记为原片完成。

### D11 详细截图卡：MCP 工具目录与 Schema

**目标**

证明 EdgeSentinel 不只是内部函数集合，而是向 Agent 暴露了结构化、带风险注解和 JSON Schema 的 MCP 工具目录。截图需同时展示工具总数、多个工具名称、L0/只读/本地或外部网络标记，以及至少一个已展开工具的参数 Schema。

**截图前准备**

1. 保持 Dashboard 已登录、`API 在线`。
2. 滚动到 `EDGE RUNTIME / 服务运行状态` 面板。
3. Agent 任务、事件详情和确认窗口无需出现在截图中。
4. 不调用任何 MCP 工具；D11 只查看目录，属于 L0 只读操作。

**具体操作步骤**

1. 在“服务运行状态”中确认 `MCP 工具协议` 一行显示类似：

   ```text
   按需启动 · 25工具 · 5资源 · 3提示
   ```

   实际数字可随版本增长，以当前页面为准，不要手工修改。
2. 点击面板底部“查看 MCP 工具”。
3. 等待摘要变为“XX 个只读 MCP 工具 · 点击名称查看参数 Schema”，不能停留在“正在读取”。
4. 在工具列表中找到并展开 `vision.get_people_count`；如果它的输入 Schema 过短，可改为展开参数更丰富且仍为 L0 的 `event.query`。
5. 只展开一个工具，其余工具保持收起，以便同图展示至少 5 个不同工具名称。
6. 截图范围从 `EDGE RUNTIME / 服务运行状态` 标题开始，必须包含：

   - `MCP 工具协议` 状态行；
   - “XX 个只读 MCP 工具”摘要；
   - 至少 5 个工具名称；
   - 每个名称旁的 `L0 · 只读 · 本地` 或 `L0 · 只读 · 外部网络`；
   - 一个工具的说明文字和 JSON Schema。

7. 如果列表在右侧窄栏中导致 Schema 太窄，可只对右侧 Edge Runtime 面板做区域长截图；不要把左侧大面积空库存面板纳入最终图。
8. 使用系统截图或 Edge 区域长截图，不使用手机拍屏。

**推荐展开顺序**

首选：

```text
vision.get_people_count
```

备选：

```text
event.query
weather.get_current
```

如果展示 `weather.get_current`，必须让“外部网络”标记可见，但不需要实际发起天气请求。

**原始文件名**

```text
20260812_D11_mcp-catalog-schema_take01.png
```

若另拍外部网络工具：

```text
20260812_D11_mcp-catalog-external-weather_take02.png
```

保存到：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\02_raw_screens\2026-08-12\
```

**不要这样截**

- 不要只截工具名称而没有摘要、风险标记或 Schema。
- 不要一次展开多个工具，导致截图过长且难读。
- 不要停留在“正在读取 MCP 工具目录”或读取失败状态。
- 不要把 Agent Task ID、长期记忆、事件详情或用户/IP 纳入图中。
- 不要打开浏览器开发者工具来展示原始 API Payload；Dashboard 的脱敏目录就是公开证据。

**验收标准**

- [ ] MCP 协议状态行与只读工具总数可见。
- [ ] 至少 5 个不同 MCP 工具名可读。
- [ ] L0、只读、本地/外部网络注解可读。
- [ ] 一个工具的描述与 JSON Schema 完整可见。
- [ ] 没有调用写工具，也没有凭据、Task ID、IP 或用户名。

### E09 详细截图卡：瓶子移除事件与前后证据

**目标**

用真实物理动作完成“瓶子出现并成为稳定库存 → 保存变化前检查点 → 拿走瓶子 → 生成 `OBJECT_REMOVED` → 打开事件详情 → 校验 before/after 证据”的完整闭环。最终截图重点是事件详情和前后证据，而不是只拍一个瓶子检测框。

**当前实际触发参数**

```text
minimum_hits：3
出现确认：连续 15 帧
移除确认：连续 30 帧
稳定库存证据检查点：每 15 帧
当前视觉速度：约 14.9 FPS
```

理论确认只需数秒，但真实拍摄必须按下述 8–10 秒等待执行，不要看到一次检测框就立刻拿走。

**物理场景准备**

1. 准备一个外形标准的塑料饮料瓶，首选透明或有明显标签的 500–600 ml 瓶；不要用异形保温杯代替。
2. 摄像头对准桌面，使完整瓶身占画面高度约 25%–50%。如果当前镜头主要拍到墙和天花板，需要先向下调整摄像头。
3. 瓶子直立放置，背景使用与瓶身颜色反差明显的纯色桌面或纸板。
4. 画面中只保留一个待测瓶子，移开其他可能被识别为 bottle/cup 的物品。
5. 不要求人员进入区域；手放下或拿走瓶子后应立即离开画面。
6. 调整摄像头后先等待 Dashboard 回到 `LIVE`，不要在 `STALE` 状态测试。

**阶段 A：建立稳定库存与 before 证据**

1. 回到 Dashboard 顶部，确认“当前物品”为 0 或没有 bottle 稳定库存。
2. 将瓶子直立放在画面中央或光线较好的位置，然后把手移出画面。
3. 等待出现 `bottle XX.X%` 检测框。
4. 保持瓶子完全不动至少 8–10 秒。
5. 只有同时满足以下条件才进入下一阶段：

   - “当前物品”至少为 1；
   - “画面中的稳定物品”出现 `bottle`，数量为 1；
   - 实时画面仍显示 bottle 检测框；
   - 视觉状态为“实时”；
   - 上述稳定状态再持续至少 5 秒，以确保 before 检查点已写入。

6. 如果 20 秒内仍未稳定识别，停止操作并调整瓶子距离、照明或背景；不要直接进入移除阶段。

**阶段 B：触发真实移除事件**

1. 从瓶身顶部或侧面快速拿走瓶子，手不要在画面中停留。
2. 拿走后保持画面空白至少 8–10 秒。
3. 等待“当前物品”回到 0，稳定库存列表不再显示 bottle。
4. 不要反复放回瓶子；一次完整出现/移除只生成一组清晰事件。

**阶段 C：筛选并打开事件详情**

1. 滚动到事件中心，设置：

   ```text
   事件类型：物品移除
   处置状态：待处理
   严重级别：全部级别
   目标类别：bottle
   摄像头：留空
   显示数量：6条
   时间范围：最近10分钟
   ```

2. 点击“应用筛选”，等待最新一条“物品移除 / bottle / Global Scene”出现。
3. 核对时间是刚才操作时间，再点击该条目的“详情”。不要确认处理事件。
4. 等事件详情与证据完整性加载完毕，不能停留在“等待读取/等待校验”。

**事件详情必须达到的状态**

- 标题为“物品移除”。
- 目标类别为 `bottle`。
- 处置状态为“待处理 · 尚未修改事件记录”。
- 证据完整性为 `PASS`，有效证据数与引用数一致。
- 至少出现“变化前”和“变化后”两张证据图。
- 变化前图中瓶子清楚存在；变化后图中瓶子已经消失。
- 如果另有“主要证据”，允许保留，但 before/after 是核心。

**截图方式**

1. 只截事件详情弹窗，不截背后的整站页面。
2. 截图范围从 `EVENT DETAIL / 物品移除` 开始，到完整证据图片网格结束。
3. 保留事件字段、处置状态、证据完整性和 before/after 标签。
4. 不要包含弹窗底部“结构化详情”JSON；其中可能含相对证据路径，公开图没有必要展示。
5. 如果弹窗单屏放不下，使用区域长截图，仅捕获详情弹窗顶部到证据网格。

**原始文件名**

```text
20260812_E09_object-removed-bottle-before-after_take01.png
```

如需补一张事件列表定位图：

```text
20260812_E09_object-removed-bottle-event-list_take02.png
```

保存到：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\02_raw_screens\2026-08-12\
```

**常见失败与处理**

- `当前物品=0`：瓶子未进入稳定库存，不能拿走；改善光线和尺寸后重试。
- 有 bottle 框但库存仍为 0：继续保持不动，等待确认帧数。
- 移除后没有事件：继续保持画面空白 10 秒，再刷新事件中心。
- 只有 after、没有 before：稳定库存检查点尚未建立；重新放置瓶子并在库存=1后多等 5–10 秒。
- 证据完整性不是 PASS：不要截图为成功案例，保留错误状态并告诉 Codex排查。
- 模型始终无法识别真实瓶子：不要伪造事件，拍下实际摆放场景并停止该项。

**不要这样做**

- 不要编辑数据库、复制旧事件或修改系统时间制造移除事件。
- 不要通过拔摄像头代替拿走瓶子。
- 不要在瓶子尚未成为稳定库存时拿走。
- 不要点击“通过 Agent 确认已处理”。
- 不要公开完整 Event ID 或结构化 JSON 中的证据路径；最终版会截断 Event ID。
- 不要让人脸、工牌、私人文件或其他显示器进入证据画面。

**验收标准**

- [ ] 事件类型为 OBJECT_REMOVED/物品移除，目标为 bottle。
- [ ] 事件时间与本次实际拿走瓶子的时间一致。
- [ ] 处置状态仍为待处理，没有写操作。
- [ ] 证据完整性 PASS，引用均有效。
- [ ] before 图有瓶子，after 图无瓶子，变化直观。
- [ ] 截图不包含结构化 JSON、证据路径、用户名或 IP。

## 7. 视觉与事件闭环截图

最终文件放 `docs/media/vision/` 或 `docs/media/events/`。动态功能优先录制连续视频，再从已验收原片无损提取关键帧作为 README 静态图；不要为了同一结论同时重复录制和截图。E01–E03 由 V02 覆盖；E04 使用 V02 的跨区动作并由 V03 中一致的 Track ID 补强；E05–E07 由 V03 覆盖，E08–E09 由 V04 覆盖，E10 由 V05 覆盖，E11 由 V12 覆盖；E12–E13 是稳定的完整性/哈希结论，使用单独截图。

| 编号 | 公开文件名 | 触发动作 | 验收点 |
|---|---|---|---|
| E01 | `vision/01-people-count.png` | 0、1、2 人各停留 3 秒 | 人数与实际一致 |
| E02 | `vision/02-object-count.png` | 两瓶加一本书入画 | 使用模型支持的 `bottle`/`book`，类别和数量清晰 |
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
| V02 | `edgesentinel-demo-02-live-vision-zh-cn-1080p.mp4` | 90–120 秒 | 0/1/2 人 → 跨区域轨迹 → 两瓶加鼠标 → 稳定库存 | PHY |
| V03 | `edgesentinel-demo-03-zone-events-zh-cn-1080p.mp4` | 150–210 秒 | 左区进入 → 连续停留 → 原路离开 → 三类证据 → Agent 核对匿名 Track ID | PHY/L0 |
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
| V18 | `edgesentinel-demo-18-release-engineering-zh-cn-1080p.mp4` | 可选 | 发布工程以 P01–P04 静态截图为主；宣传片需要时再做动态蒙太奇 | L0 |
| V19 | `edgesentinel-demo-19-full-uncut-proof-zh-cn-1080p.mp4` | 5–8 分钟 | 实物、浏览器、关键终端连续无剪辑 | L0/PHY |
| V20 | `edgesentinel-demo-20-project-trailer-zh-cn-1080p.mp4` | 45–60 秒 | 硬件、检测、事件、Agent、MCP、安全、恢复、CI | 发布片 |

### 截图与视频的选择规则

- **必须录视频**：状态随时间变化、物理动作触发、轨迹连续性、自动恢复或多步 Agent 执行。视频保留动作发生前、发生时和发生后的连续因果链。
- **优先截图**：哈希、SBOM、测试 PASS、配置摘要、工具 Schema、审计/恢复最终状态等稳定结论。截图信息密度高，也便于读者放大核对文字。
- **视频派生截图**：人数 0→1→2、物品出现/稳定/移除、区域进入/停留/离开等动态功能先录视频；README 所需静态图从验收视频关键帧提取，不要求再次摆拍。
- **不重复拍摄**：一个已验收视频若完整覆盖某个 E 编号，只补缺失的关键帧，不重新执行物理动作。
- **危险或扰动操作**：摄像头拔插、重启、清理、长期记忆写入等只在明确的维护窗口录制一次；静态证明优先使用已有 acceptance summary。

### V02 原片验收记录：实时人数、跨区移动与稳定库存

原片：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\03_raw_videos\2026-08-12\20260812_V02_live-vision-people-objects-tracks_take01.mp4
```

实际规格与结果：

- 时长 `231.1` 秒，画面 `1920×1080`，`30 FPS`，文件约 `21.8 MiB`；时长偏长但核心过程连续，无需整段重录。
- 清楚录到无人 `Left/Right Zone 0/0`、单人跨区、两人分站左右区域 `1/1`，再依次离场回到无人，E01 动态人数闭环成立。
- 清楚录到第一瓶、第二瓶和鼠标依次进入画面；最终 Dashboard 显示当前物品 `3`、稳定类别 `2`、库存 `bottle 2 / mouse 1`，E02–E03 成立。
- 后续事件中心包含本次 `bottle`/`mouse` 物品出现记录，强化了物理动作与系统记录的对应关系。
- V02 录到了人员跨区域移动，但标注画面没有直接显示 Track ID/轨迹点；E04 不判定为独立完成，由 V03 的 ZONE_ENTER/ZONE_DWELL/ZONE_EXIT 一致 Track ID 补强，不重录 V02。
- 原片带音轨，发布版必须静音；地址栏包含 LAN IP 和“不安全”提示、右上角账户标记，且至少一名人员面部未完全遮挡，发布剪辑必须裁掉浏览器顶栏并对所有可辨认人脸打码。
- 推荐发布剪辑保留约 `80–110` 秒：无人基准、单人跨区、两人 `1/1`、人数归零、两瓶与鼠标、最终 `bottle 2 / mouse 1`；删除事件列表中的重复滚动和等待。

### V03 详细录制卡：区域进入、停留、离开与匿名轨迹核对

原片保存为：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\03_raw_videos\2026-08-13\20260813_V03_zone-enter-dwell-exit-track_take01.mp4
```

录制规格：`1920×1080`、`30 FPS`、预计 `150–210` 秒；关闭麦克风和系统声音。全程只使用一个测试人员，另一人操作 PC。录制前保持瓶子、鼠标等现有物品不动，避免在本段产生无关物品事件；浏览器只打开 EdgeSentinel Dashboard，确保 HTTPS、摄像头与 DeepSeek 均正常。

物理动作必须按以下顺序连续完成，不能暂停或剪切：

1. 将 Dashboard 停在顶部实时画面，测试人员完全离开镜头，保留 `5` 秒无人基准。
2. 测试人员从画面左边缘进入 **Left Zone**，脚部和人体下缘保持可见；进入后不要跨过中央分界线。
3. 等 Dashboard 显示当前人数 `1`、Left Zone `1` 后开始计时，在左区原地连续停留 `30–35` 秒。动作可以轻微变化，但不要走出检测框，也不要遮挡摄像头。
4. 测试人员沿原路径从左侧完全离开，仍然不要经过 Right Zone；离开后保持空画面 `8` 秒，让 `30` 帧离区确认完成。

随后由 PC 操作者在同一段录屏中完成核验：

5. 打开事件中心，时间范围选最近可用窗口，摄像头选 `camera_01`，对象类别选 `person`，事件类型、严重级别和状态均选“全部”，显示数量选 `6`，应用筛选。
6. 列表必须同时出现本轮 Left Zone 的 `ZONE_ENTER`、`ZONE_DWELL`、`ZONE_EXIT`；时间顺序正确，严重级别应为 `INFO / MEDIUM / INFO`。若出现额外的 Right Zone 事件，本次动作不合格。
7. 依次打开三条事件详情，各停留约 `4` 秒；至少让事件类型、区域、时间、证据图片和完整性状态进入画面。不要点击“确认事件”等写操作。
8. 在 Vision Copilot 输入下面这句中文并发送：

```text
查询最近10分钟 camera_01 的人员区域事件。分别找到最近一次进入区域、长时间停留以及随后对应的离开区域事件，列出三条事件的区域、时间和 track_id，并判断是否属于同一条匿名轨迹。不要推断人员身份。
```

9. 等待回答完整出现。验收要求：`event.query` 显示 `SUCCEEDED`，回答列出三类事件，三条记录的 `track_id` 一致，并明确说明 Track ID 只是匿名跟踪编号、不能据此识别人名。完整回答保留 `6–8` 秒后停止录制。

重拍条件：停留 `35` 秒仍无 `ZONE_DWELL`、中途丢失检测导致 Track ID 改变、产生 Right Zone 事件、三类事件缺任意一类、Agent 将匿名 Track ID 误说成人员身份。若物理事件链已经正确而只有 Agent 首次回答不完整，不覆盖原片；保存为 `take02` 后仅补录查询与回答，发布剪辑再拼接。

发布处理：裁掉浏览器地址栏和 LAN IP，隐藏账户标记，对所有可辨认人脸持续跟踪打码并彻底移除音轨。E05–E07 静态图直接从三条事件详情关键帧提取，不再重复摆拍。

### V04 原片验收记录：瓶子生命周期与移除证据

原片：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\03_raw_videos\2026-08-12\20260812_V04_object-lifecycle-bottle-removal_take01.mp4
```

实际规格与结果：

- 时长 `89.8` 秒，画面 `1920×1080`，约 `23.6 FPS`，文件约 `4.7 MiB`。
- 连续录到了登录、实时瓶子检测、稳定库存、拿走瓶子、库存归零、事件筛选和事件详情。
- 最新事件为“物品移除”，目标类别为 `bottle`，处置状态仍为“待处理”。
- 证据完整性为 `PASS · 3/3有效 · primary=VALID · before=VALID · after=VALID`。
- “变化前”清楚显示瓶子，“变化后”清楚显示瓶子已消失，物理变化闭环成立。
- 原片可验收，无需重录；E09 公开静态图可从事件详情清晰帧无损截取，直接截图仅作为可选补拍。
- 发布前应裁去或遮挡浏览器地址中的 LAN IP、右上角用户名、完整 Event ID，并删除或静音原始音轨（如存在）。

### V01 原片验收记录：Dashboard、Agent、事件与 MCP 端到端

原片：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\03_raw_videos\2026-08-12\20260812_V01_end-to-end-dashboard-agent-mcp_take01.mp4
```

实际规格与结果：

- 时长 `209.4` 秒，画面 `1920×1080`，约 `23.6 FPS`，文件约 `16.5 MiB`。
- 登录入口、Dashboard 实时画面、人员从 0 变为 1、左侧区域人数 1 和实时状态均清楚可见。
- Agent 对“请只回答当前摄像头有几个人，并调用视觉人数工具”的任务返回当前 1 人，`vision.get_people_count · SUCCEEDED`。
- Workbench 清楚显示 `DETERMINISTIC` 路由、`COMPLETED · 2 steps`、模型调用、L0 工具、Hooks、工具结果、Token/执行预算与任务结束。
- 事件段展示的是本次人员入画产生的“长时间停留 / person / Left Zone / MEDIUM / 待处理”，证据完整性 `PASS · 1/1有效 · primary=VALID`；它与 V04 的 bottle before/after 形成互补，不视为缺陷。
- MCP Catalog 显示 `25个只读MCP工具`，并展开 `vision.get_people_count` 的 L0/只读/本地标记、说明和 JSON Schema。
- 原片可验收，无需重录。发布剪辑应删除前半段无关的 `who are you` 请求、排队等待、重复滚动和事件加载等待，将成片压缩到约 150–180 秒。
- 发布前应遮挡 LAN IP、右上角用户名、完整 Task/Event/Session ID，并默认打码人员面部；原始音轨如存在应删除或静音。

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

### V01 详细录制卡：端到端核心演示

**目标**

用一段连续的 PC 屏幕录像，证明“认证进入 → Jetson 实时视觉 → 人数变化 → Agent 自动选择工具 → Harness Workbench 可观测 → 事件证据可追溯 → MCP 工具 Schema 可见”的核心链路。硬件真实性由 H01/H10 和 V04 补充，V01 不需要再用手机拍开发板。

**录制参数**

```text
画面：1920×1080
帧率：30 FPS（录制软件若只能稳定到 24 FPS 也可）
预计时长：2–3 分钟
录制范围：浏览器窗口或 1920×1080 显示器
麦克风：关闭
系统声音：关闭
鼠标指针：保留
浏览器缩放：90% 或 100%，全程不变
```

不要使用长截图录制模式，不要在录像过程中切换分辨率。Chrome 地址栏和 Dashboard 用户名允许留在原片中，发布版会统一裁剪或遮挡。

**录制前准备**

1. 确认 `https://192.168.1.101:8443/dashboard` 可以打开，证书仍为当前已验证证书。
2. 退出 Dashboard 回到登录页，但不要在录像中展示或输入真实密码。可在开始录制前让浏览器已记住表单，或只展示登录页 2 秒后暂停录制、登录、再继续；最终会剪辑转场。
3. 确认 Dashboard 启动模式为远程 DeepSeek，API 在线，视觉状态为 `LIVE/实时`。
4. 让摄像头初始画面无人，当前人员为 0；移走桌面上会干扰识别的其他物品。
5. 准备让一名人员进入摄像头画面并停留 5–8 秒。人脸可以进入原片，公开版默认打码。
6. 事件中心应能找到 V04 刚生成的“物品移除 / bottle”事件；如超过最近 10 分钟，将时间范围改为“最近 24 小时”或“全部历史”。
7. 清空 Vision Copilot 输入框，不要清除本次已有事件或修改处置状态。

**连续镜头顺序**

1. **登录入口，约 3 秒**

   - 从 EdgeSentinel 登录页开始。
   - 页面标题和登录卡必须完整可见。
   - 不在录像中敲真实密码；使用已填充的圆点密码并点击登录，或后期在此处使用切镜。

2. **系统总览，约 8 秒**

   - 登录后停在 Dashboard 顶部。
   - 让项目标题、`API 在线`、摄像头最新标注画面、当前人员和视觉状态同时可见。
   - 初始画面保持无人，展示“当前人员 0 / 可见 0 / 实时”。

3. **真实人员检测，约 15 秒**

   - 人员进入摄像头画面中央或左侧区域，站定 5–8 秒。
   - 等待画面出现 `person XX.X%` 检测框，当前人员和可见人员变为 1。
   - 鼠标不要遮住检测框或人数数字。
   - 人员离开画面后再等 3–5 秒，让画面回到无人状态；不要求在这一段打开事件。

4. **Agent 工具调用，约 25–40 秒**

   - 在 Vision Copilot 输入：

     ```text
     请只回答当前摄像头里有几个人，并调用视觉人数工具。
     ```

   - 点击“发送问题”后不要重复点击。
   - 等待任务显示 `TASK COMPLETED`、`1 step`，并显示 `vision.get_people_count · SUCCEEDED`。
   - 答案人数必须与此时实时画面一致；如人员已离开，应为 0。不要为了得到 1 人而让操作人员在键盘和摄像头之间来回奔跑。

5. **Agent Harness Workbench，约 25–35 秒**

   - 展开刚才任务的 Workbench/执行详情。
   - 缓慢滚动，至少依次停留在以下内容各 2–3 秒：

     ```text
     Task COMPLETED
     TOOL_ROUTE / DETERMINISTIC
     MODEL_DECISION
     vision.get_people_count / SUCCEEDED
     Policy / L0
     Trace 或生命周期时间线
     模型调用、工具调用与 Token/执行预算
     ```

   - 不展开原始模型内容、完整 Task ID、会话原文或任何内部证据路径。

6. **真实事件证据，约 20–30 秒**

   - 滚动至事件中心，筛选：物品移除、待处理、全部级别、`bottle`，时间选择能覆盖 V04 事件。
   - 打开最新一条与 V04 时间一致的事件详情。
   - 停留到清楚显示：`PASS`、`3/3有效`、`before=VALID`、`after=VALID`，以及变化前有瓶子、变化后无瓶子的三张图。
   - 不点击“通过 Agent 确认已处理”，不展开结构化 JSON。

7. **MCP Catalog，约 20–30 秒**

   - 关闭事件详情，滚动到 MCP Catalog。
   - 显示工具总数、资源数、Prompt 数和只读工具摘要。
   - 展开 `weather.get_current` 或 `vision.get_people_count`，让工具说明、L0/只读标记及 JSON Schema 同时可见。
   - 不实际调用外部天气，不产生额外网络结果；本段只证明 Schema 和注册目录。

8. **结尾，约 5 秒**

   - 回到 Dashboard 顶部或停在 Workbench 总览。
   - 让 `API 在线`、`实时` 或 `TASK COMPLETED` 中至少两个状态可见。
   - 鼠标移到空白处，静止 3–5 秒后停止录制。

**原始文件名与位置**

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\03_raw_videos\2026-08-12\20260812_V01_end-to-end-dashboard-agent-mcp_take01.mp4
```

如果因登录剪切必须录成两段，第二段命名：

```text
20260812_V01_end-to-end-dashboard-agent-mcp_take02.mp4
```

不要覆盖 take01；后期可以合并。

**立即停止并报告的情况**

- API 不在线、视觉状态为 STALE、摄像头画面不刷新。
- 人员进入 15 秒仍无 person 框，或人数与实际不一致。
- Agent 未调用 `vision.get_people_count`，工具失败，或答案人数与实时状态冲突。
- Workbench 显示 Task FAILED、Policy denied、预算超限或 Trace 缺失。
- 事件证据不是 PASS，before/after 缺失或图片内容相反。
- MCP Catalog 加载失败、工具计数为空或 Schema 不可见。
- 页面出现 API Key、密码、恢复口令、完整本机目录或其他秘密。

**验收标准**

- [ ] 1080p，画面清晰，无系统弹窗、通知、私人标签页或桌面文件泄露。
- [ ] 登录入口、API 在线、实时视觉、0→1 人变化均被录到。
- [ ] Agent 任务完成，人数工具调用成功，回答与实时画面一致。
- [ ] Workbench 的路由、模型决策、工具结果、L0 策略、Trace 和预算可辨认。
- [ ] V04 的 bottle 移除事件、PASS 和 before/after 证据可辨认。
- [ ] MCP Catalog 的计数、风险/只读标记和至少一个 JSON Schema 可辨认。
- [ ] 没有执行确认事件、重启、清理、记忆写入或其他 L1/L2 写操作。
- [ ] 原片时长尽量控制在 180 秒内；操作等待过长可后期剪掉，但关键状态不能跳过。

### V06 详细录制卡：Agent Harness 多步 Skill 与全生命周期 Trace

**目标**

用一个真实只读调查任务，证明 Agent 不只是“一问一答”，而是能先选择版本固定的 Skill，再按限定工具集合执行多步调查，并把工具路由、模型决策、Hooks、工具结果、预算和终态记录在 Workbench 中。V06 不重复人员计数，也不需要人员再次入画。

**录制参数**

```text
画面：1920×1080
帧率：30 FPS（稳定 24 FPS 也可）
预计时长：90–150 秒
录制范围：浏览器窗口或 1920×1080 显示器
麦克风：关闭
系统声音：关闭
浏览器缩放：90% 或 100%，全程固定
```

**录制前准备**

1. 登录 Dashboard，确认 API 在线、模型为“在线 DeepSeek”、视觉状态为实时。
2. 确认 V04 产生的 `物品移除 / bottle` 事件仍存在；它不必是事件列表第一条，但必须是最近的 bottle 移除事件。
3. 滚动到 Vision Copilot，关闭上一任务的 Workbench 展开项，清空输入框。
4. 不清除短期会话、不写长期记忆、不确认任何事件；本次只执行 L0 调查。
5. 关闭私人浏览器标签页和通知；录制期间不要切换到终端。

**精确操作步骤**

1. **起始状态，约 5 秒**

   - 让 Vision Copilot 标题、在线 DeepSeek、Harness 评测基线 `PASS` 和空输入框同时可见。
   - 鼠标停在空白区域 2–3 秒后开始输入。

2. **输入固定调查问题，约 5 秒**

   为确保命中已经验收的版本固定 Skill，原样输入英文：

   ```text
   Who took the bottle in the most recent removal event?
   ```

   这是功能验收用自然语言，不是脚本命令。只点击一次“发送问题”。

3. **等待多步执行，约 10–30 秒**

   - 录到任务进入 QUEUED/RUNNING 的过程即可，不要重复提交。
   - 等待最终状态 `TASK COMPLETED`。
   - 如果回答如实说明证据无法确定具体人员，也属于正确结果；不要要求模型猜测身份。

4. **最终回答与工具链，约 12–20 秒**

   保持页面静止，确保能读到：

   ```text
   TASK COMPLETED
   vision.investigate_removed_item@1.0.0
   event.query · SUCCEEDED
   event.get_detail · SUCCEEDED
   evidence.verify_event · SUCCEEDED
   ```

   实际工具数量可能因当前事件上下文略有差异，但只允许上述三类 L0 工具，且所有已调用工具必须为 SUCCEEDED。

5. **Workbench 摘要，约 15 秒**

   - 展开该任务的 `HARNESS RUN`。
   - 在摘要区停留，使以下字段清楚可见：Task COMPLETED、Skill 名称及版本、工具路由、模型服务路径、步骤数、耗时、模型/工具/外部调用预算和 Token 使用量。
   - 完整 Task ID 可留在原片，最终发布版会截断；不要主动选中或复制它。

6. **生命周期 Trace，约 35–60 秒**

   缓慢向下滚动，每个关键节点停留约 2 秒，依次让观众看到：

   ```text
   SKILL_SELECTED / Skill 选择
   TOOL_ROUTE / 工具路由
   before_model Hook（FAIL_CLOSED）
   MODEL_RESILIENCE / 模型韧性
   MODEL_USAGE / 模型用量
   MODEL_DECISION / 模型决策
   before_tool Hook
   event.query 工具结果 / SUCCEEDED
   event.get_detail 工具结果 / SUCCEEDED
   evidence.verify_event 工具结果 / SUCCEEDED
   after_tool / on_checkpoint Hook
   TASK_RESULT 或任务结束 / COMPLETED
   on_task_complete Hook
   ```

   某些节点顺序会因模型的多步决定交错出现，以实际 Trace 为准；不要为了凑顺序重新提交任务。

7. **结尾，约 5 秒**

   - 回到 Workbench 摘要，或停在最后的 `COMPLETED`/`on_task_complete` 节点。
   - 鼠标移到空白处，静止 3–5 秒后停止录制。

**原始文件名与位置**

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\03_raw_videos\2026-08-12\20260812_V06_agent-harness-skill-hooks-trace_take01.mp4
```

如第一次任务因远端网络短暂失败需要重拍，不覆盖原文件，使用：

```text
20260812_V06_agent-harness-skill-hooks-trace_take02.mp4
```

**立即停止并报告的情况**

- 任务状态为 FAILED、CANCELLED 或 AWAITING_CONFIRMATION。
- 未选择 `vision.investigate_removed_item@1.0.0`，或 Skill 字段显示未触发。
- 调用了允许集合之外的工具，或者任何工具状态不是 SUCCEEDED。
- 任务要求确认、发生 L1/L2 写操作，或事件处置状态被改变。
- Workbench 没有 Skill、Hooks、Trace、预算或任务终态。
- 页面暴露 API Key、密码、恢复口令、证据绝对路径或模型原始隐藏内容。

**验收标准**

- [ ] 任务 `COMPLETED`，固定 Skill 名称、版本和多步执行可辨认。
- [ ] 至少一个、最好三个调查工具执行成功，且全部为 L0 只读。
- [ ] Workbench 摘要显示路由、步骤、耗时和执行/Token 预算。
- [ ] Trace 中可看到 Skill 选择、模型决策、工具结果、Hooks、Checkpoint 和终态。
- [ ] 回答不凭空识别具体人员，证据不足时明确说明不确定性。
- [ ] 未确认事件、未写长期记忆、未执行重启或清理。
- [ ] 视频无私人通知、秘密、绝对路径或其他页面干扰。

### V06 原片验收记录：中文多步调查与脱敏 Trace

原片：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\03_raw_videos\2026-08-12\20260812_V06_agent-harness-skill-hooks-trace_take01.mp4
```

实际规格与结果：

- 时长 `50.2` 秒，画面 `1920×1080`，约 `23.6 FPS`，文件约 `5.3 MiB`；节奏紧凑，无需为达到预估时长而重录。
- 中文问题“调查最近一次瓶子移除事件，核验证据并判断是谁拿走了瓶子。”成功命中 `vision.investigate_removed_item@1.0.0`。
- 任务 `COMPLETED · 3 steps`，路由为 `SKILL_PINNED · 3/33 · -87.7%`，无 retry、无 fallback，Circuit 为 CLOSED。
- `event.query`、`event.get_detail`、`evidence.verify_event` 三个限定 L0 本地工具全部 `SUCCEEDED`。
- 回答核验出 bottle 数量 `1 → 0`、3/3 证据有效、SHA-256 通过、前后证据完整，同时明确拒绝在无 track_id/身份信息时猜测拿走者。
- Workbench 清楚覆盖 Skill 选择、工具路由、模型韧性、模型用量、模型决策、before/after model Hooks、before/after tool Hooks、工具结果、Checkpoint、任务结束、on_task_complete 和会话记忆保存。
- 执行预算为 `3/5M · 3/8T · 0/2E · 14457/16384 tok`，步骤、耗时与预算均可辨认。
- 原片可验收，无需重录。发布前遮挡 LAN IP、完整 Task ID 和 Event ID；开头一句英文过渡可保留，也可剪掉以保持中文一致。

### P01–P04 详细截图卡：发布工程证明

发布工程展示的是终态、哈希和独立 CI 结论，静态截图比视频信息密度更高。V18 从核心必录项降为可选，README 与项目文档使用以下四张局部截图即可。

**统一截图要求**

- Jetson 终端最大化，深色主题，字号 18–22 px，宽度至少 120 列。
- 每次运行命令前先清屏；截图只保留该命令及最终摘要，不截 shell history。
- `sudo` 密码提前通过 `sudo -v` 缓存，截图中不得出现密码交互。
- 不显示环境变量、API Key、私钥、邮箱或 `/etc/edgesentinel-visionops/*.env` 内容。
- 截图保存为 PNG，不做长截图；每张只证明一个结论。

**P01：全量测试与发布边界**

依次运行：

```bash
sudo docker exec edgesentinel-visionops bash -c 'cd /workspace/edgesentinel && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q'
sudo docker exec edgesentinel-visionops bash -c 'cd /workspace/edgesentinel && bash scripts/run_repository_publication_gate.sh'
```

第二条执行结束后，调整终端窗口，使上一条测试的 `Ran ... tests / OK` 与本条 `Repository Publication Gate passed.` 同屏。如果两段不能同屏，不要缩小到看不清，拆为 `take01` 和 `take02` 两张。

原始文件名：

```text
20260812_P01_full-tests-publication-gate_take01.png
```

**P02：Release provenance 与 CycloneDX SBOM**

运行：

```bash
sudo docker exec edgesentinel-visionops bash -c 'cd /workspace/edgesentinel && bash scripts/run_release_provenance_test.sh'
```

截图必须完整包含 acceptance summary 中的：`Status: PASS`、Release ID、文件数、Manifest SHA-256、`SBOM: CycloneDX 1.7 VERIFIED`、`Source integrity: MATCH`、两个 `False` 以及最后的 smoke test passed。

原始文件名：

```text
20260812_P02_release-provenance-cyclonedx_take01.png
```

**P03：可再生 Release 产物完整性**

运行：

```bash
sudo docker exec edgesentinel-visionops bash -c 'cd /workspace/edgesentinel && bash scripts/build_release_artifacts.sh && bash scripts/check_release_integrity.sh'
```

截图必须包含构建 `status: CREATED`、Release ID、manifest/SBOM SHA-256，以及校验 `status: PASS`、`source_integrity: MATCH`、`sbom_verified: true`、`credentials_included: false`。内容超过一屏时使用两张普通截图，不使用超长图。

原始文件名：

```text
20260812_P03_release-artifacts-integrity_take01.png
```

**P04：GitHub Actions 绿色 CI**

在 PC 浏览器打开 `https://github.com/zja0011/edgesentinel-visionops/actions`，进入当前 `main` 最新提交对应的绿色 `CI` 工作流，再展开 `validate` Job。截图范围仅保留工作流标题、绿色结论、分支/提交短 SHA，以及六个绿色步骤：publication boundary、依赖安装、full unit suite、release provenance、release metadata、verified provenance upload。

不要打开账户设置、Secrets、Token 页面或完整日志；GitHub 用户头像可以保留，私人邮箱和通知必须避开。

原始文件名：

```text
20260812_P04_github-actions-ci-green_take01.png
```

以上四张统一保存到：

```text
H:\AI_learning\jetson-nano-ai-harness\pictures_and_media\edgesentinel\02_raw_screens\2026-08-12\
```

**验收标准**

- [x] P01 同时证明全量测试 OK 和 publication gate passed。已验收原片：`20260812_P01_full-tests-publication-gate_take02.png`（656 项测试通过，publication gate PASS，未显示密码提示）。
- [x] P02 明确证明 CycloneDX VERIFIED、Source integrity MATCH、无凭据和绝对路径。已验收原片：`20260812_P02_release-provenance-cyclonedx_take01.png`（Release ID `esv_0_1_0_dev_1_fae092fe8e7b8d12`）。
- [x] P03 的构建与校验 Release ID 一致且校验 PASS。已验收原片：`20260812_P03_release-artifacts-integrity_take01.png`（Release ID `esv_0_1_0_dev_1_fae092fe8e7b8d12`）。
- [x] P04 对应当前 main 提交，关键 CI 步骤全部绿色。已验收主图：`20260812_P04_github-actions-ci-green_take01.png`（Run #20、validate succeeded、关键步骤全绿）；辅助历史图：`20260812_P04b_github-actions-history_take01.png`（提交 `64fe038` 与连续 CI 记录）。
- [ ] 四张图文字清晰，没有密码、令牌、私钥、邮箱或秘密路径。

## 11. 推荐分批执行

| 批次 | 内容 | 预计时间 |
|---|---|---:|
| Batch 1 | H10 工作台同框照 + D02、D03、D06、D09、D10、D11 核心 Dashboard | 40 分钟 |
| Batch 2 | E01–E13 视觉事件闭环 | 60–90 分钟 |
| Batch 3 | D14–D30、A01–A12、M01–M04、S01–S05 | 60–90 分钟 |
| Batch 4 | O01–O08、R01–R09、P01–P05 | 60–90 分钟 |
| Batch 5 | V01、V02、V03、V06、V08；发布工程使用 P01–P04 截图 | 半天 |
| Batch 6 | 其余专项视频 | 1–2 天 |
| Batch 7 | V20 宣传片 | 1–2 小时 |

H10、D02、D03、D06、D09、D10、D11、V01、V02、V04、V06 和 P01–P04 已完成原片验收。V02 已覆盖 E01–E03 并提供 E04 的跨区动作；V04 已同时覆盖 E09 的事件详情与前后证据；发布工程核心证明截图已经齐备。

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
- [x] D09 Agent 工具调用（0 人/1 人整页原片已验收，待制作对照裁图）
- [x] D10 Agent Workbench（整页原片已覆盖完整 Workbench，待安全裁图）
- [x] D11 MCP Catalog（局部截图已验收）
- [x] E09 物品移走事件与证据（V04 清晰帧已覆盖，直接截图可选）
- [x] V04 瓶子生命周期视频（89.8 秒、1080p，完整闭环已验收）
- [x] V01 端到端演示（209.4 秒、1080p，待剪至约 150–180 秒）
- [x] V06 Agent Harness 多步 Skill 与 Trace（50.2 秒、1080p，固定 Skill 与 3 工具已验收）
- [ ] P01–P04 发布工程截图：测试/门禁、来源/SBOM、产物完整性、GitHub CI

现有硬件总览加上这些核心界面、事件和视频，就能显著提升 GitHub 首页可信度；无需用大量器材特写稀释项目重点。
