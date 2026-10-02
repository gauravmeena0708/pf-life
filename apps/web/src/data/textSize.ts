import { useCallback, useState } from "react";

/** Larger text for those who need it (senior citizens, pensioners, low vision): the page's base size, which every
 *  rem-sized style follows. Kept in this browser; the default if storage is blocked. */
export const TEXT_SIZES = [100, 115, 130, 150] as const;
export type TextSize = (typeof TEXT_SIZES)[number];
const KEY = "epfo.text-size";

export function storedTextSize(): TextSize {
  try {
    const value = Number(window.localStorage.getItem(KEY));
    return (TEXT_SIZES as readonly number[]).includes(value) ? (value as TextSize) : 100;
  } catch { return 100; }
}

export function applyTextSize(size: TextSize): void {
  document.documentElement.style.fontSize = size === 100 ? "" : `${size}%`;
}

export function useTextSize(): [TextSize, (size: TextSize) => void] {
  const [size, setSize] = useState<TextSize>(storedTextSize);
  const choose = useCallback((next: TextSize) => {
    try { window.localStorage.setItem(KEY, String(next)); } catch { /* this page only */ }
    applyTextSize(next);
    setSize(next);
  }, []);
  return [size, choose];
}
