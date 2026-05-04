/**
 * Portfolio Settings Panel — required cash + risk + max position %.
 *
 * GET /api/admin/portfolio/settings to load
 * PUT /api/admin/portfolio/settings to save (all 3 fields required → 422 if missing)
 *
 * Until all three fields are saved, the parent disables the analysis buttons.
 */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, AlertCircle, CheckCircle } from "lucide-react";
import { apiClient } from "../../services/api";

export interface PortfolioSettings {
  cash_balance: number;
  risk_tolerance: "conservative" | "moderate" | "aggressive";
  max_position_pct: number;
}

const SETTINGS_PATH = "/api/admin/portfolio/settings";

async function fetchSettings(): Promise<PortfolioSettings | null> {
  const { data } = await apiClient.get<PortfolioSettings | null>(SETTINGS_PATH);
  return data;
}

async function saveSettings(s: PortfolioSettings): Promise<PortfolioSettings> {
  const { data } = await apiClient.put<PortfolioSettings>(SETTINGS_PATH, s);
  return data;
}

export function usePortfolioSettings() {
  return useQuery({
    queryKey: ["portfolio-settings"],
    queryFn: fetchSettings,
    staleTime: 60_000,
  });
}

interface Props {
  onSaved?: (s: PortfolioSettings) => void;
}

export function SettingsPanel({ onSaved }: Props) {
  const qc = useQueryClient();
  const { data, isLoading } = usePortfolioSettings();
  const [cash, setCash] = useState<string>("");
  const [risk, setRisk] = useState<PortfolioSettings["risk_tolerance"] | "">(
    "",
  );
  const [maxPos, setMaxPos] = useState<number>(15);
  const [touched, setTouched] = useState(false);

  // Hydrate from server
  useEffect(() => {
    if (data) {
      setCash(String(data.cash_balance));
      setRisk(data.risk_tolerance);
      setMaxPos(data.max_position_pct);
    }
  }, [data]);

  const cashNum = Number(cash);
  const cashValid = cash !== "" && Number.isFinite(cashNum) && cashNum > 0;
  const riskValid = risk !== "";
  const maxPosValid = maxPos >= 5 && maxPos <= 30;
  const allValid = cashValid && riskValid && maxPosValid;

  const mut = useMutation({
    mutationFn: saveSettings,
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["portfolio-settings"] });
      onSaved?.(s);
    },
  });

  const handleSave = () => {
    setTouched(true);
    if (!allValid || !risk) return;
    mut.mutate({
      cash_balance: cashNum,
      risk_tolerance: risk,
      max_position_pct: maxPos,
    });
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900">
          Portfolio Settings
          <span className="ml-2 text-xs font-normal text-gray-500">
            (required for analysis)
          </span>
        </h3>
        {data && !mut.isPending && (
          <span className="inline-flex items-center gap-1 text-xs text-green-700">
            <CheckCircle className="h-3 w-3" />
            Saved
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="text-sm text-gray-500">Loading…</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Cash to Deploy ($)
            </label>
            <input
              type="number"
              step="100"
              min="1"
              placeholder="10000"
              value={cash}
              onChange={(e) => setCash(e.target.value)}
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            />
            {touched && !cashValid && (
              <p className="mt-1 text-xs text-red-600">Enter a positive number</p>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Risk Tolerance
            </label>
            <select
              value={risk}
              onChange={(e) =>
                setRisk(e.target.value as PortfolioSettings["risk_tolerance"])
              }
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="">— select —</option>
              <option value="conservative">Conservative</option>
              <option value="moderate">Moderate</option>
              <option value="aggressive">Aggressive</option>
            </select>
            {touched && !riskValid && (
              <p className="mt-1 text-xs text-red-600">Pick one</p>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Max Single Position: {maxPos}%
            </label>
            <input
              type="range"
              min="5"
              max="30"
              step="1"
              value={maxPos}
              onChange={(e) => setMaxPos(Number(e.target.value))}
              className="w-full accent-blue-600"
            />
          </div>

          <div className="flex flex-col items-stretch">
            <button
              onClick={handleSave}
              disabled={mut.isPending || (touched && !allValid)}
              className="inline-flex items-center justify-center gap-1 rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-blue-300"
            >
              <Save className="h-4 w-4" />
              {mut.isPending ? "Saving…" : "Save Settings"}
            </button>
            {mut.error && (
              <p className="mt-1 text-xs text-red-600 inline-flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                {(mut.error as Error).message}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
