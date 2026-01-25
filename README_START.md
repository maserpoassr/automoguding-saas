# 项目启动指南（新手版）

本项目包含：

- 后端：FastAPI（Python），默认端口 `8000`
- 前端：Vue 3 + Vite，默认端口 `5173`
- 数据库：SQLite（默认 `database.db`，可通过环境变量修改）

本文档按“零基础新人也能照做”的方式写。

---

## 1. 你需要先安装什么

### Windows 必备

1. **Python 3.10+**（建议 3.11）
2. **Node.js 18+**（建议 20 LTS）
3. **Git**（可选，但推荐）

安装好后，打开 PowerShell，分别执行：

```powershell
python --version
node --version
npm --version
```

能看到版本号即可。

---

## 2. 获取项目代码

把项目放到一个你有写权限的目录。

---

## 3. 后端启动（FastAPI）

### 3.1 创建虚拟环境（第一次必须做）

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
```

### 3.2 安装后端依赖

```powershell
.\.venv\Scripts\pip install -r server\requirements.txt
```

### 3.3 启动后端

在项目根目录执行：

```powershell
$env:DB_PATH="database.db"
$env:GEOCODE_PROVIDER="osm"
.\.venv\Scripts\python -m uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
```

启动成功后你会看到类似输出：

- `Uvicorn running on http://0.0.0.0:8000`

打开浏览器验证：

- 后端接口文档（Swagger）：`http://localhost:8000/docs`
- OpenAPI JSON：`http://localhost:8000/openapi.json`

### 3.4 常用环境变量说明

- `DB_PATH`：SQLite 数据库文件路径（默认 `database.db`）
- `GEOCODE_PROVIDER`：地理编码提供商（默认 `osm`）
- `AMAP_KEY`：如果你想用高德地理编码，设置 `GEOCODE_PROVIDER=amap` 并配置该 key
- `ADMIN_USERNAME` / `ADMIN_PASSWORD`：管理员登录账号密码（生产环境必须设置）

---

## 4. 前端启动（Vue + Vite）

### 4.1 安装依赖

进入 `web` 目录执行：

```powershell
cd web
npm install
```

### 4.2 启动前端

```powershell
npm run dev
```

启动成功后你会看到类似输出：

- `Local: http://localhost:5173/`

打开浏览器：

- `http://localhost:5173/`

---

## 5. 登录后台（管理员）

当前版本仅保留管理员账号登录。

默认开发环境管理员（若未通过环境变量覆盖）：

- 用户名：`admin`
- 密码：`admin123456`

上线/部署时请务必通过环境变量修改默认密码：

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

---

## 6. 最常见问题（新人必看）

### 6.1 端口被占用

- 后端端口：8000
- 前端端口：5173

如果提示端口占用，先关闭占用该端口的程序，再重启。

### 6.2 前端能打开但接口报错

确认后端也在跑，并能打开：

- `http://localhost:8000/docs`

### 6.3 “账号地址填充 / 地理搜索”不可用

- 若你在内网/受限网络下，OSM 可能不稳定
- 你可以配置高德地理编码：
  - 设置 `GEOCODE_PROVIDER=amap`
  - 并配置 `AMAP_KEY`

---

## 7. 一键启动（建议）

新手最推荐：开两个 PowerShell 窗口。

### 窗口 A：后端

```powershell
cd "<你的项目目录>"
$env:DB_PATH="database.db"
$env:GEOCODE_PROVIDER="osm"
.\.venv\Scripts\python -m uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
```

### 窗口 B：前端

```powershell
cd "<你的项目目录>\web"
npm install
npm run dev
```

---

## 8. Docker 启动（可用于部署）

### 8.1 使用 Docker Compose 启动（推荐）

在项目根目录执行：

```powershell
docker compose up -d --build
```

访问：

- `http://localhost:8000/`（生产风格：前端静态文件由后端托管）

### 8.2 修改管理员账号（强烈建议）

你可以在运行前设置环境变量，或在同级目录新建 `.env` 文件（Docker Compose 会自动读取）：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请改成强密码
GEOCODE_PROVIDER=osm
```

### 8.3 镜像构建说明（GitHub Actions）

仓库已配置构建并推送到 GHCR：

- `ghcr.io/<owner>/<repo>:latest`（main 分支）
- `ghcr.io/<owner>/<repo>:sha-...`（每次提交）
- `ghcr.io/<owner>/<repo>:vX.Y.Z`（打 tag 时）

---
