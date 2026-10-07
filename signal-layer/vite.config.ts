/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode, command }) => {
  const entry = mode === 'public' ? '/src/public-main.tsx' : '/src/private-main.tsx'
  // VITE_API_BASE 会被内联进产物。构建时若没传，产物会指向 localhost:8000，
  // 上线后表现为"页面能打开但任何数据都拿不到"——这个坑只在运行时暴露。
  // 这里只告警不阻断（本地与 CI 的普通构建不应因此失败）。
  if (command === 'build' && !process.env.VITE_API_BASE) {
    console.warn(
      '\n[signal-layer] 警告：构建时未设置 VITE_API_BASE，产物将使用默认的 http://localhost:8000/api/v1。\n'
      + '            若要产出可部署的包，请显式传入，例如：\n'
      + '            VITE_API_BASE=https://api.example.com/api/v1 npm run build:private\n',
    )
  }
  return {
  plugins: [
    tailwindcss(), react(),
    { name: 'signal-layer-entry', transformIndexHtml: { order: 'pre', handler: (html: string) => html.replace('/src/main.tsx', entry) } },
  ],
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  server: {
    proxy: {
      // 把前端 /api 请求转发到后端 FastAPI (默认 8000 端口)
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: './src/testing/setup.ts',
    css: true,
  },
  }
})
