import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    build: {
        outDir: '../app/web_dist',
        emptyOutDir: true
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
