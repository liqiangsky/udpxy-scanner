# ==========================================
# 前端 Dockerfile — nginx 独立部署
# 构建: docker build \
#   --build-arg VITE_API_BASE=/api \
#   -t udpxy-frontend -f web/Dockerfile web/
# 运行: docker run -p 8080:80 udpxy-frontend
# ==========================================
FROM node:20-alpine AS builder

ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

# Cloudflare Pages 场景无需此 Dockerfile
# 直接在 Pages 管理面板设置环境变量 VITE_API_BASE

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]