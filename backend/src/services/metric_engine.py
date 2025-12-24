"""
Metric Calculation Engine

Dynamically calculates metrics based on config_lv2_metric table definitions.

Supports three metric types:
1. api_field: Extract values from API responses
2. aggregation: Transform base metrics (TTM, Last, Avg, etc.)
3. expression: Calculate using formulas

Architecture:
1. Build dependency graph from config_lv2_metric
2. Topologically sort metrics (resolve dependencies)
3. Calculate in order: api_field → aggregation → expression
4. Group results by domain
"""

import logging
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict, deque

logger = logging.getLogger("alsign")


class MetricCalculationEngine:
    """
    Engine for calculating metrics based on config_lv2_metric definitions.

    Now supports dynamic calculation from config_lv2_metric_transform.calculation column.
    Falls back to hardcoded functions if calculation is not available.

    Handles dependency resolution, calculation ordering, and domain grouping.
    """

    def __init__(
        self, 
        metrics_by_domain: Dict[str, List[Dict[str, Any]]],
        transforms: Optional[Dict[str, Dict[str, Any]]] = None
    ):
        """
        Initialize the metric calculation engine.

        Args:
            metrics_by_domain: Metrics grouped by domain suffix from config_lv2_metric.
                               Format: {'valuation': [{'name': 'PER', 'formula': '...', ...}], ...}
            transforms: Transform definitions from config_lv2_metric_transform.
                       If None, falls back to hardcoded functions.
        """
        self.metrics_by_domain = metrics_by_domain
        self.all_metrics = self._flatten_metrics()
        self.metrics_by_name = {m['name']: m for m in self.all_metrics}
        self.dependency_graph = {}
        self.calculation_order = []
        self.transforms = transforms or {}  # Transform definitions from DB

    def _flatten_metrics(self) -> List[Dict[str, Any]]:
        """Flatten metrics_by_domain into a single list."""
        all_metrics = []
        for domain_metrics in self.metrics_by_domain.values():
            all_metrics.extend(domain_metrics)
        return all_metrics

    def get_required_apis(self) -> Set[str]:
        """
        Extract all required api_list_id values from metrics.

        Returns:
            Set of api_list_id strings that need to be called
        """
        api_ids = set()
        for metric in self.all_metrics:
            api_list_id = metric.get('api_list_id')
            if api_list_id and metric.get('source') == 'api_field':
                api_ids.add(api_list_id)
        return api_ids

    def build_dependency_graph(self) -> None:
        """
        Build dependency graph for all metrics.

        Parses expressions to find dependencies (referenced metric names).
        Builds adjacency list: {metric_name: [dependent_metric_names]}
        """
        self.dependency_graph = {}

        for metric in self.all_metrics:
            metric_name = metric['name']
            dependencies = self._extract_dependencies(metric)
            self.dependency_graph[metric_name] = dependencies

        logger.debug(f"[MetricEngine] Built dependency graph with {len(self.dependency_graph)} metrics")

    def _extract_dependencies(self, metric: Dict[str, Any]) -> List[str]:
        """
        Extract dependencies from a metric definition.

        For api_field: No dependencies
        For aggregation: base_metric_id is the dependency
        For expression: Parse formula to find referenced metrics

        Args:
            metric: Metric definition with 'name', 'formula', etc.

        Returns:
            List of metric names this metric depends on
        """
        dependencies = []
        source = metric.get('source')

        if source == 'api_field':
            # No dependencies - directly from API
            return []

        elif source == 'aggregation':
            # Depends on base_metric_id
            base_metric_id = metric.get('base_metric_id')
            if base_metric_id:
                dependencies.append(base_metric_id)

        elif source == 'expression':
            # Parse expression to find referenced metrics
            formula = metric.get('formula', '')
            if formula:
                # Find all metric names in formula
                for other_metric_name in self.metrics_by_name.keys():
                    if other_metric_name in formula and other_metric_name != metric['name']:
                        dependencies.append(other_metric_name)

        return dependencies

    def topological_sort(self) -> List[str]:
        """
        Perform topological sort on dependency graph.

        Returns calculation order: [base_metrics, ..., derived_metrics]
        Ensures dependencies are calculated before dependents.

        Returns:
            List of metric names in calculation order

        Raises:
            ValueError: If circular dependency detected
        """
        logger.debug(f"[MetricEngine] Starting topological sort for {len(self.dependency_graph)} metrics")

        # Kahn's algorithm for topological sort
        # in_degree[A] = number of metrics that A depends on
        in_degree = defaultdict(int)

        # Build reverse graph: for each dependency, track what depends on it
        reverse_graph = defaultdict(list)

        # Initialize all metrics with in-degree 0
        for metric_name in self.dependency_graph:
            if metric_name not in in_degree:
                in_degree[metric_name] = 0

        logger.debug(f"[MetricEngine] Building reverse graph...")

        # Calculate in-degrees and build reverse graph
        # If A depends on [B, C], then:
        # - in_degree[A] += 2 (A has 2 incoming dependencies)
        # - reverse_graph[B].append(A) (B is depended on by A)
        # - reverse_graph[C].append(A) (C is depended on by A)
        for metric_name, dependencies in self.dependency_graph.items():
            in_degree[metric_name] = len(dependencies)
            for dependency in dependencies:
                reverse_graph[dependency].append(metric_name)
                # Ensure dependency exists in in_degree
                if dependency not in in_degree:
                    in_degree[dependency] = 0

        # Start with metrics that have no dependencies (in_degree == 0)
        # These are base metrics like api_field metrics
        zero_deps = [name for name, degree in in_degree.items() if degree == 0]
        logger.debug(f"[MetricEngine] Found {len(zero_deps)} metrics with no dependencies (starting nodes)")

        queue = deque(zero_deps)
        result = []

        while queue:
            current = queue.popleft()
            result.append(current)

            # For each metric that depends on current, reduce its in-degree
            for dependent in reverse_graph.get(current, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(in_degree):
            logger.error(f"[MetricEngine] Circular dependency! Processed {len(result)} of {len(in_degree)} metrics")
            # Log metrics that weren't processed
            unprocessed = set(in_degree.keys()) - set(result)
            logger.error(f"[MetricEngine] Unprocessed metrics: {list(unprocessed)[:10]}")
            raise ValueError("Circular dependency detected in metrics")

        self.calculation_order = result
        logger.debug(f"[MetricEngine] Topological sort completed: {len(result)} metrics in order")
        logger.debug(f"[MetricEngine] First 10 metrics: {result[:10]}")
        logger.debug(f"[MetricEngine] Last 10 metrics: {result[-10:]}")
        return result

    def calculate_all(
        self,
        api_data: Dict[str, List[Dict[str, Any]]],
        target_domains: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Calculate all metrics for target domains.

        Args:
            api_data: API responses keyed by api_list_id
                     Example: {
                         'fmp-income-statement': [{'date': '...', 'netIncome': 123, ...}],
                         'fmp-balance-sheet-statement': [...],
                         'fmp-quote': [{'marketCap': 456}]
                     }
            target_domains: List of domain suffixes to calculate (e.g., ['valuation', 'profitability'])
                           If None, calculates all domains.

        Returns:
            Dict with calculated metrics grouped by domain
            Example: {
                'valuation': {
                    'PER': 25.5,
                    'PBR': 3.2,
                    '_meta': {'date_range': '...', 'calcType': 'TTM_fullQuarter', 'count': 4}
                },
                'profitability': {...}
            }
        """
        # Build calculation order if not already done
        if not self.calculation_order:
            self.build_dependency_graph()
            self.topological_sort()

        # Calculate each metric in order
        calculated_values = {}

        for metric_name in self.calculation_order:
            metric = self.metrics_by_name[metric_name]

            # Always calculate internal metrics (needed as intermediate values)
            # Only skip non-internal metrics that aren't in target domains
            if target_domains:
                domain = metric.get('domain', '')
                domain_suffix = domain.split('-', 1)[1] if '-' in domain else domain

                # Skip only if:
                # 1. Not an internal metric AND
                # 2. Not in target domains
                if domain != 'internal' and domain_suffix not in target_domains:
                    logger.debug(f"[MetricEngine] Skipping {metric_name} (domain: {domain}, not in target)")
                    continue

            try:
                value, failure_reason = self._calculate_metric_with_reason(metric, api_data, calculated_values)
                calculated_values[metric_name] = value
                if value is not None:
                    # Smart formatting: show first item + count for lists, full value for scalars
                    if isinstance(value, list) and len(value) > 0:
                        first_item = value[0]
                        value_str = f"[{first_item}, ...] ({len(value)} items)"
                    else:
                        value_str = str(value)
                    
                    # Truncate only if still too long (for safety)
                    if len(value_str) > 150:
                        value_str = value_str[:150] + "..."
                    
                    logger.debug(f"[MetricEngine] ✓ {metric_name} = {value_str} (source: {metric.get('source')})")
                else:
                    # Include failure reason for debugging
                    reason_str = f" | reason: {failure_reason}" if failure_reason else ""
                    logger.debug(f"[MetricEngine] ✗ {metric_name} = None (source: {metric.get('source')}){reason_str}")
            except Exception as e:
                logger.error(f"[MetricEngine] Failed to calculate {metric_name}: {e}")
                calculated_values[metric_name] = None

        # Group by domain
        result = self._group_by_domain(calculated_values, target_domains)
        return result

    def _calculate_metric_with_reason(
        self,
        metric: Dict[str, Any],
        api_data: Dict[str, List[Dict[str, Any]]],
        calculated_values: Dict[str, Any]
    ) -> tuple:
        """
        Calculate a single metric with failure reason tracking.

        Returns:
            Tuple of (value, failure_reason)
        """
        source = metric.get('source')
        metric_name = metric.get('name')

        if source == 'api_field':
            value = self._calculate_api_field(metric, api_data)
            if value is None:
                api_list_id = metric.get('api_list_id')
                if not api_list_id:
                    return None, "Missing api_list_id"
                elif api_list_id not in api_data or not api_data.get(api_list_id):
                    return None, f"No data from API '{api_list_id}'"
                else:
                    return None, f"Field extraction failed from '{api_list_id}'"
            return value, None
            
        elif source == 'aggregation':
            value = self._calculate_aggregation(metric, api_data, calculated_values)
            if value is None:
                base_metric = metric.get('base_metric')
                transform_id = metric.get('transform')
                if not base_metric:
                    return None, "Missing base_metric"
                elif base_metric not in calculated_values:
                    return None, f"Base metric '{base_metric}' not calculated"
                elif calculated_values.get(base_metric) is None:
                    return None, f"Base metric '{base_metric}' is None"
                else:
                    return None, f"Transform '{transform_id}' returned None"
            return value, None
            
        elif source == 'expression':
            value = self._calculate_expression(metric, calculated_values)
            if value is None:
                dependencies = metric.get('dependencies', [])
                missing = [d for d in dependencies if d not in calculated_values or calculated_values.get(d) is None]
                if missing:
                    return None, f"Missing dependencies: {', '.join(missing)}"
                else:
                    return None, "Expression evaluation returned None"
            return value, None
            
        else:
            return None, f"Unknown source type '{source}'"

    def _calculate_metric(
        self,
        metric: Dict[str, Any],
        api_data: Dict[str, List[Dict[str, Any]]],
        calculated_values: Dict[str, Any]
    ) -> Any:
        """
        Calculate a single metric (backward compatibility).

        Routes to appropriate calculator based on metric source type.

        Args:
            metric: Metric definition
            api_data: API responses
            calculated_values: Already calculated metrics

        Returns:
            Calculated metric value
        """
        value, _ = self._calculate_metric_with_reason(metric, api_data, calculated_values)
        return value

    def _convert_value(self, value: Any) -> Any:
        """
        Convert API value to appropriate Python type.

        Handles numeric strings, booleans, and keeps other types as-is.

        Args:
            value: Raw value from API

        Returns:
            Converted value (float for numbers, bool for booleans, original otherwise)
        """
        # Handle boolean values
        if isinstance(value, bool):
            return value

        # Handle numeric values
        if isinstance(value, (int, float)):
            return float(value)

        # Handle string values
        if isinstance(value, str):
            # Try to convert to number
            try:
                # Remove whitespace
                value_clean = value.strip()

                # Check if it's a valid number (including negative and decimals)
                if value_clean and (value_clean.replace('.', '').replace('-', '').replace('+', '').isdigit()):
                    return float(value_clean)
            except:
                pass

            # Check for boolean strings
            if value.lower() in ('true', 'false'):
                return value.lower() == 'true'

        # Return as-is if not convertible
        return value

    def _calculate_api_field(
        self,
        metric: Dict[str, Any],
        api_data: Dict[str, List[Dict[str, Any]]]
    ) -> Any:
        """
        Extract value from API response.

        Args:
            metric: Metric with api_list_id and response_key
            api_data: API responses keyed by api_list_id

        Returns:
            List of quarterly values or single value (for snapshot APIs like fmp-quote)
        """
        api_list_id = metric.get('api_list_id')
        response_key_json = metric.get('response_key')

        if not api_list_id or not response_key_json:
            logger.warning(f"[MetricEngine] Missing api_list_id or response_key for {metric.get('name')}")
            return None

        # Get API data
        api_response = api_data.get(api_list_id)
        if not api_response:
            if metric.get('name') == 'priceEodOHLC':
                logger.warning(f"[MetricEngine][priceEodOHLC] No API data for api_list_id={api_list_id}, available APIs: {list(api_data.keys())}")
            logger.debug(f"[MetricEngine] No API data for {api_list_id}")
            return None

        # Parse response_key from JSONB (stored as JSON string like '"netIncome"')
        import json as json_module
        try:
            # response_key is stored as JSONB, which is a JSON-encoded string
            # Example: '"netIncome"' or '{"key": "value"}'
            field_key = json_module.loads(response_key_json) if isinstance(response_key_json, str) else response_key_json
        except:
            field_key = response_key_json

        # Handle dict response_key (complex schema mapping)
        # Example: {"low": "low", "high": "high", "open": "open", "close": "close"}
        # Maps output field name to API response field name
        if isinstance(field_key, dict):
            # Extract multiple fields from API response
            if isinstance(api_response, list):
                # For time-series data, extract dict for each record
                result_list = []
                for idx, record in enumerate(api_response):
                    record_dict = {}
                    for output_key, api_key in field_key.items():
                        value = record.get(api_key)
                        if value is not None:
                            record_dict[output_key] = self._convert_value(value)
                    
                    if record_dict:  # Only add if at least one field was found
                        result_list.append(record_dict)

                # Return scalar dict if single record, else list of dicts
                if len(result_list) == 1:
                    return result_list[0]
                elif len(result_list) > 1:
                    return result_list
                else:
                    logger.debug(f"[MetricEngine] No fields extracted from {api_list_id} for {metric.get('name')}")
                    return None
            elif isinstance(api_response, dict):
                # For snapshot data, extract dict from single record
                result_dict = {}
                for output_key, api_key in field_key.items():
                    value = api_response.get(api_key)
                    if value is not None:
                        result_dict[output_key] = self._convert_value(value)
                return result_dict if result_dict else None
            else:
                return None

        # Handle simple string response_key (single field extraction)
        # Extract values from API response
        if isinstance(api_response, list):
            # Extract field from each record
            values = []
            for record in api_response:
                value = record.get(field_key)
                if value is not None:
                    # Convert to appropriate type
                    converted_value = self._convert_value(value)
                    values.append(converted_value)

            # If single record (snapshot API), return scalar value
            # Otherwise return list (time-series API)
            if len(values) == 1:
                return values[0]
            elif len(values) > 1:
                return values
            else:
                return None
        elif isinstance(api_response, dict):
            # Single snapshot (e.g., fmp-quote returns single market cap)
            value = api_response.get(field_key)
            if value is not None:
                return self._convert_value(value)
            return None
        else:
            return None

    def _calculate_aggregation(
        self,
        metric: Dict[str, Any],
        api_data: Dict[str, List[Dict[str, Any]]],
        calculated_values: Dict[str, Any]
    ) -> Any:
        """
        Apply aggregation transform to base metric.

        Now uses dynamic calculation from config_lv2_metric_transform.calculation.
        Falls back to hardcoded functions if calculation is not available.

        Args:
            metric: Metric with aggregation_kind (TTM, Last, etc.)
            api_data: API responses
            calculated_values: Base metric values

        Returns:
            Aggregated value
        """
        base_metric_id = metric.get('base_metric_id')
        aggregation_kind = metric.get('aggregation_kind')
        aggregation_params = metric.get('aggregation_params', {})

        if not base_metric_id or not aggregation_kind:
            logger.warning(f"[MetricEngine] Missing base_metric_id or aggregation_kind for {metric.get('name')}")
            return None

        # Get base metric values
        base_values = calculated_values.get(base_metric_id)
        if base_values is None:
            logger.warning(f"[MetricEngine] Base metric {base_metric_id} not found for {metric.get('name')} (available: {list(calculated_values.keys())[:10]}...)")
            return None

        # Ensure base_values is a list (quarterly data)
        if not isinstance(base_values, list):
            base_values = [base_values]

        # Try dynamic calculation from DB first
        transform_def = self.transforms.get(aggregation_kind)
        if transform_def and transform_def.get('calculation'):
            try:
                return self._execute_dynamic_calculation(
                    transform_def['calculation'],
                    base_values,
                    aggregation_params
                )
            except Exception as e:
                logger.warning(
                    f"[MetricEngine] Dynamic calculation failed for {aggregation_kind}, "
                    f"falling back to hardcoded: {e}"
                )
                # Fall through to hardcoded functions

        # Fallback to hardcoded functions (backward compatibility)
        if aggregation_kind == 'ttmFromQuarterSumOrScaled':
            return self._ttm_sum_or_scaled(base_values, aggregation_params)
        elif aggregation_kind == 'lastFromQuarter':
            return self._last_from_quarter(base_values, aggregation_params)
        elif aggregation_kind == 'avgFromQuarter':
            return self._avg_from_quarter(base_values, aggregation_params)
        elif aggregation_kind == 'qoqFromQuarter':
            return self._qoq_from_quarter(base_values, aggregation_params)
        elif aggregation_kind == 'yoyFromQuarter':
            return self._yoy_from_quarter(base_values, aggregation_params)
        elif aggregation_kind == 'leadPairFromList':
            return self._lead_pair_from_list(base_values, aggregation_params)
        else:
            logger.warning(f"[MetricEngine] Unknown aggregation_kind '{aggregation_kind}' for {metric.get('name')}")
            return None

    def _execute_dynamic_calculation(
        self,
        calculation_code: str,
        quarterly_values: List[float],
        params: Dict[str, Any]
    ) -> Any:
        """
        Execute calculation code from config_lv2_metric_transform.calculation.

        Runs in a restricted namespace for security.

        Args:
            calculation_code: Python code string from DB
            quarterly_values: List of quarterly values (most recent first)
            params: Aggregation parameters dict

        Returns:
            Calculated value

        Raises:
            Exception: If calculation fails or contains unsafe code
        """
        # Restricted namespace - only allow safe operations
        import json as json_module
        
        safe_namespace = {
            # Built-in functions
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'len': len,
            'round': round,
            'sorted': sorted,
            'range': range,
            'float': float,
            'int': int,
            'bool': bool,
            'enumerate': enumerate,
            'isinstance': isinstance,
            'str': str,
            'dict': dict,
            'list': list,
            'tuple': tuple,
            
            # JSON parsing (safe)
            'json': json_module,

            # Input variables
            'quarterly_values': quarterly_values,
            'params': params,
        }

        # Restrict builtins to safe functions only
        restricted_builtins = {
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'len': len,
            'round': round,
            'sorted': sorted,
            'range': range,
            'float': float,
            'int': int,
            'bool': bool,
            'enumerate': enumerate,
            'isinstance': isinstance,
            'str': str,
            'dict': dict,
            'list': list,
            'tuple': tuple,
        }
        safe_namespace['__builtins__'] = restricted_builtins

        try:
            # Execute calculation code
            result = eval(calculation_code, safe_namespace)
            return result
        except Exception as e:
            logger.error(f"[MetricEngine] Dynamic calculation execution failed: {e}")
            logger.debug(f"[MetricEngine] Calculation code: {calculation_code[:200]}...")
            raise

    def _ttm_sum_or_scaled(self, quarterly_values: List[float], params: Dict[str, Any]) -> Optional[float]:
        """
        Calculate TTM (Trailing Twelve Months) by summing recent 4 quarters.
        If fewer than 4 quarters available, scale proportionally.

        Args:
            quarterly_values: List of quarterly values (most recent first)
            params: Aggregation parameters (window, scale_to, min_points)

        Returns:
            TTM value or None
        """
        if not quarterly_values:
            return None

        window = params.get('window', 4)
        scale_to = params.get('scale_to', 4)
        min_points = params.get('min_points', 1)

        # Take most recent N quarters
        recent_quarters = quarterly_values[:window]
        count = len(recent_quarters)

        if count < min_points:
            return None

        # Sum available quarters
        total = sum(recent_quarters)

        # Scale if fewer than target
        if count < scale_to:
            total = (total / count) * scale_to

        return total

    def _last_from_quarter(self, quarterly_values: List[float], params: Dict[str, Any]) -> Optional[float]:
        """
        Get the most recent quarter value.

        Args:
            quarterly_values: List of quarterly values (most recent first)
            params: Aggregation parameters

        Returns:
            Most recent value or None
        """
        if not quarterly_values:
            return None
        return quarterly_values[0]

    def _avg_from_quarter(self, quarterly_values: List[float], params: Dict[str, Any]) -> Optional[float]:
        """
        Calculate average of recent quarters.

        Args:
            quarterly_values: List of quarterly values (most recent first)
            params: Aggregation parameters (window)

        Returns:
            Average value or None
        """
        if not quarterly_values:
            return None

        window = params.get('window', 4)
        recent_quarters = quarterly_values[:window]

        if not recent_quarters:
            return None

        return sum(recent_quarters) / len(recent_quarters)

    def _qoq_from_quarter(self, quarterly_values: List[float], params: Dict[str, Any]) -> Optional[float]:
        """
        Calculate Quarter-over-Quarter growth rate.

        Args:
            quarterly_values: List of quarterly values (most recent first)
            params: Aggregation parameters

        Returns:
            QoQ growth rate (e.g., 0.05 = 5% growth) or None
        """
        if len(quarterly_values) < 2:
            return None

        current = quarterly_values[0]
        previous = quarterly_values[1]

        if previous == 0:
            return None

        return (current - previous) / previous

    def _yoy_from_quarter(self, quarterly_values: List[float], params: Dict[str, Any]) -> Optional[float]:
        """
        Calculate Year-over-Year growth rate.

        Args:
            quarterly_values: List of quarterly values (most recent first)
            params: Aggregation parameters

        Returns:
            YoY growth rate (e.g., 0.10 = 10% growth) or None
        """
        if len(quarterly_values) < 5:  # Need 5 quarters (current + 4 previous)
            return None

        current = quarterly_values[0]
        year_ago = quarterly_values[4]  # 4 quarters ago

        if year_ago == 0:
            return None

        return (current - year_ago) / year_ago

    def _calculate_expression(
        self,
        metric: Dict[str, Any],
        calculated_values: Dict[str, Any]
    ) -> Any:
        """
        Evaluate expression formula.

        Parses formulas like "marketCap / netIncomeTTM" and evaluates them
        using calculated metric values.

        Args:
            metric: Metric with formula/expression
            calculated_values: Already calculated metrics

        Returns:
            Calculated value
        """
        formula = metric.get('formula')
        if not formula:
            logger.warning(f"[MetricEngine] No formula for expression metric {metric.get('name')}")
            return None

        try:
            # Build evaluation context with calculated values
            # Create a safe namespace with only math operations and calculated metrics
            import math

            eval_context = {
                # Safe math functions
                'abs': abs,
                'min': min,
                'max': max,
                'round': round,
                'sqrt': math.sqrt,
                'pow': pow,

                # Add calculated metrics as variables
                **calculated_values
            }

            # Handle special functions in expressions
            # Example: "if operatingIncomeTTM >= 0 then null else ..."
            if 'if ' in formula.lower() and ' then ' in formula.lower():
                return self._evaluate_conditional(formula, calculated_values)

            # Evaluate the formula
            result = eval(formula, {"__builtins__": {}}, eval_context)

            return float(result) if result is not None else None

        except ZeroDivisionError:
            # Division by zero - return None
            logger.debug(f"[MetricEngine] Division by zero in {metric.get('name')}")
            return None
        except Exception as e:
            logger.debug(f"[MetricEngine] Failed to evaluate expression for {metric.get('name')}: {e}")
            logger.debug(f"[MetricEngine] Formula: {formula}")
            return None

    def _evaluate_conditional(self, formula: str, calculated_values: Dict[str, Any]) -> Any:
        """
        Evaluate conditional expression (if-then-else).

        Example: "if operatingIncomeTTM >= 0 then null else cashLast / abs(operatingIncomeTTM)"

        Args:
            formula: Conditional formula string
            calculated_values: Calculated metrics

        Returns:
            Result of conditional evaluation
        """
        import re

        # Parse: "if CONDITION then VALUE1 else VALUE2"
        pattern = r'if\s+(.+?)\s+then\s+(.+?)\s+else\s+(.+)'
        match = re.match(pattern, formula, re.IGNORECASE)

        if not match:
            logger.warning(f"[MetricEngine] Invalid conditional format: {formula}")
            return None

        condition_str = match.group(1).strip()
        then_value_str = match.group(2).strip()
        else_value_str = match.group(3).strip()

        try:
            import math

            eval_context = {
                'abs': abs,
                'min': min,
                'max': max,
                'round': round,
                'sqrt': math.sqrt,
                'pow': pow,
                **calculated_values
            }

            # Evaluate condition
            condition_result = eval(condition_str, {"__builtins__": {}}, eval_context)

            # Return appropriate value
            if condition_result:
                if then_value_str.lower() == 'null':
                    return None
                return eval(then_value_str, {"__builtins__": {}}, eval_context)
            else:
                if else_value_str.lower() == 'null':
                    return None
                return eval(else_value_str, {"__builtins__": {}}, eval_context)

        except Exception as e:
            logger.warning(f"[MetricEngine] Failed to evaluate conditional: {e}")
            return None

    def _group_by_domain(
        self,
        calculated_values: Dict[str, Any],
        target_domains: Optional[List[str]]
    ) -> Dict[str, Any]:
        """
        Group calculated metrics by domain.

        Args:
            calculated_values: All calculated metrics
            target_domains: Domains to include (filters out 'internal' domain)

        Returns:
            Dict grouped by domain with _meta information
        """
        result = {}

        for metric_name, value in calculated_values.items():
            metric = self.metrics_by_name.get(metric_name)
            if not metric:
                continue

            domain = metric.get('domain', '')
            if not domain or domain == 'internal':
                continue

            # Extract domain suffix
            domain_suffix = domain.split('-', 1)[1] if '-' in domain else domain

            # Filter by target domains
            if target_domains and domain_suffix not in target_domains:
                continue

            # Initialize domain group if needed
            if domain_suffix not in result:
                result[domain_suffix] = {}

            result[domain_suffix][metric_name] = value

        # Add _meta to each domain
        for domain_suffix in result:
            if '_meta' not in result[domain_suffix]:
                result[domain_suffix]['_meta'] = {
                    'date_range': None,
                    'calcType': 'TTM_fullQuarter',  # Placeholder
                    'count': 4  # Placeholder
                }

        return result

    def _lead_pair_from_list(
        self,
        base_values: List[Dict[str, Any]],
        params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Find previous record for the same partition and attach lead (previous) values.

        This aggregation is used for consensusSignal to track analyst's previous predictions.

        Workflow:
        1. Partition records by (ticker, analyst_name, analyst_company)
        2. Sort each partition by event_date (desc)
        3. For the most recent record, find the previous record
        4. Attach prev values from previous record

        Args:
            base_values: List of consensus records from evt_consensus
            params: {
                "partitionBy": ["ticker", "analyst_name", "analyst_company"],
                "orderBy": [{"event_date": "desc"}],
                "leadFields": [
                    {"field": "price_target", "as": "price_target_prev"},
                    {"field": "price_when_posted", "as": "price_when_posted_prev"}
                ],
                "emitPrevRow": true  # If true, also emit prev values
            }

        Returns:
            Dict with current record + prev field values, or None if no records
        """
        if not base_values:
            logger.warning("[MetricEngine] leadPairFromList: No base_values provided")
            return None

        # Ensure base_values is a list
        if not isinstance(base_values, list):
            base_values = [base_values]

        # Extract parameters
        partition_by = params.get('partitionBy', [])
        order_by = params.get('orderBy', [])
        lead_fields = params.get('leadFields', [])

        if not partition_by or not order_by or not lead_fields:
            logger.warning(
                f"[MetricEngine] leadPairFromList: Missing required params "
                f"(partitionBy={bool(partition_by)}, orderBy={bool(order_by)}, leadFields={bool(lead_fields)})"
            )
            return None

        # Group records by partition
        from collections import defaultdict
        partitions = defaultdict(list)

        for record in base_values:
            if not isinstance(record, dict):
                continue

            # Build partition key
            partition_key = tuple(record.get(field) for field in partition_by)
            partitions[partition_key].append(record)

        # Sort each partition
        for partition_key, records in partitions.items():
            # Extract sort field and direction from orderBy
            if order_by:
                sort_config = order_by[0]  # Use first sort config
                sort_field = list(sort_config.keys())[0]
                sort_direction = sort_config[sort_field]  # 'asc' or 'desc'

                records.sort(
                    key=lambda r: r.get(sort_field, ''),
                    reverse=(sort_direction == 'desc')
                )

        # Find the most recent record (first record in first partition after sorting)
        if not partitions:
            logger.warning("[MetricEngine] leadPairFromList: No partitions created")
            return None

        # Get first partition (arbitrary, should be configured to select specific partition)
        first_partition_key = next(iter(partitions))
        sorted_records = partitions[first_partition_key]

        if len(sorted_records) == 0:
            logger.warning("[MetricEngine] leadPairFromList: No records in partition")
            return None

        # Most recent record
        current_record = sorted_records[0].copy()

        # Find previous record (if exists)
        if len(sorted_records) > 1:
            prev_record = sorted_records[1]

            # Attach lead fields from previous record
            for lead_config in lead_fields:
                source_field = lead_config.get('field')
                target_field = lead_config.get('as', f"{source_field}_prev")

                prev_value = prev_record.get(source_field)
                current_record[target_field] = prev_value

            # Optionally include prev record as nested dict
            if params.get('emitPrevRow', False):
                current_record['_prev'] = prev_record
        else:
            # No previous record - set prev fields to None
            for lead_config in lead_fields:
                target_field = lead_config.get('as', f"{lead_config.get('field')}_prev")
                current_record[target_field] = None

            if params.get('emitPrevRow', False):
                current_record['_prev'] = None

        logger.info(
            f"[MetricEngine] leadPairFromList: Processed {len(sorted_records)} records, "
            f"attached {len(lead_fields)} lead fields"
        )

        return current_record
