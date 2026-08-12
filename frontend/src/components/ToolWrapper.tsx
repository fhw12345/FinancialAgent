/**
 * Tool Wrapper Component - Generic Collapsible Container
 *
 * Provides a collapsible UI pattern for displaying tool results in chat.
 * Features:
 * - Expand/collapse animation
 * - Icon customization
 * - Badge for quick status
 * - Accessible keyboard navigation
 */

import React, { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

interface ToolWrapperProps {
  /** Tool title displayed in header */
  title: string;

  /** Optional icon component to display before title */
  icon?: React.ReactNode;

  /** Optional badge text (e.g., "3 positive", "5 items") */
  badge?: string;

  /** Badge color variant */
  badgeVariant?: "default" | "success" | "warning" | "error" | "info";

  /** Content to display when expanded */
  children: React.ReactNode;

  /** Initial expanded state (default: false) */
  defaultExpanded?: boolean;

  /** Optional className for custom styling */
  className?: string;
}

function badgeColor(variant: NonNullable<ToolWrapperProps["badgeVariant"]>) {
  switch (variant) {
    case "success":
      return "bg-green-100 text-green-800";
    case "warning":
      return "bg-yellow-100 text-yellow-800";
    case "error":
      return "bg-red-100 text-red-800";
    case "info":
      return "bg-blue-100 text-blue-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
}

export const ToolWrapper: React.FC<ToolWrapperProps> = ({
  title,
  icon,
  badge,
  badgeVariant = "default",
  children,
  defaultExpanded = false,
  className = "",
}) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const toggleExpand = () => {
    setIsExpanded((prev) => !prev);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggleExpand();
    }
  };

  return (
    <div
      className={`border border-gray-200 rounded-lg overflow-hidden ${className}`}
    >
      {/* Header */}
      <button
        onClick={toggleExpand}
        onKeyDown={handleKeyDown}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-inset"
        aria-expanded={isExpanded}
        aria-label={`${isExpanded ? "Collapse" : "Expand"} ${title}`}
      >
        <div className="flex items-center space-x-2">
          {/* Icon */}
          {icon && <span className="text-gray-600">{icon}</span>}

          {/* Title */}
          <span className="font-medium text-gray-900">{title}</span>

          {/* Badge */}
          {badge && (
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${badgeColor(badgeVariant)}`}
            >
              {badge}
            </span>
          )}
        </div>

        {/* Expand/Collapse Icon */}
        <span className="text-gray-500">
          {isExpanded ? (
            <ChevronDown className="h-5 w-5" />
          ) : (
            <ChevronRight className="h-5 w-5" />
          )}
        </span>
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="px-4 py-3 bg-white border-t border-gray-200">
          {children}
        </div>
      )}
    </div>
  );
};
