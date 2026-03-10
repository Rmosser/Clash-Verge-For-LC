import { getRegisteredFile, readRegisteredText, resolveAppFileUrl } from "../runtime";

export const readTextFile = async (path: string) => {
  if (getRegisteredFile(path)) {
    return readRegisteredText(path);
  }
  const response = await fetch(resolveAppFileUrl(path));
  if (!response.ok) {
    throw new Error(`Failed to read file: ${path}`);
  }
  return response.text();
};

export const exists = async (path: string) => {
  if (getRegisteredFile(path)) {
    return true;
  }
  const response = await fetch(resolveAppFileUrl(path), { method: "HEAD" });
  return response.ok;
};
