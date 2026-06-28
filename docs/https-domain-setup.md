# HTTPS 域名接入说明

这份说明用于把新媒体 AI 平台从服务器 IP 访问升级为正式 HTTPS 域名访问。

## 1. 准备域名

准备一个二级域名，例如：

```text
media.your-domain.com
```

本项目当前建议使用：

```text
media.tech-ark.com
```

在域名 DNS 控制台添加 A 记录：

```text
类型: A
主机记录: media
记录值: 你的服务器公网 IP
TTL: 默认
```

等待解析生效后，在本机或服务器验证：

```bash
ping media.your-domain.com
```

返回的 IP 应该是你的服务器公网 IP。

## 2. 确认服务器端口

云服务器安全组和系统防火墙需要放行：

```text
80/tcp
443/tcp
```

平台 Docker 服务只监听服务器本机：

```text
127.0.0.1:8010
```

公网只暴露 Nginx 的 80 和 443，不要直接暴露 8000。

为了避免影响服务器上已有系统，`media.tech-ark.com` 推荐使用独立本地端口 `8010`：

```bash
PLATFORM_HOST_PORT=8010 docker compose -f infra/server/docker-compose.prod.yml up -d --build
```

## 3. 配置 Nginx 反向代理

复制项目模板：

```bash
cd /opt/new-media-ai-platform
cp infra/server/nginx-platform.conf /etc/nginx/conf.d/new-media-ai-platform.conf
```

编辑：

```bash
vim /etc/nginx/conf.d/new-media-ai-platform.conf
```

把：

```nginx
server_name _;
```

改成你的域名：

```nginx
server_name media.your-domain.com;
```

如果使用 `media.tech-ark.com`，也可以直接复制项目里的专用模板：

```bash
cp infra/server/nginx-media-tech-ark.conf /etc/nginx/conf.d/media-tech-ark.conf
nginx -t
systemctl reload nginx
```

检查并重载：

```bash
nginx -t
systemctl reload nginx
```

此时应该可以访问：

```text
http://media.your-domain.com/
```

## 4. 签 HTTPS 证书

OpenCloudOS / CentOS / Rocky Linux 可以用 certbot：

```bash
dnf install -y certbot python3-certbot-nginx
certbot --nginx -d media.tech-ark.com
```

按提示选择自动重定向 HTTP 到 HTTPS。

完成后验证自动续期：

```bash
certbot renew --dry-run
```

## 5. 发布后验收

```bash
curl -I --max-time 20 https://media.tech-ark.com/
curl -I --max-time 20 https://media.tech-ark.com/api/health
curl -I --max-time 20 https://media.tech-ark.com/api/dashboard
```

预期：

- `/` 返回 `200`。
- `/api/health` 返回 `200`。
- `/api/dashboard` 返回 `401`，表示接口已经被登录保护，不是故障。

浏览器打开：

```text
https://media.tech-ark.com/
```

使用后台账号登录后，再检查素材预览、视频任务、发布中心。

## 6. 常见问题

### 证书申请失败

先确认：

- 域名 A 记录已经指向服务器公网 IP。
- 安全组已放行 80 和 443。
- Nginx 正在运行。
- `http://域名/` 能打开或至少能连通。

### HTTPS 可以打开，但上传大文件失败

确认 Nginx 配置里有：

```nginx
client_max_body_size 2048m;
proxy_read_timeout 600s;
proxy_send_timeout 600s;
```

当前模板已经包含这些配置。

### 不要覆盖服务器 `.env`

生产服务器的 `backend/.env` 只在服务器上维护。同步代码时不要用本机 `.env` 覆盖服务器 `.env`，避免把正式密码、模型 Key、服务器路径覆盖掉。
