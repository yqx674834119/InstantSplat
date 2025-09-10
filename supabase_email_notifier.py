#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supabase邮件通知器
用于在SceneGEN训练完成后发送邮件通知
"""

import os
import json
import asyncio
import aiohttp
from typing import Dict, Any, Optional
from datetime import datetime
import logging
from pathlib import Path

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

class SupabaseEmailNotifier:
    """Supabase邮件通知器类"""
    
    def __init__(self):
        """初始化邮件通知器"""
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_anon_key = os.getenv('SUPABASE_ANON_KEY')
        self.function_name = 'send-notification-email'
        
        if not self.supabase_url or not self.supabase_anon_key:
            raise ValueError("缺少必要的Supabase环境变量: SUPABASE_URL 和 SUPABASE_ANON_KEY")
        
        # 构建Edge Function URL
        self.function_url = f"{self.supabase_url}/functions/v1/{self.function_name}"
        
        logger.info(f"Supabase邮件通知器初始化完成: {self.function_url}")
    
    async def send_notification(self, 
                              email: str, 
                              subject: str, 
                              message: str, 
                              task_id: str = None,
                              status: str = "completed",
                              additional_data: Dict[str, Any] = None) -> bool:
        """发送邮件通知
        
        Args:
            email: 收件人邮箱
            subject: 邮件主题
            message: 邮件内容
            task_id: 任务ID
            status: 任务状态 (completed, failed, processing)
            additional_data: 额外数据
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 构建请求数据
            payload = {
                "email": email,
                "subject": subject,
                "message": message,
                "task_id": task_id or "unknown",
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "additional_data": additional_data or {}
            }
            
            # 设置请求头
            headers = {
                "Authorization": f"Bearer {self.supabase_anon_key}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"发送邮件通知到: {email}, 主题: {subject}")
            
            # 发送异步HTTP请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.function_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"邮件发送成功: {result}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"邮件发送失败 (状态码: {response.status}): {error_text}")
                        return False
                        
        except asyncio.TimeoutError:
            logger.error("邮件发送超时")
            return False
        except Exception as e:
            logger.error(f"邮件发送异常: {str(e)}")
            return False
    
    async def send_training_completion_notification(self,
                                                  email: str,
                                                  task_id: str,
                                                  success: bool = True,
                                                  processing_time: float = None,
                                                  public_url: str = None,
                                                  error_message: str = None) -> bool:
        """发送训练完成通知
        
        Args:
            email: 收件人邮箱
            task_id: 任务ID
            success: 是否成功
            processing_time: 处理时间(秒)
            public_url: 公网下载链接
            error_message: 错误信息(如果失败)
            
        Returns:
            bool: 发送是否成功
        """
        if success:
            subject = f"SceneGEN训练完成 - 任务 {task_id}"
            message = f"""
亲爱的用户，

您的SceneGEN 3D重建任务已成功完成！

任务详情:
- 任务ID: {task_id}
- 完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 处理时长: {processing_time:.2f}秒 

感谢使用SceneGEN服务！

此邮件由系统自动发送，请勿回复。
            """.strip()
            
            additional_data = {
                "processing_time": processing_time,
                "public_url": public_url,
                "result_type": "ply_file"
            }
            
            return await self.send_notification(
                email=email,
                subject=subject,
                message=message,
                task_id=task_id,
                status="completed",
                additional_data=additional_data
            )
        else:
            subject = f"SceneGEN训练失败 - 任务 {task_id}"
            message = f"""
亲爱的用户，

很抱歉，您的SceneGEN 3D重建任务执行失败。

任务详情:
- 任务ID: {task_id}
- 失败时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 错误信息: {error_message or '未知错误'}

请检查输入数据或联系技术支持。

此邮件由系统自动发送，请勿回复。
            """.strip()
            
            additional_data = {
                "error_message": error_message,
                "failed_at": datetime.now().isoformat()
            }
            
            return await self.send_notification(
                email=email,
                subject=subject,
                message=message,
                task_id=task_id,
                status="failed",
                additional_data=additional_data
            )
    
    async def send_test_notification(self, email: str) -> bool:
        """发送测试邮件
        
        Args:
            email: 收件人邮箱
            
        Returns:
            bool: 发送是否成功
        """
        subject = "SceneGEN邮件通知测试"
        message = f"""
这是一封测试邮件，用于验证SceneGEN邮件通知功能。

测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

如果您收到此邮件，说明邮件通知功能工作正常。

此邮件由系统自动发送，请勿回复。
        """.strip()
        
        return await self.send_notification(
            email=email,
            subject=subject,
            message=message,
            task_id="test",
            status="test",
            additional_data={"test": True}
        )

# 全局邮件通知器实例
_email_notifier = None

def get_email_notifier() -> SupabaseEmailNotifier:
    """获取邮件通知器实例(单例模式)"""
    global _email_notifier
    if _email_notifier is None:
        _email_notifier = SupabaseEmailNotifier()
    return _email_notifier

# 便捷函数
async def send_training_completion_email(email: str, 
                                       task_id: str,
                                       success: bool = True,
                                       processing_time: float = None,
                                       public_url: str = None,
                                       error_message: str = None) -> bool:
    """发送训练完成邮件的便捷函数"""
    notifier = get_email_notifier()
    return await notifier.send_training_completion_notification(
        email=email,
        task_id=task_id,
        success=success,
        processing_time=processing_time,
        public_url=public_url,
        error_message=error_message
    )

async def send_test_email(email: str) -> bool:
    """发送测试邮件的便捷函数"""
    notifier = get_email_notifier()
    return await notifier.send_test_notification(email)

if __name__ == "__main__":
    # 测试代码
    import sys
    
    async def test_email():
        if len(sys.argv) < 2:
            print("用法: python supabase_email_notifier.py <email>")
            return
        
        email = sys.argv[1]
        print(f"发送测试邮件到: {email}")
        
        success = await send_test_email(email)
        if success:
            print("测试邮件发送成功！")
        else:
            print("测试邮件发送失败！")
    
    # 运行测试
    asyncio.run(test_email())