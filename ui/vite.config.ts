import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The build output goes straight into the Python package so pip installs ship the UI.
// base './' keeps asset URLs relative, which the local static server relies on.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: { outDir: '../weekly_report/gui_static', emptyOutDir: true },
  server: { port: 5173 },
})
