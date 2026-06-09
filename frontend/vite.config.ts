import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// envDir: '..' so Vite reads VITE_* vars from the repo-root .env (where
// VITE_API_URL lives), not just the frontend/ folder.
export default defineConfig({
  plugins: [react()],
  envDir: '..',
  server: { port: 3002 },
})
