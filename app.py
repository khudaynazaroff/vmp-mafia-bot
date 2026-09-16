import asyncio
import logging
import random
import sqlite3
from collections import Counter

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup


# ============================================================
# 🔑 SOZLAMALAR
# ============================================================
TOKEN = "8816776063:AAF4PYFBC0T38R1IX93sZ3XWPUr9-mbgADY"
ADMIN_IDS = [7144305935]
DB_NAME = "vmp_mafia.db"

MIN_PLAYERS = 5
MAX_PLAYERS = 20
JOIN_SECONDS = 60
DAY_SECONDS = 60
NIGHT_SECONDS = 45

# Rollar uchun standart nisbatlar
ROLE_SETUPS = {
    5:  {"mafia": 1, "doctor": 1, "detective": 1, "civilian": 2},
    6:  {"mafia": 2, "doctor": 1, "detective": 1, "civilian": 2},
    7:  {"mafia": 2, "doctor": 1, "detective": 1, "civilian": 3},
    8:  {"mafia": 2, "doctor": 1, "detective": 1, "civilian": 4},
    9:  {"mafia": 3, "doctor": 1, "detective": 1, "civilian": 4},
    10: {"mafia": 3, "doctor": 1, "detective": 1, "civilian": 5},
    11: {"mafia": 3, "doctor": 1, "detective": 1, "civilian": 6},
    12: {"mafia": 4, "doctor": 1, "detective": 1, "civilian": 6},
    13: {"mafia": 4, "doctor": 1, "detective": 1, "civilian": 7},
    14: {"mafia": 4, "doctor": 1, "detective": 1, "civilian": 8},
    15: {"mafia": 5, "doctor": 1, "detective": 1, "civilian": 8},
    16: {"mafia": 5, "doctor": 1, "detective": 1, "civilian": 9},
    17: {"mafia": 5, "doctor": 1, "detective": 1, "civilian": 10},
    18: {"mafia": 5, "doctor": 1, "detective": 1, "civilian": 11},
    19: {"mafia": 6, "doctor": 1, "detective": 1, "civilian": 11},
    20: {"mafia": 6, "doctor": 1, "detective": 1, "civilian": 12},
}

ROLE_NAMES = {
    "mafia": "🔪 Mafia",
    "doctor": "💉 Doktor",
    "detective": "🔎 Komissar",
    "civilian": "👤 Tinch aholi",
}

# Do'kon buyumlari: o'yin mexanikasi shu yerda ishlatiladi.
SHOP_ITEMS = {
    "basic_protection": {
        "name": "🛡 Oddiy himoya",
        "price": 5_000,
        "desc": "Mafia hujumidan bir marta saqlaydi.",
    },
    "death_protection": {
        "name": "💀 O'limdan himoya",
        "price": 15_000,
        "desc": "Bir marta o'limga olib keluvchi hujumni bekor qiladi.",
    },
    "poison_protection": {
        "name": "☠️ Zahar himoyasi",
        "price": 8_000,
        "desc": "Zahar hujumidan bir marta saqlaydi.",
    },
    "bullet_protection": {
        "name": "🔫 O'qdan himoya",
        "price": 10_000,
        "desc": "Otishma turidagi hujumdan himoya.",
    },
    "investigation_protection": {
        "name": "👁 Tekshiruvdan himoya",
        "price": 12_000,
        "desc": "Komissar tekshiruvini yashiradi.",
    },
    "strong_protection": {
        "name": "🛡️ Kuchli himoya",
        "price": 20_000,
        "desc": "Ikki hujumga yetadigan himoya.",
    },
    "revive": {
        "name": "❤️ Jonlantirish",
        "price": 30_000,
        "desc": "Bir marta qayta tirilish imkoniyati.",
    },
    "extra_vote": {
        "name": "🗳 Qo'shimcha ovoz",
        "price": 7_000,
        "desc": "Kunduzgi ovoz berishda qo'shimcha ovoz.",
    },
}


# ============================================================
# 🤖 BOT
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# Bir guruh = bitta faol o'yin.
games = {}
game_counter = 0


# ============================================================
# 🗄️ SQLITE
# ============================================================
def db():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            username TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            diamonds INTEGER NOT NULL DEFAULT 0,
            games INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, item_key)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            winner TEXT,
            players INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    for admin_id in ADMIN_IDS:
        cur.execute(
            "INSERT OR IGNORE INTO admins(user_id) VALUES (?)",
            (admin_id,),
        )

    conn.commit()
    conn.close()


def register_user(user):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    exists = cur.fetchone()

    if exists:
        cur.execute(
            "UPDATE users SET full_name=?, username=? WHERE user_id=?",
            (user.full_name, user.username, user.id),
        )
    else:
        cur.execute(
            """
            INSERT INTO users(user_id, full_name, username)
            VALUES (?, ?, ?)
            """,
            (user.id, user.full_name, user.username),
        )

    conn.commit()
    conn.close()


def is_admin(user_id):
    if user_id in ADMIN_IDS:
        return True
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
    ok = cur.fetchone() is not None
    conn.close()
    return ok


def get_balance(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def get_profile(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT full_name, username, balance, diamonds, games, wins, losses
        FROM users WHERE user_id=?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def add_money(user_id, amount):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET balance=balance+? WHERE user_id=?",
        (amount, user_id),
    )
    conn.commit()
    conn.close()


def add_diamonds(user_id, amount):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET diamonds=diamonds+? WHERE user_id=?",
        (amount, user_id),
    )
    conn.commit()
    conn.close()


def buy_item(user_id, item_key):
    item = SHOP_ITEMS.get(item_key)
    if not item:
        return False, "❌ Mahsulot topilmadi."

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "❌ Foydalanuvchi topilmadi."

    balance = row[0]
    if balance < item["price"]:
        conn.close()
        return False, (
            f"❌ Balans yetarli emas.\n"
            f"💰 Sizda: {money(balance)} so'm\n"
            f"💵 Narxi: {money(item['price'])} so'm"
        )

    cur.execute(
        "UPDATE users SET balance=balance-? WHERE user_id=?",
        (item["price"], user_id),
    )
    cur.execute("""
        INSERT INTO inventory(user_id,item_key,quantity)
        VALUES(?,?,1)
        ON CONFLICT(user_id,item_key)
        DO UPDATE SET quantity=quantity+1
    """, (user_id, item_key))

    conn.commit()
    conn.close()
    return True, f"✅ {item['name']} sotib olindi!"


def item_count(user_id, item_key):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_key=?",
        (user_id, item_key),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def use_item(user_id, item_key):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE inventory
        SET quantity=quantity-1
        WHERE user_id=? AND item_key=? AND quantity>0
    """, (user_id, item_key))
    changed = cur.rowcount
    if changed:
        cur.execute(
            "DELETE FROM inventory WHERE user_id=? AND item_key=? AND quantity<=0",
            (user_id, item_key),
        )
    conn.commit()
    conn.close()
    return changed > 0


def get_inventory(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT item_key, quantity
        FROM inventory
        WHERE user_id=? AND quantity>0
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def update_result(user_id, win):
    conn = db()
    cur = conn.cursor()
    if win:
        cur.execute(
            "UPDATE users SET games=games+1,wins=wins+1 WHERE user_id=?",
            (user_id,),
        )
    else:
        cur.execute(
            "UPDATE users SET games=games+1,losses=losses+1 WHERE user_id=?",
            (user_id,),
        )
    conn.commit()
    conn.close()


def money(value):
    return f"{value:,}".replace(",", " ")


# ============================================================
# 🎭 O'YIN MODELI
# ============================================================
class Player:
    def __init__(self, user):
        self.user_id = user.id
        self.name = user.full_name
        self.username = user.username
        self.role = None
        self.alive = True
        self.protected = False
        self.protection_type = None
        self.voted = False

    @property
    def mention(self):
        safe = self.name.replace("<", "").replace(">", "")
        return f'<a href="tg://user?id={self.user_id}">{safe}</a>'


class Game:
    def __init__(self, chat_id, title):
        self.chat_id = chat_id
        self.title = title
        self.players = {}
        self.phase = "lobby"
        self.started = False
        self.day = 0
        self.votes = {}
        self.mafia_target = None
        self.doctor_target = None
        self.detective_target = None
        self.poison_target = None
        self.timer_task = None
        self.message_id = None

    def alive_players(self):
        return [p for p in self.players.values() if p.alive]

    def alive_except(self, user_id):
        return [p for p in self.alive_players() if p.user_id != user_id]

    def mafia(self):
        return [p for p in self.alive_players() if p.role == "mafia"]

    def civilians(self):
        return [
            p for p in self.alive_players()
            if p.role != "mafia"
        ]

    def add_player(self, user):
        if user.id not in self.players and len(self.players) < MAX_PLAYERS:
            self.players[user.id] = Player(user)
            return True
        return False

    def remove_player(self, user_id):
        self.players.pop(user_id, None)

    def assign_roles(self):
        count = len(self.players)
        setup = ROLE_SETUPS.get(count)
        if not setup:
            return False

        roles = []
        for role, amount in setup.items():
            roles += [role] * amount
        random.shuffle(roles)

        for player, role in zip(self.players.values(), roles):
            player.role = role
        return True

    def find(self, user_id):
        return self.players.get(user_id)

    def winner(self):
        alive_mafia = len(self.mafia())
        alive_civilians = len(self.civilians())

        if alive_mafia == 0:
            return "civilian"

        if alive_mafia >= alive_civilians:
            return "mafia"

        return None

    def alive_text(self):
        return "\n".join(
            f"• {p.mention}" for p in self.alive_players()
        )


# ============================================================
# ⌨️ KLAVIATURALAR
# ============================================================
def profile_keyboard():
    k = types.InlineKeyboardMarkup(row_width=2)
    k.row(
        types.InlineKeyboardButton("🛒 Do'kon", callback_data="shop"),
        types.InlineKeyboardButton("🎒 Inventar", callback_data="inventory"),
    )
    k.add(types.InlineKeyboardButton("📊 Statistika", callback_data="my_stats"))
    return k


def shop_keyboard():
    k = types.InlineKeyboardMarkup(row_width=1)
    for key, item in SHOP_ITEMS.items():
        k.add(types.InlineKeyboardButton(
            f"{item['name']} • {money(item['price'])} so'm",
            callback_data=f"buy:{key}",
        ))
    k.add(types.InlineKeyboardButton("🎒 Inventar", callback_data="inventory"))
    k.add(types.InlineKeyboardButton("🔙 Profil", callback_data="profile_back"))
    return k


def lobby_keyboard():
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton(
        "🎯 O'yinga qo'shilish",
        callback_data="join_game",
    ))
    return k


def target_keyboard(game, user_id, action):
    k = types.InlineKeyboardMarkup(row_width=2)
    for p in game.alive_except(user_id):
        k.insert(types.InlineKeyboardButton(
            p.name[:28],
            callback_data=f"{action}:{p.user_id}",
        ))
    k.add(types.InlineKeyboardButton(
        "❌ Bekor qilish",
        callback_data="close_action",
    ))
    return k


# ============================================================
# 🧾 PROFIL
# ============================================================
def profile_text(user_id):
    row = get_profile(user_id)
    if not row:
        return "❌ Profil topilmadi."

    name, username, balance, diamonds, games_n, wins, losses = row
    username_text = f"@{username}" if username else "Mavjud emas"

    return (
        "👤 <b>SIZNING PROFILINGIZ</b>\n\n"
        f"▪️ Ism: {name}\n"
        f"🔗 Username: {username_text}\n"
        f"🆔 ID: <code>{user_id}</code>\n\n"
        f"💰 Balans: <b>{money(balance)}</b> so'm\n"
        f"💎 Olmos: <b>{diamonds}</b>\n\n"
        f"🎮 O'yinlar: <b>{games_n}</b>\n"
        f"🏆 G'alabalar: <b>{wins}</b>\n"
        f"💔 Mag'lubiyatlar: <b>{losses}</b>"
    )


@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    register_user(message.from_user)
    await message.reply(
        "👋 Assalomu alaykum!\n\n"
        "🎭 <b>VMP Mafia</b> botiga xush kelibsiz!\n\n"
        "🎮 Guruhda /game — yangi o'yin\n"
        "👤 /profile — profilingiz\n"
        "🆔 /myid — Telegram ID\n"
        "📖 /help — yordam",
        parse_mode="HTML",
    )


@dp.message_handler(commands=["profile"])
async def profile_cmd(message: types.Message):
    register_user(message.from_user)
    await message.reply(
        profile_text(message.from_user.id),
        reply_markup=profile_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query_handler(text="profile_back")
async def profile_back(call: types.CallbackQuery):
    register_user(call.from_user)
    await call.message.edit_text(
        profile_text(call.from_user.id),
        reply_markup=profile_keyboard(),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query_handler(text="my_stats")
async def my_stats(call: types.CallbackQuery):
    await call.answer(
        "📊 Statistika profilingizda ko'rsatilgan.",
        show_alert=True,
    )


@dp.message_handler(commands=["myid"])
async def myid_cmd(message: types.Message):
    register_user(message.from_user)
    await message.reply(
        f"🆔 Telegram ID: <code>{message.from_user.id}</code>",
        parse_mode="HTML",
    )


@dp.message_handler(commands=["help"])
async def help_cmd(message: types.Message):
    await message.reply(
        "📖 <b>VMP Mafia yordam</b>\n\n"
        "/game — guruhda o'yin yaratish\n"
        "/profile — profil, balans va inventar\n"
        "/myid — ID raqam\n"
        "/stats — bot statistikasi\n"
        "/admin — admin panel\n\n"
        "🎭 O'yinda maxfiy rollar bot orqali yuboriladi.",
        parse_mode="HTML",
    )


# ============================================================
# 🛒 DO'KON
# ============================================================
@dp.callback_query_handler(text="shop")
async def shop_call(call: types.CallbackQuery):
    register_user(call.from_user)
    balance = get_balance(call.from_user.id)

    lines = [
        "🛒 <b>VMP MAFIA DO'KONI</b>",
        "",
        f"💰 Balans: <b>{money(balance)}</b> so'm",
        "",
    ]
    for item in SHOP_ITEMS.values():
        lines.append(
            f"{item['name']} — <b>{money(item['price'])}</b> so'm\n"
            f"└ {item['desc']}"
        )

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=shop_keyboard(),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("buy:"))
async def buy_call(call: types.CallbackQuery):
    key = call.data.split(":", 1)[1]
    ok, text = buy_item(call.from_user.id, key)
    await call.answer(
        text.replace("<b>", "").replace("</b>", ""),
        show_alert=True,
    )
    if ok:
        await shop_call(call)


@dp.callback_query_handler(text="inventory")
async def inventory_call(call: types.CallbackQuery):
    rows = get_inventory(call.from_user.id)

    if not rows:
        text = "🎒 <b>INVENTAR</b>\n\n📦 Inventaringiz bo'sh."
    else:
        lines = ["🎒 <b>INVENTAR</b>", ""]
        for key, qty in rows:
            if key in SHOP_ITEMS:
                lines.append(
                    f"{SHOP_ITEMS[key]['name']} × <b>{qty}</b>"
                )
        text = "\n".join(lines)

    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton("🛒 Do'kon", callback_data="shop"))
    k.add(types.InlineKeyboardButton("🔙 Profil", callback_data="profile_back"))

    await call.message.edit_text(
        text,
        reply_markup=k,
        parse_mode="HTML",
    )
    await call.answer()


# ============================================================
# 📊 UMUMIY STATISTIKA
# ============================================================
@dp.message_handler(commands=["stats"])
async def stats_cmd(message: types.Message):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM game_history")
    games_n = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(balance),0) FROM users")
    balance = cur.fetchone()[0]
    conn.close()

    await message.reply(
        "📊 <b>VMP MAFIA STATISTIKASI</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{users}</b>\n"
        f"🎮 O'tkazilgan o'yinlar: <b>{games_n}</b>\n"
        f"💰 Tizimdagi balans: <b>{money(balance)}</b> so'm",
        parse_mode="HTML",
    )


# ============================================================
# 🎮 O'YIN YARATISH
# ============================================================
@dp.message_handler(commands=["game"])
async def game_cmd(message: types.Message):
    register_user(message.from_user)

    if message.chat.type not in ("group", "supergroup"):
        await message.reply("❌ /game faqat guruhda ishlaydi.")
        return

    if message.chat.id in games:
        await message.reply("⚠️ Bu guruhda allaqachon faol o'yin bor.")
        return

    game = Game(message.chat.id, message.chat.title or "VMP Mafia")
    game.add_player(message.from_user)

    global game_counter
    game_counter += 1
    games[message.chat.id] = game

    text = (
        "🎭 <b>VMP MAFIA — YANGI O'YIN</b>\n\n"
        f"👥 O'yinchilar: <b>1/{MAX_PLAYERS}</b>\n"
        f"⏱ Qabul vaqti: <b>{JOIN_SECONDS} soniya</b>\n\n"
        f"Minimal o'yinchi: <b>{MIN_PLAYERS}</b>\n"
        "👇 O'yinga qo'shiling:"
    )

    sent = await message.reply(
        text,
        reply_markup=lobby_keyboard(),
        parse_mode="HTML",
    )
    game.message_id = sent.message_id

    game.timer_task = asyncio.create_task(
        lobby_timer(game.chat_id)
    )


async def lobby_timer(chat_id):
    await asyncio.sleep(JOIN_SECONDS)
    game = games.get(chat_id)
    if not game or game.started:
        return

    if len(game.players) < MIN_PLAYERS:
        await bot.send_message(
            chat_id,
            f"❌ O'yin bekor qilindi. Kamida {MIN_PLAYERS} o'yinchi kerak."
        )
        games.pop(chat_id, None)
        return

    await start_game(game)


@dp.callback_query_handler(text="join_game")
async def join_game_call(call: types.CallbackQuery):
    game = games.get(call.message.chat.id)

    if not game or game.started:
        await call.answer("❌ Bu o'yin endi qabul qilmaydi.", show_alert=True)
        return

    register_user(call.from_user)

    if call.from_user.id in game.players:
        await call.answer("ℹ️ Siz allaqachon o'yindasiz.")
        return

    if len(game.players) >= MAX_PLAYERS:
        await call.answer("❌ O'yin to'ldi.", show_alert=True)
        return

    game.add_player(call.from_user)

    await call.answer("✅ O'yinga qo'shildingiz!")

    names = "\n".join(
        f"• {p.mention}" for p in game.players.values()
    )
    try:
        await call.message.edit_text(
            "🎭 <b>VMP MAFIA — YANGI O'YIN</b>\n\n"
            f"👥 O'yinchilar: <b>{len(game.players)}/{MAX_PLAYERS}</b>\n\n"
            f"{names}\n\n"
            "👇 Qo'shilish uchun tugmani bosing.",
            reply_markup=lobby_keyboard(),
            parse_mode="HTML",
        )
    except Exception:
        pass

    if len(game.players) >= MAX_PLAYERS:
        if game.timer_task:
            game.timer_task.cancel()
        await start_game(game)


# ============================================================
# 🎭 O'YINNI BOSHLASH
# ============================================================
async def start_game(game):
    if game.started:
        return

    if len(game.players) < MIN_PLAYERS:
        return

    game.started = True
    game.phase = "night"
    game.day = 1

    if not game.assign_roles():
        await bot.send_message(
            game.chat_id,
            "❌ Bu o'yinchi soni uchun rol konfiguratsiyasi yo'q."
        )
        games.pop(game.chat_id, None)
        return

    await bot.send_message(
        game.chat_id,
        "🎭 <b>O'YIN BOSHLANDI!</b>\n\n"
        "🔐 Rollaringiz shaxsiy xabarda yuborildi.\n"
        "🌙 Birinchi tun boshlandi.",
        parse_mode="HTML",
    )

    # Rollarni shaxsiy xabarda yuborish
    for player in game.players.values():
        mafia_names = [
            p.name for p in game.players.values()
            if p.role == "mafia" and p.user_id != player.user_id
        ]

        role_text = (
            f"🎭 <b>SIZNING ROLINGIZ</b>\n\n"
            f"{ROLE_NAMES[player.role]}\n\n"
        )

        if player.role == "mafia":
            role_text += (
                "🔪 Siz Mafia jamoasisiz.\n"
                "🌙 Tunda nishon tanlang.\n"
            )
            if mafia_names:
                role_text += "\n🔪 Mafia jamoadoshlaringiz:\n"
                role_text += "\n".join(f"• {n}" for n in mafia_names)

        elif player.role == "doctor":
            role_text += (
                "💉 Har tun bir o'yinchini himoya qiling.\n"
                "🎒 Inventardagi himoyalar ham ishlatilishi mumkin."
            )

        elif player.role == "detective":
            role_text += (
                "🔎 Har tun bir o'yinchini tekshiring.\n"
                "⚠️ Tekshiruv natijasi faqat sizga keladi."
            )

        else:
            role_text += (
                "👤 Siz Tinch aholisiz.\n"
                "🗳 Kunduzgi muhokama va ovoz berishda qatnashing."
            )

        try:
            await bot.send_message(
                player.user_id,
                role_text,
                parse_mode="HTML",
            )
        except Exception:
            pass

    await night_phase(game)


# ============================================================
# 🌙 TUN
# ============================================================
async def night_phase(game):
    if game.chat_id not in games:
        return

    game.phase = "night"
    game.mafia_target = None
    game.doctor_target = None
    game.detective_target = None
    game.poison_target = None
    game.votes.clear()

    await bot.send_message(
        game.chat_id,
        f"🌙 <b>{game.day}-TUN</b>\n\n"
        "🌃 Shahar uxlamoqda...\n"
        "🔐 Maxsus rollar o'z harakatlarini shaxsiy xabarda bajaradi.",
        parse_mode="HTML",
    )

    # Har bir maxsus rolga target tanlash tugmasini yuborish
    for player in game.alive_players():
        if player.role == "mafia":
            try:
                await bot.send_message(
                    player.user_id,
                    "🔪 <b>Mafia</b>\nNishonni tanlang:",
                    reply_markup=target_keyboard(game, player.user_id, "night_mafia"),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        elif player.role == "doctor":
            try:
                await bot.send_message(
                    player.user_id,
                    "💉 <b>Doktor</b>\nKimni davolaysiz?",
                    reply_markup=target_keyboard(game, player.user_id, "night_doctor"),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        elif player.role == "detective":
            try:
                await bot.send_message(
                    player.user_id,
                    "🔎 <b>Komissar</b>\nKimni tekshirasiz?",
                    reply_markup=target_keyboard(game, player.user_id, "night_detective"),
                    parse_mode="HTML",
                )
            except Exception:
                pass

    await asyncio.sleep(NIGHT_SECONDS)
    await resolve_night(game)


@dp.callback_query_handler(lambda c: c.data.startswith("night_mafia:"))
async def night_mafia(call: types.CallbackQuery):
    game = games.get(call.message.chat.id)
    if not game:
        # Shaxsiy xabarda chat_id user id bo'ladi; barcha o'yinlardan qidiramiz.
        game = next(
            (g for g in games.values() if call.from_user.id in g.players),
            None
        )

    if not game or game.phase != "night":
        await call.answer("❌ Hozir tun emas.", show_alert=True)
        return

    player = game.find(call.from_user.id)
    target_id = int(call.data.split(":")[1])
    target = game.find(target_id)

    if not player or player.role != "mafia" or not player.alive:
        await call.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    if not target or not target.alive:
        await call.answer("❌ Bu o'yinchi faol emas.", show_alert=True)
        return

    game.mafia_target = target_id
    await call.answer(f"🎯 Nishon: {target.name}")


@dp.callback_query_handler(lambda c: c.data.startswith("night_doctor:"))
async def night_doctor(call: types.CallbackQuery):
    game = next(
        (g for g in games.values() if call.from_user.id in g.players),
        None
    )
    if not game or game.phase != "night":
        await call.answer("❌ Hozir tun emas.", show_alert=True)
        return

    player = game.find(call.from_user.id)
    target_id = int(call.data.split(":")[1])
    target = game.find(target_id)

    if not player or player.role != "doctor" or not player.alive:
        await call.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    if not target or not target.alive:
        await call.answer("❌ Noto'g'ri nishon.", show_alert=True)
        return

    game.doctor_target = target_id
    await call.answer(f"💉 Davolandi: {target.name}")


@dp.callback_query_handler(lambda c: c.data.startswith("night_detective:"))
async def night_detective(call: types.CallbackQuery):
    game = next(
        (g for g in games.values() if call.from_user.id in g.players),
        None
    )
    if not game or game.phase != "night":
        await call.answer("❌ Hozir tun emas.", show_alert=True)
        return

    player = game.find(call.from_user.id)
    target_id = int(call.data.split(":")[1])
    target = game.find(target_id)

    if not player or player.role != "detective" or not player.alive:
        await call.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    if not target or not target.alive:
        await call.answer("❌ Noto'g'ri nishon.", show_alert=True)
        return

    game.detective_target = target_id

    hidden = item_count(target_id, "investigation_protection") > 0
    if hidden:
        result = "🟢 Tinch aholi"
    else:
        result = "🔴 Mafia" if target.role == "mafia" else "🟢 Tinch aholi"

    try:
        await bot.send_message(
            player.user_id,
            f"🔎 <b>Tekshiruv natijasi</b>\n\n"
            f"👤 {target.name}\n"
            f"📌 {result}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    if hidden:
        use_item(target_id, "investigation_protection")

    await call.answer("🔎 Tekshiruv bajarildi.")


async def resolve_night(game):
    if game.chat_id not in games:
        return

    killed = None
    target = game.find(game.mafia_target) if game.mafia_target else None

    if target and target.alive:
        # Himoya buyumlari navbat bilan tekshiriladi.
        if game.doctor_target == target.user_id:
            target = None
        elif use_item(target.user_id, "strong_protection"):
            target = None
        elif use_item(target.user_id, "death_protection"):
            target = None
        elif use_item(target.user_id, "basic_protection"):
            target = None
        elif use_item(target.user_id, "bullet_protection"):
            target = None
        elif use_item(target.user_id, "revive"):
            # Jonlantirish bu yerda o'limning oldini oladi; keyingi o'yin
            # versiyasida haqiqiy "o'lganidan keyin qaytish"ga ham kengaytirish mumkin.
            target = None
        else:
            killed = target

    if killed:
        killed.alive = False

    winner = game.winner()
    if winner:
        await finish_game(game, winner)
        return

    if killed:
        msg = (
            f"🌅 <b>TONG OTI</b>\n\n"
            f"💀 Bugun tunda <b>{killed.name}</b> halok bo'ldi.\n"
            f"🎭 Roli: <b>{ROLE_NAMES[killed.role]}</b>"
        )
    else:
        msg = (
            "🌅 <b>TONG OTI</b>\n\n"
            "😮 Bu tun hech kim halok bo'lmadi!"
        )

    await bot.send_message(game.chat_id, msg, parse_mode="HTML")
    await day_phase(game)


# ============================================================
# ☀️ KUN / OVOZ BERISH
# ============================================================
async def day_phase(game):
    game.phase = "day"
    game.votes.clear()

    alive = game.alive_players()
    text = (
        f"☀️ <b>{game.day}-KUN</b>\n\n"
        "🗣 Muhokama vaqti.\n\n"
        f"👥 Tiriklar ({len(alive)}):\n"
        f"{game.alive_text()}\n\n"
        f"🗳 Ovoz berish {DAY_SECONDS} soniyadan keyin yopiladi."
    )

    await bot.send_message(game.chat_id, text, parse_mode="HTML")

    # Ovoz berish tugmasi guruhda, lekin har kim o'z tugmasidan faqat bir marta ovoz beradi.
    k = types.InlineKeyboardMarkup(row_width=2)
    for p in alive:
        k.insert(types.InlineKeyboardButton(
            p.name[:28],
            callback_data=f"vote:{p.user_id}",
        ))
    k.add(types.InlineKeyboardButton(
        "⏭ Ovoz bermaslik",
        callback_data="vote:skip",
    ))

    await bot.send_message(
        game.chat_id,
        "🗳 <b>Kimni chiqaramiz?</b>",
        reply_markup=k,
        parse_mode="HTML",
    )

    await asyncio.sleep(DAY_SECONDS)
    await resolve_votes(game)


@dp.callback_query_handler(lambda c: c.data.startswith("vote:"))
async def vote_call(call: types.CallbackQuery):
    game = games.get(call.message.chat.id)
    if not game or game.phase != "day":
        await call.answer("❌ Hozir ovoz berish vaqti emas.", show_alert=True)
        return

    voter = game.find(call.from_user.id)
    if not voter or not voter.alive:
        await call.answer("❌ Siz bu o'yinda ovoz bera olmaysiz.", show_alert=True)
        return

    if voter.user_id in game.votes:
        await call.answer("⚠️ Siz allaqachon ovoz bergansiz.", show_alert=True)
        return

    value = call.data.split(":", 1)[1]
    if value == "skip":
        game.votes[voter.user_id] = None
        await call.answer("⏭ Ovoz berish o'tkazib yuborildi.")
        return

    target_id = int(value)
    target = game.find(target_id)
    if not target or not target.alive or target.user_id == voter.user_id:
        await call.answer("❌ Bu o'yinchiga ovoz berib bo'lmaydi.", show_alert=True)
        return

    game.votes[voter.user_id] = target_id
    await call.answer(f"🗳 Ovoz qabul qilindi: {target.name}")


async def resolve_votes(game):
    if game.chat_id not in games:
        return

    counts = Counter(
        target_id
        for target_id in game.votes.values()
        if target_id is not None
    )

    if not counts:
        await bot.send_message(
            game.chat_id,
            "🗳 Bugun hech kim chiqarilmadi."
        )
        game.day += 1
        await night_phase(game)
        return

    highest = max(counts.values())
    winners = [uid for uid, count in counts.items() if count == highest]

    if len(winners) != 1:
        names = ", ".join(game.find(uid).name for uid in winners)
        await bot.send_message(
            game.chat_id,
            f"⚖️ Ovozlar teng bo'ldi: <b>{names}</b>\n"
            "Hech kim chiqarilmadi.",
            parse_mode="HTML",
        )
    else:
        victim = game.find(winners[0])
        victim.alive = False

        await bot.send_message(
            game.chat_id,
            f"🚪 <b>{victim.name}</b> o'yindan chiqarildi.\n\n"
            f"🎭 Roli: <b>{ROLE_NAMES[victim.role]}</b>",
            parse_mode="HTML",
        )

    winner = game.winner()
    if winner:
        await finish_game(game, winner)
        return

    game.day += 1
    await night_phase(game)


# ============================================================
# 🏁 G'ALABA
# ============================================================
async def finish_game(game, winner):
    if game.chat_id not in games:
        return

    game.phase = "finished"

    if winner == "mafia":
        title = "🔪 MAFIA G'ALABA QOZONDI!"
    else:
        title = "🏆 TINCH AHOLI G'ALABA QOZONDI!"

    lines = [title, "", "🎭 <b>Rollar:</b>"]

    for p in game.players.values():
        status = "💚" if p.alive else "💀"
        lines.append(
            f"{status} {p.name} — {ROLE_NAMES[p.role]}"
        )

    await bot.send_message(
        game.chat_id,
        "\n".join(lines),
        parse_mode="HTML",
    )

    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO game_history(chat_id,winner,players) VALUES(?,?,?)",
        (game.chat_id, winner, len(game.players)),
    )
    conn.commit()
    conn.close()

    for p in game.players.values():
        update_result(p.user_id, p.role == winner)

    games.pop(game.chat_id, None)


@dp.callback_query_handler(text="close_action")
async def close_action(call: types.CallbackQuery):
    await call.message.delete()
    await call.answer()


# ============================================================
# 👑 ADMIN
# ============================================================
class AdminState(StatesGroup):
    user_id = State()
    amount = State()
    diamond_user_id = State()
    diamond_amount = State()
    new_admin_id = State()


def admin_keyboard():
    k = types.InlineKeyboardMarkup(row_width=2)
    k.row(
        types.InlineKeyboardButton("💰 Pul berish", callback_data="admin_money"),
        types.InlineKeyboardButton("💎 Olmos berish", callback_data="admin_diamond"),
    )
    k.row(
        types.InlineKeyboardButton("📊 Statistika", callback_data="admin_stats"),
        types.InlineKeyboardButton("👑 Admin qo'shish", callback_data="admin_add"),
    )
    k.add(types.InlineKeyboardButton("❌ Yopish", callback_data="admin_close"))
    return k


@dp.message_handler(commands=["admin"])
async def admin_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("❌ Bu bo'lim faqat adminlar uchun.")
        return

    await message.reply(
        "⚙️ <b>VMP MAFIA ADMIN PANEL</b>\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query_handler(text="admin_money")
async def admin_money(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await call.message.answer(
        "🆔 Pul beriladigan foydalanuvchi ID raqamini yuboring.\n"
        "/cancel — bekor qilish"
    )
    await AdminState.user_id.set()
    await call.answer()


@dp.message_handler(commands=["cancel"], state="*")
async def cancel_admin(message: types.Message, state: FSMContext):
    await state.finish()
    await message.reply("✅ Bekor qilindi.")


@dp.message_handler(state=AdminState.user_id)
async def admin_money_user(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.finish()
        return

    if not (message.text or "").isdigit():
        await message.reply("❌ Faqat ID raqamini kiriting.")
        return

    uid = int(message.text)
    if not get_profile(uid):
        await message.reply("❌ Foydalanuvchi topilmadi.")
        return

    async with state.proxy() as data:
        data["uid"] = uid

    await message.reply("💰 Qancha so'm beramiz? Masalan: 10000")
    await AdminState.amount.set()


@dp.message_handler(state=AdminState.amount)
async def admin_money_amount(message: types.Message, state: FSMContext):
    if not (message.text or "").isdigit() or int(message.text) <= 0:
        await message.reply("❌ Musbat raqam kiriting.")
        return

    async with state.proxy() as data:
        uid = data["uid"]

    amount = int(message.text)
    add_money(uid, amount)
    await message.reply(
        f"✅ {uid} hisobiga {money(amount)} so'm qo'shildi.\n"
        f"💰 Yangi balans: {money(get_balance(uid))} so'm"
    )
    await state.finish()


@dp.callback_query_handler(text="admin_diamond")
async def admin_diamond(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await call.message.answer(
        "🆔 Olmos beriladigan foydalanuvchi ID raqamini yuboring."
    )
    await AdminState.diamond_user_id.set()
    await call.answer()


@dp.message_handler(state=AdminState.diamond_user_id)
async def admin_diamond_user(message: types.Message, state: FSMContext):
    if not (message.text or "").isdigit():
        await message.reply("❌ Faqat ID raqamini kiriting.")
        return

    uid = int(message.text)
    if not get_profile(uid):
        await message.reply("❌ Foydalanuvchi topilmadi.")
        return

    async with state.proxy() as data:
        data["uid"] = uid

    await message.reply("💎 Qancha olmos beramiz?")
    await AdminState.diamond_amount.set()


@dp.message_handler(state=AdminState.diamond_amount)
async def admin_diamond_amount(message: types.Message, state: FSMContext):
    if not (message.text or "").isdigit() or int(message.text) <= 0:
        await message.reply("❌ Musbat raqam kiriting.")
        return

    async with state.proxy() as data:
        uid = data["uid"]

    amount = int(message.text)
    add_diamonds(uid, amount)
    await message.reply(
        f"✅ {uid} hisobiga 💎 {amount} ta olmos qo'shildi."
    )
    await state.finish()


@dp.callback_query_handler(text="admin_stats")
async def admin_stats(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM game_history")
    games_n = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM admins")
    admins = cur.fetchone()[0]
    conn.close()

    await call.message.answer(
        "📊 <b>ADMIN STATISTIKA</b>\n\n"
        f"👥 Foydalanuvchilar: {users}\n"
        f"🎮 O'yinlar: {games_n}\n"
        f"👑 Adminlar: {admins}",
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query_handler(text="admin_add")
async def admin_add(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return

    await call.message.answer("👑 Yangi admin Telegram ID raqamini yuboring.")
    await AdminState.new_admin_id.set()
    await call.answer()


@dp.message_handler(state=AdminState.new_admin_id)
async def admin_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.finish()
        return

    if not (message.text or "").isdigit():
        await message.reply("❌ Faqat raqam kiriting.")
        return

    uid = int(message.text)
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO admins(user_id) VALUES(?)",
        (uid,),
    )
    conn.commit()
    conn.close()

    await message.reply(f"✅ {uid} adminlar ro'yxatiga qo'shildi.")
    await state.finish()


@dp.callback_query_handler(text="admin_close")
async def admin_close(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await call.message.delete()
    await call.answer()


# ============================================================
# 🛑 XAVFSIZ START
# ============================================================
async def on_startup(_):
    init_db()
    logging.info("VMP Mafia bot ishga tushdi.")


if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise ValueError(
            "TOKEN kiritilmagan. TOKEN = '...' qatoriga "
            "BotFather tokenini yozing."
        )

    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
    )
