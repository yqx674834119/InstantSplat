# PLY文件压缩功能实现方案

## 需求分析
在训练结束后，需要对生成的PLY文件进行压缩，然后上传到公网服务器。压缩后的文件需要替换原文件，并更新相关的URL引用。

## 压缩命令
```bash
/opt/glibc-2.38/lib/ld-linux-x86-64.so.2 \
  --library-path /opt/glibc-2.38/lib:/usr/lib/x86_64-linux-gnu \
  "$(command -v node)" \
  "$(command -v splat-transform)" \
  <输入PLY文件路径> \
  <输出压缩PLY文件路径>
```

## 实现方案

### 1. 修改位置
- **文件**: `/home/livablecity/InstantSplat/api_server.py`
- **位置**: 第533-534行获取PLY文件路径后
- **函数**: `process_video_task` 函数中的重建完成处理部分

### 2. 实现步骤

#### 2.1 在获取PLY文件后添加压缩逻辑
```python
# 在第534行后添加压缩逻辑
ply_file_path = reconstruction_result.files.get('point_cloud', '')
if ply_file_path and os.path.exists(ply_file_path):
    # 生成压缩文件路径
    compressed_ply_path = ply_file_path.replace('.ply', '.compressed.ply')
    
    # 执行压缩命令
    compress_cmd = [
        '/opt/glibc-2.38/lib/ld-linux-x86-64.so.2',
        '--library-path', '/opt/glibc-2.38/lib:/usr/lib/x86_64-linux-gnu',
        '$(command -v node)',
        '$(command -v splat-transform)',
        ply_file_path,
        compressed_ply_path
    ]
    
    # 执行压缩
    result = subprocess.run(compress_cmd, capture_output=True, text=True, shell=True)
    
    if result.returncode == 0:
        # 删除原文件
        os.remove(ply_file_path)
        # 更新文件路径为压缩后的文件
        ply_file_path = compressed_ply_path
    else:
        logger.error(f"PLY压缩失败: {result.stderr}")
```

#### 2.2 更新SCP上传逻辑
- **位置**: 第540行 `remote_filename = f"{task_id}.compressed.ply"`
- **说明**: 已经添加了`.compressed.ply`后缀，需要确保与压缩后的文件名一致

#### 2.3 更新文件路径引用
- 确保后续所有对PLY文件的引用都使用压缩后的文件路径
- 更新`model_url`和`public_url`的构建逻辑

### 3. 影响分析

#### 3.1 对SCP上传的影响
- ✅ 远程文件名已经使用`.compressed.ply`后缀
- ✅ 上传的将是压缩后的文件，文件大小更小，传输更快
- ⚠️ 需要确保压缩成功后才进行SCP上传

#### 3.2 对URL构建的影响
- 需要更新`public_url`中的文件名，确保包含`.compressed.ply`后缀
- 邮件中的下载链接将指向压缩后的文件

#### 3.3 错误处理
- 如果压缩失败，应该使用原文件进行上传
- 需要记录压缩过程的日志
- 压缩失败不应该导致整个任务失败

### 4. 代码修改清单

1. **api_server.py**:
   - 在获取PLY文件后添加压缩逻辑
   - 更新错误处理机制
   - 确保压缩后文件路径的正确传递

2. **日志记录**:
   - 添加压缩开始、成功、失败的日志记录
   - 记录压缩前后文件大小对比

### 5. 测试要点

1. 验证压缩命令是否正确执行
2. 确认压缩后文件可以正常上传
3. 验证下载链接指向正确的压缩文件
4. 测试压缩失败时的降级处理

### 6. 风险评估

- **低风险**: 压缩是在原文件基础上生成新文件，不会直接破坏原数据
- **中风险**: 压缩失败可能导致文件处理流程中断
- **缓解措施**: 添加完善的错误处理和日志记录

## 实施计划

1. 首先在测试环境验证压缩命令
2. 实现压缩逻辑和错误处理
3. 更新相关的文件路径引用
4. 进行完整的端到端测试
5. 更新文档记录