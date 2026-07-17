"""Convert cover photos into Telegram stickers (or re-upload as photo)."""
from __future__ import annotations

import io
import logging
from typing import Optional, Tuple

from aiogram import Bot
from aiogram.types import BufferedInputFile

logger = logging.getLogger("catalog.sticker")


def image_to_sticker_webp(image_bytes: bytes) -> bytes:
    """Resize to Telegram static-sticker rules (one side 512px) and encode WEBP."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size
    if w <= 0 or h <= 0:
        raise ValueError("invalid image size")

    if w >= h:
        new_w = 512
        new_h = max(1, int(round(h * 512 / w)))
    else:
        new_h = 512
        new_w = max(1, int(round(w * 512 / h)))

    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=90, method=6)
    return out.getvalue()


async def upload_sticker(bot: Bot, chat_id: int, image_bytes: bytes) -> Optional[str]:
    """
    Upload a static sticker to `chat_id` and return sticker file_id.
    Message is deleted afterwards when possible.
    """
    try:
        webp = image_to_sticker_webp(image_bytes)
    except Exception as e:
        logger.warning("sticker convert failed: %s", e)
        return None

    try:
        msg = await bot.send_sticker(
            chat_id=chat_id,
            sticker=BufferedInputFile(webp, filename="cover.webp"),
        )
        file_id = msg.sticker.file_id if msg.sticker else None
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
        except Exception:
            pass
        return file_id
    except Exception as e:
        logger.warning("sticker upload failed: %s", e)
        return None


async def upload_photo(bot: Bot, chat_id: int, image_bytes: bytes) -> Optional[str]:
    """Upload photo and return largest size file_id (fallback delivery)."""
    try:
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=BufferedInputFile(image_bytes, filename="cover.jpg"),
        )
        file_id = None
        if msg.photo:
            file_id = msg.photo[-1].file_id
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
        except Exception:
            pass
        return file_id
    except Exception as e:
        logger.warning("photo upload failed: %s", e)
        return None


async def process_cover_image(
    bot: Bot,
    storage_chat_id: int,
    image_bytes: bytes,
    prefer_sticker: bool = True,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (sticker_file_id, photo_file_id).
    At least one may be set.
    """
    sticker_id = None
    photo_id = None
    if prefer_sticker:
        sticker_id = await upload_sticker(bot, storage_chat_id, image_bytes)
    if not sticker_id:
        photo_id = await upload_photo(bot, storage_chat_id, image_bytes)
    return sticker_id, photo_id
