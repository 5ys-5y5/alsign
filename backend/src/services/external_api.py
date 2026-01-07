"""External API client with DB-based dynamic API configuration."""

import httpx
import logging
import re
from typing import Dict, Any, Optional, List
from ..config import settings
from .utils.batch_utils import RateLimiter
from ..database.connection import db_pool
from ..database.queries import api_config
from ..utils.logging_utils import log_error, log_warning

logger = logging.getLogger("alsign")


class FMPAPIClient:
    """
    Financial Modeling Prep API client with DB-based configuration.

    Reads API configurations from config_lv1_api_list table and dynamically
    constructs requests with schema mapping.
    """

    def __init__(self):
        """Initialize FMP API client."""
        self.rate_limiter = RateLimiter(settings.FMP_RATE_LIMIT)
        self.client: Optional[httpx.AsyncClient] = None
        self._api_key_cache: Optional[str] = None
        self._usage_per_min_cache: Optional[int] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=30.0),
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)
        )
        await self._load_service_config()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()

    async def _load_service_config(self) -> None:
        """
        Load API service config and update rate limiter.
        """
        if self._api_key_cache and self._usage_per_min_cache:
            return

        pool = await db_pool.get_pool()
        service_config = await api_config.get_api_service_config(pool, 'financialmodelingprep')

        if not service_config or not service_config.get('apiKey'):
            raise ValueError("FMP API key not found in config_lv1_api_service")

        self._api_key_cache = service_config['apiKey']
        usage_per_min = service_config.get('usagePerMin')
        if isinstance(usage_per_min, int) and usage_per_min > 0:
            self._usage_per_min_cache = usage_per_min
            self.rate_limiter.calls_per_minute = usage_per_min
        else:
            self._usage_per_min_cache = self.rate_limiter.calls_per_minute

    async def _get_api_key(self) -> str:
        """
        Get API key from config_lv1_api_service table.

        Returns:
            API key string

        Raises:
            ValueError: If API key not found
        """
        if not self._api_key_cache:
            await self._load_service_config()

        return self._api_key_cache

    def _apply_schema_mapping(self, data: Any, schema: Dict[str, str]) -> Any:
        """
        Apply schema mapping to API response data.

        Converts API field names to internal standard field names.
        Supports both simple string mappings and complex nested object/array mappings.

        Args:
            data: API response (dict or list of dicts)
            schema: Schema mapping (internal_name: api_field_name or nested schema)

        Returns:
            Mapped data with standardized field names
        """
        if not schema:
            return data

        # Handle case where schema is still a JSON string
        import json
        if isinstance(schema, str):
            schema = json.loads(schema)

        # Build reverse mapping for simple fields only
        reverse_schema = {}
        nested_schemas = {}

        for internal_name, mapping_value in schema.items():
            if isinstance(mapping_value, dict):
                # This is a nested schema (for arrays/objects)
                api_field = mapping_value.get('value')
                if api_field:
                    nested_schemas[api_field] = {
                        'internal_name': internal_name,
                        'type': mapping_value.get('type'),
                        'items': mapping_value.get('items', {})
                    }
            elif isinstance(mapping_value, str):
                # Simple string mapping
                reverse_schema[mapping_value] = internal_name

        def map_array_items(items: List[Any], item_schema: Dict[str, Any]) -> List[Any]:
            """Map items in an array using the item schema."""
            mapped_items = []
            for item in items:
                if isinstance(item, dict):
                    mapped_item = {}
                    for field_name, field_spec in item_schema.items():
                        if isinstance(field_spec, dict):
                            api_field_name = field_spec.get('value')
                            if api_field_name and api_field_name in item:
                                mapped_item[field_name] = item[api_field_name]
                    mapped_items.append(mapped_item)
                else:
                    # Item is not a dict, keep as-is
                    mapped_items.append(item)
            return mapped_items

        def map_item(item: Dict[str, Any]) -> Dict[str, Any]:
            """Map a single item."""
            mapped = {}

            for api_field, value in item.items():
                # Check if this is a nested field
                if api_field in nested_schemas:
                    nested_info = nested_schemas[api_field]
                    internal_name = nested_info['internal_name']

                    if nested_info['type'] == 'array' and isinstance(value, list):
                        # Map array items
                        mapped[internal_name] = map_array_items(value, nested_info['items'])
                    else:
                        # Keep as-is for other nested types
                        mapped[internal_name] = value
                else:
                    # Simple field mapping
                    internal_field = reverse_schema.get(api_field, api_field)
                    mapped[internal_field] = value

            return mapped

        if isinstance(data, list):
            return [map_item(item) for item in data]
        elif isinstance(data, dict):
            return map_item(data)
        else:
            return data

    def _substitute_url_template(self, url_template: str, variables: Dict[str, Any]) -> str:
        """
        Substitute variables in URL template.

        Replaces {variable_name} with actual values.

        Args:
            url_template: URL with {placeholders}
            variables: Dict of variable values

        Returns:
            URL with substituted values
        """
        # Find all {variable} patterns
        pattern = r'\{(\w+)\}'

        def replace_var(match):
            var_name = match.group(1)
            value = variables.get(var_name)
            if value is None:
                logger.warning(f"URL template variable '{var_name}' not provided, keeping placeholder")
                return match.group(0)
            return str(value)

        return re.sub(pattern, replace_var, url_template)

    async def call_api(
        self,
        api_id: str,
        variables: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None
    ) -> Any:
        """
        Call API using DB configuration.

        Args:
            api_id: API identifier in config_lv1_api_list (e.g., 'fmp-company-screener')
            variables: Variables for URL template substitution (e.g., {'ticker': 'AAPL', 'fromDate': '2024-01-01'})
            event_id: Optional txn_events.id for tracing (e.g., '86f110f9-43a9-4a32-8600-c95daff9565d')

        Returns:
            API response with schema mapping applied

        Raises:
            ValueError: If API config not found
            httpx.HTTPStatusError: If request fails
        """
        # Get API configuration from DB
        pool = await db_pool.get_pool()
        config = await api_config.get_api_config_by_id(pool, api_id)

        if not config:
            raise ValueError(f"API configuration not found: {api_id}")

        # Get API key and ensure rate limit is configured
        api_key = await self._get_api_key()

        # Prepare variables for substitution
        substitution_vars = variables.copy() if variables else {}
        substitution_vars['apiKey'] = api_key

        # Substitute URL template
        url = self._substitute_url_template(config['api'], substitution_vars)

        # Build row context for tracing
        row_context = f"[table: txn_events | id: {event_id}]" if event_id else "[no event context]"

        logger.info(f"{row_context} | [API Call] {api_id} -> {url}")

        # Wait for rate limiter
        await self.rate_limiter.acquire()

        # Make request
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            logger.info(f"{row_context} | [API Response] {api_id} -> HTTP {response.status_code}")
        except Exception as e:
            log_error(logger, f"{row_context} | API call failed: {api_id}", exception=e)
            raise

        # Parse response
        try:
            data = response.json()
            data_type = type(data).__name__
            data_len = len(data) if isinstance(data, (list, dict)) else 0
            logger.info(f"{row_context} | [API Parse] {api_id} -> Type: {data_type}, Length: {data_len}")
        except Exception as e:
            log_error(logger, f"{row_context} | API parse failed: {api_id}", exception=e)
            raise

        # Apply schema mapping
        schema = config.get('schema')
        if schema:
            try:
                data = self._apply_schema_mapping(data, schema)
                mapped_len = len(data) if isinstance(data, (list, dict)) else 0
                logger.info(f"{row_context} | [Schema Mapping] {api_id} -> Mapped {mapped_len} items")
            except Exception as e:
                log_error(logger, f"Schema mapping failed: {api_id} (schema type: {type(schema).__name__})", exception=e)
                raise

        return data

    # Legacy wrapper methods for backward compatibility
    # These will call the DB-based call_api method

    async def get_market_holidays(self, exchange: str = "NASDAQ") -> List[Dict[str, Any]]:
        """
        Fetch market holidays using DB config.

        Args:
            exchange: Exchange identifier (default: NASDAQ)

        Returns:
            List of holiday dictionaries
        """
        try:
            result = await self.call_api('fmp-holidays-by-exchange', {'exchange': exchange})
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Failed to fetch market holidays: {str(e)}", exc_info=True)
            return []

    async def get_company_screener(self, limit: int = 30000) -> List[Dict[str, Any]]:
        """
        Fetch company screener data using DB config.

        Args:
            limit: Maximum number of companies to fetch (ignored - uses DB config limit)

        Returns:
            List of company dictionaries with schema mapping applied
        """
        logger.info("=" * 80)
        logger.info("[get_company_screener] FUNCTION START")
        logger.info(f"[get_company_screener] Parameters: limit={limit}")
        logger.info("=" * 80)

        try:
            logger.info("[get_company_screener] Step 1: Calling self.call_api('fmp-company-screener')")
            result = await self.call_api('fmp-company-screener')

            logger.info(f"[get_company_screener] Step 2: call_api returned - Type: {type(result)}")

            if isinstance(result, list):
                logger.info(f"[get_company_screener] Step 3: Result is a list with {len(result)} items")
                if result:
                    logger.info(f"[get_company_screener] First item type: {type(result[0])}")
                    logger.info(f"[get_company_screener] First item keys: {list(result[0].keys()) if isinstance(result[0], dict) else 'N/A'}")
                    logger.info(f"[get_company_screener] First item sample: {str(result[0])[:200]}")
                logger.info("=" * 80)
                logger.info(f"[get_company_screener] FUNCTION END - SUCCESS: {len(result)} companies")
                logger.info("=" * 80)
                return result
            else:
                logger.error("=" * 80)
                logger.error(f"[get_company_screener] CRITICAL ERROR: Result is not a list")
                logger.error(f"[get_company_screener] Type: {type(result)}")
                logger.error(f"[get_company_screener] Value: {str(result)[:500]}")
                logger.error("=" * 80)
                logger.error(f"[get_company_screener] FUNCTION END - FAILED: Returning empty list")
                logger.error("=" * 80)
                return []
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"[get_company_screener] EXCEPTION: {type(e).__name__}")
            logger.error(f"[get_company_screener] Exception message: {str(e)}")
            logger.error(f"[get_company_screener] Full stack trace:", exc_info=True)
            logger.error("=" * 80)
            logger.error(f"[get_company_screener] FUNCTION END - EXCEPTION: Returning empty list")
            logger.error("=" * 80)
            return []

    async def get_price_target_consensus(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Fetch price target consensus using DB config.

        Args:
            ticker: Stock ticker symbol

        Returns:
            List of consensus data dictionaries (multiple analysts per ticker)
        """
        try:
            result = await self.call_api('fmp-price-target', {'ticker': ticker})

            # API returns a list of consensus from different analysts
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return [result]
            else:
                return []
        except Exception as e:
            logger.error(f"Failed to fetch consensus for {ticker}: {str(e)}", exc_info=True)
            return []

    async def get_earnings_calendar(self, from_date: str, to_date: str) -> List[Dict[str, Any]]:
        """
        Fetch earnings calendar using DB config.

        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            List of earnings event dictionaries
        """
        try:
            result = await self.call_api('fmp-earnings-calendar', {
                'fromDate': from_date,
                'toDate': to_date
            })
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Failed to fetch earnings calendar: {str(e)}", exc_info=True)
            return []

    async def get_historical_price_eod(
        self,
        ticker: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical end-of-day OHLC prices using DB config.

        Args:
            ticker: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            List of OHLC data dictionaries
        """
        try:
            result = await self.call_api('fmp-historical-price-eod-full', {
                'ticker': ticker,
                'fromDate': from_date,
                'toDate': to_date
            })

            # FMP returns {symbol, historical: [...]}
            if isinstance(result, dict) and 'historical' in result:
                return result['historical']
            elif isinstance(result, list):
                return result
            else:
                return []
        except Exception as e:
            logger.error(f"Failed to fetch OHLC for {ticker}: {str(e)}", exc_info=True)
            return []

    async def get_income_statement(
        self,
        ticker: str,
        period: str = 'annual',
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch income statement data using DB config.

        Args:
            ticker: Stock ticker symbol
            period: 'annual' or 'quarter'
            limit: Number of periods to fetch

        Returns:
            List of income statement dictionaries
        """
        try:
            result = await self.call_api('fmp-income-statement', {
                'ticker': ticker,
                'period': period,
                'limit': limit
            })
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Failed to fetch income statement for {ticker}: {str(e)}", exc_info=True)
            return []

    async def get_balance_sheet(
        self,
        ticker: str,
        period: str = 'annual',
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch balance sheet data using DB config.

        Args:
            ticker: Stock ticker symbol
            period: 'annual' or 'quarter'
            limit: Number of periods to fetch

        Returns:
            List of balance sheet dictionaries
        """
        try:
            result = await self.call_api('fmp-balance-sheet-statement', {
                'ticker': ticker,
                'period': period,
                'limit': limit
            })
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Failed to fetch balance sheet for {ticker}: {str(e)}", exc_info=True)
            return []

    async def get_cash_flow(
        self,
        ticker: str,
        period: str = 'annual',
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch cash flow statement data using DB config.

        Args:
            ticker: Stock ticker symbol
            period: 'annual' or 'quarter'
            limit: Number of periods to fetch

        Returns:
            List of cash flow statement dictionaries
        """
        try:
            result = await self.call_api('fmp-cash-flow-statement', {
                'ticker': ticker,
                'period': period,
                'limit': limit
            })
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Failed to fetch cash flow for {ticker}: {str(e)}", exc_info=True)
            return []

    async def get_quote(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Fetch current quote/market data using DB config.

        Args:
            ticker: Stock ticker symbol

        Returns:
            List with single quote dictionary containing marketCap, price, etc.
        """
        try:
            result = await self.call_api('fmp-quote', {
                'ticker': ticker
            })
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Failed to fetch quote for {ticker}: {str(e)}", exc_info=True)
            return []

    def get_current_rate(self) -> int:
        """Get current API call rate."""
        return self.rate_limiter.get_current_rate()

    def get_rate_limit(self) -> int:
        """Get maximum API call rate."""
        return self.rate_limiter.calls_per_minute

    def get_usage_percentage(self) -> float:
        """Get current usage as percentage of rate limit."""
        return self.rate_limiter.get_usage_percentage()
