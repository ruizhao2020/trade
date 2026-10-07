FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG APP_MODE=private
# VITE_API_BASE 会被构建期内联进产物，因此**刻意不给默认值**：
# 默认成 localhost 会产出"构建成功、上线连不上后端"的镜像，且只在运行时暴露。
# 构建时必须显式声明后端地址：
#   docker build --build-arg APP_MODE=private \
#                --build-arg VITE_API_BASE=https://api.example.com/api/v1 ...
ARG VITE_API_BASE
RUN test -n "$VITE_API_BASE" || { \
      echo "错误：必须传 --build-arg VITE_API_BASE=<后端 API 地址>（会内联进产物，不能留空）" >&2; \
      exit 1; \
    }
ENV VITE_API_BASE=$VITE_API_BASE
RUN if [ "$APP_MODE" = "public" ]; then npm run build:public && cp -R dist-public dist; else npm run build:private && cp -R dist-private dist; fi

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
