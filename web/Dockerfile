# ==========================================
# 前端 Dockerfile
# 构建: docker build -t udpxy-scanner-frontend .
# 运行(后端直连): docker run -d --name udpxy-scanner-frontend -e VITE_BACKEND_URL=http://HOST:PORT（后端服务地址） -p 8080:80 udpxy-scanner-frontend
# 运行(NGINX反代): docker run -d --name udpxy-scanner-frontend -e NGINX_BACKEND_URL=http://HOST:PORT（后端服务地址） -p 8080:80 udpxy-scanner-frontend
# ==========================================
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./

# 核心修改：设置国内淘宝镜像源（或使用腾讯云镜像源：https://mirrors.cloud.tencent.com/npm/）
RUN npm config set registry https://registry.npmmirror.com && npm install

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
COPY env.sh /env.sh
RUN chmod +x /env.sh

EXPOSE 80

ENTRYPOINT ["/env.sh"]
