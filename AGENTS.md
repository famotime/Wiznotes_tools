# AGENTS.md

本文档旨在为接入本项目的编程 Agent 提供高密度的核心上下文，帮助快速理解项目架构、最新进展、执行命令及编码规范。

---

## 1. 项目定位与核心机制

本项目是**为知笔记（WizNote）批量导出与本地迁移工具集**，支持导出为标准 Markdown 并完整保留元数据与多媒体资源。

- **支持笔记类型**：
  - **HTML 笔记**：旧版富文本，通过 [`markdownify`](file:///d:/MyCodingProjects/Wiznotes_tools/export_wiznotes/note_exporter.py) 转为 Markdown，图片附件下载至同级 `<title>_assets` 目录。
  - **Lite Markdown 笔记**：新版轻量 Markdown，保留原生 Markdown 内容并提取元数据。
  - **协作笔记（`collaboration`）**：基于 WebSocket 协议拉取服务端 Delta JSON 块，经专用解析器转换为标准 Markdown。
- **元数据保留**：导出的 Markdown 文件顶部自动注入 YAML Front Matter（包含 `docGuid`、`title`、创建/修改时间、标签 `tags` 等）。
- **运行形态**：提供 **Web UI 模式**（FastAPI + Jinja2 + WebSocket 实时进度）与 **CLI 模式**（多线程并发 + 断点续传 + 靶向补导）。

---

## 2. 核心架构与模块导航

```
Wiznotes_tools/
├── get_wiz_notes.py              # CLI 批量导出主入口脚本（支持全量导出与靶向补导）
├── requirements.txt              # 项目全量依赖清单（根目录一键安装）
├── .env.example                  # 账号与服务器配置模板（复制为 .env）
├── export_wiznotes/              # 核心导出业务库
│   ├── wiz_client.py             # WizNote Web API 客户端（认证、网络容错、WebSocket）
│   ├── note_exporter.py          # 笔记下载、格式转换、资源处理与断点续传
│   ├── collaboration_parser.py   # 协作笔记 WebSocket Delta 块 Markdown 解析器
│   ├── get_folders_and_notes_list.py # 目录树与在线笔记清单拉取
│   ├── get_exported_mdfiles.py   # 本地已导出 Markdown 文件统计扫描
│   ├── compare_notes_in_folders.py # 在线与本地笔记清单对比分析（生成 compare_diff.txt）
│   ├── utils.py                  # 日志配置与通用工具
│   └── output/                   # 默认导出目标目录、断点与日志存储
└── web/                          # Web UI 模块 (FastAPI + WebSocket)
    ├── app.py                    # Web 服务启动入口（默认端口 8000）
    ├── models.py                 # Pydantic 请求与响应模型
    ├── routers/                  # API 路由（auth、folders、export、stats）
    ├── services/                 # 导出后台任务调度、目录树构建与校验服务
    └── templates/ & static/      # 前端 Jinja2 模板与静态资源
```

---

## 3. 最新开发进展与关键实现

1. **自建服务器（Docker / 私有部署）适配**：
   - [`WizNoteClient`](file:///d:/MyCodingProjects/Wiznotes_tools/export_wiznotes/wiz_client.py#L14) 支持读取 `WIZ_SERVER_URL`（默认官方云服务 `https://as.wiz.cn`）。
   - Web UI 登录界面新增服务器地址输入项，支持自建用户灵活接入。
2. **Token 失效无感自动重登**：
   - [`WizNoteClient._http_request`](file:///d:/MyCodingProjects/Wiznotes_tools/export_wiznotes/wiz_client.py) 底层统一拦截 401 与 Token 过期错误，通过 `_token_lock` 线程锁自动调用 `login()` 重新鉴权并自动重发请求，解决海量长时导出的中断问题。
3. **协作笔记代码块与多段文本解析增强**：
   - [`collaboration_parser.py`](file:///d:/MyCodingProjects/Wiznotes_tools/export_wiznotes/collaboration_parser.py) 修复了多行代码块及同一块内多个 Delta Insert 时文本截断问题，确保协作笔记完整解析。
4. **CLI 靶向补导机制**：
   - [`get_wiz_notes.py`](file:///d:/MyCodingProjects/Wiznotes_tools/get_wiz_notes.py) 新增 `--retry-diff` 参数。在运行对比工具生成 `compare_diff.txt` 后，可精准补录漏导笔记，无需重走全库遍历。
5. **智能目录容错与清单生成**：
   - [`get_wiz_notes.py`](file:///d:/MyCodingProjects/Wiznotes_tools/get_wiz_notes.py) 缺失 `为知笔记目录.log` 时自动通过 API 拉取全量目录，无需手工分步预执行。
   - [`get_folders_and_notes_list.py`](file:///d:/MyCodingProjects/Wiznotes_tools/export_wiznotes/get_folders_and_notes_list.py) 默认一次性自动生成目录日志与完整笔记清单。
6. **故障排查诊断增强**：
   - 登录失败时提供密码特殊字符双引号包裹、自建网络端口、以及官方客户端「二次验证（两步验证）」关闭排查指引。

---

## 4. 常用执行命令

```bash
# 1. 安装项目完整依赖
pip install -r requirements.txt

# 2. 配置账号（复制 .env.example 为 .env）
cp .env.example .env

# === 方式 A：Web UI 模式（推荐交互操作）===
python web/app.py
# 浏览器访问 http://127.0.0.1:8000

# === 方式 B：CLI 命令行模式 ===
# 批量导出笔记（自动拉取或读取 output/为知笔记目录.log）
python get_wiz_notes.py

# 对比在线笔记与本地已导出笔记的差异
python export_wiznotes/get_folders_and_notes_list.py
python export_wiznotes/compare_notes_in_folders.py

# 基于差异清单靶向补导缺失笔记
python get_wiz_notes.py --retry-diff
```

---

## 5. 关键编码规范与避坑原则

- **账号与二次验证**：为知 Web API 不支持开启「两步验证」的账号，调试登录前请确认该功能已关闭。
- **Windows 路径与文件名处理**：
  - 文件名中的非法字符必须经过 [`_get_valid_filename`](file:///d:/MyCodingProjects/Wiznotes_tools/export_wiznotes/note_exporter.py) 清洗（剔除 `\ / : * ? " < > |`）。
  - 原笔记标题中若含有 `.`（如版本号 `v1.0.2`），**严禁使用 `Path.with_suffix()`** 更改后缀，否则会导致文件名被误截断；必须显式字符串拼接 `.md`。
- **单目录超过 1000 篇笔记分页**：官方 API 单次查询上限 1000 篇，[`get_all_notes_in_folder`](file:///d:/MyCodingProjects/Wiznotes_tools/export_wiznotes/get_folders_and_notes_list.py) 采用升序+降序双向查询并按 `docGuid` 去重处理。
- **请求限速与断点续传**：
  - 导出单篇笔记后保留微小延时（0.5s）避免触发服务端频控。
  - 断点记录保存在每个文件夹下的 [`.export_checkpoint.json`](file:///d:/MyCodingProjects/Wiznotes_tools/export_wiznotes/note_exporter.py)，包含已导出的 `docGuid` 集合。
- **Web UI 与同步导出代码的桥接**：
  - `export_wiznotes` 均为同步阻塞逻辑，在 FastAPI 中须使用 `asyncio.to_thread()` 或 `threading.Thread` 调度，严禁在异步主循环中直接执行阻塞网络 IO。
