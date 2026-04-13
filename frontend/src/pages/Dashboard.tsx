import { useEffect, useState, useCallback } from 'react';
import { api } from '../api/client';
import type { DashboardStats, EmailRecord, PipelineStatus } from '../api/types';
import EmailTable from '../components/EmailTable';
import PipelineControls from '../components/PipelineControls';

const defaultPipelineStatus: PipelineStatus = {
  running: false,
  current_phase: null,
  last_run: null,
  last_result: null,
  emails_processed: 0,
};

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [emails, setEmails] = useState<EmailRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([
        api<DashboardStats>('/api/dashboard'),
        api<EmailRecord[]>('/api/emails'),
      ]);
      setStats(s);
      setEmails(e);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Poll pipeline status every 5s when running
  useEffect(() => {
    if (!stats?.pipeline_status?.running) return;
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [stats?.pipeline_status?.running, fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <svg className="animate-spin h-8 w-8 text-indigo-500" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 p-6 rounded-xl">
        <h3 className="font-semibold mb-1">Error loading dashboard</h3>
        <p className="text-sm">{error}</p>
        <button onClick={fetchData} className="mt-3 text-sm text-red-600 underline hover:no-underline">
          Retry
        </button>
      </div>
    );
  }

  const pipelineStatus = stats?.pipeline_status ?? defaultPipelineStatus;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

      {/* Stats cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard label="Total Emails" value={stats?.total_emails ?? 0} color="indigo" />
        <StatCard label="Follow-ups" value={stats?.total_followups ?? 0} color="emerald" />
        <StatCard label="Resumes" value={stats?.total_resumes ?? 0} color="amber" />
      </div>

      {/* Pipeline controls */}
      <PipelineControls status={pipelineStatus} onStatusChange={fetchData} />

      {/* Email table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Processed Emails</h2>
        </div>
        <EmailTable emails={emails} />
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colorMap: Record<string, string> = {
    indigo: 'bg-indigo-50 border-indigo-200 text-indigo-700',
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-700',
    amber: 'bg-amber-50 border-amber-200 text-amber-700',
  };

  const iconColorMap: Record<string, string> = {
    indigo: 'text-indigo-500',
    emerald: 'text-emerald-500',
    amber: 'text-amber-500',
  };

  return (
    <div className={`rounded-xl border p-5 ${colorMap[color]}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium opacity-75">{label}</p>
          <p className="text-3xl font-bold mt-1">{value}</p>
        </div>
        <div className={`text-4xl ${iconColorMap[color]} opacity-30`}>
          {color === 'indigo' && '\u2709'}
          {color === 'emerald' && '\u21A9'}
          {color === 'amber' && '\uD83D\uDCC4'}
        </div>
      </div>
    </div>
  );
}
