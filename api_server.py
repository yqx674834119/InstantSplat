#!/usr/bin/env python3
"""
FastAPI服务器用于视频上传和三维重建处理
基于InstantSplat的三维重建流程
"""

import os
import uuid
import asyncio
import shutil
import tempfile
import zipfile
import glob
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import json
import subprocess
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse, FileResponse,StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exception_handlers import http_exception_handler
from pydantic import BaseModel, Field, ValidationError
import uvicorn
import logging
import traceback

# 导入自定义模块
from task_manager import TaskManager, TaskStatus as TMTaskStatus, TaskType, task_manager
from reconstruction_processor import ReconstructionProcessor, reconstruction_processor
from supabase_email_notifier import send_training_completion_email, send_test_email
from config import api_config

# 使用配置模块
config = api_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 辅助函数
def validate_zip_file(file: UploadFile) -> bool:
    """验证zip文件是否有效"""
    try:
        # 重置文件指针
        file.file.seek(0)
        
        # 读取文件内容到内存
        file_content = file.file.read()
        
        # 使用BytesIO创建文件对象
        import io
        zip_buffer = io.BytesIO(file_content)
        
        # 尝试读取zip文件
        with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
            # 检查zip文件是否损坏
            bad_file = zip_ref.testzip()
            if bad_file:
                logger.warning(f"zip文件中存在损坏的文件: {bad_file}")
                return False
            
            # 检查是否包含图像文件
            image_files = []
            for filename in zip_ref.namelist():
                if not filename.startswith('__MACOSX/') and not filename.startswith('.'):  # 忽略系统文件
                    file_ext = Path(filename).suffix.lower()
                    if file_ext in config.ALLOWED_IMAGE_FORMATS:
                        image_files.append(filename)
            
            if len(image_files) < 3:  # 至少需要3张图像进行重建
                logger.warning(f"zip文件中图像数量不足: {len(image_files)} < 3")
                return False
                
            logger.info(f"zip文件验证成功，包含{len(image_files)}张图像")
            return True
            
    except zipfile.BadZipFile:
        logger.warning("无效的zip文件格式")
        return False
    except Exception as e:
        logger.error(f"zip文件验证异常: {e}")
        return False
    finally:
        # 重置文件指针
        file.file.seek(0)

def extract_images_from_zip(zip_path: Path, images_dir: Path) -> int:
    """从zip文件中提取图像到指定目录"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            image_files = []
            for filename in zip_ref.namelist():
                if not filename.startswith('__MACOSX/') and not filename.startswith('.'):  # 忽略系统文件
                    file_ext = Path(filename).suffix.lower()
                    if file_ext in config.ALLOWED_IMAGE_FORMATS:
                        image_files.append(filename)
            
            # 按文件名排序确保一致性
            image_files.sort()
            
            # 提取图像文件并重命名为标准格式
            for i, filename in enumerate(image_files):
                file_ext = Path(filename).suffix.lower()
                standard_name = f"{i:06d}{file_ext}"  # 000000.jpg, 000001.jpg, ...
                
                # 提取文件
                file_data = zip_ref.read(filename)
                target_path = images_dir / standard_name
                with open(target_path, 'wb') as target:
                    target.write(file_data)
                        
            logger.info(f"成功提取{len(image_files)}张图像到{images_dir}")
            return len(image_files)
            
    except Exception as e:
        logger.error(f"提取zip文件失败: {e}")
        raise

async def run_segmentation_preprocessing(input_dir: str, points: str) -> None:
    """执行SAM2分割预处理
    
    Args:
        input_dir: 输入图像目录路径
        points: 分割点参数，格式为JSON字符串，例如"[(630, 283, 1, 0)]"
                每个点包含(x, y, label, frame)，其中frame用于指定处理帧
    """
    try:
        # 解析points参数（JSON格式）
        import json
        points_list = json.loads(points)
        
        if not isinstance(points_list, list) or len(points_list) == 0:
            raise ValueError(f"points参数必须是非空列表，实际为: {points}")
        
        # 验证每个点的格式
        for i, point in enumerate(points_list):
            if not isinstance(point, (list, tuple)) or len(point) != 4:
                raise ValueError(f"第{i+1}个点格式错误，应为[x, y, label, frame]，实际为: {point}")
        
        # 提取frame参数（假设所有点使用同一帧）
        frame = points_list[0][3]  # 使用第一个点的frame参数
        
        # 构建points参数列表 (x, y, label格式，去掉frame)
        point_coords = []
        for x, y, label, _ in points_list:
            point_coords.extend([str(x), str(y), str(label)])
        
        logger.info(f"处理{len(points_list)}个分割点，目标帧: {frame}")
        logger.info(f"点坐标: {points_list}")
        
        # 构建分割命令 - 所有点作为一次调用的参数
        cmd = [
            "conda", "run", "-n", "sam2",
            "python", "/home/livablecity/Grounded-SAM-2/sam2_video.py",
            input_dir,
            "--points"
        ]
        
        # 添加所有点的坐标
        cmd.extend(point_coords)
        
        # 添加frame参数
        cmd.extend(["--frame", str(frame)])
        
        # 添加输出目录
        cmd.extend(["--output", input_dir])
        
        logger.info(f"执行分割命令: {' '.join(cmd)}")
        
        # 执行命令
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/home/livablecity/Grounded-SAM-2"
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = f"分割命令执行失败，返回码: {process.returncode}, stderr: {stderr.decode()}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info(f"分割处理完成，处理了{len(points_list)}个点")
        
        logger.info(f"分割命令执行成功，stdout: {stdout.decode()}")
        
    except Exception as e:
        logger.error(f"分割预处理异常: {e}")
        raise

# 数据模型
class TaskStatusResponse(BaseModel):
    task_id: str
    status: str = Field(..., description="任务状态: pending, processing, completed, failed")
    progress: float = Field(0.0, description="进度百分比 (0-100)")
    current_step: str = Field("", description="当前处理步骤")
    message: str = Field("", description="状态消息")
    created_at: datetime
    updated_at: datetime
    result_path: Optional[str] = None
    error_message: Optional[str] = None
    estimated_time_remaining: Optional[float] = None
    processing_time: Optional[float] = None

class UploadResponse(BaseModel):
    task_id: str
    message: str
    status: str

class ProcessingResult(BaseModel):
    task_id: str
    status: str
    result_files: List[str] = []
    processing_time: Optional[float] = None
    error_message: Optional[str] = None

class FileInfo(BaseModel):
    file_id: str = Field(..., description="文件唯一标识符")
    filename: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小（字节）")
    file_type: str = Field(..., description="文件类型")
    download_url: str = Field(..., description="下载链接")

class ResultResponse(BaseModel):
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    files: List[FileInfo] = Field(default_factory=list, description="可下载的文件列表")
    message: str = Field("", description="响应消息")

# 使用全局任务管理器
# task_manager 已在模块中定义

# FastAPI应用
app = FastAPI(
    title="InstantSplat 3D Reconstruction API",
    description="基于InstantSplat的视频三维重建API服务",
    version="1.0.0"
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"全局异常: {str(exc)}")
    logger.error(f"异常详情: {traceback.format_exc()}")
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误",
            "error_type": type(exc).__name__,
            "message": str(exc) if config.DEBUG else "服务器内部错误，请稍后重试"
        }
    )

@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """数据验证异常处理器"""
    logger.warning(f"数据验证错误: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "数据验证失败",
            "errors": exc.errors()
        }
    )

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """HTTP异常处理器"""
    logger.warning(f"HTTP异常: {exc.status_code} - {exc.detail}")
    return await http_exception_handler(request, exc)

# 工具函数使用模块化组件
# validate_video_file 和 extract_frames_from_video 现在在 video_processor 模块中

# update_task_status 现在通过 task_manager 模块处理

# run_3d_reconstruction 函数已移至 reconstruction_processor 模块

# API端点
@app.get("/", summary="健康检查")
async def root():
    """API健康检查端点"""
    return {"message": "InstantSplat 3D Reconstruction API is running", "version": "1.0.0"}

@app.post("/upload", response_model=UploadResponse, summary="上传包含多个图像的zip文件")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="包含多个图像的zip文件"),
    email: Optional[str] = None,
    points: Optional[str] = None
):
    """上传包含多个图像的zip文件并开始三维重建处理
    
    Args:
        file: 包含多个图像的zip文件
        email: 可选的邮件地址，用于接收处理完成通知
        points: 可选的分割点参数，格式为JSON字符串，例如"[(630, 283, 1, 0)]"或"[(630, 283, 1, 0), (400, 200, 1, 1)]"
    """
    logger.info(f"收到zip文件上传请求: {file.filename}, email参数: {email}")
    logger.info(f"email参数类型: {type(email)}, 是否为None: {email is None}")
    
    try:
        # 验证文件名
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="文件名不能为空"
            )
        
        # 检测文件类型并验证格式 - 仅支持zip格式
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in config.ALLOWED_ARCHIVE_FORMATS:
            logger.warning(f"不支持的文件格式: {file.filename}")
            raise HTTPException(
                status_code=400, 
                detail=f"仅支持zip格式文件。当前文件格式: {file_ext}"
            )
        
        # 检查文件大小
        try:
            file.file.seek(0, 2)  # 移动到文件末尾
            file_size = file.file.tell()
            file.file.seek(0)  # 重置到文件开头
        except Exception as e:
            logger.error(f"读取文件大小失败: {e}")
            raise HTTPException(
                status_code=400,
                detail="无法读取文件大小"
            )
        
        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="文件为空"
            )
        
        # 检查zip文件大小限制
        max_size = config.MAX_FILE_SIZE
        if file_size > max_size:
            logger.warning(f"zip文件大小超限: {file_size} > {max_size}")
            raise HTTPException(
                status_code=400,
                detail=f"zip文件大小超过限制({max_size // (1024*1024)}MB)"
            )
        
        # 验证zip文件
        if not validate_zip_file(file):
            logger.warning(f"zip文件验证失败: {file.filename}")
            raise HTTPException(
                status_code=400,
                detail="zip文件格式无效或已损坏"
            )
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        logger.info(f"生成任务ID: {task_id}")
        
        # 创建InstantSplat标准目录结构
        # assets/api_uploads/task_id/images/
        scene_dir = config.ASSETS_DIR / config.DATASET_NAME / task_id
        images_dir = scene_dir / "images"
        
        try:
            images_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"创建标准目录结构: {scene_dir}")
        except OSError as e:
            logger.error(f"创建任务目录失败: {e}")
            raise HTTPException(
                status_code=500,
                detail="创建任务目录失败"
            )
        
        # 处理zip文件：先保存到临时位置，然后解压
        temp_zip_path = images_dir.parent / f"temp_{file.filename}"
        try:
            with open(temp_zip_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            logger.info(f"zip文件保存成功: {temp_zip_path}")
            
            # 解压图像文件到images目录
            n_images = extract_images_from_zip(temp_zip_path, images_dir)
            
            # 删除临时zip文件
            temp_zip_path.unlink()
            
            # 如果提供了points参数，执行分割预处理
            if points:
                try:
                    logger.info(f"开始执行分割预处理，points参数: {points}")
                    await run_segmentation_preprocessing(str(images_dir), points)
                    logger.info("分割预处理完成")
                except Exception as seg_e:
                    logger.error(f"分割预处理失败: {seg_e}")
                    # 分割失败不影响后续处理，只记录错误
                    pass
            
        except Exception as e:
            logger.error(f"处理zip文件失败: {e}")
            # 清理文件
            if temp_zip_path.exists():
                temp_zip_path.unlink()
            if scene_dir.exists():
                shutil.rmtree(scene_dir, ignore_errors=True)
            raise HTTPException(
                status_code=500,
                detail="处理zip文件失败"
            )
        
        # 创建任务
        try:
            task_type = TaskType.IMAGE_RECONSTRUCTION
            task_params = {
                "task_id": task_id,
                "input_path": str(images_dir),
                "scene_path": str(scene_dir),
                "images_path": str(images_dir),
                "filename": file.filename,
                "file_size": file_size,
                "file_type": "multi_image",
                "email": email
            }
            
            task_manager.create_task(task_type, task_params)
        except Exception as e:
            logger.error(f"创建任务失败: {e}")
            # 清理文件
            if scene_dir.exists():
                shutil.rmtree(scene_dir, ignore_errors=True)
            raise HTTPException(
                status_code=500,
                detail="创建任务失败"
            )
        
        # 添加后台任务
        try:
            background_tasks.add_task(process_multi_image_task, task_id, n_images)
        except Exception as e:
            logger.error(f"添加后台任务失败: {e}")
            raise HTTPException(
                status_code=500,
                detail="启动处理任务失败"
            )
        
        logger.info(f"任务创建成功: {task_id}")
        return UploadResponse(
            task_id=task_id,
            message=f"zip文件上传成功，包含{n_images}张图像，开始处理",
            status="pending"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传处理异常: {e}")
        logger.error(f"异常详情: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="服务器内部错误"
        )


async def process_multi_image_task(task_id: str, n_images: int):
    """后台处理多图像重建任务（来自zip文件）"""
    logger.info(f"开始处理多图像重建任务 {task_id}: {n_images}张图像")
    task = task_manager.get_task(task_id)
    logger.info(f"任务 {task_id} keys: {task.input_data.keys()}")

    try:
        # 获取场景目录路径
        scene_path = config.ASSETS_DIR / config.DATASET_NAME / task_id
        images_dir = scene_path / "images"
        
        # 验证目录和文件
        if not scene_path.exists():
            raise FileNotFoundError(f"场景目录不存在: {scene_path}")
        if not images_dir.exists():
            raise FileNotFoundError(f"图像目录不存在: {images_dir}")
            
        # 检查图像文件数量
        image_files = list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.jpeg")) + list(images_dir.glob("*.png"))
        if len(image_files) < 3:
            raise Exception(f"图像数量不足: {len(image_files)} < 3（三维重建最少需要3张图像）")
            
        # 上传第一张图像到公网服务器（压缩为JPEG格式）
        first_image_url = None
        if image_files:
            try:
                first_image_path = image_files[2]
                
                # 创建临时JPEG文件
                temp_jpeg_path = Path(tempfile.mkdtemp()) / f"{task_id}.jpg"
                
                # 使用PIL压缩图像为JPEG格式
                with Image.open(first_image_path) as img:
                    # 如果是RGBA模式，转换为RGB
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')
                    # 保存为JPEG格式，质量设为85%
                    img.save(temp_jpeg_path, 'JPEG', quality=85, optimize=True)
                
                # 构建scp命令，使用固定的.jpg扩展名
                remote_filename = f"{task_id}.jpg"
                scp_command = [
                    "sshpass", "-p", "RAs@z4uY!n",
                    "scp", "-o", "StrictHostKeyChecking=no",
                    str(temp_jpeg_path),
                    f"Administrator@10.100.0.164:/E:/SceneGEN_data/{remote_filename}"
                ]
                
                logger.info(f"任务 {task_id}: 开始上传压缩后的第一张图像到公网服务器: {remote_filename}")
                result = subprocess.run(scp_command, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    first_image_url = f"https://livablecitylab.hkust-gz.edu.cn/SceneGEN_data/{remote_filename}"
                    logger.info(f"任务 {task_id}: 第一张图像上传成功，公网URL: {first_image_url}")
                    task_manager.set_field(task_id,"preview_image_url", first_image_url)
                else:
                    logger.error(f"任务 {task_id}: 第一张图像上传失败 - {result.stderr}")
                
                # 清理临时文件
                try:
                    temp_jpeg_path.unlink()
                    temp_jpeg_path.parent.rmdir()
                except Exception as cleanup_e:
                    logger.warning(f"任务 {task_id}: 清理临时文件失败 - {str(cleanup_e)}")
                    
            except subprocess.TimeoutExpired:
                logger.error(f"任务 {task_id}: 第一张图像上传超时")
            except Exception as e:
                logger.error(f"任务 {task_id}: 第一张图像上传异常 - {str(e)}")
            
        task_manager.update_task_status(task_id, TMTaskStatus.EXTRACTING)
        task_manager.update_task_progress(
            task_id, "处理多图像重建", 1, 5,
            {"message": f"正在处理{n_images}张图像..."}
        )
        
        logger.info(f"任务 {task_id}: 使用场景路径 {scene_path}，包含{len(image_files)}张图像")
        task_manager.update_task_progress(
            task_id, "准备三维重建", 2, 5,
            {"message": "准备多图像三维重建..."}
        )
        
        # 使用reconstruction_processor执行三维重建
        try:
            # 定义进度回调函数
            def progress_callback(progress, message=""):
                # 将进度转换为步骤信息
                percentage = int(progress * 100)
                task_manager.update_task_progress(task_id, message, percentage, 100, {"progress": progress})
            
            loop = asyncio.get_event_loop()
            reconstruction_result = await loop.run_in_executor(
                None, reconstruction_processor.process_reconstruction,
                str(scene_path), progress_callback
            )
            
            if reconstruction_result.success:
                task_manager.update_task_status(task_id, TMTaskStatus.COMPLETED)
                task_manager.update_task_progress(
                    task_id, "多图像三维重建完成", 5, 5,
                    {
                        "message": "多图像三维重建完成",
                        "output_dir": reconstruction_result.output_dir,
                        "processing_time": reconstruction_result.processing_time,
                        "files": reconstruction_result.files
                    }
                )
                
                # 设置任务结果数据，用于结果下载
                ply_file_path = reconstruction_result.files.get('point_cloud', '')

                # PLY文件压缩处理
                if ply_file_path and os.path.exists(ply_file_path):
                    try:
                        # 生成压缩文件路径
                        compressed_ply_path = ply_file_path.replace('.ply', '.compressed.ply')
                        
                        # 构建压缩命令
                        compress_cmd = [
                            "/opt/glibc-2.38/lib/ld-linux-x86-64.so.2",
                            "--library-path", "/opt/glibc-2.38/lib:/usr/lib/x86_64-linux-gnu",
                            "/home/livablecity/.nvm/versions/node/v22.17.1/bin/node",
                            "/home/livablecity/.nvm/versions/node/v22.17.1/bin/splat-transform",
                            ply_file_path,
                            compressed_ply_path
                        ]
                        
                        logger.info(f"任务 {task_id}: 开始压缩PLY文件: {ply_file_path} -> {compressed_ply_path}")
                        result = subprocess.run(compress_cmd, capture_output=True, text=True, timeout=300)
                        
                        if result.returncode == 0:
                            # 压缩成功，删除原文件并更新路径
                            original_size = os.path.getsize(ply_file_path)
                            compressed_size = os.path.getsize(compressed_ply_path)
                            compression_ratio = (1 - compressed_size / original_size) * 100
                            
                            logger.info(f"任务 {task_id}: PLY文件压缩成功，原大小: {original_size} bytes, 压缩后: {compressed_size} bytes, 压缩率: {compression_ratio:.1f}%")
                            
                            # 删除原文件
                            os.remove(ply_file_path)
                            # 更新文件路径为压缩后的文件
                            ply_file_path = compressed_ply_path
                        else:
                            logger.error(f"任务 {task_id}: PLY文件压缩失败: {result.stderr}")
                            logger.info(f"任务 {task_id}: 将使用原始PLY文件进行上传")
                    except Exception as compress_e:
                        logger.error(f"任务 {task_id}: PLY文件压缩过程出错: {compress_e}")
                        logger.info(f"任务 {task_id}: 将使用原始PLY文件进行上传")
                
                # 上传PLY文件到公网服务器
                public_url = None
                if ply_file_path and os.path.exists(ply_file_path):
                    try:
                        # 构建scp命令，将文件重命名为taskid.compressed.ply
                        remote_filename = f"{task_id}.compressed.ply"
                        scp_command = [
                            "sshpass", "-p", "RAs@z4uY!n",
                            "scp", "-o", "StrictHostKeyChecking=no",
                            ply_file_path,
                            f"Administrator@10.100.0.164:/E:/SceneGEN_data/{remote_filename}"
                        ]
                        
                        logger.info(f"任务 {task_id}: 开始上传PLY文件到公网服务器: {remote_filename}")
                        result = subprocess.run(scp_command, capture_output=True, text=True, timeout=300)
                        
                        if result.returncode == 0:
                            public_url = f"https://livablecitylab.hkust-gz.edu.cn/SceneGEN_data/{remote_filename}"
                            logger.info(f"任务 {task_id}: PLY文件上传成功，公网URL: {public_url}")
                        else:
                            logger.error(f"任务 {task_id}: PLY文件上传失败 - {result.stderr}")
                    except subprocess.TimeoutExpired:
                        logger.error(f"任务 {task_id}: PLY文件上传超时")
                    except Exception as e:
                        logger.error(f"任务 {task_id}: PLY文件上传异常 - {str(e)}")
                
                # 如果上传失败，设置默认公网URL为None，但仍然标记任务为完成
                if not public_url:
                    logger.warning(f"任务 {task_id}: PLY文件上传失败，但任务仍标记为完成")
                
                # 确保public_url存在才设置任务结果
                if public_url:
                    # 获取最终文件大小
                    final_file_size = compressed_size if compressed_size else 0
                    
                    task_manager.set_task_result(task_id, {
                        "output_path": reconstruction_result.output_dir,
                        "ply_file_path": ply_file_path,
                        "public_url": public_url,  # 添加公网URL
                        "files": reconstruction_result.files,
                        "metrics": reconstruction_result.metrics,
                        "processing_time": reconstruction_result.processing_time,
                        "file_size": final_file_size  # 添加文件大小
                    })
                else:
                    # 如果没有公网URL，任务标记为失败
                    raise Exception("PLY文件上传到公网服务器失败")
                
                logger.info(f"任务 {task_id}: 多图像三维重建完成，输出目录: {reconstruction_result.output_dir}")
                
                # 发送成功邮件通知
                task = task_manager.get_task(task_id)
                logger.info(f"开始发送邮件 - 任务task is None:{task is None}- task-email is None:{task.input_data.get('email') is None} keys: {task.input_data.keys()}")

                if task and task.input_data.get('email'):
                    try:
                        # 构建下载URL
                        logger.info(f"开始发送邮件 - 任务 {task_id} keys: {task.input_data.keys()}")

                        
                        
                        # 使用Supabase邮件通知器发送完成通知
                        await send_training_completion_email(
                            email=task.input_data.get('email'),
                            task_id=task_id,
                            success=True,
                            processing_time=reconstruction_result.processing_time,
                            public_url=public_url
                        )
                        logger.info(f"任务 {task_id}: 邮件通知发送成功")
                    except Exception as email_e:
                        logger.error(f"发送邮件通知失败 {task_id}: {email_e}")
            else:
                raise Exception(reconstruction_result.error_message or "多图像三维重建失败")
                
        except Exception as e:
            logger.error(f"多图像三维重建失败 {task_id}: {e}")
            raise Exception(f"多图像三维重建处理失败: {e}")
        
    except FileNotFoundError as e:
        logger.error(f"文件错误 {task_id}: {e}")
        task_manager.update_task_status(task_id, TMTaskStatus.FAILED, str(e))
        # 发送失败邮件通知
        task = task_manager.get_task(task_id)
        if task and task.input_data.get('email'):
            try:
                await send_training_completion_email(
                    email=task.input_data.get('email'),
                    task_id=task_id,
                    success=False,
                    error_message=str(e)
                )
            except Exception as email_e:
                logger.error(f"发送邮件通知失败 {task_id}: {email_e}")
    except PermissionError as e:
        logger.error(f"权限错误 {task_id}: {e}")
        error_msg = f"权限不足: {e}"
        task_manager.update_task_status(task_id, TMTaskStatus.FAILED, error_msg)
        # 发送失败邮件通知
        task = task_manager.get_task(task_id)
        if task and task.input_data.get('email'):
            try:
                await send_training_completion_email(
                    email=task.input_data.get('email'),
                    task_id=task_id,
                    success=False,
                    error_message=error_msg
                )
            except Exception as email_e:
                logger.error(f"发送邮件通知失败 {task_id}: {email_e}")
    except Exception as e:
        logger.error(f"多图像任务处理失败 {task_id}: {e}")
        logger.error(f"异常详情: {traceback.format_exc()}")
        task_manager.update_task_status(task_id, TMTaskStatus.FAILED, str(e))
        # 发送失败邮件通知
        task = task_manager.get_task(task_id)
        if task and task.input_data.get('email'):
            try:
                await send_training_completion_email(
                    email=task.input_data.get('email'),
                    task_id=task_id,
                    success=False,
                    error_message=str(e)
                )
            except Exception as email_e:
                logger.error(f"发送邮件通知失败 {task_id}: {email_e}")

@app.get("/status/{task_id}", response_model=TaskStatusResponse, summary="查询任务状态")
async def get_task_status(task_id: str):
    """查询指定任务的处理状态"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return TaskStatusResponse(
        task_id=task_id,
        status=task.status.value,
        progress=task.progress.percentage if task.progress else 0,
        current_step=task.progress.current_step if task.progress else "",
        message=task.progress.message if task.progress else "",
        error_message=task.error_message or "",
        created_at=task.created_at,
        updated_at=task.updated_at,
        result_path=task.result_data.get('output_path', '') if task.result_data else '',
        estimated_time_remaining=task.progress.estimated_time_remaining if task.progress else None,
        processing_time=task.processing_time
    )

@app.get("/tasks", summary="获取所有任务列表")
async def list_all_tasks():
    """获取所有任务的状态列表"""
    tasks = task_manager.list_tasks()
    return {"tasks": [
        {
            "task_id": task.task_id,
            "status": task.status.value,
            "progress": task.progress.percentage if task.progress else 0,
            "created_at": task.created_at,
            "updated_at": task.updated_at
        } for task in tasks
    ]}

@app.get("/result/{task_id}", response_model=ResultResponse, summary="获取处理结果信息")
async def get_result_info(task_id: str):
    """获取任务处理结果的文件信息和下载链接"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status != TMTaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    if not task.result_data:
        raise HTTPException(status_code=404, detail="结果路径不存在")
    
    # 任务完成后直接返回公网URL
    public_url = task.result_data.get('public_url')
    if public_url:
        file_info = FileInfo(
            file_id=f"{task_id}_point_cloud",
            filename=f"{task_id}.ply",
            file_size=0,  # 公网文件大小暂时设为0
            file_type="application/octet-stream",
            download_url=config.VIEWER_URL+"content="+public_url  # 直接使用公网URL
        )
        
        return ResultResponse(
            task_id=task_id,
            status=task.status.value,
            files=[file_info],
            message="结果文件已上传到公网服务器"
        )
    
    # 如果没有公网URL，说明上传失败，返回错误
    raise HTTPException(status_code=500, detail="PLY文件上传到公网服务器失败")

@app.delete("/task/{task_id}", summary="删除任务")
async def delete_task(task_id: str):
    """删除指定的任务及其相关文件"""
    logger.info(f"删除任务请求: {task_id}")
    
    try:
        task = task_manager.get_task(task_id)
        if not task:
            logger.warning(f"尝试删除不存在的任务: {task_id}")
            raise HTTPException(status_code=404, detail="任务不存在")
        
        # 删除任务文件
        deleted_dirs = []
        
        # 删除assets目录下的任务文件
        scene_dir = config.ASSETS_DIR / config.DATASET_NAME / task_id
        if scene_dir.exists():
            try:
                shutil.rmtree(scene_dir)
                deleted_dirs.append(str(scene_dir))
                logger.info(f"删除场景目录: {scene_dir}")
            except Exception as e:
                logger.error(f"删除场景目录失败 {scene_dir}: {e}")
        
        task_dir = config.TEMP_DIR / task_id
        if task_dir.exists():
            try:
                shutil.rmtree(task_dir)
                deleted_dirs.append(str(task_dir))
                logger.info(f"删除临时目录: {task_dir}")
            except Exception as e:
                logger.error(f"删除临时目录失败 {task_dir}: {e}")
        
        output_dir = config.OUTPUT_DIR / task_id
        if output_dir.exists():
            try:
                shutil.rmtree(output_dir)
                deleted_dirs.append(str(output_dir))
                logger.info(f"删除输出目录: {output_dir}")
            except Exception as e:
                logger.error(f"删除输出目录失败 {output_dir}: {e}")
        
        # 删除任务记录
        try:
            task_manager.cancel_task(task_id)
            logger.info(f"任务记录已删除: {task_id}")
        except Exception as e:
            logger.error(f"删除任务记录失败: {e}")
            raise HTTPException(
                status_code=500,
                detail="删除任务记录失败"
            )
        
        return {
            "message": "任务已删除",
            "task_id": task_id,
            "deleted_directories": deleted_dirs
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除任务异常 {task_id}: {e}")
        logger.error(f"异常详情: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="删除任务时发生错误"
        )

if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=3080,
        reload=True,
        log_level="info"
    )