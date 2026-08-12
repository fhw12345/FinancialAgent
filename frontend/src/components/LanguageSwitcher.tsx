import { useTranslation } from "react-i18next";
import { Globe } from "lucide-react";
import { supportedLanguages, type SupportedLanguage } from "../i18n";

interface LanguageSwitcherProps {
  /** Display style variant */
  variant?: "dropdown" | "toggle" | "minimal";
  /** Additional CSS classes */
  className?: string;
}

/**
 * Language switcher component for switching between supported languages.
 * Supports dropdown, toggle, and minimal display variants.
 */
export function LanguageSwitcher({
  variant = "dropdown",
  className = "",
}: LanguageSwitcherProps) {
  const { i18n, t } = useTranslation("common");

  const currentLanguage =
    supportedLanguages.find((lang) => lang.code === i18n.language) ||
    supportedLanguages[0];

  const handleLanguageChange = (langCode: SupportedLanguage) => {
    i18n.changeLanguage(langCode);
  };

  if (variant === "minimal") {
    return (
      <button
        onClick={() => {
          // Toggle between languages
          const currentIndex = supportedLanguages.findIndex(
            (lang) => lang.code === i18n.language,
          );
          const nextIndex = (currentIndex + 1) % supportedLanguages.length;
          const nextLanguage = supportedLanguages.at(nextIndex);
          if (nextLanguage) handleLanguageChange(nextLanguage.code);
        }}
        className={`flex items-center gap-1 px-2 py-1 text-sm text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 ${className}`}
        title={t("labels.language")}
      >
        <Globe className="h-4 w-4" />
        <span>{currentLanguage.flag}</span>
      </button>
    );
  }

  if (variant === "toggle") {
    return (
      <div className={`flex items-center gap-1 ${className}`}>
        {supportedLanguages.map((lang) => (
          <button
            key={lang.code}
            onClick={() => handleLanguageChange(lang.code)}
            className={`px-2 py-1 text-sm rounded ${
              i18n.language === lang.code
                ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
            }`}
            title={lang.name}
          >
            {lang.flag}
          </button>
        ))}
      </div>
    );
  }

  // Default: dropdown variant
  return (
    <div className={`relative inline-block ${className}`}>
      <select
        value={i18n.language}
        onChange={(e) =>
          handleLanguageChange(e.target.value as SupportedLanguage)
        }
        className="appearance-none bg-transparent pl-7 pr-8 py-1.5 text-sm border border-gray-300 rounded-md cursor-pointer hover:border-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:border-gray-600 dark:hover:border-gray-500 dark:bg-gray-800 dark:text-gray-200"
        aria-label={t("labels.language")}
      >
        {supportedLanguages.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.flag} {lang.name}
          </option>
        ))}
      </select>
      <Globe className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500 pointer-events-none" />
      <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none">
        <svg
          className="h-4 w-4 text-gray-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </div>
    </div>
  );
}

export default LanguageSwitcher;
