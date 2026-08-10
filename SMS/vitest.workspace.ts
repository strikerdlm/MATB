import { defineWorkspace } from "vitest/config";

export default defineWorkspace([
  "packages/*",
  "apps/*",
  "tools/*",
  {
    test: {
      name: "integration",
      include: ["test/**/*.test.ts"],
    },
  },
]);
