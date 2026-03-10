import { addAppEventListener, dispatchAppEvent, ensureDragDropBridge } from "../runtime";

export type EventCallback<T> = (event: { payload: T }) => void;
export type UnlistenFn = () => void;

export const TauriEvent = {
  DRAG_DROP: "tauri://drag-drop"
} as const;

export const listen = async <T>(
  eventName: string,
  callback: EventCallback<T>
): Promise<UnlistenFn> => {
  ensureDragDropBridge(eventName);
  return addAppEventListener<T>(eventName, callback);
};

export const emit = async <T>(eventName: string, payload?: T) => {
  dispatchAppEvent(eventName, payload as T);
};
