/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    // The notices of every bundled package (MIT, BSD and ISC ask for them wherever the code is
    // redistributed), beside index.html; the Modal deploy refuses a build without it.
    license: { fileName: "THIRD_PARTY_LICENSES.md" },
    rolldownOptions: {
      output: {
        // three.js is loaded lazily for the GLB preview. Its scene core, its WebGL renderer and
        // its loaders are kept in separate chunks so none passes Vite's 500 kB warning.
        codeSplitting: {
          groups: [
            { name: "three-loaders", test: /node_modules[\\/]three[\\/]examples[\\/]/, priority: 1 },
            { name: "three-renderer", test: /node_modules[\\/]three[\\/]build[\\/]three\.module\.js$/, priority: 2 },
            { name: "three-core", test: /node_modules[\\/]three[\\/]build[\\/]three\.core\.js$/, priority: 3 },
          ],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.mjs"],
    setupFiles: ["./src/test-setup.ts"],
  },
});
