# HealthAI 构建与部署指南

本文覆盖本地开发、单机自托管部署、镜像构建和前端静态资源打包。当前项目只提供本机构建与部署流程，不包含镜像仓库推送。

## 使用方式总览

| 场景 | 推荐命令 | 说明 |
| --- | --- | --- |
| 日常开发 | `npm run dev` | 同时启动 FastAPI 后端与 Vite 前端 |
| 本地自托管体验 | `npm run docker:up` | 通过 Docker Compose 构建并启动完整栈 |
| 生产单机部署 | `docker compose build` + `docker compose up -d` | 使用本机构建的镜像运行服务 |
| 前端静态部署 | `npm --prefix frontend run build` | 生成 `frontend/dist`，交给 Nginx 或对象存储/CDN |

## 1. 开发环境

在仓库根目录执行：

```bash
npm run dev
```

脚本会自动完成：

- 创建 `backend/.env` 和 `frontend/.env`。
- 创建后端虚拟环境并安装 Python 依赖。
- 安装前端依赖。
- 启动 FastAPI 和 Vite。

常用变体：

```bash
npm run dev -- --backend-only
npm run dev -- --frontend-only
npm run dev -- --skip-install
```

开发地址：

- 前端：<http://localhost:5173>
- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/v1/health>

停止开发服务时，在终端按 `Ctrl+C`。脚本会同时结束后端和前端进程。

## 2. 构建前检查

提交或打包前建议先完成以下检查：

```bash
cd frontend
npm ci
npm run type-check
npm run build

cd ../backend
python -m pytest
```

如果尚未创建后端虚拟环境，先执行：

```bash
cd backend
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

## 3. 生产环境配置

复制并修改环境变量文件：

```bash
Copy-Item backend/.env.sample backend/.env   # Windows PowerShell
# cp backend/.env.sample backend/.env        # macOS / Linux

Copy-Item frontend/.env.sample frontend/.env # Windows PowerShell
# cp frontend/.env.sample frontend/.env      # macOS / Linux
```

生产部署至少检查以下配置：

| 配置 | 要求 |
| --- | --- |
| `JWT_SECRET_KEY` | 必须替换为高强度随机值 |
| `DEEPSEEK_API_KEY` | 使用你自己的模型服务凭据 |
| `DASHSCOPE_API_KEY` | 启用 RAG Embedding 时必须配置 |
| `DATABASE_URL` | 生产建议使用 PostgreSQL |
| `ELASTICSEARCH_URL` | 生产 RAG 和长期记忆建议配置 |
| `SHORT_TERM_BACKEND` | 多进程或多实例部署建议使用 `redis` |
| `VITE_API_BASE_URL` | 同域部署通常为 `/api`；跨域部署填写完整 API 地址 |

不要把 `.env`、API Key 或数据库密码提交到 Git。

## 4. Docker Compose 单机部署

当前 Compose 编排包含 `frontend`、`backend`、`postgres`、`redis` 和 `elasticsearch`。以下流程只构建和运行本地镜像。

### 4.1 构建镜像

```bash
docker compose build backend frontend
```

也可以一次构建全部服务：

```bash
docker compose build
```

### 4.2 启动服务

```bash
docker compose up -d backend frontend
```

Compose 会根据 `depends_on` 先启动 PostgreSQL、Redis 和 Elasticsearch。

查看服务状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f backend frontend
```

验证后端健康状态：

```bash
curl -fsS http://localhost:8000/api/v1/health
```

访问入口：

- 前端：<http://localhost:5173>
- API 文档：<http://localhost:8000/docs>

### 4.3 更新部署

代码更新后执行：

```bash
git pull
docker compose build backend frontend
docker compose up -d backend frontend
```

如需清理已停止容器：

```bash
docker compose down
```

`docker compose down` 默认保留 `pg_data`、`redis_data`、`es_data` 和 `hf_cache` 卷。除非确认要清空本地数据，否则不要执行 `docker compose down -v`。

## 5. 裸机 / 虚拟机部署

如果不想使用 Docker，可以分别部署后端和前端。

### 5.1 后端启动

```bash
cd backend
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

生产环境不要使用 `--reload`。Worker 数量可以根据主机 CPU、内存和并发模型调整。

后端不应直接暴露在公网。建议使用 Nginx 或其他反向代理提供 TLS、访问控制和 `/api` 转发。

### 5.2 前端打包

```bash
cd frontend
npm ci
npm run build
```

构建产物位于：

```text
frontend/dist/
```

如果前端和后端部署在同一个域名下，构建前保持：

```env
VITE_API_BASE_URL=/api
```

如果部署到不同域名，构建前设置完整的后端地址：

```env
VITE_API_BASE_URL=https://api.example.com
```

`VITE_API_BASE_URL` 是构建期变量。修改后需要重新执行 `npm run build`。

### 5.3 Nginx 参考配置

同域部署时，可以把静态资源和 API 放在同一个域名下：

```nginx
server {
    listen 80;
    server_name example.com;

    root /usr/share/nginx/healthai;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 300s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

生产环境应为域名启用 HTTPS。

## 6. 打包产物

### Docker 镜像

执行以下命令后，镜像只保存在本机：

```bash
docker compose build backend frontend
docker compose images
```

如需把镜像复制到另一台无法访问镜像仓库的机器，可先使用 `docker compose images` 确认镜像名称，再用 `docker save` 导出：

```bash
docker save -o healthai-images.tar <backend-image> <frontend-image>
```

目标机器导入：

```bash
docker load -i healthai-images.tar
```

本流程不包含 `docker push` 或任何镜像仓库发布步骤。

### 前端静态资源

```bash
npm --prefix frontend run build
```

打包结果：

```text
frontend/dist/
```

可以将该目录部署到 Nginx、Caddy、云对象存储或 CDN。部署时需要保证 `/api` 能正确到达后端服务。

## 7. 部署检查清单

部署完成后逐项确认：

- `GET /api/v1/health` 返回 `200`。
- 前端首页可以正常打开。
- 注册、登录、退出流程正常。
- 前端请求没有跨域或 `/api` 路径错误。
- PostgreSQL、Redis、Elasticsearch 连接正常。
- `JWT_SECRET_KEY` 已替换为生产值。
- `.env` 没有提交到 Git。
- 公网环境已启用 HTTPS。
- PostgreSQL、Redis、Elasticsearch 端口没有直接暴露给公网。
- 必要的数据卷已纳入备份计划。

## 8. 常见问题

### 端口被占用

默认端口为 `5173`、`8000`、`9200`、`6379` 和 `5432`。如果端口冲突，修改 `docker-compose.yml` 中的宿主机端口映射，或停止占用端口的进程。

### 后端健康检查失败

查看日志：

```bash
docker compose logs -f backend
```

常见原因是 `.env` 缺失、数据库不可达或 Elasticsearch 未就绪。

### 前端 API 请求失败

确认 `VITE_API_BASE_URL` 配置正确：

- 同域部署使用 `/api`。
- 跨域部署使用完整 API 地址，并确保反向代理和 CORS 配置正确。
- 修改该变量后需要重新构建前端。

### Elasticsearch 启动慢

Elasticsearch 首次启动和索引初始化可能较慢。等待其健康状态通过后再访问 RAG 相关功能；如果只在无 Elasticsearch 的环境体验基础功能，应在后端配置中关闭相关依赖或接受降级行为。
