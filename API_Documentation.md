# InstantSplat 3D Reconstruction API 文档

## 概述

InstantSplat 3D Reconstruction API 是一个基于 FastAPI 的 RESTful API 服务，提供视频和图像的三维重建功能。该 API 支持多种文件格式的上传，并通过异步处理提供高效的三维重建服务。

**服务信息：**
- 版本：1.0.0
- 基础URL：`http://localhost:3080`
- 协议：HTTP/HTTPS
- 数据格式：JSON

---

## 接口列表

| 序号 | 接口路径 | 方法 | 功能描述 |
|------|----------|------|----------|
| 1 | `/` | GET | 健康检查 |
| 2 | `/upload` | POST | 上传文件并开始三维重建 |
| 3 | `/status/{task_id}` | GET | 查询任务状态 |
| 4 | `/tasks` | GET | 获取所有任务列表 |
| 5 | `/result/{task_id}` | GET | 下载处理结果 |
| 6 | `/task/{task_id}` | DELETE | 删除任务 |

---

## 接口详细说明

### 1. 健康检查

**接口描述：** 检查 API 服务是否正常运行

**请求信息：**
```
GET /
```

**请求参数：** 无

**响应格式：**
```json
{
  "message": "InstantSplat 3D Reconstruction API is running",
  "version": "1.0.0"
}
```

**状态码：**
- `200 OK`：服务正常运行

---

### 2. 上传文件并开始三维重建

**接口描述：** 上传图像、视频或压缩包文件，并启动三维重建任务

**请求信息：**
```
POST /upload
Content-Type: multipart/form-data
```

**请求参数：**

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| `file` | File | 是 | 上传的文件（图像/视频/压缩包） |
| `email` | String | 否 | 邮箱地址，用于接收处理完成通知 |

**支持的文件格式：**
- **视频格式：** `.mp4`, `.mov`, `.avi`
- **图像格式：** `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.webp`
- **压缩包格式：** `.zip`（包含多张图像）

**文件大小限制：**
- 视频文件：最大 500MB
- 图像文件：最大 100MB
- 压缩包文件：最大 500MB
- 图像分辨率：256×256 至 4096×4096

**响应格式：**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "视频上传成功，开始处理",
  "status": "pending"
}
```

**状态码：**
- `200 OK`：文件上传成功
- `400 Bad Request`：文件格式不支持、文件大小超限、文件损坏等
- `500 Internal Server Error`：服务器内部错误

**错误响应示例：**
```json
{
  "detail": "不支持的文件格式。支持的格式: .mp4, .mov, .avi, .jpg, .jpeg, .png, .bmp, .tiff, .webp, .zip"
}
```

---

### 3. 查询任务状态

**接口描述：** 查询指定任务的处理状态和进度

**请求信息：**
```
GET /status/{task_id}
```

**路径参数：**

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| `task_id` | String | 是 | 任务唯一标识符 |

**响应格式：**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 65.5,
  "current_step": "三维重建训练中",
  "message": "正在进行Gaussian Splatting训练...",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:35:30Z",
  "result_path": null,
  "error_message": null,
  "estimated_time_remaining": 120.5,
  "processing_time": 330.2
}
```

**任务状态说明：**
- `pending`：等待处理
- `processing`：处理中
- `completed`：处理完成
- `failed`：处理失败

**状态码：**
- `200 OK`：查询成功
- `404 Not Found`：任务不存在

---

### 4. 获取所有任务列表

**接口描述：** 获取所有任务的状态列表

**请求信息：**
```
GET /tasks
```

**请求参数：** 无

**响应格式：**
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

**状态码：**
- `200 OK`：查询成功

---

### 5. 下载处理结果

**接口描述：** 下载任务处理完成后的三维重建结果文件

**请求信息：**
```
GET /result/{task_id}
```

**路径参数：**

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| `task_id` | String | 是 | 任务唯一标识符 |

**响应格式：**
- **成功时：** 返回 PLY 格式的点云文件（二进制流）
- **Content-Type：** `application/octet-stream`
- **文件名：** `point_cloud_{task_id}.ply`

**状态码：**
- `200 OK`：文件下载成功
- `400 Bad Request`：任务尚未完成
- `404 Not Found`：任务不存在或结果文件不存在
- `500 Internal Server Error`：文件访问错误

**错误响应示例：**
```json
{
  "detail": "任务尚未完成"
}
```

---

### 6. 删除任务

**接口描述：** 删除指定任务及其相关文件

**请求信息：**
```
DELETE /task/{task_id}
```

**路径参数：**

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| `task_id` | String | 是 | 任务唯一标识符 |

**响应格式：**
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

**状态码：**
- `200 OK`：删除成功
- `404 Not Found`：任务不存在
- `500 Internal Server Error`：删除过程中发生错误

---

## 错误代码说明

### HTTP 状态码

| 状态码 | 说明 | 常见原因 |
|--------|------|----------|
| 200 | OK | 请求成功 |
| 400 | Bad Request | 请求参数错误、文件格式不支持、文件大小超限 |
| 404 | Not Found | 任务不存在、结果文件不存在 |
| 422 | Unprocessable Entity | 请求数据验证失败 |
| 500 | Internal Server Error | 服务器内部错误 |

### 业务错误代码

| 错误信息 | 描述 | 解决方案 |
|----------|------|----------|
| "文件名不能为空" | 上传文件缺少文件名 | 确保上传的文件有有效的文件名 |
| "不支持的文件格式" | 文件格式不在支持列表中 | 使用支持的文件格式 |
| "文件为空" | 上传的文件大小为0 | 检查文件是否损坏 |
| "文件大小超过限制" | 文件大小超过最大限制 | 压缩文件或使用较小的文件 |
| "视频文件格式无效或已损坏" | 视频文件无法解析 | 检查视频文件完整性 |
| "图像文件格式无效或已损坏" | 图像文件无法解析 | 检查图像文件完整性 |
| "压缩包文件格式无效或已损坏" | ZIP文件无法解压 | 检查ZIP文件完整性 |
| "任务不存在" | 指定的任务ID不存在 | 检查任务ID是否正确 |
| "任务尚未完成" | 尝试下载未完成任务的结果 | 等待任务完成后再下载 |
| "结果文件不存在" | 任务完成但结果文件丢失 | 联系管理员检查服务器状态 |

---

## 使用示例

### 1. 上传视频文件

```bash
curl -X POST "http://localhost:3080/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@example_video.mp4" \
  -F "email=user@example.com"
```

**响应：**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "视频上传成功，开始处理",
  "status": "pending"
}
```

### 2. 查询任务状态

```bash
curl -X GET "http://localhost:3080/status/550e8400-e29b-41d4-a716-446655440000"
```

**响应：**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 75.0,
  "current_step": "三维重建训练中",
  "message": "正在进行Gaussian Splatting训练...",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:37:30Z",
  "result_path": null,
  "error_message": null,
  "estimated_time_remaining": 60.0,
  "processing_time": 450.2
}
```

### 3. 下载结果文件

```bash
curl -X GET "http://localhost:3080/result/550e8400-e29b-41d4-a716-446655440000" \
  -o point_cloud_result.ply
```

### 4. JavaScript 示例

```javascript
// 上传文件
async function uploadFile(file, email) {
  const formData = new FormData();
  formData.append('file', file);
  if (email) {
    formData.append('email', email);
  }
  
  const response = await fetch('http://localhost:3080/upload', {
    method: 'POST',
    body: formData
  });
  
  return await response.json();
}

// 查询任务状态
async function getTaskStatus(taskId) {
  const response = await fetch(`http://localhost:3080/status/${taskId}`);
  return await response.json();
}

// 轮询任务状态直到完成
async function waitForCompletion(taskId) {
  while (true) {
    const status = await getTaskStatus(taskId);
    console.log(`任务进度: ${status.progress}% - ${status.current_step}`);
    
    if (status.status === 'completed') {
      console.log('任务完成！');
      return status;
    } else if (status.status === 'failed') {
      throw new Error(`任务失败: ${status.error_message}`);
    }
    
    // 等待5秒后再次查询
    await new Promise(resolve => setTimeout(resolve, 5000));
  }
}
```

---

## 处理流程说明

### 1. 视频处理流程
1. **文件上传验证**：检查文件格式、大小和完整性
2. **视频帧提取**：从视频中提取关键帧（默认15帧）
3. **几何初始化**：使用MASt3R进行初始几何重建
4. **三维重建训练**：使用Gaussian Splatting进行训练（500次迭代）
5. **结果渲染**：生成最终的点云文件
6. **邮件通知**：发送处理完成通知（如提供邮箱）

### 2. 图像处理流程
1. **文件上传验证**：检查图像格式、大小和完整性
2. **图像预处理**：调整图像尺寸和格式
3. **几何初始化**：使用MASt3R进行初始几何重建
4. **三维重建训练**：使用Gaussian Splatting进行训练
5. **结果渲染**：生成最终的点云文件
6. **邮件通知**：发送处理完成通知（如提供邮箱）

### 3. 多图像处理流程（ZIP文件）
1. **压缩包验证**：检查ZIP文件完整性
2. **图像提取**：从ZIP中提取所有图像文件
3. **图像验证**：确保至少有3张有效图像
4. **批量处理**：按照图像处理流程处理所有图像
5. **结果合并**：生成综合的三维重建结果
6. **邮件通知**：发送处理完成通知（如提供邮箱）

---

## 注意事项

### 1. 性能考虑
- 最大并发处理任务数：2个
- 建议文件大小：视频 < 200MB，图像 < 50MB
- 处理时间：视频约5-15分钟，图像约2-8分钟

### 2. 文件要求
- 视频：建议分辨率不超过1920×1080，时长不超过5分钟
- 图像：建议分辨率在512×512到2048×2048之间
- ZIP文件：包含至少3张图像，总大小不超过500MB

### 3. 安全考虑
- 所有上传文件都会进行格式验证
- 任务文件会在24小时后自动清理
- 不支持可执行文件上传

### 4. 错误处理
- 建议实现客户端重试机制
- 长时间运行的任务可能会超时
- 网络中断时需要重新查询任务状态

---

## 更新日志

### v1.0.0 (2024-01-15)
- 初始版本发布
- 支持视频、图像和ZIP文件上传
- 实现异步三维重建处理
- 添加邮件通知功能
- 提供完整的任务管理接口

---

## 联系信息

如有问题或建议，请联系开发团队。

**技术支持：** 请查看服务器日志文件 `api_server.log` 获取详细错误信息。