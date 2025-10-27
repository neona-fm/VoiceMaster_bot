# main_clean.py — минимальная версия VoiceMaster
# Функции: /start, приём voice/audio, расшифровка через OpenAI,
# если прислали ВИДЕО — показываем кнопку с твоим туториалом (зашито в коде).
#
# ENV:
#   TELEGRAM_BOT_TOKEN=...
#   OPENAI_API_KEY=...
#
# Зависимости: aiogram>=3, python-dotenv, openai>=1.37, requests, imageio-ffmpeg

import os
import logging
import asyncio
import requests
import imageio_ffmpeg as ffmpeg_lib

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from openai import AsyncOpenAI
from dotenv import load_dotenv

# -------------------- Конфиг --------------------
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")

if not BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Нужно указать TELEGRAM_BOT_TOKEN и OPENAI_API_KEY в .env")

# Реклама (зашито в коде): ссылка на твой урок по вырезанию аудио из видео
HOWTO_URL_HARD = "https://t.me/Neona_FM/1224"

# -------------------- Core ----------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicemaster-clean")

FFMPEG_PATH = ffmpeg_lib.get_ffmpeg_exe()

def how_to_extract_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪄 Как вырезать аудио с видео", url=HOWTO_URL_HARD)]
    ])

# -------------------- OpenAI --------------------
async def transcribe_audio(file_path: str) -> str | None:
    try:
        with open(file_path, "rb") as f:
            res = await client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=f
            )
        return getattr(res, "text", None)
    except Exception as e:
        logger.error(f"OpenAI transcription error: {e}")
        return None

# -------------------- Media flow ----------------
async def handle_media(message: types.Message, file_type: str):
    user_id = message.from_user.id

    # Если прислали видео — показываем кнопку и уходим
    if file_type == "video":
        await message.answer(
            "🎬 Я принимаю только аудио/голосовые.\n"
            "Вырежьте звук из видео и отправьте мне аудио-файл.",
            reply_markup=how_to_extract_button()
        )
        return

    # Скачиваем файл
    if file_type == "voice":
        file_id = message.voice.file_id
        input_path = f"input_{user_id}.ogg"
    else:
        file_id = message.audio.file_id
        input_path = f"input_{user_id}.bin"

    wait_msg = await message.answer("⏳ Обрабатываю файл...")
    output_path = f"output_{user_id}.wav"

    try:
        file_info = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        r = requests.get(file_url, timeout=60)
        r.raise_for_status()
        with open(input_path, "wb") as f:
            f.write(r.content)

        # Конвертируем в WAV 44.1kHz, stereo
        os.system(
            f'"{FFMPEG_PATH}" -i "{input_path}" '
            f'-vn -acodec pcm_s16le -ar 44100 -ac 2 "{output_path}" '
            f'-y -loglevel quiet'
        )

        text = await transcribe_audio(output_path)

        # Удаляем "жду" сообщение
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
        except Exception:
            pass

        if text and text.strip():
            await message.answer(f"📝 Расшифровка:\n\n{text}")
        else:
            await message.answer("⚠️ Не удалось расшифровать этот файл.")
    except Exception as e:
        logger.error(f"Media handling error: {e}")
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
        except Exception:
            pass
        await message.answer("⚠️ Не удалось обработать файл.")
    finally:
        for p in (input_path, output_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

# -------------------- Handlers ------------------
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "🎙 Привет! Я перевожу голосовые и аудиофайлы в текст.\n"
        "Просто пришли мне аудио или voice-сообщение.\n\n"
        "Если у тебя видео — сначала вырежи звук и отправь аудио."
    )

@dp.message(lambda m: m.text and m.text.strip().lower() == "/myid")
async def myid_cmd(message: types.Message):
    await message.answer(f"Твой Telegram ID: {message.from_user.id}")

@dp.message(lambda m: m.voice)
async def on_voice(message: types.Message):
    await handle_media(message, "voice")

@dp.message(lambda m: m.audio)
async def on_audio(message: types.Message):
    await handle_media(message, "audio")

@dp.message(lambda m: m.video)
async def on_video(message: types.Message):
    await handle_media(message, "video")

# -------------------- Run -----------------------
async def run_bot():
    logging.info("🤖 VoiceMaster clean bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(run_bot())
