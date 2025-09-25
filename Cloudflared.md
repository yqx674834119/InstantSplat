# 使用 Cloudflare Tunnel 暴露本地服务
## 1. 前提条件

你有一个域名（已经托管在 Cloudflare上）

你的本地服务器能运行 cloudflared

## 2. 安装 cloudflared

在本地服务器（你的 3080 服务所在的机器）上安装：

Ubuntu/Debian:

```
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

验证安装：
```
cloudflared --version
```

## 3. 登录 Cloudflare 账号

运行：

```
cloudflared tunnel login
```

它会打开一个浏览器，要求你登录 Cloudflare，并选择你的域名。
这一步会把认证信息保存到本地。

## 4. 创建 Tunnel

创建一个新的 tunnel（例如叫 my-service）：

```
cloudflared tunnel create my-service
```

这个命令会输出一个 `Tunnel UUID`，并在 ~/.cloudflared/ 下生成配置文件。

## 5. 配置 Tunnel 访问本地服务  

编辑 ~/.cloudflared/config.yml，写入： 这里的hostname 可以使用二级域名  比如 一级域名是scenegen.cn  二级域名是app.scenegen.cn 或者其他的。
```yml
tunnel: <TUNNEL-UUID>
credentials-file: /home/<your-user>/.cloudflared/<TUNNEL-UUID>.json

ingress:
  - hostname: app.scenegen.cn
    service: http://localhost:3080
  - service: http_status:404
```

## 6. 配置 DNS

让 Cloudflare 把 app.yourdomain.com 指向这个 Tunnel：
```
cloudflared tunnel route dns my-service app.scenegen.cn
```

这会在 Cloudflare 控制台自动创建一条 CNAME 记录。
## 7. 启动 Tunnel

启动服务：
```
nohup cloudflared tunnel run my-service > cloudflared.log 2>&1 &
<!-- ps aux | grep '[c]loudflared tunnel run my-service' -->
```

## 8. 访问测试

现在你可以访问 https://app.scenegen.cn 来测试。
