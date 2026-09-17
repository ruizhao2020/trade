# SignalLayer 前端

同一个前端工程包含两个独立入口，公共指标组件、行情接口和图表渲染代码共用：

- `src/public-main.tsx`：公开受限指标站，不包含登录和私有模块依赖。
- `src/private-main.tsx`：私有完整研究工作区，需要登录和 `private.access` 权限。

## 本地启动

```bash
npm run dev:public -- --host 127.0.0.1 --port 4174
npm run dev:private -- --host 127.0.0.1 --port 4175
```

## 构建

```bash
npm run build:public   # 输出 dist-public
npm run build:private  # 输出 dist-private
```

公开站允许展示的指标、参数、详情、信号标记和缠论子功能由后端数据库控制，管理员在“系统 → 公开展示”中修改。前端展示和后端响应裁剪同时执行。
