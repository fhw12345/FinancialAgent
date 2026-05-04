/**
 * ExpandableText - Collapsible text block with show more/less toggle.
 *
 * Truncates text via line-clamp and shows a toggle button when the
 * content exceeds the visible area. Uses CSS line-clamp for performance.
 */

import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useTranslated } from '../../../hooks/useTranslated';

interface ExpandableTextProps {
  text: string;
  /** Maximum visible lines when collapsed. Defaults to 3. */
  maxLines?: number;
  className?: string;
}

function ExpandableTextInner({ text, maxLines = 3, className = '' }: ExpandableTextProps) {
  const { t } = useTranslation(['chat']);
  const { text: displayText, isLoading: translating } = useTranslated(text);
  const [expanded, setExpanded] = useState(false);
  const [needsTruncation, setNeedsTruncation] = useState(false);
  const textRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const el = textRef.current;
    if (el) {
      // Compare scroll height vs client height to detect overflow
      setNeedsTruncation(el.scrollHeight > el.clientHeight + 2);
    }
  }, [displayText, maxLines]);

  // Tailwind line-clamp classes (1-6 supported)
  const clampClass = expanded ? '' : `line-clamp-${maxLines}`;

  return (
    <div>
      <p
        ref={textRef}
        className={`text-xs text-gray-600 dark:text-gray-400 whitespace-pre-line leading-relaxed ${clampClass} ${className}`}
        style={translating ? { opacity: 0.7 } : undefined}
      >
        {displayText}
      </p>
      {(needsTruncation || expanded) && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="mt-0.5 text-xs text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300"
        >
          {expanded
            ? t('chat:deepAgent.showLess', { defaultValue: 'Show less' })
            : t('chat:deepAgent.showMore', { defaultValue: 'Show more' })}
        </button>
      )}
    </div>
  );
}

export const ExpandableText = React.memo(ExpandableTextInner);
