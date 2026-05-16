import { useState } from 'react';
import { Clock, RefreshCw, AlertCircle, CheckCircle } from 'lucide-react';
import { authStorage } from '../../services/authService';

// API base URL - empty string for relative URLs in production (nginx proxy)
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

/**
 * CronController - Admin-only view of the GLOBAL portfolio analysis CronJob.
 *
 * Architecture:
 * - ONE Kubernetes CronJob runs daily at 9:30 AM ET (2:30 PM UTC) for ALL users
 * - This is a system-wide scheduled job, NOT per-user
 * - Only admin users can see this component and manually trigger analysis
 * - The cronjob schedule is defined in K8s YAML (30 14 * * *)
 *
 * Features:
 * - View global cronjob schedule
 * - Manual trigger button for testing
 * - System-wide status indicator
 */
export function CronController() {
  const [isTriggering, setIsTriggering] = useState(false);
  const [triggerStatus, setTriggerStatus] = useState<{
    type: 'success' | 'error' | null;
    message: string;
  }>({ type: null, message: '' });

  const handleManualTrigger = async () => {
    setIsTriggering(true);
    setTriggerStatus({ type: null, message: '' });

    try {
      const token = authStorage.getAccessToken();
      const response = await fetch(`${API_BASE_URL}/api/admin/portfolio/trigger-analysis`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setTriggerStatus({
          type: 'success',
          message: `Analysis triggered successfully. Run ID: ${data.run_id}`,
        });
      } else {
        const error = await response.json();
        setTriggerStatus({
          type: 'error',
          message: error.detail || 'Failed to trigger analysis',
        });
      }
    } catch (error) {
      setTriggerStatus({
        type: 'error',
        message: `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`,
      });
    } finally {
      setIsTriggering(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 border border-gray-200">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <RefreshCw className="w-5 h-5 text-blue-600" />
          <h3 className="text-lg font-semibold text-gray-900">
            Portfolio Analysis CronJob (Global)
          </h3>
        </div>
        <div className="px-3 py-1 bg-green-100 text-green-800 text-xs font-semibold rounded-full">
          ACTIVE
        </div>
      </div>

      {/* Global CronJob Information */}
      <div className="space-y-4">
        {/* Schedule Display */}
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4">
          <div className="flex items-center gap-3 mb-2">
            <Clock className="w-5 h-5 text-blue-600" />
            <span className="text-sm font-medium text-gray-700">System Schedule</span>
          </div>
          <div className="text-2xl font-mono font-bold text-blue-600 tracking-wider">
            Daily at 9:30 AM ET
          </div>
          <div className="text-xs text-gray-600 mt-2">
            Kubernetes CronJob: <code className="bg-white px-1 rounded">30 14 * * *</code> (UTC)
          </div>
        </div>

        {/* Scope Information */}
        <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-5 h-5 text-yellow-700 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-yellow-900">System-Wide Job</p>
              <p className="text-xs text-yellow-800 mt-1">
                This CronJob runs portfolio analysis for <strong>ALL active users</strong> at the
                scheduled time. It is NOT per-user configurable.
              </p>
            </div>
          </div>
        </div>

        {/* Manual Trigger Section */}
        <div className="pt-4 border-t border-gray-200">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h4 className="text-sm font-semibold text-gray-900">Manual Trigger</h4>
              <p className="text-xs text-gray-500 mt-1">
                Manually trigger portfolio analysis for all active users (testing only)
              </p>
            </div>
          </div>

          <button
            onClick={handleManualTrigger}
            disabled={isTriggering}
            className={`w-full py-2 px-4 rounded-lg font-medium text-sm transition-colors ${
              isTriggering
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            {isTriggering ? (
              <span className="flex items-center justify-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin" />
                Triggering...
              </span>
            ) : (
              'Trigger Analysis Now'
            )}
          </button>

          {/* Status Messages */}
          {triggerStatus.type && (
            <div
              className={`mt-3 p-3 rounded-lg flex items-start gap-2 ${
                triggerStatus.type === 'success'
                  ? 'bg-green-50 border border-green-200'
                  : 'bg-red-50 border border-red-200'
              }`}
            >
              {triggerStatus.type === 'success' ? (
                <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              )}
              <p
                className={`text-sm ${
                  triggerStatus.type === 'success' ? 'text-green-800' : 'text-red-800'
                }`}
              >
                {triggerStatus.message}
              </p>
            </div>
          )}
        </div>

        {/* Admin Notice */}
        <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
          <p className="text-xs text-gray-600">
            <strong className="text-gray-900">Admin Only:</strong> This component is only visible
            to administrators. Regular users do not see or control the CronJob schedule.
          </p>
        </div>
      </div>
    </div>
  );
}
