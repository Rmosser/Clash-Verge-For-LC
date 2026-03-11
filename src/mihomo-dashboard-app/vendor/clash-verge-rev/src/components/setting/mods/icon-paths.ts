export const buildTrayIconFileNames = (name: string, updateTime?: string) => {
  if (updateTime) {
    return [`${name}-${updateTime}.ico`, `${name}-${updateTime}.png`];
  }

  return [`${name}.ico`, `${name}.png`];
};
