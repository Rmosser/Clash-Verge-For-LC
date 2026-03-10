export const join = async (...segments: string[]) =>
  segments
    .filter(Boolean)
    .join("/")
    .replace(/\/+/g, "/");
