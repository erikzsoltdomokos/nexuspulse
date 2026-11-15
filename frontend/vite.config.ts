import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Dev server binds to loopback only and proxies API calls to the Python backend.
// `--mode static` (npm run build:static) builds the GitHub Pages demo served under /nexuspulse/.
export default defineConfig(({ mode }) => ({
  base: mode === 'static' ? '/nexuspulse/' : '/',
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
  },
  build: {
    // The ECharts chunk (~585 kB, ~194 kB gzip) is expected and split out below.
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        // Keep ECharts in its own cacheable chunk.
        manualChunks: { echarts: ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'] },
      },
    },
  },
}));
