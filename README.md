# 答案之书

基于 Flask、SQLite 和原生 HTML/CSS/JavaScript 的手机优先答案之书。

## 本地运行

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

浏览器打开 `http://127.0.0.1:5000/`。SQLite 数据库默认创建在 `instance\answerbook.sqlite3`；初始化只使用 `CREATE TABLE IF NOT EXISTS`，不会重置表内记录。可用 `ANSWERBOOK_DATABASE` 指定其他路径。

默认时区为 `Asia/Shanghai`，可通过 `ANSWERBOOK_TIMEZONE` 更改。闰日生日在非闰年按 2 月 28 日庆祝。

## 用户资料与隐私

- 初次进入可登记姓名和生日；生日不通过公开接口返回。生日当天进入祝福流程时，系统仅向配置的管理员邮箱发送提醒，不向访客发送邮件。
- 回访需提供姓名和生日；如果两项完全相同的资料有多条记录，再要求一次性识别码。
- 识别码只在登记成功时显示一次，请用户自行保存。登录令牌保存在当前浏览器；SQLite 中只保存令牌和识别码的 SHA-256 摘要。
- 问题内容不会写入数据库。用户彩蛋发现记录和访问次数会持久保存。
- 生日祝福首次展示后，用户点击“收下祝福”才解锁普通提问；在确认前，答案 API 也会优先返回生日祝福。

## 非生日彩蛋

彩蛋通过问题内容、回访次数或概率触发，不会在页面公开具体关键词，供访客自行探索。触发后会先进入全屏主题揭晓仪式，再显示答案，并叠加专属粒子与提示音。粒子遵循系统减少动态效果设置，切换页面标签或开始下一个问题时会停止。背景音乐和提示音需浏览器首次交互后才能播放，也可通过声音开关关闭。彩蛋发现记录按访客保存，少数彩蛋仅能发现一次或需要多次回访。

## 指定问题审核

普通用户提交的问题会保存为 `pending`，未经审核不会参与答案匹配。审核管理接口默认关闭；设置强随机管理员令牌后启用：

```powershell
$env:ANSWERBOOK_ADMIN_TOKEN = "替换成足够长的随机秘密"
python app.py
```

管理员接口通过 `Authorization: Bearer <令牌>` 验证：

- `GET /api/admin/special-questions?status=pending`：查看待审申请。
- `PATCH /api/admin/special-questions/<编号>`，请求体示例：

```json
{"status":"approved","answer":"经审核的答案","review_note":"审核说明"}
```

拒绝时将 `status` 设为 `rejected`，可附 `review_note`。审核通过必须提供不超过 500 字的答案。被拒绝或待审核的问题都不会影响答案匹配。

## 音效与动态效果

- 音效由浏览器 Web Audio API 本地合成，不依赖外部音频文件或第三方音频资源。
- 背景音乐由本地 Web Audio 合成轻柔的空灵铺底、带停顿与转音的钢琴星点，以及间隔不规则的柔和低鼓点；在用户首次点击或按键后启动，并在页面使用期间持续播放。浏览器自动播放限制意味着打开页面时不会未经交互自动出声。
- 书本打开、翻页、答案、彩蛋、生日和按钮交互也有独立提示音。切换页面标签时暂停背景音乐，返回后在声音仍开启的情况下恢复。
- 页面上的声音开关会立即停止音效并保存偏好。浏览器或设备不支持 Web Audio 时，核心提问流程仍可正常使用。
- 页面也会根据系统的“减少动态效果”设置简化动画。

## 验证

```powershell
python -m unittest -v
```

## 邮件提醒

采用模式 A：访客生日当天首次进入生日祝福流程时，系统给管理员发送一封提醒；同一用户同一当地日期通过 SQLite 唯一约束去重。邮件包含姓名、生日月日和当地触发时间，主题固定，不含个人资料。缺少 SMTP 配置或发送失败不会阻塞访客，事件和失败原因类型会记录在数据库/日志中。新表由 `CREATE TABLE IF NOT EXISTS` 增量创建，不删除或重写现有用户数据。

### 配置

依赖清单包含 `python-dotenv`，应用启动时会读取项目根目录 `.env`。复制示例并在本机编辑：

```powershell
Copy-Item .env.example .env
notepad .env
```

设置以下值；`.env` 已被 `.gitignore` 排除，不能提交或分享：

QQ 邮箱（端口 465，隐式 SSL）示例：

```dotenv
MAIL_SERVER=smtp.qq.com
MAIL_PORT=465
MAIL_USE_TLS=false
MAIL_USE_SSL=true
MAIL_USERNAME=your-sender@qq.com
MAIL_PASSWORD=your-qq-mail-authorization-code
MAIL_DEFAULT_SENDER=your-sender@qq.com
ADMIN_EMAIL=your-admin@example.com
APP_TIMEZONE=Asia/Shanghai
ANSWERBOOK_ADMIN_TOKEN=replace-with-a-long-random-secret
```

- QQ 邮箱使用 `smtp.qq.com:465` 与隐式 SSL（`MAIL_USE_SSL=true`、`MAIL_USE_TLS=false`）。需在 QQ 邮箱设置中开启 SMTP 服务，并填写生成的**授权码**作为 `MAIL_PASSWORD`；这不是 QQ 登录密码。
- Gmail 使用 `smtp.gmail.com:587` 与 STARTTLS（`MAIL_USE_TLS=true`、`MAIL_USE_SSL=false`）。先为账号启用两步验证，再创建并填写**应用专用密码**；不要使用普通登录密码。
- Outlook.com 通常使用 `smtp-mail.outlook.com:587` 与 STARTTLS；需确保邮箱账号/组织策略允许 SMTP AUTH。具体以邮箱服务商当前配置为准。
- `MAIL_USE_TLS`（STARTTLS）和 `MAIL_USE_SSL`（隐式 SSL）不可同时设为 `true`。465 通常用隐式 SSL，587 通常用 STARTTLS。
- 密码只保存在本地 `.env` 或托管平台的环境变量中。不要把真实密码发到聊天、提交到代码仓库或填入 `.env.example`。
- `APP_TIMEZONE` 同时决定生日日期边界和邮件中的访问时间。若未配置邮件参数，网站仍可运行；生日事件会记为 `failed`，配置补齐后可由管理员手动重试。

### 事件审查和受控重试

配置 `ANSWERBOOK_ADMIN_TOKEN` 后，使用管理员 Bearer Token：

- `GET /api/admin/birthday-events?status=failed`：查看失败事件；`status` 可为 `pending`、`sent`、`failed`，省略则查看最近事件。
- `POST /api/admin/birthday-events/<事件编号>/retry`：重试单条失败邮件。每个事件最多尝试 3 次（首次发送加最多 2 次手动重试）；已发送或正在发送的事件不可重复领取。

示例（PowerShell）：

```powershell
# 将 .env 中设置的同一个值加载到当前 PowerShell 会话后再调用管理接口。
$env:ANSWERBOOK_ADMIN_TOKEN = "从本机 .env 安全复制的管理员令牌"
$headers = @{ Authorization = "Bearer $env:ANSWERBOOK_ADMIN_TOKEN" }
Invoke-RestMethod -Headers $headers `
  http://127.0.0.1:5000/api/admin/birthday-events?status=failed
Invoke-RestMethod -Method Post -Headers $headers `
  http://127.0.0.1:5000/api/admin/birthday-events/1/retry
```

SQLite 默认文件为 `instance\answerbook.sqlite3`。停止 Flask 后备份数据库文件。生日提醒记录位于 `birthday_events` 表，含访客 ID、本地事件日期、触发时间、通知状态、尝试次数和非敏感错误类型；使用 SQLite 浏览器或 Python `sqlite3` 执行以下只读查询可检查状态：

```sql
SELECT id, user_id, event_date, triggered_at, notification_status,
       attempts, last_attempt_at, sent_at, last_error_code
FROM birthday_events
ORDER BY event_date DESC, id DESC;
```

不要公开数据库文件。SMTP 没有跨网络事务协议：若连接在服务器接受邮件后意外中断，人工重试存在极小的重复投递风险；因此没有自动循环重试，并限制每个事件的尝试次数。

目前通过模拟 SMTP 测试发送、去重和失败重试；未使用真实邮箱凭据，尚未验证真实邮件送达。
