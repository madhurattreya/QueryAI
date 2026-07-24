'use client';

import React, { useState } from 'react';

interface EmbedWidgetProps {
  apiBaseUrl?: string;
  theme?: 'dark' | 'light';
  datasetId?: string;
  title?: string;
}

export default function EmbedWidget({
  apiBaseUrl = 'http://localhost:8000',
  theme = 'dark',
  datasetId = 'default',
  title = 'QueryIQ AI Analytics'
}: EmbedWidgetProps) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${apiBaseUrl}/api/query`, {

        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query, dataset_id: datasetId }),
      });

      if (!res.ok) {
        throw new Error(`Error ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch query results');
    } finally {
      setLoading(false);
    }
  };

  const isDark = theme === 'dark';

  return (
    <div
      style={{
        backgroundColor: isDark ? '#0f172a' : '#ffffff',
        color: isDark ? '#f8fafc' : '#0f172a',
        padding: '1.5rem',
        borderRadius: '0.75rem',
        border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`,
        boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)',
        fontFamily: 'Inter, system-ui, sans-serif',
        maxWidth: '600px',
        margin: '0 auto',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <h3 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>⚡ {title}</h3>
        <span style={{ fontSize: '0.75rem', backgroundColor: isDark ? '#1e293b' : '#f1f5f9', padding: '0.25rem 0.5rem', borderRadius: '0.375rem' }}>
          Embedded SDK
        </span>
      </div>

      <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask a question about your data..."
          style={{
            flex: 1,
            padding: '0.625rem 0.875rem',
            borderRadius: '0.375rem',
            border: `1px solid ${isDark ? '#475569' : '#cbd5e1'}`,
            backgroundColor: isDark ? '#1e293b' : '#f8fafc',
            color: 'inherit',
            fontSize: '0.875rem',
            outline: 'none',
          }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: '0.625rem 1.25rem',
            borderRadius: '0.375rem',
            border: 'none',
            backgroundColor: '#3b82f6',
            color: '#ffffff',
            fontWeight: 600,
            fontSize: '0.875rem',
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? 'Searching...' : 'Ask'}
        </button>
      </form>

      {error && (
        <div style={{ color: '#ef4444', backgroundColor: '#fef2f2', padding: '0.75rem', borderRadius: '0.375rem', fontSize: '0.875rem', marginBottom: '1rem' }}>
          ⚠️ {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: '1rem', borderTop: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`, paddingTop: '1rem' }}>
          {result.summary && <p style={{ fontSize: '0.875rem', marginBottom: '0.75rem', lineHeight: 1.5 }}>{result.summary}</p>}
          {result.data && Array.isArray(result.data) && (
            <div style={{ overflowX: 'auto', maxHeight: '200px' }}>
              <table style={{ width: '100%', fontSize: '0.75rem', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${isDark ? '#475569' : '#cbd5e1'}` }}>
                    {Object.keys(result.data[0] || {}).map((col) => (
                      <th key={col} style={{ padding: '0.5rem', fontWeight: 600 }}>
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.data.slice(0, 5).map((row: any, idx: number) => (
                    <tr key={idx} style={{ borderBottom: `1px solid ${isDark ? '#1e293b' : '#f1f5f9'}` }}>
                      {Object.values(row).map((val: any, vIdx: number) => (
                        <td key={vIdx} style={{ padding: '0.5rem' }}>
                          {String(val)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
