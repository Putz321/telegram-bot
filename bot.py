import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    PicklePersistence,
    PersistenceInput,  # Import PersistenceInput untuk mengunci bot_data
)
from telegram.error import TelegramError, Forbidden

# --- CONFIGURATION ---
TOKEN = "8871982955:AAEWteO9fFCn-MzbrQXVaJc-bjdYwAT1Aww"
TOKEN_BOT_V2 = "8715967513:AAHaik2g01x1guyIxsHwUVLfMrN4TlFxgd4"
ADMIN_ID = 8874242457

bot_v2 = Bot(token=TOKEN_BOT_V2)

CHANNEL_USERNAME = "@storgmailynd4" 
GROUP_USERNAME = "@storgmailkuid" 

# --- MEMATIKAN LOG INTERNAL TELEGRAM/PYTHON (AGAR TERMINAL BERSIH) ---
logging.basicConfig(level=logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("telegram").setLevel(logging.CRITICAL)

# State Percakapan
STOR_GMAIL, CHECK_SANDI, CEK_PAYMENT_LAMA, DATA_PAYMENT, WD_NO_DANA, WD_ATAS_NAMA, WD_JUMLAH = range(7)

# --- TOMBOL (INLINE KEYBOARD & REPLY KEYBOARD) ---
def get_main_inline_menu():
    """Menu Utama dalam bentuk Inline Keyboard (Menempel di bawah Teks/GIF)"""
    keyboard = [
        [InlineKeyboardButton("💌 Setor Gmail", callback_data="menu_stor"), InlineKeyboardButton("👥 Referral", callback_data="menu_referral")],
        [InlineKeyboardButton("🏆 Top Leaderboard", callback_data="menu_leaderboard")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_referral_menu():
    keyboard = [
        [KeyboardButton("💸 Withdrawal"), KeyboardButton("🏠 Kembali Kehalaman Utama")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_cancel_menu():
    keyboard = [[KeyboardButton("❌ Batal")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_yes_no_menu():
    keyboard = [[KeyboardButton("Iya"), KeyboardButton("Tidak")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_password_choice_menu():
    keyboard = [
        [KeyboardButton("sgsg1122"), KeyboardButton("fineirga")],
        [KeyboardButton("prabujaya")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_verification_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 Join Saluran", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}")],
        [InlineKeyboardButton("💬 Join Grup Wajib", url=f"https://t.me/{GROUP_USERNAME.replace('@','')}")],
        [InlineKeyboardButton("✅ Verifikasi", callback_data="check_membership")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- UTILITY & HELPER ---
async def is_user_joined(bot, user_id: int) -> bool:
    try:
        channel_member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if channel_member.status in ['left', 'kicked']:
            return False
            
        group_member = await bot.get_chat_member(chat_id=GROUP_USERNAME, user_id=user_id)
        if group_member.status in ['left', 'kicked']:
            return False
            
        return True
    except TelegramError:
        return False

def is_blacklisted(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    blacklist = context.bot_data.get('blacklist', {})
    return user_id in blacklist

def save_username_mapping(user, context: ContextTypes.DEFAULT_TYPE):
    if 'username_to_id' not in context.bot_data:
        context.bot_data['username_to_id'] = {}
    if user.username:
        clean_username = user.username.replace("@", "").lower()
        context.bot_data['username_to_id'][clean_username] = user.id

def check_and_reset_monthly_leaderboard(context: ContextTypes.DEFAULT_TYPE):
    """Mengecek apakah sudah ganti bulan. Data HANYA direset jika bulan kalender berubah."""
    current_month_key = datetime.now().strftime("%Y-%m")
    last_reset_month = context.bot_data.get('last_leaderboard_month')

    # Inisialisasi awal jika bot baru pertama kali run
    if 'leaderboard_income' not in context.bot_data:
        context.bot_data['leaderboard_income'] = {}

    if last_reset_month is None:
        context.bot_data['last_leaderboard_month'] = current_month_key
    elif last_reset_month != current_month_key:
        # Hanya reset jika berganti bulan (misal dari 2026-07 ke 2026-08)
        context.bot_data['leaderboard_income'] = {}
        context.bot_data['last_leaderboard_month'] = current_month_key

# --- USER FLOW ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return

    user = update.effective_user
    save_username_mapping(user, context)

    if is_blacklisted(user.id, context):
        await update.message.reply_text("⛔ Akun Anda telah diblokir/blacklist dari penggunaan bot ini.")
        return

    if 'all_users' not in context.bot_data:
        context.bot_data['all_users'] = set()
    context.bot_data['all_users'].add(user.id)
    
    if 'referral_parents' not in context.bot_data:
        context.bot_data['referral_parents'] = {}
    if 'referral_count' not in context.bot_data:
        context.bot_data['referral_count'] = {}
    if 'referral_balance' not in context.bot_data:
        context.bot_data['referral_balance'] = {}

    if context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.replace("ref_", ""))
                if referrer_id != user.id and user.id not in context.bot_data['referral_parents']:
                    context.bot_data['referral_parents'][user.id] = referrer_id
                    context.bot_data['referral_count'][referrer_id] = context.bot_data['referral_count'].get(referrer_id, 0) + 1
            except ValueError:
                pass

    joined = await is_user_joined(context.bot, user.id)
    if not joined:
        text_verify = (
            f"Hallo {user.mention_html()} 👋🏼\n\n"
            f"Sebelum menggunakan bot ini, Anda wajib bergabung ke Saluran dan Grup resmi kami terlebih dahulu.Untuk Mendapatkan Informasi Rules Dan Lain-Lain\n\n"
            f"Silakan klik tombol di bawah untuk bergabung, kemudian klik Verifikasi!"
        )
        await update.message.reply_text(text_verify, parse_mode="HTML", reply_markup=get_verification_keyboard())
        return
        
    await send_welcome_message(update.effective_chat.id, user, context)

async def send_welcome_message(chat_id, user, context):
    try:
        chat = await context.bot.get_chat(chat_id)
        if chat.type in ["group", "supergroup"]:
            return
    except Exception:
        pass

    text_welcome = (
        f"<b>💮 Gmailストアへようこそ</b>\n\n"
        f"こんにちは {user.mention_html()} 👋🏼\n\n"
        f"こんにちは。私は—͟͟͞͞𝐍𝖆𝖙𝖎𝖔𝖓𝖆𝖑𝖞𝖙𝖎 𝐒𝖊𝖓𝖕𝖆𝖎⃟𒁍私はあなたのGmailアカウントを売却するお手伝いをいたします.\n\n"
        f"<blockquote>"
        "📢 <b>PENGUMUMAN ADMIN</b>\n"
        "➢ Wajib bergabung ke Saluran Admin untuk mendapatkan informasi terbaru laporan harian.\n"
        "➢ Link Saluran: https://t.me/storgmailynd4"
        "</blockquote>\n"
        "<b>👇🏼 Silakan Klik Tombol Di Bawah Untuk Memulai Proses Setoran!</b>"
    )
    
    try:
        with open("welcome.gif", "rb") as animation:
            await context.bot.send_animation(
                chat_id=chat_id,
                animation=animation,
                caption=text_welcome,
                parse_mode="HTML",
                reply_markup=get_main_inline_menu()
            )
    except FileNotFoundError:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text_welcome, 
            parse_mode="HTML", 
            reply_markup=get_main_inline_menu()
        )

async def verification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        await query.answer()
        return

    await query.answer()
    user = query.from_user
    save_username_mapping(user, context)

    if is_blacklisted(user.id, context):
        await query.message.reply_text("⛔ Akun Anda dalam daftar blacklist.")
        return

    joined = await is_user_joined(context.bot, user.id)
    
    if joined:
        try:
            await query.message.delete()
        except Exception:
            pass
        await send_welcome_message(query.message.chat_id, user, context)
    else:
        text_fail = "❌ Verifikasi Gagal! Anda belum bergabung ke Saluran atau Grup kami. Silakan join lalu cek gabung kembali."
        await query.message.reply_text(text_fail, parse_mode="Markdown", reply_markup=get_verification_keyboard())

# --- HANDLER TOMBOL INLINE MENU UTAMA ---

async def main_menu_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if is_blacklisted(user.id, context):
        await query.message.reply_text("⛔ Akun Anda dalam daftar blacklist.")
        return

    data = query.data

    if data == "menu_stor":
        await query.message.reply_text("Ketik /stor atau klik tombol di bawah untuk memulai setoran.", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/stor📍")]], resize_keyboard=True))
        await stor_command(update, context)

    elif data == "menu_referral":
        await referral_command(update, context)

    elif data == "menu_leaderboard":
        await leaderboard_command(update, context)

# --- MENU: LEADERBOARD PENGHASILAN ---

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return

    user = update.effective_user
    save_username_mapping(user, context)

    if is_blacklisted(user.id, context):
        await update.message.reply_text("⛔ Akun Anda dalam daftar blacklist.")
        return

    check_and_reset_monthly_leaderboard(context)
    leaderboard_data = context.bot_data.get('leaderboard_income', {})

    if not leaderboard_data:
        text_empty = "🏆 **Top Leaderboard**\n\nBelum Ada Data Leaderboard"
        if update.callback_query:
            await update.callback_query.message.reply_text(text_empty, parse_mode="Markdown")
        else:
            await update.message.reply_text(text_empty, parse_mode="Markdown")
        return

    sorted_leaderboard = sorted(leaderboard_data.items(), key=lambda item: item[1], reverse=True)
    month_name = datetime.now().strftime("%B %Y")
    lines = [f"🏆 **Top Leaderboard ({month_name.upper()})**\n"]
    
    rank = 1
    for u_id, total_income in sorted_leaderboard[:10]:
        try:
            user_chat = await context.bot.get_chat(u_id)
            name = f"@{user_chat.username}" if user_chat.username else user_chat.first_name
        except Exception:
            name = f"User ID `{u_id}`"
        
        if rank == 1:
            medal = "🥇"
        elif rank == 2:
            medal = "🥈"
        elif rank == 3:
            medal = "🥉"
        else:
            medal = f"{rank}."

        lines.append(f"{medal} {name} — **Rp {total_income:,}**".replace(",", "."))
        rank += 1

    user_total = leaderboard_data.get(user.id, 0)
    lines.append(f"\n📊 Total: **Rp {user_total:,}**".replace(",", "."))

    final_text = "\n".join(lines)
    if update.callback_query:
        await update.callback_query.message.reply_text(final_text, parse_mode="Markdown")
    else:
        await update.message.reply_text(final_text, parse_mode="Markdown")

# --- FITUR REFERRAL ---

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return

    user = update.effective_user
    save_username_mapping(user, context)

    if is_blacklisted(user.id, context):
        await update.message.reply_text("⛔ Akun Anda dalam daftar blacklist.")
        return

    bot_username = (await context.bot.get_me()).username

    balance = context.bot_data.get('referral_balance', {}).get(user.id, 0)
    count = context.bot_data.get('referral_count', {}).get(user.id, 0)
    user_valid_count = context.bot_data.get('referral_valid_count', {}).get(user.id, 0)
    ref_link = f"https://t.me/{bot_username}?start=ref_{user.id}"

    text_ref = (
        f"Hallo {user.first_name} Bagikan Kode Referral Anda Kepada Orang, Dan Anda Bisa Menghasilkan Uang!!\n\n"
        f"Saldo Referral: Rp {balance:,}\n"
        f"User Valid: {user_valid_count}\n"
        f"User Invite: {count}\n"
        f"Link Referral Anda: {ref_link}\n\n"
        f"Trimakasih Sudah Berkomposisi Untuk Membagikan Referral Kami."
    ).replace(",", ".")

    if update.callback_query:
        await update.callback_query.message.reply_text(text_ref, reply_markup=get_referral_menu())
    else:
        await update.message.reply_text(text_ref, reply_markup=get_referral_menu())

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return ConversationHandler.END

    await send_welcome_message(update.effective_chat.id, update.effective_user, context)
    return ConversationHandler.END

# --- WITHDRAWAL REFERRAL ---

async def start_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return ConversationHandler.END

    user = update.effective_user
    save_username_mapping(user, context)

    if is_blacklisted(user.id, context):
        await update.message.reply_text("⛔ Akun Anda dalam daftar blacklist.")
        return ConversationHandler.END

    balance = context.bot_data.get('referral_balance', {}).get(user.id, 0)

    if balance < 2000:
        await update.message.reply_text(
            f"⚠️ Maaf, Minimal Withdrawal Yaitu Rp 2.000\nSaldo Referral Anda Saat Ini: Rp {balance:,}".replace(",", "."),
            reply_markup=get_referral_menu()
        )
        return ConversationHandler.END

    await update.message.reply_text("Silakan masukkan Nomor Dana Anda untuk penarikan:", reply_markup=get_cancel_menu())
    return WD_NO_DANA

async def process_wd_no_dana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Batal":
        return await cancel_wd(update, context)

    context.user_data['wd_no_dana'] = update.message.text.strip()
    await update.message.reply_text("Silakan masukkan Atas Nama pemilik akun Dana Anda:", reply_markup=get_cancel_menu())
    return WD_ATAS_NAMA

async def process_wd_atas_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Batal":
        return await cancel_wd(update, context)

    context.user_data['wd_atas_nama'] = update.message.text.strip()
    user = update.effective_user
    balance = context.bot_data.get('referral_balance', {}).get(user.id, 0)

    await update.message.reply_text(
        f"Masukkan Jumlah Penarikan (Minimal Rp 2.000, Saldo Anda: Rp {balance:,}):".replace(",", "."),
        reply_markup=get_cancel_menu()
    )
    return WD_JUMLAH

async def process_wd_jumlah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Batal":
        return await cancel_wd(update, context)

    text_jumlah = update.message.text.strip().replace("Rp", "").replace(".", "").replace(",", "").strip()
    if not text_jumlah.isdigit():
        await update.message.reply_text("⚠️ Jumlah penarikan harus berupa angka! Silakan masukkan kembali. Contoh: `2000`", reply_markup=get_cancel_menu())
        return WD_JUMLAH

    jumlah = int(text_jumlah)
    user = update.effective_user
    balance = context.bot_data.get('referral_balance', {}).get(user.id, 0)

    if jumlah < 2000:
        await update.message.reply_text("⚠️ Minimal Withdrawal Yaitu Rp 2.000! Silakan masukkan jumlah yang sesuai:", reply_markup=get_cancel_menu())
        return WD_JUMLAH

    if jumlah > balance:
        await update.message.reply_text(f"⚠️ Saldo Anda tidak mencukupi (Saldo: Rp {balance:,}). Silakan masukkan jumlah yang sesuai:".replace(",", "."), reply_markup=get_cancel_menu())
        return WD_JUMLAH

    context.bot_data['referral_balance'][user.id] -= jumlah
    no_dana = context.user_data.get('wd_no_dana')
    atas_nama = context.user_data.get('wd_atas_nama')
    tgl_laporan_str = datetime.now().strftime("%d, %B %Y")

    await update.message.reply_text(
        f"✅ **PENGAJUAN WITHDRAWAL BERHASIL**\n\n"
        f"Penarikan sebesar Rp {jumlah:,} sedang diproses oleh Admin.".replace(",", "."),
        parse_mode="Markdown",
        reply_markup=get_referral_menu()
    )

    text_admin_wd = (
        f"💸 **PERMINTAAN WITHDRAWAL REFERRAL**\n\n"
        f"👤 User: {user.mention_html()} (ID: <code>{user.id}</code>)\n"
        f"📱 Nomor Dana: <code>{no_dana}</code>\n"
        f"👤 Atas Nama: {atas_nama}\n"
        f"💵 Jumlah WD: Rp {jumlah:,}\n"
        f"📅 Tanggal: {tgl_laporan_str}"
    ).replace(",", ".")

    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text_admin_wd, parse_mode="HTML")
    except Exception:
        pass

    try:
        await bot_v2.send_message(chat_id=ADMIN_ID, text=text_admin_wd, parse_mode="HTML")
    except Exception:
        pass

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_wd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Penarikan dibatalkan.", reply_markup=get_referral_menu())
    context.user_data.clear()
    return ConversationHandler.END

# --- SETOR GMAIL ---

async def stor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return ConversationHandler.END

    user = update.effective_user
    save_username_mapping(user, context)

    if is_blacklisted(user.id, context):
        msg = "⛔ Akun Anda dalam daftar blacklist dan tidak dapat melakukan setoran."
        if update.callback_query:
            await update.callback_query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    is_open = context.bot_data.get('is_open', True)
    if not is_open:
        close_message = context.bot_data.get('close_message', "⚠️ Maaf, bot setoran sedang tutup.")
        if update.callback_query:
            await update.callback_query.message.reply_text(close_message, parse_mode="HTML")
        else:
            await update.message.reply_text(close_message, parse_mode="HTML")
        return ConversationHandler.END

    if not await is_user_joined(context.bot, user.id):
        msg = "⚠️ Anda harus memverifikasi keanggotaan terlebih dahulu! Klik /start untuk memverifikasi."
        if update.callback_query:
            await update.callback_query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    text_stor = (
        "<b>⚠️❗❗ PERINGATAN ❗❗⚠️</b>\n\n"
        "Silakan Kirimkan List Gmail Anda Langsung Di Bawah Pesan Ini Sesuai Dengan Format Contoh.\n\n"
        "<blockquote>"
        "⚠️ <b>RULES GMAIL</b>\n"
        "➢ Gmail Fresh / Baru Dibuat\n"
        "➢ Tahun Lahir 1990 [ Wajib ]\n"
        "➢ Nama Harus Nama Orang Indonesia [ Wajib ]\n"
        "➢ Password Wajib `sgsg1122` | `fineirga` | `prabujaya`"
        "</blockquote>\n"
        "<blockquote>"
        "📌 <b>WAJIB DIIKUTI</b>\n"
        "➢ Nama Gmail [ Harus Beda ] Wajib\n"
        "➢ Maksimal 2 Angka Dalam Alamat Gmail\n"
        "➢ Wajib Cek Gmail Di Gmail Checker Sebelum Di Stor\n"
        "➢ Open Di Jam ± 07:00 WIB"
        "</blockquote>\n"
        "<blockquote>"
        "🚫 <b>LARANGAN</b>\n"
        "➢ Dilarang Titik Dan Angka Di Tengah Alamat\n"
        "➢ Gmail Tidak Boleh Terverifikasi Nomor HP\n"
        "➢ Gmail Dilarang Di Hapus Jika Belum Di Payment"
        "</blockquote>\n"
        "<blockquote>"
        "💳 <b>INFORMASI PEMBAYARAN</b>\n"
        "➢ Setor 1 - 20 Gmail: Rp 4.500 / akun\n"
        "➢ Setor 21 - Seterusnya: Rp 5.000 / akun\n"
        "➢ Minimal 1 Gmail, Tanpa Batas Transaksi"
        "</blockquote>\n"
        "<b>📝 Contoh Format Pengisian:</b>\n"
        "<code>nama1@gmail.com\n"
        "nama2@gmail.com</code>\n\n"
        "⚠️ <i>Peringatan: Wajib isi list akun seperti di contoh!</i>"
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(text_stor, parse_mode="HTML", reply_markup=get_cancel_menu())
    else:
        await update.message.reply_text(text_stor, parse_mode="HTML", reply_markup=get_cancel_menu())
    return STOR_GMAIL

async def process_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return ConversationHandler.END

    text_received = update.message.text
    if text_received == "❌ Batal":
        return await cancel(update, context)

    context.user_data['gmail_list'] = text_received

    text_sandi = (
        "<b>⚠️ KONFIRMASI RULES PASSWORD</b>\n\n"
        "Data Anda Sudah Di Database, Konfirmasi Password Anda. Silakan pilih salah satu password di bawah ini.\n\n"
        "<b>🔑 PASTIKAN AKUN ANDA SUDAH SESUAI RULES!!!</b>\n"
        "Admin Hanya Menerima Gmail Fresh Dan Sesuai Rules Di Atas, Selain Itu Admin Tolak.!!!"
    )
    await update.message.reply_text(text_sandi, parse_mode="HTML", reply_markup=get_password_choice_menu())
    return CHECK_SANDI

async def process_check_sandi(update: Update, update_context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return ConversationHandler.END

    answer = update.message.text
    user_id = update.effective_user.id

    allowed_passwords = ["sgsg1122", "fineirga", "prabujaya"]

    if answer in allowed_passwords:
        update_context.user_data['selected_password'] = answer
        if 'user_history' in update_context.bot_data and user_id in update_context.bot_data['user_history']:
            saved_data = update_context.bot_data['user_history'].get(user_id)
            text_lama = (
                "<b>🔄 DETEKSI DATA PEMBAYARAN LAMA</b>\n\n"
                "Sistem kami menemukan riwayat informasi pembayaran yang pernah Anda gunakan sebelumnya.\n\n"
                "<blockquote>"
                "💳 <b>DATA PAYMENT ANDA</b>\n"
                f"➢ Nomor Dana: <code>{saved_data['no_dana']}</code>\n"
                f"➢ Atas Nama: <b>{saved_data['atas_nama']}</b>"
                "</blockquote>\n"
                "Apakah Anda ingin melanjutkan transaksi menggunakan data pembayaran di atas?"
            )
            await update.message.reply_text(text_lama, parse_mode="HTML", reply_markup=get_yes_no_menu())
            return CEK_PAYMENT_LAMA
        else:
            return await request_new_payment(update, update_context)
    else:
        await update.message.reply_text(
            "⚠️ Password Tidak Sesuai, Peringatan Keras!!! Admin Hanya Menerima Password Pilihan Di Tombol Dan Gmail Fresh.!! Jika Berbohong Admin Akan Meng Blacklist Akun Mu Agar Tidak Bisa Menyetorkan Gmail Secara Permanent ❗❗❗",
            parse_mode="HTML",
            reply_markup=get_password_choice_menu()
        )
        return CHECK_SANDI

async def request_new_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return ConversationHandler.END

    text_payment = (
        "<b>💳 PENGISIAN DATA PEMBAYARAN</b>\n\n"
        "Isi Data Payment Anda Dengan Benar, Dan Baca Agar Tidak Salah!!.\n\n"
        "<blockquote>"
        "💳 <b>INFORMASI PEMBAYARAN</b>\n"
        "➢ Metode pencairan saat ini hanya tersedia via <b>DANA</b>.\n"
        "➢ Pastikan nomor HP and nama pemilik akun sudah benar.\n"
        "➢ Proses pencairan memakan waktu 1-2 hari kerja."
        "</blockquote>\n"
        "<b>📝 Silakan salin, isi, dan kirim format di bawah ini:</b>\n"
        "<code>Nomor Dana: 0882xxxxxxxx\n"
        "Atas Nama: Nama Akun Dana Anda</code>"
    )
    await update.message.reply_text(text_payment, parse_mode="HTML", reply_markup=get_cancel_menu())
    return DATA_PAYMENT

async def process_cek_payment_lama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return ConversationHandler.END

    answer = update.message.text
    user_id = update.effective_user.id

    if answer == "Iya":
        saved_data = context.bot_data['user_history'].get(user_id)
        context.user_data['no_dana'] = saved_data['no_dana']
        context.user_data['atas_nama'] = saved_data['atas_nama']
        return await finalize_stor(update, context)
    elif answer == "Tidak":
        return await request_new_payment(update, context)
    else:
        await update.message.reply_text("Silakan pilih Iya atau Tidak.", reply_markup=get_yes_no_menu())
        return CEK_PAYMENT_LAMA

async def process_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return ConversationHandler.END

    payment_data = update.message.text
    if payment_data == "❌ Batal":
        return await cancel(update, context)

    no_dana = "-"
    atas_nama = "-"
    try:
        lines = payment_data.split('\n')
        for line in lines:
            if "nomor" in line.lower():
                no_dana = line.split(":")[-1].strip()
            elif "atas nama" in line.lower():
                atas_nama = line.split(":")[-1].strip()
    except Exception:
        pass

    if no_dana == "-" and atas_nama == "-":
        no_dana = payment_data
        atas_nama = "User Tidak Mengisi Format"

    context.user_data['no_dana'] = no_dana
    context.user_data['atas_nama'] = atas_nama

    user_id = update.effective_user.id
    if 'user_history' not in context.bot_data:
        context.bot_data['user_history'] = {}
    context.bot_data['user_history'][user_id] = {"no_dana": no_dana, "atas_nama": atas_nama}

    return await finalize_stor(update, context)

async def finalize_stor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return ConversationHandler.END

    user = update.effective_user
    gmail_raw = context.user_data.get('gmail_list', '')
    no_dana = context.user_data.get('no_dana', '-')
    atas_nama = context.user_data.get('atas_nama', '-')
    selected_password = context.user_data.get('selected_password', 'sgsg1122')

    gmail_lines = [g.strip() for g in gmail_raw.split('\n') if "@gmail.com" in g.lower()]
    jumlah_gmail = len(gmail_lines)

    if 1 <= jumlah_gmail <= 20:
        total_harga = jumlah_gmail * 4500
    else:
        total_harga = jumlah_gmail * 5000

    now = datetime.now()
    tgl_sekarang_str = now.strftime("%d-%m-%Y")
    tgl_laporan_str = now.strftime("%d, %B %Y")

    if 'setoran_log' not in context.bot_data:
        context.bot_data['setoran_log'] = {}
    if tgl_sekarang_str not in context.bot_data['setoran_log']:
        context.bot_data['setoran_log'][tgl_sekarang_str] = set()
    context.bot_data['setoran_log'][tgl_sekarang_str].add(user.id)

    if 'gmail_owners' not in context.bot_data:
        context.bot_data['gmail_owners'] = {}
    
    if 'gmail_passwords' not in context.bot_data:
        context.bot_data['gmail_passwords'] = {}

    for g in gmail_lines:
        context.bot_data['gmail_owners'][g.lower()] = user.id
        context.bot_data['gmail_passwords'][g.lower()] = selected_password

    if 'daily_gmails' not in context.bot_data:
        context.bot_data['daily_gmails'] = {}
    if tgl_sekarang_str not in context.bot_data['daily_gmails']:
        context.bot_data['daily_gmails'][tgl_sekarang_str] = []

    for g in gmail_lines:
        if g not in context.bot_data['daily_gmails'][tgl_sekarang_str]:
            context.bot_data['daily_gmails'][tgl_sekarang_str].append(g)

    if 'daily_user_gmails' not in context.bot_data:
        context.bot_data['daily_user_gmails'] = {}
    if tgl_sekarang_str not in context.bot_data['daily_user_gmails']:
        context.bot_data['daily_user_gmails'][tgl_sekarang_str] = {}
    if user.id not in context.bot_data['daily_user_gmails'][tgl_sekarang_str]:
        context.bot_data['daily_user_gmails'][tgl_sekarang_str][user.id] = []

    for g in gmail_lines:
        if g.lower() not in context.bot_data['daily_user_gmails'][tgl_sekarang_str][user.id]:
            context.bot_data['daily_user_gmails'][tgl_sekarang_str][user.id].append(g.lower())

    text_success = (
        "<b>✅ SETORAN GMAIL BERHASIL DITERIMA</b>\n\n"
        "Terima Kasih, Data Setoran Anda Telah Berhasil Simpan Di Sistem Database Kami!!.\n\n"
        "<blockquote>"
        "📌 <b>ESTIMASI & INFORMASI</b>\n"
        "➢ Proses pengecekan dilakukan besok sore/malam (paling cepat).\n"
        "➢ Paling lambat memakan waktu hingga 2 hari kerja.\n"
        "➢ Jika ingin menambah setoran lagi, silakan klik kembali <code>/stor📍</code>"
        "</blockquote>\n"
        "<b>🔔 Pantau terus Saluran Resmi untuk laporan sukses pembayaran:</b>\n"
        "https://t.me/storgmailynd4"
    )
    await update.message.reply_text(text_success, parse_mode="HTML", reply_markup=get_main_inline_menu())

    text_to_admin = (
        f"🧾NEW STORAN\n"
        f"📨Gmail:\n{gmail_raw}\n\n"
        f"🔑Password: {selected_password}\n"
        f"📱Nomor Dana: <code>{no_dana}</code>\n"
        f"👤Atas Nama: {atas_nama}\n"
        f"💸Jumlah Dana: {total_harga:,}\n"
        f"📅Tanggal Stor Gmail: {tgl_laporan_str}"
    ).replace(",", ".")

    try:
        await bot_v2.send_message(chat_id=ADMIN_ID, text=text_to_admin, parse_mode="HTML")
    except Exception:
        pass

    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return ConversationHandler.END

    await update.message.reply_text("Yahh... Sayang Sekali, Storan Anda Di Batalkan....", reply_markup=get_main_inline_menu())
    context.user_data.clear()
    return ConversationHandler.END


# --- FITUR ADMIN: BLACKLIST & UNBLACKLIST ---

async def bl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    raw_text = update.message.text.split(None, 1)
    if len(raw_text) < 2 or "," not in raw_text[1]:
        await update.message.reply_text("❌ Format salah!\nGunakan format: `/bl @namauser, Alasan`", parse_mode="Markdown")
        return

    args_part = raw_text[1].split(",", 1)
    target_user_str = args_part[0].strip()
    alasan = args_part[1].strip()

    clean_username = target_user_str.replace("@", "").lower()
    username_mapping = context.bot_data.get('username_to_id', {})

    target_id = None
    if clean_username.isdigit():
        target_id = int(clean_username)
    else:
        target_id = username_mapping.get(clean_username)

    if not target_id:
        await update.message.reply_text(f"❌ User `{target_user_str}` Tidak Ditemukan Di Database..", parse_mode="Markdown")
        return

    if 'blacklist' not in context.bot_data:
        context.bot_data['blacklist'] = {}

    context.bot_data['blacklist'][target_id] = alasan

    text_notif_bl = (
        f"⚠️ MOHON MAAF ANDA DI BLACKLIST ⚠️\n\n"
        f"PERINGATAN KERAS UNTUK ANDA❗❗\n"
        f"Atas Nama: @{clean_username}\n"
        f"Status: PERMANENT\n"
        f"Alasan: {alasan}\n"
        f"Terimakasih."
    )

    try:
        await context.bot.send_message(chat_id=target_id, text=text_notif_bl)
        notif_status = "✅ Notifikasi berhasil dikirimkan ke user."
    except Exception:
        notif_status = "⚠️ User telah memblokir/menghapus bot, notifikasi gagal terkirim."

    await update.message.reply_text(
        f"⛔ **BERHASIL DI BLACKLIST**\n"
        f"User: @{clean_username} (ID: `{target_id}`)\n"
        f"Alasan: {alasan}\n\n"
        f"{notif_status}",
        parse_mode="Markdown"
    )

async def unbl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("❌ Format salah!\nGunakan format: `/unbl @namauser`", parse_mode="Markdown")
        return

    target_user_str = context.args[0].strip()
    clean_username = target_user_str.replace("@", "").lower()
    username_mapping = context.bot_data.get('username_to_id', {})

    target_id = None
    if clean_username.isdigit():
        target_id = int(clean_username)
    else:
        target_id = username_mapping.get(clean_username)

    blacklist = context.bot_data.get('blacklist', {})

    if not target_id or target_id not in blacklist:
        await update.message.reply_text(f"❌ User `{target_user_str}` tidak ada di daftar blacklist.", parse_mode="Markdown")
        return

    del context.bot_data['blacklist'][target_id]

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text="✅ Status Blacklist Anda telah dicabut oleh Admin. Sekarang Anda dapat /stor gmail kembali."
        )
    except Exception:
        pass

    await update.message.reply_text(f"✅ User @{clean_username} (ID: `{target_id}`) berhasil dihapus dari daftar Blacklist.", parse_mode="Markdown")


# --- FITUR ADMIN: /cuser ---

async def cuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    all_users = context.bot_data.get('all_users', set())
    if not all_users:
        await update.message.reply_text("👥 Belum ada pengguna yang terdaftar.")
        return

    status_msg = await update.message.reply_text("🔄 Memeriksa username aktif.....")

    active_usernames = []
    inactive_count = 0

    for user_id in list(all_users):
        try:
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            chat_info = await context.bot.get_chat(user_id)
            if chat_info.username:
                active_usernames.append(f"@{chat_info.username}")
            else:
                active_usernames.append(f"{chat_info.first_name} (ID: <code>{user_id}</code>)")
        except Forbidden:
            inactive_count += 1
        except Exception:
            pass

    report_lines = [
        "<b>📢 LIST USERNAME AKTIF</b>\n",
        f"✅ Total Aktif: <b>{len(active_usernames)}</b>",
        f"❌ Total Nonaktif: <b>{inactive_count}</b>\n",
        "<b>📋 Daftar User Name:</b>"
    ]

    for uname in active_usernames:
        report_lines.append(f"• {uname}")

    final_report = "\n".join(report_lines)

    try:
        await status_msg.edit_text(final_report, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(final_report, parse_mode="HTML")


# --- COMMAND ADMIN LAINNYA ---

async def storan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    now = datetime.now()
    tgl_sekarang_str = now.strftime("%d-%m-%Y")

    gmail_owners = context.bot_data.get('gmail_owners', {})
    daily_user_gmails = context.bot_data.get('daily_user_gmails', {}).get(tgl_sekarang_str, {})
    user_history = context.bot_data.get('user_history', {})

    user_valid_map = {}
    for u_id, g_list in daily_user_gmails.items():
        valid_list = [g for g in g_list if g in gmail_owners]
        if valid_list:
            user_valid_map[u_id] = valid_list

    if not user_valid_map:
        await update.message.reply_text(
            f"Informasi Storan Hari Ini\nTanggal: {tgl_sekarang_str}\n\n❌ Belum Ada Storan Ganteng....",
            parse_mode="HTML"
        )
        return

    response_lines = ["Informasi Storan Hari Ini", f"Tanggal: {tgl_sekarang_str}\n"]
    total_pengeluaran_hari_ini = 0

    for u_id, g_list in user_valid_map.items():
        jumlah_gmail = len(g_list)
        if jumlah_gmail == 0:
            continue

        try:
            user_chat = await context.bot.get_chat(u_id)
            username_tele = f"@{user_chat.username}" if user_chat.username else f"{user_chat.first_name}"
        except Exception:
            username_tele = f"User ID {u_id}"

        if 1 <= jumlah_gmail <= 20:
            total_harga = jumlah_gmail * 4500
        else:
            total_harga = jumlah_gmail * 5000

        total_pengeluaran_hari_ini += total_harga
        total_harga_str = f"{total_harga:,}".replace(",", ".")

        pay_info = user_history.get(u_id, {"no_dana": "-", "atas_nama": "-"})
        no_dana = pay_info.get("no_dana", "-")

        entry = (
            f"User Name Tele: {username_tele}\n"
            f"Jumlah Gmail: {jumlah_gmail}\n"
            f"Harga: Rp {total_harga_str}\n"
            f"Nomor Dana: <code>{no_dana}</code>\n"
            f"-----------------------------------"
        )
        response_lines.append(entry)

    total_pengeluaran_str = f"{total_pengeluaran_hari_ini:,}".replace(",", ".")
    response_lines.append(f"<b>💰 TOTAL: Rp {total_pengeluaran_str}</b>")

    final_response = "\n".join(response_lines)
    await update.message.reply_text(final_response, parse_mode="HTML")

async def hpsgmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    command_text = " ".join(context.args)
    if not command_text:
        await update.message.reply_text("❌ Format salah! Gunakan:\n`/hpsgmail username@gmail.com, username2@gmail.com`", parse_mode="Markdown")
        return

    raw_gmails = command_text.replace("\n", ",").split(",")
    valid_gmails = [g.strip().lower() for g in raw_gmails if "@gmail.com" in g.lower()]

    if not valid_gmails:
        await update.message.reply_text("❌ Tidak ditemukan alamat gmail yang valid.")
        return

    gmail_owners = context.bot_data.get('gmail_owners', {})
    gmail_passwords = context.bot_data.get('gmail_passwords', {})
    daily_gmails = context.bot_data.get('daily_gmails', {})

    deleted_count = 0
    not_found_count = 0

    for g in valid_gmails:
        found = False
        if g in gmail_owners:
            del gmail_owners[g]
            found = True
            
        if g in gmail_passwords:
            del gmail_passwords[g]

        for date_key, g_list in daily_gmails.items():
            new_list = [item for item in g_list if item.lower() != g]
            if len(new_list) < len(g_list):
                daily_gmails[date_key] = new_list
                found = True

        if found:
            deleted_count += 1
        else:
            not_found_count += 1

    await update.message.reply_text(
        f"🗑 **Laporan Penghapusan Gmail:**\n"
        f"✅ Berhasil dihapus dari database: **{deleted_count}** Gmail bad\n"
        f"⚠️ Tidak ditemukan / sudah terhapus: **{not_found_count}** Gmail",
        parse_mode="Markdown"
    )

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    custom_text = update.message.text.split(None, 1)[1] if len(update.message.text.split(None, 1)) > 1 else ""
    context.bot_data['is_open'] = True
    context.bot_data['open_message'] = custom_text

    pesan_balasan = "✅ Bot berhasil DIBUKA untuk interaksi user."
    if custom_text:
        pesan_balasan += f"\n\nPesan open custom yang diatur:\n{custom_text}"

    await update.message.reply_text(pesan_balasan, parse_mode="Markdown")

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    context.bot_data['is_open'] = False
    default_close_msg = "⚠️ PEMBERITAHUAN\n\nMohon maaf, setoran Gmail saat ini sedang TUTUP. Silakan coba lagi nanti ketika bot sudah dibuka kembali!!."

    if context.bot_data.get('open_message'):
        context.bot_data['close_message'] = context.bot_data.get('open_message')
    else:
        context.bot_data['close_message'] = default_close_msg

    await update.message.reply_text("🔴 Bot berhasil DITUTUP. User tidak akan bisa melakukan setoran.", parse_mode="Markdown")

async def useraktif_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    all_users = context.bot_data.get('all_users', set())
    if not all_users:
        await update.message.reply_text("👥 Belum ada data pengguna yang tersimpan.")
        return

    status_msg = await update.message.reply_text("🔄 Memeriksa status pengguna aktif...")
    active_users = []
    inactive_users = []

    for user_id in list(all_users):
        try:
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            active_users.append(user_id)
        except Forbidden:
            inactive_users.append(user_id)
        except Exception:
            active_users.append(user_id)

    report_lines = [
        "📊 **LAPORAN USER AKTIF BOT**",
        f"✅ Active Users: **{len(active_users)}**",
        f"❌ Inactive Users: **{len(inactive_users)}**",
        f"👥 Total Terdaftar: **{len(all_users)}**\n",
        "🆔 **Daftar User ID Aktif:**"
    ]

    for uid in active_users:
        report_lines.append(f"• `{uid}`")

    final_report = "\n".join(report_lines)
    try:
        await status_msg.edit_text(final_report, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(final_report, parse_mode="Markdown")

async def useraktifd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    now = datetime.now()
    tgl_sekarang_str = now.strftime("%d-%m-%Y")
    log_harian = context.bot_data.get('setoran_log', {})
    users_today = log_harian.get(tgl_sekarang_str, set())

    if not users_today:
        await update.message.reply_text(
            f"📊 **LAPORAN USER AKTIF HARIAN**\nTanggal: `{tgl_sekarang_str}`\n\n❌ Belum ada pengguna yang melakukan setoran hari ini.",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text("🔄 Memeriksa status pengguna yang aktif menyetor hari ini...")

    active_users = []
    inactive_users = []

    for user_id in list(users_today):
        try:
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            active_users.append(user_id)
        except Forbidden:
            inactive_users.append(user_id)
        except Exception:
            active_users.append(user_id)

    report_lines = [
        "📊 **LAPORAN USER AKTIF HARIAN (HARI INI)**",
        f"📅 Tanggal: `{tgl_sekarang_str}`\n",
        f"✅ Active Users: **{len(active_users)}**",
        f"❌ Inactive Users: **{len(inactive_users)}**",
        f"👥 Total Penyetor Hari Ini: **{len(users_today)}**\n",
        "🆔 **Daftar User ID Aktif Hari Ini:**"
    ]

    for uid in active_users:
        report_lines.append(f"• `{uid}`")

    final_report = "\n".join(report_lines)
    try:
        await status_msg.edit_text(final_report, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(final_report, parse_mode="Markdown")

async def cekpayv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    command_text = " ".join(context.args)
    if not command_text:
        await update.message.reply_text("❌ Format salah! Gunakan:\n`/cekpayv nama1@gmail.com, nama2@gmail.com`", parse_mode="Markdown")
        return

    raw_gmails = command_text.replace("\n", ",").split(",")
    valid_gmails = [g.strip().lower() for g in raw_gmails if "@gmail.com" in g.lower()]

    if not valid_gmails:
        await update.message.reply_text("❌ Tidak ditemukan alamat gmail yang valid.")
        return

    gmail_owners = context.bot_data.get('gmail_owners', {})
    user_history = context.bot_data.get('user_history', {})

    owner_to_gmails = {}
    for g in valid_gmails:
        if g in gmail_owners:
            u_id = gmail_owners[g]
            if u_id not in owner_to_gmails:
                owner_to_gmails[u_id] = []
            owner_to_gmails[u_id].append(g)

    if not owner_to_gmails:
        await update.message.reply_text("❌ Tidak ditemukan data pemilik untuk list Gmail yang dimasukkan.")
        return

    response_lines = ["Data Storan User Valid\n"]
    for u_id, g_list in owner_to_gmails.items():
        pay_info = user_history.get(u_id, {"no_dana": "-", "atas_nama": "-"})
        no_dana = pay_info.get("no_dana", "-")
        atas_nama = pay_info.get("atas_nama", "-")

        jumlah_valid = len(g_list)
        if 1 <= jumlah_valid <= 20:
            total_harga = jumlah_valid * 4500
        else:
            total_harga = jumlah_valid * 5000

        total_harga_str = f"{total_harga:,}".replace(",", ".")

        entry = (
            f"Nomor Dana: <code>{no_dana}</code>\n"
            f"Atas Nama: {atas_nama}\n"
            f"Jumlah Valid: {jumlah_valid} Akun\n"
            f"Total Payment: Rp {total_harga_str}\n"
            f"--------------------------------"
        )
        response_lines.append(entry)

    final_response = "\n".join(response_lines)
    await update.message.reply_text(final_response, parse_mode="HTML")

# --- FILTER COMMAND KHUSUS PASSWORD (/sgsg1122, /fineirga, /prabujaya) ---

async def password_filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    command_text = update.message.text.strip().lower()
    target_pwd = command_text.replace("/", "")

    gmail_passwords = context.bot_data.get('gmail_passwords', {})

    filtered_gmails = [
        gmail for gmail, pwd in gmail_passwords.items() 
        if pwd == target_pwd
    ]

    total_gmail = len(filtered_gmails)

    if total_gmail == 0:
        await update.message.reply_text(
            f"Total Gmail: 0\nAll Password: {target_pwd}\n\n❌ Tidak ada Gmail terdaftar dengan password ini."
        )
        return

    list_gmail_str = "\n".join(filtered_gmails)
    
    response_text = (
        f"Total Gmail: {total_gmail}\n"
        f"All Password: {target_pwd}\n\n"
        f"{list_gmail_str}"
    )

    await update.message.reply_text(response_text)

async def cekuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    all_users = context.bot_data.get('all_users', set())
    if not all_users:
        await update.message.reply_text("👥 Data Pengguna:\nBelum ada pengguna yang menekan /start.")
        return
    total_users = len(all_users)
    user_list_str = "\n".join([f"• <code>{uid}</code>" for uid in all_users])
    text_report = f"📊 LAPORAN USER BOT\n\n👤 Total User Aktif: {total_users} pengguna\n\n🆔 Daftar User ID:\n{user_list_str}"
    await update.message.reply_text(text_report, parse_mode="HTML")

async def suksespay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    check_and_reset_monthly_leaderboard(context)

    kemarin = datetime.now() - timedelta(days=1)
    tgl_kemarin_str = kemarin.strftime("%d-%m-%Y")
    tgl_display_str = kemarin.strftime("%d, %B %Y")
    log_harian = context.bot_data.get('setoran_log', {})
    user_kemarin = log_harian.get(tgl_kemarin_str, set())

    if not user_kemarin:
        await update.message.reply_text(f"❌ Tidak ada pengguna baru yang perlu dikirimkan notifikasi payment ({tgl_display_str}).")
        return

    text_pay = (
        "Sukses Full Payment✅\n"
        "Admin Sudah Melakukan Payment Kedalam Dana Anda, Mohon Cek Akun Dana Anda\n"
        "Jangan Lupa Stor Gmail Anda Lagi Yaa\n"
        "Join Saluran Admin https://t.me/storgmailynd4\n"
        f"Date: {tgl_display_str}"
    )
    counter = 0

    gmail_owners = context.bot_data.get('gmail_owners', {})
    gmail_passwords = context.bot_data.get('gmail_passwords', {})
    daily_user_gmails = context.bot_data.get('daily_user_gmails', {}).get(tgl_kemarin_str, {})
    daily_gmails = context.bot_data.get('daily_gmails', {})
    referral_parents = context.bot_data.get('referral_parents', {})

    if 'referral_balance' not in context.bot_data:
        context.bot_data['referral_balance'] = {}
        
    if 'leaderboard_income' not in context.bot_data:
        context.bot_data['leaderboard_income'] = {}

    for user_id in list(user_kemarin):
        try:
            user_chat = await context.bot.get_chat(user_id)
            if user_chat.type in ["private"]:
                await context.bot.send_message(chat_id=user_id, text=text_pay)
                counter += 1
        except Exception:
            pass

        valid_user_gmails = [g for g in daily_user_gmails.get(user_id, []) if g in gmail_owners]
        jumlah_valid = len(valid_user_gmails)

        if jumlah_valid > 0:
            if 1 <= jumlah_valid <= 20:
                penghasilan_user = jumlah_valid * 4500
            else:
                penghasilan_user = jumlah_valid * 5000

            context.bot_data['leaderboard_income'][user_id] = (
                context.bot_data['leaderboard_income'].get(user_id, 0) + penghasilan_user
            )

        if user_id in referral_parents and jumlah_valid > 0:
            parent_id = referral_parents[user_id]
            komisi = jumlah_valid * 50
            context.bot_data['referral_balance'][parent_id] = context.bot_data['referral_balance'].get(parent_id, 0) + komisi

            if 'referral_valid_set' not in context.bot_data:
                context.bot_data['referral_valid_set'] = {}
            if parent_id not in context.bot_data['referral_valid_set']:
                context.bot_data['referral_valid_set'][parent_id] = set()

            if user_id not in context.bot_data['referral_valid_set'][parent_id]:
                context.bot_data['referral_valid_set'][parent_id].add(user_id)
                if 'referral_valid_count' not in context.bot_data:
                    context.bot_data['referral_valid_count'] = {}
                context.bot_data['referral_valid_count'][parent_id] = len(context.bot_data['referral_valid_set'][parent_id])

    gmails_to_remove = set()
    for uid in user_kemarin:
        user_gmails = daily_user_gmails.get(uid, [])
        for g in user_gmails:
            gmails_to_remove.add(g.lower())

    for g in gmails_to_remove:
        if g in gmail_owners:
            del gmail_owners[g]
        if g in gmail_passwords:
            del gmail_passwords[g]

    if tgl_kemarin_str in daily_gmails:
        del daily_gmails[tgl_kemarin_str]

    if 'daily_user_gmails' in context.bot_data and tgl_kemarin_str in context.bot_data['daily_user_gmails']:
        del context.bot_data['daily_user_gmails'][tgl_kemarin_str]

    del log_harian[tgl_kemarin_str]

    await update.message.reply_text(
        f"✅ Berhasil mengirimkan 1x notifikasi Sukses Payment ke {counter} user dari setoran kemarin.\n"
        f"💸 Komisi Referral sebesar Rp 50/Gmail telah ditambahkan ke pengundang.\n"
        f"📊 Leaderboard Penghasilan berhasil diperbarui otomatis.\n"
        f"🗑 Data Gmail setoran tanggal {tgl_kemarin_str} otomatis dibersihkan dari database."
    )

async def hapusdata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    context.bot_data['gmail_owners'] = {}
    context.bot_data['gmail_passwords'] = {}
    context.bot_data['daily_gmails'] = {}
    context.bot_data['daily_user_gmails'] = {}
    context.bot_data['setoran_log'] = {}

    await update.message.reply_text(
        "🗑 **BERHASIL MENGHAPUS DATABASE!**\n\n"
        "Seluruh data Gmail user dan log setoran harian telah dibersihkan.",
        parse_mode="Markdown"
    )

async def tolak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    command_text = " ".join(context.args)
    if not command_text or "," not in command_text:
        await update.message.reply_text("❌ Format salah! Gunakan: \n`/tolak nama@gmail.com, (Alasan penolakan)`", parse_mode="Markdown")
        return
    try:
        parts = [p.strip() for p in command_text.split(",")]
        alasan = parts[-1].replace("(", "").replace(")", "")
        gmail_targets = parts[:-1]
        owner_to_gmails = {}
        gmail_owners = context.bot_data.get('gmail_owners', {})

        for gmail in gmail_targets:
            g_low = gmail.lower()
            if g_low in gmail_owners:
                u_id = gmail_owners[g_low]
                if u_id not in owner_to_gmails:
                    owner_to_gmails[u_id] = []
                owner_to_gmails[u_id].append(gmail)

        if not owner_to_gmails:
            await update.message.reply_text("❌ Tidak ditemukan data pemilik.")
            return

        for u_id, gmails in owner_to_gmails.items():
            text_tolak = f"⚠️ Penghapusan Gmail Dari Admin❗\nJumlah Gmail: {len(gmails)}\nDomain Gmail: {', '.join(gmails)}\nAlasan: {alasan}"
            try:
                user_chat = await context.bot.get_chat(u_id)
                if user_chat.type in ["private"]:
                    await context.bot.send_message(chat_id=u_id, text=text_tolak)
            except Exception:
                pass

        await update.message.reply_text(f"✅ Sukses menolak {len(gmail_targets)} gmail.")
    except Exception as e:
        await update.message.reply_text(f"❌ Kesalahan format: {e}")

async def informasi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.effective_user.id != ADMIN_ID:
        return

    pesan_siaran = update.message.text.split(None, 1)[1] if len(update.message.text.split(None, 1)) > 1 else ""
    if not pesan_siaran:
        await update.message.reply_text("❌ Silakan ketik isi pengumuman setelah perintah.")
        return

    all_users = context.bot_data.get('all_users', set())
    counter = 0
    for user_id in list(all_users):
        try:
            user_chat = await context.bot.get_chat(user_id)
            if user_chat.type in ["private"]:
                await context.bot.send_message(chat_id=user_id, text=pesan_siaran)
                counter += 1
        except Exception:
            pass

    await update.message.reply_text(f"✅ Berhasil Tuan, Terkirim Ke {counter} Pengguna.")


# --- MAIN PROGRAM ---
async def main():
    # Mengonfigurasi persistence agar menyimpan SEMUA bot_data secara menyeluruh
    my_persistence = PicklePersistence(
        filepath='bot_persistence.pickle',
        store_data=PersistenceInput(
            bot_data=True,
            user_data=True,
            chat_data=True,
            callback_data=True
        )
    )

    app = (
        Application.builder()
        .token(TOKEN)
        .persistence(my_persistence)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('stor', stor_command, filters=filters.ChatType.PRIVATE),
            MessageHandler(filters.TEXT & filters.Regex(r'(?i)stor') & filters.ChatType.PRIVATE, stor_command)
        ],
        states={
            STOR_GMAIL: [
                MessageHandler(filters.TEXT & filters.Regex(r'(?i)stor') & filters.ChatType.PRIVATE, stor_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, process_gmail)
            ],
            CHECK_SANDI: [
                MessageHandler(filters.TEXT & filters.Regex(r'(?i)stor') & filters.ChatType.PRIVATE, stor_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, process_check_sandi)
            ],
            CEK_PAYMENT_LAMA: [
                MessageHandler(filters.TEXT & filters.Regex(r'(?i)stor') & filters.ChatType.PRIVATE, stor_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, process_cek_payment_lama)
            ],
            DATA_PAYMENT: [
                MessageHandler(filters.TEXT & filters.Regex(r'(?i)stor') & filters.ChatType.PRIVATE, stor_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, process_payment)
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel, filters=filters.ChatType.PRIVATE), 
            MessageHandler(filters.Regex(r'^❌ Batal$') & filters.ChatType.PRIVATE, cancel)
        ],
        name="my_conversation",     
        persistent=True,
        per_message=False  
    )

    conv_wd_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^💸 Withdrawal$') & filters.ChatType.PRIVATE, start_withdrawal)
        ],
        states={
            WD_NO_DANA: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, process_wd_no_dana)],
            WD_ATAS_NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, process_wd_atas_nama)],
            WD_JUMLAH: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, process_wd_jumlah)],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r'^❌ Batal$') & filters.ChatType.PRIVATE, cancel_wd)
        ],
        name="wd_conversation",
        persistent=True,
        per_message=False
    )

    app.add_handler(CommandHandler('start', start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(verification_callback, pattern=r'^check_membership$'))
    
    app.add_handler(CallbackQueryHandler(main_menu_inline_callback, pattern=r'^menu_'))

    app.add_handler(CommandHandler('referral', referral_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('leaderboard', leaderboard_command, filters=filters.ChatType.PRIVATE))

    app.add_handler(MessageHandler(filters.Regex(r'^🏠 Kembali Kehalaman Utama$') & filters.ChatType.PRIVATE, back_to_main))

    # --- HANDLER KHUSUS ADMIN ---
    app.add_handler(CommandHandler('bl', bl_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('unbl', unbl_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('cuser', cuser_command, filters=filters.ChatType.PRIVATE))

    # --- HANDLER COMMAND FILTER PASSWORD ADMIN ---
    app.add_handler(CommandHandler('sgsg1122', password_filter_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('fineirga', password_filter_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('prabujaya', password_filter_command, filters=filters.ChatType.PRIVATE))

    # --- HANDLER ADMIN LAINNYA ---
    app.add_handler(CommandHandler('open', open_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('close', close_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('useraktif', useraktif_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('useraktifd', useraktifd_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('cekpayv', cekpayv_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('cekuser', cekuser_command, filters=filters.ChatType.PRIVATE))  
    app.add_handler(CommandHandler('suksespay', suksespay_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('hapusdata', hapusdata_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('tolak', tolak_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('informasi', informasi_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('hpsgmail', hpsgmail_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('storan', storan_command, filters=filters.ChatType.PRIVATE))

    app.add_handler(conv_handler)
    app.add_handler(conv_wd_handler)

    print("==========================================")
    print("      BOT TELEGRAM BERHASIL DIAKTIFKAN    ")
    print("==========================================")
    print("Status: Online & Persistence Active!")
    print("Tekan CTRL + C untuk menghentikan bot.")
    print("------------------------------------------")

    await app.initialize()
    await app.updater.start_polling()
    await app.start()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        print("\n[!] Bot dihentikan.")
        await app.updater.stop()
        await app.stop()

if __name__ == '__main__':
    asyncio.run(main())
