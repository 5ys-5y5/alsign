/**
 * ControlPage Component
 *
 * Control panels and data management UI.
 * Based on alsign/prompt/2_designSystem.ini route contract for control route.
 */

import React, { useState, useEffect } from 'react';

import { API_BASE_URL, getAuthHeaders } from '../services/api';

/**
 * APIServicePanel - Environment & API configuration panel.
 */
function APIServicePanel() {
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [revealedKeys, setRevealedKeys] = useState({});
  const [editingService, setEditingService] = useState(null);
  const [editValues, setEditValues] = useState({});
  const [saveStatus, setSaveStatus] = useState(null);

  useEffect(() => {
    fetchServices();
  }, []);

  async function fetchServices() {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`${API_BASE_URL}/control/apiServices`, {
        headers: await getAuthHeaders(),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setServices(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const toggleReveal = (serviceName) => {
    setRevealedKeys((prev) => ({
      ...prev,
      [serviceName]: !prev[serviceName],
    }));
  };

  const startEdit = (service) => {
    setEditingService(service.api_service);
    setEditValues({
      apiKey: service.apiKey || '',
      usagePerMin: service.usagePerMin || '',
    });
    setSaveStatus(null);
  };

  const cancelEdit = () => {
    setEditingService(null);
    setEditValues({});
    setSaveStatus(null);
  };

  const saveEdit = async (serviceName) => {
    try {
      setSaveStatus('saving');
      const response = await fetch(`${API_BASE_URL}/control/apiServices/${serviceName}`, {
        method: 'PUT',
        headers: await getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          apiKey: editValues.apiKey || null,
          usagePerMin: editValues.usagePerMin ? parseInt(editValues.usagePerMin) : null,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      setSaveStatus('success');
      setTimeout(() => {
        setEditingService(null);
        setSaveStatus(null);
        fetchServices();
      }, 1000);
    } catch (err) {
      setSaveStatus('error');
      setError(err.message);
    }
  };

  if (loading) return <div className="loading">Loading API services...</div>;
  if (error) return <div className="alert alert-error">Error: {error}</div>;

  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <h3 style={{ marginBottom: 'var(--space-3)' }}>Environment & API Configuration</h3>
      <div
        style={{
          display: 'grid',
          gap: 'var(--space-3)',
        }}
      >
        {services.map((service) => {
          const isEditing = editingService === service.api_service;
          const isRevealed = revealedKeys[service.api_service];
          const maskedKey = service.apiKey ? '••••••••••' : '(not set)';

          return (
            <div
              key={service.api_service}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 'var(--rounded-lg)',
                padding: 'var(--space-3)',
                backgroundColor: 'white',
              }}
            >
              <div style={{ marginBottom: 'var(--space-2)' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: 'var(--text-sm)',
                    fontWeight: 'var(--font-semibold)',
                    color: 'var(--ink)',
                    marginBottom: 'var(--space-1)',
                  }}
                >
                  API Service
                </label>
                <input
                  type="text"
                  value={service.api_service}
                  readOnly
                  style={{
                    backgroundColor: 'var(--surface)',
                    cursor: 'not-allowed',
                  }}
                />
              </div>

              <div style={{ marginBottom: 'var(--space-2)' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: 'var(--text-sm)',
                    fontWeight: 'var(--font-semibold)',
                    color: 'var(--ink)',
                    marginBottom: 'var(--space-1)',
                  }}
                >
                  API Key
                </label>
                <div style={{ display: 'flex', gap: 'var(--space-1)', alignItems: 'center' }}>
                  <input
                    type={isEditing || isRevealed ? 'text' : 'password'}
                    value={isEditing ? editValues.apiKey : service.apiKey || ''}
                    onChange={(e) =>
                      isEditing && setEditValues({ ...editValues, apiKey: e.target.value })
                    }
                    readOnly={!isEditing}
                    placeholder={!isEditing ? maskedKey : 'Enter API key'}
                    style={{
                      flex: 1,
                      backgroundColor: isEditing ? 'white' : 'var(--surface)',
                      cursor: isEditing ? 'text' : 'not-allowed',
                    }}
                  />
                  {!isEditing && (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline"
                      onClick={() => toggleReveal(service.api_service)}
                    >
                      {isRevealed ? 'Hide' : 'Show'}
                    </button>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: 'var(--space-3)' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: 'var(--text-sm)',
                    fontWeight: 'var(--font-semibold)',
                    color: 'var(--ink)',
                    marginBottom: 'var(--space-1)',
                  }}
                >
                  Usage Per Minute
                </label>
                <input
                  type="number"
                  value={isEditing ? editValues.usagePerMin : service.usagePerMin || ''}
                  onChange={(e) =>
                    isEditing && setEditValues({ ...editValues, usagePerMin: e.target.value })
                  }
                  readOnly={!isEditing}
                  placeholder="Rate limit"
                  min="0"
                  style={{
                    backgroundColor: isEditing ? 'white' : 'var(--surface)',
                    cursor: isEditing ? 'text' : 'not-allowed',
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: 'var(--space-1)' }}>
                {!isEditing ? (
                  <button
                    type="button"
                    className="btn btn-md btn-primary"
                    onClick={() => startEdit(service)}
                  >
                    Edit
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      className="btn btn-md btn-success"
                      onClick={() => saveEdit(service.api_service)}
                      disabled={saveStatus === 'saving'}
                    >
                      {saveStatus === 'saving' ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm btn-outline"
                      onClick={cancelEdit}
                      disabled={saveStatus === 'saving'}
                    >
                      Cancel
                    </button>
                  </>
                )}
              </div>

              {saveStatus === 'success' && (
                <div className="alert alert-success" style={{ marginTop: 'var(--space-2)' }}>
                  Saved successfully
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * TimebasePanel - Runtime information panel.
 */
function TimebasePanel() {
  const [runtime, setRuntime] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchRuntime();
    const interval = setInterval(fetchRuntime, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  async function fetchRuntime() {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`${API_BASE_URL}/control/runtime`, {
        headers: await getAuthHeaders(),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setRuntime(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <div className="loading">Loading runtime info...</div>;
  if (error) return <div className="alert alert-error">Error: {error}</div>;

  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <h3 style={{ marginBottom: 'var(--space-3)' }}>Timebase</h3>
      <div
        style={{
          border: '1px solid var(--border)',
          borderRadius: 'var(--rounded-lg)',
          padding: 'var(--space-3)',
          backgroundColor: 'white',
        }}
      >
        <div style={{ marginBottom: 'var(--space-2)' }}>
          <label
            style={{
              display: 'block',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-dim)',
              marginBottom: 'var(--space-1)',
            }}
          >
            Server Time (ISO)
          </label>
          <div style={{ fontSize: 'var(--text-base)', fontWeight: 'var(--font-medium)' }}>
            {runtime?.server_time_iso || 'N/A'}
          </div>
        </div>

        <div style={{ marginBottom: 'var(--space-2)' }}>
          <label
            style={{
              display: 'block',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-dim)',
              marginBottom: 'var(--space-1)',
            }}
          >
            Server Timezone
          </label>
          <div style={{ fontSize: 'var(--text-base)', fontWeight: 'var(--font-medium)' }}>
            {runtime?.server_tz || 'N/A'}
          </div>
        </div>

        <div>
          <label
            style={{
              display: 'block',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-dim)',
              marginBottom: 'var(--space-1)',
            }}
          >
            App Version
          </label>
          <div style={{ fontSize: 'var(--text-base)', fontWeight: 'var(--font-medium)' }}>
            {runtime?.app_version || 'N/A'}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * BestWindowPolicyPanel - Edit Best Window policy via control route.
 */
function BestWindowPolicyPanel() {
  const [policyText, setPolicyText] = useState('');
  const [description, setDescription] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [isDefault, setIsDefault] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saveStatus, setSaveStatus] = useState(null);

  useEffect(() => {
    fetchPolicy();
  }, []);

  async function fetchPolicy() {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`${API_BASE_URL}/control/bestWindowPolicy`, {
        headers: await getAuthHeaders(),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setPolicyText(JSON.stringify(data.policy || {}, null, 2));
      setDescription(data.description || '');
      setEndpoint(data.endpoint || '');
      setIsDefault(Boolean(data.isDefault));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const savePolicy = async () => {
    try {
      setSaveStatus('saving');
      setError(null);
      let parsed = {};
      try {
        parsed = JSON.parse(policyText || '{}');
      } catch (parseError) {
        throw new Error(`Invalid JSON: ${parseError.message}`);
      }

      const response = await fetch(`${API_BASE_URL}/control/bestWindowPolicy`, {
        method: 'PUT',
        headers: await getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          policy: parsed,
          description: description || null,
          endpoint: endpoint || null,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setPolicyText(JSON.stringify(data.policy || {}, null, 2));
      setDescription(data.description || '');
      setEndpoint(data.endpoint || '');
      setIsDefault(Boolean(data.isDefault));
      setSaveStatus('success');
      setTimeout(() => setSaveStatus(null), 1200);
    } catch (err) {
      setSaveStatus('error');
      setError(err.message);
    }
  };

  if (loading) return <div className="loading">Loading Best Window policy...</div>;
  if (error) return <div className="alert alert-error">Error: {error}</div>;

  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <h3 style={{ marginBottom: 'var(--space-2)' }}>Best Window Policy</h3>
      <div
        style={{
          border: '2px solid #f59e0b',
          borderRadius: 'var(--rounded-lg)',
          padding: 'var(--space-3)',
          background: 'linear-gradient(135deg, rgba(251, 191, 36, 0.15) 0%, rgba(253, 230, 138, 0.35) 100%)',
          boxShadow: '0 12px 30px rgba(245, 158, 11, 0.18)',
        }}
      >
        <details
          style={{
            marginBottom: 'var(--space-2)',
            padding: 'var(--space-2)',
            borderRadius: 'var(--rounded-md)',
            backgroundColor: 'rgba(255, 255, 255, 0.85)',
            fontSize: 'var(--text-xs)',
            color: 'var(--text)',
          }}
        >
          <summary style={{ cursor: 'pointer', fontWeight: 700, marginBottom: 'var(--space-1)' }}>
            사용법 안내
          </summary>
          <div
            style={{
              padding: 'var(--space-2)',
              borderRadius: 'var(--rounded-md)',
              backgroundColor: 'rgba(245, 158, 11, 0.08)',
              border: '1px dashed rgba(245, 158, 11, 0.4)',
            }}
          >
            <div style={{ marginBottom: 'var(--space-1)' }}>
            - 이 JSON은 Best Window 계산식을 정의합니다. 저장 즉시 적용됩니다.
            </div>
            <div style={{ marginBottom: 'var(--space-1)' }}>
            - 이벤트 날짜를 기준으로 한 일간 OHLC 데이터의 day offset 평균을 사용합니다.
            </div>
            <div style={{ marginBottom: 'var(--space-1)' }}>
            <strong>필수 구조</strong>
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
{`{
  "offsets": { "start": -14, "end": 14 },
  "designated": { "totalReturnFormula": "...", "avgFormula": "...", "avgAfterFeeFormula": "...", "topK": 2 },
  "previous":   { "totalReturnFormula": "...", "avgFormula": "...", "avgAfterFeeFormula": "...", "topK": 2 },
  "backtest": {
    "atr": { "period": 14, "method": "wilder" },
    "exit": { "mode": "percent", "stopLossAtr": 1.0, "takeProfitAtr": 2.0 },
    "risk": { "lambda": 1.0 },
    "strategy": { "dailyReturnMode": "spread", "annualizationDays": 252 }
  }
}`}
            </pre>
          </div>
            <div style={{ marginBottom: 'var(--space-1)' }}>
            <strong>offsets</strong>: start/end는 -14~14 범위만 허용됩니다.
            </div>
            <div style={{ marginBottom: 'var(--space-1)' }}>
            <strong>designated</strong>: 기준일(base offset)에서 종료일까지의 창(window) 계산
            </div>
            <div style={{ marginBottom: 'var(--space-1)' }}>
            <strong>previous</strong>: 모든 시작~종료 조합을 스캔해 최적 창을 계산
            </div>
            <div style={{ marginBottom: 'var(--space-1)' }}>
            <strong>사용 가능한 변수</strong>
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
{`mean_value       # 단일 offset 평균
running_sum      # 구간 합 (previous 전용)
running_compound # (1+mean_value) 누적 곱
compound_return  # running_compound - 1
total_return     # totalReturnFormula 결과
avg              # avgFormula 결과
length           # window 길이 (previous)
hold             # end-start (designated)
fee_rate         # 수수료율 (예: 0.001 = 0.1%)
start_offset
end_offset
count_value`}
            </pre>
            </div>
          <div style={{ marginBottom: 'var(--space-1)' }}>
            <strong>허용 함수</strong>: abs, min, max, sum, len, round, float, int, math
          </div>
          <div style={{ marginBottom: 'var(--space-1)' }}>
            <strong>backtest 설정</strong>: atr.period/atr.method(sma|wilder), risk.lambda,
            exit.mode(percent|atr), exit.stopLossAtr, exit.takeProfitAtr,
            strategy.dailyReturnMode(spread|lump), strategy.annualizationDays(기본 252)
          </div>
          <div style={{ marginBottom: 'var(--space-1)' }}>
            exit.mode=percent는 MIN/MAX 퍼센트 기준, exit.mode=atr는 ATR 기준으로 조기 청산합니다.
          </div>
          <div style={{ marginBottom: 'var(--space-1)' }}>
            <strong>예시</strong>: 로그 수익률 일간화
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
{`"avgFormula": "math.log(1 + total_return) / hold"`}
            </pre>
            </div>
            <div>
            저장 후 Best Window 계산이 즉시 변경됩니다.
            </div>
          </div>
        </details>
        <div style={{ marginBottom: 'var(--space-2)', display: 'flex', gap: 'var(--space-2)' }}>
          <div style={{ flex: 1 }}>
            <label
              style={{
                display: 'block',
                fontSize: 'var(--text-sm)',
                fontWeight: 'var(--font-semibold)',
                color: 'var(--ink)',
                marginBottom: 'var(--space-1)',
              }}
            >
              Endpoint
            </label>
            <input
              type="text"
              value={endpoint}
              onChange={(e) => setEndpoint(e.target.value)}
              placeholder="eventsHistory"
            />
          </div>
          <div style={{ flex: 2 }}>
            <label
              style={{
                display: 'block',
                fontSize: 'var(--text-sm)',
                fontWeight: 'var(--font-semibold)',
                color: 'var(--ink)',
                marginBottom: 'var(--space-1)',
              }}
            >
              Description
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Policy description"
            />
          </div>
        </div>

        <div style={{ marginBottom: 'var(--space-2)' }}>
          <label
            style={{
              display: 'block',
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--font-semibold)',
              color: 'var(--ink)',
              marginBottom: 'var(--space-1)',
            }}
          >
            Policy JSON
          </label>
          <textarea
            rows={12}
            value={policyText}
            onChange={(e) => setPolicyText(e.target.value)}
            style={{
              width: '100%',
              fontFamily: 'SFMono-Regular, ui-monospace, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
              fontSize: 'var(--text-xs)',
              lineHeight: 1.4,
            }}
          />
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-1)', alignItems: 'center' }}>
          <button
            type="button"
            className="btn btn-md btn-primary"
            onClick={savePolicy}
            disabled={saveStatus === 'saving'}
          >
            {saveStatus === 'saving' ? 'Saving...' : 'Save'}
          </button>
          <button type="button" className="btn btn-sm btn-outline" onClick={fetchPolicy}>
            Reload
          </button>
          {isDefault ? (
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
              Default policy (not stored)
            </span>
          ) : null}
        </div>

        {saveStatus === 'success' && (
          <div className="alert alert-success" style={{ marginTop: 'var(--space-2)' }}>
            Saved successfully
          </div>
        )}
        {saveStatus === 'error' && (
          <div className="alert alert-error" style={{ marginTop: 'var(--space-2)' }}>
            Failed to save policy
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * DataCatalogPanel - Displays JSON data in compact format.
 */
function DataCatalogPanel({ title, data, loading, error }) {
  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="alert alert-error">Error: {error}</div>;

  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <h3 style={{ marginBottom: 'var(--space-3)' }}>{title}</h3>
      <div
        style={{
          border: '1px solid var(--border)',
          borderRadius: 'var(--rounded-lg)',
          padding: 'var(--space-3)',
          backgroundColor: 'white',
          maxHeight: '70vh',
          overflowY: 'auto',
        }}
      >
        <pre
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            margin: 0,
          }}
        >
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    </div>
  );
}

/**
 * ControlPage component.
 */
export default function ControlPage() {
  const [apiList, setApiList] = useState([]);
  const [apiListLoading, setApiListLoading] = useState(true);
  const [apiListError, setApiListError] = useState(null);

  const [metrics, setMetrics] = useState([]);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [metricsError, setMetricsError] = useState(null);

  const [transforms, setTransforms] = useState([]);
  const [transformsLoading, setTransformsLoading] = useState(true);
  const [transformsError, setTransformsError] = useState(null);

  // Fetch API list
  useEffect(() => {
    async function fetchApiList() {
      try {
        setApiListLoading(true);
        setApiListError(null);
        const response = await fetch(`${API_BASE_URL}/control/apiList`, {
          headers: await getAuthHeaders(),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        setApiList(data);
      } catch (err) {
        setApiListError(err.message);
      } finally {
        setApiListLoading(false);
      }
    }
    fetchApiList();
  }, []);

  // Fetch metrics
  useEffect(() => {
    async function fetchMetrics() {
      try {
        setMetricsLoading(true);
        setMetricsError(null);
        const response = await fetch(`${API_BASE_URL}/control/metrics`, {
          headers: await getAuthHeaders(),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        setMetrics(data);
      } catch (err) {
        setMetricsError(err.message);
      } finally {
        setMetricsLoading(false);
      }
    }
    fetchMetrics();
  }, []);

  // Fetch metric transforms
  useEffect(() => {
    async function fetchTransforms() {
      try {
        setTransformsLoading(true);
        setTransformsError(null);
        const response = await fetch(`${API_BASE_URL}/control/metricTransforms`, {
          headers: await getAuthHeaders(),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        setTransforms(data);
      } catch (err) {
        setTransformsError(err.message);
      } finally {
        setTransformsLoading(false);
      }
    }
    fetchTransforms();
  }, []);

  return (
    <>
      <header style={{ marginBottom: 'var(--space-4)' }}>
        <h1>Control</h1>
        <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
          Control panels and data management configuration
        </p>
      </header>

      {/* Control Panels Section */}
      <section style={{ marginBottom: 'var(--space-5)' }}>
        <h2 style={{ marginBottom: 'var(--space-3)' }}>Control Panels</h2>
        <BestWindowPolicyPanel />
        <APIServicePanel />
        <TimebasePanel />
      </section>

      {/* Data Management UI Section */}
      <section>
        <h2 style={{ marginBottom: 'var(--space-3)' }}>Data Management</h2>
        <DataCatalogPanel
          title="API Catalog"
          data={apiList}
          loading={apiListLoading}
          error={apiListError}
        />
        <DataCatalogPanel
          title="Metric Catalog"
          data={metrics}
          loading={metricsLoading}
          error={metricsError}
        />
        <DataCatalogPanel
          title="Metric Transform Catalog"
          data={transforms}
          loading={transformsLoading}
          error={transformsError}
        />
      </section>
    </>
  );
}
