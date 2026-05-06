/**
 * Drag-to-resize column wrapper.
 *
 * Renders the column body plus a 4px drag handle on its inner edge
 * (right-edge for `side="left"`, left-edge for `side="right"`). The
 * width is persisted to localStorage under `storageKey` so it survives
 * reloads. Clamped to [minWidth, maxWidth].
 *
 * The handle escapes its parent on hover via a 3px translateX so it
 * feels grabbable without disturbing layout. While dragging, body cursor
 * is set to `col-resize` and text selection is disabled.
 */

import { useCallback, useEffect, useRef, useState } from "react";

const SIDEBAR_DRAG_HANDLE_PX = 4;

export interface ResizableColumnProps {
  side: "left" | "right";
  storageKey: string;
  defaultWidth: number;
  minWidth?: number;
  maxWidth?: number;
  className?: string;
  children: React.ReactNode;
}

function readStoredWidth(
  key: string,
  fallback: number,
  min: number,
  max: number,
): number {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw == null) return fallback;
    const n = Number(raw);
    if (!Number.isFinite(n)) return fallback;
    return Math.min(max, Math.max(min, n));
  } catch {
    return fallback;
  }
}

export function ResizableColumn({
  side,
  storageKey,
  defaultWidth,
  minWidth = 240,
  maxWidth = 720,
  className = "",
  children,
}: ResizableColumnProps) {
  const [width, setWidth] = useState<number>(() =>
    readStoredWidth(storageKey, defaultWidth, minWidth, maxWidth),
  );
  const draggingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);
  // Latest width tracked in a ref so the mouseup listener (registered on
  // mousedown) reads the current value instead of the closure snapshot.
  const widthRef = useRef(width);
  useEffect(() => {
    widthRef.current = width;
  }, [width]);

  const onMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const dx = e.clientX - startXRef.current;
      const next =
        side === "left"
          ? startWidthRef.current + dx
          : startWidthRef.current - dx;
      const clamped = Math.min(maxWidth, Math.max(minWidth, next));
      setWidth(clamped);
    },
    [side, minWidth, maxWidth],
  );

  const onMouseUp = useCallback(() => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
    try {
      window.localStorage.setItem(
        storageKey,
        String(Math.round(widthRef.current)),
      );
    } catch {
      // localStorage can throw in private mode — silently no-op
    }
  }, [onMouseMove, storageKey]);

  useEffect(() => {
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [onMouseMove, onMouseUp]);

  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    startXRef.current = e.clientX;
    startWidthRef.current = width;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  };

  // Drag handle is absolutely positioned at the inner edge of the column.
  const handleStyle: React.CSSProperties =
    side === "left"
      ? { right: -SIDEBAR_DRAG_HANDLE_PX / 2, top: 0, bottom: 0 }
      : { left: -SIDEBAR_DRAG_HANDLE_PX / 2, top: 0, bottom: 0 };

  return (
    <div
      className={`relative flex-shrink-0 ${className}`}
      style={{ width: `${width}px` }}
    >
      {children}
      <div
        role="separator"
        aria-orientation="vertical"
        onMouseDown={onMouseDown}
        className="absolute z-20 cursor-col-resize group"
        style={{ ...handleStyle, width: `${SIDEBAR_DRAG_HANDLE_PX}px` }}
      >
        <div className="h-full w-full transition-colors group-hover:bg-blue-400/60" />
      </div>
    </div>
  );
}
