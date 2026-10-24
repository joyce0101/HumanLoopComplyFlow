# 数据后端功能验收、篡改演示与数据库说明

说明：模型、数据后端、前端和证据报告均为职责名称，不代表团队分组或仓库命名。阶段记录保留当时状态，当前功能以 README 和实际代码为准。

优先保证数据后端的持久化、审批、统计和证据调用完整运行。本轮同步团队 `ebcdf21`，只修改数据后端自有脚本、测试和文档；`modify` 的跨模块冲突暂缓处理，不把它作为功能验收的前提。

## 数据库是谁建立、在哪里

这是 SQLite 本地文件数据库，没有单独的数据库服务器。

| 内容 | 文件 / 记录 | 说明 |
| --- | --- | --- |
| 建表和数据库逻辑 | `loopledger/ledger.py`，`DB_PATH` 与 `init_db()` | 创建 `events` 和 `cases`，负责持久化与审计链 |
| 建表代码提交者 | Git `5c47617`、`7ac188a`，作者 `yuyanwu0719` | 由数据后端维护者提交；第一步 `627b5a8` 补齐审批和审计链 |
| 默认实际数据文件 | 仓库根目录 `loopledger.db` | 当前机器为 `E:\Github\HumanLoopComplyFlow\loopledger.db` |
| 数据文件最初加入 Git | `c52fb93`，作者 `joycelan` | 这是二进制文件的提交者；仅凭 Git 不能认定是谁实际运行程序生成文件 |
| 指标代码 | `loopledger/metrics.py` | 读取数据，不创建审核记录 |
| 演示数据重置 | `scripts/demo_reset.py` | 创建指定数据库并填入合成数据；已有文件需明确 `--force` |
| 数据库路径选择 | 环境变量 `LOOPLEDGER_DB_PATH` | 未设置时用根目录文件；前端、脚本、报告必须使用同一路径 |

不要把数据库代码文件 `ledger.py` 与保存实际数据的 `loopledger.db` 混淆。团队已跟踪的根目录 `.db` 本轮保持原样；验收全部使用新的独立文件。

## 一条命令验证数据后端的完整功能

激活项目 Python 环境，在仓库根目录执行：

```bash
python scripts/demo_check.py
```

默认在系统临时目录创建新的验收目录；需要固定位置时指定一个尚不存在的目录：

```bash
python scripts/demo_check.py --output-dir .local-sync/functional-run-001
```

目录已存在就拒绝覆盖。再次运行可不传目录，让程序创建新的临时目录，或改用一个新目录。普通 CLI 的验收子进程默认最长运行 60 秒，超时明确失败；慢机器可设置 `--timeout-seconds 120`。超时后可能保留本次新建的部分验收产物用于排查，不会清空既有业务库。

顺序验证七步，失败时非零退出，不输出伪造的成功结果：

1. 创建独立 SQLite，使用合成预测和 **模型模块的真实风险闸门**，生成 16 个案例、44 条事件。
2. 调用真实 `get_pending_reviews()`，对剩余两条待审分别批准、拒绝，成功后队列清空。
3. 重复提交同一审核，被拒绝且不增加事件。
4. 验证系统计数、审核员指标，以及前端 Dashboard 的真实后台适配器。
5. 通过前端 Compliance 后台函数校验干净链，并生成证据报告模块的 Markdown/JSON 下载内容。
6. 创建独立副本，仅改副本第 10 条事件；前端后台函数定位异常，报告显示 FAIL。
7. 切回干净数据库，链仍完整、案件统计不变。

本配置审核操作和正确答案只有 `approve/reject`，不需要 `modify`。已有 basic / oversight 配置和后台对 modify 的支持保留。

完成后有 46 条事件，16 个案例，其中自动批准 1、自动拒绝 1、已审核 14、待审 0。认真审核和秒批审核员各有 6 次审核；额外的 `demo_judge` 有 2 次，因此仍显示样本不足，不会强行变绿。

产物包括：

```text
clean.db               # 干净库，最终校验应为 (True, None)
tampered.db            # 故意修改的副本，应为 (False, 10)
clean-report.md
clean-report.json
tampered-report.md
tampered-report.json
summary.json           # 每步通过记录、实际统计、数据来源及产物路径
```

预测与申请是合成数据，特征贡献不是实际模型输出；风险闸门、SQLite、审批、指标、前端与证据报告后台消费函数是真实调用。这个验收证明数据后端的功能链可运行，不代表真实模型质量，也不代表前端的会话审核已经接入数据库。

## 单独演示篡改检测

已有一份干净演示库时：

```bash
python scripts/demo_tamper.py --source .local-sync/functional-run-001/clean.db --output .local-sync/new-tampered.db --event-id 10
```

脚本用只读连接打开源库，通过 SQLite backup 获取包含已提交 WAL 内容的一致副本；只修改副本 payload，保留原 hash，验证由完整变为第 10 条断裂。备份有 10 秒期限，已有输出、源输出同一路径、事件不存在或源链已损坏时均明确失败。不会提供“直接修改源业务库”的选项。

前端的 `pages/4_Compliance.py` 固定调用后端校验及下载接口，无需切换数据源。人工展示某个数据库时，要在启动 Streamlit 的同一个终端选择路径：

```powershell
$env:LOOPLEDGER_DB_PATH = (Resolve-Path .local-sync/functional-run-001/clean.db).Path
python -m streamlit run app.py
```

打开 Compliance，点击 Verify chain，再点击 Generate report。展示损坏副本时，停止应用、改环境变量到 `tampered.db` 后重新启动，再次校验。数据后端的 CLI 已自动验证干净/损坏/恢复三种后台状态；现有页面没有数据库切换控件，本轮不添加或改动前端的界面。

## 当前必须与队友商议的改动

以下事项不能通过数据后端的正常持久化接口自动修复。本轮不修改队友文件；应由对应队友修改，或由你先与队友确认方案后再明确授权。

| 优先级 | 文件 / 函数 | 当前问题 | 需要协商的最小改动 |
| --- | --- | --- | --- |
| 优先保证可运行 · 模型与前端 | `loopledger/model.py::predict` 与 `pages/1_Run_Batch.py::run_model_batch` | 模型模块最新接口为 `predict(features, case_id, model_path=...)`；前端仍调用 `predict(application, model_path=...)`，遗漏必填 case_id | 模型模块保留旧调用兼容，或前端把已有 case_id 显式传入。数据后端的模型集成测试已适配模型模块最新接口。 |
| 优先打通真实 UI 闭环 · 前端 | `pages/1_Run_Batch.py::_record_prediction`、`main`；`pages/2_Review_Queue.py::submit_mock_review`、`main` | 批量与审核仍使用 session_state / 打印；界面操作不会自动进入数据后端的 SQLite | 前端增加明确的持久化模式：启动 init_db，保存 prediction/gate，读取真实队列并提交 ReviewAction；落库成功后再刷新 UI。数据后端的对应接口和独立功能验收已齐备。 |
| 测试交接 · 前端 | `tests/test_oversight_dashboard.py::test_backend_mode_reports_missing_functions_without_session_fallback` | 仍把数据后端指标不存在当作事实 | 由前端显式使用空 metrics 模块模拟依赖缺失；本轮保留其测试。 |
| 后续展示优化 · 证据报告模块 | `templates/evidence_report.md.j2`、`loopledger/evidence.py` | 自动决定行标签与 auto_approved 不一致；固定来源说明需按真实模式更新 | 报告维护者修改标签或展示批准+拒绝总量；来源声明按合成/真实模型区分。本轮报告生成接口可正常运行。 |
| 暂缓 | 模型与前端的 modify 语义、按钮与金标准展示 | 按本轮用户要求暂不推进 | 当前 functional 演示只用批准/拒绝，不阻塞数据后端验收。 |

最新模型模块已补齐 `sample_cases()`、`gate.check()`、`make_gold_cases()`，无需继续按“这些函数不存在”沟通；旧文档中的相关条目已更新。

为优先恢复模型预览，可先与模型维护者商议保留新标准调用，同时兼容旧前端调用。供模型维护者审阅的最小方案如下，**尚未应用到模型模块文件**：

```python
def predict(features: dict, case_id: str | None = None, model_path=MODEL_FILE) -> Prediction:
    if case_id is None and isinstance(features, dict):
        case_id = features.get("case_id")
    # 保留后续已有的非空 ID 校验、冲突校验、模型预测逻辑。
```

这样标准 `predict(features, case_id, model_path=...)` 与前端目前 `predict(application, model_path=...)` 均可工作，前提是 application 内有合法 case_id。若模型维护者希望严格保持必传参数，则改由前端更新调用和其测试中的直接预测调用。请先由模型与前端确认，再由队友修改或由你明确授权修改指定文件；数据后端不通过运行时替换、注入或改写他人模块绕过这一差异。

## 验证范围

`tests/test_demo_tools.py` 检查源库不变、输出文件保护、缺失/损坏输入、真实 WAL 备份、环境变量恢复、二元功能配置、CLI 超时、验收产物和未改动的 Compliance 页面真实链校验/报告/恢复。

`tests/test_team_integration.py` 使用模型模块最新 `predict(features, case_id, model_path=...)` 验证真实模型到数据后端审批链。完整测试还会运行队友现有测试；如仍有跨模块调用差异或旧断言失败，会明确列出，不改测试来掩盖问题。

在同步后的 `ebcdf21` 基线上，本轮结果为：

- 数据后端自有五个测试文件：**70 项通过，22 个 subtest 通过**；其中 `test_demo_tools.py` 的 17 项覆盖本轮新增脚本。
- 全项目 pytest：**125 项通过、5 项失败，另有 22 个 subtest 通过**。4 项失败位于 `tests/test_run_batch.py`，由模型预览遗漏新必填 `case_id` 引起；1 项位于 `tests/test_oversight_dashboard.py`，为旧的后台缺失断言。没有隐藏或跳过这些失败。
- 当前机的功能验收产物位于 `.local-sync/functional-run-001/`，七步全部通过；根目录团队数据库、模型、前端和证据报告文件与同步基线一致。

本轮没有进行备用机器实测。队友可在准备好项目依赖后执行同一个 `python scripts/demo_check.py`，将输出的 `summary.json` 用于复核。
