import { addAppEventListener } from "../runtime";

export type Theme = "light" | "dark";

type ResizePayload = { payload: { width: number; height: number } };
type ThemePayload = { payload: Theme };

class BrowserWindowHandle {
  private decorated = true;
  private fullscreen = false;
  private themeOverride: Theme | null = null;
  private visible = true;

  async close() {
    window.close();
  }

  async minimize() {}

  async maximize() {}

  async unmaximize() {}

  async toggleMaximize() {}

  async isMaximized() {
    return false;
  }

  async setFullscreen(value: boolean) {
    this.fullscreen = value;
  }

  async isFullscreen() {
    return this.fullscreen;
  }

  async isVisible() {
    return this.visible;
  }

  async isDecorated() {
    return this.decorated;
  }

  async setDecorations(value: boolean) {
    this.decorated = value;
  }

  async setMinimizable(_value: boolean) {}

  async startResizeDragging(_direction: string) {}

  async hide() {
    this.visible = false;
  }

  async show() {
    this.visible = true;
  }

  async theme(): Promise<Theme> {
    if (this.themeOverride) return this.themeOverride;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  async setTheme(theme: Theme | null) {
    this.themeOverride = theme;
    window.__VERGE_INITIAL_THEME_MODE = theme ?? "system";
  }

  async onResized(callback: (event: ResizePayload) => void) {
    const handler = () =>
      callback({
        payload: { width: window.innerWidth, height: window.innerHeight },
      });
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }

  async onThemeChanged(callback: (event: ThemePayload) => void) {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () =>
      callback({ payload: media.matches ? "dark" : "light" });
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }

  async onFocusChanged(callback: () => void) {
    window.addEventListener("focus", callback);
    window.addEventListener("blur", callback);
    return () => {
      window.removeEventListener("focus", callback);
      window.removeEventListener("blur", callback);
    };
  }

  async listen<T>(
    eventName: string,
    callback: (event: { payload: T }) => void,
  ) {
    return addAppEventListener<T>(eventName, callback);
  }
}

const singleton = new BrowserWindowHandle();

export const getCurrentWindow = () => singleton;
