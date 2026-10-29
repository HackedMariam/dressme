import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    strictPort: true,
    proxy: {
      // The React app calls /api/*; Vite forwards to FastAPI (no CORS needed in dev)
      // Override with BACKEND_URL=http://127.0.0.1:8001 if port 8000 is taken
      '/api': {
        target: process.env.BACKEND_URL || 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        timeout: 180000,
        ws: true, // /api/ws/live (real-time updates)
        xfwd: true, // X-Forwarded-For: the API rate-limits each browser, not the proxy
      }
    }
  },
  preview: {
    port: 3000,
  }
})
