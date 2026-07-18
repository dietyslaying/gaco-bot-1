import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app import config
from app import database
from app.utils import parse_button_markup, is_user_subscribed
from thefuzz import process

# Rule-based catalogue (filename parser → auto filters; no LLM)
try:
    from app import catalog
    from app.catalog import config as catalog_cfg
    CATALOG_AVAILABLE = True
except Exception as _cat_err:
    logging.warning("Catalogue module disabled: %s", _cat_err)
    CATALOG_AVAILABLE = False

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

REQUEST_GROUP_LINK = ""

FILES_GROUP_LINK = ""

async def get_files_link():
    global FILES_GROUP_LINK
    if not FILES_GROUP_LINK or FILES_GROUP_LINK == "https://t.me/":
        try:
            chat = await bot.get_chat(config.FILES_GROUP_ID)
            FILES_GROUP_LINK = chat.invite_link
            if not FILES_GROUP_LINK:
                FILES_GROUP_LINK = await bot.export_chat_invite_link(config.FILES_GROUP_ID)
        except Exception as e:
            print(f"Failed to get files group invite link: {e}")
            FILES_GROUP_LINK = "https://t.me/"
    return FILES_GROUP_LINK

async def get_request_link():
    global REQUEST_GROUP_LINK
    # Use a hardcoded/static URL from config if provided — avoids needing admin perms
    if config.REQUEST_GROUP_URL:
        return config.REQUEST_GROUP_URL
    if not REQUEST_GROUP_LINK or REQUEST_GROUP_LINK == "https://t.me/":
        try:
            chat = await bot.get_chat(config.REQUEST_GROUP_ID)
            REQUEST_GROUP_LINK = chat.invite_link
            if not REQUEST_GROUP_LINK:
                REQUEST_GROUP_LINK = await bot.export_chat_invite_link(config.REQUEST_GROUP_ID)
        except Exception as e:
            print(f"Failed to get invite link: {e}")
            REQUEST_GROUP_LINK = "https://t.me/"
    return REQUEST_GROUP_LINK

async def ensure_user(user_id: int):
    await database.add_user(user_id)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    await ensure_user(user_id)
    if await database.is_user_banned(user_id):
        return

    if not await is_user_subscribed(bot, user_id, config.FILES_GROUP_ID):
        files_link = await get_files_link()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⛩️ JOIN CHANNEL ⛩️", url=files_link)],
            [InlineKeyboardButton(text="✅ VERIFY ✅", callback_data="verify_sub")],
        ])
        await message.answer(config.START_MSG, parse_mode="Markdown", reply_markup=keyboard)
        return

    await message.answer(config.VERIFICATION_SUCCESS_MSG, parse_mode="Markdown")
    await asyncio.sleep(0.5)
    await message.answer(config.ASK_ANIME_MSG, parse_mode="Markdown")

@dp.callback_query(F.data == "verify_sub")
async def verify_sub_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if await database.is_user_banned(user_id):
        await callback.answer("You are banned.", show_alert=True)
        return

    if await is_user_subscribed(bot, user_id, config.FILES_GROUP_ID):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await bot.send_message(
            chat_id=user_id,
            text=config.VERIFICATION_SUCCESS_MSG,
            parse_mode="Markdown",
        )
        await asyncio.sleep(0.5)
        await bot.send_message(
            chat_id=user_id,
            text=config.ASK_ANIME_MSG,
            parse_mode="Markdown",
        )
        await callback.answer("Verified ✅")
    else:
        await callback.answer("You haven't joined the channel yet! ❌", show_alert=True)

def stats_menu_keyboard() -> InlineKeyboardMarkup:
    """Admin stats hub — each button opens a live report."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 Overview", callback_data="stats:overview")],
        [
            InlineKeyboardButton(text="🏆 Top Users", callback_data="stats:top_users"),
            InlineKeyboardButton(text="🔥 Most Requested", callback_data="stats:requested"),
        ],
        [InlineKeyboardButton(text="📭 Missing / Not in DB", callback_data="stats:missing")],
        [InlineKeyboardButton(text="✖ Close", callback_data="stats:close")],
    ])


async def format_stats_overview() -> str:
    s = await database.get_dashboard_stats()
    return (
        "📊 *GACO Stats — Overview*\n"
        "_Live numbers from the database_\n\n"
        f"👥 *Users:* `{s['users']}`\n"
        f"🚫 *Banned:* `{s['banned']}`\n"
        f"🔑 *Filters (search keys):* `{s['filters']}`\n"
        f"🎌 *Anime (series/topics):* `{s['anime']}`\n"
        f"🎬 *Movies (keys):* `{s['movies']}`\n"
        f"📁 *Indexed files:* `{s['indexed_files']}`\n"
        f"📚 *Topic covers:* `{s['topics']}`\n"
        f"📢 *Broadcasts:* `{s['broadcasts']}`\n"
        f"✅ *Successful searches:* `{s['search_hits']}`\n"
        f"❌ *Missed searches:* `{s['search_misses']}`\n"
    )


def _rank_medal(i: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"`{i}.`")


async def format_top_users(limit: int = 15) -> str:
    rows = await database.get_leaderboard(limit)
    if not rows:
        return "🏆 *Top Users*\n\n_No activity yet. Rankings update as people search._"
    lines = ["🏆 *Top Users Leaderboard*\n_Ranked by messages + successful searches_\n"]
    for i, u in enumerate(rows, 1):
        score = (u.messages_count or 0) + (u.filters_asked_count or 0)
        lines.append(
            f"{_rank_medal(i)} `{u.user_id}`\n"
            f"    └ {u.messages_count or 0} msgs · {u.filters_asked_count or 0} finds · *{score}* pts"
        )
    lines.append("\n_Updates in real time as users chat & search._")
    return "\n".join(lines)


async def format_most_requested(limit: int = 15) -> str:
    rows = await database.get_top_requested(limit)
    if not rows:
        return (
            "🔥 *Most Requested (Available)*\n\n"
            "_No successful searches logged yet._\n"
            "Whenever someone finds a title, it counts here."
        )
    lines = ["🔥 *Most Requested Animes*\n_Titles that exist in our catalogue_\n"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{_rank_medal(i)} `{r.query}` — *{r.count}*×")
    lines.append("\n_Live — increments on every successful search._")
    return "\n".join(lines)


async def format_most_missing(limit: int = 15) -> str:
    rows = await database.get_top_missing(limit)
    if not rows:
        return (
            "📭 *Most Requested — Not in DB*\n\n"
            "_No misses logged yet._\n"
            "Failed searches (not found) appear here so you know what to add."
        )
    lines = [
        "📭 *Most Requested — Not Available*\n"
        "_Searches that did not match our catalogue_\n"
    ]
    for i, r in enumerate(rows, 1):
        lines.append(f"{_rank_medal(i)} `{r.query}` — *{r.count}*×")
    lines.append("\n_Live — use this list to prioritise new uploads / filters._")
    return "\n".join(lines)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if await database.is_user_banned(message.from_user.id):
        return
    is_admin = message.from_user.id in config.ADMINS
    if is_admin:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Stats", callback_data="stats:menu"),
                InlineKeyboardButton(text="📢 Broadcast", callback_data="help:broadcast"),
            ],
            [InlineKeyboardButton(text="🗂 Broadcasts History", callback_data="bcast_list:0")],
            [
                InlineKeyboardButton(text="➕ Add Filter", callback_data="help:filter"),
                InlineKeyboardButton(text="🗑 Delete Filter", callback_data="help:delete"),
            ],
            [
                InlineKeyboardButton(text="📋 All Filters", callback_data="help:filters"),
                InlineKeyboardButton(text="🚫 Ban/Unban", callback_data="help:ban"),
            ],
            [InlineKeyboardButton(text="📚 Catalogue", callback_data="help:catalog")],
        ])
        await message.answer(
            "⚙️ *Admin panel* — pick a command:",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    else:
        req = await get_request_link()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 How to Search", callback_data="help:how")],
            [InlineKeyboardButton(text="📩 Request Anime", url=req or config.REQUEST_GROUP_URL or "https://t.me/")],
        ])
        await message.answer(
            "👋 *Help*\n\nJust send me an anime name to search.\nNeed more? Use the buttons below.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in config.ADMINS:
        return
    text = await format_stats_overview()
    await message.answer(text, parse_mode="Markdown", reply_markup=stats_menu_keyboard())

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if message.from_user.id not in config.ADMINS: return
    reply = message.reply_to_message
    if not reply:
        await message.answer("Please reply to a message to broadcast it.")
        return
    broadcast_text = reply.text or reply.caption or "[Media Message]"
    users = await database.get_all_users()
    
    # Save broadcast first to get ID
    broadcast_id = await database.save_broadcast_and_get_id(broadcast_text, message.from_user.id)
    
    success = 0
    progress_msg = await message.answer(f"⏳ Broadcasting to {len(users)} users...")
    
    for uid in users:
        try:
            res = await bot.copy_message(chat_id=uid, from_chat_id=reply.chat.id, message_id=reply.message_id)
            await database.save_sent_broadcast_message(broadcast_id, uid, res.message_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    
    await progress_msg.edit_text(f"✅ Broadcast complete.\nID: #{broadcast_id}\nSuccessful: {success}/{len(users)}")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if message.from_user.id not in config.ADMINS: return
    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        uid = int(parts[1])
        await database.ban_user(uid, True)
        await message.answer(f"User {uid} has been banned.")

@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    if message.from_user.id not in config.ADMINS: return
    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        uid = int(parts[1])
        await database.ban_user(uid, False)
        await message.answer(f"User {uid} has been unbanned.")

# --- Stats submenu (live leaderboards) ---
@dp.callback_query(F.data.startswith("stats:"))
async def cb_stats(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMINS:
        await callback.answer("Admins only.", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]
    await callback.answer()

    if action == "close":
        try:
            await callback.message.delete()
        except Exception:
            pass
        return

    if action == "menu":
        text = "📊 *Stats menu*\n\nPick a live report:"
        kb = stats_menu_keyboard()
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        return

    if action == "overview":
        text = await format_stats_overview()
    elif action == "top_users":
        text = await format_top_users(15)
    elif action == "requested":
        text = await format_most_requested(15)
    elif action == "missing":
        text = await format_most_missing(15)
    else:
        text = "Unknown stats view."

    back = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Refresh", callback_data=f"stats:{action}"),
            InlineKeyboardButton(text="⬅ Stats menu", callback_data="stats:menu"),
        ],
        [InlineKeyboardButton(text="✖ Close", callback_data="stats:close")],
    ])
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back)
    except Exception:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=back)


# --- Help button callbacks (admin tips + simple user tip) ---
@dp.callback_query(F.data.startswith("help:"))
async def cb_help(callback: CallbackQuery):
    if await database.is_user_banned(callback.from_user.id):
        return
    action = callback.data.split(":", 1)[1]
    # Route old "stats" help into the new stats hub
    if action == "stats":
        if callback.from_user.id not in config.ADMINS:
            await callback.answer("Admins only.", show_alert=True)
            return
        await callback.answer()
        text = await format_stats_overview()
        try:
            await callback.message.edit_text(
                text, parse_mode="Markdown", reply_markup=stats_menu_keyboard()
            )
        except Exception:
            await callback.message.answer(
                text, parse_mode="Markdown", reply_markup=stats_menu_keyboard()
            )
        return

    tips = {
        "how": (
            "🔍 *How to search*\n\n"
            "Just type any anime name.\n"
            "Examples: `One Piece`, `Naruto`, `AOT`, `JJK`\n\n"
            "Typos and short names are OK when possible."
        ),
        "broadcast": "📢 Reply to any message with `/broadcast` to send it to all users.",
        "filter": "➕ `/filter <Name> [Button](buttonurl:link)`\n(Optional: reply to a sticker for a cover.)",
        "delete": "🗑 `/delete <Anime Name>`",
        "filters": "📋 `/filters` — list registered filters.",
        "ban": "🚫 `/ban <user_id>` or `/unban <user_id>`",
        "catalog": (
            "📚 *Catalogue*\n\n"
            "`/catalog` — status\n"
            "`/catalog rebuild` · `granular` · `aliases` · `backfill`"
        ),
    }
    text = tips.get(action, "Unknown action.")
    await callback.answer()
    await callback.message.answer(text, parse_mode="Markdown")

# --- Broadcast history pagination ---
PER_PAGE = 4

def bcast_list_keyboard(broadcasts, page, total):
    rows = []
    for b in broadcasts:
        preview = b[1][:30] + "…" if len(b[1]) > 30 else b[1]
        rows.append([InlineKeyboardButton(text=f"📨 {preview}", callback_data=f"bcast_view:{b[0]}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅ Prev", callback_data=f"bcast_list:{page-1}"))
    if (page + 1) * PER_PAGE < total:
        nav.append(InlineKeyboardButton(text="Next ➡", callback_data=f"bcast_list:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="✖ Close", callback_data="bcast_close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.callback_query(F.data.startswith("bcast_list:"))
async def cb_bcast_list(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMINS:
        await callback.answer("Not authorized.", show_alert=True); return
    page = int(callback.data.split(":")[1])
    broadcasts, total = await database.get_broadcasts(page, PER_PAGE)
    if not broadcasts:
        await callback.answer("No broadcasts yet.", show_alert=True); return
    text = f"📂 *Broadcast History* — Page {page+1} of {max(1,(total+PER_PAGE-1)//PER_PAGE)}"
    await callback.answer()
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=bcast_list_keyboard(broadcasts, page, total))
    except:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=bcast_list_keyboard(broadcasts, page, total))

@dp.callback_query(F.data.startswith("bcast_view:"))
async def cb_bcast_view(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMINS:
        await callback.answer("Not authorized.", show_alert=True); return
    bid = int(callback.data.split(":")[1])
    row = await database.get_broadcast(bid)
    if not row:
        await callback.answer("Not found.", show_alert=True); return
    text = f"📨 *Broadcast #{row[0]}*\n🕐 {row[2]}\n\n{row[1]}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Edit & Resend", callback_data=f"bcast_edit:{bid}"),
         InlineKeyboardButton(text="🗑 Delete", callback_data=f"bcast_del:{bid}")],
        [InlineKeyboardButton(text="⬅ Back", callback_data="bcast_list:0")],
    ])
    await callback.answer()
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("bcast_del:"))
async def cb_bcast_del(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMINS:
        await callback.answer("Not authorized.", show_alert=True); return
    bid = int(callback.data.split(":")[1])
    await database.delete_broadcast(bid)
    await callback.answer("Deleted ✅", show_alert=True)
    # Refresh list
    broadcasts, total = await database.get_broadcasts(0, PER_PAGE)
    if broadcasts:
        text = "📂 *Broadcast History* — Page 1"
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=bcast_list_keyboard(broadcasts, 0, total))
    else:
        await callback.message.edit_text("No broadcasts yet.")

@dp.callback_query(F.data.startswith("bcast_edit:"))
async def cb_bcast_edit(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMINS:
        await callback.answer("Not authorized.", show_alert=True); return
    bid = int(callback.data.split(":")[1])
    await callback.answer()
    await callback.message.answer(
        f"✏️ Reply to this message with the new text to *edit & resend broadcast #{bid}*.\n\nSend: `/bcast_update {bid} <new text>`",
        parse_mode="Markdown"
    )

@dp.message(Command("bcast_update"))
async def cmd_bcast_update(message: Message):
    if message.from_user.id not in config.ADMINS: return
    parts = message.text.split(None, 2)
    if len(parts) < 3:
        await message.answer("Usage: `/bcast_update <id> <new text>`", parse_mode="Markdown"); return
    bid = int(parts[1])
    new_text = parts[2]
    await database.update_broadcast(bid, new_text)
    
    sent_messages = await database.get_sent_broadcast_messages(bid)
    if not sent_messages:
        await message.answer(f"⚠️ No message IDs found for broadcast #{bid}. I can only update the database for this one.")
        return

    await message.answer(f"🔄 Editing broadcast #{bid} for {len(sent_messages)} users...")
    
    success = 0
    for uid, mid in sent_messages:
        try:
            await bot.edit_message_text(chat_id=uid, message_id=mid, text=new_text)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            try:
                # If editing text fails (e.g. it was a media caption), try editing caption
                await bot.edit_message_caption(chat_id=uid, message_id=mid, caption=new_text)
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
                
    await message.answer(f"✅ Finished editing broadcast #{bid}.\nSuccessful Edits: {success}/{len(sent_messages)}")

@dp.callback_query(F.data == "bcast_close")
async def cb_bcast_close(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()

@dp.message(Command("filter"))
async def cmd_filter(message: Message):
    sender_id = message.from_user.id
    logging.warning(f"[FILTER] sender_id={sender_id}, ADMINS={config.ADMINS}, is_admin={sender_id in config.ADMINS}")
    if sender_id not in config.ADMINS:
        await message.answer(f"❌ Not admin. Your ID: `{sender_id}`", parse_mode="Markdown")
        return
    
    # Optional: Still support sticker replies, but don't strictly require it
    sticker_id = None
    if message.reply_to_message and message.reply_to_message.sticker:
        sticker_id = message.reply_to_message.sticker.file_id
        
    # Robustly strip the /filter command prefix (handles newlines, spaces, @botname variants)
    full_text = message.text or message.caption or ""
    text = re.sub(r'^/filter(?:@\w+)?\s*', '', full_text, count=1).strip()
    if not text:
        await message.answer("Usage: `/filter <Anime Name> [Button Text](buttonurl:link)`", parse_mode="Markdown")
        return
    
    # The string might contain newlines!
    # E.g.
    # /filter One Piece [✨ GACO ✨]
    # (buttonurl:link)
    # So we simply find the FIRST bracket '[' to split Keyword from the rest
    if "[" not in text:
        await message.answer("Usage: `/filter <Anime Name> [Button Text](buttonurl:link)`", parse_mode="Markdown")
        return
        
    keyword, reply_data = text.split("[", 1)
    keyword = keyword.strip()
    # If the user put a newline between Keyword and '[' or inside `text`, let's strip it from keyword
    keyword = keyword.split("\n")[0].strip() 
    
    reply_data = "[" + reply_data # Re-append the bracket
    
    await database.add_filter(keyword, reply_data, sticker_id)
    if sticker_id:
        await message.answer(f"✅ Filter added for `{keyword}` with the attached sticker!", parse_mode="Markdown")
    else:
        await message.answer(f"✅ Filter added for `{keyword}` (Text only)", parse_mode="Markdown")

@dp.message(Command("filters"))
async def cmd_filters(message: Message):
    if message.from_user.id not in config.ADMINS: return
    keywords = await database.get_all_filter_keywords()
    if not keywords:
        await message.answer("No filters registered yet.")
        return
    lines = [f"• `{kw}`" for kw in sorted(keywords)]
    await message.answer("📋 *Registered Filters:*\n" + "\n".join(lines), parse_mode="Markdown")

@dp.message(F.sticker)
async def handle_sticker(message: Message):
    if message.from_user.id in config.ADMINS:
        sticker_id = message.sticker.file_id
        await message.answer(f"Sticker ID:\n`{sticker_id}`", parse_mode="Markdown")

@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    if message.from_user.id not in config.ADMINS: return
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        keyword = parts[1]
        deleted = await database.delete_filter(keyword)
        if deleted:
            await message.answer(f"✅ Filter `{keyword}` deleted.")
        else:
            await message.answer(f"❌ Filter `{keyword}` not found.")

async def _deliver_filter(target, filter_data, *, chat_id=None):
    """Send sticker/photo card + GACO/DOWNLOAD buttons (screenshot UX)."""
    clean_text, markup = parse_button_markup(filter_data["reply_text"])
    if not clean_text:
        clean_text = "Here you go!"
    file_id = filter_data.get("file_id")

    async def _send_sticker(fid):
        if chat_id is not None:
            await bot.send_sticker(chat_id=chat_id, sticker=fid, reply_markup=markup)
        else:
            await target.answer_sticker(sticker=fid, reply_markup=markup)

    async def _send_photo(fid):
        if chat_id is not None:
            await bot.send_photo(chat_id=chat_id, photo=fid, caption=clean_text, reply_markup=markup)
        else:
            await target.answer_photo(photo=fid, caption=clean_text, reply_markup=markup)

    async def _send_text():
        if chat_id is not None:
            await bot.send_message(chat_id=chat_id, text=clean_text, reply_markup=markup)
        else:
            await target.answer(clean_text, reply_markup=markup)

    if file_id:
        try:
            await _send_sticker(file_id)
            return
        except Exception:
            try:
                await _send_photo(file_id)
                return
            except Exception:
                pass
    await _send_text()


# Short-lived "did you mean" picks (callback_data is max 64 bytes)
_SUGGESTIONS: dict[int, list[str]] = {}


@dp.callback_query(F.data.startswith("typo_yes:"))
async def cb_typo_yes(callback: CallbackQuery):
    if await database.is_user_banned(callback.from_user.id): return
    keyword = callback.data.split(":", 1)[1]
    filter_data = await database.get_filter(keyword)
    if filter_data:
        await _deliver_filter(callback.message, filter_data, chat_id=callback.from_user.id)
        await database.log_activity(callback.from_user.id, "filter")
        await database.log_search_hit(keyword)
        await callback.message.delete()
    else:
        await callback.answer("An error occurred.", show_alert=True)


@dp.callback_query(F.data.startswith("sug:"))
async def cb_suggest_pick(callback: CallbackQuery):
    if await database.is_user_banned(callback.from_user.id):
        return
    try:
        idx = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Invalid.", show_alert=True)
        return
    options = _SUGGESTIONS.get(callback.from_user.id) or []
    if idx < 0 or idx >= len(options):
        await callback.answer("Expired — search again.", show_alert=True)
        return
    keyword = options[idx]
    filter_data = await database.get_filter(keyword)
    if filter_data:
        await _deliver_filter(callback.message, filter_data, chat_id=callback.from_user.id)
        await database.log_activity(callback.from_user.id, "filter")
        await database.log_search_hit(keyword)
        await callback.message.delete()
        _SUGGESTIONS.pop(callback.from_user.id, None)
    else:
        await callback.answer("Not found.", show_alert=True)

@dp.message(Command("catalog"))
async def cmd_catalog(message: Message):
    """Admin: catalogue + cover server (topics → stickers → classic filters)."""
    if message.from_user.id not in config.ADMINS:
        return
    if not CATALOG_AVAILABLE:
        await message.answer("❌ Catalogue module not loaded.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1:
        st = await catalog.status()
        on = "🟢 ON" if st["enabled"] else "🔴 OFF"
        sess = "🟢 ready" if st.get("session_ready") else "🔴 set TELEGRAM_SESSION"
        await message.answer(
            f"📚 *Catalogue / Cover Server*\n"
            f"Status: {on}\n"
            f"User session: {sess}\n"
            f"Indexed files: `{st['indexed']}`\n"
            f"Parseable: `{st['parseable']}`\n"
            f"Topics (covers): `{st.get('topics', 0)}`\n"
            f"Filters: `{st['filters']}`\n"
            f"Buttons: `{st.get('gaco_button')}` · `{st.get('download_button')}`\n"
            f"Stickers: `{'on' if st.get('use_stickers') else 'off'}`\n\n"
            f"Commands:\n"
            f"`/catalog on` · `/catalog off`\n"
            f"`/catalog rebuild` — series + seasons/eps + aliases\n"
            f"`/catalog granular` — season/episode/movie/OVA links\n"
            f"`/catalog aliases` — short names (AOT, JJK, OP…)\n"
            f"`/catalog backfill` — forum topic covers\n"
            f"`/catalog backfill force` — re-process covers",
            parse_mode="Markdown",
        )
        return
    arg = parts[1].strip().lower()
    if arg == "on":
        catalog_cfg.CATALOG_ENABLED = True
        await message.answer("✅ Catalogue auto-update enabled.")
    elif arg == "off":
        catalog_cfg.CATALOG_ENABLED = False
        await message.answer("⏹ Catalogue auto-update disabled (indexing still runs).")
    elif arg == "rebuild":
        progress = await message.answer("🔄 Rebuilding filters (series + granular + aliases)…")
        result = await catalog.rebuild_all_filters()
        g = result.get("granular") or {}
        await progress.edit_text(
            f"✅ Rebuild complete.\n"
            f"Filters total: *{result['filters']}*\n"
            f"Base series: *{result.get('base_filters', '—')}*\n"
            f"Granular keys: *{g.get('granular_keys', 0)}*\n"
            f"Aliases added: *{result.get('aliases_created', 0)}*\n"
            f"Index rows: *{result['indexed']}*\n"
            f"Topics: *{result.get('topics', 0)}*",
            parse_mode="Markdown",
        )
    elif arg in ("granular", "episodes", "seasons"):
        progress = await message.answer("🔄 Building season / episode / movie / OVA filters…")
        result = await catalog.apply_granular_filters()
        await progress.edit_text(
            f"✅ Granular filters ready.\n"
            f"Keys written: *{result.get('granular_keys', 0)}*\n"
            f"By level: `{result.get('by_level')}`\n"
            f"Total filters: *{result.get('filters_total', 0)}*",
            parse_mode="Markdown",
        )
    elif arg in ("aliases", "alias", "expand"):
        progress = await message.answer("🔄 Expanding fan short names / abbreviations…")
        result = await catalog.expand_filter_aliases()
        total = len(await database.get_all_filter_keywords())
        await progress.edit_text(
            f"✅ Alias expand complete.\n"
            f"New alias keys: *{result.get('created', 0)}*\n"
            f"Total filters now: *{total}*\n"
            f"Series covered: *{result.get('series', 0)}*",
            parse_mode="Markdown",
        )
    elif arg in ("backfill", "backfill force") or arg.startswith("backfill"):
        force = "force" in arg
        if not catalog_cfg.session_configured():
            await message.answer(
                "❌ User session not configured.\n"
                "1. `python scripts/login_session.py`\n"
                "2. Put `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` in env\n"
                "3. Account must be admin of the files group"
            )
            return
        progress = await message.answer(
            "🔄 Cover server backfill started…\n"
            "This can take a while (topics × delay). I'll update when done."
        )

        async def run_backfill():
            try:
                from app.catalog.cover_server import backfill
                stats = await backfill(
                    bot,
                    config.FILES_GROUP_ID,
                    force=force,
                    limit=0,
                )
                await progress.edit_text(
                    f"✅ Backfill complete.\n"
                    f"Topics: *{stats['topics']}*\n"
                    f"OK: *{stats['ok']}* · Skipped: *{stats['skipped']}*\n"
                    f"No cover: *{stats['no_cover']}* · Errors: *{stats['errors']}*",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logging.exception("backfill failed")
                await progress.edit_text(f"❌ Backfill failed: `{e}`", parse_mode="Markdown")

        asyncio.create_task(run_backfill())
    else:
        await message.answer(
            "Usage: `/catalog [on|off|rebuild|granular|aliases|backfill|backfill force]`",
            parse_mode="Markdown",
        )


@dp.callback_query(F.data == "typo_no")
async def cb_typo_no(callback: CallbackQuery):
    if await database.is_user_banned(callback.from_user.id): return
    req_link = await get_request_link()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Request Group", url=req_link)
    ]])
    await bot.send_message(chat_id=callback.from_user.id, text=config.NOT_FOUND_MSG, reply_markup=keyboard)
    await callback.message.delete()

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in config.ADMINS:
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Stats", callback_data="stats:menu")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast_help")],
        [
            InlineKeyboardButton(text="🚫 Ban User", callback_data="admin_ban_help"),
            InlineKeyboardButton(text="✅ Unban", callback_data="admin_unban_help"),
        ],
        [
            InlineKeyboardButton(text="➕ Add Filter", callback_data="admin_filter_help"),
            InlineKeyboardButton(text="➖ Delete Filter", callback_data="admin_delete_help"),
        ],
        [InlineKeyboardButton(text="📚 Catalogue", callback_data="help:catalog")],
        [InlineKeyboardButton(text="🗂 Broadcast History", callback_data="bcast_list:0")],
    ])
    await message.answer(
        "🛠 *Admin panel*\nSelect an option:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )

@dp.callback_query(F.data.startswith("admin_"))
async def cb_admin(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMINS: return
    action = callback.data.split("_", 1)[1]
    
    back_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_back")]])

    if action == "stats":
        # redirect to stats hub
        await callback.answer()
        text = await format_stats_overview()
        try:
            await callback.message.edit_text(
                text, parse_mode="Markdown", reply_markup=stats_menu_keyboard()
            )
        except Exception:
            await callback.message.answer(
                text, parse_mode="Markdown", reply_markup=stats_menu_keyboard()
            )
        return
    elif action == "broadcast_help":
        await callback.message.edit_text("To broadcast, simply reply to any message with the `/broadcast` command.", reply_markup=back_markup)
    elif action in ["ban_help", "unban_help"]:
        cmd = "/ban" if action == "ban_help" else "/unban"
        await callback.message.edit_text(f"To ban/unban someone, use `{cmd} <user_id>`.", parse_mode="Markdown", reply_markup=back_markup)
    elif action in ["filter_help", "delete_help"]:
        cmd = "/filter <Keyword> [Button Text](buttonurl:link)" if action == "filter_help" else "/delete <Keyword>"
        await callback.message.edit_text(f"To manage filters, use:\n`{cmd}`", parse_mode="Markdown", reply_markup=back_markup)
    elif action == "back":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Stats", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast_help")],
            [InlineKeyboardButton(text="🚫 Ban User", callback_data="admin_ban_help"), InlineKeyboardButton(text="✅ Unban", callback_data="admin_unban_help")],
            [InlineKeyboardButton(text="➕ Add Filter", callback_data="admin_filter_help"), InlineKeyboardButton(text="➖ Delete Filter", callback_data="admin_delete_help")]
        ])
        await callback.message.edit_text("🛠 **Admin Panel**\nWelcome! Please select an option below:", parse_mode="Markdown", reply_markup=keyboard)

@dp.message(F.chat.id.in_([int(config.FILES_GROUP_ID), str(config.FILES_GROUP_ID)]))
async def index_files_group(message: Message):
    # Track new forum topics (name → later covers)
    if getattr(message, "forum_topic_created", None) and CATALOG_AVAILABLE:
        try:
            name = message.forum_topic_created.name
            thread_id = message.message_thread_id
            if name and thread_id:
                from app.catalog.parser import normalize_keyword
                await database.upsert_topic(
                    thread_id=int(thread_id),
                    title=name,
                    keyword=normalize_keyword(name),
                )
        except Exception as e:
            logging.warning("topic create index failed: %s", e)

    chat_id_str = str(message.chat.id).replace("-100", "")
    if message.chat.username:
        message_url = f"https://t.me/{message.chat.username}/{message.message_id}"
    else:
        message_url = f"https://t.me/c/{chat_id_str}/{message.message_id}"

    # Cover photo in a topic → Cover Server (bot path, no Telethon)
    if (
        CATALOG_AVAILABLE
        and catalog_cfg.CATALOG_ENABLED
        and message.photo
        and message.message_thread_id
    ):
        asyncio.create_task(_live_cover_from_message(message, message_url))

    if message.video or message.document:
        file_name = message.video.file_name if message.video else message.document.file_name
        caption = message.caption or ""
        await database.add_auto_index(message.message_id, file_name or "", caption, message_url)

        if CATALOG_AVAILABLE and catalog_cfg.CATALOG_ENABLED:
            async def _refresh_all():
                await catalog.refresh_series_filter(file_name or "", caption, message_url)
                try:
                    await catalog.apply_granular_filters()
                except Exception as e:
                    logging.warning("granular refresh failed: %s", e)
            asyncio.create_task(_refresh_all())


async def _live_cover_from_message(message: Message, message_url: str):
    """If this topic has no sticker yet, treat photo as cover."""
    try:
        from app.catalog.cover_server import ingest_live_cover
        from app.catalog.parser import normalize_keyword

        thread_id = int(message.message_thread_id)
        existing = await database.get_topic(thread_id)
        if existing and existing.get("sticker_file_id"):
            return

        title = (existing or {}).get("title")
        if not title and message.caption:
            title = message.caption.splitlines()[0].strip()[:120]
        if not title:
            title = f"Topic {thread_id}"

        # Download largest photo
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        buf = await bot.download_file(file.file_path)
        if hasattr(buf, "read"):
            image_bytes = buf.read()
        elif isinstance(buf, (bytes, bytearray)):
            image_bytes = bytes(buf)
        else:
            image_bytes = bytes(buf.getvalue()) if hasattr(buf, "getvalue") else None
        if not image_bytes:
            return

        await ingest_live_cover(
            bot,
            thread_id=thread_id,
            title=title,
            message_id=message.message_id,
            chat_id=message.chat.id,
            image_bytes=image_bytes,
            caption=message.caption or "",
            username=message.chat.username,
        )
    except Exception as e:
        logging.warning("live cover failed: %s", e)

@dp.message()
async def search_anime(message: Message):
    if message.chat.type != "private": return
    user_id = message.from_user.id
    if not message.text or message.text.startswith("/"): return
    await ensure_user(user_id)
    if await database.is_user_banned(user_id): return
    
    # Log regular message activity (only for users)
    await database.log_activity(user_id, 'message')
        
    if not await is_user_subscribed(bot, user_id, config.FILES_GROUP_ID):
        files_link = await get_files_link()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⛩️ JOIN CHANNEL ⛩️", url=files_link)],
            [InlineKeyboardButton(text="✅ VERIFY ✅", callback_data="verify_sub")]
        ])
        await message.answer(config.START_MSG, reply_markup=keyboard)
        return

    # Multi-stage search: exact / season-ep variants / partial / fuzzy / auto-index
    if CATALOG_AVAILABLE:
        from app.catalog.search import resolve_search
        hit = await resolve_search(message.text)
    else:
        hit = None
        data = await database.get_filter(message.text.strip().lower())
        if data:
            from app.catalog.search import SearchHit
            hit = SearchHit(kind="exact", filter_data=data, keyword=message.text.strip().lower())

    if hit and hit.filter_data:
        await _deliver_filter(message, hit.filter_data)
        await database.log_activity(user_id, 'filter')
        # Real-time most-requested (available)
        label = hit.keyword or message.text.strip().lower()
        await database.log_search_hit(label)
        return

    if hit and hit.suggestions:
        # Up to 5 "did you mean" options (callback uses short index — 64-byte limit)
        opts = hit.suggestions[:5]
        _SUGGESTIONS[user_id] = opts
        rows = []
        for i, kw in enumerate(opts):
            label = kw if len(kw) <= 60 else kw[:57] + "…"
            rows.append([InlineKeyboardButton(
                text=f"{i+1}. {label}",
                callback_data=f"sug:{i}",
            )])
        rows.append([InlineKeyboardButton(text="✖ None of these", callback_data="typo_no")])
        await message.reply(
            "Did you mean one of these?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    if hit and hit.auto_results:
        keyboard_buttons = []
        for res in hit.auto_results[:10]:
            btn_text = res.get("file_name") or "Video/File"
            if len(btn_text) > 40:
                btn_text = btn_text[:37] + "..."
            keyboard_buttons.append([InlineKeyboardButton(text=f"🎬 {btn_text}", url=res["url"])])
        if keyboard_buttons:
            await message.answer(
                f"✅ Found **{len(hit.auto_results)}** file matches:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
                parse_mode="Markdown",
            )
            await database.log_activity(user_id, "filter")
            await database.log_search_hit(message.text.strip().lower())
            return

    # Miss — not in catalogue
    await database.log_search_miss(message.text.strip().lower())
    req_link = await get_request_link()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Request Group", url=req_link)
    ]])
    await message.answer(config.NOT_FOUND_MSG, reply_markup=keyboard)

async def main():
    await database.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
