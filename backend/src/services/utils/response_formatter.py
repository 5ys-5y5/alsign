"""Response formatting utilities for better readability."""

from typing import Dict, Any, List, Optional


def format_value_quantitative(value_quant: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform value_quantitative response to separate "values" and "dateInfo".
    
    Original format:
    {
        "risk": {
            "_meta": { "sources": {...}, "calcType": "...", "count": 4 },
            "currentRatio": 0.79,
            "cashToRevenueTTM": 0.17
        }
    }
    
    Transformed format:
    {
        "risk": {
            "values": {
                "currentRatio": 0.79,
                "cashToRevenueTTM": 0.17
            },
            "dateInfo": {
                "calcType": "TTM_fullQuarter",
                "dateRange": "2021-03-31 ~ 2021-12-31",
                "count": 4,
                "metrics": {
                    "currentRatio": {
                        "formula": "totalCurrentAssetsLast / totalCurrentLiabilitiesLast",
                        "dataSources": {...}
                    }
                }
            }
        }
    }
    
    Args:
        value_quant: Original value_quantitative dictionary
        
    Returns:
        Transformed dictionary with "values" and "dateInfo" sections
    """
    if not value_quant:
        return None
    
    result = {}
    
    for domain_key, domain_data in value_quant.items():
        if not isinstance(domain_data, dict):
            result[domain_key] = domain_data
            continue
        
        # Extract metrics (non-_meta keys)
        metrics = {}
        meta_info = domain_data.get('_meta', {})
        
        for key, value in domain_data.items():
            if key != '_meta':
                metrics[key] = value
        
        # Build simplified reference date info
        reference_dates = _build_reference_dates(meta_info, metrics.keys())
        
        result[domain_key] = {
            "values": metrics,
            "dateInfo": reference_dates
        }
    
    return result


def _build_reference_dates(meta: Dict[str, Any], metric_names: List[str]) -> Dict[str, Any]:
    """
    Build simplified reference date information from _meta.
    
    Args:
        meta: The _meta object containing sources and date info
        metric_names: List of metric names in this domain
        
    Returns:
        Simplified reference date dictionary
    """
    sources = meta.get('sources', {})
    
    # Common info
    result = {
        "calcType": meta.get('calcType', 'unknown'),
        "count": meta.get('count', 0),
    }
    
    # Add date range if available
    date_range = meta.get('date_range')
    if date_range:
        if isinstance(date_range, dict):
            start = date_range.get('start', '')
            end = date_range.get('end', '')
            result["dateRange"] = f"{start} ~ {end}"
        else:
            result["dateRange"] = str(date_range)
    elif meta.get('dateRange'):
        result["dateRange"] = meta.get('dateRange')
    
    # Build per-metric date info
    metrics_info = {}
    for metric_name in metric_names:
        metric_source = sources.get(metric_name, {})
        metric_info = _extract_metric_dates(metric_source)
        if metric_info:
            metrics_info[metric_name] = metric_info
    
    if metrics_info:
        result["metrics"] = metrics_info
    
    return result


def _extract_metric_dates(source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract simplified date information from a metric source definition.
    
    Args:
        source: Source definition for a metric
        
    Returns:
        Simplified metric date info or None
    """
    if not source:
        return None
    
    source_type = source.get('type')
    
    if source_type == 'expression':
        # Expression metric - extract formula and data sources
        formula = source.get('formula', '')
        
        # Collect unique data sources and their dates (recursively)
        data_sources = {}
        nested_sources = source.get('sources', {})
        
        _collect_data_sources_recursive(nested_sources, data_sources)
        
        result = {
            "formula": formula,
        }
        
        if data_sources:
            result["dataSources"] = {}
            for api, info in data_sources.items():
                api_short = api.replace('fmp-', '')
                source_info = {
                    "dates": info['dates'],
                    "transforms": list(info['transforms'])
                }
                # Mark single-date sources (like marketCap)
                if info.get('useSingleDate'):
                    source_info["note"] = "uses single date (event_date basis)"
                result["dataSources"][api_short] = source_info
        
        return result
    
    elif source_type == 'aggregation':
        # Aggregation metric
        dates = source.get('dates', [])
        transform = source.get('transform', '')
        base_metric = source.get('baseMetric', '')
        api = source.get('api', '').replace('fmp-', '')
        
        return {
            "transform": transform,
            "baseMetric": base_metric,
            "api": api,
            "dates": dates[:4] if len(dates) > 4 else dates
        }
    
    elif source_type == 'api_field':
        # Direct API field
        api = source.get('api', '').replace('fmp-', '')
        dates = source.get('dates', [])
        
        return {
            "api": api,
            "dates": dates[:4] if len(dates) > 4 else dates
        }
    
    return None


def _collect_data_sources_recursive(sources: Dict[str, Any], data_sources: Dict[str, Any]):
    """
    Recursively collect data sources from nested source definitions.
    
    Handles nested expressions like:
    evEBITDA -> enterpriseValue -> marketCap
    
    Args:
        sources: Source definitions dictionary
        data_sources: Output dictionary to collect API sources
    """
    for dep_name, dep_info in sources.items():
        if not isinstance(dep_info, dict):
            continue
        
        dep_type = dep_info.get('type')
        api = dep_info.get('api', '')
        dates = dep_info.get('dates', [])
        transform = dep_info.get('transform', '')
        
        # Direct API source (api_field or aggregation)
        if api:
            if api not in data_sources:
                data_sources[api] = {
                    'dates': [],
                    'transforms': set(),
                    'useSingleDate': False
                }
            
            # For marketCap (historical-market-capitalization), only the most recent date is used
            # This matches the calculation logic in metric_engine.py (I-25)
            if 'historical-market-cap' in api:
                # Only show the first date (event_date basis)
                if dates:
                    data_sources[api]['dates'] = [dates[0]]
                    data_sources[api]['useSingleDate'] = True
            elif dates:
                # Only keep first 4 dates for brevity
                data_sources[api]['dates'] = dates[:4] if len(dates) > 4 else dates
            
            if transform:
                data_sources[api]['transforms'].add(transform)
        
        # Nested expression - recursively collect its sources
        if dep_type == 'expression':
            nested_sources = dep_info.get('sources', {})
            if nested_sources:
                _collect_data_sources_recursive(nested_sources, data_sources)


def format_value_qualitative(value_qual: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform value_qualitative response for better readability.
    
    Args:
        value_qual: Original value_qualitative dictionary
        
    Returns:
        Transformed dictionary with separated sections
    """
    if not value_qual:
        return None
    
    metrics = {}
    reference_info = {}
    
    for key, value in value_qual.items():
        if key == '_meta':
            reference_info = {
                "source": value.get('source', 'unknown'),
                "eventDate": value.get('event_date', ''),
                "dataAvailable": value.get('dataAvailable', False)
            }
            if value.get('reason'):
                reference_info["reason"] = value.get('reason')
        elif key == 'targetSummary' and isinstance(value, dict):
            # Flatten targetSummary for readability
            metrics[key] = {
                "allTimeCount": value.get('allTimeCount'),
                "allTimeAvgPriceTarget": value.get('allTimeAvgPriceTarget'),
                "lastYearCount": value.get('lastYearCount'),
                "lastYearAvgPriceTarget": value.get('lastYearAvgPriceTarget'),
                "lastQuarterCount": value.get('lastQuarterCount'),
                "lastQuarterAvgPriceTarget": value.get('lastQuarterAvgPriceTarget'),
                "lastMonthCount": value.get('lastMonthCount'),
                "lastMonthAvgPriceTarget": value.get('lastMonthAvgPriceTarget'),
                "publishers": value.get('publishers', [])
            }
        else:
            metrics[key] = value
    
    return {
        "values": metrics,
        "dateInfo": reference_info
    }


def format_event_result(event_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a single event result for better readability.
    
    Args:
        event_result: Single event processing result
        
    Returns:
        Formatted event result
    """
    formatted = {
        "ticker": event_result.get('ticker'),
        "eventDate": event_result.get('eventDate'),
        "source": event_result.get('source'),
    }
    
    # Format value_quantitative
    value_quant = event_result.get('value_quantitative')
    if value_quant:
        formatted["value_quantitative"] = format_value_quantitative(value_quant)
    
    # Format value_qualitative
    value_qual = event_result.get('value_qualitative')
    if value_qual:
        formatted["value_qualitative"] = format_value_qualitative(value_qual)
    
    # Copy other fields as-is
    for key in ['position_quantitative', 'position_qualitative', 
                'disparity_quantitative', 'disparity_qualitative',
                'quantitativeStatus', 'qualitativeStatus', 'errorCode']:
        if key in event_result:
            formatted[key] = event_result[key]
    
    return formatted
