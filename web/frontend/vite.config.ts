import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": "/src" } },  // shadcn/ui imports ("@/lib/utils")
  server: { port: 5173, proxy: { "/api": "http://localhost:8501" } },
});
