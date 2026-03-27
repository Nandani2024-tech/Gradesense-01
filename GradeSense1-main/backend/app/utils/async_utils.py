import asyncio
from typing import List, Any

async def safe_gather(tasks: List[Any]) -> List[Any]:
    """
    Safely executes multiple tasks using asyncio.gather.
    If any task raises an exception, it is re-raised immediately after all tasks complete.
    """
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final = []
    for r in results:
        if isinstance(r, Exception):
            raise r
        final.append(r)

    return final
