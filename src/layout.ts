import type { Rect } from "./types";
export interface LabelSize { width: number; height: number; }
export interface Placement { left: number; top: number; width: number; height: number; }

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(value, Math.max(low, high)));
const overlap = (a: Placement, b: Placement) => Math.max(0, Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left)) *
  Math.max(0, Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top));

// Prefer just above or below each detected line, then the nearest free vertical
// slot. Coordinates are in the displayed screenshot, including letterboxing.
export function placeLabels(rects: Rect[], sizes: LabelSize[], width: number, height: number): Placement[] {
  const placed: Placement[] = [];
  rects.forEach((rect, index) => {
    const size = sizes[index];
    const left = clamp((rect.left + rect.right) * width / 2 - size.width / 2, 4, width - size.width - 4);
    const above = rect.top * height - size.height - 4;
    const below = rect.bottom * height + 4;
    const candidates = [above, below];
    for (let step = 1; step <= rects.length; step++) {
      candidates.push(above - step * (size.height + 4), below + step * (size.height + 4));
    }
    const scored = candidates.map((top, rank) => {
      const box = { left, top: clamp(top, 1, height - size.height - 1), ...size };
      const collision = placed.reduce((sum, other) => sum + overlap(box, { left: other.left - 3, top: other.top - 3, width: other.width + 6, height: other.height + 6 }), 0);
      const coveredText = rects.reduce((sum, source) => sum + overlap(box, {
        left: source.left * width, top: source.top * height,
        width: (source.right - source.left) * width, height: (source.bottom - source.top) * height,
      }), 0);
      return { box, score: collision * 1000 + coveredText * 100 + Math.abs(box.top - above) + rank / 100 };
    });
    scored.sort((a, b) => a.score - b.score);
    placed.push(scored[0].box);
  });
  return placed;
}
