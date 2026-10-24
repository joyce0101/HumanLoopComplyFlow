# B 组任务与交付

第一步与第二步均已完成。第二步接口、演示、口头同步事项和队友阅读清单见 [B_METRICS.md](./B_METRICS.md)。

依据：`PLAN.md` 第 3、4、7 节，`README.md`，以及 `LoopLedger.md` 列出的评委要求。以下优先级针对项目现有目标，不代表赛事官方评分或获奖保证。

## 你的职责与获奖贡献

B 负责证据的产生、保存和统计，连接 A 的预测、C 的审批界面与 D 的证据报告。最值得投入的主线是：**记录真实审核行为 → 展示监督质量差异 → 让证据可以复查**。

| 阶段 | 具体交付 | 对演示和评审的贡献 | 完成标准 |
| --- | --- | --- | --- |
| 第一步：Sprint 1，数据底座 | `schemas.py`、`ledger.py`、`scripts/demo_reset.py`、后端测试 | A/C/D 有稳定接口；演示不依赖网络；审计记录可以核验 | 20 条事件校验通过，篡改能定位；预测到审批的后端闭环跑通 |
| 第二步：Sprint 2，核心差异化（已完成） | `metrics.py`：`reviewer_stats()`、`system_stats()` | 展示认真审核与“橡皮图章”的可观察差异，回应“如何衡量监督” | 两名模拟审核员各六次审核、三道错误探针；真实 Dashboard 与报告调用已验证 |
| 第三步：Sprint 3，现场演示 | 配合 C 完成 `4_Compliance.py` 的链检查；独立副本上的模拟篡改脚本 | 现场完成“校验通过 → 修改记录 → 显示断裂位置” | 保留干净数据库，可反复重置，两台机器都可运行 |
| 集成与交接 | A：事件输入；C：队列和提交；D：事件与统计输出 | 避免各模块各自可用、组合后失败 | 按 PLAN 检查点打通完整流程，供 D 录制备用演示 |

优先完成 P0 的审计闭环与监督质量指标，再做 P1 的金标准和篡改演示。PDF、登录体系和 LLM 理由评分都不应挤占这条主线。

## 第一步已经完成

- 使用团队现有 `schemas.py`，保持共享 dataclass 的字段和默认值不变；本次同步不修改该文件。
- SQLite 使用约定的 `events` 与 `cases` 表，支持 `auto / pending / reviewed` 状态。
- 日志记录 UTC 时间，使用稳定 JSON 序列化和 `sha256(prev_hash + ts + event_type + payload)`；链首前驱值是 64 个 `0`。
- 预测默认保留为 `pending`；闸门明确判定后才可转为 `auto`。每个案例只接受一次闸门路由和一次人工审批。
- 每次业务状态更新与对应审计事件使用同一事务。写入串行化，重复点击和并发审批不会产生两次有效提交。
- 拒绝空审核员、空理由、无效操作、负耗时和非有限数值；发生错误不留下部分业务更新。
- 读取 JSON 后恢复 `top_factors` 的 tuple，保留金标准元数据以供后台统计。
- 重置脚本离线生成 20 条合成事件，其中两个审核员各完成两次审核，并各遇到一道金标准题；认真审核员检出错误，秒批审核员漏检。
- 工作区使用小写 `loopledger`。团队最新 main 已删除误建的大写目录，本次直接同步该结果。
- 对接 A 的最新金标准数据，后台正确答案支持 `approve / reject / modify`；保留已有 `python -m loopledger.ledger` 初始化入口。

### 运行与验收

```bash
python -m unittest discover -s tests -p test_ledger.py -v
python scripts/demo_reset.py --db demo-local.db
```

已有数据库需使用 `--force` 才会清空；重置前停止应用。可用 `--db` 指定文件，`--empty` 跳过样例数据。`init_db()` 只建表，不清空已有证据；默认数据库固定在仓库根目录，也可通过环境变量 `LOOPLEDGER_DB_PATH` 覆盖。

后端 17 项测试覆盖：独立重算 20 条哈希；修改 payload、时间、事件类型、前驱 hash、hash、case_id 后定位第 10 条；删除中间或末尾事件；预测/分流/审批闭环；无效及重复提交；模拟事件插入失败后的事务回滚；40 次并发追加；两人同时审批仅一人成功；重置命令重复运行与空库模式。

`tests/test_team_integration.py` 另验证 A 的真实闸门、六道金标准题（包括 `modify`）、答案脱敏、初始化入口，以及从本地 German Credit 数据训练的模型到 B 审批落库的流程。完整测试使用 pytest，额外需要 Jinja2、pandas、scikit-learn：

```bash
python -m pytest -q
```

测试全程使用临时数据库，不修改实际演示库。

第一步完成时的历史 pytest 结果为 **82 项测试通过，另有 22 个 subtest 通过**。第二步结果和剩余旧测试问题见 [B_METRICS.md](./B_METRICS.md)，第一步同步记录见 [B_SYNC.md](./B_SYNC.md)。

## A / C / D 可以怎样接入

事件采用展开的 dataclass 字典；闸门事件额外带 `case_id`。这补充了 PLAN 未明确的 payload 形状，没有更改已有签名。

```python
from dataclasses import asdict

from loopledger.ledger import (
    init_db, log_event, get_pending_reviews, submit_review,
    get_all_events, verify_chain,
)
from loopledger.schemas import Prediction, GateResult, ReviewAction

init_db()  # C 在应用启动时调用；重复调用安全

# A/C：先保存预测，再保存 evaluate_risk(application, pred) 的结果。
pred = Prediction(
    case_id="loan-001",
    features={"age": 24, "credit_amount": 8000},
    decision="reject", confidence=0.61,
    top_factors=[("credit_amount", -0.23)],
)
log_event("prediction", asdict(pred))
gate = GateResult(needs_review=True, reasons=["low_confidence"])
log_event("gate", {"case_id": pred.case_id, **asdict(gate)})

# C：只展示业务字段、AI 建议及解释，不把金标准答案渲染给审核员。
pending = get_pending_reviews()
submit_review(ReviewAction(
    case_id=pending[0].case_id, reviewer="reviewer-1",
    action="approve", reason="核对了收入证明与还款能力，决定推翻 AI 建议。",
    seconds_spent=35.0,
))

# D：payload 已解析为字典，事件按 id 排序。
events = get_all_events()
intact, broken_id = verify_chain()  # (True, None) 或 (False, 首个异常/缺失 id)
```

`log_event("review", asdict(action))` 与 `submit_review(action)` 走同一条校验与事务路径，不可绕过重复审批检查。其他事件类型（如 `export`）只追加证据。重复案例、重复路由、非待审案例提交等业务错误抛出 `ValueError`，C 应展示可理解的提示并刷新队列。

## 第二步已落地的指标口径

保留 PLAN 约定的列：`reviewer, n_reviews, avg_seconds, override_rate, gold_catch_rate, short_reason_rate, flag`。用这里的两个模拟审核员先验证，再接真实页面。

- **平均时长**：只统计成功落库的审核，秒批与认真审核需在演示中明显可辨。
- **推翻率**：已与 D 对齐，`modify` 计为推翻；`modify` 表示修改/暂缓并请求补充材料，保存时不猜测最终二元决定。
- **金标准检出率**：已审且 AI 已知出错的探针为分母，操作与答案相同才算检出，包括 `modify`；正确 AI 控制题不计入该分母。没有探针测量时为空值，不能当成 0%。
- **短理由率**：与 D 对齐，使用去除两端空白后少于 12 字符的阈值；保存理由原文，说明这是启发式指标。
- **flag**：枚举与 C 对齐，提供原因与样本数；少于 5 次审核优先显示样本不足，金标准告警至少需 3 道错误探针。时长短、推翻率低都只能作为调查信号。
- **系统数量**：区分自动决策与自动批准。`auto` 状态也可能是自动拒绝，不能全部算进 `auto_approved`；送审量应含已审及待审案例。

第二步对照数据和现有 C/D 接口的真实调用均已验证，分母和告警原因可复查。默认 basic 配置仍是 20 条事件；新 oversight 配置为 44 条事件，支持六次审核的红绿对照。这些测试证明实现与合成预期一致，尚未证明真实审核质量或模型效果。

## 当前边界与交接事项

- B 当前完成第一、二步；团队模型、闸门、金标准、Streamlit 页面与报告代码已同步。真实落库数据的指标、Dashboard 和报告已可调用，但 C 页面提供的会话审核和模型预览尚未连接数据库队列，完整持久化 Demo 尚未打通。新交接见 [B_METRICS.md](./B_METRICS.md)，其他接口差异见 [B_SYNC.md](./B_SYNC.md)。
- 哈希链可以发现保留原链关系时的修改、断链和缺失记录；末尾删除检测依赖 SQLite 自增序号未被重置。拥有数据库完整写权限的人可以重算整条链、重置序号或替换整库。更强的证明需要独立可信的链头检查点，当前未实现。
- `verify_chain()` 验证审计事件，不验证独立的 `cases` 状态表；不能宣称整个数据库不可篡改。
- `get_pending_reviews()` 按共享契约返回金标准字段。C 必须选择展示字段，不能直接把整个 dataclass 渲染成 JSON。当前没有账号和权限隔离。
- `modify` 按原样记录，不补造最终决策；审核耗时由调用方提供，当前无服务端防伪计时。
- 维护者已确认 `Loopledger` 是误建遗留目录，实际代码在 `loopledger` 中维护。团队已提交删除大写目录，本次 main 快进同步包含该清理，不再重复提交删除。
- 团队跟踪的根目录 `loopledger.db` 保持原样，未把本地合成数据覆盖进去。本次同步前的 20 条事件演示库保存在本地忽略目录 `.local-sync/local-demo.db`；新演示建议使用独立 `--db demo-local.db`。`.gitignore` 不会自动取消团队已有数据库的跟踪。
- 第一步仅提交 B 的 `ledger.py`、`scripts/demo_reset.py`、自有测试与交接文档；第二步仅扩展 B 的 `metrics.py`、演示脚本、自有测试和交接文档。团队 `.gitignore`、README、schemas、A/C/D 源码、报告模板、现有测试、模型文件及数据集均保留团队版本；历史本地 README/schema/.gitignore 改动已备份，不纳入提交。虚拟环境、同步临时文件和独立演示库仅配置本机 `.git/info/exclude`，不修改团队忽略规则；其他机器运行后也应避免提交生成的数据库。
