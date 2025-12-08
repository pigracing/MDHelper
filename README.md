# Markdown 图片迁移工具 (Docker 版)

这是一个基于 Flask 的 Web 应用，旨在帮助用户一键迁移 Markdown 文件中的网络图片。它会自动下载 Markdown 内引用的图片，并将其上传到指定的图床（Cloud 模式）或保存在本地服务器（Local 模式），最后生成链接替换好的新 Markdown 文件。

## ✨ 功能特性

*   **双模式支持**：支持对接第三方图床 API (Cloud) 或本地存储 (Local)。
*   **智能检索**：Web 界面支持按文件名模糊搜索历史记录。
*   **API 支持**：提供 REST API 接口，支持脚本化调用。
*   **鉴权机制**：Web 访问与 API 调用均受 Token 保护。
*   **文件去重**：同名文件自动覆盖旧版本，节省空间。
*   **现代化 UI**：基于 Tailwind CSS 的时尚界面，支持拖拽上传。

## 🐳 快速部署

### 前置条件
*   已安装 Docker 和 Docker Compose。

### 方式一：使用 Docker Compose (推荐)

1.  **准备文件**：确保目录中有 `app.py`, `Dockerfile`, `requirements.txt`, `docker-compose.yml`。
2.  **修改配置**：打开 `docker-compose.yml`，根据需求修改环境变量。
3.  **启动服务**：

    ```bash
    docker-compose up -d --build
    ```

4.  **访问应用**：浏览器打开 `http://localhost:7860` (或服务器 IP:7860)。

### 方式二：手动构建运行

1.  **构建镜像**：
    ```bash
    docker build -t md-migrator .
    ```

2.  **运行容器** (示例)：
    ```bash
    docker run -d -p 7860:7860 \
      -e PORT=7860 \
      -e APP_TOKEN="my_secret" \
      -e STORAGE_MODE="cloud" \
      -e UPLOAD_API_URL="https://api.example.com/upload" \
      -e AUTH_CODE="my_auth_code" \
      -v $(pwd)/data/temp_md:/app/static/temp_md \
      --name md-migrator \
      md-migrator
    ```

## ⚙️ 环境变量配置

| 变量名 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `PORT` | `7860` | 应用监听端口 |
| `APP_TOKEN` | `admin123` | **重要**：Web 登录密码及 API 调用的 Bearer Token |
| `STORAGE_MODE` | `cloud` | `cloud`: 上传到远程图床 API<br>`local`: 保存在本机 `static/uploads` |
| `UPLOAD_API_URL`| - | (Cloud模式) 图床上传接口地址 |
| `AUTH_CODE` | - | (Cloud模式) 图床鉴权码 |
| `SITE_DOMAIN` | `http://127.0.0.1:7860` | (Local模式) 图片和下载链接的前缀域名，需包含端口 |
| `FLASK_SECRET_KEY`| 随机值 | Flask Session 加密密钥，建议生产环境固定设置 |

## 📂 目录挂载说明

为了防止容器重启后数据丢失，建议挂载以下目录：

*   `/app/static/temp_md`: 存放处理完成的 Markdown 文件。
*   `/app/static/uploads`: (仅 Local 模式需要) 存放下载下来的图片文件。

## 🖥️ 使用指南

### 1. Web 界面使用
1.  打开网页 `http://localhost:7860`。
2.  输入 `APP_TOKEN` 进行登录。
3.  将 `.md` 文件拖入上传区域，点击“开始处理”。
4.  处理完成后，可直接下载，或在下方“历史文件列表”中搜索并下载。

### 2. API 调用示例

**上传处理文件：**

```bash
curl --location --request POST 'http://127.0.0.1:7860/api/process' \
--header 'Authorization: Bearer admin123' \
--form 'file=@"/path/to/your/article.md"'
```

**获取历史文件列表：**

```bash
curl --location --request GET 'http://127.0.0.1:7860/api/history' \
--header 'Authorization: Bearer admin123'
```

**下载指定文件：**

```bash
# 浏览器直接访问
http://127.0.0.1:7860/api/download/article.md?token=admin123
```