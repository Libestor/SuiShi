# 开发、测试与本地启动

## 1. 环境要求

- Docker 28+
- Docker Compose 2.36+
- Node.js 22+
- `uv` 0.9+

日常完整启动只需要 Docker。前端 HMR 开发可在宿主机使用 Node.js。

## 2. 配置

```bash
cp .env.example .env
```

`.env` 中的值仅用于本机。至少应修改：

- `PLATFORM_TOKEN`
- `SESSION_SECRET`
- `RUNNER_SHARED_SECRET`
- `MYSQL_PASSWORD`
- `MYSQL_ROOT_PASSWORD`

仓库不再提供可直接使用的开发凭证。`PLATFORM_TOKEN`、`SESSION_SECRET` 和 `RUNNER_SHARED_SECRET` 必须分别填写至少 32 个字符的不同随机值；缺失、重复或使用公开示例值时，Compose 或服务会拒绝启动。可分别运行三次以下命令生成：

```bash
openssl rand -hex 32
```

Compose 网关默认开启 Nginx Basic Auth。请创建不纳入版本控制的 htpasswd 文件，并将 `.env` 中的 `BASIC_AUTH_FILE` 设置为其绝对路径。默认所有对外端口都只绑定 `127.0.0.1`。

`SESSION_SECRET` 用于签署浏览器会话，必须与 `PLATFORM_TOKEN` 不同且足够长。HTTPS 部署必须设置 `SESSION_COOKIE_SECURE=true`。

生成新凭证（macOS 自带 OpenSSL）：

```bash
printf 'your-user:' > /absolute/safe/path/investment.htpasswd
openssl passwd -apr1 >> /absolute/safe/path/investment.htpasswd
```

第二条命令会交互式提示输入密码，避免把密码写进 shell 历史。

## 3. 完整启动

```bash
docker compose up --build
```

服务：

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| Web | http://localhost:8080 | 推荐访问入口 |
| Frontend | http://localhost:3000 | 前端直连 |
| Backend | http://localhost:8000 | API 与文档 |
| Runner | http://localhost:9000 | 仅供本机后端调用的脚本执行服务 |
| MySQL | localhost:3306 | 本地数据库 |

后端首次启动会运行 Alembic 迁移并写入演示数据。后续启动不会重复创建演示记录。
通过 8080 访问时需要先通过 Basic Auth；进入应用后，登录页使用平台 Token 向后端换取签名的 `HttpOnly` Cookie。前端代码和浏览器存储都不保留 Token。

命令行客户端仍可使用 `X-Platform-Token` 访问 API；该方式不面向浏览器。

## 4. 前端开发

保持 Docker 中的 MySQL、Runner 和 Backend 运行：

```bash
docker compose up mysql runner backend
npm run dev
```

前端开发服务器会将 `/api` 代理到 `http://localhost:8000`。

### 后端与前端的宿主机模式

可用项目内 SQLite 文件在宿主机启动 API；正式 Compose 方案仍使用 MySQL。Runner 的 UID 隔离、进程回收和资源上限依赖 Linux 容器，因此不再直接在 macOS 宿主机运行。分别打开三个终端：

```bash
docker compose up --build runner
```

```bash
cd backend
uv sync --dev
set -a
source ../.env
set +a
export DATABASE_URL=sqlite:///../data/development.sqlite3
export RUNNER_URL=http://127.0.0.1:9000
export DATA_SOURCE_REPO=../data/data-sources
export SCHEDULER_ENABLED=true
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
npm run dev
```

此模式的数据写入 `data/development.sqlite3`，不会提交到 Git。切换到 MySQL 时以 MySQL 数据库为新的权威存储，不会自动导入该开发文件。

## 5. 后端依赖

后端使用 `uv`：

```bash
cd backend
uv sync --dev
```

添加后端包：

```bash
uv add package-name
```

数据源包从网页配置，Runner 使用 `uv` 按依赖集合创建独立缓存环境。

## 6. 数据库迁移与备份

创建迁移：

```bash
docker compose exec backend uv run alembic revision --autogenerate -m "describe change"
```

执行迁移前备份：

```bash
./scripts/db-backup.sh
docker compose exec backend uv run alembic upgrade head
```

备份文件写入 `backups/`，不会提交到 Git。表结构变更必须先成功生成备份。

## 7. 测试

运行后端单元与 API 测试：

```bash
docker compose run --rm backend uv run pytest
```

运行前端构建和静态渲染测试：

```bash
npm test
```

运行全部检查：

```bash
./scripts/test-all.sh
```

## 8. 常见操作

查看日志：

```bash
docker compose logs -f backend runner
```

手动保存一轮估值：

```bash
curl -X POST http://localhost:8000/api/v1/snapshots \
  -H "X-Platform-Token: ${PLATFORM_TOKEN}"
```

保存估值时会同时检查已启用的通用数值和里程碑推送规则。Webhook 响应或失败原因保存在 `notification_deliveries`，敏感 Header 不写入响应日志。

停止服务：

```bash
docker compose down
```

数据库数据保存在 Docker volume 中，`down` 不会删除。不要使用 `down -v`，除非确定要清空本地数据库。
