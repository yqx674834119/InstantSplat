// Supabase Edge Function for sending notification emails
// 使用globalThis访问Deno运行时
const { Deno } = globalThis as any;

// 邮件通知请求接口
interface NotificationRequest {
  email: string;
  subject: string;
  message: string;
  task_id?: string;
  status?: string;
  timestamp?: string;
  additional_data?: Record<string, any>;
  test?: boolean;
}

// 邮件发送响应接口
interface EmailResponse {
  success: boolean;
  message: string;
  email_id?: string;
  error?: string;
}

// CORS头部
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

// 主处理函数
Deno.serve(async (req: Request): Promise<Response> => {
  // 处理CORS预检请求
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: corsHeaders,
    });
  }

  // 只允许POST请求
  if (req.method !== 'POST') {
    return new Response(
      JSON.stringify({ success: false, error: 'Method not allowed' }),
      {
        status: 405,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  }

  try {
    // 获取环境变量
    const resendApiKey = Deno.env.get('RESEND_API_KEY');
    const fromEmail = Deno.env.get('FROM_EMAIL') || 'noreply@SceneGEN.com';

    if (!resendApiKey) {
      console.error('RESEND_API_KEY environment variable is not set');
      return new Response(
        JSON.stringify({ 
          success: false, 
          error: 'Email service not configured' 
        }),
        {
          status: 500,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    // 解析请求体
    const requestData: NotificationRequest = await req.json();
    
    // 验证必需字段
    if (!requestData.email || !requestData.subject || !requestData.message) {
      return new Response(
        JSON.stringify({ 
          success: false, 
          error: 'Missing required fields: email, subject, message' 
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    // 验证邮箱格式
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(requestData.email)) {
      return new Response(
        JSON.stringify({ 
          success: false, 
          error: 'Invalid email format' 
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    console.log(`Sending email to: ${requestData.email}, Subject: ${requestData.subject}`);

    // 构建HTML邮件内容
    const htmlContent = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${requestData.subject}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 20px;
            text-align: center;
            border-radius: 8px 8px 0 0;
        }
        .content {
            background: #f8f9fa;
            padding: 30px 20px;
            border-radius: 0 0 8px 8px;
        }
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }
        .status-completed {
            background: #d4edda;
            color: #155724;
        }
        .status-failed {
            background: #f8d7da;
            color: #721c24;
        }
        .status-test {
            background: #d1ecf1;
            color: #0c5460;
        }
        .footer {
            text-align: center;
            margin-top: 20px;
            font-size: 12px;
            color: #666;
        }
        .message-content {
            white-space: pre-line;
            background: white;
            padding: 20px;
            border-radius: 4px;
            border-left: 4px solid #667eea;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 SceneGEN</h1>
        <p>3D重建服务通知</p>
    </div>
    <div class="content">
        ${requestData.additional_data?.download_url ? `
        <div style="text-align: center; margin: 20px 0;">
            <a href="${requestData.additional_data.download_url}" 
               style="background: #667eea; color: white; padding: 12px 24px; 
                      text-decoration: none; border-radius: 4px; 
                      display: inline-block; font-size: 16px;">
                🔍 查看重建模型
            </a>
        </div>
        ` : ''}
        ${requestData.status ? `<p><span class="status-badge status-${requestData.status}">${requestData.status}</span></p>` : ''}
        ${requestData.task_id ? `<p><strong>任务ID:</strong> ${requestData.task_id}</p>` : ''}
        ${requestData.timestamp ? `<p><strong>时间:</strong> ${new Date(requestData.timestamp).toLocaleString('zh-CN')}</p>` : ''}
        
        <div class="message-content">
            ${requestData.message}
        </div>        
    </div>
    <div class="footer">
        <p>此邮件由SceneGEN系统自动发送，请勿回复。</p>
        <p>如有问题，请联系技术支持 <a href="mailto:qyao951@connect.hkust-gz.edu.cn">qyao951@connect.hkust-gz.edu.cn</a> 。</p>
    </div>
</body>
</html>
    `.trim();

    // 发送邮件到Resend API
    const emailPayload = {
      from: fromEmail,
      to: [requestData.email],
      subject: requestData.subject,
      html: htmlContent,
      text: requestData.message, // 纯文本备用
    };

    const resendResponse = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${resendApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(emailPayload),
    });

    const resendResult = await resendResponse.json();

    if (resendResponse.ok) {
      console.log('Email sent successfully:', resendResult);
      
      const response: EmailResponse = {
        success: true,
        message: 'Email sent successfully',
        email_id: resendResult.id,
      };

      return new Response(JSON.stringify(response), {
        status: 200,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    } else {
      console.error('Resend API error:', resendResult);
      
      const response: EmailResponse = {
        success: false,
        message: 'Failed to send email',
        error: resendResult.message || 'Unknown error from email service',
      };

      return new Response(JSON.stringify(response), {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

  } catch (error) {
    console.error('Function error:', error);
    
    const response: EmailResponse = {
      success: false,
      message: 'Internal server error',
      error: error instanceof Error ? error.message : 'Unknown error',
    };

    return new Response(JSON.stringify(response), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});