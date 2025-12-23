/**
 * Condition Group Management Page
 *
 * Displays form for creating condition groups and table of existing groups
 * with edit/delete functionality.
 */

import { useState, useEffect } from 'react';
import ConditionGroupForm from '../components/forms/ConditionGroupForm';
import {
  getConditionGroups,
  deleteConditionGroup,
} from '../services/conditionGroupService';

export default function ConditionGroupPage() {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [deletingGroup, setDeletingGroup] = useState(null);

  // Load condition groups on mount
  useEffect(() => {
    loadGroups();
  }, []);

  async function loadGroups() {
    setLoading(true);
    setError(null);

    try {
      const data = await getConditionGroups();
      setGroups(data);
    } catch (err) {
      console.error('Failed to load condition groups:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const handleSuccess = (result) => {
    setSuccess(
      `Condition group "${result.name || 'unknown'}" created successfully. ${
        result.affectedRows || 0
      } rows updated.`
    );
    setError(null);

    // Reload groups
    loadGroups();

    // Clear success message after 5 seconds
    setTimeout(() => setSuccess(null), 5000);
  };

  const handleError = (errorMessage) => {
    setError(errorMessage);
    setSuccess(null);
  };

  const handleDelete = async (groupName) => {
    if (!confirm(`Are you sure you want to delete the condition group "${groupName}"?`)) {
      return;
    }

    setDeletingGroup(groupName);
    setError(null);
    setSuccess(null);

    try {
      const result = await deleteConditionGroup(groupName);
      setSuccess(
        `Condition group "${groupName}" deleted successfully. ${
          result.affectedRows || 0
        } rows updated.`
      );

      // Reload groups
      loadGroups();

      // Clear success message after 5 seconds
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error('Failed to delete condition group:', err);
      setError(err.message);
    } finally {
      setDeletingGroup(null);
    }
  };

  return (
    <div style={{ padding: 'var(--space-4)', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ marginBottom: 'var(--space-4)' }}>
        <h1>Condition Group</h1>
        <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
          Create and manage condition groups for filtering events by source, sector, or industry
        </p>
      </header>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: 'var(--space-3)' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {success && (
        <div className="alert alert-success" style={{ marginBottom: 'var(--space-3)' }}>
          <strong>Success:</strong> {success}
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr',
          gap: 'var(--space-4)',
        }}
      >
        <section style={{ marginBottom: 'var(--space-4)' }}>
          <h2 style={{ marginBottom: 'var(--space-3)' }}>Create New Condition Group</h2>
          <ConditionGroupForm onSuccess={handleSuccess} onError={handleError} />
        </section>

        <section>
          <h2 style={{ marginBottom: 'var(--space-3)' }}>Existing Condition Groups</h2>

          {loading ? (
            <div className="loading">Loading condition groups...</div>
          ) : groups.length === 0 ? (
            <div className="empty-state">
              <p>No condition groups found.</p>
              <p style={{ marginTop: 'var(--space-1)', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                Create a condition group using the form above to get started.
              </p>
            </div>
          ) : (
            <div className="table-shell">
              <div className="scroll-y">
                <div className="scroll-x">
                  <table>
                    <thead>
                      <tr>
                        <th>Condition Name</th>
                        <th>Column</th>
                        <th>Value</th>
                        <th style={{ textAlign: 'right' }}>Row Count</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {groups.map((group) => (
                        <tr key={group.name}>
                          <td>
                            <strong>{group.name}</strong>
                          </td>
                          <td>{group.column}</td>
                          <td>
                            <code
                              style={{
                                backgroundColor: 'var(--surface)',
                                padding: '4px var(--space-1)',
                                borderRadius: 'var(--rounded-lg)',
                                fontFamily: 'monospace',
                                fontSize: 'var(--text-sm)',
                              }}
                            >
                              {group.value}
                            </code>
                          </td>
                          <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                            {group.rowCount.toLocaleString()}
                          </td>
                          <td>
                            <button
                              onClick={() => handleDelete(group.name)}
                              disabled={deletingGroup === group.name}
                              className="btn btn-sm btn-danger"
                              title={`Delete ${group.name}`}
                            >
                              {deletingGroup === group.name ? 'Deleting...' : 'Delete'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
