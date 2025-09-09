#!/usr/bin/env python3
"""
视频处理模块 - 处理视频上传、验证、帧提取等功能
"""

import os
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import tempfile
import shutil
from PIL import Image, ImageOps
import logging

from config import api_config, video_config

class ImageProcessor:
    """图像处理器类"""
    
    def __init__(self):
        self.config = api_config
        self.video_config = video_config
    
    def validate_image_file(self, file_path: Path, max_size: Optional[int] = None) -> Dict[str, Any]:
        """验证图像文件
        
        Args:
            file_path: 图像文件路径
            max_size: 最大文件大小（字节）
            
        Returns:
            验证结果字典，包含是否有效、错误信息、图像信息等
        """
        result = {
            "valid": False,
            "error": None,
            "info": {}
        }
        
        try:
            # 检查文件是否存在
            if not file_path.exists():
                result["error"] = "文件不存在"
                return result
            
            # 检查文件扩展名
            file_ext = file_path.suffix.lower()
            allowed_formats = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp']
            if file_ext not in allowed_formats:
                result["error"] = f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(allowed_formats)}"
                return result
            
            # 检查文件大小
            file_size = file_path.stat().st_size
            max_size = max_size or self.config.MAX_FILE_SIZE
            if file_size > max_size:
                result["error"] = f"文件大小({file_size / (1024*1024):.1f}MB)超过限制({max_size / (1024*1024):.1f}MB)"
                return result
            
            # 使用PIL验证图像文件
            try:
                with Image.open(file_path) as img:
                    # 获取图像信息
                    width, height = img.size
                    format_name = img.format
                    mode = img.mode
                    
                    # 验证图像完整性
                    img.verify()
                    
                    # 验证通过
                    result["valid"] = True
                    result["info"] = {
                        "file_size": file_size,
                        "width": width,
                        "height": height,
                        "format": format_name,
                        "mode": mode,
                        "aspect_ratio": width / height if height > 0 else 0
                    }
                    
            except Exception as e:
                result["error"] = f"无法打开或验证图像文件: {str(e)}"
                return result
                
        except Exception as e:
            result["error"] = f"图像验证过程中发生错误: {str(e)}"
            logger.error(f"图像验证错误: {e}")
        
        return result
    
    def preprocess_image(self, image_path: Path, output_path: Path, 
                        max_dimension: Optional[int] = None, quality: int = 95) -> Path:
        """预处理图像
        
        Args:
            image_path: 输入图像路径
            output_path: 输出图像路径
            max_dimension: 最大尺寸限制
            quality: JPEG质量
            
        Returns:
            处理后的图像路径
        """
        max_dimension = max_dimension or self.video_config.PREPROCESSING["resize_max_dimension"]
        
        with Image.open(image_path) as img:
            # 转换为RGB模式（如果需要）
            if img.mode in ('RGBA', 'LA', 'P'):
                # 创建白色背景
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 调整尺寸
            width, height = img.size
            if max(width, height) > max_dimension:
                if width > height:
                    new_width, new_height = max_dimension, int(height * max_dimension / width)
                else:
                    new_width, new_height = int(width * max_dimension / height), max_dimension
                
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 自动调整方向（基于EXIF信息）
            img = ImageOps.exif_transpose(img)
            
            # 保存处理后的图像
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path, 'JPEG', quality=quality, optimize=True)
            
        logger.info(f"图像预处理完成: {image_path.name} -> {output_path.name}")
        return output_path
    
    def process_image(self, input_path: Path, output_dir: Path, 
                             max_dimension: Optional[int] = None, quality: int = 95) -> Path:
        """处理单个图像文件
        
        Args:
            input_path: 输入图像路径
            output_dir: 输出目录路径
            max_dimension: 最大尺寸限制
            quality: JPEG质量
            
        Returns:
            处理后的图像路径
        """
        # 验证输入文件
        validation_result = self.validate_image_file_path(input_path)
        if not validation_result["valid"]:
            raise ValueError(f"图像文件验证失败: {validation_result['error']}")
        
        # 确保输出目录存在
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成输出文件路径
        output_filename = f"processed_{input_path.stem}.jpg"
        output_path = output_dir / output_filename
        
        max_dimension = max_dimension or self.video_config.PREPROCESSING["resize_max_dimension"]
        
        with Image.open(input_path) as img:
            # 自动调整方向（基于EXIF信息）
            img = ImageOps.exif_transpose(img)
            
            # 转换为RGB模式（如果需要）
            if img.mode in ('RGBA', 'LA', 'P'):
                # 创建白色背景
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 调整尺寸
            width, height = img.size
            if max(width, height) > max_dimension:
                if width > height:
                    new_width, new_height = max_dimension, int(height * max_dimension / width)
                else:
                    new_width, new_height = int(width * max_dimension / height), max_dimension
                
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 保存处理后的图像
            img.save(output_path, 'JPEG', quality=quality, optimize=True)
            
        logger.info(f"图像处理完成: {input_path.name} -> {output_path.name}")
        return output_path
    
    def validate_image_file_path(self, file_path: Path, max_size: Optional[int] = None) -> Dict[str, Any]:
        """验证图像文件路径
        
        Args:
            file_path: 图像文件路径
            max_size: 最大文件大小（字节）
            
        Returns:
            验证结果字典
        """
        result = {
            "valid": False,
            "error": None,
            "info": {}
        }
        
        try:
            # 检查文件是否存在
            if not file_path.exists():
                result["error"] = "文件不存在"
                return result
            
            # 检查文件扩展名
            file_ext = file_path.suffix.lower()
            allowed_formats = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp']
            if file_ext not in allowed_formats:
                result["error"] = f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(allowed_formats)}"
                return result
            
            # 检查文件大小
            file_size = file_path.stat().st_size
            max_size = max_size or self.config.MAX_FILE_SIZE
            if file_size > max_size:
                result["error"] = f"文件大小({file_size / (1024*1024):.1f}MB)超过限制({max_size / (1024*1024):.1f}MB)"
                return result
            
            # 使用PIL验证图像文件
            try:
                with Image.open(file_path) as img:
                    # 验证图像完整性
                    img.verify()
                    
                # 重新打开获取信息（verify后需要重新打开）
                with Image.open(file_path) as img:
                    width, height = img.size
                    format_name = img.format
                    mode = img.mode
                    
                    result["valid"] = True
                    result["info"] = {
                        "file_size": file_size,
                        "width": width,
                        "height": height,
                        "format": format_name,
                        "mode": mode,
                        "aspect_ratio": width / height if height > 0 else 0
                    }
                    
            except Exception as e:
                result["error"] = f"无法打开或验证图像文件: {str(e)}"
                return result
                
        except Exception as e:
            result["error"] = f"图像验证过程中发生错误: {str(e)}"
            logger.error(f"图像验证错误: {e}")
        
        return result
    
    def get_image_info(self, image_path: Path) -> Dict[str, Any]:
        """获取图像详细信息
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            图像信息字典
        """
        with Image.open(image_path) as img:
            info = {
                "filename": image_path.name,
                "file_size": image_path.stat().st_size,
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "mode": img.mode,
                "aspect_ratio": img.width / img.height if img.height > 0 else 0
            }
            
            # 获取EXIF信息（如果有）
            if hasattr(img, '_getexif') and img._getexif() is not None:
                info["has_exif"] = True
            else:
                info["has_exif"] = False
                
            return info

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoProcessor:
    """视频处理器类"""
    
    def __init__(self):
        self.config = api_config
        self.video_config = video_config
    
    def validate_video_file(self, file_path: Path, max_size: Optional[int] = None) -> Dict[str, Any]:
        """验证视频文件
        
        Args:
            file_path: 视频文件路径
            max_size: 最大文件大小（字节）
            
        Returns:
            验证结果字典，包含是否有效、错误信息、视频信息等
        """
        result = {
            "valid": False,
            "error": None,
            "info": {}
        }
        
        try:
            # 检查文件是否存在
            if not file_path.exists():
                result["error"] = "文件不存在"
                return result
            
            # 检查文件扩展名
            file_ext = file_path.suffix.lower()
            if file_ext not in self.config.ALLOWED_VIDEO_FORMATS:
                result["error"] = f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(self.config.ALLOWED_VIDEO_FORMATS)}"
                return result
            
            # 检查文件大小
            file_size = file_path.stat().st_size
            max_size = max_size or self.config.MAX_FILE_SIZE
            if file_size > max_size:
                result["error"] = f"文件大小({file_size / (1024*1024):.1f}MB)超过限制({max_size / (1024*1024):.1f}MB)"
                return result
            
            # 使用OpenCV验证视频文件
            cap = cv2.VideoCapture(str(file_path))
            if not cap.isOpened():
                result["error"] = "无法打开视频文件，可能文件损坏或格式不支持"
                return result
            
            # 获取视频信息
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            
            cap.release()
            
            # 检查视频参数
            if frame_count < self.config.N_FRAMES:
                result["error"] = f"视频帧数({frame_count})少于所需最小帧数({self.config.N_FRAMES})"
                return result
            
            if duration > self.video_config.PREPROCESSING["duration_limit"]:
                result["error"] = f"视频时长({duration:.1f}秒)超过限制({self.video_config.PREPROCESSING['duration_limit']}秒)"
                return result
            
            if fps > self.video_config.PREPROCESSING["fps_limit"]:
                logger.warning(f"视频FPS({fps})较高，可能影响处理速度")
            
            # 验证通过
            result["valid"] = True
            result["info"] = {
                "file_size": file_size,
                "duration": duration,
                "fps": fps,
                "frame_count": frame_count,
                "width": width,
                "height": height,
                "format": file_ext
            }
            
        except Exception as e:
            result["error"] = f"视频验证过程中发生错误: {str(e)}"
            logger.error(f"视频验证错误: {e}")
        
        return result
    
    def extract_frames_uniform(self, video_path: Path, output_dir: Path, 
                              n_frames: int, quality: int = 95) -> List[Path]:
        """从视频中均匀提取帧
        
        Args:
            video_path: 视频文件路径
            output_dir: 输出目录
            n_frames: 要提取的帧数
            quality: JPEG质量(1-100)
            
        Returns:
            提取的帧文件路径列表
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")
        
        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if total_frames < n_frames:
                raise ValueError(f"视频帧数({total_frames})少于所需帧数({n_frames})")
            
            # 计算均匀采样的帧索引
            if n_frames == 1:
                frame_indices = [total_frames // 2]  # 取中间帧
            else:
                frame_indices = np.linspace(0, total_frames - 1, n_frames, dtype=int)
            
            extracted_frames = []
            
            for i, frame_idx in enumerate(frame_indices):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if not ret:
                    logger.warning(f"无法读取第{frame_idx}帧，跳过")
                    continue
                
                # 预处理帧
                frame = self._preprocess_frame(frame)
                
                # 保存帧
                frame_filename = f"frame_{i:04d}.jpg"
                frame_path = output_dir / frame_filename
                
                # 使用OpenCV保存，设置JPEG质量
                cv2.imwrite(
                    str(frame_path), 
                    frame, 
                    [cv2.IMWRITE_JPEG_QUALITY, quality]
                )
                
                extracted_frames.append(frame_path)
                logger.info(f"提取帧 {i+1}/{n_frames}: {frame_filename}")
            
            if len(extracted_frames) < n_frames:
                logger.warning(f"实际提取帧数({len(extracted_frames)})少于预期({n_frames})")
            
            return extracted_frames
            
        finally:
            cap.release()
    
    def extract_frames_keyframe(self, video_path: Path, output_dir: Path, 
                               n_frames: int, quality: int = 95) -> List[Path]:
        """从视频中提取关键帧
        
        Args:
            video_path: 视频文件路径
            output_dir: 输出目录
            n_frames: 要提取的帧数
            quality: JPEG质量
            
        Returns:
            提取的关键帧文件路径列表
        """
        # 这里可以实现更复杂的关键帧检测算法
        # 目前使用简化版本，基于帧差检测
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")
        
        try:
            frames_info = []
            prev_frame = None
            frame_idx = 0
            
            # 分析所有帧，计算帧差
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                if prev_frame is not None:
                    # 计算帧差
                    diff = cv2.absdiff(gray, prev_frame)
                    diff_score = np.mean(diff)
                    frames_info.append((frame_idx, diff_score, frame.copy()))
                else:
                    frames_info.append((frame_idx, 0, frame.copy()))
                
                prev_frame = gray
                frame_idx += 1
            
            # 按帧差排序，选择变化最大的帧作为关键帧
            frames_info.sort(key=lambda x: x[1], reverse=True)
            selected_frames = frames_info[:n_frames]
            selected_frames.sort(key=lambda x: x[0])  # 按时间顺序排序
            
            extracted_frames = []
            for i, (orig_idx, diff_score, frame) in enumerate(selected_frames):
                # 预处理帧
                frame = self._preprocess_frame(frame)
                
                # 保存帧
                frame_filename = f"keyframe_{i:04d}.jpg"
                frame_path = output_dir / frame_filename
                
                cv2.imwrite(
                    str(frame_path), 
                    frame, 
                    [cv2.IMWRITE_JPEG_QUALITY, quality]
                )
                
                extracted_frames.append(frame_path)
                logger.info(f"提取关键帧 {i+1}/{n_frames}: {frame_filename} (原始帧{orig_idx}, 差值{diff_score:.2f})")
            
            return extracted_frames
            
        finally:
            cap.release()
    
    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """预处理单帧图像
        
        Args:
            frame: 输入帧(BGR格式)
            
        Returns:
            处理后的帧
        """
        # 限制最大尺寸
        max_dim = self.video_config.PREPROCESSING["resize_max_dimension"]
        h, w = frame.shape[:2]
        
        if max(h, w) > max_dim:
            if h > w:
                new_h, new_w = max_dim, int(w * max_dim / h)
            else:
                new_h, new_w = int(h * max_dim / w), max_dim
            
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
        
        return frame
    
    def extract_frames_fps_based(self, video_path: Path, output_dir: Path, 
                                 fps: int = 1, quality: int = 95) -> List[Path]:
        """基于FPS提取视频帧（每秒提取指定帧数）
        
        Args:
            video_path: 视频文件路径
            output_dir: 输出目录
            fps: 每秒提取的帧数
            quality: JPEG质量
            
        Returns:
            提取的帧文件路径列表
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")
        
        try:
            video_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / video_fps if video_fps > 0 else 0
            
            # 计算帧间隔（每隔多少帧提取一次）
            frame_interval = int(video_fps / fps) if fps > 0 else int(video_fps)
            
            extracted_frames = []
            frame_count = 0
            extracted_count = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 按间隔提取帧
                if frame_count % frame_interval == 0:
                    # 预处理帧
                    frame = self._preprocess_frame(frame)
                    
                    # 保存帧
                    timestamp = frame_count / video_fps
                    frame_filename = f"frame_{extracted_count:04d}_t{timestamp:.2f}s.jpg"
                    frame_path = output_dir / frame_filename
                    
                    cv2.imwrite(
                        str(frame_path), 
                        frame, 
                        [cv2.IMWRITE_JPEG_QUALITY, quality]
                    )
                    
                    extracted_frames.append(frame_path)
                    logger.info(f"提取帧 {extracted_count+1} at {timestamp:.2f}s: {frame_filename}")
                    extracted_count += 1
                
                frame_count += 1
            
            logger.info(f"FPS提取完成: 总共提取 {len(extracted_frames)} 帧")
            return extracted_frames
            
        finally:
            cap.release()
    
    def extract_frames(self, video_path: Path, output_dir: Path, 
                      n_frames: int = None, method: str = "uniform", 
                      fps: int = 1, quality: int = 95) -> List[Path]:
        """提取视频帧的统一接口
        
        Args:
            video_path: 视频文件路径
            output_dir: 输出目录
            n_frames: 要提取的帧数（uniform和keyframe方法使用）
            method: 提取方法 ('uniform', 'keyframe', 'fps_based')
            fps: 每秒提取帧数（fps_based方法使用）
            quality: JPEG质量
            
        Returns:
            提取的帧文件路径列表
        """
        logger.info(f"开始从视频提取帧: {video_path.name}, 方法: {method}")
        
        if method == "uniform":
            if n_frames is None:
                n_frames = self.config.N_FRAMES
            return self.extract_frames_uniform(video_path, output_dir, n_frames, quality)
        elif method == "keyframe":
            if n_frames is None:
                n_frames = self.config.N_FRAMES
            return self.extract_frames_keyframe(video_path, output_dir, n_frames, quality)
        elif method == "fps_based":
            return self.extract_frames_fps_based(video_path, output_dir, fps, quality)
        else:
            raise ValueError(f"不支持的提取方法: {method}")
    
    def get_video_info(self, video_path: Path) -> Dict[str, Any]:
        """获取视频详细信息
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            视频信息字典
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")
        
        try:
            info = {
                "filename": video_path.name,
                "file_size": video_path.stat().st_size,
                "fps": cap.get(cv2.CAP_PROP_FPS),
                "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fourcc": int(cap.get(cv2.CAP_PROP_FOURCC)),
            }
            
            info["duration"] = info["frame_count"] / info["fps"] if info["fps"] > 0 else 0
            info["aspect_ratio"] = info["width"] / info["height"] if info["height"] > 0 else 0
            
            # 转换fourcc为可读格式
            fourcc = info["fourcc"]
            info["codec"] = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
            
            return info
            
        finally:
            cap.release()

    def process_image(self, image_path: Path, output_dir: Path) -> Path:
        """处理单个图像文件，进行预处理并保存到输出目录"""
        try:
            logger.info(f"开始处理图像: {image_path}")
            
            # 验证图像文件
            if not self.validate_image_file_path(image_path):
                raise ValueError(f"图像文件验证失败: {image_path}")
            
            # 生成输出文件名
            output_filename = f"processed_{image_path.stem}.jpg"
            output_path = output_dir / output_filename
            
            # 预处理图像
            processed_path = self.preprocess_image(image_path, output_path)
            
            logger.info(f"图像处理完成: {processed_path}")
            return processed_path
            
        except Exception as e:
            logger.error(f"图像处理失败 {image_path}: {e}")
            raise
    
    def validate_image_file_path(self, image_path: Path) -> bool:
        """验证图像文件路径"""
        try:
            if not image_path.exists():
                logger.error(f"图像文件不存在: {image_path}")
                return False
            
            # 检查文件扩展名
            if image_path.suffix.lower() not in config.ALLOWED_IMAGE_FORMATS:
                logger.error(f"不支持的图像格式: {image_path.suffix}")
                return False
            
            # 检查文件大小
            file_size = image_path.stat().st_size
            if file_size > config.MAX_IMAGE_SIZE:
                logger.error(f"图像文件过大: {file_size} > {config.MAX_IMAGE_SIZE}")
                return False
            
            # 验证图像完整性
            with Image.open(image_path) as img:
                img.verify()
            
            return True
            
        except Exception as e:
            logger.error(f"图像文件验证失败 {image_path}: {e}")
            return False

# 全局处理器实例
video_processor = VideoProcessor()
image_processor = ImageProcessor()

if __name__ == "__main__":
    # 测试代码
    import sys
    if len(sys.argv) > 1:
        test_video = Path(sys.argv[1])
        if test_video.exists():
            processor = VideoProcessor()
            
            # 验证视频
            validation = processor.validate_video_file(test_video)
            print(f"验证结果: {validation}")
            
            if validation["valid"]:
                # 获取视频信息
                info = processor.get_video_info(test_video)
                print(f"视频信息: {info}")
                
                # 提取帧
                output_dir = Path("./test_frames")
                frames = processor.extract_frames(test_video, output_dir, 5)
                print(f"提取的帧: {frames}")
        else:
            print(f"视频文件不存在: {test_video}")
    else:
        print("用法: python video_processor.py <video_file>")

# 创建全局实例
video_processor = VideoProcessor()