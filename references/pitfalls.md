# 已知坑清单

每条格式：**NEVER … / 原因 / 正确做法**。前两条借自 `occupation-analysis` 技能，其余为研制过程中所付代价的记录。

---

## 1. NEVER 用名称字符串匹配对应中国职业与 O*NET 职业

**原因**：不同分类体系的命名差异极大——"汽车维修工" ≠ "Motor Vehicle Mechanic"。任何基于名称的匹配都会系统性地错，而且错得不容易被发现。

**正确做法**：语义推断。以"职业面向 + 主要专业能力要求 + 职业类证书"为输入，由 agent 判断；用 `onet_index.py --show` 把 O*NET 指标展示给使用者复核。

*（出处：`occupation-analysis` 技能 NEVER 清单）*

## 2. NEVER 在用户确认映射前进入打分环节

**原因**：映射错了，后面全部工作都白做——而且是**看起来做完了**的那种白做，最危险。

**正确做法**：步骤 2 用 `AskUserQuestion` 展示确认面板并**等待回复**。即使使用者说"全流程跑一遍"，这一步也不能省。

*（出处：`occupation-analysis` 技能 NEVER 清单）*

## 3. NEVER 让分类轴的 `levels` 顺序与刻度标签顺序不一致

**原因**：研制过程中 2026-09-28 实际发生过——`LEVELS = [0.80, 0.55, 0.20]` 配 `xticklabels(['0.20','0.55','0.80'])`，导致 `LEVELS.index(0.20) = 2` 落在标签"0.80"的位置上，**两轴整体反向**。图看起来"很正常"，只是全错了。

**正确做法**：`render.py` 已内置 `quad_counts()`，按分数反推象限后与任务表的 `quad` 字段交叉核对，不一致就报错退出。**改绘图代码后必须跑 `_selftest_render.py`。**

## 4. NEVER 重排已分配的任务编号

**原因**：使用者会跨多轮填写复核清单。2026-09-27 曾因把复核清单 E 区从 49 条重编号为 37 条，导致使用者第二轮用旧编号、第三轮用新编号，**同一批编号在两种基准下指向完全不同的条目**，只能回问使用者才敢落笔。

**正确做法**：编号一次分配、永久冻结；已判定条目保留编号、留空位；清单里同时给出「编号」与「轮次前缀」。

## 5. NEVER 在 YAML frontmatter 的 `title` 里保留 ASCII 冒号+空格

**原因**：`title: Generative AI and Jobs: A Refined…` 会让 YAML 解析失败，而且**症状是连环的**——同时报 `mapping values are not allowed here`、`缺少 id 字段`、`缺少 title 字段`，还连带让检查工具报"索引登记了但无对应页"（因为 id 根本没读出来）。看到"缺 id"要先怀疑语法，而不是真的缺字段。

**正确做法**：整体加引号：`title: "Generative AI and Jobs: A Refined…"`。

## 6. NEVER 用相对路径在 HTML 里引图

**原因**：内置预览宿主只提供单个 HTML 文件，相对路径会 404。本方法的图谱页（D3 渲染的 HTML）已踩过。

**正确做法**：base64 内嵌。代价是文件变大（四张图约 1 MB），但保证断网打开与预览都能显示。

## 7. NEVER 让规则法把"待定"条目排除出均值

**原因**：会**系统性压低**条目拆解质量差的专业。真实实例：休闲农业生产与经营 8 条任务中有 4 条未命中关键词被排除，专业层均值因此只有 0.34；而 O*NET 中该专业对应职业的感知—操作负担指数居 896 个职业的 **99.8 百分位**。这不是判断分歧，是测量缺陷。

**正确做法**：待定单列、逐条消化，不参与均值；清单里明确标出。

## 8. NEVER 对复合能力条目整体判定

**原因**：一条能力内部可能含方向相反的任务。真实实例：服装设计与工艺的"绘制款式图、纸样制作、放版排料"一条，前段落 Ⅲ（仅生成式 AI 高）、后段落 Ⅰ（仅自动化高）；整体判定无论给哪个象限都是错的。

**正确做法**：规则 R1b——先拆后判。`build_tasks.py` 会给出 `split_hint` 标记（拆分后仍跨类型）与 `n_parts`（并列段数，**≥3 提示疑似复合**）两个信号，复核清单两列都列出，交人工扫读。

## 9. NEVER 把纵轴窄化为"工业机器人"

**原因**：规则化业务系统（离港系统、票务系统、单证处理）的风险会被误判为低暴露。真实实例：航空服务 4/5 条任务落双高象限，但其乘务员岗位的自动化可及性仅处 33.4 百分位——**风险来自业务系统而非设备**。

**正确做法**：纵轴称"自动化替代"，并在方法与报告中说明其 `manual` / `routine_cog` 双成分。

## 10. NEVER 在专业层均值上作图（对照图除外）

**原因**：本方法的核心主张是"专业层的单一分数会掩盖专业内部的任务异质性"。若图示落在专业层，等于在图上复现所批评的做法——审稿人或读者会立刻抓住这个自相矛盾。

**正确做法**：图一律在任务层展开。唯一的例外是"专业层 vs 任务层对照图"，它的作用恰恰是展示专业层丢掉了什么。

## 11. NEVER 假设 matplotlib 一定能显示中文

**原因**：缺字体时中文渲染为方框，而图看起来仍然"生成成功"。

**正确做法**：`render.py` 已用候选字体列表（Microsoft YaHei → SimHei → PingFang SC → Noto Sans CJK SC → …）并打印警告。看到警告就装字体，不要将就。

## 12. NEVER 把 pip 的 `[safe-delete][SAFE_DELETE_FAIL_CLOSED]` 当作安装失败

**原因**：那是沙箱拦截 pip 的**缓存清理**，与安装结果无关。2026-09-29 实测：安装 matplotlib 时刷出一屏该报错，但 `import matplotlib` 正常。

**正确做法**：回读确认——`python -c "import matplotlib; print(matplotlib.__version__)"`。

## 13. NEVER 用 Git Bash 的 `/tmp` 在 shell 与 Windows Python 之间传文件

**原因**：Git Bash 的 `/tmp` 映射到 Windows 临时目录，而 Windows 版 Python 不认 `/tmp/x.json` 这个路径——`curl -o /tmp/x.json` 写出的文件，Python 读不到。

**正确做法**：跨 shell／解释器传文件一律用 Windows 绝对路径（如 `E:/tmp/xxx/`）。

## 14. NEVER 依赖 `raw.githubusercontent.com` 取 GitHub 文件

**原因**：本机实测该域名 DNS 不可达（`os error 11001`），走代理与 `--noproxy '*'` 都失败。

**正确做法**：用 `git clone --depth 1 https://github.com/<owner>/<repo>.git`（github.com 稳定可用），或用 `https://api.github.com/repos/<owner>/<repo>/contents/<path>` 取单文件。

## 15. NEVER 用「分隔符两侧是否都含任务词」作为拆分的唯一判据

**原因**：中文能力条目里，并列结构的**末段**往往是前段的补足语而非独立任务。2026-09-29 在 10 个专业 83 条能力条目的真实数据上实测：旧判据切出 **90 条任务**，其中大量是残片——

| 原条目 | 旧规则切出的残片 |
|---|---|
| 具备汽车发动机总成及其零部件拆装、检测与更换的能力 | `检测与更换的能力` |
| 具有物联网产品装配、焊接、检测与调试的能力 | `检测与调试的能力` |
| 具有使用常用工量具、机械识图、拆装调试机械的能力 | `拆装调试机械的能力` |
| 具有旅游景区、旅游电子商务、旅行社、定制旅行、导游、酒店服务的能力 | `酒店服务的能力` |

这些残片**不是一个可独立判定的任务**，却会一路带进复核清单和最终报告。旧判据失效的原因：`检测与更换的能力` 里含「更换」「调试」等任务词，于是被当成"完整动宾结构"。

**正确做法**：改用 R1a 三条判据（完整表述 + 长度足够 + **类型与缓冲段不同**），切出 **64 条**，与人工核定的 69 条同一量级。判据实现见 `build_tasks.py::split_item`，单元断言见 `_selftest_build_tasks.py::test_split_rules`。**改这里之前先跑自检。**

## 16. NEVER 把需要受控取值的填报表做成 csv

**原因**：`.csv` 是纯文本，**没有任何"数据有效性"的概念**——下拉列表是 Excel 工作簿（`.xlsx`）的特性，不是文本格式能承载的。把判定列交给教研组手打，就会出现 `0.2`（应为 `0.20`）、`0.20 `（尾随空格）、`Ⅲ仅LLM高`（漏空格）这类不一致；读回时要么报错，要么静默写进任务表，把污染带到最终报告里。

**正确做法**：填报表出 `.xlsx`，判定列挂列表型数据有效性（`type="list"`）并设 `showErrorMessage="1"` + `errorStyle="stop"`，把表外取值直接拦下。**csv 默认不再产出**——留着只会让人以为有两条填写渠道；确需扁平文本时用 `--out-csv` 显式导出，且只作其它系统的导入源，**不要交给教研组填**。实现见 `build_review_sheet.py::write_xlsx`。

## 17. NEVER 在手写 xlsx 的 `<f>` 里带前导等号，也别把 `showDropDown` 填 1

**原因**：两个反直觉的 OOXML 细节：

| 写法 | 后果 |
|---|---|
| `<f>=IF(A1="","",A1)</f>` | Excel 视为公式文本 `=IF(…)`，openpyxl 回读变成 `==IF(…)`；**`<f>` 内本来就不写等号**，等号是 Excel 的输入约定 |
| `showDropDown="1"` | 该属性名与含义**相反**——`1` 表示"隐藏下拉箭头"，要显示箭头必须写 `showDropDown="0"` |

另外公式里的 `>=` 必须 XML 转义成 `&gt;=`；工作表内元素次序为 `sheetPr / dimension / sheetViews / sheetFormatPr / cols / sheetData / dataValidations`，顺序错了 Excel 会提示"需要修复"。

**正确做法**：直接用现成的 `scripts/xlsx_min.py`（纯标准库），它已处理上述三点与样式索引；改它之后**必须**跑 `_selftest_review_sheet.py`（含 `<f>="` 出现即失败的断言、以及用 openpyxl 回读的闭环测试）。

### 交付前怎么确认"Excel 真能打开"（2026-09-29 实测通过的完整做法）

自研 XML 最怕的是"openpyxl 读得动、Excel 却提示需要修复"。三级验证，从弱到强：

| 级别 | 做法 | 能证明什么 |
|---|---|---|
| ① 结构 | 解压看部件齐全、元素次序、`<f>` 无前导等号 | 结构没写错 |
| ② 回读 | `openpyxl.load_workbook()` 读工作表/样式/冻结/`dataValidations` | 主流解析器认它 |
| ③ **引擎往返** | 让本机办公引擎**打开并另存**，再看下拉是否还在 | **引擎真的理解了下拉**——不理解的引擎保存时会把 `dataValidation` 丢掉 |

③ 的做法：用本机 Excel/WPS 打开该 xlsx → 另存 → 用 openpyxl 复查 `xl/worksheets/sheetN.xml` 里的
`<dataValidation sqref="…"><formula1>…</formula1>`。**sqref 与选项列表原样保留 = 通过。**

**本机（Windows + WorkBuddy）实测的可行与不可行路径**：

| 路径 | 结果 |
|---|---|
| `New-Object -ComObject Excel.Application` / `Ket.Application` | ✗ 沙箱按命令文本拦 `New-Object -ComObject`；即使关沙箱，Excel 也报 `CO_E_SERVER_EXEC_FAILURE (0x80080005)` |
| `wpscli.exe` | ✗ 拒绝运行：`parent process signature verification failed`（只允许被签名 WPS 进程拉起） |
| **WorkBuddy 本地编辑器通道**（`tencent-local-office-edit` 的 `edsdk.py`） | ✓ **可用**：`open_file … wait=true` 成功即"引擎解析通过"；`save_file` 后下拉原样保留。宿主机 `.xlsx` 默认程序是 `ET.Xlsx.6`（WPS 表格），所以这等于 WPS 引擎验证 |

**旁证**：引擎的 `sheet_get_used_range` 会把**数据验证范围计入"已使用区域"**。本技能的两张待填表
内容只到第 1 行，却报出 42 行 / 32 行——恰好等于给下拉设的范围末行（`H2:H42`、`H2:H32`），
可作为"下拉确实在位"的独立交叉验证。
