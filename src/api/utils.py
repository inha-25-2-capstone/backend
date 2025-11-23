"""
Utility functions for API endpoints.
"""
import asyncio
from functools import partial
from typing import Callable, TypeVar
from concurrent.futures import ThreadPoolExecutor

T = TypeVar('T')

# Shared thread pool executor for blocking operations
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="api_db_")


async def run_in_executor(func: Callable[..., T], *args, **kwargs) -> T:
    """
    Run a synchronous function in a thread pool executor.

    This prevents blocking the async event loop when performing
    synchronous operations like database queries.

    Args:
        func: Synchronous function to execute
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result of the function execution

    Example:
        result = await run_in_executor(sync_db_query, param1, param2)
    """
    loop = asyncio.get_event_loop()
    if kwargs:
        func = partial(func, **kwargs)
    return await loop.run_in_executor(_executor, func, *args)


def get_executor() -> ThreadPoolExecutor:
    """Get the shared thread pool executor."""
    return _executor
