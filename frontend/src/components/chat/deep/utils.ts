/**
 * Shared utilities for deep agent accordion components.
 */

import type { ElementType } from 'react';
import { Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react';

/** Format milliseconds into a human-readable duration string. */
export function formatDuration(ms: number): string {
  if (ms <= 0) return '';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.round((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
}

/** Status → icon component mapping. */
export const STATUS_ICONS: Record<string, ElementType> = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
};

/** Status → text color mapping. */
export const STATUS_COLORS: Record<string, string> = {
  pending: 'text-gray-400',
  running: 'text-blue-500',
  completed: 'text-green-500',
  failed: 'text-red-500',
};

/** Status → background color mapping (for sub-agent badges). */
export const STATUS_BG: Record<string, string> = {
  pending: 'bg-gray-100 dark:bg-gray-800',
  running: 'bg-blue-50 dark:bg-blue-900/20',
  completed: 'bg-green-50 dark:bg-green-900/20',
  failed: 'bg-red-50 dark:bg-red-900/20',
};
