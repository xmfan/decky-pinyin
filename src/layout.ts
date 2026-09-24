import type { Rect } from "./types";
export interface LabelSize { width: number; height: number; }
export interface Placement { left: number; top: number; width: number; height: number; }

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(value, Math.max(low, high)));
const overlap = (a: Placement, b: Placement) => Math.max(0, Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left)) *
  Math.max(0, Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top));
export const labelsOverlap = (boxes: Placement[]) => boxes.some((box, index) => boxes.slice(index + 1).some(other => overlap(box, other) > 0));

// Anchor over the original text. Search neighboring free edges only when a
// label would collide. If no layout fits, the view uses a scrollable stack.
export function placeLabels(rects: Rect[], sizes: LabelSize[], width: number, height: number): Placement[] {
  const placed: Placement[] = [];
  rects.forEach((rect, index) => {
    const size = sizes[index];
    const anchorX = clamp(rect.left * width, 4, width - size.width - 4);
    const anchorY = clamp(rect.top * height, 32, height - size.height - 4);
    const xs = [anchorX, 4, width - size.width - 4];
    const ys = [anchorY, 32, height - size.height - 4];
    for (const other of placed) {
      xs.push(other.left - size.width - 6, other.left + other.width + 6);
      ys.push(other.top - size.height - 6, other.top + other.height + 6);
    }
    const candidates = xs.flatMap(left => ys.map(top => {
      const box = { left: clamp(left, 4, width - size.width - 4), top: clamp(top, 32, height - size.height - 4), ...size };
      const collision = placed.reduce((sum, other) => sum + overlap(box, {
        left: other.left - 3, top: other.top - 3, width: other.width + 6, height: other.height + 6,
      }), 0);
      return { box, collision, distance: Math.abs(box.left - anchorX) + Math.abs(box.top - anchorY) };
    }));
    candidates.sort((a, b) => a.collision - b.collision || a.distance - b.distance);
    placed.push(candidates[0].box);
  });
  return placed;
}
