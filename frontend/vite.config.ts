import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * Vite 配置（Phase 3b 前端网页 Demo）。
 *
 * - dev server 端口 5173；/api 与 /health 代理到 http://127.0.0.1:8000（FastAPI 后端）；
 * - manualChunks 将 3dmol 与 echarts 分开分包，避免主包过大；
 * - 16GB 内存约束：Viewer3D / RadarChart 通过 React.lazy 懒加载（见 App.tsx）。
 */
const BACKEND_URL = 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: BACKEND_URL, changeOrigin: true },
      '/health': { target: BACKEND_URL, changeOrigin: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-3dmol': ['3dmol'],
          'vendor-echarts': ['echarts'],
        },
      },
    },
  },
});
