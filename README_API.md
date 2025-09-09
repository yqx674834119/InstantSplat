# InstantSplat FastAPI 接口服务

基于 InstantSplat 的三维重建 FastAPI 接口服务，支持视频上传、帧提取和三维重建功能。

## 功能特性

- 🎥 支持多种视频格式（MP4/MOV/AVI）
- 🖼️ 智能帧提取（均匀采样或关键帧检测）
- 🏗️ 集成 InstantSplat 三维重建流程
- 📊 实时进度反馈和状态查询
- 🔄 异步任务处理
- 📝 完整的 API 文档
- 🛡️ 错误处理和验证

## 安装依赖

### 1. 安装 InstantSplat 依赖

```bash
# 安装原始 InstantSplat 依赖
pip install -r requirements.txt
```

### 2. 安装 API 服务依赖

```bash
# 安装 FastAPI 相关依赖
pip install -r api_requirements.txt
```

## 配置

### 环境配置

编辑 `config.py` 文件中的配置参数：

```python
# 基础配置
INSTANT_SPLAT_ROOT = "/home/livablecity/InstantSplat"  # InstantSplat 根目录
UPLOAD_DIR = "./uploads"                              # 上传目录
OUTPUT_DIR = "./outputs"                              # 输出目录

# 服务器配置
HOST = "0.0.0.0"
PORT = 8000

# 文件限制
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
ALLOWED_VIDEO_FORMATS = [".mp4", ".mov", ".avi"]

# 处理参数
N_FRAMES = 15  # 提取帧数
```

### CUDA 配置（可选）

如果有 GPU，可以配置 CUDA：

```python
# 在 config.py 中设置
CUDA_VISIBLE_DEVICES = "0"  # 使用第一块 GPU
```

## 启动服务

### 开发模式

```bash
python start_server.py --reload --log-level debug
```

### 生产模式

```bash
python start_server.py --host 0.0.0.0 --port 8000 --workers 1
```

### 自定义参数

```bash
python start_server.py --host 127.0.0.1 --port 8080 --reload
```

## API 使用

### 1. 上传视频并开始处理

```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
     -F "file=@your_video.mp4" \
     -F "n_frames=15" \
     -F "extraction_method=uniform"
```

响应：
```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "pending",
  "message": "任务已创建，开始处理"
}
```

### 2. 查询任务状态

```bash
curl "http://localhost:8000/api/v1/tasks/123e4567-e89b-12d3-a456-426614174000/status"
```

响应：
```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "processing",
  "progress": {
    "current_step": "模型训练",
    "percentage": 65.5,
    "estimated_time_remaining": 120.5
  }
}
```

### 3. 下载结果

```bash
# 下载 PLY 文件
curl "http://localhost:8000/api/v1/tasks/123e4567-e89b-12d3-a456-426614174000/download/ply" \
     -o result.ply

# 下载渲染视频
curl "http://localhost:8000/api/v1/tasks/123e4567-e89b-12d3-a456-426614174000/download/video" \
     -o result.mp4
```

### 4. 获取任务列表

```bash
curl "http://localhost:8000/api/v1/tasks?limit=10"
```

## API 文档

启动服务后，访问以下地址查看完整的 API 文档：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## 支持的视频格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| MP4  | .mp4   | 推荐格式，兼容性最好 |
| MOV  | .mov   | Apple 格式，质量较高 |
| AVI  | .avi   | 传统格式，文件较大 |

## 帧提取方法

### 1. 均匀采样 (uniform)
- 从视频中均匀间隔提取帧
- 适合大多数场景
- 处理速度快

### 2. 关键帧检测 (keyframe)
- 基于帧差检测提取关键帧
- 适合场景变化较大的视频
- 处理时间稍长，但质量更好

## 错误处理

### 常见错误码

| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| 400 | 请求参数错误 | 检查上传文件格式和参数 |
| 413 | 文件过大 | 减小文件大小或调整配置 |
| 422 | 视频格式不支持 | 转换为支持的格式 |
| 500 | 服务器内部错误 | 查看日志文件 |

### 任务状态说明

| 状态 | 说明 |
|------|------|
| pending | 等待处理 |
| uploading | 上传中 |
| validating | 验证中 |
| extracting | 提取帧中 |
| processing | 三维重建处理中 |
| rendering | 渲染中 |
| completed | 完成 |
| failed | 失败 |
| cancelled | 取消 |

## 性能优化

### 1. 硬件要求
- **CPU**: 4核以上推荐
- **内存**: 8GB以上推荐
- **GPU**: NVIDIA GPU（可选，显著提升速度）
- **存储**: SSD 推荐

### 2. 配置优化

```python
# 在 config.py 中调整
MAX_CONCURRENT_TASKS = 2  # 根据硬件调整并发数
RESIZE_MAX_DIMENSION = 1024  # 降低分辨率提升速度
ITERATIONS = 7000  # 减少迭代次数
```

### 3. 视频预处理建议
- 分辨率: 1080p 以下
- 时长: 30秒以内
- 帧率: 30fps 以下
- 场景: 避免快速运动和模糊

## 监控和日志

### 查看日志

```bash
# 实时查看日志
tail -f logs/api_server.log

# 查看错误日志
grep ERROR logs/api_server.log
```

### 监控任务

```bash
# 获取系统统计
curl "http://localhost:8000/api/v1/stats"
```

## 故障排除

### 1. 服务启动失败
- 检查端口是否被占用
- 确认依赖是否正确安装
- 查看配置文件路径

### 2. 处理失败
- 检查 CUDA 环境（如果使用 GPU）
- 确认 InstantSplat 环境正常
- 查看任务错误信息

### 3. 内存不足
- 减少并发任务数
- 降低处理分辨率
- 增加系统内存

## 开发和扩展

### 项目结构

```
InstantSplat/
├── api_server.py          # FastAPI 主服务
├── config.py              # 配置文件
├── video_processor.py     # 视频处理模块
├── task_manager.py        # 任务管理模块
├── reconstruction_processor.py  # 重建处理模块（需要创建）
├── start_server.py        # 启动脚本
├── api_requirements.txt   # API 依赖
└── README_API.md         # 本文档
```

### 添加新功能

1. 在相应模块中添加功能
2. 更新 API 端点
3. 添加测试用例
4. 更新文档

## 许可证

本项目基于 InstantSplat 项目，请遵循相应的许可证条款。

## 支持

如有问题，请：
1. 查看日志文件
2. 检查配置设置
3. 参考 API 文档
4. 提交 Issue