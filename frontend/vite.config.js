import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // El backend solo permite CORS desde :5173 — si ese puerto está ocupado,
    // preferimos que falle claro en vez de arrancar en otro puerto en silencio
    // (eso rompe las llamadas a la API con un "Failed to fetch" sin explicación).
    strictPort: true,
  },
})
