from .start import router as start_router
from .music import router as music_router
from .callbacks import router as callbacks_router
from .inline import router as inline_router
from .group_admin import router as g_admin_router
from .admin import router as admin_router
from aiogram import Router

async def register_bot_routes(dispatcher):
    if not dispatcher.get("routers_registered", False):
        for router in [start_router, g_admin_router, admin_router, music_router, callbacks_router, inline_router]:
            new_router = Router()
            new_router.message.handlers.extend(router.message.handlers)
            new_router.callback_query.handlers.extend(router.callback_query.handlers)
            new_router.inline_query.handlers.extend(router.inline_query.handlers)
            new_router.chat_member.handlers.extend(router.chat_member.handlers)
            new_router.chosen_inline_result.handlers.extend(router.chosen_inline_result.handlers)
            dispatcher.include_router(new_router)

        dispatcher["routers_registered"] = True
