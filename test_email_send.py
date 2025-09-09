#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supabase邮件发送测试脚本
用于测试邮件通知功能是否正常工作
"""

import asyncio
import sys
import os
from datetime import datetime

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from supabase_email_notifier import send_training_completion_email, send_test_email
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请确保 supabase_email_notifier.py 文件存在且配置正确")
    sys.exit(1)

async def test_basic_email(email: str):
    """测试基础邮件发送功能"""
    print(f"📧 测试基础邮件发送到: {email}")
    try:
        result = await send_test_email(email)
        if result:
            print("✅ 基础邮件发送成功")
            return True
        else:
            print("❌ 基础邮件发送失败")
            return False
    except Exception as e:
        print(f"❌ 基础邮件发送异常: {e}")
        return False

async def test_training_completion_email(email: str):
    """测试训练完成邮件发送功能"""
    print(f"📧 测试训练完成邮件发送到: {email}")
    
    # 模拟训练完成的数据
    test_data = {
        'task_id': 'test-task-12345',
        'success': True,
        'download_url': 'http://localhost:3080/api/v1/tasks/test-task-12345/download/ply',
        'processing_time': 120.5,
        'error_message': None
    }
    
    try:
        result = await send_training_completion_email(
            email=email,
            task_id=test_data['task_id'],
            success=test_data['success'],
            download_url=test_data['download_url'],
            processing_time=test_data['processing_time']
        )
        if result:
            print("✅ 训练完成邮件发送成功")
            return True
        else:
            print("❌ 训练完成邮件发送失败")
            return False
    except Exception as e:
        print(f"❌ 训练完成邮件发送异常: {e}")
        return False

async def test_training_failure_email(email: str):
    """测试训练失败邮件发送功能"""
    print(f"📧 测试训练失败邮件发送到: {email}")
    
    # 模拟训练失败的数据
    test_data = {
        'task_id': 'test-task-67890',
        'success': False,
        'download_url': None,
        'processing_time': 45.2,
        'error_message': '几何初始化失败：无法提取足够的特征点'
    }
    
    try:
        result = await send_training_completion_email(
            email=email,
            task_id=test_data['task_id'],
            success=test_data['success'],
            download_url=test_data['download_url'],
            processing_time=test_data['processing_time'],
            error_message=test_data['error_message']
        )
        if result:
            print("✅ 训练失败邮件发送成功")
            return True
        else:
            print("❌ 训练失败邮件发送失败")
            return False
    except Exception as e:
        print(f"❌ 训练失败邮件发送异常: {e}")
        return False

def check_environment():
    """检查环境配置"""
    print("🔍 检查环境配置...")
    
    # 检查环境变量文件
    env_file = '.env.supabase'
    if not os.path.exists(env_file):
        print(f"❌ 未找到环境变量文件: {env_file}")
        print("请复制 .env.supabase.example 为 .env.supabase 并配置相关参数")
        return False
    
    # 检查必要的环境变量
    required_vars = ['SUPABASE_URL', 'SUPABASE_ANON_KEY', 'RESEND_API_KEY', 'FROM_EMAIL']
    missing_vars = []
    
    # 读取环境变量文件
    try:
        with open(env_file, 'r') as f:
            env_content = f.read()
            for var in required_vars:
                if f'{var}=' not in env_content or f'{var}=your-' in env_content or f'{var}=""' in env_content:
                    missing_vars.append(var)
    except Exception as e:
        print(f"❌ 读取环境变量文件失败: {e}")
        return False
    
    if missing_vars:
        print(f"❌ 缺少或未配置的环境变量: {', '.join(missing_vars)}")
        print("请在 .env.supabase 文件中配置这些变量")
        return False
    
    print("✅ 环境配置检查通过")
    return True

async def run_all_tests(email: str):
    """运行所有测试"""
    print("🚀 开始邮件发送测试...")
    print(f"📅 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📧 测试邮箱: {email}")
    print("=" * 50)
    
    # 检查环境配置
    if not check_environment():
        return False
    
    print("")
    
    # 运行测试
    tests = [
        ("基础邮件发送", test_basic_email(email)),
        ("训练完成邮件", test_training_completion_email(email)),
        ("训练失败邮件", test_training_failure_email(email))
    ]
    
    results = []
    for test_name, test_coro in tests:
        print(f"\n🧪 {test_name}测试:")
        result = await test_coro
        results.append((test_name, result))
        print("")
    
    # 输出测试结果
    print("=" * 50)
    print("📊 测试结果汇总:")
    success_count = 0
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
        if result:
            success_count += 1
    
    print(f"\n📈 总体结果: {success_count}/{len(results)} 个测试通过")
    
    if success_count == len(results):
        print("🎉 所有测试通过！邮件通知功能正常工作")
        return True
    else:
        print("⚠️  部分测试失败，请检查配置和网络连接")
        return False

def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("使用方法: python3 test_email_send.py <email>")
        print("示例: python3 test_email_send.py test@example.com")
        sys.exit(1)
    
    email = sys.argv[1]
    
    # 简单的邮箱格式验证
    if '@' not in email or '.' not in email:
        print("❌ 邮箱格式不正确")
        sys.exit(1)
    
    try:
        success = asyncio.run(run_all_tests(email))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 测试过程中发生未预期的错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()