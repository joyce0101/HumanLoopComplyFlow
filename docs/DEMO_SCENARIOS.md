# LoopLedger 演示场景与操作脚本

建议时长：约 12 分钟。更新日期：2026-10-25。

目标：用一条连续流程展示模型分流、人工复核、审核行为对照，以及审计证据。审核只使用批准／拒绝。明确区分真实模型输出、预设控制题和合成审核历史。

## 1. 演示前准备

在项目根目录、已安装项目依赖的 Python 环境下运行。整场演示只使用项目根目录的 `loopledger.db`，不创建临时数据库。

**每次演示或彩排前，都必须清空上一轮记录、重新初始化，并从场景一完整重演。** 不沿用上次的批次、审核记录或待审队列。

先在运行 8503 服务的终端按 `Ctrl+C` 停止服务，再执行下面的准备命令。**命令会清空 `loopledger.db` 的现有申请和审计事件并重建本轮演示数据；不创建备份。**

```bash
python scripts/demo_reset.py --db loopledger.db --force --profile functional
LOOPLEDGER_DB_PATH=loopledger.db python - <<'PY'
from loopledger import ledger
from loopledger.schemas import ReviewAction

for pred, decision in zip(ledger.get_pending_reviews(), ("approve", "reject")):
    ledger.submit_review(ReviewAction(
        pred.case_id, "demo_judge", decision,
        "Checked the application and supporting evidence.", 35.0,
    ))
print("Chain check:", ledger.verify_chain())
PY
```

重置命令先生成合成对照数据，随后 Python 代码完成其中两条待审申请，得到每轮一致的起点：**16 条合成申请、14 次审核、46 条事件、0 条待审**。这些是本轮重新生成的预置历史，供场景五对比审核行为。

确认命令无报错且输出 `Chain check: (True, None)` 后，再启动页面。准备失败时先排查，不继续运行批处理。

终端 A：启动正式演示页面。

```bash
LOOPLEDGER_DB_PATH=loopledger.db python -m streamlit run app.py --server.port 8503
```

打开或刷新 http://127.0.0.1:8503/，确认总申请数为 16、已审核为 14、待审核为 0，然后从场景一开始。现场所有新操作统一使用 `live_reviewer`，避免改变预置对照。

每轮完整重演的计数检查点如下（场景二、三、四各提交一次审核）：

| 检查点 | 申请总数 | 已审核 | 待审核 | 审计事件 |
| --- | --- | --- | --- | --- |
| 演示前初始化完成 | 16 | 14 | 0 | 46 |
| 场景一运行 50 条批处理后 | 66 | 14 | 18 | 146 |
| 场景二至四完成三次审核后 | 66 | 17 | 15 | 149 |

固定当前数据集和模型文件，不在现场重新训练。正式演示前彩排一次，并记录将要选择的 Application 显示编号；每次新批次的原始编号和 APP 显示编号都会变化。

## 2. 六个主线场景

### 场景一：高置信度申请自动分流，约 1.5 分钟

**页面：Run Batch。** 选择 50 条，勾选“Assume identity verified for this dataset demo”，运行一次。

当前本地模型和固定抽样已验证：45 条真实模型申请、5 条合成控制题；27 条自动批准、5 条自动拒绝、18 条转人工。若数据集或模型文件变化，应重新彩排，以实际页面结果为准。

可讲解的真实模型样本：

| 金额（数据集单位） | 期限 | 年龄 | 模型建议 | 模型置信度 | 路由 |
| --- | --- | --- | --- | --- | --- |
| 1,237 | 6 个月 | 27 岁 | 批准 | 97.84%，界面约 98% | 自动批准 |
| 2,511 | 15 个月 | 23 岁 | 拒绝 | 71.50%，界面约 72% | 自动拒绝 |

讲解：“自动分流可以批准，也可以拒绝。需要人工处理与否，由风险闸门决定；身份已验证也不表示贷款已经获批。”

预置库已有 16 条，所以本批次显示 50 条，系统累计显示 66 条是正常现象。现场只运行一次，避免重复批次干扰计数。

### 场景二：模型不确定，审核员查看证据再作决定，约 1.5 分钟

**页面：Review Queue。** 选择一条普通、低置信度的申请。

真实模型示例：金额 9,271，期限 36 个月，年龄 24 岁；AI 建议拒绝，置信度 53.38%，触发低于 0.70 的人工审核规则。它属于前述 50 条批次。

操作：

1. 查看信用记录、账户、储蓄、工作和还款信息。
2. 在十项贡献因素上悬停两次，展示字段含义、原始值与影响方向。
3. 以 `live_reviewer` 填写与所查看信息对应的理由，演示提交一次批准或拒绝。

理由示例：`Checked the recorded credit history, savings and repayment term before deciding.`

讲解：“低置信度触发人工复核，不直接等于应当拒绝。审核员可以同意或推翻 AI；普通申请没有预设正确答案，不能仅凭人工推翻就认定 AI 错了。”

贡献值是 log-odds 贡献，不是每个因素各自的可信度或概率；整体 Confidence 单独显示。

### 场景三：高置信度建议也可能违反演示规则，约 2 分钟

**页面：Review Queue。** 选择带 GOLD 标记、金额 25,000 且缺少额外证明的控制题。

| 项目 | 预设内容 |
| --- | --- |
| 身份标记 | 已验证 |
| 额外证明 | `extra_proof=False` |
| 展示的 AI 建议 | 批准 |
| 展示的置信度 | 95%，脚本预设 |
| 正确演示动作 | 拒绝 |

操作：查看 Application evidence，指出金额与证明信息，填写理由并拒绝。

理由示例：`The requested amount exceeds the demo threshold and additional supporting evidence is missing.`

讲解：“这个控制题故意给出错误建议。高置信度不能替代对约束和证据的检查；这里的 95% 是控制题设定，不是实测模型性能。”

控制题始终进入人工队列，金额规则也会触发复核。这类样例没有模型特征贡献，不应补造十项解释。

备选：金额 3,000、身份未验证、AI 建议批准的控制题；按当前演示答案应拒绝。两者可任选一个作为主展示，另一个用于问答。

### 场景四：AI 正确时，人工也可以同意，约 1 分钟

**页面：Review Queue。** 选择金额 2,500、场景为“所有演示政策检查通过”的控制题。

AI 建议批准，预设答案也是批准。查看证据后，以 `live_reviewer` 批准。

讲解：“人工审核并不要求每次推翻 AI。该题用于展示正确建议的对照；它不计入 Gold catch rate，因为 AI 在这道题上没有犯错。”

如果现场只审核了场景二、三、四，live_reviewer 共 3 次审核，只有场景三是已审的 AI 错误控制题：答对后检出率为 1/1=100%，Gold checks 为 1，状态仍应是样本不足。正确对照题答错也不会降低当前错误检出率；不要把该指标描述为全部金标准题准确率。

### 场景五：区分认真审核、机械跟随与样本不足，约 2 分钟

**页面：Oversight Dashboard。** 刷新指标，对比预置合成审核历史。

| 审核员 | 审核数 | 平均用时 | 推翻率 | 错误控制题检出率 | 短理由率 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| careful_reviewer | 6 | 50 秒 | 50% | 3/3=100% | 0% | 绿色，无经验规则告警 |
| rubber_stamp | 6 | 2 秒 | 0% | 0/3=0% | 100% | 红色，建议复核 |
| demo_judge | 2 | 35 秒 | 50% | 无有效错误控制题 | 0% | 灰色，样本不足 |

操作：悬停 Flag reasons 列表头，解释速度、短理由、零推翻和控制题漏检的组合；展示用时图与分布。

讲解：“同样是人在点击审批，观察到的行为可以不同。红色是需要复核的信号，绿色仅表示未触发经验规则。现场新审核员即使暂时 100%，样本少也不能据此认为监督有效。”

以上数字来自预置合成历史，不能说成真人实验结果。当前 GOLD 标记可见，是受控演示，不能据此宣称完成隐藏抽检或验证了真实审核能力。

### 场景六：从审核结果到可检查的证据，约 2 分钟

**页面：Compliance。**

1. 在 8503 的干净库页面点击 Verify chain，展示通过。
2. 生成报告，预览当前申请、审核和指标，下载 Markdown 与 JSON。
3. 报告下载完成后，在终端 A 按 `Ctrl+C` 停止 8503 服务。直接修改根目录 `loopledger.db` 中第 10 条事件的 payload，保留原 hash：

```python
import json
import sqlite3
from pathlib import Path

from loopledger import ledger

assert ledger.verify_chain() == (True, None), "先确认原始事件链通过"
with sqlite3.connect(Path("loopledger.db").resolve()) as db:
    row = db.execute("SELECT payload FROM events WHERE id = 10").fetchone()
    assert row is not None, "数据库中不存在第 10 条事件"
    payload = json.loads(row[0])
    payload["_demo_tamper_marker"] = "manually_changed_for_demo"
    db.execute(
        "UPDATE events SET payload = ? WHERE id = 10",
        (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),),
    )

print("Chain check:", ledger.verify_chain())  # 预期为 (False, 10)
```

4. 确认输出为 `(False, 10)` 后，仍使用同一个 `loopledger.db` 重启页面：

```bash
LOOPLEDGER_DB_PATH=loopledger.db python -m streamlit run app.py --server.port 8503
```

5. 在 http://127.0.0.1:8503/ 的 Compliance 页面校验，展示“发现异常，首个失败事件 #10”。生成的异常证据报告应明确显示 FAIL，仍可下载留存。

讲解：“我们既记录业务结果，也检查记录的一致性。改动一条本地事件能被发现，但本地哈希链并不等于不可篡改存储，也不证明事件完整或系统已经获得合规认证。”本场演示结束时，根目录数据库的事件链处于故意损坏状态；下次演示前重新执行第 1 节的初始化命令，即可从场景一开始并恢复完整链。

## 3. 现场顺序与准备检查

- 每次演示或彩排都先停止服务，执行第 1 节全部准备命令，再启动页面并从场景一开始；不要跳过重置或复用上一轮进度。
- 前半段展示一轮真实模型批次及三次人工操作；后半段查看预置行为对照、导出报告，并直接检查被修改的根数据库。
- 暂不将“授权例外与 AI 拒绝矛盾”的控制题作为主案例：当前场景文案暗示应推翻 AI，入库标准答案却同为拒绝，题意与答案尚需统一。
- 现场审核理由写完整，使用新审核员名称；不修改预置审核历史来凑颜色或分数。
- 演示全程只启动 8503；直接修改数据库前先停止服务，修改后再用相同路径重启，避免应用连接占用或页面显示旧状态。
- 路径、模型和 Python 环境提前确认；浏览器中只保留必要页面，避免连错数据库或端口。
- 本轮报告在场景六重新生成并下载；不要把上一轮下载的报告当成本轮结果。场景六直接修改本轮的根数据库，下次演示准备步骤会清空并重建它。

## 4. 已做的验证

纯预览调用当前 `run_mixed_batch(50, identity_verified=True)` 时，确认 45 条模型申请、5 条控制题及 27/5/18 的分流结果。该结果不写入数据库；正式演示时在场景一通过页面将批次写入根目录 `loopledger.db`。正式演示前仍需彩排完整浏览器操作。
