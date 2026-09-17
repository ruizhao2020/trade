/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const entry = mode === 'public' ? '/src/public-main.tsx' : '/src/private-main.tsx'
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
