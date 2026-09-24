export const findModuleChild = () => () => {};
export const useQuickAccessVisible = () => false;
export const Navigation = { CloseSideMenus: () => { (window as any).menuClosed = true; } };
export const call = (name: string, ...args: unknown[]) => (window as any).testRpc(name, ...args);
export const callable = (name: string) => (...args: unknown[]) => call(name, ...args);
export const toaster = { toast: (value: unknown) => { throw new Error(JSON.stringify(value)); } };
