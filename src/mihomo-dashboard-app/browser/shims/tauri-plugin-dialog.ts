import { basename, registerFiles } from "../runtime";

type DialogFilter = {
  name?: string;
  extensions?: string[];
};

type OpenOptions = {
  directory?: boolean;
  multiple?: boolean;
  filters?: DialogFilter[];
};

type SaveOptions = {
  defaultPath?: string;
};

const buildAccept = (filters: DialogFilter[] | undefined) =>
  (filters ?? [])
    .flatMap((filter) => filter.extensions ?? [])
    .map((extension) => `.${extension}`)
    .join(",");

export const open = async (options?: OpenOptions) =>
  new Promise<string | string[] | null>((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = Boolean(options?.multiple);
    if (options?.directory) {
      input.setAttribute("webkitdirectory", "true");
    }
    const accept = buildAccept(options?.filters);
    if (accept) {
      input.accept = accept;
    }
    input.style.display = "none";
    document.body.appendChild(input);
    input.addEventListener(
      "change",
      () => {
        const files = input.files;
        input.remove();
        if (!files?.length) {
          resolve(null);
          return;
        }
        const tokens = registerFiles(files);
        resolve(options?.multiple ? tokens : tokens[0] ?? null);
      },
      { once: true }
    );
    input.click();
  });

export const save = async (options?: SaveOptions) =>
  options?.defaultPath ? basename(options.defaultPath) : "download";
