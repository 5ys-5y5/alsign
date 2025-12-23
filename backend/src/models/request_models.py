"""Request models for API endpoints."""

from pydantic import BaseModel, Field, validator, ConfigDict
from typing import Optional, List
from datetime import date


class SourceDataQueryParams(BaseModel):
    """
    Query parameters for GET /sourceData endpoint.

    Supports selective mode execution and consensus maintenance mode.
    """

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

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
        description="Consensus Phase 2 calculation mode: 'maintenance' for scope-based recalculation. If unset, only affected partitions."
    )

    calc_scope: Optional[str] = Field(
        default=None,
        description="Required when calc_mode=maintenance. One of: all, ticker, event_date_range, partition_keys"
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
        if v is not None and v != 'maintenance':
            raise ValueError("calc_mode must be 'maintenance' or unset")
        return v

    @validator('calc_scope')
    def validate_calc_scope(cls, v, values):
        """Validate calc_scope parameter."""
        calc_mode = values.get('calc_mode')

        # calc_scope requires calc_mode=maintenance
        if v is not None and calc_mode != 'maintenance':
            raise ValueError("calc_scope requires calc_mode=maintenance")

        # If calc_mode=maintenance, calc_scope is required
        if calc_mode == 'maintenance' and v is None:
            raise ValueError("calc_scope is required when calc_mode=maintenance")

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


class BackfillEventsTableQueryParams(BaseModel):
    """Query parameters for POST /backfillEventsTable endpoint."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    overwrite: bool = Field(
        default=False,
        description="If false, partially update NULL values within value_* jsonb. If true, fully replace value_* fields."
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
