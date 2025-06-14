# 为知笔记导出工具

从为知笔记读取信息，导出单篇或批量导出笔记的模块化工具。

## 功能特性

1. 登录为知笔记Web版
2. 获取指定文件夹下的笔记列表
3. 下载笔记内容并根据内容类型导出为markdown或html格式
4. 支持断点续传，避免重复下载
5. 自动处理文件名中的非法字符
6. 支持协作笔记的导出

## 项目结构

```
export_wiznotes/
├── __init__.py                 # 包初始化文件
├── get_wiz_notes.py           # 主程序入口
├── wiz_client.py              # 为知笔记客户端核心类
├── collaboration_parser.py    # 协作笔记解析模块
├── note_exporter.py           # 笔记导出模块
├── utils.py                   # 工具函数模块
├── requirements.txt           # 依赖包列表
├── README.md                  # 项目说明文档
├── output/                    # 默认导出目录
└── logs/                      # 日志文件目录
```

## 模块说明

### wiz_client.py
- `WizNoteClient`: 核心客户端类
  - 登录认证
  - 获取文件夹列表
  - 获取笔记列表
  - 下载笔记内容
  - 下载资源文件和附件
  - 获取标签信息

### collaboration_parser.py
- `CollaborationParser`: 协作笔记解析器
  - WebSocket通信
  - 协作笔记内容解析
  - 各种块类型解析（文本、列表、代码、表格等）

### note_exporter.py
- `NoteExporter`: 笔记导出器
  - 批量导出笔记
  - 断点续传功能
  - 文件名处理
  - YAML front matter生成

### utils.py
- `setup_logging`: 日志配置
- `list_folders_and_notes`: 文件夹和笔记列表功能

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. 配置文件

在上级目录的 `account/web_accounts.json` 中配置账号信息：

```json
{
    "wiz": {
        "username": "your_email@example.com",
        "password": "your_password"
    }
}
```

### 2. 运行脚本

```bash
cd export_wiznotes
python get_wiz_notes.py
```

### 3. 自定义使用

```python
from export_wiznotes import WizNoteClient, NoteExporter, setup_logging

# 设置日志
setup_logging("./output")

# 创建客户端
client = WizNoteClient("../account/web_accounts.json")
client.login()

# 创建导出器
exporter = NoteExporter(client)

# 导出笔记
exporter.export_notes(
    folder="/My Drafts/",
    export_dir="./output",
    max_notes=1000,
    resume=True
)
```

## 注意事项

1. 为知笔记API限制单次最多获取1000篇笔记，超过1000篇笔记的文件夹会自动进行两次查询
2. 导出过程支持断点续传，可以随时中断后继续；如果需要覆盖已导出文件，请删除导出目录下checkpoint文件
3. 协作笔记使用WebSocket通信，需要确保网络连接稳定
4. 导出的文件会保存在 `output` 目录下，日志文件保存在 `logs` 目录下

## 输出格式

- 普通笔记：同时生成 `.html` 和 `.md` 格式
- LiteMD笔记：生成 `.md` 格式
- 协作笔记：直接生成 `.md` 格式
- 资源文件：保存在 `{笔记名}_assets` 目录下
- 附件：同样保存在 `{笔记名}_assets` 目录下

## 版本信息

- 版本：1.0.0
- 支持Python 3.6+