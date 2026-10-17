import { clsx, type ClassValue } from "clsx";

/** Class joiner. Tailwind v4 utilities don't collide in practice at this size; add tailwind-merge if they start to. */
export const cn = (...inputs: ClassValue[]) => clsx(inputs);
