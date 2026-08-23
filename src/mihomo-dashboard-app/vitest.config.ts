import { defineConfig, mergeConfig } from 'vitest/config'

import viteConfig from './vite.config.mts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    root: __dirname,
    test: {
      environment: 'node',
      include: [
        'browser/**/*.test.ts',
        'tests/**/*.test.ts',
        'vendor/clash-verge-rev/src/**/*.test.{ts,tsx}',
      ],
    },
  }),
)
