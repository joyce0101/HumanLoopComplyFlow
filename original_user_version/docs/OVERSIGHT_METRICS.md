# 监督质量指标与接口交接

说明：模型、数据后端、前端和证据报告均为职责名称，不代表团队分组或仓库命名。阶段记录保留当时状态，当前功能以 README 和实际代码为准。

后续第三步已加入二元操作的完整数据后端功能验收与独立副本篡改演示。当前优先可运行、暂缓 modify 跨模块冲突；最新操作和协作边界见 [BACKEND_DEMO.md](./BACKEND_DEMO.md)。下文保留指标既有语义，不删除已支持的操作。

当前基于第一步提交 `627b5a8`，并已快进同步前端的首页提交 `0509d53`。仅修改数据后端自有实现、演示脚本、测试与文档，不修改队友的页面、共享结构、报告或测试。

## 已完成什么

`loopledger/metrics.py` 实现 PLAN 中的 `reviewer_stats()` 与 `system_stats()`。指标读取 SQLite 中的真实落库数据，不读取 Streamlit 会话假数据，不自动生成审核，也不写入业务记录。每次调用都读取新数据，不缓存旧统计。

- 审核统计从审计事件关联审核发生前已有的 AI 预测；不会把后来修改的 `cases.prediction` 当成当时展示的 AI 建议。
- 系统数量读取当前 `cases` 状态；单次查询有一致快照。完整报告仍由报告生成逻辑顺序读取多个函数，尚非跨模块的单一原子快照。
- 未审核的案例不计入审核员指标；无金标准测量返回 `None`，严格 JSON 导出为 `null`，不伪造成 0%。
- 前端现有 Backend metrics 页面、证据报告模块 Markdown/JSON 报告、前端 Compliance 导出已使用真实数据后端后台进行集成验证，不需要改动这些消费方文件才能调用。
- `scripts/demo_reset.py --profile oversight` 生成满足最低样本数的合成对照；默认 `basic` 保留第一步 20 条事件样例。

## 接口和统计口径

初始化与数据库选择沿用 `ledger.py`：应用启动先 `init_db()`，所有模块读取同一个 `LOOPLEDGER_DB_PATH`；未设置时使用仓库根目录的 `loopledger.db`。

### `reviewer_stats() -> pandas.DataFrame`

前七列保持 PLAN 顺序；后四列是供显示和复核使用的补充信息。

| 列 | 定义 |
| --- | --- |
| `reviewer` | 审核事件中的审核员名称；目前不是已认证身份 |
| `n_reviews` | 已成功落库的审核事件数 |
| `avg_seconds` | 有效、有限、非负的 `seconds_spent` 的算术平均数；无有效值为空 |
| `override_rate` | 对有原始 AI 决策的审核，操作为 `modify` 或不同于 AI 的比例 |
| `gold_catch_rate` | 已审的已知 AI 错误探针中，操作与正确答案完全相同的比例；答案支持 `approve/reject/modify`；正确 AI 控制题不计入分母 |
| `short_reason_rate` | 去除理由两端空白后，字符数小于 12 的比例；12 字符不算短理由 |
| `flag` | `no_alert / watch / review_signals / insufficient_data`，与前端页面现有枚举相同 |
| `comparison_samples` | 可与当时 AI 决策比较的审核数，即推翻率分母 |
| `gold_samples` | 已审、答案已知且 AI 已知出错的探针数，即检出率分母 |
| `timed_samples` | 有有效耗时的审核数，即平均耗时分母 |
| `flag_reasons` | 告警原因代码列表；没有触发条件时为空列表；不包含金标准答案 |

金标准中“人选了另一种推翻操作”不一定答对。例如正确答案是 `modify`，人直接 `reject`：计为推翻 AI，但不计为检出成功。模型模块的正确 AI 控制题，例如 AI 建议与答案均为 `approve`，不能因为审核员选错而稀释“发现 AI 错误”的检出率；它属于另一个控制题准确率问题，当前没有新增这个指标。

### 告警阈值

这些是与前端会话演示对齐的经验阈值，没有经过真实业务校准。

| 状态 | 触发条件 |
| --- | --- |
| `insufficient_data` | 少于 5 次审核，或存在缺失/无效耗时，或有审核找不到原始 AI 决策；优先于红黄状态 |
| `review_signals`（红） | 平均耗时 < 5 秒；或短理由率 ≥ 80%；或至少 3 道错误探针且检出率 < 50% |
| `watch`（黄） | 无红色条件时，平均耗时 < 15 秒；或短理由率 ≥ 40%；或至少 5 次可比较审核且推翻率为 0；或至少 3 道错误探针且检出率 < 80% |
| `no_alert`（绿） | 已满足基础样本条件，且上述规则均未触发；不表示已证明监督有效 |

原因代码示例：`fewer_than_5_reviews`、`missing_or_invalid_timings`、`missing_ai_predictions`、`avg_seconds_below_5`、`zero_overrides_across_5_or_more_reviews`、`gold_catch_rate_below_0.5`。前端可以将代码映射成便于理解的文案；目前已有页面也可直接读取该补充列。

### `system_stats() -> dict`

保持 PLAN 五个键，另补充前端已预留的 `auto_rejected`：

```python
{
    "total": 16,
    "auto_approved": 1,
    "sent_to_review": 14,
    "reviewed": 12,
    "pending": 2,
    "auto_rejected": 1,
}
```

`sent_to_review = reviewed + pending`；`total = auto_approved + auto_rejected + sent_to_review`。新预测在闸门完成路由前按 ledger 的保守策略属于 pending。`auto_approved` 仅统计自动批准，不能拿它代表自动决定总量。

## 离线演示与验收

`oversight` 配置包含 16 个合成案例、12 次审核、44 条事件；两个自动案例分别批准和拒绝，另有两个待审案例。两名审核员各有六次审核和三道错误探针，探针正确答案覆盖 `modify`。

| 审核员 | 审核数 | 平均秒数 | 推翻率 | 错误探针检出率 | 短理由率 | flag |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `careful_reviewer` | 6 | 50 | 50% | 100%（3/3） | 0% | `no_alert` |
| `rubber_stamp` | 6 | 2 | 0% | 0%（0/3） | 100% | `review_signals` |

这些数值是为可重复联调设计的合成对照，不是对真实审核员或模型效果的实验结论。默认 `basic` 每人只有两次审核，仍正确显示 `insufficient_data`。

Windows PowerShell，从仓库根目录运行，先激活项目 Python 环境：

```powershell
$env:LOOPLEDGER_DB_PATH = Join-Path (Get-Location) "demo-local.db"
python scripts/demo_reset.py --db $env:LOOPLEDGER_DB_PATH --profile oversight
python -c "from loopledger.metrics import reviewer_stats, system_stats; print(system_stats()); print(reviewer_stats().to_string(index=False))"
python -m streamlit run pages/3_Oversight_Dashboard.py
```

页面选择 **Backend metrics**，不要用 Session demo 查看本数据库。Compliance 页面选择 **Backend interfaces**。已有演示文件需要明确加 `--force` 才会重置；先停止正在使用它的应用。不要提交生成的数据库，也不要用 `--force` 覆盖团队跟踪的根目录 `loopledger.db`。

## 需要口头同步的事项

建议先用一两分钟把“现在能接入什么”和“还有什么没接上”说清楚，具体字段和边界交给下节文件核对。

| 对象 | 需要当面确认的话 |
| --- | --- |
| 前端 | “数据后端的数据库指标已能被 Backend metrics 读取，报告后台也可调用。你的会话审核仍不入库，要接 `get_pending_reviews/submit_review`；`modify` 按钮还禁用，部分金标准无法正确作答。首页的数据后端指标/报告待实现文案也需要更新。” |
| 模型与前端 | “`modify` 表示修改/暂缓并补充材料，不代表放款；检出率包含以 modify 为答案的错误探针。审核前必须保留后台答案，传 UI 前脱敏；当前 GOLD ID 和测试原因仍可能暴露测试身份。” |
| 前端与证据报告 | “绿色只表示未触发规则，少于五次审核显示样本不足。红色也只是调查信号。不要把这套经验阈值讲成已经验证有效的监督质量评分。” |
| 证据报告模块 | “JSON/Markdown 已能用真实 SQLite 指标导出。模板里‘自动决定总数’目前只用了 auto_approved，要改成‘自动批准’，或明确相加自动拒绝。数据来源仍需区分合成演示与真实模型运行。” |
| 前端 | “你有一项旧测试没有模拟缺失依赖，直接假定数据后端指标不存在；现在需要改测试前提，不能要求真实可用的后台一直报错。” |

## 队友应该看哪些文件

| 对象 | 必读文件 | 重点 |
| --- | --- | --- |
| 前端 | `loopledger/metrics.py`、本文的接口/阈值部分 | 返回列、额外分母、flag 枚举、None 与 0 的差别、数据库路径 |
| 前端 | `tests/test_metrics_integration.py` | 已有页面不改源码也能加载真实后台的可执行示例，以及真正模拟依赖缺失的测试 |
| 前端 | `loopledger/ledger.py`、`pages/1_Run_Batch.py`、`pages/2_Review_Queue.py` | 页面当前会话数据与持久化接口的接入位置；提交成功后才从队列移除；修改按钮与缺失特征展示 |
| 前端 | `pages/3_Oversight_Dashboard.py`、`tests/test_oversight_dashboard.py` | Backend/Session 数据源区别；旧测试 `test_backend_mode_reports_missing_functions_without_session_fallback` 应用 stub 明确模拟缺失，而不是依赖数据后端未实现 |
| 前端 | `app.py` | 已保留你的最新首页；其中“数据后端的数据库指标/报告待完成”的状态文案应更新，仍未接通的会话持久化要继续明确说明 |
| 模型模块 | `loopledger/gold.py`、`loopledger/schemas.py`、本文的检出率定义 | include_answers=True、三种正确操作、正确 AI 控制题的排除、答案脱敏和标记泄露 |
| 证据报告模块 | `loopledger/metrics.py`、`tests/test_metrics_integration.py`、`loopledger/evidence.py` | 真实报告可调用、空值/百分比/原因代码、报告 ID 与链状态验证；报告仍非单一事务快照 |
| 证据报告模块 | `templates/evidence_report.md.j2`、`loopledger/evidence.py` | 自动决定行的标签和统计口径；固定 data_origin、methodology 和 limitations 需按实际模式更新 |
| 演示主讲人 | `scripts/demo_reset.py`、本文的演示表 | 用 oversight 配置获得足够样本，准确说明 44 条合成事件的来历 |

## 测试和剩余边界

`tests/test_metrics.py` 检查指标分母、阈值边界、读操作不写库、空值、历史缺失数据、自动拒绝、当前与审计状态区别、两种演示配置。`tests/test_metrics_integration.py` 直接调用未改动的前端与证据报告代码，验证真实数据库到 Dashboard、Markdown/JSON、Compliance 下载以及异常链状态。

第二步新增的 **31 项测试全部通过**。完整 pytest 为 **112 项通过、1 项失败，另有 22 个 subtest 通过**；唯一失败项是下面的前端旧断言，未将其隐藏或跳过，因此不宣称全量测试通过。团队跟踪的数据库和模型文件保持原样。

全量测试中，前端的旧测试 `tests/test_oversight_dashboard.py::test_backend_mode_reports_missing_functions_without_session_fallback` 仍把“数据后端函数不存在”当成环境事实，接口实现后其 `assert app.error` 已过时。应由前端使用空 `loopledger.metrics` 模块 stub 模拟缺失；本次不修改队友测试。数据后端新增集成测试验证了这条真正的缺失依赖路径仍正确报错，没有退回会话数据。

本次打通的是 **已落库数据 → 指标 → 现有页面/报告**。前端的模型批量结果和会话审核尚未持久化，完整贷款审批 Demo 仍需前端接入；证据报告模块的展示标签与来源声明尚需证据报告模块调整。指标不验证身份，不防伪计时，也不替代链校验或有效监督实验。
