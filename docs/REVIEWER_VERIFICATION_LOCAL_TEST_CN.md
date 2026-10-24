# LoopLedger 强制登录 → 活体检测 → 业务访问：Windows 本地测试

## 关键修复

- 当前所有页面（`app.py`、Run Batch、Review Queue、Oversight Dashboard、Compliance）均强制执行 `require_workspace_access()`，不是只有 Review Queue 才登录。
- **默认**使用 `camera`；无需设置任何环境变量。出于安全和演示一致性，`off` 已被删除。你如果曾经设置过 `LOOPLEDGER_REVIEWER_VERIFY_MODE=off`，请在当前终端改为 `camera`。旧的 `LOOPLEDGER_LIVENESS_MODE` 被忽略。
- 进入业务系统必须完成 **Step 1 登录账号 → Step 2 摄像头/行为挑战 → 解锁工作区**。
- 成功解锁后工作区会话有效 20 分钟；注销或过期后需要重做验证。切换账号时不能沿用旧验证。
- 进入 Review Queue 后，**每笔申请的最终审批还要做该申请的独立挑战**，通过后审核按钮才会启用，审核仍绑定一次性签名凭证。
- 依然不进行生物特征注册比对。账号登录证明账户控制权，活体挑战提供交互迹象；两者都不等于真实实名身份确认。

## 1. 安装

在 Windows 本机 VS Code PowerShell 项目根目录中：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-verification.txt
python scripts/download_liveness_model.py
python scripts/diagnose_verification.py
```

下载模型的脚本已经修复 Windows `NamedTemporaryFile` 未关闭导致的 `WinError 32`。模型应出现在 `models/face_landmarker.task`，由模型官方 CDN 下载（本包不含模型二进制文件）。

## 2. 测试代码

```powershell
python -m pytest tests/test_liveness.py tests/test_reviewer_verification.py tests/test_workspace_access.py -v
```

上述测试检验挑战的逻辑状态、数据库审计、签名凭证、全页面入口校验（静态）、未登录阻断、账号切换和令牌过期。它们**不会**自动测试真实摄像头或 Windows 光标采集精度。

## 3. 开启 camera 模式

```powershell
$env:LOOPLEDGER_REVIEWER_VERIFY_MODE = "camera"
$env:LOOPLEDGER_DB_PATH = Join-Path (Get-Location) "workspace-gate-local-test.db"
python scripts/demo_reset.py --db $env:LOOPLEDGER_DB_PATH --empty
python -m streamlit run app.py
```

注意：`demo_reset.py` 拒绝覆盖已存在的 DB，如果已经测试过，请更换测试 DB 文件名。**不要**用 `--force` 覆盖原始数据。

### 预期页面顺序

1. 启动后进入 `LoopLedger — Access control`：**Step 1 / 2 Reviewer account login**，普通页面内容不显示。
2. 新用户选择 Create test reviewer 注册用户名（3–32 字符）与密码（至少 10 字符）；随后 Sign in 登录。
3. 登录完成页面变为 **Step 2 / 2 — Complete verification to enter**，此时即使点击侧边栏 Run Batch / Dashboard，也应该仍然被拦回该验证页面。
4. 勾选摄像头分析同意，点击 **Start new verification**，点摄像头框中的 **START**，允许访问摄像头。
5. 正视摄像头，**眨眼两次 → 向一侧转头并回正 → 向另一侧转头并回正**。刷新状态后看到 `Face challenge: passed`。
6. 点击 **Finish verification and enter workspace**。此后首页和四个业务页面解锁。
7. 在 Run Batch 生成 10 笔申请。在 Review Queue 中，选申请后必须重新完成这一申请的单独挑战才能解锁批准/拒绝按钮；提交后在 Compliance 检查哈希链 `PASS`。
8. 点击右侧 **Log out**，应立即回到登录页面。过期/换账号也必须重新验证。

## 4. full 模式：再加 Windows 鼠标轨迹和屏幕对照

在 Streamlit 终端按 Ctrl+C，执行：

```powershell
$env:LOOPLEDGER_REVIEWER_VERIFY_MODE = "full"
python -m streamlit run app.py
```

`full` 仍按 **登录 → 摄像头+鼠标/屏幕验证 → 进入业务 → 每笔审核前独立验证** 的顺序运行。务必在审核员的同一台 Windows 电脑上通过 localhost 浏览器访问：操作系统鼠标坐标与 screen capture 来源于运行 Streamlit 的服务器电脑，不适用于异地客户端。

鼠标/屏幕对照要求在采集中有足够移动距离、至少四次可检测可见指针对照，以及符合阈值的匹配率。显卡/WinRT 不支持指针叠加采集时 full 模式会阻止解锁，应先切回 camera 进行功能测试；检测失败不能证明欺诈。

## 5. 重要限制

- Python UI 已强制先验证后操作，**但 Python 后端的 `ledger.submit_review()` 等底层 API 仍可由可信本地脚本直接调用**。不能声称这是生产级权限系统。
- WebRTC/MediaPipe 的动作验证无法保证抵御回放/Deepfake，且不比对真实身份证明，也不能把鼠标轨迹当作可靠的机器人识别结论。
- 一次挑战通过后解锁 20 分钟；这只是本地会话授权政策，不等于持续监控。
- 摄像头视频和屏幕图像不作为审计数据持久保存；只在对应审计事件保存必要的非图像统计证据。
- 新版 `scripts/download_liveness_model.py` 修复了 Windows 文件占用导致的替换失败问题。
- 尚未在真实 Windows 摄像头和 WinRT 设备上做集成验证，需本机测试后再发布。
