import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5000,
    // Avoid accepting arbitrary Host headers in the development server.
    allowedHosts: ['localhost', '127.0.0.1'],
    proxy: {
      '/py-api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/py-api/, '')
      },
      '/bc-api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/bc-api/, '')
      }
    }
  }
})
