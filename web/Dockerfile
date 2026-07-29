# ==========================================
# 前端 Dockerfile
# 构建: docker build -t udpxy-scanner-frontend .
# 运行(NGINX反代): docker run -d --name udpxy-scanner-frontend -e NGINX_BACKEND_URL=http://HOST:PORT -p 8080:80 udpxy-scanner-frontend
# 运行(JS直连):   docker run -d --name udpxy-scanner-frontend -e VITE_BACKEND_URL=http://HOST:PORT -p 8080:80 udpxy-scanner-frontend
# 国内镜像加速: docker build --build-arg BASE_REGISTRY=docker.m.daocloud.io .
# ==========================================

# 基础镜像 registry（国内用户可改为 docker.m.daocloud.io 等镜像源）
ARG BASE_REGISTRY=docker.io
FROM ${BASE_REGISTRY}/library/node:20-alpine AS builder

# 国内 npm 镜像加速（可选，覆盖默认的 npmmirror.com）
# 使用: docker build --build-arg NPM_REGISTRY=https://registry.npmjs.org .
ARG NPM_REGISTRY=https://registry.npmmirror.com

WORKDIR /app
COPY package.json package-lock.json* ./

# 核心修改：设置 npm 镜像源
RUN npm config set registry ${NPM_REGISTRY} && npm install

COPY . .
RUN npm run build

# 第二阶段需要重新声明 ARG（Docker 语法限制）
ARG BASE_REGISTRY=docker.io
FROM ${BASE_REGISTRY}/library/nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
COPY env.sh /env.sh
RUN chmod +x /env.sh

EXPOSE 80

ENTRYPOINT ["/env.sh"]
