import re
from aiogram import Bot

from app.config import config


class BotTexts:
    def __init__(self, info: Bot, user: dict):
        self._info = info
        self.lang = "en"
        self.user = user
        
    def res_maker(self, res: str) -> str:
        user = self.user
        bot = self._info
        
        filters = {
            "<user_id>": user.id,
            "<user_first_name>": user.first_name,
            "<user_last_name>": user.last_name,
            "<user_username>": user.username,
            "<bot_id>": bot.id,
            "<bot_name>": bot.first_name,
            "<bot_username>": bot.username,
            "<link_to_user>": f"[{user.first_name}](tg://user?id={user.id})"
        }
        
        for filter_, value in filters.items():
            res = res.replace(filter_, str(value))
            
        def replace_text(match):
            key = match.group(1)
            return str(self.__getattr__(key))
        
        res = re.sub(r"<text_(\w+)>", replace_text, res)
            
        return res

    def __getattr__(self, item) -> str:
        res = config.DEFAULT_TEXTS.get(self.lang, {}).get(item, f"[{item} not found]")
        return self.res_maker(res)


class BotData:
    def __init__(self, bot_info, user):
        self.id = bot_info.id
        self.info = bot_info
        self.texts = BotTexts(bot_info, user)
