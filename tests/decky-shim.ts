import { createElement as h } from "react";
export const findModuleChild = () => () => {};
export const useQuickAccessVisible = () => false;
export const Navigation = { CloseSideMenus: () => { (window as any).menuClosed = true; } };
export const call = (name: string, ...args: unknown[]) => (window as any).testRpc(name, ...args);
export const callable = (name: string) => (...args: unknown[]) => call(name, ...args);
export const toaster = { toast: (value: unknown) => { throw new Error(JSON.stringify(value)); } };

export const PanelSection = ({title,children}: any) => h("section", {}, h("h3", {}, title), children);
export const PanelSectionRow = ({children}: any) => h("div", {}, children);
export const ButtonItem = ({children,onClick,disabled}: any) => h("button", {onClick,disabled}, children);
export const ToggleField = ({label,checked,onChange,disabled}: any) => h("label", {}, label, h("input", {type:"checkbox",checked,disabled,onChange:(e:any)=>onChange(e.target.checked)}));
export const DropdownItem = ({label,selectedOption,rgOptions,onChange,disabled}: any) => h("label", {}, label, h("select", {value:selectedOption,disabled,onChange:(e:any)=>onChange(rgOptions.find((o:any)=>String(o.data)===e.target.value))}, rgOptions.map((o:any)=>h("option",{key:o.data,value:o.data},o.label))));
export const SliderField = ({label,value,min,max,step,onChange}: any) => h("label", {}, label,h("input",{type:"range",value,min,max,step,onChange:(e:any)=>onChange(Number(e.target.value))}));
