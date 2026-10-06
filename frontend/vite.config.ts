import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({ plugins: [react()], server: { proxy: { "/api": "http://127.0.0.1:8001", "/chat": "http://127.0.0.1:8001", "/images": "http://127.0.0.1:8001" } } });
