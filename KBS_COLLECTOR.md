# 小米 KBS 本地采集器 V0.1

这是独立的 **人工导航、最多 5 产品**试采集程序。它使用 Selenium 4 的可见 Chrome/Edge 窗口和 PySide6 本地控制窗口，不调用网站后台接口、不自动遍历知识库、不调用大模型。自动化测试全部使用虚构页面；现场已完成平板电脑、生活电器、穿戴设备、日用百货各一个样本的本地保存，并验证技术详情、FAQ 和视频链接入口。**人工完整性、品牌与准确型号验收尚未完成，实际资料全部待审核。**

## 安装和启动

在仓库目录的 PowerShell 中执行，无需激活虚拟环境：

```powershell
# 已有小鲸环境只需安装这一组可选依赖
.\.venv\Scripts\python.exe -m pip install -r requirements-kbs.txt

# 先运行虚构演示，不访问小米知识库
.\.venv\Scripts\python.exe -m kbs_collector.main --demo --browser chrome

# 真实站点：默认可见 Chrome，首次人工输入账号及验证信息
.\.venv\Scripts\python.exe -m kbs_collector.main --browser chrome
# 可改为 --browser edge，但两个浏览器的登录配置独立

# 打开本轮四类试采资料；可直接“预览已采集文章”，无需先打开浏览器
.\.venv\Scripts\python.exe -m kbs_collector.main --collection pilot_four_categories --browser chrome
```

新机器先按主 README 创建 Python 3.11+ 环境并安装主应用依赖。实际开发验证为 Windows、Python 3.13.15、Selenium 4.52.0；没有单独验证 Python 3.11。Selenium 支持依赖范围见 `requirements-kbs.txt`；本机实际可复现版本及间接依赖见 `requirements-kbs-lock.txt`。

浏览器必须已安装。默认由 Selenium Manager 查找或下载匹配的官方驱动，缓存放在 Git 忽略的 `data/kbs_import/driver_cache/`，禁止 Manager 使用统计。企业网络不能下载驱动时，由管理员从浏览器厂商的官方来源提供版本匹配的驱动，再执行：

```powershell
.\.venv\Scripts\python.exe -m kbs_collector.main --browser edge --driver 'C:\Tools\msedgedriver.exe'
```

没有 `--headless` 开关，底层明确使用 `headless=False` 并拒绝 True。按用户 2026-11-05 的要求，**使用普通浏览模式，取消无痕/InPrivate，保留独立的浏览器配置目录**：Chrome 为 `data/kbs_import/browser_profiles/chrome/kbs/`，Edge 为 `data/kbs_import/browser_profiles/edge/kbs/`。正常关闭、启动失败和下次对话重新启动均不会删除该目录；浏览器自行保存和复用 Cookie，并启用其会话恢复设置。演示使用单独的 `demo/` 配置，浏览器测试使用独立测试目录。

旧无痕会话不能自动转换为持久登录，本程序不会复制其认证数据。首次使用新的普通模式须手动登录一次；以后继续选择同一浏览器、同一 Windows 用户和同一目录。站点可能使登录过期或要求重新验证，不能保证永不重新登录。一个配置目录同时只供一个浏览器进程使用；提示配置占用时使用已有窗口或正常关闭后重试，程序不删除锁文件、不强制结束浏览器。

浏览器配置包含敏感登录数据，已随 `data/` 被 Git 忽略，不要上传公开仓库或分享。采集代码不读取、序列化、输出、迁移或另行导出 Cookie/Token，也不附着日常浏览器的普通用户配置或记录网络日志。此前“临时隐私会话”的实现已由此明确要求替代。

## 第一轮操作流程

1. 点击 **1 打开浏览器**。在浏览器中自己登录、完成验证，人工确认公司授权、站点条款及访问规则允许这种操作，再勾选控制窗口的两项确认。若规则不允许自动采集，不勾选、不继续。
2. 人工进入获准的产品百科/栏目页面，点击 **2 检查当前结构**。程序只读检查主文档和可见嵌套 iframe，结果保存在本地 `structure.json`，并在本地预览显示 iframe 路径、实际根节点选择器、标题、表格/链接/列表/标签页数量。不会在终端打印页面内容。
3. 根据实际页面人工查找指定产品并打开；每次页面或 SPA 路由变化后重新检查。下拉框选择实际 iframe 和正文根节点；可以输入从本地浏览器开发者工具只读检查得到的 CSS 选择器。必须唯一匹配可见正文，拒绝 html/body、表单和导航区。大型详情页可填写已观察到的正文选择器，点击“检查指定正文结构”，避免扫描无关区域。真实选择器均在只读检查之后适配。
4. 点击 **3 读取选区并预览**。在本地预览核对章节、编号、表格、FAQ、标题、来源地址和更新时间。按原文填品牌、名称、类别及准确型号；在“型号证据”填选区正文中含完整型号的一句原文。比如虚构演示的 `型号： DEMO-CAM-A`。型号不明确可以留空保存，但会标为 `MODEL_UNCONFIRMED`，不能导入商品。
5. 核对预览属于授权产品资料，不含客户、账号或经营信息；勾选确认，点击 **4 保存待审核**。保存为 `pending_review`，不会宣称官方已验证。相同选区内容重复保存记为 skipped；不同内容保留新版本，同型号相关版本进入冲突复核队列。
6. 人工切换产品页内 FAQ/说明书/视频标签、展开折叠章节、翻页，等待加载后重复检查及读取。浏览器新标签页用“刷新标签页数量/切换选中标签页”。局部滚动可手动操作，或填实际滚动容器 CSS 后按一次滚动。程序不自动点击分页、播放视频、附件或导航链接。
7. 先处理 3–5 个不同品类，查看 `crawl_manifest.json` 的成功、失败尝试、重复跳过、待审核数及任务状态。本轮最多 5 个明确型号（缺型号时按名称计数），最多 100 个资料版本。批量采集开关没有开放。

**完整性说明**：读取的是当前已加载且可见的 DOM。程序不会声称一次读取覆盖整产品。隐藏标签、虚拟列表、折叠章节、画布内容、图片说明、未加载分页需逐个打开核对；图片不 OCR、不抓屏。独立文章/页签逐条保留，不合并猜测型号。稳定检测只代表选区连续 1.5 秒未变化，不保证网站已经加载全部资料；发现后到内容应再读取。单次 DOM 等待 15 秒，陈旧 iframe 最多重试一次，无自动刷新。

演示页面提供摄像头、清洁设备和耳机三类，名称和型号均为虚构。默认进入两层 iframe 中的摄像头。可以在 iframe 的导航链接中切换另外两类；随页面原文修改品牌、名称、型号证据。演示数据隔离于 `data/kbs_import/demo/`，不允许导入真实商品。

## 输出与恢复

所有实际采集资料、结构报告、索引、浏览器配置及驱动缓存位于已被 `.gitignore` 忽略的 `data/` 内。不要复制到源码目录、粘贴到 Codex 对话或提交到公开仓库。没有自动正文日志、截图、页面源码转储或独立 Cookie/Token 导出文件；浏览器自身的登录数据仅留在专用本地配置目录。

本轮现场资料位于 `data/kbs_import/pilot_four_categories/`。`pilot_report.md` 是含本地型号和来源的核对清单；`pilot_report.json` 仅含统计，`latest_articles.jsonl` 为每个已选页面/正文范围的最新版本。原始 `articles.jsonl` 保留历史版本。导入前优先核对最新版本，旧版不会自动覆盖。索引失败数只统计已入队任务，不代表现场所有结构适配尝试都成功。

| 文件 | 内容 |
|---|---|
| `products.jsonl` | 原文品牌/名称/准确型号/型号证据/类别、pending_review |
| `articles.jsonl` | 标题、来源 URL、frame URL/路径、原文块、章节路径、表格单元格及跨行跨列、编号步骤及嵌套深度、页面显示日期、采集 UTC 时间、哈希 |
| `faq.jsonl` | 明确 Q/A 或 dt/dd 的问题与回答，附章节、原始型号、来源 |
| `videos.jsonl` | 页面明确标识的视频链接标题、原始 URL、页面用途文字、适用型号；默认未验证、不可对客分享 |
| `review_queue.jsonl` | 每篇文章及不确定/关联版本/潜在冲突/缺失 FAQ 等审核原因 |
| `crawl_manifest.json` | 成功、失败尝试、跳过、待审核统计、任务 ID/状态及各导出文件摘要 |
| `index.sqlite3` | 权威采集索引、不可覆盖的内容版本、任务及事件；JSONL 可从此重建 |
| `structure.json` | 最近一次人工触发的只读结构检查 |
| `markdown/*.md` | 本地可读副本，供人工核查；不作为可执行 HTML 使用 |

文本只做结构化，不生成维修建议或产品事实。FAQ 不符合明确格式时保留正文并提示人工核对，不编造问答。视频仅识别页面中明确标注视频的可见 `<a href>`；iframe 播放器、blob、无公开链接的按钮不猜 URL。附件只记链接、不下载。含认证参数、登录跳转、非 HTTPS 的真实链接被拒绝保存，不改写参数后继续使用。这个检查是保守规则；不能把它当成公司资料的自动脱敏审查。

现场视频卡片另使用正常的“复制链接”按钮取得 URL：`clipboard_link.py` 先记录剪贴板序号，点击后只读取新写入的链接，不读取、保存或恢复先前剪贴板内容；短暂操作期间不要另行复制内容。链接参数原样保留，认证链接拒绝保存。没有复制按钮的卡片列入 `video_candidates.jsonl`，不播放视频、猜地址或访问后台接口。视频适用型号、官方性及分享权限仍须人工审核。

页面标注为内部的备注保留在本地原件，Markdown 明确提示仅供操作员核对；它们不进入 FAQ 答案或小鲸知识片段，内部视频也不导入客户候选视频。准确页面、名称和品类一致时补充明确型号不会重复计为新产品；不同的非空型号不会合并。

异常/关机后重新启动，运行中的任务恢复为 pending。选择“失败 / 中断任务 → 载入恢复信息”，从本地预览核对原 iframe 和选择器，复制恢复地址到已经人工登录的浏览器，重新检查、读取和保存。不会从文件恢复认证会话。索引提交与内容保存同事务完成；导出崩溃后启动或“重新生成本地报告”可重建 JSONL。manifest 最后替换；外部工具需要多文件一致视图时应核对摘要或直接读取 SQLite。失败统计是历史尝试数，成功重试不会删除历史失败。

验证码、访问限制或禁止采集文字出现时暂停并清除授权/登录确认，**不会自动重试或绕过**。保守检测可能误报，不能为绕过限制而关闭检查。若网站禁止自动化，请使用站点自带且获准的导出功能，或向资料负责人索取获准的说明书/FAQ 文件，在现有“知识库与视频”中手工导入；不存在获准导出时停止采集，不用浏览器打印/抓包规避权限。

## 导入小鲸并人工审核

1. 在小鲸“知识库与视频 → 商品与型号”建立准确品牌、硬件型号和真实 SKU。采集器不会根据相似名称自动新建或覆盖商品。
2. 采集窗口点击“刷新本地待导入列表”，选择文章与现有 SKU，核对后勾选“追加导入”，再点击导入。品牌和型号须完全一致，型号证据必须出现在原文；不符合时阻止导入。每篇文章/商品组合幂等导入。
3. 资料追加为 `internal_faq`、`pending`（这是现有系统对 staging 的 `pending_review` 的状态映射），保留来源 URL、本地原件、章节/步骤、原始型号及采集时间。型号、原文出处和官方性仍需人工审核。视频候选为 `pending / unknown / customer_shareable=false`，不自动核实其官方性或可分享性。
4. 在小鲸知识库界面逐项审核批准；版本冲突人工选择并弃用旧版。视频必须另行核对官方出处、链接有效性、准确型号及可向客户分享权限，满足原有全部门槛后才能推荐。采集区导出状态始终保持待审核，应用内审核结论独立维护。
5. 使用 `.\.venv\Scripts\python.exe -m app.main` 启动小鲸。批准后的内部资料用于本地检索和待审核草稿。小鲸已按用户要求固定离线运行，在线客户端及配置入口已移除。来源和视频继续保留 `local_only=1` 追踪内部属性；编辑视频不能清除此标记。

首个真实商品可用 `python -m app.main --first-product` 打开本地核对流程：填写品牌与店铺 SKU → 追加为待审核 → 亲自审核 → 离线验证。品牌缺失时记录人工依据，不改写采集原件，不推断缺失型号。具体操作见主 README。

数据库是加法迁移：给来源和视频增加 `local_only`，增加导入来源映射表，不删除旧表、不覆盖已有资料或审核状态。现有普通公开知识仍按原规则处理。先关闭程序并备份整个 `data/` 再迁移到其他机器。

## 测试

```powershell
# 纯虚构单元/Qt offscreen/应用回归；专用临时目录避免旧系统临时目录 ACL 冲突
.\.venv\Scripts\python.exe -m pytest -q -m 'not browser' -p no:cacheprovider --basetemp=test-results/kbs-local-tests

# 明确开启真实可见 Chrome，访问 127.0.0.1 的虚构页面，不访问小米
$env:KBS_HEADED_TEST='1'
$env:KBS_TEST_BROWSER='chrome'
.\.venv\Scripts\python.exe -m pytest -q tests/test_kbs_browser.py -p no:cacheprovider --basetemp=test-results/kbs-headed-tests
Remove-Item Env:KBS_HEADED_TEST

# 可见 Windows 控制窗口 + Chrome 的纯虚构端到端检查
.\.venv\Scripts\python.exe scripts/kbs_native_smoke.py
```

`--basetemp` 是 pytest 专用且会清空的临时目录，不要指定含有需要保留资料的目录。浏览器测试可通过 `KBS_TEST_DRIVER` 指定本地官方驱动。开发执行结果见 `KBS_TEST_REPORT.md`。

## 本轮范围与工程决策

- 现场只读检查已观察到产品百科 iframe 中的 `.section-header` 与 `ul.spec-list` 结构，提取器增加了对应章节、字段和问答适配；回归测试仍使用完全虚构的页面，不把真实正文放入测试或报告。当前授权范围限定为平板电脑、生活电器、穿戴设备、日用百货，范围配置仅存本地 `data/kbs_import/category_scope.json`。

- 真实 DOM 已经现场检查：百科参数使用 `.spec-label/.spec-value`，复制工具栏 `.value-tools` 排除；技术详情通过独立 `.tree-editor-container` 读取知识单元，排除评论、人员信息、标签和浮动操作栏。网页更新后仍应重新检查，不把这些选择器当作永久接口。
- 第一轮优先实现有头登录、结构检查、结构化保存和审核导入闭环。按名称/型号/品类的无人值守查询、自动翻页、SKU 清单批采和全站采集延期到真实单产品验证通过后，不以自动试探来补猜 DOM。
- 2026-11-06 用户进一步取消全部在线模型功能；小鲸客服回复完全离线，`local_only` 继续标记内部来源。
- 任何未审核或不明确的链接留待人工确认；不以页面出现在小米域名就宣称官方已验证。
- 官方实现参考：[Selenium Chrome 选项](https://www.selenium.dev/documentation/webdriver/browsers/chrome/)、[显式等待](https://www.selenium.dev/documentation/webdriver/waits/)、[iframe 切换](https://www.selenium.dev/documentation/webdriver/interactions/frames/)。
