export type DownloadEvent =
  | { event: "Started"; data: { contentLength?: number } }
  | { event: "Progress"; data: { chunkLength: number; contentLength?: number } }
  | { event: "Finished" };

export type Update = {
  version: string;
  body: string;
  date: string;
  available: boolean;
  rawJson?: Record<string, unknown>;
  downloadAndInstall: (onEvent?: (event: DownloadEvent) => void) => Promise<void>;
  close: () => Promise<void>;
};

export type CheckOptions = {
  allowDowngrades?: boolean;
};

export const check = async (_options?: CheckOptions): Promise<Update | null> => null;
