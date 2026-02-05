import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple, Set

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found. Put it into .env file")

admin_env = os.getenv("ADMIN_USER_IDS", "7868363667")
ADMIN_USER_IDS: Set[int] = {int(x) for x in admin_env.split(",") if x.strip()}

CITY_CONFIG = {
    "muc": {"title": "Мюнхен", "channel_id": -1002219465811},
    "augs": {"title": "Аугсбург", "channel_id": -1002981130084},
    "ulm": {"title": "Ульм", "channel_id": -1003498951036},
    "bhv": {"title": "Бремерхафен", "channel_id": -1002371775576},
    "freib": {"title": "Фрайбург", "channel_id": -1002271961159},
    "fulda": {"title": "Фульда", "channel_id": -1002850532206},
    "kiel": {"title": "Киль", "channel_id": -1002869339962},
    "ing": {"title": "Ингольштадт", "channel_id": -1002729434772},
    "old": {"title": "Ольденбург", "channel_id": -1002261517622},
    "sb": {"title": "Саарбрюкен", "channel_id": -1002425353443},
    "reg": {"title": "Регенсбург", "channel_id": -1002824918500},
    "lue": {"title": "Любек", "channel_id": -1002728230169},
    "mag": {"title": "Магдебург", "channel_id": -1003583811847},
    "str": {"title": "Штутгарт", "channel_id": -1002800255602},
    "ks": {"title": "Кассель", "channel_id": -1002656196874},
    "leip": {"title": "Лейпциг", "channel_id": -1002835449921},
    "bre": {"title": "Бремен", "channel_id": -1002877691247},
    "hh": {"title": "Гамбург", "channel_id": -1003666199517},
    "nue": {"title": "Нюрнберг", "channel_id": -1002741882907},
    "wib": {"title": "Висбаден", "channel_id": -1002807012302},
    "man": {"title": "Мангейм", "channel_id": -1002705598877},
    "dre": {"title": "Дрезден", "channel_id": -1003809886365},
    "mrb": {"title": "Марбург/Гиссен", "channel_id": -1002488276982},
    "han": {"title": "Ганновер", "channel_id": -1003131952570},
}

USER_CITY: Dict[int, str] = {}

@dataclass
class Suggestion:
    city_code: str
    from_user_id: int
    from_username: Optional[str]
    text: Optional[str]
    media: Optional[List[Tuple[str, str]]]
    status: str

SUGGESTIONS: Dict[int, Suggestion] = {}
NEXT_ID = 1
MEDIA_GROUPS: Dict[Tuple[int, str], Dict[str, object]] = {}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

def kb(sid: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Опубликовать", callback_data=f"publish:{sid}")
    b.button(text="❌ Отклонить", callback_data=f"reject:{sid}")
    b.adjust(2)
    return b.as_markup()

def city_title(code: str) -> str:
    return CITY_CONFIG.get(code, {}).get("title", code)

dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: Message, command: CommandStart):
    arg = (command.args or "").strip().lower()
    if arg and arg in CITY_CONFIG:
        USER_CITY[m.from_user.id] = arg
        await m.answer(
            f"✅ Город выбран: {city_title(arg)}\n"
            f"Отправь текст — уйдёт админу на модерацию."
        )
        return
    lines = ["❌ Город не выбран.", "Выбери город через /start <код>:", ""]
    for code, cfg in CITY_CONFIG.items():
        lines.append(f"• {cfg['title']}: /start {code}")
    await m.answer("\n".join(lines))

@dp.message(F.text)
async def handle_text(m: Message):
    global NEXT_ID
    text = (m.text or "").strip()
    if not text:
        return
    city = USER_CITY.get(m.from_user.id)
    if not city:
        await m.answer("❌ Сначала выбери город: /start muc (пример)")
        return
    sid = NEXT_ID
    NEXT_ID += 1
    SUGGESTIONS[sid] = Suggestion(
        city_code=city,
        from_user_id=m.from_user.id,
        from_username=m.from_user.username,
        text=text,
        media=None,
        status="pending",
    )
    user = f"@{m.from_user.username}" if m.from_user.username else "без username"
    admin_text = (
        f"🧾 Предложка #{sid} ({city_title(city)})\n"
        f"Прислано от: {user} | id:{m.from_user.id}\n\n"
        f"{text}"
    )
    admin_id = next(iter(ADMIN_USER_IDS))
    for admin_id in ADMIN_USER_IDS:
        try:
            await m.bot.forward_message(admin_id, m.chat.id, m.message_id)
        except Exception:
            try:
                await m.bot.send_message(admin_id, text)
            except Exception:
                logging.warning(f"Failed to notify admin {admin_id} for text")
                continue
        try:
            await m.bot.send_message(
                admin_id,
                f"Пост от: {m.from_user.full_name}" + (f" (@{m.from_user.username})" if m.from_user.username else "") + f"\nID: {m.from_user.id}\nГород: {city_title(city)}",
                reply_markup=kb(sid),
            )
        except Exception:
            logging.warning(f"Failed to send admin card to {admin_id}")
    await m.answer("✅ Принял. Ждёт решения админа.")

@dp.message(F.photo & ~F.media_group_id)
async def handle_single_photo(m: Message):
    global NEXT_ID
    city = USER_CITY.get(m.from_user.id)
    if not city:
        await m.answer("❌ Сначала выбери город: /start muc (пример)")
        return
    file_id = m.photo[-1].file_id
    caption = (m.caption or "").strip() or None
    sid = NEXT_ID
    NEXT_ID += 1
    SUGGESTIONS[sid] = Suggestion(
        city_code=city,
        from_user_id=m.from_user.id,
        from_username=m.from_user.username,
        text=caption,
        media=[("photo", file_id)],
        status="pending",
    )
    for admin_id in ADMIN_USER_IDS:
        try:
            await m.bot.forward_message(admin_id, m.chat.id, m.message_id)
        except Exception:
            try:
                await m.bot.send_photo(admin_id, file_id, caption=caption or "")
            except Exception:
                logging.warning(f"Failed to notify admin {admin_id} for photo")
                continue
        try:
            await m.bot.send_message(
                admin_id,
                f"Пост от: {m.from_user.full_name}" + (f" (@{m.from_user.username})" if m.from_user.username else "") + f"\nID: {m.from_user.id}\nГород: {city_title(city)}",
                reply_markup=kb(sid),
            )
        except Exception:
            logging.warning(f"Failed to send admin card to {admin_id}")
    await m.answer("✅ Фото принято. Ждёт решения админа.")

@dp.message(F.video & ~F.media_group_id)
async def handle_single_video(m: Message):
    global NEXT_ID
    city = USER_CITY.get(m.from_user.id)
    if not city:
        await m.answer("❌ Сначала выбери город: /start muc (пример)")
        return
    file_id = m.video.file_id
    caption = (m.caption or "").strip() or None
    sid = NEXT_ID
    NEXT_ID += 1
    SUGGESTIONS[sid] = Suggestion(
        city_code=city,
        from_user_id=m.from_user.id,
        from_username=m.from_user.username,
        text=caption,
        media=[("video", file_id)],
        status="pending",
    )
    for admin_id in ADMIN_USER_IDS:
        try:
            await m.bot.forward_message(admin_id, m.chat.id, m.message_id)
        except Exception:
            try:
                await m.bot.send_video(admin_id, file_id, caption=caption or "")
            except Exception:
                logging.warning(f"Failed to notify admin {admin_id} for video")
                continue
        try:
            await m.bot.send_message(
                admin_id,
                f"Пост от: {m.from_user.full_name}" + (f" (@{m.from_user.username})" if m.from_user.username else "") + f"\nID: {m.from_user.id}\nГород: {city_title(city)}",
                reply_markup=kb(sid),
            )
        except Exception:
            logging.warning(f"Failed to send admin card to {admin_id}")
    await m.answer("✅ Видео принято. Ждёт решения админа.")

async def _finalize_album(key: Tuple[int, str]):
    data = MEDIA_GROUPS.get(key)
    if not data:
        return
    m: Message = data["message"]  # type: ignore
    city: str = data["city"]  # type: ignore
    items: List[Tuple[str, str]] = data["items"]  # type: ignore
    caption: Optional[str] = data["caption"]  # type: ignore
    global NEXT_ID
    sid = NEXT_ID
    NEXT_ID += 1
    SUGGESTIONS[sid] = Suggestion(
        city_code=city,
        from_user_id=m.from_user.id,
        from_username=m.from_user.username,
        text=caption,
        media=items,
        status="pending",
    )
    medias = []
    for i, (kind, fid) in enumerate(items):
        if kind == "photo":
            if i == 0 and caption:
                medias.append(InputMediaPhoto(media=fid, caption=caption))
            else:
                medias.append(InputMediaPhoto(media=fid))
        elif kind == "video":
            if i == 0 and caption:
                medias.append(InputMediaVideo(media=fid, caption=caption))
            else:
                medias.append(InputMediaVideo(media=fid))
    for admin_id in ADMIN_USER_IDS:
        try:
            await m.bot.send_media_group(admin_id, media=medias)
            await m.bot.send_message(
                admin_id,
                f"Пост от: {m.from_user.full_name}" + (f" (@{m.from_user.username})" if m.from_user.username else "") + f"\nID: {m.from_user.id}\nГород: {city_title(city)}",
                reply_markup=kb(sid),
            )
        except Exception:
            logging.warning(f"Failed to notify admin {admin_id} for album")
    MEDIA_GROUPS.pop(key, None)

@dp.message(F.photo & F.media_group_id)
async def handle_album_photo(m: Message):
    city = USER_CITY.get(m.from_user.id)
    if not city:
        await m.answer("❌ Сначала выбери город: /start muc (пример)")
        return
    key = (m.from_user.id, m.media_group_id)
    entry = MEDIA_GROUPS.get(key)
    if not entry:
        entry = {"items": [], "caption": None, "city": city, "message": m, "task": None}
        MEDIA_GROUPS[key] = entry
    entry["items"].append(("photo", m.photo[-1].file_id))
    if m.caption:
        entry["caption"] = (m.caption or "").strip()
    task: Optional[asyncio.Task] = entry.get("task")  # type: ignore
    if task and not task.done():
        task.cancel()
    async def schedule():
        try:
            await asyncio.sleep(1.2)
        except asyncio.CancelledError:
            return
        await _finalize_album(key)
    entry["task"] = asyncio.create_task(schedule())  # type: ignore
    await m.answer("📷 Принял фото(альбом). Формирую предложку…")

@dp.message(F.video & F.media_group_id)
async def handle_album_video(m: Message):
    city = USER_CITY.get(m.from_user.id)
    if not city:
        await m.answer("❌ Сначала выбери город: /start muc (пример)")
        return
    key = (m.from_user.id, m.media_group_id)
    entry = MEDIA_GROUPS.get(key)
    if not entry:
        entry = {"items": [], "caption": None, "city": city, "message": m, "task": None}
        MEDIA_GROUPS[key] = entry
    entry["items"].append(("video", m.video.file_id))
    if m.caption:
        entry["caption"] = (m.caption or "").strip()
    task: Optional[asyncio.Task] = entry.get("task")  # type: ignore
    if task and not task.done():
        task.cancel()
    async def schedule():
        try:
            await asyncio.sleep(1.2)
        except asyncio.CancelledError:
            return
        await _finalize_album(key)
    entry["task"] = asyncio.create_task(schedule())  # type: ignore
    await m.answer("🎬 Принял видео(альбом). Формирую предложку…")

@dp.callback_query(F.data.startswith("publish:"))
async def publish(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет прав", show_alert=True)
        return
    sid = int(cb.data.split(":")[1])
    s = SUGGESTIONS.get(sid)
    if not s:
        await cb.answer("Не найдено", show_alert=True)
        return
    if s.status != "pending":
        await cb.answer(f"Уже обработано: {s.status}", show_alert=True)
        return
    channel_id = CITY_CONFIG[s.city_code]["channel_id"]
    if s.media:
        medias = []
        for i, (kind, fid) in enumerate(s.media):
            if kind == "photo":
                if i == 0 and s.text:
                    medias.append(InputMediaPhoto(media=fid, caption=s.text))
                else:
                    medias.append(InputMediaPhoto(media=fid))
            elif kind == "video":
                if i == 0 and s.text:
                    medias.append(InputMediaVideo(media=fid, caption=s.text))
                else:
                    medias.append(InputMediaVideo(media=fid))
        await cb.bot.send_media_group(channel_id, media=medias)
    else:
        await cb.bot.send_message(channel_id, s.text or "")
    s.status = "approved"
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.reply(
        f"✅ Опубликовано анонимно (#{sid}, {city_title(s.city_code)})"
    )
    await cb.answer("Опубликовано")

@dp.callback_query(F.data.startswith("reject:"))
async def reject(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет прав", show_alert=True)
        return
    sid = int(cb.data.split(":")[1])
    s = SUGGESTIONS.get(sid)
    if not s:
        await cb.answer("Не найдено", show_alert=True)
        return
    if s.status != "pending":
        await cb.answer(f"Уже обработано: {s.status}", show_alert=True)
        return
    s.status = "rejected"
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.reply(
        f"❌ Отклонено (#{sid}, {city_title(s.city_code)})"
    )
    await cb.answer("Отклонено")

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
