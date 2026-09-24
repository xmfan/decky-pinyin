import type { Rect } from "./types";
export interface LabelSize { width: number; height: number; }
export interface Placement { left: number; top: number; width: number; height: number; }

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(value, Math.max(low, high)));
const gap = 4;
const sameColumn = (a: Placement, b: Placement) => a.left < b.left + b.width + gap && b.left < a.left + a.width + gap;
export const labelsOverlap = (boxes: Placement[]) => boxes.some((a, index) => boxes.slice(index + 1).some(b =>
  a.left < b.left + b.width && b.left < a.left + a.width && a.top < b.top + b.height && b.top < a.top + a.height));
const layoutFits = (boxes: Placement[], width: number, height: number) => !labelsOverlap(boxes) && boxes.every(box =>
  box.left >= 4 && box.top >= 32 && box.left + box.width <= width - 4 && box.top + box.height <= height - 4);

// Keep OCR reading order within each overlapping column. Push later rows down,
// then move the group upward if its last row reaches the bottom of the screen.
// An over-tall group stays out of bounds so pagination can split it safely.
export function placeLabels(rects: Rect[], sizes: LabelSize[], width: number, height: number): Placement[] {
  const placed = rects.map((rect, index) => ({
    left: clamp(rect.left * width, 4, width - sizes[index].width - 4),
    top: clamp(rect.top * height, 32, height - sizes[index].height - 4),
    ...sizes[index],
  }));
  for (let i = 0; i < placed.length; i++) {
    for (let j = 0; j < i; j++) if (sameColumn(placed[i], placed[j])) {
      placed[i].top = Math.max(placed[i].top, placed[j].top + placed[j].height + gap);
    }
  }
  for (let i = placed.length - 1; i >= 0; i--) {
    placed[i].top = Math.min(placed[i].top, height - placed[i].height - 4);
    for (let j = i + 1; j < placed.length; j++) if (sameColumn(placed[i], placed[j])) {
      placed[i].top = Math.min(placed[i].top, placed[j].top - placed[i].height - gap);
    }
  }
  return placed;
}

export interface LabelPage { indices: number[]; positions: Placement[]; }

// Split sequential rows only when the whole group cannot fit on screen.
export function paginateLabels(rects: Rect[], sizes: LabelSize[], width: number, height: number): LabelPage[] {
  const pages: LabelPage[] = [];
  let current: LabelPage = { indices: [], positions: [] };
  rects.forEach((_, index) => {
    const indices = [...current.indices, index];
    const positions = placeLabels(indices.map(i => rects[i]), indices.map(i => sizes[i]), width, height);
    if (current.indices.length && !layoutFits(positions, width, height)) {
      pages.push(current);
      current = { indices: [index], positions: placeLabels([rects[index]], [sizes[index]], width, height) };
    } else current = { indices, positions };
  });
  if (current.indices.length) pages.push(current);
  return pages;
}
