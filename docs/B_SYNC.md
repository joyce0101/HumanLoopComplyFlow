# B 组与团队版本同步事项

第三步功能验收已完成，已同步 A 的 `ebcdf21`。当前优先运行批准/拒绝闭环，modify 冲突暂缓。最新数据库说明、可运行命令和需要队友修改的文件以 [B_DEMO.md](./B_DEMO.md) 为准。

第二步指标已实现，现有 C/D 的真实后台调用已验证。最新接口、口头同步事项、队友应读文件和旧测试调整说明以 [B_METRICS.md](./B_METRICS.md) 为准。

本次以团队 `main` 的 `0b41de2`（`Implement Streamlit demo workflows and frontend tests`）为基线，直接在本地 `main` 快进同步 26 个提交，其中包括 A 的 `7f05b61` 数据结构对齐和 C 的最新页面及测试。没有新建分支，没有改动 A/C/D 的修订文件；下列差异仅作交接说明。

## 本次 B 组已处理

- 在已有 SQLite 初始化实现上补全审计、审批队列与原子写入，保留 `DB_PATH`、`init_db()` 和模块初始化入口。
- 复用团队 `schemas.py`，不重新定义 dataclass。
- 接受 A 最新金标准答案中的 `modify`，并按原值存储；后台题目须通过 `get_gold_cases(n, include_answers=True)` 获取。默认隐藏答案的返回值不能作为完整后台题目入库，B 会明确报错，防止统计时丢失答案。
- 保留团队删除误建 `Loopledger` 目录的提交；所有 import 使用 `loopledger`。
- 仅新增 B 自有测试与说明文件；保留 D 的既有证据测试，测试对外部后台使用 stub，不能据此宣称真实报告已联通。

## 接口差异与待同步事项

| 优先级 / 对接方 | PLAN / 旧约定 | 团队 main 当前实现 | 调用方式或需要对齐的事项 |
| --- | --- | --- | --- |
| P0 · A / C | `predict(features, case_id)` | A 最新 `ebcdf21` 已实现 `predict(features, case_id, model_path=...)` | C 的 `run_model_batch` 仍只传 application 与 model_path，会缺少 case_id。需 A 保留兼容或 C 显式传案例 ID；本轮只适配 B 自有集成测试，不修改两组文件。 |
| 已处理 · A | `gate.check(pred)` | A 最新已增加 `check(pred)`，同时保留 `evaluate_risk(application, pred)` | 两种接口可用。features 未带 case_id 时不再判为不匹配；有字段但与 pred 不一致时仍拦截。 |
| 已处理 · A | `sample_cases(n)` | A 最新已提供从固定 holdout 抽样的接口 | 返回值不含目标标签；identity_verified=True 是演示假设，不是 German Credit 原始事实。C 可协商后改用此入口，不改其现有文件。 |
| 已处理 · A / B | `make_gold_cases(n)` | A 最新已增加标准接口，返回含答案的后台 Prediction | 后台可直接交 B 保存；UI 仍需脱敏。modify 相关跨组优化按用户要求暂缓，functional 验收只使用二元操作。 |
| 已处理 · B / C / D | 指标与报告可按签名调用 | `reviewer_stats()`、`system_stats()` 已实现 | 已用真实 SQLite 验证 Dashboard、D 报告及 Compliance 下载；D 原有替身测试保留，另增 B 的真实集成测试。 |
| P0 · C | 缺失后台时应明确报错 | `tests/test_oversight_dashboard.py::test_backend_mode_reports_missing_functions_without_session_fallback` 未模拟缺失依赖，仍断言真实后台报错 | 指标实现后该断言过时。请 C 用空 metrics 模块 stub 模拟缺失；B 自有集成测试已验证真正缺失时仍报错。本次不修改队友文件。 |
| P0 · B / C | 批量 → SQLite 队列 → 审批落库 | C 的 mock batch/审核使用 session_state，Model preview 不入队也不落库 | C 接入时先调用 `init_db()`，逐案例保存 prediction 和 gate；审核页改用 `get_pending_reviews()` 与 `submit_review()`，成功落库后才刷新 UI。B 接口已完成，本次未改 C 页面。 |
| 暂缓 · A / C | 审核操作包含 `modify` | A 部分金标准答案为 modify，C 按钮仍禁用 | 按本轮用户要求暂不推进；B 后台保留兼容，functional 演示只用批准/拒绝，不因该问题暂停验收。 |
| P1 · A / C | 审核页可展示任意共享 Prediction | C 假定 features 必含 age、duration，且 top_factors 非空；A 金标准缺少这些数值且 factors 为空 | 直接换成真实队列会有 KeyError / 空序列解包风险。C 接入时需对缺失字段和无特征贡献提供合理展示；本次未改页面。 |
| P1 · B / D | `auto_approved` 表示自动批准 | 报告模板将该字段展示为所有 `status=auto` 的自动决定 | 自动拒绝不能算自动批准。后续 B 应只计批准；请 D 同步修改展示标签，或全队确认新增独立 `auto_decided` 字段。当前未改模板。 |
| 已处理 · B / D | 旧本地文档没有确定 `modify` 的统计口径 | 与 D 对齐：`modify` 计为 override，短理由为去除两端空白后少于 12 字符 | 正确答案为 `modify` 的错误探针已计入；无探针测量返回空值，不用 0% 代替无数据。 |
| 已处理 · B / C | flag 仅约定红黄绿 | 已输出 C 的四个枚举并沿用最小 5 次审核、金标准告警至少 3 道错误探针的阈值 | 保留默认 basic 的样本不足结果；新增 `--profile oversight` 为两人各六次审核、三道错误探针。C 的 Session demo 目前只统计二元错误探针，后续如接 `modify` 题需与 Backend 口径对齐。 |
| P1 · A / D | 方案为 XGBoost + SHAP / 前 3 个特征 | 模型为 LogisticRegression + 标准化/独热编码，输出前 5 个 log-odds 特征贡献 | B 按原值保存，不将系数贡献称为 SHAP。请 A/D 对齐海报、报告和讲解用语。 |
| P1 · D | 报告描述当前系统的数据来源 | 报告仍固定写 A/B/C 为 mock，未使用 German Credit 和真实模型；C 最新 README 已准确区分模型、会话演示与未接入的数据库 | 对真实模型运行生成报告前，需要 D 确认并更新来源声明；当前 B 的 `demo_reset` 确实使用合成数据，不能将其说成真实模型结果。README 本次保留 C 最新版本，其中 B 接口状态仍需后续由维护者更新。 |
| P1 · A / C | 金标准题在审核员视角不可识别 | 答案字段虽有脱敏函数，但 case_id 为 `GOLD-*`，闸门原因含 `Gold-standard oversight test` | C 不应将后台测试标记和原始测试原因显示给审核员；如需真正盲测，应由 A/C 协商匿名 ID 和展示策略。当前未修改两组实现。 |
| P2 · 全队 | 本地运行数据不参与代码协作 | 团队已跟踪 `loopledger.db` 二进制文件 | 本次保持该文件原样；本地演示库另存，避免 pull/merge 覆盖操作数据。是否取消跟踪由团队统一决定。 |

## B 组事件输入与输出

```python
from dataclasses import asdict
from loopledger import ledger
from loopledger.gate import evaluate_risk
from loopledger.gold import get_gold_cases, public_review_payload

ledger.init_db()

# 后台构造测试题，保留答案用于监督指标。
pred = get_gold_cases(1, include_answers=True)[0]
application = {**pred.features, "case_id": pred.case_id}
gate = evaluate_risk(application, pred)
ledger.log_event("prediction", asdict(pred))
ledger.log_event("gate", {"case_id": pred.case_id, **asdict(gate)})

# 传给审核视图前做字段选择；仍需按上表处理可识别的测试 ID。
review_view = public_review_payload(ledger.get_pending_reviews()[0])
```

- `prediction` payload 是展开的 `asdict(Prediction)`；`gate` 是 `case_id` 加展开的 `asdict(GateResult)`。不是嵌套的 `{"prediction": ...}`。
- `get_all_events()` 返回按 id 排序的字典列表，`payload` 已解析为字典，包含 `hash` 和 `prev_hash`，供 D 直接消费。
- `submit_review()` 仅接受共享 `ReviewAction`，重复审批和不合法参数不写入事件。`modify` 关闭当前审核任务并记录修改/暂缓意见，不执行贷款操作，也不生成不存在的最终二元决定。
- `verify_chain()` 返回 `(True, None)` 或 `(False, 首个异常/缺失事件 ID)`；验证的是事件链，未覆盖独立 cases 状态表或提供外部可信锚定。

## 第一步历史复核

在同步后的 `0b41de2` 基线上，使用 Python 3.13.17 执行完整 pytest：**82 项测试通过，另有 22 个 subtest 通过**。包括 B 的 17 项后端测试、5 项团队接口集成测试，以及团队已有页面/报告契约测试。真实模型集成测试使用本地 German Credit 数据和临时训练产物；现有前端/报告测试中使用替身的部分仍只证明各自契约行为，不证明整个持久化 Demo 已完成。

提交前已逐项核验团队 `.gitignore`、README、schemas、A 模型/闸门/金标准、D 报告、模板、C 四个页面及已有模型/数据库文件与团队基线一致。提交范围限定为 B 的两个实现文件、两个测试文件、两个交接文档。

```bash
python -m unittest discover -s tests -p test_ledger.py -v
python -m pytest -q
python scripts/demo_reset.py --db demo-local.db
```

pytest 需另行安装；Jinja2、pandas、scikit-learn 在项目原依赖中。集成测试自行训练临时模型，不覆盖团队的 `credit_model.joblib`；测试数据库也全部位于临时目录。团队根目录数据库及同步前本地演示库均保留。
