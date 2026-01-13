"""Request models for API endpoints."""

from pydantic import BaseModel, Field, validator, ConfigDict
from typing import Optional, List
from datetime import date

# Maximum batch size for backfillEventsTable to prevent memory exhaustion
# Based on Supabase free tier limitations (1GB RAM, 60 connections)
MAX_BACKFILL_BATCH_SIZE = 2000


class SourceDataQueryParams(BaseModel):
    """
    Query parameters for GET /sourceData endpoint.

    Supports selective mode execution and consensus maintenance mode.
    """

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    overwrite: bool = Field(
        default=False,
        description="If false, update only NULL values. If true, overwrite existing data."
    )

    mode: Optional[str] = Field(
        default=None,
        description="Comma-separated list of modes: holiday, target, consensus, earning. If unspecified, executes all in default order."
    )

    past: bool = Field(
        default=False,
        description="If true and mode includes 'earning', fetch past 5 years + future 28 days. Only effective for earning mode."
    )

    calc_mode: Optional[str] = Field(
        default=None,
        description="Consensus calculation mode: 'maintenance' (Phase 1+2 with scope), 'calculation' (Phase 2 only, no API calls). If unset, Phase 1+2 for affected partitions."
    )

    calc_scope: Optional[str] = Field(
        default=None,
        description="Required when calc_mode=maintenance or calculation. One of: all, ticker, event_date_range, partition_keys"
    )

    tickers: Optional[str] = Field(
        default=None,
        description="Required when calc_scope=ticker. Comma-separated ticker symbols."
    )

    from_date: Optional[date] = Field(
        default=None,
        alias="from",
        serialization_alias="from",
        description="Required when calc_scope=event_date_range. Start date (YYYY-MM-DD)."
    )

    to_date: Optional[date] = Field(
        default=None,
        alias="to",
        serialization_alias="to",
        description="Required when calc_scope=event_date_range. End date (YYYY-MM-DD)."
    )

    partitions: Optional[str] = Field(
        default=None,
        description="Required when calc_scope=partition_keys. JSON array of {ticker, analyst_name, analyst_company} objects."
    )

    max_workers: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of concurrent workers (1-100). Lower values reduce DB CPU load. Default: 20. Recommended: 10-30."
    )

    @validator('mode')
    def validate_mode(cls, v):
        """Validate mode parameter contains only allowed values."""
        if v is None:
            return v

        allowed_modes = {'holiday', 'target', 'consensus', 'earning'}
        modes = [m.strip() for m in v.split(',')]

        for mode in modes:
            if mode not in allowed_modes:
                raise ValueError(f"Invalid mode '{mode}'. Allowed: {', '.join(allowed_modes)}")

        return v

    @validator('calc_mode')
    def validate_calc_mode(cls, v):
        """Validate calc_mode parameter."""
        allowed_modes = {'maintenance', 'calculation'}
        if v is not None and v not in allowed_modes:
            raise ValueError(f"calc_mode must be one of: {', '.join(allowed_modes)}")
        return v

    @validator('calc_scope')
    def validate_calc_scope(cls, v, values):
        """Validate calc_scope parameter."""
        calc_mode = values.get('calc_mode')

        # calc_scope requires calc_mode=maintenance or calculation
        if v is not None and calc_mode not in ('maintenance', 'calculation'):
            raise ValueError("calc_scope requires calc_mode=maintenance or calc_mode=calculation")

        # If calc_mode=maintenance or calculation, calc_scope is required
        if calc_mode in ('maintenance', 'calculation') and v is None:
            raise ValueError(f"calc_scope is required when calc_mode={calc_mode}")

        # Validate allowed values
        if v is not None:
            allowed_scopes = {'all', 'ticker', 'event_date_range', 'partition_keys'}
            if v not in allowed_scopes:
                raise ValueError(f"Invalid calc_scope '{v}'. Allowed: {', '.join(allowed_scopes)}")

        return v

    @validator('tickers')
    def validate_tickers(cls, v, values):
        """Validate tickers parameter when calc_scope=ticker."""
        calc_scope = values.get('calc_scope')

        if calc_scope == 'ticker' and not v:
            raise ValueError("tickers parameter is required when calc_scope=ticker")

        return v

    @validator('from_date')
    def validate_from_date(cls, v, values):
        """Validate from_date parameter when calc_scope=event_date_range."""
        calc_scope = values.get('calc_scope')

        if calc_scope == 'event_date_range' and v is None:
            raise ValueError("from parameter is required when calc_scope=event_date_range")

        return v

    @validator('to_date')
    def validate_to_date(cls, v, values):
        """Validate to_date parameter when calc_scope=event_date_range."""
        calc_scope = values.get('calc_scope')

        if calc_scope == 'event_date_range' and v is None:
            raise ValueError("to parameter is required when calc_scope=event_date_range")

        return v

    @validator('partitions')
    def validate_partitions(cls, v, values):
        """Validate partitions parameter when calc_scope=partition_keys."""
        calc_scope = values.get('calc_scope')

        if calc_scope == 'partition_keys' and not v:
            raise ValueError("partitions parameter is required when calc_scope=partition_keys")

        # Try to parse JSON if provided
        if v:
            import json
            try:
                partitions = json.loads(v)
                if not isinstance(partitions, list):
                    raise ValueError("partitions must be a JSON array")

                for partition in partitions:
                    if not isinstance(partition, dict):
                        raise ValueError("Each partition must be an object")
                    if 'ticker' not in partition:
                        raise ValueError("Each partition must have 'ticker' key")

            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in partitions parameter: {e}")

        return v

    def get_mode_list(self) -> List[str]:
        """
        Get list of modes to execute in default order.

        Returns:
            List of mode strings in default execution order
        """
        default_order = ['holiday', 'target', 'consensus', 'earning']

        if self.mode is None:
            # Execute all modes
            return default_order

        # Parse and deduplicate
        requested_modes = list(dict.fromkeys([m.strip() for m in self.mode.split(',')]))

        # Return in default order
        return [mode for mode in default_order if mode in requested_modes]


class SetEventsTableQueryParams(BaseModel):
    """Query parameters for POST /setEventsTable endpoint."""

    overwrite: bool = Field(
        default=False,
        description="If false, update only NULL sector/industry. If true, update both NULL and mismatched."
    )

    dryRun: bool = Field(
        default=False,
        description="If true, return projected changes without modifying database."
    )

    schema: str = Field(
        default="public",
        description="Target schema to search for evt_* tables."
    )

    table: Optional[str] = Field(
        default=None,
        description="Comma-separated list of specific evt_* tables to process."
    )

    cleanup_mode: Optional[str] = Field(
        default=None,
        description="Cleanup mode for invalid tickers (not in config_lv3_targets): 'preview' (show what will be deleted), 'archive' (move to txn_events_archived), 'delete' (permanent deletion). If not specified, no cleanup is performed."
    )

    max_workers: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of concurrent workers (1-100). Lower values reduce DB CPU load. Default: 20. Recommended: 10-30."
    )

    @validator('table')
    def validate_table(cls, v):
        """Validate table parameter matches evt_* pattern."""
        if v is None:
            return v

        tables = [t.strip() for t in v.split(',')]
        for table in tables:
            if not table.startswith('evt_'):
                raise ValueError(f"Table '{table}' does not match required evt_* pattern")

        return v

    @validator('cleanup_mode')
    def validate_cleanup_mode(cls, v):
        """Validate cleanup_mode parameter."""
        if v is not None:
            allowed_modes = {'preview', 'archive', 'delete'}
            if v not in allowed_modes:
                raise ValueError(f"cleanup_mode must be one of: {', '.join(allowed_modes)}")
        return v


class BackfillEventsTableQueryParams(BaseModel):
    """Query parameters for POST /backfillEventsTable endpoint."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    overwrite: bool = Field(
        default=False,
        description="If false, update only NULL values. If true, overwrite existing values. When used with 'metrics' parameter: applies to specified metrics only. When used without 'metrics': applies to all value_* JSONB fields."
    )
    from_date: Optional[date] = Field(
        default=None,
        alias="from",
        description="Start date for filtering events by event_date. If not specified, no lower bound is applied."
    )
    to_date: Optional[date] = Field(
        default=None,
        alias="to",
        description="End date for filtering events by event_date. If not specified, no upper bound is applied."
    )
    tickers: Optional[str] = Field(
        default=None,
        description="Comma-separated list of ticker symbols to process (e.g., 'AAPL,MSFT,GOOGL'). If not specified, processes all tickers."
    )
    table: Optional[str] = Field(
        default=None,
        description="Comma-separated list of source tables for price trends. Allowed: txn_events, txn_trades. If not specified, both tables are processed."
    )
    start_point: Optional[str] = Field(
        default=None,
        alias="startPoint",
        description="Start ticker (alphabetical) to resume processing from this point. Applies to the ordered ticker list."
    )
    metrics: Optional[str] = Field(
        default=None,
        description="Comma-separated list of metric IDs to recalculate (e.g., 'priceQuantitative,PER,PBR'). If not specified, all metrics are calculated. When specified with overwrite=true, overwrites existing values; with overwrite=false, updates only NULL values. (I-41)"
    )
    batch_size: Optional[int] = Field(
        default=None,
        ge=1,
        le=MAX_BACKFILL_BATCH_SIZE,
        description=f"BATCH PROCESSING: Number of unique tickers to process per batch. Each ticker in the batch is processed concurrently (up to max_workers), equivalent to running per-ticker requests in parallel. Range: 1-{MAX_BACKFILL_BATCH_SIZE}. Maximum enforced for Supabase free tier (1GB RAM). Example: batch_size=500 processes 500 tickers at a time until all are done. Use 200-1000 for optimal memory usage. (CRITICAL for large datasets)"
    )

    max_workers: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of concurrent workers (1-100). Lower values reduce DB CPU load. Default: 20. Recommended: 10-30."
    )

    def get_ticker_list(self) -> Optional[List[str]]:
        """
        Parse tickers parameter into a list of ticker symbols.

        Returns:
            List of ticker symbols, or None if tickers parameter is not provided
        """
        if self.tickers is None:
            return None

        # Remove brackets if present and split by comma
        tickers_str = self.tickers.strip()
        if tickers_str.startswith('[') and tickers_str.endswith(']'):
            tickers_str = tickers_str[1:-1]

        # Split by comma and clean up whitespace
        ticker_list = [t.strip().upper() for t in tickers_str.split(',') if t.strip()]

        return ticker_list if ticker_list else None

    def get_table_list(self) -> Optional[List[str]]:
        """
        Parse table parameter into a list of source table names.

        Returns:
            List of table names (lowercase), or None if not provided
        """
        if self.table is None:
            return None

        tables = [t.strip().lower() for t in self.table.split(',') if t.strip()]
        return tables if tables else None

    def get_start_point(self) -> Optional[str]:
        """
        Normalize startPoint parameter into a ticker symbol.

        Returns:
            Uppercased ticker string or None if not provided
        """
        if not self.start_point:
            return None

        start_point = self.start_point.strip().upper()
        return start_point if start_point else None

    @validator('table')
    def validate_price_trend_table(cls, v):
        """Validate table parameter for price trend source tables."""
        if v is None:
            return v

        allowed = {'txn_events', 'txn_trades'}
        tables = [t.strip().lower() for t in v.split(',') if t.strip()]

        for table in tables:
            if table not in allowed:
                raise ValueError(f"table must be one of: {', '.join(sorted(allowed))}")

        return ",".join(tables)

    @validator('batch_size')
    def validate_batch_size(cls, v):
        """Enforce maximum batch size for Supabase free tier."""
        if v is not None and v > MAX_BACKFILL_BATCH_SIZE:
            # Automatically cap at maximum instead of raising error
            return MAX_BACKFILL_BATCH_SIZE
        return v

    def get_metrics_list(self) -> Optional[List[str]]:
        """
        Parse metrics parameter into a list of metric IDs.

        Returns:
            List of metric IDs, or None if metrics parameter is not provided

        Example:
            'priceQuantitative,PER,PBR' -> ['priceQuantitative', 'PER', 'PBR']
        """
        if self.metrics is None:
            return None

        # Remove brackets if present and split by comma
        metrics_str = self.metrics.strip()
        if metrics_str.startswith('[') and metrics_str.endswith(']'):
            metrics_str = metrics_str[1:-1]

        # Split by comma and clean up whitespace
        metrics_list = [m.strip() for m in metrics_str.split(',') if m.strip()]

        return metrics_list if metrics_list else None


class FillAnalystQueryParams(BaseModel):
    """Query parameters for POST /fillAnalyst endpoint."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    overwrite: bool = Field(
        default=False,
        description="If false, update only NULL values in analyst performance data. If true, recalculate all metrics."
    )

    max_workers: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of concurrent workers (1-100). Lower values reduce DB CPU load. Default: 20. Recommended: 10-30."
    )


class QuantitativesQueryParams(BaseModel):
    """Query parameters for POST /getQuantitatives endpoint."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    overwrite: bool = Field(
        default=False,
        description="If true, refetch all APIs even if data exists. If false, skip APIs with existing data."
    )

    apis: Optional[str] = Field(
        default=None,
        description="Comma-separated list of APIs to fetch. Available: ratios,key-metrics,cash-flow,balance-sheet,market-cap,price,income,quote. If not specified, fetches all APIs."
    )

    tickers: Optional[str] = Field(
        default=None,
        description="Comma-separated list of tickers to process. Only tickers that exist in config_lv3_targets (ticker or peer column) will be processed. If not specified, processes all targets and their peers."
    )

    max_workers: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of concurrent workers (1-100). Lower values reduce DB CPU load. Default: 20. Recommended: 10-30."
    )

    def get_api_list(self) -> Optional[List[str]]:
        """
        Parse apis parameter into a list of API names.

        Returns:
            List of API names, or None if apis parameter is not provided
        """
        if self.apis is None:
            return None

        # Split by comma and clean up whitespace
        api_list = [api.strip() for api in self.apis.split(',') if api.strip()]

        return api_list if api_list else None

    def get_ticker_list(self) -> Optional[List[str]]:
        """
        Parse tickers parameter into a list of ticker symbols.

        Returns:
            List of ticker symbols, or None if tickers parameter is not provided
        """
        if self.tickers is None:
            return None

        # Remove brackets if present and split by comma
        tickers_str = self.tickers.strip()
        if tickers_str.startswith('[') and tickers_str.endswith(']'):
            tickers_str = tickers_str[1:-1]

        # Split by comma and clean up whitespace
        ticker_list = [t.strip().upper() for t in tickers_str.split(',') if t.strip()]

        return ticker_list if ticker_list else None


class TradeRecord(BaseModel):
    """Individual trade record for bulk insertion."""

    model_config = ConfigDict(extra='forbid')

    ticker: str = Field(
        ...,
        description="Stock ticker symbol (e.g., AAPL, MSFT)"
    )

    trade_date: date = Field(
        ...,
        description="Date when the trade was executed (YYYY-MM-DD)"
    )

    model: str = Field(
        default='default',
        description="Trading model/strategy identifier"
    )

    source: Optional[str] = Field(
        default=None,
        description="Event source: 'consensus' or 'earning'"
    )

    position: Optional[str] = Field(
        default=None,
        description="Trade position: 'long', 'short', or 'neutral'"
    )

    entry_price: Optional[float] = Field(
        default=None,
        description="Entry price (optional)"
    )

    exit_price: Optional[float] = Field(
        default=None,
        description="Exit price (optional)"
    )

    quantity: Optional[int] = Field(
        default=None,
        description="Trade quantity (optional)"
    )

    notes: Optional[str] = Field(
        default=None,
        description="Additional notes (optional)"
    )

    @validator('source')
    def validate_source(cls, v):
        """Validate source parameter."""
        if v is not None and v not in ('consensus', 'earning'):
            raise ValueError("source must be 'consensus' or 'earning'")
        return v

    @validator('position')
    def validate_position(cls, v):
        """Validate position parameter."""
        if v is not None and v not in ('long', 'short', 'neutral'):
            raise ValueError("position must be 'long', 'short', or 'neutral'")
        return v


class BulkTradesRequest(BaseModel):
    """Request body for POST /trades endpoint."""

    model_config = ConfigDict(extra='forbid')

    trades: List[TradeRecord] = Field(
        ...,
        description="List of trade records to insert"
    )
