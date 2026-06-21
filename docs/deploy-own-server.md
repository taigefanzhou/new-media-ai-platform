# 自有服务器部署说明

适用服务器：OpenCloudOS 9.x / CentOS Stream / Rocky Linux 这类 Linux 服务器。

推荐架构：

- 主平台：Docker 运行 FastAPI 后台和前端页面。
- 视频号解析代理：Docker 运行在 `8099` 端口，给后台“短视频采集接入”调用。
- 外网入口：Nginx 反向代理到平台服务。
- 视频/素材文件：保存在服务器磁盘或后台配置的外部存储目录。
- AI 模型：仍然调用火山、阿里、D-ID 等 API，不建议在 4 核 8G 服务器上本地跑大模型。

## 1. 安装基础环境

在服务器终端执行：

```bash
dnf update -y
dnf install -y git docker nginx
systemctl enable --now docker
systemctl enable --now nginx
```

如果系统没有 `docker compose`，可以继续安装 Compose 插件：

```bash
dnf install -y docker-compose-plugin
```

## 2. 拉取项目

```bash
mkdir -p /opt
cd /opt
git clone https://github.com/taigefanzhou/new-media-ai-platform.git
cd /opt/new-media-ai-platform
```

如果目录已经存在：

```bash
cd /opt/new-media-ai-platform
git pull
```

## 3. 配置环境变量

```bash
cp backend/.env.example backend/.env
```

然后编辑 `backend/.env`，至少修改：

```env
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="换成强密码"
DATABASE_URL="sqlite:///./data/platform.db"
STORAGE_DIR="./data/storage"
```

模型 Key、D-ID Key、视频号解析服务 Key 不要写在聊天窗口里，直接在服务器或后台页面填写。

## 4. 启动平台

```bash
docker compose -f infra/server/docker-compose.prod.yml up -d --build
```

如果服务器访问默认 PyPI 慢或失败，可以显式使用国内镜像：

```bash
PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.11-slim \
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
ALLOW_PRODUCTION_DOCKER_BUILD=1 \
docker compose -f infra/server/docker-compose.prod.yml up -d --build
```

如果基础镜像仍然拉不下来，可以换腾讯云镜像再试：

```bash
PYTHON_BASE_IMAGE=ccr.ccs.tencentyun.com/library/python:3.11-slim \
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
ALLOW_PRODUCTION_DOCKER_BUILD=1 \
docker compose -f infra/server/docker-compose.prod.yml up -d --build
```

检查服务：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8099/health
```

## 5. 配置 Nginx

```bash
cp infra/server/nginx-platform.conf /etc/nginx/conf.d/new-media-ai-platform.conf
nginx -t
systemctl reload nginx
```

然后在云服务器安全组里放行：

- `80/tcp`：平台网页入口
- `443/tcp`：后续绑定域名和 HTTPS 时使用
- `8099/tcp`：视频号解析代理接口。如果只通过内网或 Nginx 转发访问，可以不对公网开放。

如果暂时没有域名，可以先访问：

```text
http://82.156.2.200/
```

## 6. 后续更新

```bash
cd /opt/new-media-ai-platform
git pull
docker compose -f infra/server/docker-compose.prod.yml up -d --build
```

## 7. 视频号解析服务

平台后台已经支持短视频链接解析接口。推荐两种方式：

### 临时测试

后台进入：

```text
系统设置 -> 短视频采集接入 -> 视频号公开测试
```

保存后可以用“链接解析测试”验证视频号链接。

### 正式自有服务

后台进入：

```text
系统设置 -> 短视频采集接入 -> 视频号自有服务
```

默认接口：

```text
http://82.156.2.200:8099/api/fetch_video_profile
```

这个接口需要你自己的解析服务部署成功，并在解析服务内部保存元宝 Web Cookie。Cookie 不要发给任何人，直接放在你自己的服务器配置里。

当前仓库已经提供一个轻量“解析代理服务”，默认会转发到公开测试解析站：

```text
services/link-resolver-proxy
```

如果要把代理服务改成你自己的 Worker 或正式解析 API，在服务器启动前设置：

```bash
export UPSTREAM_RESOLVER_URL="https://你的解析服务/api/fetch_video_profile"
docker compose -f infra/server/docker-compose.prod.yml up -d --build
```

如果想保护 `8099` 接口，可以设置：

```bash
export RESOLVER_ACCESS_TOKEN="自己生成一串长密码"
docker compose -f infra/server/docker-compose.prod.yml up -d --build
```

设置后，后台“短视频采集接入”的 Access Token 也填同一串值。
