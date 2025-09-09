#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件通知功能测试脚本
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from email_notifier import email_notifier
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_success_notification():
    """测试成功通知"""
    logger.info("测试成功通知邮件...")
    try:
        email_notifier.send_task_completion_notification(
            task_id="test_task_001",
            status="completed",
            recipient_email=None,  # 使用默认邮件地址
            processing_time=120.5,
            result_files={
                "output_dir": "/test/output",
                "files": ["model.ply", "cameras.json"]
            }
        )
        logger.info("成功通知邮件发送完成")
    except Exception as e:
        logger.error(f"发送成功通知邮件失败: {e}")

def test_failure_notification():
    """测试失败通知"""
    logger.info("测试失败通知邮件...")
    try:
        email_notifier.send_task_completion_notification(
            task_id="test_task_002",
            status="failed",
            recipient_email=None,  # 使用默认邮件地址
            error_message="测试错误：文件格式不支持"
        )
        logger.info("失败通知邮件发送完成")
    except Exception as e:
        logger.error(f"发送失败通知邮件失败: {e}")

def test_custom_email():
    """测试自定义邮件地址"""
    logger.info("测试自定义邮件地址...")
    try:
        email_notifier.send_task_completion_notification(
            task_id="test_task_003",
            status="completed",
            recipient_email="674834119@qq.com",  # 指定邮件地址
            processing_time=85.2,
            result_files={
                "output_dir": "/custom/output",
                "files": ["scene.ply"]
            }
        )
        logger.info("自定义邮件地址通知发送完成")
    except Exception as e:
        logger.error(f"发送自定义邮件通知失败: {e}")

if __name__ == "__main__":
    logger.info("开始邮件通知功能测试")
    
    # 测试成功通知
    test_success_notification()
    
    # 等待一下
    import time
    time.sleep(2)
    
    # 测试失败通知
    test_failure_notification()
    
    # 等待一下
    time.sleep(2)
    
    # 测试自定义邮件地址
    test_custom_email()
    
    logger.info("邮件通知功能测试完成")