import { useEffect } from "react";
import { Bot, MessageSquare, Microscope, Route, X } from "lucide-react";
import { useTranslation } from "react-i18next";

interface HelpModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function HelpModal({ isOpen, onClose }: HelpModalProps) {
  const { t } = useTranslation("chat");

  useEffect(() => {
    if (!isOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const flows = [
    {
      key: "assistant",
      icon: MessageSquare,
      cardClass: "border-purple-200 bg-purple-50",
      iconClass: "text-purple-600",
      titleClass: "text-purple-900",
      subtitleClass: "text-purple-700",
    },
    {
      key: "agent",
      icon: Bot,
      cardClass: "border-blue-200 bg-blue-50",
      iconClass: "text-blue-600",
      titleClass: "text-blue-900",
      subtitleClass: "text-blue-700",
    },
    {
      key: "deep",
      icon: Microscope,
      cardClass: "border-amber-200 bg-amber-50",
      iconClass: "text-amber-600",
      titleClass: "text-amber-900",
      subtitleClass: "text-amber-700",
    },
  ] as const;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <button
        type="button"
        aria-label="Close help dialog"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
      />
      <div
        className="relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-modal-title"
      >
        <div className="sticky top-0 flex items-center justify-between rounded-t-2xl bg-gradient-to-r from-blue-500 to-indigo-500 p-6 text-white">
          <div>
            <h2 id="help-modal-title" className="text-2xl font-bold">
              {t("help.title")}
            </h2>
            <p className="mt-1 text-sm text-blue-100">{t("help.subtitle")}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-white transition-colors hover:bg-white/20"
            aria-label={t("help.close")}
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        <div className="space-y-5 p-6">
          <div className="flex items-start gap-3 rounded-xl border border-indigo-200 bg-indigo-50 p-4">
            <Route className="mt-0.5 h-5 w-5 flex-shrink-0 text-indigo-600" />
            <div>
              <p className="font-semibold text-indigo-900">
                {t("help.autoRouting.title")}
              </p>
              <p className="mt-1 text-sm text-indigo-800">
                {t("help.autoRouting.description")}
              </p>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {flows.map(
              ({
                key,
                icon: Icon,
                cardClass,
                iconClass,
                titleClass,
                subtitleClass,
              }) => (
                <div key={key} className={`rounded-xl border p-4 ${cardClass}`}>
                  <Icon className={`h-6 w-6 ${iconClass}`} />
                  <h3 className={`mt-3 font-bold ${titleClass}`}>
                    {t(`help.flows.${key}.title`)}
                  </h3>
                  <p className={`mt-1 text-xs font-medium ${subtitleClass}`}>
                    {t(`help.flows.${key}.when`)}
                  </p>
                  <p className="mt-3 text-sm text-gray-700">
                    {t(`help.flows.${key}.description`)}
                  </p>
                </div>
              ),
            )}
          </div>

          <div className="rounded-xl bg-gray-50 p-4 text-sm text-gray-700">
            <p className="font-semibold">{t("help.tips.title")}</p>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>{t("help.tips.symbol")}</li>
              <li>{t("help.tips.quickTools")}</li>
              <li>{t("help.tips.transparency")}</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
