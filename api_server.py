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
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import json
import subprocess
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exception_handlers import http_exception_handler
from pydantic import BaseModel, Field, ValidationError
import uvicorn
import logging
import traceback

# 导入自定义模块
from task_manager import TaskManager, TaskStatus as TMTaskStatus, TaskType, task_manager
from video_processor import VideoProcessor, video_processor, ImageProcessor, image_processor
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

@app.post("/upload", response_model=UploadResponse, summary="上传图像或视频文件")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="图像或视频文件 (支持JPG/PNG/MP4/MOV/AVI等格式)"),
    email: Optional[str] = None
):
    """上传图像或视频文件并开始三维重建处理"""
    logger.info(f"收到文件上传请求: {file.filename}, email参数: {email}")
    logger.info(f"email参数类型: {type(email)}, 是否为None: {email is None}")
    
    try:
        # 验证文件名
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="文件名不能为空"
            )
        
        # 检测文件类型并验证格式
        file_ext = Path(file.filename).suffix.lower()
        is_video = file_ext in config.ALLOWED_VIDEO_FORMATS
        is_image = file_ext in config.ALLOWED_IMAGE_FORMATS
        is_archive = file_ext in config.ALLOWED_ARCHIVE_FORMATS
        
        if not is_video and not is_image and not is_archive:
            logger.warning(f"不支持的文件格式: {file.filename}")
            supported_formats = list(config.ALLOWED_VIDEO_FORMATS) + list(config.ALLOWED_IMAGE_FORMATS) + list(config.ALLOWED_ARCHIVE_FORMATS)
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的文件格式。支持的格式: {', '.join(supported_formats)}"
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
        
        # 根据文件类型检查大小限制
        if is_image:
            max_size = config.MAX_IMAGE_SIZE
            size_type = "图像"
        elif is_archive:
            max_size = config.MAX_FILE_SIZE  # zip文件使用视频文件的大小限制
            size_type = "压缩包"
        else:
            max_size = config.MAX_FILE_SIZE
            size_type = "视频"
        
        if file_size > max_size:
            logger.warning(f"{size_type}文件大小超限: {file_size} > {max_size}")
            raise HTTPException(
                status_code=400,
                detail=f"{size_type}文件大小超过限制({max_size // (1024*1024)}MB)"
            )
        
        # 根据文件类型进行详细验证
        if is_video:
            if not video_processor.validate_video_file(file, config):
                logger.warning(f"视频文件验证失败: {file.filename}")
                raise HTTPException(
                    status_code=400,
                    detail="视频文件格式无效或已损坏"
                )
        elif is_image:
            if not image_processor.validate_image_file(file, config):
                logger.warning(f"图像文件验证失败: {file.filename}")
                raise HTTPException(
                    status_code=400,
                    detail="图像文件格式无效或已损坏"
                )
        elif is_archive:
            # 验证zip文件
            if not validate_zip_file(file):
                logger.warning(f"压缩包文件验证失败: {file.filename}")
                raise HTTPException(
                    status_code=400,
                    detail="压缩包文件格式无效或已损坏"
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
        
        # 保存上传的文件到images目录
        file_ext = Path(file.filename).suffix.lower()
        n_images = 1  # 默认图像数量
        
        if is_archive:
            # zip文件：先保存到临时位置，然后解压
            temp_zip_path = images_dir.parent / f"temp_{file.filename}"
            try:
                with open(temp_zip_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                logger.info(f"zip文件保存成功: {temp_zip_path}")
                
                # 解压图像文件到images目录
                n_images = extract_images_from_zip(temp_zip_path, images_dir)
                
                # 删除临时zip文件
                temp_zip_path.unlink()
                
                file_path = images_dir  # 对于zip文件，file_path指向images目录
                
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
        else:
            # 单个文件处理
            if is_image:
                # 图像文件使用000000.ext格式
                standard_filename = f"000000{file_ext}"
            else:
                # 视频文件保持原名，后续提取帧时会重命名
                standard_filename = file.filename
                
            file_path = images_dir / standard_filename
            try:
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                logger.info(f"文件保存成功: {file_path}")
            except Exception as e:
                logger.error(f"保存文件失败: {e}")
                # 清理已创建的目录
                if scene_dir.exists():
                    shutil.rmtree(scene_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=500,
                    detail="保存文件失败"
                )
        
        # 创建任务
        try:
            task_type = TaskType.VIDEO_RECONSTRUCTION if is_video else TaskType.IMAGE_RECONSTRUCTION
            task_params = {
                "task_id": task_id,
                "input_path": str(file_path),
                "scene_path": str(scene_dir),
                "images_path": str(images_dir),
                "filename": file.filename,
                "file_size": file_size,
                "file_type": "video" if is_video else "image",
                "email": email
            }
            
            if is_video:
                task_params["n_frames"] = config.N_FRAMES
            
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
            if is_video:
                background_tasks.add_task(process_video_task, task_id, file_path)
            elif is_archive:
                background_tasks.add_task(process_multi_image_task, task_id, n_images)
            else:
                background_tasks.add_task(process_image_task, task_id, file_path)
        except Exception as e:
            logger.error(f"添加后台任务失败: {e}")
            raise HTTPException(
                status_code=500,
                detail="启动处理任务失败"
            )
        
        logger.info(f"任务创建成功: {task_id}")
        file_type_msg = "视频" if is_video else "图像"
        return UploadResponse(
            task_id=task_id,
            message=f"{file_type_msg}上传成功，开始处理",
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

async def process_video_task(task_id: str, video_path: Path):
    """后台处理视频任务"""
    logger.info(f"开始处理任务 {task_id}: {video_path}")
    
    try:
        # 验证输入文件
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        task_manager.update_task_status(task_id, TMTaskStatus.EXTRACTING)
        task_manager.update_task_progress(
            task_id, "提取帧", 1, 5,
            {"message": "正在从视频中提取帧..."}
        )
        
        # 创建输出目录
        task_dir = video_path.parent  # 这是 assets/api_uploads/task_id/images/
        scene_dir = task_dir.parent   # 这是 assets/api_uploads/task_id/
        frames_dir = scene_dir / "images"
        output_dir = config.OUTPUT_DIR / task_id
        
        try:
            frames_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise Exception(f"创建目录失败: {e}")
        
        # 使用video_processor提取帧
        try:
            frames = video_processor.extract_frames_fps_based(
                video_path, frames_dir, fps=1
            )
        except Exception as e:
            logger.error(f"帧提取失败 {task_id}: {e}")
            raise Exception(f"视频帧提取失败: {e}")
        
        # 检查提取的帧数（至少需要3帧进行三维重建）
        if len(frames) < 3:
            error_msg = f"提取的帧数不足: {len(frames)} < 3（三维重建最少需要3帧）"
            logger.warning(f"任务 {task_id}: {error_msg}")
            raise Exception(error_msg)
        
        logger.info(f"任务 {task_id}: 成功提取 {len(frames)} 帧")
        task_manager.update_task_progress(
            task_id, "帧提取完成", 2, 5,
            {"message": f"成功提取{len(frames)}帧"}
        )
        
        # 使用reconstruction_processor执行三维重建
        try:
            # 定义进度回调函数
            def progress_callback(progress, message=""):
                # 将进度转换为步骤信息
                percentage = int(progress * 100)
                task_manager.update_task_progress(task_id, message, percentage, 100, {"progress": progress})
            
            # 获取场景目录路径（scene_dir即为scene_path）
            scene_path = scene_dir
            
            loop = asyncio.get_event_loop()
            reconstruction_result = await loop.run_in_executor(
                None, reconstruction_processor.process_reconstruction,
                scene_path, progress_callback
            )
            
            if reconstruction_result.success:
                task_manager.update_task_status(task_id, TMTaskStatus.COMPLETED)
                
                # 设置任务结果数据，用于结果下载
                ply_file_path = reconstruction_result.files.get('point_cloud', '')
                task_manager.set_task_result(task_id, {
                    "output_path": reconstruction_result.output_dir,
                    "ply_file_path": ply_file_path,
                    "files": reconstruction_result.files,
                    "metrics": reconstruction_result.metrics,
                    "processing_time": reconstruction_result.processing_time
                })
                
                logger.info(f"任务 {task_id}: 三维重建完成，输出目录: {reconstruction_result.output_dir}")
                
                # 任务成功完成，发送邮件通知
                task = task_manager.get_task(task_id)
                if task and task.input_data.get('email'):
                    try:
                        # 构建下载URL（如果需要）
                        download_url = f"/result/{task_id}"  # 相对URL，前端可以构建完整URL
                        
                        # 使用Supabase邮件通知器发送完成通知
                        # 创建新的事件循环任务来处理异步邮件发送
                        loop = asyncio.get_event_loop()
                        email_task = loop.create_task(send_training_completion_email(
                            email=task.input_data.get('email'),
                            task_id=task_id,
                            success=True,
                            processing_time=reconstruction_result.processing_time,
                            download_url=download_url
                        ))
                        # 等待邮件发送完成，但设置超时
                        await asyncio.wait_for(email_task, timeout=60.0)
                        logger.info(f"任务 {task_id}: 邮件通知发送成功")
                    except Exception as e:
                        logger.error(f"发送邮件通知失败 {task_id}: {e}")
            else:
                raise Exception(reconstruction_result.error_message or "视频三维重建失败")
        except Exception as e:
            logger.error(f"三维重建失败 {task_id}: {e}")
            raise Exception(f"三维重建处理失败: {e}")
        
    except FileNotFoundError as e:
        logger.error(f"文件错误 {task_id}: {e}")
        task_manager.update_task_status(task_id, TMTaskStatus.FAILED, str(e))
        # 发送失败邮件通知
        task = task_manager.get_task(task_id)
        if task and task.input_data.get('email'):
            try:
                # 创建新的事件循环任务来处理异步邮件发送
                loop = asyncio.get_event_loop()
                email_task = loop.create_task(send_training_completion_email(
                    email=task.input_data.get('email'),
                    task_id=task_id,
                    success=False,
                    error_message=str(e)
                ))
                # 等待邮件发送完成，但设置超时
                await asyncio.wait_for(email_task, timeout=60.0)
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
                # 创建新的事件循环任务来处理异步邮件发送
                loop = asyncio.get_event_loop()
                email_task = loop.create_task(send_training_completion_email(
                    email=task.input_data.get('email'),
                    task_id=task_id,
                    success=False,
                    error_message=error_msg
                ))
                # 等待邮件发送完成，但设置超时
                await asyncio.wait_for(email_task, timeout=60.0)
            except Exception as email_e:
                logger.error(f"发送邮件通知失败 {task_id}: {email_e}")
    except Exception as e:
        logger.error(f"任务处理失败 {task_id}: {e}")
        logger.error(f"异常详情: {traceback.format_exc()}")
        task_manager.update_task_status(task_id, TMTaskStatus.FAILED, str(e))
        # 发送失败邮件通知
        task = task_manager.get_task(task_id)
        if task and task.input_data.get('email'):
            try:
                # 创建新的事件循环任务来处理异步邮件发送
                loop = asyncio.get_event_loop()
                email_task = loop.create_task(send_training_completion_email(
                    email=task.input_data.get('email'),
                    task_id=task_id,
                    success=False,
                    error_message=str(e)
                ))
                # 等待邮件发送完成，但设置超时
                await asyncio.wait_for(email_task, timeout=60.0)
            except Exception as email_e:
                logger.error(f"发送邮件通知失败 {task_id}: {email_e}")

async def process_image_task(task_id: str, image_path: Path):
    """后台处理图像任务"""
    logger.info(f"开始处理图像任务 {task_id}: {image_path}")
    
    try:
        # 验证输入文件
        if not image_path.exists():
            raise FileNotFoundError(f"图像文件不存在: {image_path}")
        
        task_manager.update_task_status(task_id, TMTaskStatus.EXTRACTING)
        task_manager.update_task_progress(
            task_id, "处理图像", 1, 5,
            {"message": "正在处理图像文件..."}
        )
        
        # 获取场景目录路径 (assets/api_uploads/task_id/)
        scene_path = image_path.parent.parent  # 从images目录向上两级到scene目录
        
        # 验证目录结构
        images_dir = scene_path / "images"
        if not images_dir.exists():
            raise Exception(f"Images目录不存在: {images_dir}")
        
        logger.info(f"任务 {task_id}: 使用场景路径 {scene_path}")
        task_manager.update_task_progress(
            task_id, "准备三维重建", 2, 5,
            {"message": "准备三维重建..."}
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
                    task_id, "三维重建完成", 5, 5,
                    {
                        "message": "三维重建完成",
                        "output_dir": reconstruction_result.output_dir,
                        "processing_time": reconstruction_result.processing_time,
                        "files": reconstruction_result.files
                    }
                )
                
                # 设置任务结果数据，用于结果下载
                ply_file_path = reconstruction_result.files.get('point_cloud', '')
                task_manager.set_task_result(task_id, {
                    "output_path": reconstruction_result.output_dir,
                    "ply_file_path": ply_file_path,
                    "files": reconstruction_result.files,
                    "metrics": reconstruction_result.metrics,
                    "processing_time": reconstruction_result.processing_time
                })
                
                logger.info(f"任务 {task_id}: 三维重建完成，输出目录: {reconstruction_result.output_dir}")
                
                # 发送成功邮件通知
                task = task_manager.get_task(task_id)
                logger.info(f"任务 {task_id}: 检查邮件发送条件 - task存在: {task is not None}")
                if task:
                    logger.info(f"任务 {task_id}: input_data: {task.input_data}")
                    email = task.input_data.get('email')
                    logger.info(f"任务 {task_id}: 邮箱地址: {email}")
                if task and task.input_data.get('email'):
                    try:
                        # 构建下载URL
                        download_url = f"/result/{task_id}"
                        logger.info(f"任务 {task_id}: 开始发送邮件通知到 {task.input_data.get('email')}")
                        
                        # 创建新的事件循环任务来处理异步邮件发送
                        loop = asyncio.get_event_loop()
                        email_task = loop.create_task(send_training_completion_email(
                            email=task.input_data.get('email'),
                            task_id=task_id,
                            success=True,
                            processing_time=reconstruction_result.processing_time,
                            download_url=download_url
                        ))
                        # 等待邮件发送完成，但设置超时
                        await asyncio.wait_for(email_task, timeout=60.0)
                        logger.info(f"任务 {task_id}: 邮件通知发送成功")
                    except Exception as email_e:
                        logger.error(f"发送邮件通知失败 {task_id}: {email_e}")
                else:
                    logger.info(f"任务 {task_id}: 跳过邮件发送 - 无邮箱地址或任务不存在")
            else:
                raise Exception(reconstruction_result.error_message or "三维重建失败")
                
        except Exception as e:
            logger.error(f"三维重建失败 {task_id}: {e}")
            raise Exception(f"三维重建处理失败: {e}")
        
    except FileNotFoundError as e:
        logger.error(f"文件错误 {task_id}: {e}")
        task_manager.update_task_status(task_id, TMTaskStatus.FAILED, str(e))
        # 发送失败邮件通知
        task = task_manager.get_task(task_id)
        if task and task.input_data.get('email'):
            try:
                # 创建新的事件循环任务来处理异步邮件发送
                loop = asyncio.get_event_loop()
                email_task = loop.create_task(send_training_completion_email(
                    email=task.input_data.get('email'),
                    task_id=task_id,
                    success=False,
                    error_message=str(e)
                ))
                # 等待邮件发送完成，但设置超时
                await asyncio.wait_for(email_task, timeout=60.0)
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
                # 创建新的事件循环任务来处理异步邮件发送
                loop = asyncio.get_event_loop()
                email_task = loop.create_task(send_training_completion_email(
                    email=task.input_data.get('email'),
                    task_id=task_id,
                    success=False,
                    error_message=error_msg
                ))
                # 等待邮件发送完成，但设置超时
                await asyncio.wait_for(email_task, timeout=60.0)
            except Exception as email_e:
                logger.error(f"发送邮件通知失败 {task_id}: {email_e}")
    except Exception as e:
        logger.error(f"图像任务处理失败 {task_id}: {e}")
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
                task_manager.set_task_result(task_id, {
                    "output_path": reconstruction_result.output_dir,
                    "ply_file_path": ply_file_path,
                    "files": reconstruction_result.files,
                    "metrics": reconstruction_result.metrics,
                    "processing_time": reconstruction_result.processing_time
                })
                
                logger.info(f"任务 {task_id}: 多图像三维重建完成，输出目录: {reconstruction_result.output_dir}")
                
                # 发送成功邮件通知
                task = task_manager.get_task(task_id)
                logger.info(f"开始发送邮件 - 任务task is None:{task is None}- task-email is None:{task.input_data.get('email') is None} keys: {task.input_data.keys()}")

                if task and task.input_data.get('email'):
                    try:
                        # 构建下载URL
                        logger.info(f"开始发送邮件 - 任务 {task_id} keys: {task.input_data.keys()}")

                        download_url = f"/result/{task_id}"
                        
                        # 使用Supabase邮件通知器发送完成通知
                        await send_training_completion_email(
                            email=task.input_data.get('email'),
                            task_id=task_id,
                            success=True,
                            processing_time=reconstruction_result.processing_time,
                            download_url=download_url
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

@app.get("/result/{task_id}", summary="下载处理结果")
async def download_result(task_id: str):
    """下载任务处理结果"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status != TMTaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    if not task.result_data or not task.result_data.get('ply_file_path'):
        raise HTTPException(status_code=404, detail="结果文件不存在")
        
    ply_file_path = Path(task.result_data['ply_file_path'])
    if not ply_file_path.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")
    
    if not ply_file_path.is_file():
        raise HTTPException(status_code=500, detail=f"File at path {ply_file_path} is not a file.")
    
    return FileResponse(
        path=str(ply_file_path),
        filename=f"point_cloud_{task_id}.ply",
        media_type="application/octet-stream"
    )

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