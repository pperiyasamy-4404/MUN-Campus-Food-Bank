import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Pass every /api request on to FastAPI. The browser then sees one
    // address for both halves, so the login cookie works and no CORS is needed.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
