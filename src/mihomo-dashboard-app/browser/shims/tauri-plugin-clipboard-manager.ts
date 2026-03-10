export const readText = async () => navigator.clipboard.readText();
export const writeText = async (value: string) => navigator.clipboard.writeText(value);
