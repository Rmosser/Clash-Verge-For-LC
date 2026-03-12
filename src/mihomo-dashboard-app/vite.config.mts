import path from "node:path";
import legacy from "@vitejs/plugin-legacy";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";
import svgr from "vite-plugin-svgr";

const APP_ROOT = __dirname;
const VENDOR_ROOT = path.resolve(APP_ROOT, "./vendor/clash-verge-rev");
const VENDOR_SRC = path.resolve(VENDOR_ROOT, "src");

const resolveApp = (...parts: string[]) => path.resolve(APP_ROOT, ...parts);
const resolveVendor = (...parts: string[]) => path.resolve(VENDOR_ROOT, ...parts);

const exactAlias = (find: RegExp, replacement: string) => ({ find, replacement });

export default defineConfig({
  root: VENDOR_SRC,
  base: "./",
  publicDir: resolveApp("public"),
  server: { port: 3000 },
  plugins: [
    svgr(),
    react(),
    {
      name: "lzcapp-config-inject",
      transformIndexHtml(html) {
        return {
          html,
          tags: [
            {
              tag: "script",
              attrs: { src: "./lzcapp-config.js" },
              injectTo: "head-prepend"
            }
          ]
        };
      }
    },
    legacy({
      targets: ["edge>=109", "safari>=13"],
      renderLegacyChunks: false,
      modernPolyfills: true,
      additionalModernPolyfills: [
        "core-js/modules/es.object.has-own.js",
        "core-js/modules/web.structured-clone.js",
        resolveVendor("src/polyfills/matchMedia.js"),
        resolveVendor("src/polyfills/WeakRef.js"),
        resolveVendor("src/polyfills/RegExp.js")
      ]
    })
  ],
  build: {
    outDir: resolveApp("dist"),
    emptyOutDir: true,
    minify: "terser",
    chunkSizeWarningLimit: 4500,
    reportCompressedSize: false,
    sourcemap: false,
    cssCodeSplit: true,
    cssMinify: true,
    terserOptions: {
      compress: {
        drop_console: false,
        drop_debugger: true,
        pure_funcs: ["console.debug", "console.trace"],
        dead_code: true,
        unused: true
      },
      mangle: {
        safari10: true
      }
    }
  },
  resolve: {
    alias: [
      exactAlias(/^@tauri-apps\/api$/, resolveApp("browser/shims/tauri-api.ts")),
      exactAlias(/^@tauri-apps\/api\/app$/, resolveApp("browser/shims/tauri-api-app.ts")),
      exactAlias(/^@tauri-apps\/api\/core$/, resolveApp("browser/shims/tauri-api-core.ts")),
      exactAlias(/^@tauri-apps\/api\/event$/, resolveApp("browser/shims/tauri-api-event.ts")),
      exactAlias(/^@tauri-apps\/api\/path$/, resolveApp("browser/shims/tauri-api-path.ts")),
      exactAlias(
        /^@tauri-apps\/api\/webviewWindow$/,
        resolveApp("browser/shims/tauri-api-webviewWindow.ts")
      ),
      exactAlias(/^@tauri-apps\/api\/window$/, resolveApp("browser/shims/tauri-api-window.ts")),
      exactAlias(
        /^@tauri-apps\/plugin-clipboard-manager$/,
        resolveApp("browser/shims/tauri-plugin-clipboard-manager.ts")
      ),
      exactAlias(
        /^@tauri-apps\/plugin-dialog$/,
        resolveApp("browser/shims/tauri-plugin-dialog.ts")
      ),
      exactAlias(/^@tauri-apps\/plugin-fs$/, resolveApp("browser/shims/tauri-plugin-fs.ts")),
      exactAlias(/^@tauri-apps\/plugin-http$/, resolveApp("browser/shims/tauri-plugin-http.ts")),
      exactAlias(
        /^@tauri-apps\/plugin-process$/,
        resolveApp("browser/shims/tauri-plugin-process.ts")
      ),
      exactAlias(/^@tauri-apps\/plugin-shell$/, resolveApp("browser/shims/tauri-plugin-shell.ts")),
      exactAlias(
        /^@tauri-apps\/plugin-updater$/,
        resolveApp("browser/shims/tauri-plugin-updater.ts")
      ),
      exactAlias(
        /^tauri-plugin-mihomo-api$/,
        resolveApp("browser/shims/tauri-plugin-mihomo-api.ts")
      ),
      {
        find: "@",
        replacement: VENDOR_SRC
      },
      {
        find: "@root",
        replacement: APP_ROOT
      }
    ]
  },
  define: {
    OS_PLATFORM: "\"linux\""
  }
});
