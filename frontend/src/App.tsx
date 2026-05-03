import { useState } from "react";
import { HelpCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EnhancedChatInterface } from "./components/EnhancedChatInterface";
import HealthPage from "./pages/HealthPage";
import InsightsPage from "./pages/InsightsPage";
import PortfolioDashboard from "./pages/PortfolioDashboard";
import HelpModal from "./components/HelpModal";
import { LanguageSwitcher } from "./components/LanguageSwitcher";

// W3b: Auth removed. App always renders as a local single-user shell.
// Default landing tab is Market Insights per the de-auth PRD.
const LOCAL_IS_ADMIN = true;

function App() {
  const { t } = useTranslation(["common", "auth"]);
  const [activeTab, setActiveTab] = useState<
    "health" | "chat" | "portfolio" | "insights"
  >("insights");
  const [isHelpModalOpen, setIsHelpModalOpen] = useState(false);

  const isAdmin = LOCAL_IS_ADMIN;

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      {/* Mobile-responsive glassmorphism header */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/70 border-b border-gray-200/50 shadow-sm">
        <div className="mx-auto px-3 sm:px-6 lg:px-8">
          {/* Mobile-first responsive layout */}
          <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center py-2 gap-2">
            {/* Logo and title */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="w-9 h-9 sm:w-11 sm:h-11 bg-gradient-to-br from-blue-500 via-indigo-500 to-purple-500 rounded-xl sm:rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/30 ring-2 ring-white/50">
                  <span className="text-xl sm:text-2xl">📊</span>
                </div>
                <div>
                  <h1 className="text-lg sm:text-xl font-bold bg-gradient-to-r from-gray-900 via-blue-900 to-indigo-900 bg-clip-text text-transparent tracking-tight">
                    Financial Agent
                  </h1>
                  <span className="text-xs font-medium text-gray-500 hidden sm:inline">
                    {t("common:app.subtitle")}
                  </span>
                </div>
              </div>
              {/* Mobile user info */}
              <div className="flex items-center gap-2 sm:hidden">
              </div>
            </div>

            {/* Navigation - stacks vertically on mobile */}
            <nav className="flex flex-wrap items-center gap-1.5 sm:gap-2">
              {isAdmin && (
                <button
                  onClick={() => setActiveTab("health")}
                  className={`px-3 sm:px-5 py-1.5 sm:py-2.5 text-xs sm:text-sm font-semibold rounded-lg sm:rounded-xl transition-all duration-200 ${
                    activeTab === "health"
                      ? "bg-gradient-to-r from-blue-500 to-indigo-500 text-white shadow-lg shadow-blue-500/30"
                      : "text-gray-700 hover:bg-gray-100/80"
                  }`}
                >
                  {t("common:navigation.health")}
                </button>
              )}
              <button
                onClick={() => setActiveTab("chat")}
                className={`px-3 sm:px-5 py-1.5 sm:py-2.5 text-xs sm:text-sm font-semibold rounded-lg sm:rounded-xl transition-all duration-200 ${
                  activeTab === "chat"
                    ? "bg-gradient-to-r from-blue-500 to-indigo-500 text-white shadow-lg shadow-blue-500/30"
                    : "text-gray-700 hover:bg-gray-100/80"
                }`}
              >
                {t("common:navigation.platform")}
              </button>
              <button
                onClick={() => setActiveTab("portfolio")}
                className={`px-3 sm:px-5 py-1.5 sm:py-2.5 text-xs sm:text-sm font-semibold rounded-lg sm:rounded-xl transition-all duration-200 ${
                  activeTab === "portfolio"
                    ? "bg-gradient-to-r from-blue-500 to-indigo-500 text-white shadow-lg shadow-blue-500/30"
                    : "text-gray-700 hover:bg-gray-100/80"
                }`}
              >
                {t("common:navigation.portfolio")}
              </button>
              <button
                onClick={() => setActiveTab("insights")}
                className={`px-3 sm:px-5 py-1.5 sm:py-2.5 text-xs sm:text-sm font-semibold rounded-lg sm:rounded-xl transition-all duration-200 ${
                  activeTab === "insights"
                    ? "bg-gradient-to-r from-blue-500 to-indigo-500 text-white shadow-lg shadow-blue-500/30"
                    : "text-gray-700 hover:bg-gray-100/80"
                }`}
              >
                {t("common:navigation.insights")}
              </button>
              {/* Desktop user info */}
              <div className="hidden sm:flex items-center gap-3 pl-4 border-l border-gray-200">
                <LanguageSwitcher variant="minimal" />
                <span className="text-sm text-gray-700">👤 Local</span>
              </div>
            </nav>
          </div>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full">
        {activeTab === "health" && isAdmin && <HealthPage />}

        {activeTab === "chat" && <EnhancedChatInterface />}

        {activeTab === "portfolio" && <PortfolioDashboard />}

        {activeTab === "insights" && <InsightsPage />}
      </main>

      <footer className="bg-white border-t">
        <div className="mx-auto py-3 px-6 lg:px-8">
          <p className="text-center text-sm text-gray-500">
            Financial Agent - {t("common:app.subtitle")}
          </p>
        </div>
      </footer>

      {/* Floating Help Button */}
      <button
        onClick={() => setIsHelpModalOpen(true)}
        className="fixed bottom-6 left-6 w-14 h-14 bg-gradient-to-r from-blue-500 to-indigo-500 text-white rounded-full shadow-lg shadow-blue-500/30 hover:shadow-xl hover:shadow-blue-500/40 hover:scale-110 transition-all duration-200 flex items-center justify-center z-40 group"
        aria-label="Open help modal"
      >
        <HelpCircle className="w-7 h-7 group-hover:rotate-12 transition-transform duration-200" />
      </button>

      {/* Help Modal */}
      <HelpModal
        isOpen={isHelpModalOpen}
        onClose={() => setIsHelpModalOpen(false)}
      />
    </div>
  );
}

export default App;
