#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import sqlite3
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)

# ------------------- KONSTANTALAR -------------------
BOT_TOKEN = "8456456490:AAHFrLODy8NWo_cPaMMQWOOC3pGr4KvT5mI"  # Tokeningiz
CHANNEL = "@TD_CODERS_CHANEL"
CHANNEL_LINK = "https://t.me/TD_CODERS_CHANEL"
DB_PATH = "users.db"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------- MA'LUMOTLAR BAZASI -------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, subscribed BOOLEAN DEFAULT 0)''')
    conn.commit()
    conn.close()

def set_subscribed(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, subscribed) VALUES (?, 1)", (user_id,))
    conn.commit()
    conn.close()

def is_subscribed(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT subscribed FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None and row[0] == 1

# ------------------- MAFIA O'YINI KLASSI -------------------
MAFIA = 'mafia'
TOWN = 'town'
DOCTOR = 'doctor'
SHERIFF = 'sheriff'

class MafiaGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = {}  # user_id -> {'name': name, 'role': None, 'alive': True}
        self.phase = 'registration'  # registration, night, day
        self.mafia_kill_target = None
        self.doctor_save_target = None
        self.sheriff_investigate_target = None
        self.votes = {}
        self.night_action_done = set()
        self.winner = None

    def add_player(self, user_id, name):
        if user_id not in self.players and self.phase == 'registration':
            self.players[user_id] = {'name': name, 'role': None, 'alive': True}
            return True
        return False

    def remove_player(self, user_id):
        if user_id in self.players and self.phase == 'registration':
            del self.players[user_id]
            return True
        return False

    def start_game(self):
        if len(self.players) < 4:
            return False
        num_players = len(self.players)
        num_mafia = max(1, num_players // 4)
        num_doctor = 1 if num_players >= 5 else 0
        num_sheriff = 1 if num_players >= 5 else 0
        roles = [MAFIA] * num_mafia + [DOCTOR] * num_doctor + [SHERIFF] * num_sheriff
        roles += [TOWN] * (num_players - len(roles))
        random.shuffle(roles)
        for i, (user_id, data) in enumerate(self.players.items()):
            data['role'] = roles[i]
        self.phase = 'night'
        self.night_action_done.clear()
        return True

    def get_alive_players(self):
        return {uid: p for uid, p in self.players.items() if p['alive']}

    def get_mafia_players(self):
        return {uid: p for uid, p in self.players.items() if p['alive'] and p['role'] == MAFIA}

    def get_town_players(self):
        return {uid: p for uid, p in self.players.items() if p['alive'] and p['role'] != MAFIA}

    def process_night(self):
        killed = None
        if self.mafia_kill_target and self.mafia_kill_target in self.players and self.players[self.mafia_kill_target]['alive']:
            killed = self.mafia_kill_target
        if self.doctor_save_target and self.doctor_save_target == killed:
            killed = None
        if killed:
            self.players[killed]['alive'] = False
        investigation_result = None
        if self.sheriff_investigate_target and self.sheriff_investigate_target in self.players:
            target_role = self.players[self.sheriff_investigate_target]['role']
            investigation_result = (self.sheriff_investigate_target, target_role)
        self.mafia_kill_target = None
        self.doctor_save_target = None
        self.sheriff_investigate_target = None
        self.night_action_done.clear()
        return killed, investigation_result

    def check_win(self):
        alive = self.get_alive_players()
        mafia_alive = [uid for uid, p in alive.items() if p['role'] == MAFIA]
        town_alive = [uid for uid, p in alive.items() if p['role'] != MAFIA]
        if len(mafia_alive) >= len(town_alive):
            self.winner = 'Mafia'
            return True
        elif len(mafia_alive) == 0:
            self.winner = 'Town'
            return True
        return False

    def reset_votes(self):
        self.votes = {}

    def vote(self, voter_id, target_id):
        if voter_id not in self.players or not self.players[voter_id]['alive']:
            return False
        if target_id not in self.players or not self.players[target_id]['alive']:
            return False
        self.votes[voter_id] = target_id
        return True

    def count_votes(self):
        vote_count = {}
        for target in self.votes.values():
            vote_count[target] = vote_count.get(target, 0) + 1
        if not vote_count:
            return None
        max_votes = max(vote_count.values())
        candidates = [uid for uid, count in vote_count.items() if count == max_votes]
        if len(candidates) == 1:
            return candidates[0]
        return None

# Global mafia o'yinlari lug'ati
mafia_games = {}

# ------------------- HOLATLAR -------------------
(SUBSCRIBE, MAIN_MENU, BOT_CREATION, PROMPTS, 
 MAFIA_REG, MAFIA_NIGHT, MAFIA_DAY, MAFIA_VOTE) = range(8)

# ------------------- KLAVIATURALAR -------------------
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("👤 Men haqimda"), KeyboardButton("🤖 Bot yaratish")],
        [KeyboardButton("📞 Telefon 2x"), KeyboardButton("🗒 QR kod")],
        [KeyboardButton("🚀 CS2"), KeyboardButton("🐍 Python")],
        [KeyboardButton("📜 Internet arxivi"), KeyboardButton("🎹 Virtual pianino")],
        [KeyboardButton("📻 Global radio"), KeyboardButton("🤖 AI rasm")],
        [KeyboardButton("📚 Bepul kitoblar"), KeyboardButton("🎮 Retro o'yinlar")],
        [KeyboardButton("🌍 Tarixiy xaritalar"), KeyboardButton("📝 Cheat sheet")],
        [KeyboardButton("🎵 Musiqa yaratish"), KeyboardButton("🪐 Kosmik tasvirlar")],
        [KeyboardButton("📝 Promptlar")],
        [KeyboardButton("🎲 Mafia o'yini")]  # Yangi tugma
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def bot_creation_keyboard():
    keyboard = [
        [KeyboardButton("🎥 Video dars")],
        [KeyboardButton("📥 Video downloader bot")],
        [KeyboardButton("📱 Pydroid 3")],
        [KeyboardButton("🔙 Orqaga")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def prompts_keyboard():
    keyboard = [
        [KeyboardButton("🔥 1. Motivatsion / Ibratli rasm")],
        [KeyboardButton("💔 2. Sevgi va drama")],
        [KeyboardButton("🏍 3. Bad boy / BMW vibe")],
        [KeyboardButton("🌌 4. Fantasy / Kuchli aura")],
        [KeyboardButton("🤖 5. AI / Futuristic")],
        [KeyboardButton("🌿 6. Tinchlik va tabiat")],
        [KeyboardButton("🕌 7. Diniy / Ibratli")],
        [KeyboardButton("🎮 8. O'yin uslubida")],
        [KeyboardButton("🔙 Orqaga")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def subscription_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 Kanalga o'tish", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ------------------- HANDLERLAR -------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_subscribed(user_id):
        await update.message.reply_text("Xush kelibsiz!", reply_markup=main_menu_keyboard())
        return MAIN_MENU
    else:
        await update.message.reply_text(
            "Botdan foydalanish uchun kanalimizga obuna bo'ling:",
            reply_markup=subscription_keyboard()
        )
        return SUBSCRIBE

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            set_subscribed(user_id)
            await query.edit_message_text("✅ Obuna tasdiqlandi!")
            await query.message.reply_text("Asosiy menyu:", reply_markup=main_menu_keyboard())
            return MAIN_MENU
        else:
            await query.answer("Siz hali kanalga obuna bo‘lmagansiz.", show_alert=True)
            return SUBSCRIBE
    except Exception as e:
        logger.exception("Obuna tekshirish xatosi")
        await query.answer("Xatolik yuz berdi. Qaytadan urinib ko‘ring.", show_alert=True)
        return SUBSCRIBE

async def subscribe_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Botdan foydalanish uchun avval kanalga obuna bo‘ling:",
        reply_markup=subscription_keyboard()
    )
    return SUBSCRIBE

# ------------------- ASOSIY MENYU -------------------
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if not is_subscribed(user_id):
        await update.message.reply_text(
            "Iltimos, avval kanalga obuna bo‘ling:",
            reply_markup=subscription_keyboard()
        )
        return SUBSCRIBE

    # TD_CODERS tugmalari
    if text == "👤 Men haqimda":
        about_text = (
            "👋 Men @TD_CODERS botiman. Sizga Telegram botlar yaratishda va "
            "turli xil sirli fishkalarda yordam beraman.\n"
            "Yaratuvchilar: Temur va Doston.\n"
            "Agar bot yaratmoqchi yoki sotib olmoqchi bo‘lsangiz, admin bilan bog‘laning:\n"
            "📞 +998 77 408 00 12\n"
            "Salomat bo‘ling!"
        )
        await update.message.reply_text(about_text)
    elif text == "🤖 Bot yaratish":
        await update.message.reply_text("Bo'limni tanlang:", reply_markup=bot_creation_keyboard())
        return BOT_CREATION
    elif text == "📞 Telefon 2x":
        keyboard = [[InlineKeyboardButton("📲 Play Marketdan yuklash", url="https://play.google.com/store/apps/details?id=com.goodev.volume.booster")]]
        await update.message.reply_text(
            "📞 **Telefon ovozini 2X baland qilish**\n\n"
            "Ilovani quyidagi link orqali Play Marketdan yuklab oling 👇\n\n"
            "https://play.google.com/store/apps/details?id=com.goodev.volume.booster\n\n"
            "**Volume Booster GOODEV** - oddiy va kichik ilova.\n"
            "⚠️ Eslatma: Ovozni juda baland qilish dinamik va eshitishga zarar yetkazishi mumkin.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    elif text == "🗒 QR kod":
        keyboard = [[InlineKeyboardButton("✈️ Telegram", url=CHANNEL_LINK)]]
        await update.message.reply_text(
            "🗒 **QR kod yaratish uchun sayt**\n\n"
            "Shaxsiy QR kod kerakmi? Ushbu sayt orqali o‘zingiz uchun ma‘lumot to‘ldirilgan QR kod olishingiz mumkin.\n\n"
            "📍 **Sayt manzili:** 👇\n"
            "ru.qr-code-generator.com",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    elif text == "🚀 CS2":
        caption = (
            "🚀 **Cloud RTX — Kuchli PC’siz ham TOP daraja!**\n\n"
            "Oddiy kompyuter bilan ham og‘ir o‘yinlar va dasturlarni ishlatmoqchimisiz?\n\n"
            "Cloud RTX — bulutli RTX GPU xizmati orqali siz masofadan kuchli videokarta quvvatidan foydalanasiz.\n\n"
            "🎮 Counter-Strike 2 (CS2) ni laglarsiz o‘ynang\n"
            "🎬 Video montaj va render qiling\n"
            "💻 Og‘ir dasturlarni bemalol ishlating\n"
            "⚡️ Kuchli PC sotib olish shart emas\n\n"
            "🔗 Hoziroq sinab ko‘ring:\n"
            "🤖 Bot: @UzDigitalZTbot\n"
            "📢 Kanal: @TD_CODERS_CHANEL\n\n"
            "🔥 Cloud RTX bilan o‘yin va ish — yangi darajada!"
        )
        keyboard = [[InlineKeyboardButton("🤖 Cloud RTX bot", url="https://t.me/UzDigitalZTbot")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            with open("cloud_rtx.jpg", "rb") as photo:
                await update.message.reply_photo(photo=photo, caption=caption, parse_mode='Markdown', reply_markup=reply_markup)
        except FileNotFoundError:
            await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=reply_markup)
    elif text == "🐍 Python":
        caption = (
            "🐍 **Python dasturlash tili**\n\n"
            "Python - oddiy va kuchli dasturlash tili. Yangi boshlovchilar uchun eng yaxshi tanlov!\n\n"
            "📥 **Yuklab olish:**\n"
            "Rasmiy sayt: https://www.python.org/downloads/\n\n"
            "📚 **Qo‘shimcha resurslar:**\n"
            "- Dokumentatsiya: https://docs.python.org/\n"
            "- W3Schools darslik: https://www.w3schools.com/python/\n"
            "- GeeksforGeeks: https://www.geeksforgeeks.org/python-programming-language/\n\n"
            "💡 **Nima uchun Python?**\n"
            "- O‘rganish oson\n"
            "- Katta hamjamiyat\n"
            "- Ko‘plab kutubxonalar\n"
            "- Sun'iy intellekt, veb-ishlanma, ma'lumotlar tahlili va boshqa sohalarda ishlatiladi\n\n"
            "⚡️ **Tezkor start:**\n"
            "```python\n"
            'print("Hello, World!")\n'
            "```"
        )
        try:
            with open("python_logo.png", "rb") as photo:
                await update.message.reply_photo(photo=photo, caption=caption, parse_mode='Markdown')
        except FileNotFoundError:
            await update.message.reply_text(caption, parse_mode='Markdown')
    elif text == "📜 Internet arxivi":
        caption = (
            "📜 **Internet Archive (Wayback Machine)**\n\n"
            "Veb-saytlarning eski versiyalarini ko‘rish, millionlab kitob, musiqa, video va dasturiy ta'minot arxivi.\n\n"
            "🌐 **Sayt:** https://archive.org\n\n"
            "🔍 Wayback Machine orqali istalgan saytning tarixini kuzating."
        )
        keyboard = [[InlineKeyboardButton("🔗 Saytga o‘tish", url="https://archive.org")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "🎹 Virtual pianino":
        caption = (
            "🎹 **Online Pianino**\n\n"
            "Brauzerda bepul pianino chalish, turli kuylarni yozib olish va ijro etish.\n\n"
            "🌐 **Sayt:** https://www.onlinepianist.com/virtual-piano\n\n"
            "🎼 Klaviatura yordamida chalish mumkin."
        )
        keyboard = [[InlineKeyboardButton("🔗 Saytga o‘tish", url="https://www.onlinepianist.com/virtual-piano")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "📻 Global radio":
        caption = (
            "📻 **Radio Garden**\n\n"
            "Dunyoning istalgan nuqtasidagi radiostansiyalarni onlayn tinglash.\n\n"
            "🌐 **Sayt:** https://radio.garden\n\n"
            "🌍 Xaritada radio uzatish nuqtalarini toping va tinglang."
        )
        keyboard = [[InlineKeyboardButton("🔗 Saytga o‘tish", url="https://radio.garden")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "🤖 AI rasm":
        caption = (
            "🤖 **Craiyon (AI rasm yaratish)**\n\n"
            "Matn asosida sun'iy intellekt yordamida rasm yaratish (eski DALL-E mini).\n\n"
            "🌐 **Sayt:** https://www.craiyon.com\n\n"
            "✍️ Istalgan matnni yozing va AI rasm yaratadi."
        )
        keyboard = [[InlineKeyboardButton("🔗 Saytga o‘tish", url="https://www.craiyon.com")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "📚 Bepul kitoblar":
        caption = (
            "📚 **Project Gutenberg**\n\n"
            "60 000 dan ortiq bepul elektron kitoblar (asosan ingliz tilida).\n\n"
            "🌐 **Sayt:** https://www.gutenberg.org\n\n"
            "📖 Klassik asarlarni bepul o‘qing."
        )
        keyboard = [[InlineKeyboardButton("🔗 Saytga o‘tish", url="https://www.gutenberg.org")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "🎮 Retro o'yinlar":
        caption = (
            "🎮 **RetroGames**\n\n"
            "Brauzerda eski konsol o‘yinlarini o‘ynang (NES, SNES, GameBoy va boshqalar).\n\n"
            "🌐 **Sayt:** https://www.retrogames.cc\n\n"
            "🕹️ To‘liq o‘yinlar to‘plami."
        )
        keyboard = [[InlineKeyboardButton("🔗 Saytga o‘tish", url="https://www.retrogames.cc")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "🌍 Tarixiy xaritalar":
        caption = (
            "🌍 **Old Maps Online**\n\n"
            "Tarixiy xaritalar to‘plami, qidirish va zamonaviy xaritalar bilan solishtirish imkoniyati.\n\n"
            "🌐 **Sayt:** https://www.oldmapsonline.org\n\n"
            "🗺️ O‘tmishga sayohat qiling."
        )
        keyboard = [[InlineKeyboardButton("🔗 Saytga o‘tish", url="https://www.oldmapsonline.org")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "📝 Cheat sheet":
        caption = (
            "📝 **Cheatography**\n\n"
            "Dasturlash, tizim ma'muriyati va boshqa sohalar uchun cheat sheetlar to‘plami.\n\n"
            "🌐 **Sayt:** https://cheatography.com\n\n"
            "📋 Foydali qisqacha ma'lumotlar."
        )
        keyboard = [[InlineKeyboardButton("🔗 Saytga o‘tish", url="https://cheatography.com")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "🎵 Musiqa yaratish":
        caption = (
            "🎵 **Soundtrap**\n\n"
            "Onlayn musiqa yozish studiyasi, looplar va asboblar bilan (oddiy versiya bepul).\n\n"
            "🌐 **Sayt:** https://www.soundtrap.com\n\n"
            "🎧 O‘z trekingizni yarating."
        )
        keyboard = [[InlineKeyboardButton("🔗 Saytga o‘tish", url="https://www.soundtrap.com")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "🪐 Kosmik tasvirlar":
        caption = (
            "🪐 **NASA Image and Video Library**\n\n"
            "NASAning barcha rasmlari va videolari to‘plami.\n\n"
            "🌐 **Sayt:** https://images.nasa.gov\n\n"
            "🌌 Koinotga oid minglab tasvirlar."
        )
        keyboard = [[InlineKeyboardButton("🔗 Saytga o‘tish", url="https://images.nasa.gov")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "📝 Promptlar":
        await update.message.reply_text("Prompt variantlaridan birini tanlang:", reply_markup=prompts_keyboard())
        return PROMPTS
    elif text == "🎲 Mafia o'yini":
        # Mafia o'yinini boshlash uchun alohida holatga o'tamiz
        await update.message.reply_text(
            "Mafia o'yiniga xush kelibsiz!\n"
            "Buyruqlar:\n"
            "/mafia_join - O'yinga qo'shilish\n"
            "/mafia_leave - O'yindan chiqish (boshlanmasdan oldin)\n"
            "/mafia_start - O'yinni boshlash (kamida 4 kishi)\n"
            "/mafia_status - O'yin holati\n"
            "/mafia_cancel - O'yinni bekor qilish\n\n"
            "Mafia o'ynash uchun yuqoridagi buyruqlardan foydalaning."
        )
        return MAIN_MENU  # Mafia buyruqlarini alohida command handlerlar orqali boshqaramiz
    else:
        await update.message.reply_text("Iltimos, quyidagi tugmalardan birini tanlang.", reply_markup=main_menu_keyboard())
    return MAIN_MENU

# ------------------- BOT YARATISH -------------------
async def bot_creation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🎥 Video dars":
        keyboard = [[InlineKeyboardButton("📢 Kanalga o'tish", url=CHANNEL_LINK)]]
        await update.message.reply_text("Video darslar kanalimizda:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "📥 Video downloader bot":
        await update.message.reply_text("Video downloader bot kodi tayyorlanmoqda...")
    elif text == "📱 Pydroid 3":
        await update.message.reply_text(
            "📱 Pydroid 3 uchun qo‘llanma:\n"
            "1. Pydroid 3 ni Google Play’dan o‘rnating.\n"
            "2. `pip install python-telegram-bot` buyrug‘i bilan kutubxonani o‘rnating.\n"
            "3. Bot kodingizni yozib, ishga tushiring."
        )
    elif text == "🔙 Orqaga":
        await update.message.reply_text("Asosiy menyu:", reply_markup=main_menu_keyboard())
        return MAIN_MENU
    else:
        await update.message.reply_text("Iltimos, quyidagi tugmalardan birini tanlang:", reply_markup=bot_creation_keyboard())
    return BOT_CREATION

# ------------------- PROMPTLAR -------------------
async def prompts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if not is_subscribed(user_id):
        await update.message.reply_text("Iltimos, avval kanalga obuna bo‘ling:", reply_markup=subscription_keyboard())
        return SUBSCRIBE

    if text == "🔙 Orqaga":
        await update.message.reply_text("Asosiy menyu:", reply_markup=main_menu_keyboard())
        return MAIN_MENU
    elif text == "🔥 1. Motivatsion / Ibratli rasm":
        prompt = (
            "A lonely young man standing under heavy rain at night, holding a red rose, "
            "cinematic lighting, dramatic atmosphere, ultra realistic, 8k, emotional mood, "
            "deep shadows, high detail face, wet clothes, realistic rain drops, masterpiece photography"
        )
        await update.message.reply_text(prompt)
    elif text == "💔 2. Sevgi va drama":
        prompt = (
            "A broken hearted boy throwing a red rose into a river during heavy rain, "
            "dark cloudy sky, cinematic scene, emotional, realistic water splashes, ultra HD, "
            "dramatic lighting, sad atmosphere, 8k, highly detailed"
        )
        await update.message.reply_text(prompt)
    elif text == "🏍 3. Bad boy / BMW vibe":
        prompt = (
            "A stylish young man riding a black BMW motorcycle in the rain at night, "
            "neon city lights, cinematic, ultra realistic, wet street reflections, 8k resolution, "
            "dramatic lighting, cool attitude, masterpiece"
        )
        await update.message.reply_text(prompt)
    elif text == "🌌 4. Fantasy / Kuchli aura":
        prompt = (
            "A powerful young warrior surrounded by blue lightning aura, standing on a mountain cliff, "
            "stormy sky, fantasy art, ultra detailed, 8k, cinematic lighting, epic scene, high quality"
        )
        await update.message.reply_text(prompt)
    elif text == "🤖 5. AI / Futuristic":
        prompt = (
            "A futuristic AI robot standing in a cyberpunk city, neon lights, ultra realistic, 8k, "
            "high detail, glowing eyes, sci-fi atmosphere, cinematic angle, masterpiece"
        )
        await update.message.reply_text(prompt)
    elif text == "🌿 6. Tinchlik va tabiat":
        prompt = (
            "A peaceful green valley with waterfalls and sunlight breaking through clouds, "
            "ultra realistic, 8k landscape photography, high detail, vibrant colors, cinematic nature scene"
        )
        await update.message.reply_text(prompt)
    elif text == "🕌 7. Diniy / Ibratli":
        prompt = (
            "A young man praying alone at sunset inside a beautiful mosque, golden sunlight coming through windows, "
            "peaceful atmosphere, ultra realistic, high detail, 8k, spiritual mood, cinematic lighting"
        )
        await update.message.reply_text(prompt)
    elif text == "🎮 8. O'yin uslubida":
        prompt = (
            "A realistic open world game character standing in a modern city, GTA style, ultra HD, cinematic, "
            "high detail textures, realistic shadows, 8k, dramatic atmosphere"
        )
        await update.message.reply_text(prompt)
    else:
        await update.message.reply_text("Iltimos, quyidagi tugmalardan birini tanlang:", reply_markup=prompts_keyboard())
    return PROMPTS

# ------------------- MAFIA HANDLERLARI -------------------
async def mafia_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in mafia_games:
        mafia_games[chat_id] = MafiaGame(chat_id)
    game = mafia_games[chat_id]
    if game.add_player(user.id, user.full_name):
        await update.message.reply_text(f"{user.full_name} mafia o'yiniga qo'shildi. ({len(game.players)} o'yinchi)")
    else:
        await update.message.reply_text("Siz allaqachon qo'shilgansiz yoki o'yin boshlangan.")

async def mafia_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = mafia_games.get(chat_id)
    if game and game.remove_player(user.id):
        await update.message.reply_text(f"{user.full_name} o'yindan chiqdi.")
    else:
        await update.message.reply_text("Siz o'yinda emassiz yoki o'yin boshlangan.")

async def mafia_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = mafia_games.get(chat_id)
    if not game:
        await update.message.reply_text("Hech qanday o'yin mavjud emas. /mafia_join orqali qo'shiling.")
        return
    if game.phase != 'registration':
        await update.message.reply_text("O'yin allaqachon boshlangan.")
        return
    if game.start_game():
        await update.message.reply_text("Mafia o'yini boshlandi! Tun fasli. Shaxsiy xabarlaringizni tekshiring.")
        for user_id, data in game.players.items():
            try:
                await context.bot.send_message(
                    user_id,
                    f"Sizning rolingiz: {data['role'].capitalize()}\n"
                    f"O'yin {chat_id} chatida.\n"
                    f"Tun davomida buyruqlarni shaxsiy xabarda yuboring:\n"
                    f"Mafiya: /kill <player_id>\n"
                    f"Doktor: /save <player_id>\n"
                    f"Sherif: /investigate <player_id>"
                )
            except Exception as e:
                logger.error(f"Xabar jo'natib bo'lmadi {user_id}: {e}")
        await context.bot.send_message(chat_id, "Tun tushdi. Mafiya, Doktor va Sherif o'z harakatlarini shaxsiy xabarda bajaring.")
    else:
        await update.message.reply_text("O'yinni boshlash uchun kamida 4 o'yinchi kerak.")

async def mafia_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    game = mafia_games.get(chat_id)
    if not game:
        await update.message.reply_text("Faol o'yin mavjud emas.")
        return
    if user_id not in game.players:
        await update.message.reply_text("Siz bu o'yinda emassiz.")
        return
    player = game.players[user_id]
    alive_players = game.get_alive_players()
    status_text = f"Tirik o'yinchilar ({len(alive_players)}):\n"
    for uid, p in alive_players.items():
        status_text += f"- {p['name']} (ID: {uid})\n"
    status_text += f"\nSizning rolingiz: {player['role'].capitalize()}\n"
    if player['role'] == MAFIA:
        mafia_players = game.get_mafia_players()
        status_text += "Mafiya jamoadoshlaringiz:\n"
        for uid, p in mafia_players.items():
            if uid != user_id:
                status_text += f"- {p['name']}\n"
    await update.message.reply_text(status_text)

async def mafia_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in mafia_games:
        del mafia_games[chat_id]
        await update.message.reply_text("Mafia o'yini bekor qilindi.")
    else:
        await update.message.reply_text("Faol o'yin mavjud emas.")

# Mafia night actions (private)
async def mafia_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = None
    # Find which game this user is in (we need to know chat_id)
    for gid, game in mafia_games.items():
        if user_id in game.players:
            chat_id = gid
            break
    if not chat_id:
        await update.message.reply_text("Siz hech qanday mafia o'yinida emassiz.")
        return
    game = mafia_games[chat_id]
    if game.phase != 'night':
        await update.message.reply_text("Hozir tun emas.")
        return
    if user_id not in game.players or game.players[user_id]['role'] != MAFIA:
        await update.message.reply_text("Siz mafiya emassiz.")
        return
    if not game.players[user_id]['alive']:
        await update.message.reply_text("Siz o'liksiz.")
        return
    if user_id in game.night_action_done:
        await update.message.reply_text("Siz allaqachon tunlik harakatingizni bajargansiz.")
        return
    if not context.args:
        await update.message.reply_text("Ishlatish: /kill <player_id>")
        return
    try:
        target_id = int(context.args[0])
    except:
        await update.message.reply_text("Noto'g'ri player ID.")
        return
    if target_id not in game.players or not game.players[target_id]['alive']:
        await update.message.reply_text("Bunday tirik o'yinchi yo'q.")
        return
    if game.players[target_id]['role'] == MAFIA:
        await update.message.reply_text("Mafiya o'zini o'ldira olmaydi.")
        return
    game.mafia_kill_target = target_id
    game.night_action_done.add(user_id)
    await update.message.reply_text(f"Siz {game.players[target_id]['name']} ni o'ldirishni tanladingiz.")
    await check_mafia_night_complete(game, context)

async def mafia_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = None
    for gid, game in mafia_games.items():
        if user_id in game.players:
            chat_id = gid
            break
    if not chat_id:
        await update.message.reply_text("Siz hech qanday mafia o'yinida emassiz.")
        return
    game = mafia_games[chat_id]
    if game.phase != 'night':
        await update.message.reply_text("Hozir tun emas.")
        return
    if user_id not in game.players or game.players[user_id]['role'] != DOCTOR:
        await update.message.reply_text("Siz doktor emassiz.")
        return
    if not game.players[user_id]['alive']:
        await update.message.reply_text("Siz o'liksiz.")
        return
    if user_id in game.night_action_done:
        await update.message.reply_text("Siz allaqachon tunlik harakatingizni bajargansiz.")
        return
    if not context.args:
        await update.message.reply_text("Ishlatish: /save <player_id>")
        return
    try:
        target_id = int(context.args[0])
    except:
        await update.message.reply_text("Noto'g'ri player ID.")
        return
    if target_id not in game.players or not game.players[target_id]['alive']:
        await update.message.reply_text("Bunday tirik o'yinchi yo'q.")
        return
    game.doctor_save_target = target_id
    game.night_action_done.add(user_id)
    await update.message.reply_text(f"Siz {game.players[target_id]['name']} ni saqlashni tanladingiz.")
    await check_mafia_night_complete(game, context)

async def mafia_investigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = None
    for gid, game in mafia_games.items():
        if user_id in game.players:
            chat_id = gid
            break
    if not chat_id:
        await update.message.reply_text("Siz hech qanday mafia o'yinida emassiz.")
        return
    game = mafia_games[chat_id]
    if game.phase != 'night':
        await update.message.reply_text("Hozir tun emas.")
        return
    if user_id not in game.players or game.players[user_id]['role'] != SHERIFF:
        await update.message.reply_text("Siz sherif emassiz.")
        return
    if not game.players[user_id]['alive']:
        await update.message.reply_text("Siz o'liksiz.")
        return
    if user_id in game.night_action_done:
        await update.message.reply_text("Siz allaqachon tunlik harakatingizni bajargansiz.")
        return
    if not context.args:
        await update.message.reply_text("Ishlatish: /investigate <player_id>")
        return
    try:
        target_id = int(context.args[0])
    except:
        await update.message.reply_text("Noto'g'ri player ID.")
        return
    if target_id not in game.players or not game.players[target_id]['alive']:
        await update.message.reply_text("Bunday tirik o'yinchi yo'q.")
        return
    game.sheriff_investigate_target = target_id
    game.night_action_done.add(user_id)
    await update.message.reply_text(f"Siz {game.players[target_id]['name']} ni tekshirishni tanladingiz.")
    await check_mafia_night_complete(game, context)

async def check_mafia_night_complete(game, context):
    alive = game.get_alive_players()
    needed_roles = []
    for uid, p in alive.items():
        if p['role'] == MAFIA and uid not in game.night_action_done:
            needed_roles.append('Mafia')
        elif p['role'] == DOCTOR and uid not in game.night_action_done:
            needed_roles.append('Doctor')
        elif p['role'] == SHERIFF and uid not in game.night_action_done:
            needed_roles.append('Sheriff')
    if not needed_roles:
        killed, investigation = game.process_night()
        if killed:
            await context.bot.send_message(game.chat_id, f"Tun davomida {game.players[killed]['name']} o'ldirildi.")
        else:
            await context.bot.send_message(game.chat_id, "Tun tinch o'tdi. Hech kim o'lmadi.")
        if investigation:
            target_id, role = investigation
            sheriff_id = None
            for uid, p in alive.items():
                if p['role'] == SHERIFF:
                    sheriff_id = uid
                    break
            if sheriff_id:
                try:
                    await context.bot.send_message(sheriff_id, f"Tekshiruv natijasi: {game.players[target_id]['name']} - {role}.")
                except:
                    pass
        if game.check_win():
            await context.bot.send_message(game.chat_id, f"O'yin tugadi! {game.winner} g'alaba qozondi!")
            del mafia_games[game.chat_id]
            return
        game.phase = 'day'
        game.reset_votes()
        await context.bot.send_message(game.chat_id, "Kun boshlandi. Munozara qiling va kimni osishni hal qiling. Ovoz berish uchun /mafia_vote <player_id> dan foydalaning. Ovoz berishni tugatish uchun /mafia_endvote.")
    else:
        pass

async def mafia_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    game = mafia_games.get(chat_id)
    if not game:
        await update.message.reply_text("Bu chatda mafia o'yini mavjud emas.")
        return
    if game.phase != 'day':
        await update.message.reply_text("Hozir kun emas.")
        return
    if user_id not in game.players or not game.players[user_id]['alive']:
        await update.message.reply_text("Siz tirik o'yinchi emassiz.")
        return
    if not context.args:
        await update.message.reply_text("Ishlatish: /mafia_vote <player_id>")
        return
    try:
        target_id = int(context.args[0])
    except:
        await update.message.reply_text("Noto'g'ri player ID.")
        return
    if target_id not in game.players or not game.players[target_id]['alive']:
        await update.message.reply_text("Bunday tirik o'yinchi yo'q.")
        return
    if game.vote(user_id, target_id):
        await update.message.reply_text(f"Siz {game.players[target_id]['name']} ga ovoz berdingiz.")
    else:
        await update.message.reply_text("Ovoz berish amalga oshmadi.")

async def mafia_endvote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = mafia_games.get(chat_id)
    if not game:
        await update.message.reply_text("Bu chatda mafia o'yini mavjud emas.")
        return
    if game.phase != 'day':
        await update.message.reply_text("Hozir kun emas.")
        return
    lynched_id = game.count_votes()
    if lynched_id is None:
        await update.message.reply_text("Ko'pchilik ovoz mavjud emas. Hech kim osilmadi.")
    else:
        game.players[lynched_id]['alive'] = False
        await context.bot.send_message(chat_id, f"{game.players[lynched_id]['name']} osildi.")
        if game.check_win():
            await context.bot.send_message(chat_id, f"O'yin tugadi! {game.winner} g'alaba qozondi!")
            del mafia_games[chat_id]
            return
    game.phase = 'night'
    game.night_action_done.clear()
    await context.bot.send_message(chat_id, "Tun tushdi. Mafiya, Doktor va Sherif o'z harakatlarini bajaring.")

# ------------------- FALLBACK -------------------
async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Tushunarsiz buyruq. Iltimos, /start ni bosing.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_subscribed(user_id):
        await update.message.reply_text("Bekor qilindi. Asosiy menyu:", reply_markup=main_menu_keyboard())
        return MAIN_MENU
    else:
        await update.message.reply_text("Bekor qilindi. Iltimos, /start ni bosing.")
        return ConversationHandler.END

# ------------------- ASOSIY -------------------
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SUBSCRIBE: [
                CallbackQueryHandler(check_subscription_callback, pattern="^check_sub$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, subscribe_remind),
            ],
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)],
            BOT_CREATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot_creation_handler)],
            PROMPTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, prompts_handler)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(filters.ALL, fallback)
        ],
        per_chat=True,
        allow_reentry=True
    )
    app.add_handler(conv_handler)

    # Mafia buyruqlari (command handlerlar)
    app.add_handler(CommandHandler("mafia_join", mafia_join))
    app.add_handler(CommandHandler("mafia_leave", mafia_leave))
    app.add_handler(CommandHandler("mafia_start", mafia_start))
    app.add_handler(CommandHandler("mafia_status", mafia_status))
    app.add_handler(CommandHandler("mafia_cancel", mafia_cancel))
    app.add_handler(CommandHandler("kill", mafia_kill, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("save", mafia_save, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("investigate", mafia_investigate, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("mafia_vote", mafia_vote, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("mafia_endvote", mafia_endvote, filters=filters.ChatType.GROUPS))

    # Umumiy cancel
    app.add_handler(CommandHandler('cancel', cancel))

    logger.info("🤖 Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":

    main()
