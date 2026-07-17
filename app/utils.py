import re
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot

def parse_button_markup(text: str):
    """
    Parses text for button markups in the format [Text](buttonurl:link)
    Returns a tuple of (clean_text, InlineKeyboardMarkup)
    """
    # Allow multiline dots (so newlines between buttons or random spaces are captured naturally)
    button_pattern = r'\[(.*?)\]\(\s*buttonurl:(.*?)\s*\)'
    
    clean_text = text
    buttons = []
    
    for match in re.finditer(button_pattern, text, flags=re.DOTALL):
        btn_text = match.group(1).strip()
        btn_url = match.group(2).strip()
        buttons.append(InlineKeyboardButton(text=btn_text, url=btn_url))
        clean_text = clean_text.replace(match.group(0), "")

    clean_text = clean_text.strip()
    
    markup = None
    if buttons:
        # Putting them vertically by default. If you want multiple on same row, logic needs adjusting.
        keyboard = [[btn] for btn in buttons]
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
    return clean_text, markup

async def is_user_subscribed(bot: Bot, user_id: int, channel_id: int | str) -> bool:
    if not channel_id:
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        if member.status in ['member', 'creator', 'administrator']:
            return True
        return False
    except Exception as e:
        print(f"Error checking sub: {e}")
        return False
