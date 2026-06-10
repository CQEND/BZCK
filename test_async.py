import inspect
import asyncio
from asgiref.sync import async_to_sync

async def get_serializer():
    await asyncio.sleep(0.1)
    return "serializer"

def force_evaluate_if_async(obj):
    if inspect.iscoroutine(obj):
        async def evaluate():
            return await obj
        return async_to_sync(evaluate)()
    return obj

coro = get_serializer()
print(force_evaluate_if_async(coro))

def sync_get_serializer():
    return "sync_serializer"

sync_val = sync_get_serializer()
print(force_evaluate_if_async(sync_val))
