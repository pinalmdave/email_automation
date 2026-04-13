import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { DraftEmail } from '../api/types';

export default function DraftEditor() {
  const { uid } = useParams<{ uid: string }>();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DraftEmail | null>(null);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    if (!uid) return;
    api<DraftEmail>(`/api/drafts/${encodeURIComponent(uid)}`)
      .then((d) => {
        setDraft(d);
        setSubject(d.subject);
        setBody(d.body);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [uid]);

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleSave = async () => {
    if (!uid) return;
    setSaving(true);
    try {
      await api(`/api/drafts/${encodeURIComponent(uid)}`, {
        method: 'PUT',
        body: JSON.stringify({ subject, body }),
      });
      showToast('Draft saved successfully', 'success');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to save', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleSend = async () => {
    if (!uid) return;
    if (!window.confirm('Are you sure you want to send this email?')) return;
    setSaving(true);
    try {
      await api(`/api/drafts/${encodeURIComponent(uid)}/send`, { method: 'POST' });
      showToast('Email sent successfully', 'success');
      setTimeout(() => navigate('/'), 1500);
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to send', 'error');
      setSaving(false);
    }
  };

  const handleDiscard = async () => {
    if (!uid) return;
    if (!window.confirm('Are you sure you want to discard this draft?')) return;
    setSaving(true);
    try {
      await api(`/api/drafts/${encodeURIComponent(uid)}`, { method: 'DELETE' });
      showToast('Draft discarded', 'success');
      setTimeout(() => navigate('/'), 1500);
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to discard', 'error');
      setSaving(false);
    }
  };

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

  if (error || !draft) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 p-6 rounded-xl">
        <h3 className="font-semibold mb-1">Error loading draft</h3>
        <p className="text-sm">{error ?? 'Draft not found'}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 relative">
      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium ${
            toast.type === 'success'
              ? 'bg-green-500 text-white'
              : 'bg-red-500 text-white'
          }`}
        >
          {toast.message}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="text-gray-400 hover:text-gray-600 transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
        </button>
        <h1 className="text-2xl font-bold text-gray-900">Edit Draft</h1>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">To</label>
            <div className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded-lg">{draft.to}</div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">Date</label>
            <div className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded-lg">
              {new Date(draft.date).toLocaleString()}
            </div>
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">Subject</label>
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">Body</label>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={16}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-y"
          />
        </div>

        {draft.has_attachment && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
            </svg>
            Resume attached
          </div>
        )}

        <div className="flex items-center gap-3 pt-4 border-t border-gray-100">
          <button
            onClick={handleSend}
            disabled={saving}
            className="px-5 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? 'Processing...' : 'Send'}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2.5 bg-gray-100 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Save Draft
          </button>
          <button
            onClick={handleDiscard}
            disabled={saving}
            className="px-5 py-2.5 bg-red-50 text-red-600 text-sm font-medium rounded-lg hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ml-auto"
          >
            Discard
          </button>
        </div>
      </div>
    </div>
  );
}
