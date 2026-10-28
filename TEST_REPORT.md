# 实际测试报告

测试环境：Windows 11 `10.0.26300`，Python 3.13.15 x64，PySide6 6.12.0，RapidOCR 3.10.0，onnxruntime 1.31.1。源码和测试均在 `D:\UserData\Desktop\ZLS\pdd`。没有真实 PDD 客户数据、真实产品资料或 API Key。

## 结果

| 范围 | 实际执行 | 结果 |
|---|---|---|
| M0 / M1 基础 | `tests/test_foundation.py tests/test_ocr.py` | 10 passed；初始化、配置、主窗口构造、坐标/DPI 换算、OCR 适配与过期任务 |
| M1 真实本地 OCR | `tests/test_local_ocr.py` | 2 passed；合成中文截图实际识别、空白图错误恢复，禁止网络连接 |
| M2 业务首轮 | `tests/test_knowledge.py tests/test_videos.py tests/test_draft.py` | 首轮 47 passed；随后增加了意图区分测试 |
| M3 API / 隐私 / Qt 首轮 | `tests/test_llm.py tests/test_privacy.py tests/test_ui.py` | 首轮 26 passed；随后增加了 3 项输出门控测试 |
| 最终全套 | `python -m pytest -q --junitxml=test-results/pytest.xml` | **89 passed，0 failed，0 skipped，6.37 秒** |
| Windows 原生窗口演示 | `python scripts/native_smoke.py` | `platform=windows, ok=true`；实际本地 OCR 得到 5 行，生成 Mock 草稿；本次 2.13 秒 |
| 渲染人工检查 | 查看 `test-results/native-demo-window.png` | 检查了中文文本、OCR 行、来源、草稿、审核按钮；修复小屏拥挤后复查 |
| 正式入口启动 | `python -m app.main --smoke`（Qt offscreen） | 退出码 0，无 Key 启动成功 |
| 安装一致性 / 编译 | `python -m pip check`；`python -m compileall -q app scripts tests` | 无依赖冲突；退出码 0 |
| 可选 PowerShell 启动器 | `./run.ps1 -Smoke` | 被本机执行策略阻止，未修改策略；已用直接 Python 命令验证启动 |
| 真正服务商 API | 未运行 | 无真实 Key；只使用 httpx MockTransport 验证请求与响应边界 |
| 真实 PDD / 多屏混合缩放 | 未运行 | 需要用户在获授权的真实聊天区域现场验证 |

上述耗时仅是本机合成测试记录，不是客服场景性能承诺。Qt 自动化默认 offscreen；原生检查另用 Windows 平台插件，不能等同真实 PDD 端到端试运行。原生检查只渲染并导出本程序自己的虚构测试界面，没有截取桌面或其他应用。

测试过程中实际发现并修复：商品表插入占位符数量错误、演示资料文件名错误、演示初始化不完整时恢复、视频意图只按品类判断导致误匹配、原生窗口小屏拥挤。新增无依据功能描述、裸域名与拆机步骤门控后重新运行全套。

## 原需求测试矩阵对应

| 需求 | 自动化覆盖 / 真实边界 |
|---|---|
| T01 / T25 无 Key、关闭在线、零模型请求 | `test_mock_disabled_has_zero_network`；`test_full_offline_ui_review_copy_and_edits` |
| T02 空截图 / OCR 空值 | `test_empty_region_and_persistence`、`test_empty_ocr_is_recoverable`、真实 `test_real_blank_image` |
| T03 OCR 纠错、角色未知、必须确认 | OCR 适配与真实识别断言 `speaker=unknown`；Qt 编辑/确认按钮测试 |
| T04 无型号 | `test_deterministic_risk_rules`，只追问准确型号 |
| T05 / T11 相似型号不串用 | 精确商品检索、SKU/别名歧义、错误型号视频测试 |
| T06 来源与页码 | 四种格式实际解析；PDF 第 1 页、原件存在、章节与 source_id 断言 |
| T07 pending / demo 不作为真实事实 | `test_demo_isolation_and_never_approved`；审核撤回过滤 |
| T08 扫描 PDF | 空白 PDF 触发明确的扫描页处理提示；不实现逐页 OCR |
| T09 合格视频加入回复 | 核验原始 URL（含 query）进入草稿；人工移除不影响复制 |
| T10 / T12 未审核、失效、未知可访问性 | 全部门槛过滤及复制时重新校验；**未执行真实链接联网探测** |
| T13 / T14 / T15 赔偿、危险电池、提示注入 | 确定性 R2/R3、停止使用、人工处理、无金额承诺；注入资料不检索 |
| T16 已尝试步骤 | 包内历史样例；本地模板不把换线作为唯一重复建议 |
| T17 / T18 / T19 会话、编辑、无关截屏变化 | 会话清空、指纹与过期复制测试；capture_id 不纳入内容指纹 |
| T20 虚构视频/知识 ID | pydantic 及本次候选子集验证，非法结果拒绝 |
| T21 桌宠混入客户回复 | 模型及人工编辑复制门控 |
| T22 脱敏 / 无原文持久化 | 手机、订单、姓名标签、地址、邮箱以及实际 payload 检查；SQLite dump 不含客户问题 |
| T23 超时 / 非 JSON | MockTransport 实际走 HTTP 客户端、JSON 校验与本地回退，单次请求 |
| T24 审核复制 | Qt 点击操作检验剪贴板内容、编辑撤销审核、问题变化禁止复制；代码无 PDD 发送接口 |
| T26 未授权政策承诺 | R2 本地保守模板、经营承诺拦截、SOP 生效/失效测试 |
| T27 视频未解析 | 不描述视频时点/内容的输出校验；项目没有视频下载/解析服务 |
| T28 损坏文件 | 破损 PDF、扫描 PDF 及文档错误处理，不静默导入 |
| T29 迟到结果 | Qt 新会话丢弃旧任务、连续请求只保留最新请求的结果 |
| T30 example.com | 拒绝批准占位域名；demo URL 不进入草稿 |

## 尚待实机或业务验证

1. 用户主动在真实 PDD 窗口拖框、截图权限、重选、最小化/遮挡，以及 100% / 125% / 150% 混合 DPI 和负坐标多屏。已测试的是坐标转换函数，未实测这些硬件组合。
2. 真实聊天中的长段落、emoji、不同气泡、截图清晰度和型号 OCR 准确率。当前真实 OCR 验证仅用合成中文素材。
3. 系统剪贴板与真实 PDD 粘贴适配。Qt offscreen 剪贴板通过；未向 PDD 粘贴或发送。
4. 用户实际 API 服务的 HTTPS 地址、模型名、JSON 输出兼容性、时延、费用与数据许可。当前仅模拟 HTTP 响应。
5. 经许可的 10–20 款真实商品说明书、FAQ、现行 SOP 与人工核实视频。没有真实资料，不报告真实业务正确率或效率提升。
6. 干净 Windows 10、Python 3.11 与不同显卡/安全软件的安装及运行兼容性。

## 未实现项

M4 商品 CSV/Excel 批导、官方白名单说明书发现/下载、在线链接探测、资料版本冲突比对；扫描 PDF 逐页 OCR；全局快捷键和多会话自动监听；打包为独立 EXE。均未作为已完成项目报告。自动发送、私有接口和视频理解不在本版本范围内。
