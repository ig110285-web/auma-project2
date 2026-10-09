import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// В dev-режиме фронтенд работает на 5173 и проксирует /api на backend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
