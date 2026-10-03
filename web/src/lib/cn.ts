import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge conditional class names, letting later Tailwind utilities win over
 * earlier ones.
 *
 * `clsx` flattens the conditionals; `twMerge` resolves the conflict. Without the
 * second step a caller passing `className="px-2"` to a `Button` that already
 * sets `px-4` would get both in the output, and which one won would depend on CSS
 * source order rather than on the caller's intent.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}