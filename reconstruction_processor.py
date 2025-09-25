#!/usr/bin/env python3
"""
InstantSplat 三维重建处理模块

该模块负责集成 InstantSplat 的三维重建处理流程，包括：
1. 环境验证和输入准备
2. 几何初始化 (init_geo.py)
3. 模型训练 (train.py)
4. 渲染生成 (render.py)
5. 结果收集和清理

作者: InstantSplat API Team
日期: 2025-01-09
"""

import os
import sys
import json
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
import time
import glob

from config import ProcessingConfig
from task_manager import TaskStatus, ProgressCallback

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ReconstructionResult:
    """三维重建结果数据类"""
    success: bool
    output_dir: str
    metrics: Dict[str, Any]
    files: Dict[str, str]  # 文件类型 -> 文件路径
    processing_time: float
    error_message: Optional[str] = None

class ReconstructionProcessor:
    """三维重建处理器
    
    负责执行完整的 InstantSplat 三维重建流程
    """
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 验证环境
        self._verify_environment()
    
    def _verify_environment(self) -> None:
        """验证运行环境"""
        # 检查必要的脚本文件
        required_files = [
            'init_geo.py',
            'train.py', 
            'render.py'
        ]
        
        for file_name in required_files:
            file_path = Path(self.config.instantsplat_root) / file_name
            if not file_path.exists():
                raise FileNotFoundError(f"Required file not found: {file_path}")
        
        # 检查 CUDA 环境（如果配置了）
        if self.config.use_cuda:
            try:
                result = subprocess.run(
                    ['nvidia-smi'], 
                    capture_output=True, 
                    text=True, 
                    timeout=10,
                    encoding='utf-8',
                    errors='ignore'
                )
                if result.returncode != 0:
                    self.logger.warning("CUDA not available, falling back to CPU")
                    self.config.use_cuda = False
            except (subprocess.TimeoutExpired, FileNotFoundError, UnicodeDecodeError) as e:
                self.logger.warning(f"nvidia-smi check failed: {e}, assuming no CUDA")
                self.config.use_cuda = False
    
    def process_reconstruction(
        self, 
        scene_path: str,
        progress_callback: Optional[ProgressCallback] = None
    ) -> ReconstructionResult:
        """执行完整的三维重建流程
        
        Args:
            scene_path: 场景目录路径 (assets/api_uploads/task_id/)
            progress_callback: 进度回调函数
            
        Returns:
            ReconstructionResult: 重建结果
        """
        start_time = time.time()
        scene_path = Path(scene_path)
        
        try:
            # 1. 验证输入目录结构
            self._update_progress(progress_callback, 0.05, "验证输入目录结构...")
            images_dir = scene_path / "images"
            if not images_dir.exists():
                raise ValueError(f"Images directory not found: {images_dir}")
            
            # 计算图像数量和n_views参数
            image_files = sorted(list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png")))
            if len(image_files) < 3:
                raise ValueError(f"三维重建需要至少3张图像，当前只有{len(image_files)}张")
            
            n_views = len(image_files)  # 使用实际图像数量作为n_views
            
            # 2. 设置输出目录 (output_infer/api_uploads/task_id/N_views/)
            from config import api_config
            task_id = scene_path.name
            output_dir = api_config.OUTPUT_INFER_DIR / api_config.DATASET_NAME / task_id / f"{n_views}_views"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 3. 几何初始化
            self._update_progress(progress_callback, 0.15, "执行几何初始化...")
            init_result = self._run_geometry_initialization(str(scene_path), str(output_dir), n_views)
            if not init_result:
                raise RuntimeError("Geometry initialization failed")
            
            # 4. 模型训练
            self._update_progress(progress_callback, 0.30, "开始模型训练...")
            train_result = self._run_training(str(scene_path), str(output_dir), n_views, progress_callback)
            if not train_result:
                raise RuntimeError("Training failed")
            
            # 5. 训练完成后收集ply文件
            self._update_progress(progress_callback, 0.85, "收集训练结果...")
            result_files = self._collect_training_results(str(output_dir))
            metrics = self._extract_metrics(str(output_dir))
            
            # # 6. 异步启动渲染生成（不等待完成）
            # self._update_progress(progress_callback, 0.90, "启动渲染任务...")
            # self._start_async_rendering(str(scene_path), str(output_dir), n_views)
            
            processing_time = time.time() - start_time
            
            self._update_progress(progress_callback, 1.0, "重建完成")
            
            return ReconstructionResult(
                success=True,
                output_dir=str(output_dir),
                metrics=metrics,
                files=result_files,
                processing_time=processing_time
            )
            
        except Exception as e:
            self.logger.error(f"Reconstruction failed: {str(e)}")
            processing_time = time.time() - start_time
            
            return ReconstructionResult(
                success=False,
                output_dir=str(output_dir) if 'output_dir' in locals() else "",
                metrics={},
                files={},
                processing_time=processing_time,
                error_message=str(e)
            )
    
    def _run_geometry_initialization(self, source_path: str, model_path: str, n_views: int) -> bool:
        """运行几何初始化
        
        Args:
            source_path: 源路径 (assets/api_uploads/task_id/)
            model_path: 模型输出路径 (output_infer/api_uploads/task_id/N_views/)
            n_views: 视图数量
        """
        try:
            # 使用与 run_infer.sh 一致的参数
            cmd = [
                str(sys.executable), "-W", "ignore", "./init_geo.py",
                "-s", str(source_path),
                "-m", str(model_path),
                "--n_views", str(n_views),
                "--focal_avg",
                "--co_vis_dsp",
                "--conf_aware_ranking",
                "--infer_video"
            ]
            
            if self.config.use_cuda:
                env = os.environ.copy()
                env['CUDA_VISIBLE_DEVICES'] = '0'
                env['MKL_THREADING_LAYER'] = 'INTEL'
                env['MKL_SERVICE_FORCE_INTEL'] = '1'
                env['OMP_NUM_THREADS'] = '1'
            else:
                env = os.environ.copy()
                env['CUDA_VISIBLE_DEVICES'] = ''
                env['MKL_THREADING_LAYER'] = 'INTEL'
                env['MKL_SERVICE_FORCE_INTEL'] = '1'
                env['OMP_NUM_THREADS'] = '1'
            
            # 设置日志文件路径
            log_file = os.path.join(model_path, "01_init_geo.log")
            
            self.logger.info(f"Running geometry initialization: {' '.join(cmd)}")
            self.logger.info(f"Log will be saved to: {log_file}")
            
            # 重定向输出到日志文件
            with open(log_file, 'w') as log_f:
                result = subprocess.run(
                    cmd,
                    cwd=self.config.instantsplat_root,
                    env=env,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    timeout=self.config.init_timeout
                )
            
            if result.returncode != 0:
                # 读取日志文件内容用于错误报告
                try:
                    with open(log_file, 'r') as log_f:
                        log_content = log_f.read()
                    self.logger.error(f"Geometry initialization failed. Log content: {log_content[-1000:]}")
                except:
                    self.logger.error("Geometry initialization failed and could not read log file")
                return False
            
            self.logger.info("Geometry initialization completed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            self.logger.error("Geometry initialization timed out")
            return False
        except Exception as e:
            self.logger.error(f"Geometry initialization error: {str(e)}")
            return False
    
    def _run_training(
        self, 
        source_path: str, 
        model_path: str, 
        n_views: int,
        progress_callback: Optional[ProgressCallback] = None
    ) -> bool:
        """运行模型训练
        
        Args:
            source_path: 源路径 (assets/api_uploads/task_id/)
            model_path: 模型输出路径 (output_infer/api_uploads/task_id/N_views/)
            n_views: 视图数量
            progress_callback: 进度回调函数
        """
        try:
            # 使用与 run_infer.sh 一致的参数
            cmd = [
                str(sys.executable), "./train.py",
                "-s", str(source_path),
                "-m", str(model_path),
                "-r", "1",
                "--n_views", str(n_views),
                "--iterations", str(self.config.iterations),
                "--pp_optimizer",
                "--optim_pose"
            ]
            
            if self.config.use_cuda:
                env = os.environ.copy()
                env['CUDA_VISIBLE_DEVICES'] = '0'
                env['MKL_THREADING_LAYER'] = 'INTEL'
                env['MKL_SERVICE_FORCE_INTEL'] = '1'
                env['OMP_NUM_THREADS'] = '1'
            else:
                env = os.environ.copy()
                env['CUDA_VISIBLE_DEVICES'] = ''
                env['MKL_THREADING_LAYER'] = 'INTEL'
                env['MKL_SERVICE_FORCE_INTEL'] = '1'
                env['OMP_NUM_THREADS'] = '1'
            
            # 设置日志文件路径
            log_file = os.path.join(model_path, "02_train.log")
            
            self.logger.info(f"Running training: {' '.join(cmd)}")
            self.logger.info(f"Log will be saved to: {log_file}")
            
            # 启动训练进程，重定向输出到日志文件
            with open(log_file, 'w') as log_f:
                process = subprocess.Popen(
                    cmd,
                    cwd=self.config.instantsplat_root,
                    env=env,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    text=True
                )
            
            # 监控训练进度
            start_time = time.time()
            while process.poll() is None:
                elapsed = time.time() - start_time
                if elapsed > self.config.train_timeout:
                    process.terminate()
                    process.wait(timeout=10)
                    raise subprocess.TimeoutExpired(cmd, self.config.train_timeout)
                
                # 更新进度（训练阶段占 30% - 80%）
                if progress_callback:
                    progress = min(0.30 + (elapsed / self.config.train_timeout) * 0.50, 0.80)
                    estimated_remaining = max(0, self.config.train_timeout - elapsed)
                    progress_callback(
                        progress, 
                        f"模型训练中... (已用时: {elapsed:.0f}s)"
                    )
                
                time.sleep(5)  # 每5秒更新一次进度
            
            # 检查结果
            process.communicate()
            
            if process.returncode != 0:
                # 读取日志文件内容用于错误报告
                try:
                    with open(log_file, 'r') as log_f:
                        log_content = log_f.read()
                    self.logger.error(f"Training failed. Log content: {log_content[-1000:]}")
                except:
                    self.logger.error("Training failed and could not read log file")
                return False
            
            self.logger.info("Training completed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            self.logger.error("Training timed out")
            return False
        except Exception as e:
            self.logger.error(f"Training error: {str(e)}")
            return False
    
    def _run_rendering(self, source_path: str, model_path: str, n_views: int) -> bool:
        """运行渲染生成
        
        Args:
            source_path: 源路径 (assets/api_uploads/task_id/)
            model_path: 模型输出路径 (output_infer/api_uploads/task_id/N_views/)
            n_views: 视图数量
        """
        try:
            # 使用与 run_infer.sh 一致的参数
            cmd = [
                str(sys.executable), "./render.py",
                "-s", str(source_path),
                "-m", str(model_path),
                "-r", "1",
                "--n_views", str(n_views),
                "--iterations", str(self.config.iterations),
                "--infer_video"
            ]
            
            if self.config.use_cuda:
                env = os.environ.copy()
                env['CUDA_VISIBLE_DEVICES'] = '0'
                env['MKL_THREADING_LAYER'] = 'INTEL'
                env['MKL_SERVICE_FORCE_INTEL'] = '1'
                env['OMP_NUM_THREADS'] = '1'
            else:
                env = os.environ.copy()
                env['CUDA_VISIBLE_DEVICES'] = ''
                env['MKL_THREADING_LAYER'] = 'INTEL'
                env['MKL_SERVICE_FORCE_INTEL'] = '1'
                env['OMP_NUM_THREADS'] = '1'
            
            # 设置日志文件路径
            log_file = os.path.join(model_path, "03_render.log")
            
            self.logger.info(f"Running rendering: {' '.join(cmd)}")
            self.logger.info(f"Log will be saved to: {log_file}")
            
            # 重定向输出到日志文件
            with open(log_file, 'w') as log_f:
                result = subprocess.run(
                    cmd,
                    cwd=self.config.instantsplat_root,
                    env=env,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    timeout=self.config.render_timeout
                )
            
            if result.returncode != 0:
                # 读取日志文件内容用于错误报告
                try:
                    with open(log_file, 'r') as log_f:
                        log_content = log_f.read()
                    self.logger.error(f"Rendering failed. Log content: {log_content[-1000:]}")
                except:
                    self.logger.error("Rendering failed and could not read log file")
                return False
            
            self.logger.info("Rendering completed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            self.logger.error("Rendering timed out")
            return False
        except Exception as e:
            self.logger.error(f"Rendering error: {str(e)}")
            return False
    
    def _collect_training_results(self, output_dir: str) -> Dict[str, str]:
        """收集训练完成后的结果文件（主要是ply文件）"""
        result_files = {}
        
        # 查找训练生成的ply文件
        ply_patterns = [
            'point_cloud/iteration_*/point_cloud.ply',
            'point_cloud.ply',
            '*.ply'
        ]
        
        for pattern in ply_patterns:
            search_path = os.path.join(output_dir, pattern)
            matches = glob.glob(search_path)
            if matches:
                # 取最新的ply文件
                ply_file = max(matches, key=os.path.getmtime)
                result_files['point_cloud'] = ply_file
                self.logger.info(f"Found ply file: {ply_file}")
                break
        
        # 查找模型文件
        model_patterns = ['*.pth', 'chkpnt*.pth']
        for pattern in model_patterns:
            search_path = os.path.join(output_dir, pattern)
            matches = glob.glob(search_path)
            if matches:
                result_files['model'] = matches[0]
                break
        
        self.logger.info(f"Collected {len(result_files)} training result files")
        return result_files
    
    def _start_async_rendering(self, source_path: str, model_path: str, n_views: int) -> None:
        """异步启动渲染任务（不等待完成）"""
        try:
            import threading
            
            def render_task():
                self.logger.info("Starting async rendering task...")
                self._run_rendering(source_path, model_path, n_views)
                self.logger.info("Async rendering task completed")
            
            # 在后台线程中启动渲染
            render_thread = threading.Thread(target=render_task, daemon=True)
            render_thread.start()
            self.logger.info("Async rendering thread started")
            
        except Exception as e:
            self.logger.warning(f"Failed to start async rendering: {e}")
    
    def _collect_results(self, output_dir: str) -> Dict[str, str]:
        """收集处理结果文件"""
        result_files = {}
        
        # 查找各种结果文件
        file_patterns = {
            'point_cloud': ['point_cloud.ply', '*.ply'],
            'renders': ['renders/*.png', 'test/renders/*.png'],
            'metrics': ['results.json', 'metrics.json'],
            'model': ['*.pth', 'chkpnt*.pth'],
            'config': ['cfg_args', 'config.json']
        }
        
        for file_type, patterns in file_patterns.items():
            for pattern in patterns:
                search_path = os.path.join(output_dir, pattern)
                matches = glob.glob(search_path)
                if matches:
                    # 取第一个匹配的文件
                    result_files[file_type] = matches[0]
                    break
        
        self.logger.info(f"Collected {len(result_files)} result files")
        return result_files
    
    def _extract_metrics(self, output_dir: str) -> Dict[str, Any]:
        """提取处理指标"""
        metrics = {}
        
        # 查找指标文件
        metrics_files = [
            os.path.join(output_dir, 'results.json'),
            os.path.join(output_dir, 'metrics.json'),
            os.path.join(output_dir, 'test', 'results.json')
        ]
        
        for metrics_file in metrics_files:
            if os.path.exists(metrics_file):
                try:
                    with open(metrics_file, 'r') as f:
                        file_metrics = json.load(f)
                        metrics.update(file_metrics)
                    self.logger.info(f"Loaded metrics from {metrics_file}")
                    break
                except Exception as e:
                    self.logger.warning(f"Failed to load metrics from {metrics_file}: {e}")
        
        # 添加基本统计信息
        try:
            # 统计点云点数
            ply_files = glob.glob(os.path.join(output_dir, '*.ply'))
            if ply_files:
                # 这里可以添加点云分析代码
                metrics['point_cloud_files'] = len(ply_files)
            
            # 统计渲染图像数量
            render_dirs = [
                os.path.join(output_dir, 'renders'),
                os.path.join(output_dir, 'test', 'renders')
            ]
            
            total_renders = 0
            for render_dir in render_dirs:
                if os.path.exists(render_dir):
                    renders = glob.glob(os.path.join(render_dir, '*.png'))
                    total_renders += len(renders)
            
            metrics['total_renders'] = total_renders
            
        except Exception as e:
            self.logger.warning(f"Failed to extract additional metrics: {e}")
        
        return metrics
    

    
    def _update_progress(
        self, 
        callback: Optional[ProgressCallback], 
        progress: float, 
        message: str
    ) -> None:
        """更新进度"""
        if callback:
            callback(progress, message)
        self.logger.info(f"Progress: {progress:.1%} - {message}")

# 全局处理器实例
_processor_instance = None

def get_reconstruction_processor() -> ReconstructionProcessor:
    """获取全局重建处理器实例"""
    global _processor_instance
    if _processor_instance is None:
        from config import processing_config
        _processor_instance = ReconstructionProcessor(processing_config)
    return _processor_instance

# 创建全局实例
from config import processing_config
reconstruction_processor = ReconstructionProcessor(processing_config)

# 测试代码
if __name__ == "__main__":
    # 测试重建处理器
    processor = ReconstructionProcessor(processing_config)
    
    # 模拟处理
    def test_progress_callback(progress: float, message: str):
        print(f"Progress: {progress:.1%} - {message}")
    
    print("ReconstructionProcessor initialized successfully")