import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  use: { baseURL: process.env.BASE_URL || 'http://localhost:8000', viewport: { width: 1400, height: 1000 } },
  reporter: 'list',
})
