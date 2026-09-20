import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir:'./e2e',testMatch:'semantic-review.spec.ts',workers:1,timeout:60000,
  use:{...devices['Desktop Chrome'],baseURL:'http://127.0.0.1:3331'},
  webServer:{command:'node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3331',
    url:'http://127.0.0.1:3331/evidence',reuseExistingServer:false,
    env:{MATB_BACKEND_PORT:'8331'},timeout:60000},
});
