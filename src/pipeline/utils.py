import contextlib
import functools
import logging
import random
import time
from typing import Any, Callable, Dict, Optional, TypeVar

import requests

T = TypeVar("T")

logger = logging.getLogger(__name__)


def retry_with_policy(
    retry_policy: Dict[str, Any],
    on_retry: Optional[Callable[[int, float, float, int, Exception], None]] = None,
) -> Callable:
    """
    Decorator for retrying API calls based on the project's retry policy (FR-1.1.4).
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            attempts = retry_policy.get("attempts", 3)
            per_request_timeout = retry_policy.get("per_request_timeout_s", 10)
            max_total_duration = retry_policy.get("max_total_duration_s", 60)
            base_delay_ms = retry_policy.get("base_delay_ms", 500)
            multiplier = retry_policy.get("multiplier", 2.0)
            jitter_factor = retry_policy.get("jitter_factor", 0.20)

            start_time = time.time()
            last_exception: Exception = Exception("Unknown error")

            for attempt in range(attempts):
                elapsed = time.time() - start_time
                if elapsed >= max_total_duration:
                    logger.error(
                        f"Retry hard cap reached ({elapsed:.2f}s >= {max_total_duration}s)"
                    )
                    raise last_exception

                try:
                    # Inject timeout if not already present in kwargs
                    if "timeout" not in kwargs:
                        kwargs["timeout"] = per_request_timeout

                    return func(*args, **kwargs)

                except requests.exceptions.HTTPError as e:
                    last_exception = e
                    status_code = (
                        e.response.status_code if e.response is not None else 0
                    )

                    # Non-retryable errors (FR-1.1.4)
                    if status_code in [400, 401, 403, 404]:
                        logger.error(f"Non-retryable HTTP error: {status_code}")
                        raise

                    # Rate limiting (429)
                    delay = (base_delay_ms / 1000.0) * (multiplier**attempt)
                    if status_code == 429 and e.response is not None:
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after:
                            with contextlib.suppress(ValueError):
                                delay = float(retry_after)

                    # Apply jitter
                    jitter = delay * jitter_factor
                    actual_delay = delay + random.uniform(-jitter, jitter)

                    # Check if next attempt will exceed hard cap
                    if (time.time() - start_time) + actual_delay >= max_total_duration:
                        logger.warning(
                            "Next retry would exceed hard cap. Raising last error."
                        )
                        raise last_exception

                    if on_retry:
                        on_retry(
                            attempt + 1,
                            time.time() - start_time,
                            actual_delay,
                            status_code,
                            e,
                        )
                    else:
                        logger.warning(
                            f"Retry attempt {attempt + 1} after {actual_delay:.2f}s "
                            f"(Status: {status_code}, Elapsed: {time.time() - start_time:.2f}s)"
                        )

                    time.sleep(actual_delay)

                except (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                ) as e:
                    last_exception = e
                    delay = (base_delay_ms / 1000.0) * (multiplier**attempt)
                    jitter = delay * jitter_factor
                    actual_delay = delay + random.uniform(-jitter, jitter)

                    if (time.time() - start_time) + actual_delay >= max_total_duration:
                        raise last_exception

                    logger.warning(
                        f"Retry attempt {attempt + 1} after {actual_delay:.2f}s "
                        f"(Error: {type(e).__name__}, Elapsed: {time.time() - start_time:.2f}s)"
                    )
                    time.sleep(actual_delay)

                except Exception as e:
                    # Unknown errors are not retried by default to avoid infinite loops on logic errors
                    logger.error(
                        f"Unexpected error in retry loop: {type(e).__name__}: {e}"
                    )
                    raise

            raise last_exception

        return wrapper

    return decorator


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_nested_metadata(
    metadata: Dict[str, Any], top_key: str, sub_key: str, default: Any = None
) -> Any:
    """
    Safely retrieves a value from nested metadata with a fallback to flattened key.

    Example:
        get_nested_metadata(meta, "equity_thresholds", "high_access_min")
        checks meta["equity_thresholds"]["high_access_min"]
        then meta["equity_thresholds.high_access_min"]
    """
    # Try nested access
    top_value = metadata.get(top_key)
    if isinstance(top_value, dict) and sub_key in top_value:
        return top_value[sub_key]

    # Fallback to flattened key pattern
    flattened_key = f"{top_key}.{sub_key}"
    return metadata.get(flattened_key, default)
@contextlib.contextmanager
def timer(name: str):
    """
    Context manager for measuring execution time of a block of code (8.1.5).
    """
    start = time.perf_counter()
    logger.info(f"Starting {name}...")
    try:
        yield
    finally:
        end = time.perf_counter()
        logger.info(f"Finished {name} in {end - start:.2f} seconds.")
