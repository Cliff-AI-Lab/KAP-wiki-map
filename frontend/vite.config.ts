import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify('13.0.0'),
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          graph: ['react-force-graph-2d'],
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        // V15: 8000 端口被其他服务占用，后端临时跑 8001
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
});
