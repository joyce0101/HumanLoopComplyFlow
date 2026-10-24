# LoopLedger — 4 人执行计划与分工

> 配合 [LoopLedger.md](./LoopLedger.md) 使用。本文档只讲**谁在什么时候交付什么**。

---

## 0. 关键决策（开工前 5 分钟定下来，之后不再讨论）

| 决策 | 选择 | 理由 |
|---|---|---|
| 前端 | **Streamlit** | 一个人半天就能做出多页面应用，不需要前后端联调 |
| 后端 | **不单独起 API 服务**，Streamlit 直接调用 Python 模块 | 省掉 FastAPI 联调的时间，降低集成风险 |
| 存储 | **SQLite 单文件** `loopledger.db` | 不用部署，Demo 时可以直接重置 |
| 数据集 | **German Credit**（`sklearn.datasets.fetch_openml("credit-g")`） | 1000 行，训练只需几秒 |
| 协作 | 一个 GitHub 仓库，每人一个分支，**每个检查点合并到 main** | |
| 演示 | 一台主力笔记本 + 一台备用机，都能跑 | 防止现场翻车 |

---

## 1. 角色分工

| 角色 | 代号 | 负责模块 | 交付物 |
|---|---|---|---|
| **ML 工程师** | A | 被监督的 AI + 风险闸门 + 金标准题 | `model.py`、`gate.py`、`gold.py` |
| **后端 / 数据工程师** | B | 数据库 + 哈希链日志 + 监督质量指标 | `ledger.py`、`metrics.py` |
| **前端工程师** | C | Streamlit 全部页面 | `app.py`、`pages/*.py` |
| **合规 / 产品 / Pitch** | D | 证据包导出 + 法规映射 + 海报 + 演示脚本 + 测试 | `evidence.py`、`templates/`、海报、pitch 稿 |

> D 既写代码也负责"讲故事"。评委走动打分时，D 是主讲人。

---

## 2. 项目结构（B 在 11:50 前建好仓库并推送）

```
synoptix/
├── LoopLedger.md          # 方案文档
├── PLAN.md                # 本文件
├── requirements.txt
├── loopledger/
│   ├── __init__.py
│   ├── schemas.py         # 共享数据结构（全员遵守，改动需全队同意）
│   ├── model.py           # A：训练、预测、SHAP
│   ├── gate.py            # A：风险闸门
│   ├── gold.py            # A：金标准测试题
│   ├── ledger.py          # B：SQLite + 哈希链
│   ├── metrics.py         # B：监督质量指标
│   └── evidence.py        # D：证据包生成
├── templates/
│   └── evidence_report.md.j2   # D：报告模板
├── app.py                 # C：Streamlit 入口
├── pages/
│   ├── 1_Run_Batch.py     # C：批量提交申请
│   ├── 2_Review_Queue.py  # C：人工审批界面
│   ├── 3_Oversight_Dashboard.py  # C：监督质量面板
│   └── 4_Compliance.py    # C + D：证据导出 + 篡改检测
└── scripts/
    └── demo_reset.py      # B：一键重置 Demo 数据
```

`requirements.txt`：
```
streamlit
pandas
scikit-learn
xgboost
shap
jinja2
plotly
```

---

## 3. 接口契约（**11:45–12:00 全员一起定**，之后各自并行开发）

这是能够并行开发的关键。所有人都按下面的函数签名写代码，别人的模块还没写好时，就先用假数据代替。

### 3.1 共享数据结构 `schemas.py`

```python
from dataclasses import dataclass, field
from typing import Literal, Optional

@dataclass
class Prediction:
    case_id: str
    features: dict            # 原始申请信息
    decision: Literal["approve", "reject"]
    confidence: float         # 0~1
    top_factors: list[tuple[str, float]]  # SHAP 前 3 个特征: [(名称, 贡献值)]
    is_gold: bool = False     # 是否为金标准测试题
    gold_correct_decision: Optional[str] = None  # 金标准题的正确答案

@dataclass
class GateResult:
    needs_review: bool
    reasons: list[str]        # 例如 ["low_confidence", "high_amount"]

@dataclass
class ReviewAction:
    case_id: str
    reviewer: str
    action: Literal["approve", "reject", "modify"]
    reason: str
    seconds_spent: float      # 从打开到提交的耗时
```

### 3.2 函数签名

```python
# A — model.py
def train() -> None                                   # 训练并保存到 model.pkl
def predict(features: dict, case_id: str) -> Prediction
def sample_cases(n: int) -> list[dict]                # 从测试集抽 n 个申请

# A — gate.py
def check(pred: Prediction) -> GateResult

# A — gold.py
def make_gold_cases(n: int) -> list[Prediction]       # AI 故意判错的题，用来测试审核员

# B — ledger.py
def init_db() -> None
def log_event(event_type: str, payload: dict) -> str  # 返回该条记录的 hash
def get_pending_reviews() -> list[Prediction]
def submit_review(action: ReviewAction) -> None
def get_all_events() -> list[dict]
def verify_chain() -> tuple[bool, Optional[int]]      # (是否完整, 第一条断裂记录的 id)

# B — metrics.py
def reviewer_stats() -> "pd.DataFrame"
    # 列: reviewer, n_reviews, avg_seconds, override_rate, gold_catch_rate, short_reason_rate, flag
def system_stats() -> dict
    # {total, auto_approved, sent_to_review, reviewed, pending}

# D — evidence.py
def build_report() -> str                             # 返回 Markdown
def build_report_json() -> dict
```

### 3.3 数据库表（B 负责实现）

```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  event_type TEXT NOT NULL,       -- prediction / gate / review / export
  case_id TEXT,
  payload TEXT NOT NULL,          -- JSON
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL              -- sha256(prev_hash + ts + event_type + payload)
);
CREATE TABLE cases (
  case_id TEXT PRIMARY KEY,
  prediction TEXT NOT NULL,       -- Prediction 的 JSON
  status TEXT NOT NULL            -- auto / pending / reviewed
);
```

---

## 4. 时间线与每人任务

### Day 1（今天）

#### ⏱ 11:45–12:00　全员：对齐（15 分钟）
- [ ] 全员通读本文档，确认第 0 节的决策
- [ ] 确认第 3 节的接口契约
- [ ] B 建仓库，推送目录骨架和 `schemas.py`

#### ⏱ 12:00–13:00　午餐（Side Room）
> 建议轮流去吃饭，或者把饭拿回来边吃边写。这一小时可以先各自搭环境。

#### ⏱ 13:00–15:00　Sprint 1：核心模块各自完成

| 人 | 任务 | 完成标准 (DoD) |
|---|---|---|
| **A** | 训练 XGBoost 模型，接入 SHAP，实现 `predict()`。实现 `gate.check()`：置信度 < 0.7、贷款金额 > 某阈值、年龄 < 25 的边缘案例都进人工队列 | `python -m loopledger.model` 能打印 5 条 Prediction，其中约 20% 被闸门拦下 |
| **B** | `ledger.py`：建表、`log_event` 计算哈希链、`submit_review`、`verify_chain`。写 `demo_reset.py` | 写入 20 条事件，`verify_chain()` 返回 True；手动改一条记录后返回 False 和断裂位置 |
| **C** | 用**假数据**（硬编码几个 Prediction）做好 `2_Review_Queue.py`：卡片显示申请信息、AI 建议、置信度条、SHAP 条形图，三个按钮，必填理由框，自动计时 | 页面能跑，点击提交会打印 ReviewAction |
| **D** | 写法规映射表（Art.12/13/14、ISO 42001）。写 `evidence_report.md.j2` 模板。**开始做海报草稿**（问题 → 方案 → 架构图 → 指标 → 法规） | 模板用假数据能渲染出完整报告 |

#### ⏱ 15:00　🔄 检查点 1（15 分钟）
- [ ] 各分支合并到 main
- [ ] **端到端打通一次**：A 生成预测 → 闸门拦截 → B 写入数据库 → C 页面显示 → 审批 → 写回数据库
- [ ] 有阻塞问题当场解决

> 15:00–16:00 有 Careers Fair。**最多派 1 个人去**（建议 D），其他人继续写代码。

#### ⏱ 15:15–17:00　Sprint 2：指标 + 剩余页面

| 人 | 任务 | 完成标准 (DoD) |
|---|---|---|
| **A** | `gold.py`：从数据集挑出 AI 判错的案例，或者故意翻转结论，作为金标准题，按约 10% 的比例混进队列。帮 B 想清楚各指标的阈值 | 队列里能看到金标准题（审核员看不出来，后台有标记） |
| **B** | `metrics.py`：计算平均审阅时长、override rate、金标准题检出率、短理由比例，并给出 flag（🟢/🟡/🔴）。`system_stats()` | 跑两个模拟审核员（一个认真，一个秒批），flag 能正确区分 |
| **C** | `1_Run_Batch.py`（滑块选数量 → 运行 → 显示自动通过和送审的数量）。`3_Oversight_Dashboard.py`（每个审核员的指标表、红绿灯、审阅时长分布图） | 页面接入真实数据 |
| **D** | `evidence.py` 接入真实数据库，生成报告。在 `4_Compliance.py` 上加"导出"按钮（与 C 配合）。**写 pitch 稿初版**（30 秒电梯版 + 3 分钟完整版） | 点按钮能下载 Markdown 报告 |

#### ⏱ 16:45　🔄 检查点 2（15 分钟）
- [ ] 合并到 main，**完整跑一遍 Demo 剧本**（见 LoopLedger.md 第 6 节）
- [ ] 列出明天要修的 bug 和要打磨的地方
- [ ] 确认今晚谁做什么（可选）

#### 🌙 今晚（可选，轻量）
- D：完成海报和 pitch 稿
- C：调整 UI 样式（配色、Logo、标题）
- 其他人：**休息**，明天还有硬仗

---

### Day 2（明天）

#### ⏱ 09:00–10:00　Sprint 3：收尾
| 人 | 任务 |
|---|---|
| **A** | 生成一份**基准实验结果**：闸门拦截率、被拦截案例中 AI 的出错率（证明闸门确实拦住了高风险案例），画图给 D 放进海报 |
| **B** | 在 `4_Compliance.py` 加篡改检测按钮：显示 ✅ Chain intact 或 ❌ Tampered at #N。写好一个"模拟篡改"的脚本供演示用 |
| **C** | UI 打磨。首页 `app.py` 放产品介绍和架构图 |
| **D** | 证据报告导出 PDF（可选，Markdown 也行）。打印海报，或者准备好平板展示 |

#### ⏱ 10:00　🔒 代码冻结
> 之后**只修 bug，不加功能**。

#### ⏱ 10:00–11:00　彩排
- [ ] 全员轮流讲一遍 3 分钟 pitch（**4 个人都要会讲**，因为桌前至少要留 2 人，大家会轮换）
- [ ] 准备评委常见问题的回答（见第 6 节）
- [ ] 用 `demo_reset.py` 重置数据，确认两台机器都能跑
- [ ] 提前录一段备用演示视频，防止现场出问题

#### ⏱ 11:00–12:00　午餐 + 布置展台

#### ⏱ 12:00–14:00　展台展示
- 桌前**至少 2 人**，建议 D 加一位技术同学固定在桌前，另外两人每 30 分钟轮换一次

---

## 5. 风险与应对

| 风险 | 应对 |
|---|---|
| SHAP 装不上或太慢 | 改用 XGBoost 自带的 `feature_importances_`，或者逻辑回归的系数 |
| 集成时接口对不上 | 严格按第 3 节的契约开发，**改契约需要全员同意** |
| Streamlit 状态管理混乱 | 所有状态都存 SQLite，不依赖 `session_state` 存业务数据 |
| 时间不够 | 按第 7 节的优先级砍功能 |
| 现场网络或电脑出问题 | 全部本地运行，不依赖外部 API；准备备用机和录屏 |

---

## 6. 评委可能问的问题（D 准备，全员熟悉）

1. **"这和普通的审批流程工具有什么区别？"** → 普通工具只记录"有人批了"，我们**证明监督是有效的**（检测 automation bias），并且自动生成合规证据。
2. **"金标准题会不会让审核员反感？"** → 这在航空安检、内容审核里是成熟做法（比如安检的 TIP 威胁图像投影）。而且可以公开告知审核员会有抽检，这本身就能提升专注度。
3. **"阈值怎么定？"** → Demo 里用的是经验值；实际使用时由企业根据自身风险偏好配置，系统会记录每次阈值变更（这本身也是合规证据）。
4. **"哈希链能防止什么？"** → 防止事后篡改审计记录。如果要求更高，可以定期把链头 hash 锚定到外部可信时间戳服务。
5. **"怎么扩展到 LLM Agent？"** → 风险闸门是通用的，只要把"贷款预测"换成"Agent 要执行的操作"（发邮件、导出数据等）就行。
6. **"谁会付钱？"** → 部署高风险 AI 的银行、保险、HR、公共部门，EU AI Act 第 14 条是它们必须满足的硬性要求。

---

## 7. 功能优先级（时间不够时从下往上砍）

| 优先级 | 功能 | 说明 |
|---|---|---|
| **P0 必须有** | 模型 + 闸门 + 审批界面 + 哈希链日志 | 没有这些就没有 Demo |
| **P0 必须有** | 监督质量 Dashboard（时长 + override rate + 红绿灯） | 核心差异化 |
| **P1 应该有** | 金标准题检出 | 让差异化更有说服力 |
| **P1 应该有** | 证据报告导出（Markdown） | ComplyFlow 部分 |
| **P1 应该有** | 篡改检测演示 | 现场效果好 |
| **P2 加分项** | PDF 导出、基准实验图、`@require_oversight` SDK 示例 | |
| **P3 有空再做** | 多审核员登录、LLM 给理由质量打分 | |

---

## 8. 检查点速查

| 时间 | 事件 | 必须达成 |
|---|---|---|
| Day 1 12:00 | 对齐完成 | 仓库建好，接口契约确认 |
| Day 1 15:00 | 检查点 1 | 端到端打通一条数据 |
| Day 1 17:00 | 检查点 2 | Demo 剧本能完整跑通 |
| Day 2 10:00 | 代码冻结 | 只修 bug |
| Day 2 11:00 | 彩排完成 | 4 人都能讲 pitch |
| Day 2 12:00 | 🎤 展示开始 | |
