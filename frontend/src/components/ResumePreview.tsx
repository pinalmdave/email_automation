import { useEffect, useState } from 'react';

interface ResumePreviewProps {
  filename: string;
}

export default function ResumePreview({ filename }: ResumePreviewProps) {
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/api/resumes/${encodeURIComponent(filename)}/preview`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Failed to load preview: ${res.status}`);
        const data = await res.json();
        setText(data.text ?? data.content ?? JSON.stringify(data));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [filename]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-gray-400">
        <svg className="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
        Loading preview...
      </div>
    );
  }

  if (error) {
    return <div className="bg-red-50 text-red-700 p-4 rounded-lg text-sm">{error}</div>;
  }

  return (
    <pre className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm text-gray-800 whitespace-pre-wrap max-h-96 overflow-y-auto">
      {text}
    </pre>
  );
}
