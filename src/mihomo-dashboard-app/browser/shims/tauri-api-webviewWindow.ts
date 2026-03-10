import { getCurrentWindow } from "./tauri-api-window";

export type WebviewWindow = ReturnType<typeof getCurrentWindow>;

export const getCurrentWebviewWindow = () => getCurrentWindow();
