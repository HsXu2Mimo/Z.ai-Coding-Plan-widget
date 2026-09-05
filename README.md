# Z.ai-Coding-Plan-
基于 Z.ai 创造的 Z.ai Coding Plan 用量面板

<img width="1222" height="515" alt="image" src="https://github.com/user-attachments/assets/e04fae08-67d8-4bac-8e16-56bbcf7892c3" />
<img width="395" height="977" alt="image" src="https://github.com/user-attachments/assets/887c0ae0-9475-4d13-86b5-d68808d146fe" />


[README.md](https://github.com/user-attachments/files/31863977/README.md)
# Z.ai Coding Plan 用量面板

一个零依赖的单文件网页 widget,实时显示不同 **Z.ai / 智谱 GLM Coding Plan**(Lite / Pro / Max,支持多账号、全球站与国内站)的用量情况。

![demo](#) <!-- 打开 index.html 即可看到演示数据效果 -->

## 功能

- **多账号 / 多套餐**:每个账号一张卡片,可分别选择 Z.ai 全球站(`api.z.ai`)或智谱国内站(`open.bigmodel.cn`)
- **5 小时窗口用量**:环形进度 + 重置倒计时(配额按 5 小时一个周期滚动重置)
- **每周 Token 用量 / MCP 月度用量**:进度条 + 重置倒计时
- **近 24 小时模型用量**:按模型(glmm-4.6 等)展示 token 分布
- **自动刷新**:1 / 5 / 15 / 30 分钟可选,也可手动刷新
- **演示模式**:未配置 Key 时默认展示三个示例账号(Lite / Pro / Max),方便预览
- **紧凑模式**:URL 加 `?compact=1` 变成小卡片,适合嵌入桌面 / 侧边栏

## 快速开始

### 1. 预览(演示数据)

直接双击打开 `index.html` 即可,无需任何配置。

### 2. 接入真实数据(三种方式任选其一)

**方式 A · 面板里直接粘贴(全局密钥,推荐)**

双击桌面快捷方式打开面板 → **⚙ 设置 → API Key(加密存储在本机)** → 粘贴 Key → 保存。
密钥经 **Windows DPAPI** 加密写入 `key.enc`(绑定当前 Windows 用户,磁盘上没有明文,
复制到别的电脑/用户也解不开),由本地服务在转发时自动注入请求头,所有浏览器通用。
在输入框留空点保存即可清除已存密钥。

**方式 B · 账号里单独填写(自动加密,支持多账号)**

**⚙ 设置 → 添加账号**,在账号的 Key 字段粘贴 Key,点保存。Key 会**自动**送入本机加密库
(DPAPI 加密写入 `key.vault.json`),浏览器 localStorage 里只保留加密引用(`keyRef`)和指纹,
磁盘与浏览器均无明文;已有明文 Key 会在打开面板时自动迁移。请求时浏览器携带引用句柄,
由本地服务解密注入,因此同一账号配置在所有浏览器通用。

**方式 C · key.txt 文件(明文兜底)**

把 Key 粘贴到 `key.txt`,本地服务检测到请求无凭证时自动使用;优先级低于 `key.enc`。

> Key 获取入口:全球站 <https://z.ai/manage-apikey/apikey-list>,国内站 <https://bigmodel.cn/console/usercenter-apikeys>(平台选"智谱国内站")。
> 密钥来源优先级:`ZAI_API_KEY 环境变量 > key.enc > key.txt > 账号加密引用(keyRef) > 账号明文 Key`。

### Coding Plan 有效期

- **自动探测**:接口返回中若包含常见有效期字段(`expireTime` / `endTime` / `deadline` 等),卡片自动显示"📅 有效期至 …(剩 N 天)"
- **手动设置**:⚙ 设置 → 账号 → "有效期(手动,可选)" 选择日期;手动值优先于自动探测,请求失败时也会显示
- 剩余 <7 天红色、<30 天琥珀色,过期显示"已过期 N 天"

### 用量数字(已用 / 总量)

- 每个窗口除百分比外同时显示 **已用/总量**,如 `🔢 20.6M / 27M token`、`≈57.2M / 135M · 42.4%`
- 总量来源优先级:**接口真实数值 > 账号手动上限 > 套餐预设 > 40M 默认**;按百分比换算的数字带 `≈`
- **套餐预设**(设置里可选"自动检测/Lite/Pro/Max",自动检测按接口返回的 level 字段匹配):

| 套餐 | 官方 prompts 额度(5h/周) | Token 总量估算(5h/周,社区推算) |
|---|---|---|
| Lite | ≈80 / 400 | 27M / 135M |
| Pro | ≈400 / 2,000 | 40M / 200M |
| Max | ≈1,600 / 8,000 | 160M / 800M |

- prompts 一栏是**官方数字**([额度调整公告](https://docs.z.ai/devpack/notice/usage-revision),2026-07-30,1 prompt ≈ 15-20 次模型调用);卡片上以"📋 Lite 额度:约 80 prompts/5h · 400/周"形式显示
- Token 口径官方未公布,预设值为社区估算([opencode-glm-quota](https://github.com/guyinwonder168/opencode-glm-quota) 默认 Pro 40M、社区按此推算 Lite ≈27M、Max 按 prompts 比例 ×4,周额度按 5×5h);若你从控制台得知实际数值,直接在账号设置里填写即可覆盖

### 3. 为什么需要本地服务

浏览器直连 `api.z.ai` 会被 CORS 拦截,`proxy.py` 就是为此准备的本地小服务(纯 Python 标准库),它同时做四件事:

- 托管面板页面:`http://127.0.0.1:8788/`
- 转发官方用量接口:`/proxy?url=<官方接口>`
- 全局密钥:`/key` 加密保存到 `key.enc` 并自动注入
- 账号密钥保险库:`/key/store` 为每个账号签发加密引用(`keyRef`),转发时按 `X-Key-Ref` 解密注入

桌面快捷方式(`启动用量面板.vbs`)会先静默启动该服务,再打开面板;端口已占用时服务直接退出,所以重复双击是安全的。

### 4. 嵌入为桌面小部件

```html
<iframe src="index.html?compact=1" style="width:380px;height:640px;border:0;border-radius:16px;"></iframe>
```

## 数据来源

widget 调用 Z.ai 官方用量接口(与 [opencode-glm-quota](https://github.com/guyinwonder168/opencode-glm-quota) 插件同源):

```
GET https://api.z.ai/api/monitor/usage/quota/limit      # 配额(5h / 每周 / MCP)
GET https://api.z.ai/api/monitor/usage/model-usage      # 近 24h 模型用量
Authorization: <你的API Key 原文,不带 Bearer 前缀>
```

配额响应结构(节选):

```json
{
  "data": {
    "level": "GLM Coding Pro",
    "limits": [
      { "type": "TOKENS_LIMIT", "unit": 3, "number": 5, "percentage": 42.5, "nextResetTime": 1757000000000 },
      { "type": "TOKENS_LIMIT", "unit": 6, "number": 1, "percentage": 21.0, "nextResetTime": 1757400000000 },
      { "type": "TIME_LIMIT",   "percentage": 9.1, "usageDetails": [{ "modelCode": "glm-4.6", "usage": 123456 }] }
    ]
  }
}
```

`unit=3, number=5` 是 5 小时窗口,`unit=6, number=1` 是每周窗口,`TIME_LIMIT` 是 MCP 月度用量。`nextResetTime` 为 Unix 毫秒时间戳。

## 安全说明

- API Key 只保存在你自己浏览器的 `localStorage`,不会发往任何第三方服务器
- 代理只允许转发到 `api.z.ai` / `open.bigmodel.cn` / `dev.bigmodel.cn` 三个官方域名,且只监听 `127.0.0.1`
- `model-usage` 接口官方未文档化,widget 做了防御性解析;取不到时自动隐藏该区块,不影响配额显示

## 文件

| 文件 | 说明 |
|---|---|
| `index.html` | widget 本体(HTML + CSS + JS,零依赖) |
| `proxy.py` | 本地服务:托管面板 + 转发接口 + 密钥管理(`/key`、`/key/store`) |
| `key.enc` | 全局密钥(DPAPI 加密;在面板设置里粘贴后生成) |
| `key.vault.json` | 各账号密钥保险库(每条均为 DPAPI 密文;账号填 Key 后自动生成) |
| `key.txt` | 可选的明文 Key 兜底方案 |
| `启动用量面板.vbs` | 桌面快捷方式的目标:启动服务并打开面板 |
| `panel.ico` | 快捷方式图标 |
