# InstantSplat API 目录结构重组计划

## 问题分析

根据 `/home/livablecity/InstantSplat/scripts/run_infer.sh` 脚本的要求，InstantSplat 需要特定的目录结构：

### 标准目录结构
```
DATA_ROOT_DIR/
└── DATASET/
    └── SCENE/
        ├── images/           # 输入图像文件
        │   ├── 000000.jpg
        │   ├── 000001.jpg
        │   └── ...
        └── sparse_3/         # 几何初始化生成的中间文件
            └── 0/
                ├── cameras.bin
                ├── images.bin
                ├── points3D.bin
                ├── confidence_dsp.npy
                └── ...
```

### 输出目录结构
```
output_infer/
└── DATASET/
    └── SCENE/
        └── N_views/          # 如 3_views
            ├── 01_init_geo.log
            ├── 02_train.log
            ├── 03_render.log
            └── ...
```

## 当前问题

1. **文件存储位置不符合标准**：当前API将文件存储在 `temp/task_id/` 目录下，不符合InstantSplat的标准目录结构
2. **路径传递错误**：ReconstructionProcessor传递的路径不符合脚本期望的格式
3. **中间文件路径不匹配**：训练脚本期望在 `sparse_N/0/` 目录中找到文件，但实际生成在其他位置

## 解决方案

### 1. 修改配置文件 (config.py)

添加新的目录配置：
```python
# InstantSplat标准目录结构
ASSETS_DIR = BASE_DIR / "assets"  # DATA_ROOT_DIR
DATASET_NAME = "api_uploads"      # 统一的数据集名称
```

### 2. 修改API服务器 (api_server.py)

重新组织文件上传逻辑：
- 使用 `assets/api_uploads/task_id/images/` 作为输入目录
- 确保图像文件按顺序命名（000000.jpg, 000001.jpg, ...）

### 3. 修改ReconstructionProcessor (reconstruction_processor.py)

更新处理逻辑：
- 修改 `_prepare_input_directory` 方法，直接使用标准目录结构
- 更新脚本调用参数，使用正确的源路径和模型路径
- 确保 `n_views` 参数正确传递

### 4. 具体修改内容

#### 4.1 目录结构映射

| 原结构 | 新结构 |
|--------|--------|
| `temp/task_id/filename` | `assets/api_uploads/task_id/images/000000.ext` |
| `output_api/task_id/` | `output_infer/api_uploads/task_id/3_views/` |

#### 4.2 脚本参数调整

- `SOURCE_PATH`: `assets/api_uploads/task_id/`
- `MODEL_PATH`: `output_infer/api_uploads/task_id/3_views/`
- `IMAGE_PATH`: `assets/api_uploads/task_id/images/`

## 实施步骤

1. ✅ 分析现有代码和目录结构
2. 🔄 修改配置文件，添加新的目录配置
3. 🔄 更新API服务器的文件上传逻辑
4. 🔄 修改ReconstructionProcessor的处理逻辑
5. 🔄 测试新的目录结构是否正常工作
6. 🔄 更新文档和日志记录

## 预期效果

修改完成后，API将：
1. 按照InstantSplat标准目录结构存储文件
2. 正确传递路径参数给处理脚本
3. 确保中间文件和输出文件在正确位置生成
4. 提高与原始InstantSplat脚本的兼容性

---

**创建时间**: 2025-01-09
**修改人**: InstantSplat API Team
**状态**: 进行中