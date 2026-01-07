/**
 * Condition Group API Service
 *
 * Provides methods for managing condition groups via the backend API.
 */

const API_BASE_URL = '/api';

/**
 * Get list of allowed columns for condition groups
 * @returns {Promise<string[]>} Array of column names
 */
export async function getAllowedColumns() {
  const response = await fetch(`${API_BASE_URL}/conditionGroups/columns`);

  if (!response.ok) {
    throw new Error(`Failed to fetch allowed columns: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get distinct values for a specific column
 * @param {string} column - Column name (source, sector, or industry)
 * @returns {Promise<string[]>} Array of distinct values
 */
export async function getColumnValues(column) {
  const response = await fetch(
    `${API_BASE_URL}/conditionGroups/values?column=${encodeURIComponent(column)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch column values: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get all existing condition groups
 * @returns {Promise<Array>} Array of condition group objects
 */
export async function getConditionGroups() {
  const response = await fetch(`${API_BASE_URL}/conditionGroups`);

  if (!response.ok) {
    throw new Error(`Failed to fetch condition groups: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Create a new condition group
 * @param {Object} data - Condition group data
 * @param {string} data.column - Column name
 * @param {string} data.value - Column value
 * @param {string} data.name - Condition group name
 * @param {boolean} data.confirm - Confirmation flag
 * @returns {Promise<Object>} Creation response
 */
export async function createConditionGroup(data) {
  const response = await fetch(`${API_BASE_URL}/conditionGroups`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to create condition group: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Delete a condition group
 * @param {string} name - Condition group name to delete
 * @returns {Promise<Object>} Deletion response
 */
export async function deleteConditionGroup(name) {
  const response = await fetch(
    `${API_BASE_URL}/conditionGroups/${encodeURIComponent(name)}`,
    {
      method: 'DELETE',
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to delete condition group: ${response.statusText}`);
  }

  return response.json();
}
