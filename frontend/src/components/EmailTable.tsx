import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { EmailRecord } from '../api/types';
import { API_BASE } from '../api/client';

interface EmailTableProps {
  emails: EmailRecord[];
}

type SortKey = 'subject' | 'from_email' | 'resume_file' | 'processed_at';
type SortDir = 'asc' | 'desc';

export default function EmailTable({ emails }: EmailTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('processed_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sorted = [...emails].sort((a, b) => {
    const av = a[sortKey] ?? '';
    const bv = b[sortKey] ?? '';
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === 'asc' ? cmp : -cmp;
  });

  const headerClass = 'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700 select-none';
  const arrow = (key: SortKey) => sortKey === key ? (sortDir === 'asc' ? ' \u2191' : ' \u2193') : '';

  if (emails.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        No emails processed yet. Run the pipeline to get started.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className={headerClass} onClick={() => toggleSort('subject')}>Subject{arrow('subject')}</th>
            <th className={headerClass} onClick={() => toggleSort('from_email')}>From{arrow('from_email')}</th>
            <th className={headerClass} onClick={() => toggleSort('resume_file')}>Resume{arrow('resume_file')}</th>
            <th className={headerClass} onClick={() => toggleSort('processed_at')}>Processed{arrow('processed_at')}</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {sorted.map((email) => (
            <tr key={email.message_id} className="hover:bg-gray-50 transition-colors">
              <td className="px-4 py-3 text-sm text-gray-900 max-w-xs truncate">{email.subject}</td>
              <td className="px-4 py-3 text-sm text-gray-600">{email.from_email}</td>
              <td className="px-4 py-3 text-sm">
                {email.resume_file ? (
                  <a
                    href={`${API_BASE}/api/resumes/${encodeURIComponent(email.resume_file.split(/[/\\]/).pop() || '')}/download`}
                    className="text-indigo-600 hover:text-indigo-800 font-medium"
                    title={email.resume_file}
                  >
                    {email.resume_file.split(/[/\\]/).pop()}
                  </a>
                ) : (
                  <span className="text-gray-400">--</span>
                )}
              </td>
              <td className="px-4 py-3 text-sm text-gray-500">
                {new Date(email.processed_at).toLocaleString()}
              </td>
              <td className="px-4 py-3 text-sm">
                <Link
                  to={`/emails/${encodeURIComponent(email.message_id)}`}
                  className="text-indigo-600 hover:text-indigo-800 font-medium"
                >
                  View
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
