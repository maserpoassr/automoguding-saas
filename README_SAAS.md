# 工学云打卡管理平台 (SaaS 版)

这是一个基于 Web 的工学云自动打卡管理系统，支持多用户管理、自动打卡、日报/周报/月报自动提交。

## 快速开始（新手）

请阅读更详细的启动说明：[README_START.md](./README_START.md)

## 功能特性

- **Web 管理界面**：可视化管理用户和配置。
- **多用户支持**：单一系统可托管多个账号。
- **自动调度**：内置定时任务，自动在上下班时间打卡。
- **自动报告**：支持日报/周报/月报自动提交。
- **AI 功能**：支持使用大模型生成报告内容。

## 技术栈

- 后端：FastAPI + SQLModel + SQLite
- 前端：Vue 3 + Vite + Element Plus
- 容器：Docker

## 目录结构

- `server/`：后端服务
- `web/`：前端项目
- `data/`：运行时数据目录（SQLite、图片等）

## 启动

- 本地开发：见 [README_START.md](./README_START.md)
- Docker 部署：见 [README_START.md](./README_START.md)
