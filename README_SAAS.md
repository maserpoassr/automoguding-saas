# 工学云打卡管理平台 (SaaS 版)

这是一个基于 Web 的工学云自动打卡管理系统，支持多用户管理、自动打卡、日报/周报/月报自动提交。

## 功能特性

- **Web 管理界面**：可视化管理用户和配置。
- **多用户支持**：单一系统可托管多个账号。
- **自动调度**：内置定时任务，自动在上下班时间打卡。
- **日志查看**：实时查看运行状态和日志。
- **容器化部署**：支持 Docker 一键部署。

## 部署方法

### 使用 Docker Compose (推荐)

1. 确保已安装 Docker 和 Docker Compose。
2. 在项目根目录下运行：

```bash
docker-compose up -d --build
```

3. 访问 `http://localhost:8000` 即可进入管理后台。
4. 数据将持久化保存在 `./data` 目录。

### 本地开发运行

**后端：**

```bash
cd server
pip install -r requirements.txt
# 设置 PYTHONPATH 包含项目根目录
set PYTHONPATH=%PYTHONPATH%;..
python -m uvicorn server.main:app --reload
```

**前端：**

```bash
cd web
npm install
npm run dev
```

## 使用说明

1. 打开管理页面，点击“添加用户”。
2. 输入工学云手机号和密码。
3. 配置打卡地点（经纬度）、日报周报开关等。
4. 保存后，系统会自动在每天 8:30 和 18:30 (随机偏移) 执行打卡任务。
5. 你也可以在列表中点击“立即运行”来测试配置是否正确。
