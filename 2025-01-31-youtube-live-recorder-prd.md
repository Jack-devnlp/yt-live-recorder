# YouTube Live Recorder - PRD 文档

**版本**: v1.0
**日期**: 2025-01-31
**状态**: 已确认

---

## 1. 产品概述

### 1.1 产品名称
YouTube Live Recorder (yt-live-recorder)

### 1.2 产品定位
面向主播粉丝的 YouTube 直播录制命令行工具，用于实时录制直播内容，方便后续制作切片视频。

### 1.3 核心场景
1. **单个直播间录制**：粉丝手动录制喜欢主播的当前直播
2. **多频道监控录制**：同时监控 1-5 个 YouTube 频道，自动检测开播状态并开始录制，停播时自动保存

### 1.4 目标用户
主播粉丝、内容创作者，希望通过录制直播制作切片视频分享到社交媒体

### 1.5 技术栈
Python >= 3.9 + yt-dlp + uv (依赖管理)，支持 Windows/Linux/Mac

---

## 2. 核心功能需求

### 2.1 功能 1：单个直播间录制

**功能描述**：用户输入 YouTube 直播链接，工具立即开始录制当前直播。

**命令示例**：
```bash
# 基础录制（持续录制直到手动停止或直播结束）
yt-recorder "https://www.youtube.com/watch?v=xxxxx"

# 指定输出目录
yt-recorder "https://www.youtube.com/watch?v=xxxxx" -o ./recordings

# 录制指定时长（例如30分钟）
yt-recorder "https://www.youtube.com/watch?v=xxxxx" -t 1800
```

**功能点**：
- 支持标准 YouTube 直播链接格式
- 自动检测直播流质量和可用性
- 按 `Ctrl+C` 优雅停止录制并保存文件

### 2.2 功能 2：多频道监控录制

**功能描述**：通过配置文件指定多个 YouTube 频道，工具持续监控并在开播时自动录制。

**命令示例**：
```bash
# 使用配置文件启动监控
yt-recorder --monitor -c config.yaml

# 指定轮询间隔（默认60秒）
yt-recorder --monitor -c config.yaml --interval 30
```

**配置文件示例**：
```yaml
channels:
  - name: "主播A"
    channel_id: "UCxxxxxxxxxx"
  - name: "主播B"
    channel_id: "UCyyyyyyyyyy"

settings:
  output_dir: "./recordings"
  quality: "best"  # best, 1080p, 720p
```

**功能点**：
- 支持 1-5 个频道同时监控
- 开播自动开始录制，停播自动保存并等待下次开播
- 按直播场次分段保存文件

### 2.3 功能 3：输出文件管理

**文件命名规则**：
```
{channel_name}_{YYYYMMDD}_{HHMMSS}.mp4
```

**示例**：
```
主播A_20250131_143022.mp4
主播A_20250131_160145.mp4  # 同一场直播断线重连后
```

---

## 3. 技术实现方案

### 3.1 架构设计

```
yt-live-recorder/
├── src/
│   ├── __init__.py
│   ├── cli.py              # 命令行入口
│   ├── recorder.py         # 核心录制逻辑
│   ├── monitor.py          # 多频道监控模块
│   ├── youtube_api.py      # YouTube 接口封装
│   └── utils.py            # 工具函数
├── config/
│   └── example.yaml        # 配置文件示例
├── recordings/             # 默认录制输出目录
├── pyproject.toml
└── README.md
```

### 3.2 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 直播流获取 | yt-dlp | 支持 YouTube 直播，维护活跃，可靠性高 |
| 视频录制 | yt-dlp | yt-dlp 原生支持 YouTube，无需额外依赖 |
| 配置文件 | YAML | 可读性好，支持注释 |
| Python 版本 | >= 3.9 | 兼容性和现代特性平衡 |
| **依赖管理** | **uv** | **速度快，支持 lock 文件，现代 Python 工具链** |

### 3.3 依赖管理（使用 uv）

**项目初始化**：
```bash
# 使用 uv 创建虚拟环境
uv venv

# 添加依赖
uv add yt-dlp pyyaml requests
```

**开发工作流程**：
```bash
# 安装所有依赖（包含 lock 文件锁定版本）
uv sync

# 运行项目
uv run yt-recorder --help

# 添加新依赖
uv add <package>

# 更新依赖
uv update
```

**pyproject.toml 配置**：
```toml
[project]
name = "yt-live-recorder"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
    "yt-dlp>=2024.1.0",
    "pyyaml>=6.0",
    "requests>=2.31.0",
]

[project.scripts]
yt-recorder = "src.cli:main"
```

### 3.4 核心流程

**单直播间录制**：
1. 解析 YouTube 链接，提取视频/频道 ID
2. 检查是否为直播中状态
3. 获取直播流地址（HLS/DASH）
4. 启动 yt-dlp 进行录制
5. 处理中断信号，优雅保存

**多频道监控**：
1. 加载配置文件
2. 为每个频道创建监控任务
3. 定期检查频道直播状态（轮询 YouTube）
4. 开播时启动录制任务
5. 停播时停止录制并保存
6. 循环监控

---

## 4. 使用方式

### 4.1 安装方式

**方式 1：从源码安装（推荐）**
```bash
# 克隆仓库
git clone https://github.com/user/yt-live-recorder.git
cd yt-live-recorder

# 使用 uv 创建环境并安装依赖
uv venv
uv sync

# 运行
uv run yt-recorder --help
```

**方式 2：直接运行**
```bash
# 临时运行，无需克隆
uvx --from git+https://github.com/user/yt-live-recorder.git yt-recorder
```

### 4.2 使用示例

**单个直播录制**：
```bash
# 基础录制
yt-recorder "https://www.youtube.com/watch?v=xxxxx"

# 指定输出目录和时长
yt-recorder "https://www.youtube.com/watch?v=xxxxx" -o ./my_clips -t 1800
```

**多频道监控**：
```bash
# 创建配置文件
cat > config.yaml << EOF
channels:
  - name: "PewDiePie"
    channel_id: "UC-lHJZR3Gqxm24_Vd_AJ5Yw"
  - name: "MrBeast"
    channel_id: "UCX6OQ3DkcsbYNE6H8uQQuVA"

settings:
  output_dir: "./recordings"
  quality: "best"
EOF

# 启动监控
yt-recorder --monitor -c config.yaml
```

---

## 5. 非功能性需求

| 类别 | 需求 |
|------|------|
| **稳定性** | 断线自动重连，录制不中断；网络恢复后继续录制 |
| **容错性** | 单个频道监控失败不影响其他频道；错误日志详细记录 |
| **资源占用** | 空闲时 CPU < 1%，内存 < 50MB；录制时资源占用合理 |
| **文件安全** | 异常退出时保留已录制内容；写入临时文件，完成后重命名 |
| **可维护性** | 结构化日志输出；配置文件热更新支持 |

---

## 6. Roadmap

### Phase 1 - MVP（2 周）
- [x] 单个 YouTube 直播链接录制
- [x] 基础命令行参数支持（-o, -t）
- [x] 信号处理（Ctrl+C 优雅退出）
- [ ] uv 依赖管理集成

### Phase 2 - 多频道监控（2 周）
- [ ] YAML 配置文件支持
- [ ] 1-5 频道轮询监控
- [ ] 开播/停播自动录制
- [ ] 按场次分段保存

### Phase 3 - 稳定性优化（1 周）
- [ ] 断线重连机制
- [ ] 日志系统完善
- [ ] 异常处理增强

---

## 7. 参考项目

本项目参考 [bilibili-live-recorder](file:///mnt/c/Users/XiongJie/bilibili-live-recorder) 的设计思路，针对 YouTube 平台进行适配。

---

**文档结束**
