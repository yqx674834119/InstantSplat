# InstantSplat 项目使用指南

## 项目概述
InstantSplat 是一个基于稀疏视图的大规模场景重建方法，使用 Gaussian Splatting 技术。支持 3D-GS、2D-GS 和 Mip-Splatting。

## 环境要求
- Python 3.10.13
- CUDA 11.8 (已配置)
- PyTorch 2.5.1 with CUDA 11.8
- 足够的GPU内存 (建议 > 8GB)

## 数据准备

### 数据存放位置
项目数据应存放在以下目录结构中：

```
InstantSplat/
├── assets/                    # 数据根目录
│   ├── <数据集名称>/           # 如: sora, Tanks, MVimgNet
│   │   ├── <场景名称>/         # 如: Santorini, Art, Horse
│   │   │   ├── images/        # 输入图像文件夹 (必需)
│   │   │   │   ├── 000.jpg    # 图像文件
│   │   │   │   ├── 001.jpg
│   │   │   │   └── ...
│   │   │   └── 24_views/      # 评估模式需要 (可选)
│   │   │       └── images/
│   └── examples/              # 示例数据
```

### 数据格式要求
1. **图像格式**: JPG, PNG 等常见格式
2. **命名规则**: 建议使用数字序号命名 (如: 000.jpg, 001.jpg)
3. **图像数量**: 最少3张图像，推荐6-24张
4. **图像质量**: 高分辨率，清晰无模糊

## 使用方法

### 1. 推理模式 (无GT参考)
用于生成新视角视频，适用于自己的数据：

```bash
# 修改脚本配置后运行
bash scripts/run_infer.sh
```

**输出**: 插值渲染的视频文件

### 2. 评估模式 (有GT参考)
用于在标准数据集上评估性能：

```bash
# 修改脚本配置后运行
bash scripts/run_eval.sh
```

**输出**: 渲染图像 + 定量评估指标

## 必需修改的配置

### 1. 修改 `scripts/run_infer.sh`

```bash
# 第4行: 修改数据根目录的绝对路径
DATA_ROOT_DIR="/home/livablecity/InstantSplat/assets"  # 改为你的实际路径

# 第6-8行: 修改数据集名称
DATASETS=(
    your_dataset_name  # 替换为你的数据集名称
)

# 第10-13行: 修改场景名称
SCENES=(
    your_scene_1       # 替换为你的场景名称
    your_scene_2
)

# 第15-17行: 修改使用的视图数量
N_VIEWS=(
    3    # 可选: 3, 6, 12 等
)

# 第19行: 修改训练迭代次数
gs_train_iter=1000    # 可选: 200, 1000 等
```

### 2. 修改 `scripts/run_eval.sh`

```bash
# 第4行: 修改数据根目录
DATA_ROOT_DIR="/home/livablecity/InstantSplat"  # 改为你的实际路径

# 第6-9行: 修改数据集
DATASETS=(
    Tanks        # 或其他标准数据集
    # MVimgNet
)

# 第11-25行: 修改场景列表
SCENES=(
    Horse        # 根据你的数据集选择场景
    # 其他场景...
)
```

## 输出结果

### 推理模式输出
```
output_infer/
├── <数据集>/<场景>/<视图数>_views/
│   ├── 01_init_geo.log      # 几何初始化日志
│   ├── 02_train.log         # 训练日志
│   ├── 03_render.log        # 渲染日志
│   ├── point_cloud/         # 点云文件
│   ├── cameras.json         # 相机参数
│   └── video/               # 生成的视频
```

### 评估模式输出
```
output_eval_XL/
├── <数据集>/<场景>/<视图数>_views/
│   ├── 01_init_geo.log      # 几何初始化日志
│   ├── 02_train.log         # 训练日志
│   ├── 03_render_train.log  # 训练视图渲染日志
│   ├── 04_render_test.log   # 测试视图渲染日志
│   ├── 05_metrics.log       # 评估指标日志
│   ├── train/               # 训练视图渲染结果
│   ├── test/                # 测试视图渲染结果
│   └── metrics.json         # 定量评估结果
```

## 处理流程

### 推理模式流程
1. **几何初始化**: 使用 MASt3R 进行全局几何初始化
2. **联合优化**: 同时优化高斯参数和相机位姿
3. **视频渲染**: 生成插值视角的视频

### 评估模式流程
1. **几何初始化**: 全局几何初始化
2. **联合优化**: 优化高斯参数和位姿
3. **训练视图渲染**: 渲染训练视角
4. **测试视图渲染**: 渲染测试视角
5. **指标计算**: 计算PSNR、SSIM、LPIPS等指标

## 常见问题

### 1. GPU内存不足
- 减少 `gs_train_iter` 参数
- 减少输入图像分辨率
- 减少 `N_VIEWS` 数量

### 2. 结果质量不佳
- 增加训练迭代次数
- 确保输入图像质量
- 增加输入视图数量
- 检查相机标定精度

### 3. 处理时间过长
- 减少迭代次数
- 使用更强的GPU
- 减少输入图像数量

## 技术参数说明

- `--n_views`: 使用的输入视图数量
- `--iterations`: 高斯优化迭代次数
- `--focal_avg`: 使用平均焦距
- `--co_vis_dsp`: 启用共视深度采样
- `--conf_aware_ranking`: 置信度感知排序
- `--pp_optimizer`: 使用位姿优化器
- `--optim_pose`: 启用位姿优化
- `--infer_video`: 生成推理视频
- `--eval`: 评估模式

## 注意事项

1. **路径配置**: 确保所有路径都是绝对路径
2. **数据质量**: 输入图像应清晰、无模糊
3. **GPU资源**: 确保有足够的GPU内存
4. **依赖环境**: 确保所有依赖已正确安装
5. **预训练模型**: 确保 MASt3R 模型已下载完成

---

**创建时间**: 2025-01-07  
**项目版本**: InstantSplat v1.0  
**环境**: CUDA 11.8, PyTorch 2.5.1