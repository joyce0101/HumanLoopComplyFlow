# LoopLedger

**Oversight that proves itself. — 会自证的人工监督。**

Synoptix Responsible AI Hackathon 项目，结合 **HumanLoop（AI 人工监督）** 与 **ComplyFlow（合规证据整理）**。项目以贷款审批分类器为演示场景，计划将高风险或低置信度的 AI 决策交给人工审核，记录审核过程，并生成可追溯的证据报告。

## 当前状态

仓库已建立项目目录、依赖清单和模块骨架，部分 Streamlit 页面已实现模拟交互。**前端可以启动，完整的审批业务流程尚未打通。**

| 内容 | 状态 |
| --- | --- |
| 项目方案、执行计划与接口契约 | 已写入文档 |
| Python 包、Streamlit 页面、报告模板与脚本 | 已建立基本结构，部分页面已有模拟交互 |
| HTML 交互原型 | 已有模拟数据原型，尚未接入 Python 模块 |
| 模型训练与风险闸门 | 已有逻辑回归模型及共享数据结构接口，可在批量页面预览 |
| 数据库与审计链 | 已有数据库初始化；业务读写及哈希链接口待完成 |
| 人工审批、监督质量指标与证据导出 | 已有会话审核、指标展示和模拟报告下载；数据库集成待完成 |
| 端到端验证与演示 | 待完成 |

## 计划实现的流程

1. **生成预测**：使用 German Credit 数据集训练贷款审批分类器，输出决策、置信度和特征贡献。当前实现为逻辑回归及各项对数几率贡献；XGBoost / SHAP 是原方案，尚未接入。
2. **风险分流**：由风险闸门检查预测，将需要人工判断的申请送入审批队列。
3. **人工审核**：展示申请信息和 AI 建议，记录审核员的操作、理由与审阅时长。
4. **记录证据**：使用 SQLite 保存业务状态与哈希链审计日志，并提供链完整性检查。
5. **观察监督质量**：计算审阅时长、推翻 AI 的比例、短理由比例和金标准题检出率，辅助识别监督异常。
6. **导出报告**：汇总事件、指标与项目文档中的法规映射，生成 Markdown / JSON 证据包；PDF 为可选扩展。

## 技术方案

实现以 [PLAN.md](./PLAN.md) 中的决策和接口契约为准。

| 部分 | 当前实现与计划 |
| --- | --- |
| 界面与应用入口 | Streamlit，直接调用 Python 模块，不单独启动 API 服务 |
| 模型与解释 | scikit-learn 逻辑回归及特征贡献；XGBoost / SHAP 为原计划 |
| 数据集 | 本地 German Credit 文件 `dataset/statlog+german+credit+data/german.data` |
| 持久化 | SQLite 单文件 `loopledger.db`，已实现初始化，前端业务持久化待接入 |
| 数据处理与图表 | pandas、Plotly |
| 报告模板 | Jinja2 |

## 项目结构

```text
HumanLoopComplyFlow/
├── README.md
├── LoopLedger.md                   # 项目方案与演示构想
├── PLAN.md                         # 分工、接口契约与验收要求
├── requirements.txt
├── app.py                          # Streamlit 入口
├── loopledger/
│   ├── __init__.py
│   ├── schemas.py                  # 共享数据结构
│   ├── model.py                    # 逻辑回归训练、预测与特征贡献
│   ├── gate.py                     # 风险闸门
│   ├── gold.py                     # 金标准测试题
│   ├── ledger.py                   # SQLite 与哈希链日志
│   ├── metrics.py                  # 监督质量指标
│   └── evidence.py                 # 证据包生成
├── pages/
│   ├── 1_Run_Batch.py              # 批量提交申请
│   ├── 2_Review_Queue.py           # 人工审批
│   ├── 3_Oversight_Dashboard.py    # 监督质量面板
│   └── 4_Compliance.py             # 证据导出与篡改检测
├── templates/
│   └── evidence_report.md.j2       # 证据报告模板
├── scripts/
│   └── demo_reset.py              # Demo 数据重置脚本
└── prototype/
    └── index.html                 # 使用模拟数据的交互原型
```

## 开发环境准备

需要 Python 3、Git，以及访问 GitHub 和 Python 包源的网络连接。以下为 macOS / Linux 命令：

```bash
git clone git@github.com:joyce0101/HumanLoopComplyFlow.git
cd HumanLoopComplyFlow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

SSH 克隆需要 GitHub SSH 密钥配置。也可使用 HTTPS 地址：

```bash
git clone https://github.com/joyce0101/HumanLoopComplyFlow.git
```

默认前端模拟模式不需要训练模型。批量页面的 **Model preview** 模式读取本地 German Credit 数据和已有模型文件；需要重新训练时，在项目根目录运行：

```bash
python -m loopledger.model --train
```

### 查看界面原型

用浏览器打开 [prototype/index.html](./prototype/index.html)。原型包含批量运行、审批队列、监督面板和证据页面，使用模拟数据；其中的统计、导出和链校验结果用于展示界面交互。页面样式依赖外部脚本，加载样式需要网络。

### 启动前端页面

完成上面的依赖安装并激活对应的 Python 环境后，在项目根目录（包含 `app.py` 的文件夹）运行：

```bash
python -m streamlit run app.py
```

例如，在当前这台 Mac 上，可以执行：

```bash
cd /Users/lanqiuying/Desktop/synoptix
python -m streamlit run app.py
```

队友使用自己的项目路径；Windows、macOS 和 Linux 的 Streamlit 启动命令相同。需要通过 `python -m streamlit run` 启动网页服务，直接执行 `python app.py` 不会启动前端网页。

启动后，浏览器通常会自动打开；如果没有，请打开终端显示的 `Local URL`，默认一般为 `http://localhost:8501`。通过左侧边栏切换页面：

- **Run Batch**：批量运行页面，可选择模拟数据模式。
- **Review Queue**：人工审核页面，可查看 AI 建议并提交审核决定。
- **Oversight Dashboard**：监督质量页面，可查看当前会话的演示指标。
- **Compliance**：可演示审计链校验状态、预览报告并下载 Markdown / JSON。默认 **UI demo** 使用模拟响应和报告，不代表真实数据库校验；后端模式依赖 B / D 接口完成集成。

当前 `app.py` 首页也仍为占位文件，首页正文可能为空；请从左侧边栏进入已实现的页面。模拟数据模式下的数据保存在当前浏览器会话中，不写入 `loopledger.db`，刷新或重新建立会话可能重置数据。

运行期间保持终端开启。在该终端按 `Ctrl+C` 可停止前端服务。`scripts/demo_reset.py` 尚未实现数据重置。

## 团队分工与协作

| 角色 | 负责内容 | 主要文件 |
| --- | --- | --- |
| A：ML 工程师 | 模型、解释、风险闸门、金标准题 | `model.py`、`gate.py`、`gold.py` |
| B：后端 / 数据工程师 | 数据库、哈希链、监督指标、数据重置 | `ledger.py`、`metrics.py`、`scripts/demo_reset.py` |
| C：前端工程师 | Streamlit 入口与全部页面 | `app.py`、`pages/` |
| D：合规 / 产品 / Pitch | 证据报告、法规映射、海报与演示 | `evidence.py`、`templates/` |

每人在独立分支开发，在计划检查点合并到 `main`。开发前先阅读 [PLAN.md](./PLAN.md) 第 3 节，按共享数据结构和函数签名实现；共享契约的改动需要全队确认。

## 文档

- [LoopLedger.md](./LoopLedger.md)：项目背景、目标流程、监督指标与演示构想。
- [PLAN.md](./PLAN.md)：技术决策、四人分工、接口契约、数据库设计与验收检查点。
