import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../app/web_dist',
    emptyOutDir: true,
    // Split heavy vendors into long-cached chunks so first-paint downloads
    // only what is actually needed (react/antd/echarts) and subsequent
    // navigations re-use the cache.
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.indexOf('node_modules') >= 0) {
            if (id.indexOf('echarts') >= 0) return 'echarts';
            if (id.indexOf('@ant-design') >= 0 || id.indexOf('antd') >= 0 || id.indexOf('rc-') >= 0) return 'antd';
            if (id.indexOf('@tanstack') >= 0) return 'react-query';
            if (id.indexOf('react-dom') >= 0 || id.indexOf('/react/') >= 0 || id.indexOf('scheduler') >= 0) return 'react';
            return 'vendor';
          }
        }
      }
    },
    // Drop console/debugger in production for a few extra KB.
    minify: 'esbuild',
    sourcemap: false,
    target: 'es2020',
    chunkSizeWarningLimit: 800
  },
  server: {
    proxy: {
      '/chat': 'http://127.0.0.1:8011',
      '/history': 'http://127.0.0.1:8011',
      '/health': 'http://127.0.0.1:8011',
      '/files': 'http://127.0.0.1:8011'
    }
  }
});
