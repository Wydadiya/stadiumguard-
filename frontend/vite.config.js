import { defineConfig } from 'vite'
import { resolve } from 'path'
import autoprefixer from 'autoprefixer'
import cssnano from 'cssnano'

export default defineConfig({
  root: './notika/green-horizotal',

  plugins: [],

  build: {
    outDir: '../../dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(process.cwd(), 'notika/green-horizotal/index.html')
      },
      output: {
        manualChunks: {
          vendor: ['bootstrap']
        }
      }
    },
    target: 'es2022',
    minify: 'esbuild',
    sourcemap: true,
    reportCompressedSize: true
  },

  server: {
    port: 3101,
    open: true,
    cors: true,
    host: true
  },

  preview: {
    port: 4173,
    open: true,
    cors: true,
    host: true
  },

  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern-compiler'
      }
    },
    postcss: {
      plugins: [
        autoprefixer(),
        cssnano({
          preset: 'default'
        })
      ]
    }
  },

  assetsInclude: ['**/*.woff', '**/*.woff2', '**/*.ttf', '**/*.eot'],

  publicDir: 'public/img',

  base: './',

  resolve: {
    alias: {
      '@': resolve(process.cwd(), './src'),
      '@css': resolve(process.cwd(), './notika/green-horizotal/css'),
      '@js': resolve(process.cwd(), './notika/green-horizotal/js'),
      '@img': resolve(process.cwd(), './notika/green-horizotal/img')
    }
  },

  optimizeDeps: {
    include: ['bootstrap', 'dayjs'],
    exclude: []
  },

  define: {
    __APP_VERSION__: JSON.stringify('2.0.0')
  }
})
