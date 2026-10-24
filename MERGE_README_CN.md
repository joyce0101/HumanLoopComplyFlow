# LoopLedger 合并说明

## 默认合并入口

`python -m streamlit run app.py`

默认界面基于队友版本，**保留新版二元批准/拒绝流程**、完整特征解释和监管指标；接入了你的登录、人脸/活体检测、30 分钟工作区通行证、审核提交验证、批处理页面倒计时。

团队版本 Run Batch 的“假设申请人已验证”复选框继续保留，确保模拟样本路由行为不被悄悄更改。它与审核员人脸验证是不同的概念。

## 原版保留

`original_user_version/` 为你上传项目的独立副本，包括 **modify** 审核语义、原始批处理 UI 与人脸认证，可单独运行：

```powershell
cd original_user_version
python -m streamlit run app.py --server.port 8502
```

**两个版本不能同时连接同一个数据库**，因为二者对 `modify` 审核动作的数据契约不同。默认合并版使用根目录 `loopledger.db`，原版使用其自己的数据库。

## 环境

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-verification.txt
$env:LOOPLEDGER_REVIEWER_VERIFY_MODE = "camera"
python -m streamlit run app.py
```

## 差异与限制

- 队友版和你的版的 `modify` / binary approval 规则不同，无法同时设为默认语义。本包保留双版本，未擅自更改业务判断。
- 主入口已经融合身份验证，但完整 Windows 摄像头端到端测试需要在目标机器执行。
- 数据库文件只作为各自版本自带的演示数据，建议提交生产仓库时移除本地账号和数据库文件。
