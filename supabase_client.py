#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supabase客户端配置和数据库操作模块
用于管理InstantSplat项目的任务状态数据库更新
使用官方 supabase-py 客户端库
"""

import os
import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from pathlib import Path
from enum import Enum

# 导入官方 Supabase 客户端
from supabase import create_client, Client
from postgrest.exceptions import APIError

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 加载环境变量
def load_env_file(env_file_path: str = '.env.supabase'):
    """从.env文件加载环境变量"""
    env_path = Path(env_file_path)
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # 移除引号
                    value = value.strip('"\'')
                    os.environ[key] = value
        logger.info(f"已加载环境变量文件: {env_file_path}")
    else:
        logger.warning(f"环境变量文件不存在: {env_file_path}")

# 自动加载环境变量
load_env_file()

class TaskStatusMapping:
    """任务状态映射类 - 将TaskStatus映射到数据库状态"""
    
    # TaskStatus到数据库status字段的映射
    STATUS_MAPPING = {
        "pending": "pending",
        "uploading": "processing", 
        "validating": "processing",
        "extracting": "processing",
        "processing": "processing",
        "rendering": "processing",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled"
    }
    
    # 进度步骤到描述的映射
    STEP_DESCRIPTIONS = {
        "pending": "等待处理",
        "uploading": "上传文件中",
        "validating": "验证文件中", 
        "extracting": "提取帧中",
        "processing": "三维重建处理中",
        "rendering": "渲染中",
        "completed": "处理完成",
        "failed": "处理失败",
        "cancelled": "已取消"
    }
    
    @classmethod
    def get_db_status(cls, task_status: str) -> str:
        """获取数据库状态"""
        return cls.STATUS_MAPPING.get(task_status.lower(), "processing")
    
    @classmethod
    def get_step_description(cls, task_status: str) -> str:
        """获取步骤描述"""
        return cls.STEP_DESCRIPTIONS.get(task_status.lower(), task_status)

class SupabaseClient:
    """Supabase数据库客户端 - 使用官方客户端库"""
    
    def _load_env_variables(self):
        """加载环境变量"""
        self.supabase_url = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
        self.supabase_anon_key = os.getenv('NEXT_PUBLIC_SUPABASE_ANON_KEY')
        self.service_role_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if not self.supabase_url or not self.supabase_anon_key:
            raise ValueError("缺少必要的Supabase环境变量: NEXT_PUBLIC_SUPABASE_URL 和 NEXT_PUBLIC_SUPABASE_ANON_KEY")
    
    def _verify_connection(self) -> bool:
        """验证数据库连接"""
        try:
            # 使用管理员客户端测试连接
            response = self.admin_client.table('projects').select('count').limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"数据库连接验证失败: {e}")
            return False
    
    def __init__(self):
        """初始化Supabase客户端"""
        # 加载环境变量
        self._load_env_variables()
        
        # 初始化Supabase客户端（用户客户端）
        self.client = create_client(self.supabase_url, self.supabase_anon_key)
        
        # 初始化管理员客户端（如果有service_role key）
        service_role_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        if service_role_key:
            self.admin_client = create_client(self.supabase_url, service_role_key)
            logger.info("管理员客户端初始化成功")
        else:
            self.admin_client = self.client
            logger.info("未找到service_role_key，使用anon_key作为管理员客户端")
        
        logger.info(f"Supabase客户端初始化完成: {self.supabase_url}")
        
        # 验证连接
        if self._verify_connection():
            logger.info("Supabase客户端初始化成功")
        else:
            logger.error("Supabase客户端初始化失败")
    
    def _get_client(self, use_admin: bool = False) -> Client:
        """获取适当的客户端实例"""
        return self.admin_client if use_admin else self.client
    
    async def update_project_status(self, task_id: str, status: str, 
                                  processing_progress: Optional[float] = None,
                                  error_message: Optional[str] = None,
                                  additional_data: Optional[Dict[str, Any]] = None) -> bool:
        """更新项目状态
        
        Args:
            task_id: 任务ID
            status: 任务状态
            processing_progress: 处理进度 (0-100)
            error_message: 错误信息
            additional_data: 额外数据
            
        Returns:
            bool: 更新是否成功
        """
        try:
            # 构建更新数据
            update_data = {
                "status": TaskStatusMapping.get_db_status(status),
                "updated_at": datetime.now().isoformat()
            }
            
            # 添加可选字段
            if processing_progress is not None:
                update_data["processing_progress"] = min(100, max(0, processing_progress))
            
            if error_message:
                update_data["error_message"] = error_message
            
            # 添加额外数据到metadata字段
            if additional_data:
                update_data["metadata"] = additional_data
            
            #logger.info(f"[数据库更新] 准备更新项目状态: task_id={task_id}, status={status}, progress={processing_progress}")
            #logger.info(f"[数据库更新] 更新数据: {json.dumps(update_data, ensure_ascii=False, indent=2)}")
            
            # 使用官方客户端进行更新
            client = self._get_client(use_admin=True)
            response = client.table('projects').update(update_data).eq('task_id', task_id).execute()
            
            #logger.info(f"[数据库更新] 数据库响应: {json.dumps(response.data, ensure_ascii=False, indent=2) if response.data else 'None'}")
            
            if response.data:
                #logger.info(f"[数据库更新] 项目状态更新成功: task_id={task_id}, 影响行数={len(response.data)}")
                return True
            else:
                logger.warning(f"[数据库更新] 项目状态更新未找到匹配记录: task_id={task_id}")
                return False
                        
        except APIError as e:
            logger.error(f"[数据库更新] 项目状态更新API错误: task_id={task_id}, error={str(e)}")
            return False
        except Exception as e:
            logger.error(f"[数据库更新] 项目状态更新异常: task_id={task_id}, error={str(e)}, type={type(e).__name__}")
            return False
    
    async def update_project_progress(self, task_id: str, current_step: str,
                                    completed_steps: int, total_steps: int,
                                    details: Optional[Dict[str, Any]] = None) -> bool:
        """更新项目进度
        
        Args:
            task_id: 任务ID
            current_step: 当前步骤
            completed_steps: 已完成步骤数
            total_steps: 总步骤数
            details: 进度详情
            
        Returns:
            bool: 更新是否成功
        """
        try:
            # 计算进度百分比
            progress_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
            
            # 构建进度数据
            progress_data = {
                "current_step": TaskStatusMapping.get_step_description(current_step),
                "completed_steps": completed_steps,
                "total_steps": total_steps,
                "percentage": round(progress_percentage, 2),
                "details": details or {}
            }
            
            # 构建更新数据
            update_data = {
                "processing_progress": int(round(progress_percentage)),
                "metadata": progress_data,
                "updated_at": datetime.now().isoformat()
            }
            
            #logger.info(f"[数据库更新] 准备更新项目进度: task_id={task_id}, step={current_step}, progress={progress_percentage:.1f}%")
            #logger.info(f"[数据库更新] 更新数据: {json.dumps(update_data, ensure_ascii=False, indent=2)}")
            
            # 使用官方客户端进行更新
            client = self._get_client(use_admin=True)
            response = client.table('projects').update(update_data).eq('task_id', task_id).execute()
            
            #logger.info(f"[数据库更新] 数据库响应: {json.dumps(response.data, ensure_ascii=False, indent=2) if response.data else 'None'}")
            
            if response.data:
                #logger.info(f"[数据库更新] 项目进度更新成功: task_id={task_id}, 影响行数={len(response.data)}")
                return True
            else:
                logger.warning(f"[数据库更新] 项目进度更新未找到匹配记录: task_id={task_id}")
                return False
                        
        except APIError as e:
            logger.error(f"[数据库更新] 项目进度更新API错误: task_id={task_id}, error={str(e)}")
            return False
        except Exception as e:
            logger.error(f"[数据库更新] 项目进度更新异常: task_id={task_id}, error={str(e)}, type={type(e).__name__}")
            return False

    async def update_project_result(self, task_id: str, result_data: Dict[str, Any],
                                  processing_time: Optional[float] = None) -> bool:
        """更新项目结果数据
        
        Args:
            task_id: 任务ID
            result_data: 结果数据，包含output_path, public_url, files, metrics等
            processing_time: 处理时间（秒）
            
        Returns:
            bool: 更新是否成功
        """
        try:
            # 构建更新数据
            update_data = {
                "status": "completed",
                "processing_progress": 100,
                "processing_completed_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # 添加结果相关字段
            if result_data.get('public_url'):
                update_data["result_model_url"] = result_data['public_url']
            if result_data.get('file_size'):
                update_data["file_size"] = result_data['file_size']

            if result_data.get('files'):
                update_data["result_files"] = result_data['files']
            
            # 添加处理时间到metadata
            metadata = {}
            if processing_time is not None:
                metadata["processing_time"] = processing_time
            
            # 添加其他结果数据到metadata
            if result_data.get('metrics'):
                metadata["metrics"] = result_data['metrics']
            
            if result_data.get('output_path'):
                metadata["output_path"] = result_data['output_path']
            
            if metadata:
                update_data["metadata"] = metadata
            
            #logger.info(f"[数据库更新] 准备更新项目结果: task_id={task_id}, processing_time={processing_time}")
            #logger.info(f"[数据库更新] 更新数据: {json.dumps(update_data, ensure_ascii=False, indent=2)}")
            
            # 使用官方客户端进行更新
            client = self._get_client(use_admin=True)
            response = client.table('projects').update(update_data).eq('task_id', task_id).execute()
            
            #logger.info(f"[数据库更新] 数据库响应: {json.dumps(response.data, ensure_ascii=False, indent=2) if response.data else 'None'}")
            
            if response.data:
                #logger.info(f"[数据库更新] 项目结果更新成功: task_id={task_id}, 影响行数={len(response.data)}")
                return True
            else:
                logger.warning(f"[数据库更新] 项目结果更新未找到匹配记录: task_id={task_id}")
                return False
                        
        except APIError as e:
            logger.error(f"[数据库更新] 项目结果更新API错误: task_id={task_id}, error={str(e)}")
            return False
        except Exception as e:
            logger.error(f"[数据库更新] 项目结果更新异常: task_id={task_id}, error={str(e)}, type={type(e).__name__}")
            return False

    async def update_task_field_in_db(self, task_id: str, field_name: str, field_value: Any):
        """更新项目字段
        
        Args:
            task_id: 任务ID
            field_name: 字段名
            field_value: 字段值
            
        Returns:
            bool: 更新是否成功
        """
        try:
            client = self._get_client(use_admin=True)
            response = client.table('projects').update({field_name: field_value}).eq('task_id', task_id).execute()
            
            if response.data:
                logger.info(f"[数据库更新] 字段更新成功: task_id={task_id}, field={field_name}, value={field_value}")
                return True
            else:
                logger.warning(f"[数据库更新] 字段更新未找到匹配记录: task_id={task_id}, field={field_name}")
                return False
                        
        except APIError as e:
            logger.error(f"[数据库更新] 字段更新API错误: task_id={task_id}, field={field_name}, error={str(e)}")
            return False
        except Exception as e:
            logger.error(f"[数据库更新] 字段更新异常: task_id={task_id}, field={field_name}, error={str(e)}, type={type(e).__name__}")
            return False


    async def get_project_by_task_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """根据task_id获取项目信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            项目信息字典或None
        """
        try:
            client = self._get_client()
            response = client.table('projects').select('*').eq('task_id', task_id).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            else:
                logger.warning(f"未找到task_id对应的项目: {task_id}")
                return None
                        
        except APIError as e:
            logger.error(f"获取项目信息API错误: task_id={task_id}, error={str(e)}")
            return None
        except Exception as e:
            logger.error(f"获取项目信息异常: task_id={task_id}, error={str(e)}")
            return None
    
    async def create_project(self, project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建新项目
        
        Args:
            project_data: 项目数据
            
        Returns:
            创建的项目信息或None
        """
        try:
            # 添加创建时间
            project_data['created_at'] = datetime.now().isoformat()
            project_data['updated_at'] = datetime.now().isoformat()
            
            # 确保 processing_progress 是整数类型
            if 'processing_progress' in project_data:
                project_data['processing_progress'] = int(project_data['processing_progress'])
            
            client = self._get_client(use_admin=True)
            response = client.table('projects').insert(project_data).execute()
            
            if response.data and len(response.data) > 0:
                logger.info(f"项目创建成功: task_id={project_data.get('task_id')}")
                return response.data[0]
            else:
                logger.error(f"项目创建失败: {project_data}")
                return None
                
        except APIError as e:
            logger.error(f"项目创建API错误: error={str(e)}")
            return None
        except Exception as e:
            logger.error(f"项目创建异常: error={str(e)}")
            return None
    
    async def delete_project(self, task_id: str) -> bool:
        """删除项目
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 删除是否成功
        """
        try:
            client = self._get_client(use_admin=True)
            response = client.table('projects').delete().eq('task_id', task_id).execute()
            
            if response.data:
                logger.info(f"项目删除成功: task_id={task_id}")
                return True
            else:
                logger.warning(f"项目删除未找到匹配记录: task_id={task_id}")
                return False
                
        except APIError as e:
            logger.error(f"项目删除API错误: task_id={task_id}, error={str(e)}")
            return False
        except Exception as e:
            logger.error(f"项目删除异常: task_id={task_id}, error={str(e)}")
            return False
    
    async def list_projects(self, user_id: Optional[str] = None, 
                          status: Optional[str] = None,
                          limit: int = 100) -> List[Dict[str, Any]]:
        """获取项目列表
        
        Args:
            user_id: 用户ID过滤
            status: 状态过滤
            limit: 返回数量限制
            
        Returns:
            项目列表
        """
        try:
            client = self._get_client()
            query = client.table('projects').select('*')
            
            # 添加过滤条件
            if user_id:
                query = query.eq('user_id', user_id)
            if status:
                query = query.eq('status', status)
            
            # 添加排序和限制
            query = query.order('created_at', desc=True).limit(limit)
            
            response = query.execute()
            
            return response.data or []
                
        except APIError as e:
            logger.error(f"获取项目列表API错误: error={str(e)}")
            return []
        except Exception as e:
            logger.error(f"获取项目列表异常: error={str(e)}")
            return []

# 全局Supabase客户端实例
_supabase_client = None

def get_supabase_client() -> SupabaseClient:
    """获取Supabase客户端实例(单例模式)"""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    return _supabase_client

# 便捷函数
async def update_task_status_in_db(task_id: str, status: str, 
                                 processing_progress: Optional[float] = None,
                                 error_message: Optional[str] = None) -> bool:
    """更新任务状态到数据库的便捷函数"""
    client = get_supabase_client()
    return await client.update_project_status(
        task_id=task_id,
        status=status,
        processing_progress=processing_progress,
        error_message=error_message
    )

async def update_task_progress_in_db(task_id: str, current_step: str,
                                   completed_steps: int, total_steps: int,
                                   details: Optional[Dict[str, Any]] = None) -> bool:
    """更新任务进度到数据库的便捷函数"""
    client = get_supabase_client()
    return await client.update_project_progress(
        task_id=task_id,
        current_step=current_step,
        completed_steps=completed_steps,
        total_steps=total_steps,
        details=details
    )

async def update_task_result_in_db(task_id: str, result_data: Dict[str, Any],
                                 processing_time: Optional[float] = None
                                 ) -> bool:
    """更新任务结果到数据库的便捷函数"""
    client = get_supabase_client()
    return await client.update_project_result(
        task_id=task_id,
        result_data=result_data,
        processing_time=processing_time
    )
async def update_task_field_in_db(task_id: str, field_name: str, field_value: Any) -> bool:
    """更新任务字段到数据库的便捷函数"""
    client = get_supabase_client()
    return await client.update_task_field_in_db(
        task_id=task_id,
        field_name=field_name,
        field_value=field_value
    )

async def get_project_info(task_id: str) -> Optional[Dict[str, Any]]:
    """获取项目信息的便捷函数"""
    client = get_supabase_client()
    return await client.get_project_by_task_id(task_id)

async def create_new_project(project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """创建新项目的便捷函数"""
    client = get_supabase_client()
    return await client.create_project(project_data)

# 测试函数
async def test_supabase_connection():
    """测试Supabase连接"""
    try:
        client = get_supabase_client()
        logger.info("Supabase客户端初始化成功")
        
        # 测试获取项目列表
        projects = await client.list_projects(limit=20)
        logger.info(f"连接测试完成，获取到 {len(projects)} 个项目")
        projects2 = await get_project_info("548d8a4f-1a81-4c80-aa5b-f0ee8d020e32")
        logger.info(f"获取项目详情: {projects2}")

        return True
    except Exception as e:
        logger.error(f"Supabase连接测试失败: {str(e)}")
        return False

async def debug_supabase_permissions():
    """调试Supabase权限和数据访问问题"""
    logger.info("=== 开始调试Supabase权限问题 ===")
    
    try:
        client = get_supabase_client()
        
        # 1. 测试直接SQL查询（通过客户端）
        logger.info("1. 测试直接查询项目数量...")
        try:
            response = client.client.rpc('get_project_count').execute()
            logger.info(f"RPC查询结果: {response}")
        except Exception as e:
            logger.warning(f"RPC查询失败: {e}")
        
        # 2. 测试基本的table查询
        logger.info("2. 测试基本table查询...")
        try:
            response = client.client.table('projects').select('*').limit(1).execute()
            logger.info(f"基本查询响应: {response}")
            logger.info(f"基本查询数据: {response.data}")
            logger.info(f"基本查询数量: {len(response.data) if response.data else 0}")
        except Exception as e:
            logger.error(f"基本查询失败: {e}")
        
        # 3. 测试不同的查询条件
        logger.info("3. 测试不同查询条件...")
        try:
            # 查询所有字段
            response1 = client.client.table('projects').select('*').execute()
            logger.info(f"查询所有字段: 数据量={len(response1.data) if response1.data else 0}")
            
            # 只查询部分字段
            response2 = client.client.table('projects').select('task_id,name,status').execute()
            logger.info(f"查询部分字段: 数据量={len(response2.data) if response2.data else 0}")
            
            # 查询特定记录
            response3 = client.client.table('projects').select('*').eq('task_id', '548d8a4f-1a81-4c80-aa5b-f0ee8d020e32').execute()
            logger.info(f"查询特定记录: 数据量={len(response3.data) if response3.data else 0}")
            if response3.data:
                logger.info(f"特定记录内容: {response3.data[0]}")
                
        except Exception as e:
            logger.error(f"条件查询失败: {e}")
        
        # 4. 测试权限相关
        logger.info("4. 测试权限配置...")
        logger.info(f"当前使用的URL: {client.client.supabase_url}")
        logger.info(f"当前使用的Key类型: {'service_role' if client.client.supabase_key.startswith('eyJ') else 'anon'}")
        
        # 5. 测试原始HTTP请求
        logger.info("5. 测试原始HTTP请求...")
        import httpx
        headers = {
            'apikey': client.client.supabase_key,
            'Authorization': f'Bearer {client.client.supabase_key}',
            'Content-Type': 'application/json'
        }
        
        async with httpx.AsyncClient() as http_client:
            url = f"{client.client.supabase_url}/rest/v1/projects"
            response = await http_client.get(url, headers=headers)
            logger.info(f"原始HTTP请求状态: {response.status_code}")
            logger.info(f"原始HTTP请求响应: {response.text[:500]}...")
            
        return True
        
    except Exception as e:
        logger.error(f"调试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

async def test_database_operations():
    """测试数据库操作"""
    logger.info("=== 测试数据库操作 ===")
    
    try:
        client = get_supabase_client()
        
        # 使用现有的用户ID（从profiles表中获取）
        existing_user_id = "9c507e92-0f53-4b91-8135-e49e2b76d56e"  # 从查询结果中获取的有效用户ID
        
        # 1. 测试创建项目
        logger.info("1. 测试创建项目...")
        import uuid
        test_task_id = str(uuid.uuid4())
        
        project_data = {
            "task_id": test_task_id,
            "user_id": existing_user_id,  # 使用现有的用户ID
            "name": "调试测试项目",
            "status": "pending",
            "processing_progress": 0
        }
        
        created_project = await client.create_project(project_data)
        if created_project:
            logger.info(f"✅ 项目创建成功: {created_project.get('task_id')}")
            
            # 2. 测试查询刚创建的项目
            logger.info("2. 测试查询刚创建的项目...")
            found_project = await client.get_project_by_task_id(test_task_id)
            if found_project:
                logger.info(f"✅ 项目查询成功: {found_project.get('name')}")
            else:
                logger.error("❌ 无法查询到刚创建的项目")
            
            # 3. 测试更新项目
            logger.info("3. 测试更新项目...")
            update_success = await client.update_project_status(test_task_id, "processing")
            if update_success:
                logger.info("✅ 项目更新成功")
            else:
                logger.error("❌ 项目更新失败")
            
            # 4. 清理测试数据
            logger.info("4. 清理测试数据...")
            delete_success = await client.delete_project(test_task_id)
            if delete_success:
                logger.info("✅ 测试数据清理成功")
            else:
                logger.warning("⚠️ 测试数据清理失败")
                
        else:
            logger.error("❌ 项目创建失败")
            
        return True
        
    except Exception as e:
        logger.error(f"数据库操作测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

async def test_rls_bypass():
    """测试绕过RLS的查询方法"""
    logger.info("=== 测试RLS绕过方法 ===")
    
    try:
        client = get_supabase_client()
        
        # 方法1: 使用service_role key（如果有的话）
        logger.info("1. 测试使用service_role查询...")
        
        # 检查当前使用的key类型
        current_key = client.supabase_anon_key
        if current_key.startswith('eyJ'):
            logger.info("当前使用anon key，尝试查询...")
        else:
            logger.info("当前使用service_role key，尝试查询...")
        
        # 直接查询所有项目
        try:
            response = client.admin_client.table("projects").select("*").limit(5).execute()
            logger.info(f"✅ 查询成功，获取到 {len(response.data)} 个项目")
            if response.data:
                logger.info(f"项目示例: {response.data[0]}")
        except Exception as e:
            logger.error(f"查询失败: {e}")
        
        # 方法2: 测试特定用户的项目
        logger.info("2. 测试查询特定用户的项目...")
        existing_user_id = "9c507e92-0f53-4b91-8135-e49e2b76d56e"
        try:
            response = client.admin_client.table("projects").select("*").eq("user_id", existing_user_id).execute()
            logger.info(f"✅ 用户项目查询成功，获取到 {len(response.data)} 个项目")
        except Exception as e:
            logger.error(f"用户项目查询失败: {e}")
            
    except Exception as e:
        logger.error(f"RLS绕过测试失败: {e}")

if __name__ == "__main__":
    # 运行连接测试
    import asyncio
    
    async def main():
        logger.info("开始运行Supabase客户端测试...")
        
        # 1. 基本连接测试
        logger.info("\n=== 1. 基本连接测试 ===")
        await test_supabase_connection()
        
        # 2. 权限调试
        logger.info("\n=== 2. 权限调试 ===")
        await debug_supabase_permissions()
        
        # 3. RLS绕过测试
        logger.info("\n=== 3. RLS绕过测试 ===")
        await test_rls_bypass()
        
        # 4. 数据库操作测试
        logger.info("\n=== 4. 数据库操作测试 ===")
        await test_database_operations()
        
        logger.info("\n=== 测试完成 ===")
    
    asyncio.run(main())