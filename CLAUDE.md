# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

为知笔记（WizNote）批量操作脚本工具集。核心功能是通过 Web API 批量导出为知笔记（支持 HTML 笔记、Lite Markdown 笔记、协作笔记），并提供笔记完整性校验。另有若干历史辅助脚本用于将剪贴板/图片等内容保存到为知笔记。

## 常用命令

```bash
# 安装依赖
pip install -r export_wiznotes/requirements.txt
pip install -r web/requirements.txt  # Web UI 额外依赖

# === Web UI 模式（推荐）===
python web/app.py  # 启动 Web 服务，默认 http://127.0.0.1:8000

# === CLI 模式 ===
# 生成文件夹列表和笔记清单（在 export_wiznotes 目录下运行）
cd export_wiznotes
python get_folders_and_notes_list.py

# 批量导出笔记（在项目根目录运行，读取 output/为知笔记目录.log）
python get_wiz_notes.py

# 统计已导出的本地笔记
cd export_wiznotes
python get_exported_mdfiles.py

# 对比在线笔记与已导出笔记的差异
cd export_wiznotes
python compare_notes_in_folders.py
```

## 架构

### 核心导出模块 (`export_wiznotes/`)

- **`wiz_client.py`** — 为知笔记 Web API 客户端。封装登录（获取 token）、文件夹列表、笔记列表（含超 1000 条双向查询去重）、笔记下载（含协作笔记 WebSocket 获取）、资源/附件下载、标签获取等接口。API 基地址 `https://as.wiz.cn`，认证通过 `X-Wiz-Token` header。
- **`note_exporter.py`** — 笔记导出主逻辑。按文件夹遍历笔记，下载内容并转换为 Markdown/HTML，自动下载图片和附件到 `_assets` 目录，添加 YAML front matter（包含 docGuid、创建/修改时间、标签等元数据），支持断点续传（`.export_checkpoint.json`）。
- **`collaboration_parser.py`** — 协作笔记解析。通过 WebSocket（`wss://`）协议获取协作笔记的 JSON 块结构，解析为 Markdown 格式（支持文本、列表、代码块、表格、嵌入块等类型）。
- **`utils.py`** — 日志配置（文件 DEBUG + 控制台 INFO）和文件夹/笔记列表工具函数。
- **`get_folders_and_notes_list.py`** — 导出为知笔记的文件夹结构和笔记清单到 `output/` 目录。
- **`get_exported_mdfiles.py`** — 扫描本地 `output/` 目录统计已导出的 md 文件。
- **`compare_notes_in_folders.py`** — 对比在线笔记清单与本地导出笔记清单，生成差异报告。

### Web UI 模块 (`web/`)

基于 FastAPI 的本地 Web 服务，通过浏览器完成所有笔记导出操作。

- **`app.py`** — FastAPI 应用入口，初始化 WebSocketManager、TaskManager、WebLogHandler
- **`deps.py`** — 共享 Jinja2Templates 实例（避免循环导入）
- **`config.py`** — 默认路径和配置常量
- **`models.py`** — Pydantic 请求/响应模型
- **`routers/auth.py`** — 登录/登出/配置端点（`POST /api/login`、`POST /api/login/from-file`）
- **`routers/folders.py`** — 文件夹树浏览（`GET /api/folders`）和笔记列表（`GET /api/folders/{path}/notes`）
- **`routers/export.py`** — 导出任务管理（`POST /api/export`）+ WebSocket 实时进度（`/ws/export/{task_id}`、`/ws/logs`）
- **`routers/stats.py`** — 统计扫描（`POST /api/stats/scan`）、对比（`POST /api/stats/compare`）、日志和断点查看
- **`services/export_service.py`** — TaskManager 管理导出线程，文件夹级取消粒度
- **`services/folder_service.py`** — 文件夹树构建（扁平路径→嵌套树）
- **`services/stats_service.py`** — 本地扫描、在线对比、日志/断点列表
- **`websocket_manager.py`** — WebSocket 连接池，支持日志流和任务进度广播
- **`logging_handler.py`** — 自定义 logging.Handler，通过正则解析日志消息提取结构化进度事件

**同步→异步桥接**: `export_wiznotes` 全部同步代码，通过 `asyncio.to_thread()` 包装快速操作，`threading.Thread` 运行长时导出，`asyncio.run_coroutine_threadsafe()` 将日志事件推送到 WebSocket。tqdm 在 Web 上下文中被替换为 noop。

### 主入口 (`get_wiz_notes.py`)

读取 `export_wiznotes/output/为知笔记目录.log` 中的文件夹列表，使用 `ThreadPoolExecutor`（默认 10 线程）并行导出每个文件夹的笔记。

### 笔记类型处理

- **HTML 笔记**（旧版）：下载 HTML 内容，用 `markdownify` 转换为 Markdown
- **Lite Markdown 笔记**（新版）：直接提取 Markdown 内容
- **协作笔记**（`type='collaboration'`）：通过 WebSocket 获取 JSON 块数据，由 `CollaborationParser` 解析为 Markdown

### 配置

账号配置文件路径为 `../account/web_accounts.json`（相对于项目根目录的上级目录），格式：
```json
{ "wiz": { "username": "email", "password": "password" } }
```

### 其他辅助脚本（项目根目录）

- `clipboard_notes_mailto_wiznotes.py` — 从剪贴板提取微信/头条等链接，通过邮件保存到为知笔记
- `image2wiz_by_yagmail.py` — 图片及 OCR 文本批量发送到为知笔记
- `create_wiznotes_with_webapi.py` — 通过 Web API 创建笔记
- `check_undone_imgs.py` — 检查未成功发送的图片文件

## 开发注意事项

- 路径处理兼容 Windows（`_get_valid_filename` 替换 `\ / : * ? " < > |`）
- API 单次最多返回 1000 条笔记，超大文件夹通过双向查询（降序+升序）+ GUID 去重处理
- 断点续传通过每 10 篇笔记保存一次 checkpoint 实现
- 导出时每篇笔记间隔 0.5 秒避免请求过快
- 文件名中的 `.` 可能导致 `Path.with_suffix` 截断问题，代码中直接拼接扩展名规避
