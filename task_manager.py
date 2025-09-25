#!/usr/bin/env python3
"""
任务管理模块 - 处理异步任务的状态跟踪、进度反馈和结果管理
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
import logging
from dataclasses import dataclass, asdict
import threading
from concurrent.futures import ThreadPoolExecutor

from config import api_config
from supabase_client import update_task_status_in_db, update_task_progress_in_db,update_task_result_in_db,update_task_field_in_db

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"          # 等待处理
    UPLOADING = "uploading"      # 上传中
    VALIDATING = "validating"    # 验证中
    EXTRACTING = "extracting"    # 提取帧中
    PROCESSING = "processing"    # 三维重建处理中
    RENDERING = "rendering"      # 渲染中
    COMPLETED = "completed"      # 完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 取消

class TaskType(Enum):
    """任务类型枚举"""
    VIDEO_RECONSTRUCTION = "video_reconstruction"
    IMAGE_RECONSTRUCTION = "image_reconstruction"

@dataclass
class TaskProgress:
    """任务进度信息"""
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    percentage: float = 0.0
    message: str = ""
    estimated_time_remaining: Optional[float] = None
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}

@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    task_type: TaskType
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: TaskProgress
    input_data: Dict[str, Any]
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    processing_time: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        # 转换枚举为字符串
        data['task_type'] = self.task_type.value
        data['status'] = self.status.value
        # 转换时间为ISO格式字符串
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data

class TaskManager:
    """任务管理器"""
    
    def __init__(self, max_concurrent_tasks: int = None):
        self.max_concurrent_tasks = max_concurrent_tasks or api_config.MAX_CONCURRENT_TASKS
        self.tasks: Dict[str, TaskInfo] = {}
        self.task_lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=self.max_concurrent_tasks)
        self.cleanup_interval = api_config.AUTO_CLEANUP_INTERVAL  # 清理间隔（秒）
        
        # 启动清理任务
        self._start_cleanup_task()
    
    def create_task(self, task_type: TaskType, input_data: Dict[str, Any]) -> str:
        """创建新任务
        
        Args:
            task_type: 任务类型
            input_data: 输入数据
            
        Returns:
            任务ID
        """
        # 如果input_data中包含task_id，使用它；否则生成新的
        task_id = input_data.get('task_id', str(uuid.uuid4()))
        now = datetime.now()
        
        task_info = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            progress=TaskProgress(),
            input_data=input_data.copy()
        )
        
        with self.task_lock:
            self.tasks[task_id] = task_info
        
        logger.info(f"创建任务: {task_id}, 类型: {task_type.value}")
        return task_id
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务信息，如果不存在返回None
        """
        with self.task_lock:
            return self.tasks.get(task_id)
    
    def update_task_status(self, task_id: str, status: TaskStatus, 
                          error_message: Optional[str] = None) -> bool:
        """更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            error_message: 错误信息（如果状态为FAILED）
            
        Returns:
            是否更新成功
        """
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            
            task.status = status
            task.updated_at = datetime.now()
            
            if error_message:
                task.error_message = error_message
            
            # 如果任务完成或失败，计算处理时间
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                task.processing_time = (task.updated_at - task.created_at).total_seconds()
            
            logger.info(f"任务 {task_id} 状态更新为: {status.value}")
            
            # 异步更新数据库状态
            self._update_database_status_async(task_id, status.value, error_message)
            
            return True
        
    def update_task_progress(self, task_id: str, current_step: str, 
                           completed_steps: int, total_steps: int,
                           message: str = "", details: Optional[Dict[str, Any]] = None) -> bool:
        """更新任务进度
        
        Args:
            task_id: 任务ID
            current_step: 当前步骤描述
            completed_steps: 已完成步骤数
            total_steps: 总步骤数
            message: 进度消息
            details: 额外详情
            
        Returns:
            是否更新成功
        """
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            
            # 计算进度百分比
            percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
            
            # 估算剩余时间
            estimated_time = None
            if completed_steps > 0 and percentage < 100:
                elapsed_time = (datetime.now() - task.created_at).total_seconds()
                estimated_time = (elapsed_time / completed_steps) * (total_steps - completed_steps)
            
            task.progress = TaskProgress(
                current_step=current_step,
                total_steps=total_steps,
                completed_steps=completed_steps,
                percentage=percentage,
                message=message,
                estimated_time_remaining=estimated_time,
                details=details or {}
            )
            task.updated_at = datetime.now()
            
            logger.debug(f"任务 {task_id} 进度更新: {current_step} ({percentage:.1f}%)")
            
            # 异步更新数据库进度
            self._update_database_progress_async(task_id, current_step, completed_steps, total_steps, details)
            
            return True
    
    def set_task_result(self, task_id: str, result_data: Dict[str, Any]):
        """设置任务结果"""
        with self.task_lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.result_data = result_data
                task.status = TaskStatus.COMPLETED
                task.updated_at = datetime.now()
                
                # 计算处理时间
                if task.created_at:
                    task.processing_time = (task.updated_at - task.created_at).total_seconds()
                
                logger.info(f"任务 {task_id} 结果已设置，状态更新为完成")
                
                # 异步更新数据库结果
                self._update_database_result_async(task_id, result_data, task.processing_time)
                
                return True
        return False
    
    def set_field(self, task_id: str, field_name: str, field_value: Any):
        """设置任务字段
        
        Args:
            task_id: 任务ID
            field_name: 字段名
            field_value: 字段值
        """
        with self.task_lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                setattr(task, field_name, field_value)
                task.updated_at = datetime.now()
                
                # 异步更新数据库字段
                self._update_database_field_async(task_id, field_name, field_value)
                
                return True
        return False
    
    def _update_database_field_async(self, task_id: str, field_name: str, field_value: Any):
        """异步更新数据库字段"""
        def update_field():
            try:
                asyncio.run(update_task_field_in_db(task_id, field_name, field_value))
            except Exception as e:
                logger.error(f"[数据库更新] 字段更新异常: task_id={task_id}, field={field_name}, error={str(e)}, type={type(e).__name__}")
        
        self.executor.submit(update_field)

    def cancel_task(self, task_id: str) -> bool:
        """取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否取消成功
        """
        with self.task_lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            
            # 只能取消未完成的任务
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                return False
            
            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now()
            
            logger.info(f"任务 {task_id} 已取消")
            
            # 异步更新数据库状态
            self._update_database_status_async(task_id, TaskStatus.CANCELLED.value)
            
            return True
    def _update_database_status_async(self, task_id: str, status: str, error_message: Optional[str] = None):
        """异步更新数据库中的任务状态"""
        
        #logger.info(f"[数据库更新] 准备异步更新状态: task_id={task_id}, status={status}, error={error_message}")
        
        def update_status():
            try:
                #logger.info(f"[数据库更新] 开始执行状态更新: task_id={task_id}")
                asyncio.run(update_task_status_in_db(task_id, status, error_message))
                #logger.info(f"[数据库更新] 状态更新完成: task_id={task_id}")
            except Exception as e:
                logger.error(f"[数据库更新] 状态更新异常: task_id={task_id}, error={str(e)}, type={type(e).__name__}")
        
        self.executor.submit(update_status)
    
    def _update_database_progress_async(self, task_id: str, current_step: str,
                                      completed_steps: int, total_steps: int,
                                      details: Optional[Dict[str, Any]] = None):
        """异步更新数据库进度"""
        
        #logger.info(f"[数据库更新] 准备异步更新进度: task_id={task_id}, step={current_step}, completed={completed_steps}/{total_steps}")
        
        def update_progress():
            try:
                #logger.info(f"[数据库更新] 开始执行进度更新: task_id={task_id}")
                asyncio.run(update_task_progress_in_db(
                    task_id=task_id,
                    current_step=current_step,
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                    details=details
                ))
                #logger.info(f"[数据库更新] 进度更新完成: task_id={task_id}")
            except Exception as e:
                logger.error(f"[数据库更新] 进度更新异常: task_id={task_id}, error={str(e)}, type={type(e).__name__}")
        
        self.executor.submit(update_progress)

    def _update_database_result_async(self, task_id: str, result_data: Dict[str, Any],
                                    processing_time: Optional[float] = None):
        """异步更新数据库结果数据"""
        
        #logger.info(f"[数据库更新] 准备异步更新结果: task_id={task_id}, processing_time={processing_time}")
        #logger.info(f"[数据库更新] 结果数据: {json.dumps(result_data, ensure_ascii=False, indent=2)}")
        
        def update_result():
            try:
                #logger.info(f"[数据库更新] 开始执行结果更新: task_id={task_id}")
                asyncio.run(update_task_result_in_db(
                    task_id=task_id,
                    result_data=result_data,
                    processing_time=processing_time
                ))
                #logger.info(f"[数据库更新] 结果更新完成: task_id={task_id}")
            except Exception as e:
                logger.error(f"[数据库更新] 结果更新异常: task_id={task_id}, error={str(e)}, type={type(e).__name__}")
        
        self.executor.submit(update_result)

    def list_tasks(self, status_filter: Optional[TaskStatus] = None, 
                  limit: Optional[int] = None) -> List[TaskInfo]:
        """列出任务
        
        Args:
            status_filter: 状态过滤器
            limit: 限制返回数量
            
        Returns:
            任务列表
        """
        with self.task_lock:
            tasks = list(self.tasks.values())
        
        # 按状态过滤
        if status_filter:
            tasks = [task for task in tasks if task.status == status_filter]
        
        # 按创建时间倒序排序
        tasks.sort(key=lambda x: x.created_at, reverse=True)
        
        # 限制数量
        if limit:
            tasks = tasks[:limit]
        
        return tasks
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """获取任务统计信息
        
        Returns:
            统计信息字典
        """
        with self.task_lock:
            tasks = list(self.tasks.values())
        
        stats = {
            "total_tasks": len(tasks),
            "status_counts": {},
            "type_counts": {},
            "average_processing_time": 0,
            "active_tasks": 0
        }
        
        # 统计各状态任务数量
        for status in TaskStatus:
            stats["status_counts"][status.value] = sum(1 for task in tasks if task.status == status)
        
        # 统计各类型任务数量
        for task_type in TaskType:
            stats["type_counts"][task_type.value] = sum(1 for task in tasks if task.task_type == task_type)
        
        # 计算平均处理时间
        completed_tasks = [task for task in tasks if task.processing_time is not None]
        if completed_tasks:
            stats["average_processing_time"] = sum(task.processing_time for task in completed_tasks) / len(completed_tasks)
        
        # 活跃任务数（非终态）
        active_statuses = [TaskStatus.PENDING, TaskStatus.UPLOADING, TaskStatus.VALIDATING, 
                          TaskStatus.EXTRACTING, TaskStatus.PROCESSING, TaskStatus.RENDERING]
        stats["active_tasks"] = sum(1 for task in tasks if task.status in active_statuses)
        
        return stats
    
    def cleanup_old_tasks(self) -> int:
        """清理旧任务
        
        Returns:
            清理的任务数量
        """
        # 使用配置中的任务保留时间
        retention_hours = api_config.TASK_RETENTION_HOURS
        cutoff_time = datetime.now() - timedelta(hours=retention_hours)
        cleaned_count = 0
        
        with self.task_lock:
            # 找出需要清理的任务（已完成且超过保留时间）
            tasks_to_remove = []
            for task_id, task in self.tasks.items():
                if (task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED] and 
                    task.updated_at < cutoff_time):
                    tasks_to_remove.append(task_id)
            
            # 删除任务
            for task_id in tasks_to_remove:
                del self.tasks[task_id]
                cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"清理了 {cleaned_count} 个旧任务（保留时间: {retention_hours}小时）")
        
        return cleaned_count
    
    def _start_cleanup_task(self):
        """启动定期清理任务"""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(self.cleanup_interval)
                    self.cleanup_old_tasks()
                except Exception as e:
                    logger.error(f"清理任务出错: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        logger.info(f"启动任务清理线程，清理间隔: {self.cleanup_interval}秒")
    
    def submit_async_task(self, task_id: str, task_func: Callable, *args, **kwargs):
        """提交异步任务到线程池
        
        Args:
            task_id: 任务ID
            task_func: 任务函数
            *args: 位置参数
            **kwargs: 关键字参数
        """
        def wrapped_task():
            try:
                logger.info(f"开始执行任务: {task_id}")
                result = task_func(task_id, *args, **kwargs)
                
                # 如果任务函数返回结果，设置到任务中
                if result is not None:
                    self.set_task_result(task_id, result)
                
                # 如果任务还没有设置为完成状态，自动设置
                task = self.get_task(task_id)
                if task and task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    self.update_task_status(task_id, TaskStatus.COMPLETED)
                
                logger.info(f"任务执行完成: {task_id}")
                
            except Exception as e:
                logger.error(f"任务执行失败: {task_id}, 错误: {e}")
                self.update_task_status(task_id, TaskStatus.FAILED, str(e))
        
        # 提交到线程池
        future = self.executor.submit(wrapped_task)
        return future
    
    def shutdown(self):
        """关闭任务管理器"""
        logger.info("关闭任务管理器...")
        self.executor.shutdown(wait=True)
        logger.info("任务管理器已关闭")

# 全局任务管理器实例
task_manager = TaskManager()

# 进度回调函数类型
ProgressCallback = Callable[[str, str, int, int, Optional[Dict[str, Any]]], None]

def create_progress_callback(task_id: str) -> ProgressCallback:
    """创建进度回调函数
    
    Args:
        task_id: 任务ID
        
    Returns:
        进度回调函数
    """
    def progress_callback(current_step: str, completed_steps: int, 
                         total_steps: int, details: Optional[Dict[str, Any]] = None):
        task_manager.update_task_progress(task_id, current_step, completed_steps, total_steps, details)
    
    return progress_callback

if __name__ == "__main__":
    # 测试代码
    import time
    
    def test_task(task_id: str, duration: int = 5):
        """测试任务函数"""
        progress_callback = create_progress_callback(task_id)
        
        for i in range(duration):
            progress_callback(f"步骤 {i+1}", i, duration, {"detail": f"处理第{i+1}项"})
            time.sleep(1)
        
        return {"result": "测试完成", "processed_items": duration}
    
    # 创建任务管理器
    tm = TaskManager()
    
    # 创建测试任务
    task_id = tm.create_task(TaskType.VIDEO_RECONSTRUCTION, {"test_input": "test_value"})
    print(f"创建任务: {task_id}")
    
    # 提交异步任务
    future = tm.submit_async_task(task_id, test_task, 3)
    
    # 监控任务进度
    while True:
        task = tm.get_task(task_id)
        if task:
            print(f"任务状态: {task.status.value}, 进度: {task.progress.percentage:.1f}%")
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                print(f"任务结果: {task.result_data}")
                break
        time.sleep(0.5)
    
    # 获取统计信息
    stats = tm.get_task_statistics()
    print(f"统计信息: {stats}")
    
    # 关闭任务管理器
    tm.shutdown()