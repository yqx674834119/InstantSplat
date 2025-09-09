#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Resend API测试脚本
用于直接测试Resend API是否正常工作
"""

import os
import sys
import requests
import json
from pathlib import Path

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
        print(f"✅ 已加载环境变量文件: {env_file_path}")
    else:
        print(f"❌ 环境变量文件不存在: {env_file_path}")
        return False
    return True

def test_resend_api(email: str):
    """直接测试Resend API"""
    print("🧪 直接测试Resend API...")
    
    # 获取环境变量
    resend_api_key = os.getenv('RESEND_API_KEY')
    from_email = os.getenv('FROM_EMAIL', 'noreply@instantsplat.com')
    
    if not resend_api_key:
        print("❌ 未找到RESEND_API_KEY环境变量")
        return False
    
    print(f"📧 发送方邮箱: {from_email}")
    print(f"📧 接收方邮箱: {email}")
    print(f"🔑 API密钥: {resend_api_key[:10]}...{resend_api_key[-4:]}")
    
    # 构建邮件数据
    email_data = {
        "from": from_email,
        "to": [email],
        "subject": "Resend API测试邮件",
        "html": """
        <html>
        <body>
            <h2>🧪 Resend API测试</h2>
            <p>这是一封测试邮件，用于验证Resend API是否正常工作。</p>
            <p><strong>测试时间:</strong> {}</p>
            <p>如果您收到这封邮件，说明Resend API配置正确。</p>
        </body>
        </html>
        """.format("2025-01-10 测试"),
        "text": "这是一封Resend API测试邮件。如果您收到这封邮件，说明API配置正确。"
    }
    
    # 发送请求
    headers = {
        "Authorization": f"Bearer {resend_api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        print("📤 发送邮件请求...")
        response = requests.post(
            "https://api.resend.com/emails",
            headers=headers,
            json=email_data,
            timeout=30
        )
        
        print(f"📊 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 邮件发送成功！")
            print(f"📧 邮件ID: {result.get('id', 'N/A')}")
            return True
        else:
            print(f"❌ 邮件发送失败")
            try:
                error_data = response.json()
                print(f"🔍 错误详情: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
                
                # 分析常见错误
                if response.status_code == 401:
                    print("\n💡 可能的问题:")
                    print("   - API密钥无效或已过期")
                    print("   - 请检查Resend控制台中的API密钥")
                elif response.status_code == 403:
                    print("\n💡 可能的问题:")
                    print("   - 发送方域名未验证")
                    print("   - 请在Resend控制台验证域名")
                elif response.status_code == 422:
                    print("\n💡 可能的问题:")
                    print("   - 邮件格式或内容有误")
                    print("   - 发送方邮箱格式不正确")
                    
            except json.JSONDecodeError:
                print(f"🔍 响应内容: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ 请求超时")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 网络连接错误")
        return False
    except Exception as e:
        print(f"❌ 发生未知错误: {e}")
        return False

def check_domain_verification():
    """检查域名验证状态"""
    print("\n🔍 检查域名验证建议...")
    
    from_email = os.getenv('FROM_EMAIL', 'noreply@instantsplat.com')
    domain = from_email.split('@')[1] if '@' in from_email else 'unknown'
    
    print(f"📧 当前发送域名: {domain}")
    print("\n📋 域名验证步骤:")
    print("1. 登录 https://resend.com/domains")
    print(f"2. 添加域名: {domain}")
    print("3. 配置DNS记录（SPF、DKIM、DMARC）")
    print("4. 等待验证完成")
    print("\n⚠️  注意: 未验证的域名可能无法发送邮件")

def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("使用方法: python3 test_resend_api.py <email>")
        print("示例: python3 test_resend_api.py test@example.com")
        sys.exit(1)
    
    email = sys.argv[1]
    
    # 简单的邮箱格式验证
    if '@' not in email or '.' not in email:
        print("❌ 邮箱格式不正确")
        sys.exit(1)
    
    print("🚀 开始Resend API测试...")
    print("=" * 50)
    
    # 加载环境变量
    if not load_env_file():
        sys.exit(1)
    
    # 测试API
    success = test_resend_api(email)
    
    # 显示域名验证建议
    if not success:
        check_domain_verification()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 Resend API测试成功！")
        print("💡 如果Supabase Edge Function仍然失败，可能是环境变量配置问题")
    else:
        print("❌ Resend API测试失败")
        print("💡 请检查API密钥和域名验证状态")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()