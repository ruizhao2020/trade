# SignalLayer 双入口部署

公开版和私有版前端使用同一个 Dockerfile 的不同构建参数，生成两个独立镜像：

```bash
docker build --build-arg APP_MODE=public --build-arg VITE_API_BASE=https://api.example.com/api/v1 -t ghcr.io/your-org/signal-layer-frontend:public signal-layer
docker build --build-arg APP_MODE=private --build-arg VITE_API_BASE=https://api.example.com/api/v1 -t ghcr.io/your-org/signal-layer-frontend:private signal-layer
```

两个 Deployment 可以调度到同一个 Node，但仍保持独立 Pod、Service 和发布节奏：

```bash
kubectl apply -f deploy/k8s/frontend-public.yaml
kubectl apply -f deploy/k8s/frontend-private.yaml
kubectl apply -f deploy/k8s/ingress.yaml
```

替换 Ingress 中的域名、TLS Secret 和镜像仓库。两个前端的 `VITE_API_BASE` 在构建时通过环境变量注入；后端统一部署即可。

公开构建入口是 `src/public-main.tsx`，只包含指标页面，不显示登录/注册入口；私有构建入口是 `src/private-main.tsx`，保留登录和完整工作区。后端仍执行 Token、`private.access` 和模块权限校验，不能把 URL 隐蔽性当作安全边界。
