# InstantSplat 3D Reconstruction API 接口文档

## 概述

InstantSplat 3D Reconstruction API 是一个基于 FastAPI 的三维重建服务，支持从多张图像生成三维点云模型。API 提供了文件上传、任务状态查询、结果获取等功能。

**基础信息：**
- 服务地址：`https://app.scenegen.cn`
- API 版本：`1.0.0`
- 协议：HTTP/HTTPS
- 数据格式：JSON

## 数据模型

### TaskStatusResponse
任务状态响应模型
```json
{
  "task_id": "string",
  "status": "string",
  "progress": 0.0,
  "current_step": "string",
  "message": "string",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "result_path": "string",
  "error_message": "string",
  "estimated_time_remaining": 0.0,
  "processing_time": 0.0
}
```

**字段说明：**
- `task_id`: 任务唯一标识符
- `status`: 任务状态（pending, processing, completed, failed）
- `progress`: 进度百分比（0-100）
- `current_step`: 当前处理步骤
- `message`: 状态消息
- `created_at`: 任务创建时间
- `updated_at`: 任务更新时间
- `result_path`: 结果文件路径（可选）
- `error_message`: 错误消息（可选）
- `estimated_time_remaining`: 预计剩余时间（可选）
- `processing_time`: 处理耗时（可选）

### UploadResponse
文件上传响应模型
```json
{
  "task_id": "string",
  "message": "string",
  "status": "string"
}
```

**字段说明：**
- `task_id`: 生成的任务ID
- `message`: 响应消息
- `status`: 任务状态

### FileInfo
文件信息模型
```json
{
  "file_id": "string",
  "filename": "string",
  "file_size": 0,
  "file_type": "string",
  "download_url": "string"
}
```

**字段说明：**
- `file_id`: 文件唯一标识符
- `filename`: 文件名
- `file_size`: 文件大小（字节）
- `file_type`: 文件类型
- `download_url`: 下载链接

### ResultResponse
结果响应模型
```json
{
  "task_id": "string",
  "status": "string",
  "files": [],
  "message": "string"
}
```

**字段说明：**
- `task_id`: 任务ID
- `status`: 任务状态
- `files`: 可下载的文件列表（FileInfo数组）
- `message`: 响应消息

## API 端点

### 1. 健康检查

**GET** `/`

检查API服务是否正常运行。

**响应：**
```json
{
  "message": "InstantSplat 3D Reconstruction API is running",
  "version": "1.0.0"
}
```

### 2. 上传文件并开始三维重建

**POST** `/upload`

上传包含多个图像的zip文件并开始三维重建处理。

**请求参数：**
- `file` (FormData): 包含多个图像的zip文件（必需）
- `email` (FormData): 邮件地址，用于接收处理完成通知（使用当前用户emial/可选）
- `points` (FormData): 分割点参数，JSON字符串格式（可选）

**文件要求：**
- 格式：仅支持 `.zip` 格式
- 大小：不超过配置的最大文件大小限制
- 内容：包含至少3张图像文件（.jpg, .jpeg, .png）

**points参数格式：**
```json
"[(630, 283, 1, 0)]"
```
或多个点：
```json
"[(630, 283, 1, 0), (400, 200, 1, 1)]"
```

每个点的格式为 `(x, y, label, frame)`：
- `x, y`: 点击坐标
- `label`: 标签（通常为1）
- `frame`: 帧编号

**响应：** `UploadResponse`

**状态码：**
- `200`: 上传成功
- `400`: 请求参数错误（文件格式不支持、文件过大等）
- `500`: 服务器内部错误

### 3. 查询任务状态

**GET** `/status/{task_id}`

查询指定任务的处理状态和进度。

**路径参数：**
- `task_id`: 任务ID

**响应：** `TaskStatusResponse`

**状态码：**
- `200`: 查询成功
- `404`: 任务不存在

### 4. 获取所有任务列表

**GET** `/tasks`

获取所有任务的状态列表。

**响应：**
```json
{
  "tasks": [
    {
      "task_id": "string",
      "status": "string",
      "progress": 0.0,
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T00:00:00"
    }
  ]
}
```

**状态码：**
- `200`: 查询成功

### 5. 获取处理结果

**GET** `/result/{task_id}`

获取任务处理结果的文件信息和下载链接。

**路径参数：**
- `task_id`: 任务ID

**响应：** `ResultResponse`

**状态码：**
- `200`: 获取成功
- `400`: 任务尚未完成
- `404`: 任务不存在或结果不存在
- `500`: PLY文件上传到公网服务器失败

### 6. 删除任务

**DELETE** `/task/{task_id}`

删除指定的任务及其相关文件。

**路径参数：**
- `task_id`: 任务ID

**响应：**
```json
{
  "message": "任务已删除",
  "task_id": "string",
  "deleted_directories": ["string"]
}
```

**状态码：**
- `200`: 删除成功
- `404`: 任务不存在
- `500`: 删除失败

## 任务状态说明

任务在处理过程中会经历以下状态：

1. **pending**: 任务已创建，等待处理
2. **processing**: 任务正在处理中
   - extracting: 正在提取图像
   - reconstructing: 正在进行三维重建
3. **completed**: 任务处理完成
4. **failed**: 任务处理失败

## 错误处理

API 使用标准的 HTTP 状态码和 JSON 格式的错误响应：

```json
{
  "detail": "错误描述",
  "error_type": "异常类型",
  "message": "详细错误信息"
}
```

**常见错误码：**
- `400`: 请求参数错误
- `404`: 资源不存在
- `422`: 数据验证失败
- `500`: 服务器内部错误

## 使用流程

1. **上传文件**: 调用 `POST /upload` 上传zip文件
2. **查询状态**: 使用返回的 `task_id` 调用 `GET /status/{task_id}` 查询处理进度
3. **获取结果**: 任务完成后调用 `GET /result/{task_id}` 获取下载链接
4. **清理任务**: 可选择调用 `DELETE /task/{task_id}` 删除任务

## 注意事项

1. **文件格式**: 仅支持zip格式的压缩文件
2. **图像要求**: zip文件中至少包含3张图像文件
3. **异步处理**: 三维重建是异步处理，需要轮询状态接口获取进度
4. **邮件通知**: 提供邮箱地址可在任务完成时收到邮件通知
5. **结果存储**: 处理完成的PLY文件会上传到公网服务器供下载
6. **任务清理**: 建议在获取结果后删除不需要的任务以释放存储空间

## 请求和响应示例

### 1. 上传文件示例

**使用 curl 上传文件：**
```bash
curl -X POST "http://localhost:8003/upload" \
  -F "file=@images.zip" \
  -F "email=user@example.com" \
  -F "points=[(630, 283, 1, 0), (400, 200, 1, 1)]"
```

**使用 JavaScript 上传文件：**
```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('email', 'user@example.com');
formData.append('points', '[(630, 283, 1, 0)]');

const response = await fetch('http://localhost:8003/upload', {
  method: 'POST',
  body: formData
});

const result = await response.json();
console.log(result);
```

**响应示例：**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "文件上传成功，开始处理",
  "status": "pending"
}
```

### 2. 查询任务状态示例

**请求：**
```bash
curl -X GET "http://localhost:8003/status/550e8400-e29b-41d4-a716-446655440000"
```

**响应示例（处理中）：**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 65.5,
  "current_step": "reconstructing",
  "message": "正在进行三维重建...",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:35:30Z",
  "result_path": null,
  "error_message": null,
  "estimated_time_remaining": 120.5,
  "processing_time": 330.2
}
```

**响应示例（已完成）：**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": 100.0,
  "current_step": "completed",
  "message": "三维重建完成",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:40:00Z",
  "result_path": "/output_api/550e8400-e29b-41d4-a716-446655440000/point_cloud.ply",
  "error_message": null,
  "estimated_time_remaining": 0.0,
  "processing_time": 600.0
}
```

### 3. 获取任务列表示例

**请求：**
```bash
curl -X GET "http://localhost:8003/tasks"
```

**响应示例：**
```json
{
  "tasks": [
    {
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "completed",
      "progress": 100.0,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:40:00Z"
    },
    {
      "task_id": "660f9511-f3ac-52e5-b827-557766551111",
      "status": "processing",
      "progress": 45.2,
      "created_at": "2024-01-15T11:00:00Z",
      "updated_at": "2024-01-15T11:05:00Z"
    }
  ]
}
```

### 4. 获取处理结果示例

**请求：**
```bash
curl -X GET "http://localhost:8003/result/550e8400-e29b-41d4-a716-446655440000"
```

**响应示例：**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "files": [
    {
      "file_id": "550e8400-e29b-41d4-a716-446655440000_point_cloud",
      "filename": "point_cloud_550e8400-e29b-41d4-a716-446655440000.ply",
      "file_size": 10485760,
      "file_type": "application/octet-stream",
      "download_url": "https://public-server.com/files/point_cloud_550e8400-e29b-41d4-a716-446655440000.ply"
    }
  ],
  "message": "结果文件准备就绪"
}
```

### 5. 删除任务示例

**请求：**
```bash
curl -X DELETE "http://localhost:8003/task/550e8400-e29b-41d4-a716-446655440000"
```

**响应示例：**
```json
{
  "message": "任务已删除",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "deleted_directories": [
    "/home/livablecity/InstantSplat/assets/api_uploads/550e8400-e29b-41d4-a716-446655440000",
    "/home/livablecity/InstantSplat/temp/550e8400-e29b-41d4-a716-446655440000",
    "/home/livablecity/InstantSplat/output_api/550e8400-e29b-41d4-a716-446655440000"
  ]
}
```

### 6. 错误响应示例

**文件格式错误：**
```json
{
  "detail": "不支持的文件格式。仅支持 .zip 格式"
}
```

**任务不存在：**
```json
{
  "detail": "任务不存在"
}
```

**任务尚未完成：**
```json
{
  "detail": "任务尚未完成，无法获取结果"
}
```

## 完整的前端集成示例

### JavaScript 完整工作流程

```javascript
class InstantSplatAPI {
  constructor(baseUrl = 'http://localhost:8003') {
    this.baseUrl = baseUrl;
  }

  // 上传文件并开始处理
  async uploadFile(file, email = null, points = null) {
    const formData = new FormData();
    formData.append('file', file);
    
    if (email) {
      formData.append('email', email);
    }
    
    if (points) {
      formData.append('points', JSON.stringify(points));
    }

    const response = await fetch(`${this.baseUrl}/upload`, {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      throw new Error(`上传失败: ${response.statusText}`);
    }

    return await response.json();
  }

  // 查询任务状态
  async getTaskStatus(taskId) {
    const response = await fetch(`${this.baseUrl}/status/${taskId}`);
    
    if (!response.ok) {
      throw new Error(`查询失败: ${response.statusText}`);
    }

    return await response.json();
  }

  // 轮询任务状态直到完成
  async waitForCompletion(taskId, onProgress = null) {
    while (true) {
      const status = await this.getTaskStatus(taskId);
      
      if (onProgress) {
        onProgress(status);
      }

      if (status.status === 'completed') {
        return status;
      } else if (status.status === 'failed') {
        throw new Error(`任务失败: ${status.error_message}`);
      }

      // 等待5秒后再次查询
      await new Promise(resolve => setTimeout(resolve, 5000));
    }
  }

  // 获取处理结果
  async getResult(taskId) {
    const response = await fetch(`${this.baseUrl}/result/${taskId}`);
    
    if (!response.ok) {
      throw new Error(`获取结果失败: ${response.statusText}`);
    }

    return await response.json();
  }

  // 删除任务
  async deleteTask(taskId) {
    const response = await fetch(`${this.baseUrl}/task/${taskId}`, {
      method: 'DELETE'
    });

    if (!response.ok) {
      throw new Error(`删除任务失败: ${response.statusText}`);
    }

    return await response.json();
  }
}

// 使用示例
async function processImages() {
  const api = new InstantSplatAPI();
  
  try {
    // 1. 上传文件
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    const email = 'user@example.com';
    const points = [(630, 283, 1, 0)]; // 可选的分割点
    
    console.log('开始上传文件...');
    const uploadResult = await api.uploadFile(file, email, points);
    console.log('上传成功:', uploadResult);
    
    const taskId = uploadResult.task_id;
    
    // 2. 等待处理完成
    console.log('等待处理完成...');
    const finalStatus = await api.waitForCompletion(taskId, (status) => {
      console.log(`进度: ${status.progress}% - ${status.current_step}`);
    });
    
    console.log('处理完成:', finalStatus);
    
    // 3. 获取结果
    const result = await api.getResult(taskId);
    console.log('结果:', result);
    
    // 4. 下载文件
    if (result.files && result.files.length > 0) {
      const downloadUrl = result.files[0].download_url;
      window.open(downloadUrl, '_blank');
    }
    
    // 5. 可选：删除任务
    // await api.deleteTask(taskId);
    
  } catch (error) {
    console.error('处理失败:', error);
  }
}
```

## 配置信息

API服务的相关配置通过 `config.py` 模块管理，包括：
- 文件大小限制
- 支持的文件格式
- 存储路径配置
- 邮件服务配置