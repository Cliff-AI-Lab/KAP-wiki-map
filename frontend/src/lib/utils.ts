import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** shadcn/ui 风：合并 Tailwind 类，自动去重冲突 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
