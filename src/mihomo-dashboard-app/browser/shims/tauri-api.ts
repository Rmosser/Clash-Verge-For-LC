import { listen } from "./tauri-api-event";

export const event = {
  once: async <T>(
    eventName: string,
    callback: (event: { payload: T }) => void
  ) => {
    const unlisten = await listen<T>(eventName, (event) => {
      unlisten();
      callback(event);
    });
  }
};
