"""Request logging middleware to inject reqId and log requests/responses."""

import uuid
import time
import logging
import json
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, StreamingResponse
from ..utils.request_context import start_log_collection, get_detailed_logs, clear_detailed_logs

logger = logging.getLogger("alsign")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses with reqId."""

    async def dispatch(self, request: Request, call_next):
        """
        Process request, inject reqId, and log.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response with detailedLogs injected
        """
        # Generate unique request ID
        req_id = str(uuid.uuid4())
        request.state.reqId = req_id

        # Start log collection for this request
        start_log_collection()

        # Start timer
        start_time = time.time()

        # Log incoming request
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                'endpoint': f"{request.method} {request.url.path}",
                'phase': 'request_start',
                'elapsed_ms': 0,
                'counters': {},
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )

        # Process request
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            # Log exception
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Request failed: {str(exc)}",
                extra={
                    'endpoint': f"{request.method} {request.url.path}",
                    'phase': 'request_error',
                    'elapsed_ms': elapsed_ms,
                    'counters': {'fail': 1},
                    'progress': {},
                    'rate': {},
                    'batch': {},
                    'warn': []
                },
                exc_info=True
            )
            # Clear logs on exception
            clear_detailed_logs()
            raise

        # Calculate elapsed time
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Log response
        logger.info(
            f"Request completed: {request.method} {request.url.path} - Status: {response.status_code}",
            extra={
                'endpoint': f"{request.method} {request.url.path}",
                'phase': 'request_complete',
                'elapsed_ms': elapsed_ms,
                'counters': {'success': 1 if response.status_code < 400 else 0, 'fail': 1 if response.status_code >= 400 else 0},
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )

        # Get collected detailed logs
        detailed_logs = get_detailed_logs()

        # Inject detailedLogs into JSON response
        if response.headers.get('content-type', '').startswith('application/json'):
            try:
                # Read response body
                body = b''
                async for chunk in response.body_iterator:
                    body += chunk

                # Parse JSON
                if body:
                    data = json.loads(body.decode('utf-8'))

                    # Inject detailedLogs
                    if isinstance(data, dict):
                        data['detailedLogs'] = detailed_logs

                    # Create new response with modified body
                    new_body = json.dumps(data).encode('utf-8')

                    # Remove content-length from headers to let Response recalculate it
                    headers = dict(response.headers)
                    headers.pop('content-length', None)

                    response = Response(
                        content=new_body,
                        status_code=response.status_code,
                        headers=headers,
                        media_type='application/json'
                    )
            except Exception as e:
                logger.warning(f"Failed to inject detailedLogs: {e}")

        # Clear logs after response
        clear_detailed_logs()

        # Add reqId to response headers
        response.headers['X-Request-ID'] = req_id

        return response
