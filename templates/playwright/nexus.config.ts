import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: __NEXUS_TEST_DIR__,
  outputDir: __NEXUS_OUTPUT_DIR__,
  fullyParallel: true,
  use: {
    baseURL: __NEXUS_BASE_URL__,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: __NEXUS_VIDEO__,
  },
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,
    },
  },
  projects: __NEXUS_PROJECTS__,
});
