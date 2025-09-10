# API下载接口修改方案

## 问题描述

当前的`/result/{task_id}`接口直接使用`FileResponse`返回PLY文件，但由于使用Cloudflare隧道，存在以下问题：
- 单次请求有100秒超时限制
- 大文件（如100MB的PLY文件）容易超时
- 用户体验差，下载失败率高

## 解决方案

### 方案概述
将原有的直接文件下载改为两步式下载：
1. `/result/{task_id}` - 返回文件信息和下载链接
2. `/download/{file_id}` - 实际的文件下载接口

### 具体实现

#### 1. 修改现有接口

**原接口**: `/result/{task_id}`
- **原返回**: `FileResponse` (直接下载文件)
- **新返回**: JSON格式的文件信息和下载链接

```json
{
  "task_id": "uuid",
  "status": "completed",
  "files": {
    "point_cloud": {
      "filename": "point_cloud.ply",
      "size": 104857600,
      "download_url": "/download/uuid_point_cloud",
      "created_at": "2025-01-09T10:30:00Z"
    },
    "cameras": {
      "filename": "cameras.json",
      "size": 2048,
      "download_url": "/download/uuid_cameras",
      "created_at": "2025-01-09T10:30:00Z"
    }
  },
  "processing_time": 120.5,
  "created_at": "2025-01-09T10:28:00Z",
  "completed_at": "2025-01-09T10:30:00Z"
}
```

#### 2. 新增下载接口

**新接口**: `/download/{file_id}`
- **功能**: 实际的文件下载
- **返回**: `FileResponse` 或 `StreamingResponse`
- **优化**: 支持断点续传、分块下载

#### 3. 文件ID映射

创建文件ID到实际文件路径的映射机制：
- `file_id` 格式: `{task_id}_{file_type}`
- 例如: `abc123_point_cloud`, `abc123_cameras`

### 实现步骤

1. **修改数据模型**
   - 创建文件信息响应模型
   - 更新TaskStatusResponse模型

2. **修改/result/{task_id}接口**
   - 移除FileResponse返回
   - 添加文件信息收集逻辑
   - 返回JSON格式的文件列表和下载链接

3. **新增/download/{file_id}接口**
   - 文件ID解析和验证
   - 文件存在性检查
   - 返回FileResponse或StreamingResponse

4. **更新前端调用方式**
   - 先调用/result/{task_id}获取文件信息
   - 再调用/download/{file_id}下载具体文件

### 优势

1. **解决超时问题**: 分离文件信息获取和文件下载
2. **更好的用户体验**: 可以显示文件大小、下载进度
3. **支持多文件**: 可以返回多个相关文件的下载链接
4. **便于扩展**: 后续可以添加压缩、分块下载等功能

### 兼容性

- 保持原有接口路径不变
- 返回格式改变，需要更新前端代码
- 可以通过版本控制实现渐进式迁移

## 实施计划

1. 修改后端API接口
2. 更新API文档
3. 测试新接口功能
4. 更新前端调用代码
5. 部署和验证