#!/usr/bin/env python3
"""
配置文件 - InstantSplat API服务配置
"""

import os
from pathlib import Path
from typing import Set

class APIConfig:
    """API服务配置类"""
    
    # 基础路径配置
    BASE_DIR = Path("/home/livablecity/InstantSplat")
    UPLOAD_DIR = BASE_DIR / "uploads"
    OUTPUT_DIR = BASE_DIR / "output_api"
    TEMP_DIR = BASE_DIR / "temp"
    LOG_DIR = BASE_DIR / "logs"
    VIEWER_URL="https://viewer.scenegen.cn/?"
    # InstantSplat标准目录结构
    ASSETS_DIR = BASE_DIR / "assets"  # DATA_ROOT_DIR
    DATASET_NAME = "api_uploads"      # 统一的数据集名称
    OUTPUT_INFER_DIR = BASE_DIR / "output_infer"  # 推理输出目录
    
    # 文件限制配置
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
    ALLOWED_VIDEO_FORMATS: Set[str] = {".mp4", ".mov", ".avi"}
    ALLOWED_IMAGE_FORMATS: Set[str] = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    ALLOWED_ARCHIVE_FORMATS: Set[str] = {".zip"}  # 支持的压缩包格式
    
    # 图像处理配置
    MAX_IMAGE_SIZE = 100 * 1024 * 1024  # 100MB for images
    MIN_IMAGE_RESOLUTION = (256, 256)  # 最小分辨率
    MAX_IMAGE_RESOLUTION = (4096, 4096)  # 最大分辨率
    
    # 处理参数配置
    N_FRAMES = 15  # 从视频中抽取的帧数（用于均匀采样）
    FRAMES_PER_SECOND = 1  # 每秒提取帧数（用于时间间隔采样）
    GS_TRAIN_ITER = 1500  # Gaussian Splatting训练迭代次数
    IMAGE_SIZE = 512  # 图像处理尺寸
    
    # 服务器配置
    HOST = "0.0.0.0"
    PORT = 3080
    DEBUG = True  # 调试模式
    
    # 并发配置
    MAX_WORKERS = 2  # 最大并发处理任务数
    MAX_CONCURRENT_TASKS = 2  # 最大并发任务数
    
    # 模型配置
    MAST3R_CHECKPOINT = BASE_DIR / "mast3r" / "checkpoints" / "MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric.pth"
    
    # 日志配置
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # CUDA配置
    DEVICE = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu"
    
    # 任务清理配置
    TASK_RETENTION_HOURS = 24  # 任务保留时间（小时）
    TASK_CLEANUP_HOURS = 24  # 任务清理时间（小时）
    AUTO_CLEANUP_INTERVAL = 3600  # 自动清理间隔（秒）
    
    @classmethod
    def create_directories(cls):
        """创建必要的目录"""
        for dir_path in [cls.UPLOAD_DIR, cls.OUTPUT_DIR, cls.TEMP_DIR, cls.LOG_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def validate_environment(cls):
        """验证环境配置"""
        # 检查基础目录是否存在
        if not cls.BASE_DIR.exists():
            raise RuntimeError(f"基础目录不存在: {cls.BASE_DIR}")
        
        # 检查关键文件是否存在
        required_files = [
            cls.BASE_DIR / "init_geo.py",
            cls.BASE_DIR / "train.py",
            cls.BASE_DIR / "render.py"
        ]
        
        for file_path in required_files:
            if not file_path.exists():
                raise RuntimeError(f"必需文件不存在: {file_path}")
        
        # 检查模型检查点
        if not cls.MAST3R_CHECKPOINT.exists():
            print(f"警告: MASt3R模型检查点不存在: {cls.MAST3R_CHECKPOINT}")
        
        return True

class ProcessingConfig:
    """处理流程配置"""
    
    # 基础路径配置
    instantsplat_root = "/home/livablecity/InstantSplat"
    use_cuda = True  # 是否使用CUDA
    render_resolution = 1  # 渲染分辨率
    
    # 超时配置
    init_timeout = 300  # 几何初始化超时时间（秒）
    train_timeout = 1800  # 训练超时时间（秒）
    render_timeout = 600  # 渲染超时时间（秒）
    
    # 训练迭代次数
    iterations = 500
    
    # 几何初始化参数
    INIT_GEO_PARAMS = {
        "focal_avg": True,
        "co_vis_dsp": True,
        "conf_aware_ranking": True,
        "infer_video": True,
        "min_conf_thr": 5.0,
        "depth_thre": 0.01,
        "niter": 300,
        "lr": 0.01,
        "schedule": "cosine"
    }
    
    # 训练参数
    TRAIN_PARAMS = {
        "resolution": 1,
        "pp_optimizer": True,
        "optim_pose": True,
        "white_background": False,
        "data_device": "cuda"
    }
    
    # 渲染参数
    RENDER_PARAMS = {
        "resolution": 1,
        "infer_video": True,
        "skip_train": False,
        "skip_test": False
    }

class VideoProcessingConfig:
    """视频处理配置"""
    
    # 支持的视频编解码器
    SUPPORTED_CODECS = ["h264", "h265", "mpeg4", "mjpeg"]
    
    # 帧提取配置
    FRAME_EXTRACTION = {
        "method": "fps_based",  # uniform: 均匀采样, keyframe: 关键帧, fps_based: 每秒采样
        "fps": 1,  # 每秒提取帧数
        "quality": 95,  # JPEG质量
        "format": "jpg"
    }
    
    # 视频预处理
    PREPROCESSING = {
        "resize_max_dimension": 1920,  # 最大尺寸限制
        "fps_limit": 60,  # FPS限制
        "duration_limit": 300  # 时长限制（秒）
    }

# 全局配置实例
api_config = APIConfig()
processing_config = ProcessingConfig()
video_config = VideoProcessingConfig()

# 初始化配置
if __name__ == "__main__":
    api_config.create_directories()
    api_config.validate_environment()
    print("配置验证完成")