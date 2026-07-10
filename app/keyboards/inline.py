from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import urllib

class Inlines:
    def __init__(self, texts):
        self.data = texts
        
    def lang(self):
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇸 English", callback_data="lang:en"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")
            ],
            [
                InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang:uk"),
                InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang:es")
            ],
            [
                InlineKeyboardButton(text="🇺🇿 O‘zbekcha", callback_data="lang:uz"),
                InlineKeyboardButton(text="🇧🇷 Português", callback_data="lang:pt")
            ],
            [
                InlineKeyboardButton(text="🇩🇪 Deutsch", callback_data="lang:de"),
                InlineKeyboardButton(text="🇮🇹 Italiano", callback_data="lang:it")
            ],
            [
                InlineKeyboardButton(text="🇫🇷 Français", callback_data="lang:fr"),
                InlineKeyboardButton(text="🇹🇷 Türkçe", callback_data="lang:tr")
            ],
            [
                InlineKeyboardButton(text="🇮🇱 עברית", callback_data="lang:he"),
                InlineKeyboardButton(text="🇸🇦 العربية", callback_data="lang:ar")
            ],
            [
                InlineKeyboardButton(text="🇮🇷 فارسی", callback_data="lang:fa"),
                InlineKeyboardButton(text="🇨🇳 中文", callback_data="lang:zh")
            ],
            [
                InlineKeyboardButton(text="🇮🇩 Bahasa Indonesia", callback_data="lang:id"),
                InlineKeyboardButton(text="🇸🇪 Svenska", callback_data="lang:sv")
            ],
            [
                InlineKeyboardButton(text="🇲🇾 Bahasa Melayu", callback_data="lang:ms"),
                InlineKeyboardButton(text="🇳🇱 Nederlands", callback_data="lang:nl")
            ],
            [
                InlineKeyboardButton(text="🇮🇳 हिंदी", callback_data="lang:hi"),
                InlineKeyboardButton(text="🇰🇷 한국어", callback_data="lang:ko")
            ]
        ])
        return markup
    
    def welcome(self, bot):
        username = bot.info.username
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=self.data.inline_search, switch_inline_query_current_chat="")],
            [InlineKeyboardButton(text=self.data.add_group, url=f"https://t.me/{username}?startgroup=true")]
        ])
        
        return markup
    
    def music_search(self, results, username, text="", has_more=None, offset=0):
        max_button_length = 64

        def shorten_text(text: str, max_length: int) -> str:
            if len(text) > max_length:
                return text[:max_length - 3] + "..."
            return text

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=shorten_text(
                        f"• {result['duration']} • {result['title']} — {result['artists'][0]['name']}",
                        max_button_length
                    ),
                    callback_data=f"song:{result['videoId']}"
                )
            ]
            for result in results
        ])
        
        if has_more:
            keyboard.inline_keyboard.extend([
                [InlineKeyboardButton(text=self.data.more, callback_data=f"search:{offset + 1}")]
            ])
            
        extra_buttons = [
            [
                InlineKeyboardButton(text=self.data.inline_search, switch_inline_query_current_chat=text),
                InlineKeyboardButton(text=self.data.add_group, url=f"https://t.me/{username}?startgroup=true")
            ]
        ]
        
        keyboard.inline_keyboard.extend(extra_buttons)
        return keyboard
    
    def music_data(self, song_id, full_name, links):
        full_name_encoded = urllib.parse.quote(full_name.replace(" ", "+"))

        keyboard_buttons = []

        buttons_data = [
            (self.data.audiomack, links.get("audiomack")),
            [(self.data.google, f"https://www.google.com/search?q={full_name_encoded}"),
            (self.data.apple_music, links.get("apple_music"))],
            [(self.data.spotify, links.get("spotify")),
            (self.data.yt, links.get("youtube"))],
            [(self.data.soundcloud, links.get("soundcloud")),
            (self.data.deezer, links.get("deezer"))]
        ]

        for btn_group in buttons_data:
            row = []
            for text, link_key in (btn_group if isinstance(btn_group, list) else [btn_group]):
                if link_key:
                    row.append(InlineKeyboardButton(text=text, url=link_key))
            if row:
                keyboard_buttons.append(row)

        keyboard_buttons.append([InlineKeyboardButton(text=self.data.receive, callback_data=f"download:{song_id}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        return keyboard
    
    def music_lyrics(self, song_id, only_switch=False):
        buttons = [
            InlineKeyboardButton(text=self.data.inline_search, switch_inline_query_current_chat="")
        ]
        
        if not only_switch:
            lyrics_button = InlineKeyboardButton(text=self.data.lyrics, callback_data=f"lyrics:{song_id}")
            buttons.insert(0, lyrics_button)
            
        markup = InlineKeyboardMarkup(inline_keyboard=[
            buttons
        ])
        
        return markup
    
    def group_admin(self, settings: dict):
        queit = '✅' if settings.get("quiet") else'❌'
        all_texts = '✅' if settings.get("all_texts") else'❌'
        all_media = '✅' if settings.get("all_media") else'❌'
        
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=self.data.language, callback_data="group_lang")],
                [InlineKeyboardButton(text=f"{queit} {self.data.queit}", callback_data="group-quiet")],
                [InlineKeyboardButton(text=f"{all_texts} {self.data.all_texts}", callback_data="group-all_texts")],
                [InlineKeyboardButton(text=f"{all_media} {self.data.all_media}", callback_data="group-all_media")],
                [InlineKeyboardButton(text=self.data.refresh, callback_data="group_refresh")],
                [InlineKeyboardButton(text=self.data.done, callback_data="group_done")],
            ]
        )
        
        return markup
    
    def admin(self):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=self.data.stat, callback_data="admin-stat")],
                [InlineKeyboardButton(text=self.data.broadcast, callback_data="admin-broadcast")],
                [InlineKeyboardButton(text=self.data.done, callback_data="admin-done")]
            ]
        )
        
        return markup
    
    def admin_back(self):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=self.data.back, callback_data="admin-back")]
            ]
        )
        
        return markup
