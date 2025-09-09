# Supabase邮件通知功能设置指南

本指南将帮助您配置和部署InstantSplat的Supabase邮件通知功能。

## 前置要求

1. **Supabase账户**: 在 [supabase.com](https://supabase.com) 注册账户
2. **Resend账户**: 在 [resend.com](https://resend.com) 注册账户用于发送邮件
3. **Supabase CLI**: 安装Supabase命令行工具

## 安装Supabase CLI

```bash
# 下载 Supabase CLI 最新版 (Linux x86_64)
curl -sL https://github.com/supabase/cli/releases/latest/download/supabase_linux_amd64.tar.gz \
  | sudo tar -xz -C /usr/local/bin

# 验证安装
supabase --version

```

## 配置步骤

### 1. 创建Supabase项目

1. 登录 [Supabase Dashboard](https://app.supabase.com)
2. 点击 "New Project"
3. 选择组织并填写项目信息
4. 等待项目创建完成

### 2. 获取项目凭据

在Supabase项目的Settings > API页面获取:
- Project URL
- Anon public key
- Service role key

### 3. 配置Resend邮件服务

1. 登录 [Resend Dashboard](https://resend.com/dashboard)
2. 创建API Key
3. 验证发送域名（可选，用于生产环境）

### 4. 配置环境变量

复制环境变量模板文件:
```bash
cp .env.supabase.example .env.supabase
```

编辑 `.env.supabase` 文件，填入实际值:
```bash
# Supabase项目配置
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here

# Resend邮件服务配置
RESEND_API_KEY=your-resend-api-key-here
FROM_EMAIL=noreply@yourdomain.com

# 邮件通知配置
EMAIL_ENABLED=true
EMAIL_FROM_NAME=InstantSplat 3D重建服务

# 前端URL配置
FRONTEND_URL=http://localhost:3000
```

### 5. 登录Supabase CLI

```bash
supabase login
```

### 6. 部署邮件通知功能

运行部署脚本:
```bash
./deploy_supabase.sh
```

## 测试邮件功能

部署完成后，可以使用以下命令测试邮件发送:

```bash
python3 -c "from supabase_email_notifier import send_test_email; import asyncio; asyncio.run(send_test_email('test@example.com'))"
```

## API集成

邮件通知功能已集成到API服务器中，当3D重建任务完成时会自动发送邮件通知。

### 前端集成示例

在提交3D重建任务时，包含用户邮箱:

```javascript
const formData = new FormData();
formData.append('video', videoFile);
formData.append('email', 'user@example.com'); // 添加邮箱字段

fetch('/api/upload_video', {
    method: 'POST',
    body: formData
});
```

## 邮件模板

系统会发送包含以下信息的邮件:
- 任务完成状态
- 3D模型下载链接（成功时）
- 错误信息（失败时）
- 处理时间统计

## 故障排除

### 常见问题

1. **Edge Function部署失败**
   - 检查Supabase CLI是否正确登录
   - 确认项目权限
   - 检查网络连接

2. **邮件发送失败**
   - 验证Resend API Key
   - 检查发送域名配置
   - 确认邮箱地址格式正确

3. **环境变量问题**
   - 确保 `.env.supabase` 文件存在且配置正确
   - 检查环境变量是否正确加载

### 日志查看

查看Edge Function日志:
```bash
supabase functions logs send-notification-email
```

查看API服务器日志:
```bash
tail -f logs/api_server.log
```

## 生产环境配置

在生产环境中:

1. 使用自定义域名配置Resend
2. 设置适当的邮件发送频率限制
3. 配置邮件模板和品牌样式
4. 启用邮件发送监控和分析

## 安全注意事项

1. 不要将 `.env.supabase` 文件提交到版本控制
2. 定期轮换API密钥
3. 使用最小权限原则配置服务角色
4. 在生产环境中启用JWT验证

## 支持

如果遇到问题，请:
1. 检查本文档的故障排除部分
2. 查看Supabase和Resend的官方文档
3. 提交Issue到项目仓库