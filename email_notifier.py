#!/usr/bin/env python3
"""
邮件通知模块
用于发送任务完成或失败的邮件通知
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailNotifier:
    """邮件通知器"""
    
    def __init__(self):
        # 邮件服务器配置 (使用QQ邮箱)
        self.smtp_server = "smtp.qq.com"
        self.smtp_port = 587
        self.sender_email = "674834119@qq.com"
        self.sender_password = "your_app_password"  # 需要使用QQ邮箱的授权码
        self.default_recipient = "674834119@qq.com"
        
    def send_task_completion_notification(
        self, 
        task_id: str, 
        status: str, 
        recipient_email: Optional[str] = None,
        processing_time: Optional[float] = None,
        error_message: Optional[str] = None,
        result_files: Optional[dict] = None
    ) -> bool:
        """发送任务完成通知邮件
        
        Args:
            task_id: 任务ID
            status: 任务状态 (completed/failed)
            recipient_email: 收件人邮箱，如果为None则使用默认邮箱
            processing_time: 处理时间（秒）
            error_message: 错误信息（如果失败）
            result_files: 结果文件信息
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 如果未提供邮件地址，使用默认测试邮件地址
            to_email = recipient_email or "674834119@qq.com"
            
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = to_email
            
            # 根据状态设置邮件主题和内容
            if status == "completed":
                msg['Subject'] = f"InstantSplat 三维重建任务完成 - {task_id}"
                body = self._create_success_email_body(
                    task_id, processing_time, result_files
                )
            else:
                msg['Subject'] = f"InstantSplat 三维重建任务失败 - {task_id}"
                body = self._create_failure_email_body(
                    task_id, error_message
                )
            
            msg.attach(MIMEText(body, 'html', 'utf-8'))
            
            # 发送邮件
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            
            logger.info(f"邮件通知发送成功: {task_id} -> {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"邮件通知发送失败 {task_id}: {e}")
            return False
    
    def _create_success_email_body(
        self, 
        task_id: str, 
        processing_time: Optional[float], 
        result_files: Optional[dict]
    ) -> str:
        """创建成功邮件内容"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        processing_time_str = f"{processing_time:.2f}秒" if processing_time else "未知"
        
        # 构建结果文件信息
        files_info = ""
        if result_files:
            files_info = "<h3>生成的文件:</h3><ul>"
            for file_type, file_path in result_files.items():
                files_info += f"<li><strong>{file_type}</strong>: {file_path}</li>"
            files_info += "</ul>"
        
        body = f"""
        <html>
        <body>
            <h2>🎉 InstantSplat 三维重建任务完成</h2>
            <p>您的三维重建任务已成功完成！</p>
            
            <h3>任务信息:</h3>
            <ul>
                <li><strong>任务ID:</strong> {task_id}</li>
                <li><strong>完成时间:</strong> {current_time}</li>
                <li><strong>处理时长:</strong> {processing_time_str}</li>
                <li><strong>状态:</strong> ✅ 成功完成</li>
            </ul>
            
            {files_info}
            
            <p>您可以通过API接口下载处理结果。</p>
            
            <hr>
            <p><small>这是一封自动发送的邮件，请勿回复。</small></p>
            <p><small>InstantSplat 三维重建服务</small></p>
        </body>
        </html>
        """
        return body
    
    def _create_failure_email_body(
        self, 
        task_id: str, 
        error_message: Optional[str]
    ) -> str:
        """创建失败邮件内容"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_info = error_message or "未知错误"
        
        body = f"""
        <html>
        <body>
            <h2>❌ InstantSplat 三维重建任务失败</h2>
            <p>很抱歉，您的三维重建任务处理失败。</p>
            
            <h3>任务信息:</h3>
            <ul>
                <li><strong>任务ID:</strong> {task_id}</li>
                <li><strong>失败时间:</strong> {current_time}</li>
                <li><strong>状态:</strong> ❌ 处理失败</li>
            </ul>
            
            <h3>错误信息:</h3>
            <div style="background-color: #f8f8f8; padding: 10px; border-left: 4px solid #ff6b6b; margin: 10px 0;">
                <code>{error_info}</code>
            </div>
            
            <p>请检查您的输入文件或联系技术支持。</p>
            
            <hr>
            <p><small>这是一封自动发送的邮件，请勿回复。</small></p>
            <p><small>InstantSplat 三维重建服务</small></p>
        </body>
        </html>
        """
        return body

# 全局邮件通知器实例
email_notifier = EmailNotifier()