import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api/client';
import type { Conversation, ConversationDetail } from '../api/types';
import StatusBadge from '../components/StatusBadge';

export default function ConversationView() {
  const { email } = useParams<{ email: string }>();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEmail, setSelectedEmail] = useState<string | null>(email ?? null);

  useEffect(() => {
    api<Conversation[]>('/api/conversations')
      .then(setConversations)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedEmail) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    api<ConversationDetail>(`/api/conversations/${encodeURIComponent(selectedEmail)}`)
      .then(setDetail)
      .catch((err) => setError(err.message))
      .finally(() => setDetailLoading(false));
  }, [selectedEmail]);

  // If navigated directly with email param
  useEffect(() => {
    if (email) setSelectedEmail(email);
  }, [email]);

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

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Conversations</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-xl text-sm">{error}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Conversation list */}
        <div className="lg:col-span-1 bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="text-sm font-semibold text-gray-700">Recruiters</h2>
          </div>
          <div className="divide-y divide-gray-100 max-h-[calc(100vh-16rem)] overflow-y-auto">
            {conversations.length === 0 ? (
              <div className="p-6 text-center text-gray-400 text-sm">No conversations yet</div>
            ) : (
              conversations.map((conv) => (
                <button
                  key={conv.recruiter_email}
                  onClick={() => setSelectedEmail(conv.recruiter_email)}
                  className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors ${
                    selectedEmail === conv.recruiter_email ? 'bg-indigo-50 border-l-2 border-indigo-500' : ''
                  }`}
                >
                  <div className="font-medium text-sm text-gray-900">{conv.recruiter_name}</div>
                  <div className="text-xs text-gray-500 truncate">{conv.recruiter_email}</div>
                  <div className="text-xs text-gray-400 mt-1 truncate">{conv.latest_subject}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-gray-400">{conv.message_count} messages</span>
                    <span className="text-xs text-gray-300">{new Date(conv.last_activity).toLocaleDateString()}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Thread detail */}
        <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="text-sm font-semibold text-gray-700">
              {detail ? `${detail.recruiter_name} - Thread` : 'Select a conversation'}
            </h2>
          </div>

          {detailLoading ? (
            <div className="flex items-center justify-center py-16">
              <svg className="animate-spin h-6 w-6 text-indigo-500" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
            </div>
          ) : detail ? (
            <div className="p-4 space-y-4 max-h-[calc(100vh-16rem)] overflow-y-auto">
              {detail.messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[75%] rounded-xl px-4 py-3 ${
                      msg.direction === 'outbound'
                        ? 'bg-indigo-600 text-white'
                        : 'bg-gray-100 text-gray-900'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs font-medium ${msg.direction === 'outbound' ? 'text-indigo-200' : 'text-gray-500'}`}>
                        {msg.subject}
                      </span>
                      {msg.intent && (
                        <StatusBadge
                          label={msg.intent}
                          variant={msg.direction === 'outbound' ? 'blue' : 'green'}
                        />
                      )}
                    </div>
                    <p className="text-sm whitespace-pre-wrap">{msg.body}</p>
                    <div className={`text-xs mt-2 ${msg.direction === 'outbound' ? 'text-indigo-300' : 'text-gray-400'}`}>
                      {new Date(msg.date).toLocaleString()}
                    </div>
                    {msg.resume_file && (
                      <Link
                        to={`/api/resumes/${encodeURIComponent(msg.resume_file)}/download`}
                        className={`inline-block mt-2 text-xs underline ${
                          msg.direction === 'outbound' ? 'text-indigo-200' : 'text-indigo-600'
                        }`}
                      >
                        Attached: {msg.resume_file}
                      </Link>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
              Select a conversation to view the thread
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
