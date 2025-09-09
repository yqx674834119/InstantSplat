#!/bin/bash

# Supabase邮件通知功能部署脚本
# 使用方法: ./deploy_supabase.sh

set -e

echo "🚀 开始部署Supabase邮件通知功能..."

# 检查Supabase CLI是否安装
if ! command -v supabase &> /dev/null; then
    echo "❌ 错误: 未找到Supabase CLI"
    echo "请先安装Supabase CLI: https://supabase.com/docs/guides/cli"
    exit 1
fi

# 检查环境变量文件
if [ ! -f ".env.supabase" ]; then
    echo "❌ 错误: 未找到 .env.supabase 文件"
    echo "请复制 .env.supabase.example 为 .env.supabase 并配置相关参数"
    exit 1
fi

# 加载环境变量
source .env.supabase

# 检查必要的环境变量
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_ANON_KEY" ] || [ -z "$RESEND_API_KEY" ]; then
    echo "❌ 错误: 缺少必要的环境变量"
    echo "请检查 .env.supabase 文件中的配置"
    exit 1
fi

# 检查是否已登录Supabase
echo "🔐 检查Supabase登录状态..."
if ! supabase projects list &> /dev/null; then
    echo "❌ 未登录Supabase，请先登录:"
    echo "supabase login"
    exit 1
fi

# 初始化Supabase项目（如果尚未初始化）
if [ ! -f "supabase/config.toml" ]; then
    echo "📦 初始化Supabase项目..."
    supabase init
fi

# 创建Edge Function目录结构
echo "📁 创建Edge Function目录结构..."
mkdir -p supabase/functions/send-notification-email

# 检查Edge Function文件是否存在
if [ ! -f "supabase/functions/send-notification-email/index.ts" ]; then
    echo "❌ 错误: 未找到Edge Function文件"
    echo "请确保 supabase/functions/send-notification-email/index.ts 文件存在"
    exit 1
fi

# 部署Edge Function
echo "🚀 部署Edge Function..."
supabase functions deploy send-notification-email --project-ref $SUPABASE_PROJECT_REF --no-verify-jwt

# 设置Edge Function的环境变量
echo "⚙️ 设置Edge Function环境变量..."
supabase secrets set RESEND_API_KEY="$RESEND_API_KEY"
supabase secrets set FROM_EMAIL="$FROM_EMAIL"

echo "✅ Supabase邮件通知功能部署完成！"
echo ""
echo "📋 部署信息:"
echo "   Edge Function URL: $SUPABASE_URL/functions/v1/send-notification-email"
echo "   Anon Key: $SUPABASE_ANON_KEY"
echo ""