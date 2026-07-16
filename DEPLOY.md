# AI Berkshire Docker 部署指南
# ================================

# 1. 构建镜像
# docker build -t ai-berkshire .

# 2. 本地测试
# docker run -d -p 8501:8501 --name ai-berkshire ai-berkshire

# 3. 推送到镜像仓库（选一个）

# 阿里云容器镜像服务（国内访问快）
# docker tag ai-berkshire registry.cn-hangzhou.aliyuncs.com/<namespace>/ai-berkshire:latest
# docker push registry.cn-hangzhou.aliyuncs.com/<namespace>/ai-berkshire:latest

# Docker Hub（海外）
# docker tag ai-berkshire <username>/ai-berkshire:latest
# docker push <username>/ai-berkshire:latest

# 4. 部署到平台

# Sealos (sealos.io) - 国内可用，推荐
# 登录 sealos.io → 应用管理 → 新建应用 → 填入镜像地址 → 端口 8501

# Railway (railway.app) - 海外但访问速度还行
# railway up

# 阿里云 SAE
# 在阿里云控制台选择 SAE → 创建应用 → 选择容器镜像
