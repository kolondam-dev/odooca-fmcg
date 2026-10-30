import { defineConfig } from "vitest/config";
export default defineConfig({
    test: {
        environment: "node",
        include: ["tests/*.test.ts"],
        setupFiles: ["tests/setup.ts"],
    },
    define: { __DEMO__: true, __READ_ONLY__: false },
});
