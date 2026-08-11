# EdgeSentinel 全功能素材拍摄清单

本清单用于制作 GitHub README、作品集、答辩演示和发布视频所需的真实性素材。目标不仅是证明“能运行”，还要证明硬件、视觉流水线、Agent Harness、MCP、安全治理、运维恢复和发布工程均真实可用。

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

硬件不是项目展示重点，一张清晰的系统总览即可完成真实性证明。现有 H01 已满足最低发布要求；如果以后想升级封面，只需补拍一张同时包含 PC Dashboard 和 Jetson 实物的 H10，不需要逐个拍摄所有模块。

| 编号 | 公开文件名 | 必须拍到 | 验收标准 |
|---|---|---|---|
| H01 | `hardware/rig-overview.jpg` | Jetson、风扇、摄像头、Wi‑Fi、显示器 | **必需，已有**；README 首图 |
| H10 | `hardware/pc-jetson-workstation.jpg` | PC Dashboard、Jetson、显示器、摄像头完整工作台 | **可选升级**；一张图解释 PC 远程运维 + Jetson 边缘推理 |

不再要求 Jetson、摄像头、网卡、键鼠、电源和存储介质的独立近照。录制 V01 或 V20 时，可顺手拍一段 5–10 秒横向硬件 B-roll，无需单独组织硬件拍摄批次。

## 6. Dashboard 核心截图

最终文件放 `docs/media/dashboard/`。

| 编号 | 公开文件名 | 操作/问题 | 必须显示 | 标记 |
|---|---|---|---|---|
| D01 | `dashboard/01-login.png` | 打开 `/dashboard` | HTTPS 登录页、空密码框 | SEC |
| D02 | `dashboard/02-overview-live.png` | 登录后总览 | 实时画面、运行状态、模型模式、最新帧 | L0 |
| D03 | `dashboard/03-live-person-detection.png` | 一人进入画面 | 人员框、数量、非陈旧帧 | PHY/L0 |
| D04 | `dashboard/04-live-object-detection.png` | 放两个瓶子和一个盒子 | 类别、检测框、对象计数 | PHY/L0 |
| D05 | `dashboard/05-device-health.png` | 打开设备状态 | 负载、温度、内存、磁盘、摄像头 | L0 |
| D06 | `dashboard/06-event-center.png` | 打开事件中心 | 类型、严重度、处置状态、筛选 | L0 |
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
| Batch 1 | D02、D03、D06、D09、D10、D11 核心 Dashboard | 30 分钟 |
| Batch 2 | E01–E13 视觉事件闭环 | 60–90 分钟 |
| Batch 3 | D14–D30、A01–A12、M01–M04、S01–S05 | 60–90 分钟 |
| Batch 4 | O01–O08、R01–R09、P01–P05 | 60–90 分钟 |
| Batch 5 | V01、V02、V03、V06、V08、V18 | 半天 |
| Batch 6 | 其余专项视频 | 1–2 天 |
| Batch 7 | V20 宣传片 | 1–2 小时 |

现有 H01 已完成硬件证明。下一批最值得拍的是 D02/D03/D06/D09/D10/D11、E09、V01/V06/V18；如有合适机会再补 H10，不必专门安排。

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
- [ ] D02 Dashboard 总览
- [ ] D03 人员检测
- [ ] D06 事件中心
- [ ] D09 Agent 工具调用
- [ ] D10 Agent Workbench
- [ ] D11 MCP Catalog
- [ ] E09 物品移走事件与证据
- [ ] V01 端到端演示

现有硬件总览加上这些核心界面、事件和视频，就能显著提升 GitHub 首页可信度；无需用大量器材特写稀释项目重点。
