import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import HttpBackend from "i18next-http-backend";

// Initialize i18next
i18n
  // Load translations from /public/locales
  .use(HttpBackend)
  // Detect user language from browser/localStorage
  .use(LanguageDetector)
  // Pass the i18n instance to react-i18next
  .use(initReactI18next)
  // Initialize configuration
  .init({
    // Default language
    fallbackLng: "en",
    // Default to Chinese for our target users
    lng: "zh-CN",

    // Namespaces configuration
    ns: [
      "common",
      "auth",
      "chat",
      "portfolio",
      "market",
      "validation",
      "insights",
    ],
    defaultNS: "common",

    // Language detection options
    detection: {
      // Order of language detection - localStorage first for user preference
      order: ["localStorage", "navigator", "htmlTag"],
      // Cache language in localStorage
      caches: ["localStorage"],
      // localStorage key
      lookupLocalStorage: "i18nextLng",
      // Check localStorage for explicit selection only
      checkWhitelist: true,
    },

    // Preload essential namespaces to avoid flash of untranslated content
    preload: ["zh-CN", "en"],

    // Backend options for loading translations
    backend: {
      loadPath: "/locales/{{lng}}/{{ns}}.json",
    },

    // React specific options
    react: {
      useSuspense: true,
    },

    // Interpolation options
    interpolation: {
      // React already escapes values
      escapeValue: false,
    },

    // Debug mode (disable in production)
    debug: import.meta.env.DEV,
  });

export default i18n;

// Export supported languages for language switcher
export const supportedLanguages = [
  { code: "zh-CN", name: "简体中文", flag: "🇨🇳" },
  { code: "en", name: "English", flag: "🇺🇸" },
] as const;

export type SupportedLanguage = (typeof supportedLanguages)[number]["code"];
