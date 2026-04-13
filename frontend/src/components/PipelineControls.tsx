import { useState } from 'react';
import { api } from '../api/client';
import type { PipelineStatus } from '../api/types';
import StatusBadge from './StatusBadge';

interface PipelineControlsProps {
  status: PipelineStatus;
  onStatusChange: () => void;
}

export default function PipelineControls({ status, onStatusChange }: PipelineControlsProps) {
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runPhase = async (phase: string) => {
    setActionLoading(phase);
    setError(null);
    try {
      await api(`/api/pipeline/run`, {
        method: 'POST',
        body: JSON.stringify({ phase }),
      });
      onStatusChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start pipeline');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Pipeline Controls</h2>
        <div className="flex items-center gap-2">
          {status.running ? (
            <>
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-indigo-500"></span>
              </span>
              <StatusBadge label={status.current_phase ?? 'Running'} variant="blue" />
            </>
          ) : (
            <StatusBadge label="Idle" variant="gray" />
          )}
        </div>
      </div>

      <div className="flex gap-3 mb-4">
        <button
          onClick={() => runPhase('phase1')}
          disabled={status.running || actionLoading !== null}
          className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {actionLoading === 'phase1' ? 'Starting...' : 'Run Phase 1'}
        </button>
        <button
          onClick={() => runPhase('phase2')}
          disabled={status.running || actionLoading !== null}
          className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {actionLoading === 'phase2' ? 'Starting...' : 'Run Phase 2'}
        </button>
        <button
          onClick={() => runPhase('all')}
          disabled={status.running || actionLoading !== null}
          className="px-4 py-2 bg-indigo-800 text-white text-sm font-medium rounded-lg hover:bg-indigo-900 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {actionLoading === 'all' ? 'Starting...' : 'Run All'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 text-sm p-3 rounded-lg mb-3">{error}</div>
      )}

      <div className="grid grid-cols-3 gap-4 text-sm text-gray-600">
        <div>
          <span className="font-medium text-gray-500">Last run:</span>{' '}
          {status.last_run ? new Date(status.last_run).toLocaleString() : 'Never'}
        </div>
        <div>
          <span className="font-medium text-gray-500">Result:</span>{' '}
          {status.last_result ?? 'N/A'}
        </div>
        <div>
          <span className="font-medium text-gray-500">Emails processed:</span>{' '}
          {status.emails_processed}
        </div>
      </div>
    </div>
  );
}
