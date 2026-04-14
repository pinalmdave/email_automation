import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, API_BASE } from '../api/client';
import type { EmailRecord } from '../api/types';
import ResumePreview from '../components/ResumePreview';

export default function EmailDetail() {
  const { id } = useParams<{ id: string }>();
  const [email, setEmail] = useState<EmailRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api<EmailRecord>(`/api/emails/${encodeURIComponent(id)}`)
      .then(setEmail)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

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

  if (error || !email) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 p-6 rounded-xl">
        <h3 className="font-semibold mb-1">Error loading email</h3>
        <p className="text-sm">{error ?? 'Email not found'}</p>
        <Link to="/" className="mt-3 inline-block text-sm text-red-600 underline hover:no-underline">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-gray-400 hover:text-gray-600 transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">Email Detail</h1>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Subject" value={email.subject} />
          <Field label="From" value={email.from_email} />
          <Field label="Message ID" value={email.message_id} />
          <Field label="Processed At" value={new Date(email.processed_at).toLocaleString()} />
        </div>

        {email.resume_file && (
          <div className="pt-4 border-t border-gray-100">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-gray-900">Resume: {email.resume_file}</h3>
              <div className="flex gap-2">
                <a
                  href={`${API_BASE}/api/resumes/${encodeURIComponent(email.resume_file)}/download`}
                  className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                >
                  Download Resume
                </a>
                <Link
                  to={`/drafts/${encodeURIComponent(email.message_id)}/edit`}
                  className="px-4 py-2 bg-gray-100 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-200 transition-colors"
                >
                  Edit Draft
                </Link>
              </div>
            </div>
            <ResumePreview filename={email.resume_file.split(/[/\\]/).pop() || email.resume_file} />
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</dt>
      <dd className="mt-1 text-sm text-gray-900">{value}</dd>
    </div>
  );
}
