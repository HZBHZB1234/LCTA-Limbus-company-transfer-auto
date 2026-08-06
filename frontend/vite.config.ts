import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const currentDirectory = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  root: currentDirectory,
  base: './',
  plugins: [vue()],
  build: {
    outDir: resolve(currentDirectory, '../webui/product'),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      input: {
        main: resolve(currentDirectory, 'main.html'),
        launcher: resolve(currentDirectory, 'launcher.html'),
      },
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/shared-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
})
