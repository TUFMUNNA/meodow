import json
import os
import random
import asyncio
import re
import sys
import logging
import shutil
import subprocess
import signal
from telegram import Update, Chat, Message, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from pyrogram import Client
from pyrogram import enums

# --- Logging Setup ---
LOG_FILE = "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"
DATA_FILE = "bot_data.json"
SESSIONS_FILE = "sessions.json"
GREETINGS_FILE = "greetings.txt"
MULTIBOTS_DIR = "multibots"
MULTIBOTS_FILE = "multibots.json"

SUPER_ADMIN_IDS = [7574652791, 5689759292]  # <--- PUT YOUR TELEGRAM USER IDS HERE

DEFAULT_CONFIG = {
    "DG": [12, 15],
    "DM": [7, 10],
    "base": "NFT",
    "counter": [1, 45],
}

# Maximum simultaneous sessions processed in one batch
MAX_MULTI_CLIENTS = 10

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"groups": [], "authorized": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_sessions():
    if os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_sessions(sessions):
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f, indent=2)

def load_multibots():
    if os.path.exists(MULTIBOTS_FILE):
        with open(MULTIBOTS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_multibots(multibots):
    with open(MULTIBOTS_FILE, "w") as f:
        json.dump(multibots, f, indent=2)

def parse_greetings(greetings_file=GREETINGS_FILE):
    if not os.path.exists(greetings_file):
        return []
    with open(greetings_file, "r") as f:
        content = f.read()
    greetings = re.findall(r'"""(.*?)"""', content, re.DOTALL)
    return [g.strip() for g in greetings if g.strip()]

def is_super_admin(user_id):
    return user_id in SUPER_ADMIN_IDS

def is_authorized(user_id):
    data = load_data()
    return is_super_admin(user_id) or user_id in data["authorized"]

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("You are not authorized to use this bot.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    text = (
        "<b><i>🚀 Welcome to <u>Multi Client Group Maker Bot</u>!</i></b>\n"
        "\n"
        "<b>✨ Manage multiple Telegram groups effortlessly.</b>\n"
        "<b>🧑‍💻 Super Admin:</b> Controls everything.\n"
        "<b>🤖 Use</b> /help <b>to view all commands!</b>\n"
        "\n"
        "<i>Stay cool. Automate smarter. Build faster.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    
    keyboard = [
        [
            InlineKeyboardButton("📋 Basic Commands", callback_data="help_basic"),
            InlineKeyboardButton("👤 User Management", callback_data="help_users")
        ],
        [
            InlineKeyboardButton("📱 Session Commands", callback_data="help_sessions"),
            InlineKeyboardButton("👥 Group Commands", callback_data="help_groups")
        ],
        [
            InlineKeyboardButton("🤖 Multi-Bot", callback_data="help_multibot"),
            InlineKeyboardButton("⚙️ Advanced", callback_data="help_advanced")
        ],
        [
            InlineKeyboardButton("📊 Stats & Info", callback_data="help_stats"),
            InlineKeyboardButton("🔧 System", callback_data="help_system")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "<b>🛠️ Bot Command Menu</b>\n\n"
        "<i>Select a category to view commands:</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    help_texts = {
        "help_basic": (
            "<b>📋 Basic Commands</b>\n\n"
            "/start — <i>Show welcome message</i>\n"
            "/help — <i>Show this menu</i>\n"
            "/cancel — <i>Cancel current operation</i>"
        ),
        "help_users": (
            "<b>👤 User Management</b>\n\n"
            "/addauth &lt;user_id&gt; — <i>Authorize user</i>\n"
            "/removeauth &lt;user_id&gt; — <i>Remove authorized user</i>"
        ),
        "help_sessions": (
            "<b>📱 Session Commands</b>\n\n"
            "/addsession &lt;name&gt; &lt;string&gt; — <i>Add Pyrogram session</i>\n"
            "/removesession — <i>Remove session(s)</i>\n"
            "/check — <i>Check groups owned by session</i>\n"
            "/sendadmin — <i>Send session strings to admin</i>\n"
            "/ping — <i>Send hello from all sessions</i>"
        ),
        "help_groups": (
            "<b>👥 Group Commands</b>\n\n"
            "/cgroups — <i>Create groups via sessions (supports batch)</i>\n"
            "/RG — <i>Register group for broadcast</i>\n"
            "/drg — <i>Deregister this group</i>\n"
            "/removegrps — <i>Remove all groups</i>\n"
            "/checkgroups — <i>Check live/removed groups</i>\n"
            "/joinchat &lt;link&gt; — <i>Join chat with all sessions</i>\n"
            "/leavechat &lt;link&gt; — <i>Leave chat with all sessions</i>\n"
            "/clearall — <i>Leave non-owned groups/channels (1-3s delay)</i>"
        ),
        "help_multibot": (
            "<b>🤖 Multi-Bot Management</b>\n\n"
            "/multibot — <i>Multi-bot menu</i>\n"
            "/addmultibot — <i>Add new bot instance</i>\n"
            "/rmmultibot — <i>Remove bot instance</i>\n"
            "/deploy — <i>Deploy multi-bot (auto-starts)</i>\n"
            "/stopmultibot — <i>List running multi-bots</i>\n"
            "/killbot &lt;number&gt; — <i>Stop a running multi-bot</i>"
        ),
        "help_advanced": (
            "<b>⚙️ Advanced Commands</b>\n\n"
            "/config [option] [value] — <i>Set configuration</i>\n"
            "/broadcast &lt;msg&gt; — <i>Broadcast to all groups</i>"
        ),
        "help_stats": (
            "<b>📊 Stats & Information</b>\n\n"
            "/stats — <i>Show bot statistics</i>\n"
            "/info — <i>Show config and info</i>"
        ),
        "help_system": (
            "<b>🔧 System Commands</b>\n\n"
            "/getlogs — <i>Send log file</i>\n"
            "/restart — <i>Restart the bot</i>\n"
            "/stop — <i>Stop the bot</i>"
        )
    }
    
    # Back button
    keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="help_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = help_texts.get(query.data, "Unknown category")
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def help_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [
            InlineKeyboardButton("📋 Basic Commands", callback_data="help_basic"),
            InlineKeyboardButton("👤 User Management", callback_data="help_users")
        ],
        [
            InlineKeyboardButton("📱 Session Commands", callback_data="help_sessions"),
            InlineKeyboardButton("👥 Group Commands", callback_data="help_groups")
        ],
        [
            InlineKeyboardButton("🤖 Multi-Bot", callback_data="help_multibot"),
            InlineKeyboardButton("⚙️ Advanced", callback_data="help_advanced")
        ],
        [
            InlineKeyboardButton("📊 Stats & Info", callback_data="help_stats"),
            InlineKeyboardButton("🔧 System", callback_data="help_system")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "<b>🛠️ Bot Command Menu</b>\n\n"
        "<i>Select a category to view commands:</i>"
    )
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def add_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    data = load_data()
    try:
        auth_id = int(context.args[0])
    except:
        await update.message.reply_text("Usage: /addauth <user_id>")
        return
    if auth_id not in data["authorized"]:
        data["authorized"].append(auth_id)
        save_data(data)
        await update.message.reply_text(f"<b>✅ User</b> <code>{auth_id}</code> <b>authorized.</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("<b>Already authorized.</b>", parse_mode=ParseMode.HTML)

async def remove_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    data = load_data()
    try:
        auth_id = int(context.args[0])
    except:
        await update.message.reply_text("Usage: /removeauth <user_id>")
        return
    if auth_id in data["authorized"]:
        data["authorized"].remove(auth_id)
        save_data(data)
        await update.message.reply_text(f"<b>✅ User</b> <code>{auth_id}</code> <b>removed from authorized list.</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("<b>User not authorized.</b>", parse_mode=ParseMode.HTML)

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    config = load_config()
    args = context.args

    if not args:
        msg = (
            "<b>⚙️ Current Config:</b>\n"
            f"<b>DG</b> (delay groups): <code>{config['DG'][0]}</code> - <code>{config['DG'][1]}</code> sec\n"
            f"<b>DM</b> (delay message): <code>{config['DM'][0]}</code> - <code>{config['DM'][1]}</code> sec\n"
            f"<b>base</b>: <code>{config['base']}</code>\n"
            f"<b>counter</b>: <code>{config['counter'][0]}</code> - <code>{config['counter'][1]}</code>\n"
            "<i>Change with:</i>\n"
            "<code>/config DG 10 15</code> (group delay random 10-15s)\n"
            "<code>/config DM 5 8</code> (message delay random 5-8s)\n"
            "<code>/config base NFT</code>\n"
            "<code>/config counter 1 45</code>\n"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    key = args[0].lower()
    if key == "dg":
        if len(args) == 3 and args[1].isdigit() and args[2].isdigit():
            config["DG"] = [int(args[1]), int(args[2])]
            save_config(config)
            await update.message.reply_text(
                f"<b>Group creation delay set to:</b> <code>{config['DG'][0]}</code>-<code>{config['DG'][1]}</code> sec",
                parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("Usage: /config DG [min] [max]", parse_mode=ParseMode.HTML)
    elif key == "dm":
        if len(args) == 3 and args[1].isdigit() and args[2].isdigit():
            config["DM"] = [int(args[1]), int(args[2])]
            save_config(config)
            await update.message.reply_text(
                f"<b>Message delay set to:</b> <code>{config['DM'][0]}</code>-<code>{config['DM'][1]}</code> sec",
                parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("Usage: /config DM [min] [max]", parse_mode=ParseMode.HTML)
    elif key == "base":
        if len(args) >= 2:
            config["base"] = " ".join(args[1:])
            save_config(config)
            await update.message.reply_text(
                f"<b>Base group name set to:</b> <code>{config['base']}</code>",
                parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("Usage: /config base [name]", parse_mode=ParseMode.HTML)
    elif key == "counter":
        if len(args) == 3 and args[1].isdigit() and args[2].isdigit():
            config["counter"] = [int(args[1]), int(args[2])]
            save_config(config)
            await update.message.reply_text(
                f"<b>Counter set from</b> <code>{config['counter'][0]}</code> <b>to</b> <code>{config['counter'][1]}</code>",
                parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("Usage: /config counter [start] [end]", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            "Usage: /config [DG|DM|base|counter] [value...]\nType /config to see current config.",
            parse_mode=ParseMode.HTML)

async def join_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    chat = update.effective_chat
    data = load_data()
    if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        if chat.id not in data["groups"]:
            data["groups"].append(chat.id)
            save_data(data)
            await update.message.reply_text("<b>Group registered for broadcast.</b>", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("<b>Group already registered.</b>", parse_mode=ParseMode.HTML)

async def RG(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    chat = update.effective_chat
    data = load_data()
    if chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        await update.message.reply_text("<b>Use this command in a group/supergroup to register it.</b>", parse_mode=ParseMode.HTML)
        return
    if chat.id not in data["groups"]:
        data["groups"].append(chat.id)
        save_data(data)
        await update.message.reply_text("✅ <b>This group is now registered for broadcast.</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("ℹ️ <b>This group is already registered.</b>", parse_mode=ParseMode.HTML)

async def drg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deregister/remove current group from broadcast list."""
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    chat = update.effective_chat
    data = load_data()
    if chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        await update.message.reply_text("<b>Use this command in a group/supergroup to deregister it.</b>", parse_mode=ParseMode.HTML)
        return
    if chat.id in data["groups"]:
        data["groups"].remove(chat.id)
        save_data(data)
        await update.message.reply_text("❌ <b>This group is now deregistered from broadcast.</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("ℹ️ <b>This group was not registered.</b>", parse_mode=ParseMode.HTML)

async def removegrps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove all registered groups (super admin only)."""
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    data = load_data()
    data["groups"] = []
    save_data(data)
    await update.message.reply_text("✅ <b>All registered groups have been removed.</b>", parse_mode=ParseMode.HTML)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    data = load_data()
    # If reply to a message, broadcast that
    if update.message.reply_to_message:
        msg_to_broadcast = update.message.reply_to_message
        failed = []
        for group_id in data["groups"]:
            try:
                # If message has text/caption and media
                if msg_to_broadcast.photo:
                    await context.bot.send_photo(
                        chat_id=group_id,
                        photo=msg_to_broadcast.photo[-1].file_id,
                        caption=msg_to_broadcast.caption or "",
                        parse_mode=ParseMode.HTML
                    )
                elif msg_to_broadcast.video:
                    await context.bot.send_video(
                        chat_id=group_id,
                        video=msg_to_broadcast.video.file_id,
                        caption=msg_to_broadcast.caption or "",
                        parse_mode=ParseMode.HTML
                    )
                elif msg_to_broadcast.document:
                    await context.bot.send_document(
                        chat_id=group_id,
                        document=msg_to_broadcast.document.file_id,
                        caption=msg_to_broadcast.caption or "",
                        parse_mode=ParseMode.HTML
                    )
                elif msg_to_broadcast.audio:
                    await context.bot.send_audio(
                        chat_id=group_id,
                        audio=msg_to_broadcast.audio.file_id,
                        caption=msg_to_broadcast.caption or "",
                        parse_mode=ParseMode.HTML
                    )
                elif msg_to_broadcast.voice:
                    await context.bot.send_voice(
                        chat_id=group_id,
                        voice=msg_to_broadcast.voice.file_id,
                        caption=msg_to_broadcast.caption or "",
                        parse_mode=ParseMode.HTML
                    )
                elif msg_to_broadcast.sticker:
                    await context.bot.send_sticker(
                        chat_id=group_id,
                        sticker=msg_to_broadcast.sticker.file_id
                    )
                elif msg_to_broadcast.text or msg_to_broadcast.caption:
                    await context.bot.send_message(
                        chat_id=group_id,
                        text=msg_to_broadcast.text or msg_to_broadcast.caption,
                        parse_mode=ParseMode.HTML
                    )
                else:
                    failed.append(group_id)
            except Exception:
                failed.append(group_id)
        success = len(data["groups"]) - len(failed)
        await update.message.reply_text(
            f"<b>Broadcasted to</b> <code>{success}</code> <b>groups.</b>\n<b>Failed:</b> <code>{failed if failed else 'None'}</code>",
            parse_mode=ParseMode.HTML
        )
        return
    # If command args (text message)
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message> or reply to a post/message with /broadcast to broadcast it.")
        return
    msg = " ".join(context.args)
    failed = []
    for group_id in data["groups"]:
        try:
            await context.bot.send_message(chat_id=group_id, text=msg, parse_mode=ParseMode.HTML)
        except Exception:
            failed.append(group_id)
    success = len(data["groups"]) - len(failed)
    await update.message.reply_text(
        f"<b>Sent to</b> <code>{success}</code> <b>groups.</b>\n<b>Failed:</b> <code>{failed if failed else 'None'}</code>",
        parse_mode=ParseMode.HTML
    )

async def check_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    data = load_data()
    groups = data["groups"]
    active = []
    removed = []
    for group_id in groups:
        try:
            await context.bot.send_message(chat_id=group_id, text="✅ <b>Bot is active in this group!</b>", parse_mode=ParseMode.HTML)
            active.append(group_id)
        except Exception:
            removed.append(group_id)
    if removed:
        for gid in removed:
            data["groups"].remove(gid)
        save_data(data)
    await update.message.reply_text(
        f"<b>Active in</b> <code>{len(active)}</code> <b>groups.</b>\n<b>Removed</b> <code>{len(removed)}</code> <b>groups from list.</b>",
        parse_mode=ParseMode.HTML
    )

async def addsession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addsession <session_name> <string_session>")
        return
    session_name = context.args[0]
    string_session = " ".join(context.args[1:])
    sessions = load_sessions()
    sessions[session_name] = string_session
    save_sessions(sessions)
    await update.message.reply_text(f"<b>Session</b> <code>{session_name}</code> <b>added.</b>", parse_mode=ParseMode.HTML)

# --- Conversation states ---
CHOOSE_CLIENTS, ASK_GROUP_COUNT, ASK_SESSION_REMOVE = range(3)
MULTIBOT_ASK_TOKEN, MULTIBOT_ASK_NAME, MULTIBOT_ASK_GREETING, MULTIBOT_DEPLOY = range(3, 7)
CHECK_CHOOSE_SESSION, SENDADMIN_ASK_USERNAME, PING_ASK_USERNAME = range(7, 10)
JOINCHAT_ASK_LINK, LEAVECHAT_ASK_LINK = range(10, 12)

# For cancellation
group_creation_tasks = {}

def parse_batch_input(text, max_len):
    """Parse batch 1 20 or similar format"""
    text = text.strip().lower()
    parts = text.split()
    if len(parts) == 3 and parts[0] == "batch" and parts[1].isdigit() and parts[2].isdigit():
        start_idx = int(parts[1]) - 1
        end_idx = int(parts[2]) - 1
        if 0 <= start_idx <= end_idx < max_len:
            return list(range(start_idx, end_idx + 1))
    return None

async def cgroups_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    sessions = load_sessions()
    if not sessions:
        await update.message.reply_text("<b>No sessions found. Add one with /addsession first.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    session_list = list(sessions.keys())
    numbered = [f"{i+1}. <code>{name}</code>" for i, name in enumerate(session_list)]
    session_names = "\n".join(numbered)
    msg = (
        "<b>Choose session(s) to use:</b>\n"
        f"{session_names}\n"
        f"<b>Reply:</b>\n"
        f"• <code>all</code> (will be processed in batches of {MAX_MULTI_CLIENTS})\n"
        f"• <code>1,3,5</code> (comma-separated numbers)\n"
        f"• <code>1</code> (single number)\n"
        f"• <code>batch 1 20</code> (batch from 1 to 20, processed in batches of 10)"
    )
    context.user_data["session_list"] = session_list
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return CHOOSE_CLIENTS

async def cgroups_choose_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    session_list = context.user_data["session_list"]
    chosen_idxs = []
    
    # Check for batch format
    batch_result = parse_batch_input(text, len(session_list))
    if batch_result is not None:
        chosen_idxs = batch_result
        await update.message.reply_text(
            f"<b>Batch selected:</b> Sessions {batch_result[0]+1} to {batch_result[-1]+1} ({len(batch_result)} sessions)\n"
            f"<b>Will be processed in batches of 10.</b>",
            parse_mode=ParseMode.HTML
        )
    elif text == "all":
        chosen_idxs = list(range(len(session_list)))
    else:
        try:
            chosen_idxs = [int(x.strip())-1 for x in text.split(",") if x.strip().isdigit()]
            chosen_idxs = [i for i in chosen_idxs if 0 <= i < len(session_list)]
        except:
            await update.message.reply_text("<b>Invalid format. Try again or /cancel.</b>", parse_mode=ParseMode.HTML)
            return CHOOSE_CLIENTS
        if not chosen_idxs:
            await update.message.reply_text("<b>No valid client indices.</b>", parse_mode=ParseMode.HTML)
            return CHOOSE_CLIENTS

    # Save both indices and names so we can report progress with original positions
    context.user_data["chosen_idxs"] = chosen_idxs
    context.user_data["chosen_sessions"] = [session_list[i] for i in chosen_idxs]
    # Inform user if they selected more than batch size that processing will be batched.
    if len(chosen_idxs) > MAX_MULTI_CLIENTS:
        await update.message.reply_text(
            f"<b>Note:</b> {len(chosen_idxs)} sessions selected. They will be processed in batches of {MAX_MULTI_CLIENTS}.", parse_mode=ParseMode.HTML
        )

    await update.message.reply_text("<b>How many groups per session?</b>", parse_mode=ParseMode.HTML)
    return ASK_GROUP_COUNT

async def send_greetings_pyrogram(client, group_id, config, greetings_file=GREETINGS_FILE):
    greetings = parse_greetings(greetings_file)
    for msg in greetings:
        try:
            await client.send_message(group_id, msg)
            await asyncio.sleep(random.randint(*config["DM"]))
        except Exception as e:
            logger.error(f"Error sending greeting: {e}")

async def create_supergroups(session_name, string_session, gcount, config, cancel_token, greetings_file=GREETINGS_FILE):
    async with Client(session_name, session_string=string_session) as client:
        created = []
        start, end = config["counter"]
        base = config["base"]
        current = start
        for i in range(gcount):
            if cancel_token.get("cancelled"):
                logger.info("Group creation cancelled by user.")
                break
            if current > end:
                break
            try:
                title = f"{base} {current}"
                chat = await client.create_supergroup(title)
                created.append(chat.id)
                await send_greetings_pyrogram(client, chat.id, config, greetings_file)
                await asyncio.sleep(random.randint(*config["DG"]))
                current += 1
            except Exception as e:
                logger.error(f"Error creating group {i+1} in session {session_name}: {e}")
                current += 1
        return created

async def cgroups_ask_group_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    try:
        count = int(update.message.text.strip())
        max_count = config["counter"][1] - config["counter"][0] + 1
        if count < 1 or count > max_count:
            await update.message.reply_text(
                f"<b>Choose a number between 1 and {max_count}.</b>",
                parse_mode=ParseMode.HTML
            )
            return ASK_GROUP_COUNT
    except:
        await update.message.reply_text("<b>Please send a number.</b>", parse_mode=ParseMode.HTML)
        return ASK_GROUP_COUNT

    chosen_idxs = context.user_data.get("chosen_idxs", [])
    if not chosen_idxs:
        await update.message.reply_text("<b>No sessions chosen. Use /cgroups first.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    sessions = load_sessions()
    # Cancellation token per user
    cancel_token = {"cancelled": False}
    group_creation_tasks[update.effective_user.id] = cancel_token

    # Prepare batches of indices (absolute positions in session_list)
    batches = [chosen_idxs[i:i+MAX_MULTI_CLIENTS] for i in range(0, len(chosen_idxs), MAX_MULTI_CLIENTS)]

    total_created_overall = 0
    per_session_totals = {}  # session_name -> total created

    try:
        for batch_num, batch_idxs in enumerate(batches, start=1):
            if cancel_token.get("cancelled"):
                await update.message.reply_text("<b>❌ Group creation cancelled before starting next batch.</b>", parse_mode=ParseMode.HTML)
                break

            # determine display range in terms of positions (1-based) in the user's selection
            start_pos = batch_idxs[0] + 1
            end_pos = batch_idxs[-1] + 1
            await update.message.reply_text(
                f"<b>Starting sessions {start_pos} to {end_pos}...</b>",
                parse_mode=ParseMode.HTML
            )

            async def launch_for_session_idx(idx):
                session_list = context.user_data["session_list"]
                session_name = session_list[idx]
                string_session = sessions.get(session_name)
                if not string_session:
                    logger.error(f"Session string not found for {session_name}")
                    return session_name, []
                created_ids = await create_supergroups(session_name, string_session, count, config, cancel_token)
                return session_name, created_ids

            # Run the current batch concurrently
            batch_tasks = [launch_for_session_idx(idx) for idx in batch_idxs]
            results = await asyncio.gather(*batch_tasks, return_exceptions=False)

            # Summarize batch
            batch_total = 0
            batch_details = []
            for session_name, created_ids in results:
                created_count = len(created_ids)
                batch_total += created_count
                total_created_overall += created_count
                per_session_totals[session_name] = per_session_totals.get(session_name, 0) + created_count
                batch_details.append(f"{session_name}: {created_count}")

            # Send batch completion stats
            await update.message.reply_text(
                "<b>Batch completed.</b>\n"
                f"<b>Sessions:</b> <code>{start_pos}</code> to <code>{end_pos}</code>\n"
                f"<b>Created in this batch:</b> <code>{batch_total}</code>\n"
                f"<b>Details:</b> <code>{', '.join(batch_details)}</code>",
                parse_mode=ParseMode.HTML
            )

            # If there is another batch, inform that it will start automatically
            if batch_num < len(batches) and not cancel_token.get("cancelled"):
                next_batch_first = batches[batch_num][0] + 1
                next_batch_last = batches[batch_num][-1] + 1
                await update.message.reply_text(
                    f"<b>Starting next batch:</b> <code>{next_batch_first}</code> to <code>{next_batch_last}</code>",
                    parse_mode=ParseMode.HTML
                )

        # Final overall stats
        if not cancel_token.get("cancelled"):
            # Build per-session summary
            per_session_lines = [f"{k}: {v}" for k, v in per_session_totals.items()]
            await update.message.reply_text(
                "<b>✅ All batches completed.</b>\n"
                f"<b>Total groups created:</b> <code>{total_created_overall}</code>\n"
                f"<b>Per-session summary:</b> <code>{'; '.join(per_session_lines) if per_session_lines else 'None'}</code>\n"
                "<i>Note: Created groups are NOT added to the bot's broadcast list.</i>",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text("<b>❌ Group creation was cancelled.</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Group creation error: {e}")
        await update.message.reply_text("<b>❌ Error during group creation.</b>", parse_mode=ParseMode.HTML)
    finally:
        group_creation_tasks.pop(update.effective_user.id, None)
    return ConversationHandler.END

async def removesession_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    sessions = load_sessions()
    if not sessions:
        await update.message.reply_text("<b>No sessions to remove.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    session_list = list(sessions.keys())
    msg = "<b>Sessions:</b>\n" + "\n".join([f"{i+1}. <code>{name}</code>" for i, name in enumerate(session_list)])
    msg += "\n\n<b>Reply with the number(s) to remove (e.g. 1 or 1,2,3).</b>"
    context.user_data["session_list"] = session_list
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return ASK_SESSION_REMOVE

async def removesession_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_list = context.user_data["session_list"]
    text = update.message.text.strip()
    try:
        indices = [int(i.strip())-1 for i in text.split(",") if i.strip().isdigit()]
        to_remove = [session_list[i] for i in indices if 0 <= i < len(session_list)]
    except:
        await update.message.reply_text("<b>Invalid input. Send number(s) or /cancel.</b>", parse_mode=ParseMode.HTML)
        return ASK_SESSION_REMOVE
    if not to_remove:
        await update.message.reply_text("<b>No valid sessions chosen.</b>", parse_mode=ParseMode.HTML)
        return ASK_SESSION_REMOVE
    sessions = load_sessions()
    for name in to_remove:
        sessions.pop(name, None)
    save_sessions(sessions)
    await update.message.reply_text(
        f"<b>Removed session(s):</b> <code>{', '.join(to_remove)}</code>", parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END

# --- Multi-bot commands ---
async def multibot_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Multi-Bot", callback_data="mb_add")],
        [InlineKeyboardButton("❌ Remove Multi-Bot", callback_data="mb_remove")],
        [InlineKeyboardButton("📋 List Multi-Bots", callback_data="mb_list")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "<b>🤖 Multi-Bot Management</b>\n\n"
        "<i>Select an option:</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def multibot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "mb_add":
        await query.edit_message_text(
            "<b>Starting multi-bot setup...</b>\n\nUse /addmultibot to begin.",
            parse_mode=ParseMode.HTML
        )
    elif query.data == "mb_remove":
        await query.edit_message_text(
            "<b>Remove multi-bot...</b>\n\nUse /rmmultibot to select a bot to remove.",
            parse_mode=ParseMode.HTML
        )
    elif query.data == "mb_list":
        multibots = load_multibots()
        if not multibots:
            await query.edit_message_text("<b>No multi-bots deployed.</b>", parse_mode=ParseMode.HTML)
        else:
            bot_list = "\n".join([
                f"{i+1}. <code>{name}</code> - Status: <b>{data.get('status', 'unknown')}</b> (PID: {data.get('pid', 'N/A')})" 
                for i, (name, data) in enumerate(multibots.items())
            ])
            await query.edit_message_text(
                f"<b>Deployed Multi-Bots:</b>\n\n{bot_list}",
                parse_mode=ParseMode.HTML
            )

async def addmultibot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    
    await update.message.reply_text(
        "<b>🤖 Add Multi-Bot</b>\n\n"
        "Please send the bot token:",
        parse_mode=ParseMode.HTML
    )
    return MULTIBOT_ASK_TOKEN

async def addmultibot_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = update.message.text.strip()
    context.user_data["multibot_token"] = token
    
    await update.message.reply_text(
        "<b>✅ Token saved.</b>\n\n"
        "Now send the directory name for this bot (e.g., <code>bot1</code>):",
        parse_mode=ParseMode.HTML
    )
    return MULTIBOT_ASK_NAME

async def addmultibot_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    
    # Check if directory already exists
    bot_dir = os.path.join(MULTIBOTS_DIR, name)
    if os.path.exists(bot_dir):
        await update.message.reply_text(
            "<b>❌ A bot with this name already exists. Choose a different name or /cancel.</b>",
            parse_mode=ParseMode.HTML
        )
        return MULTIBOT_ASK_NAME
    
    context.user_data["multibot_name"] = name
    
    await update.message.reply_text(
        "<b>✅ Name saved.</b>\n\n"
        "Now send the <code>greetings.txt</code> file as a document:",
        parse_mode=ParseMode.HTML
    )
    return MULTIBOT_ASK_GREETING

async def addmultibot_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text(
            "<b>Please send a file (document).</b>",
            parse_mode=ParseMode.HTML
        )
        return MULTIBOT_ASK_GREETING
    
    # Download the file
    file = await update.message.document.get_file()
    greeting_content = await file.download_as_bytearray()
    context.user_data["multibot_greeting"] = greeting_content.decode('utf-8')
    
    await update.message.reply_text(
        "<b>✅ Greetings file received.</b>\n\n"
        "Type <code>/deploy</code> to deploy this bot now:",
        parse_mode=ParseMode.HTML
    )
    return MULTIBOT_DEPLOY

async def deploy_multibot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    
    token = context.user_data.get("multibot_token")
    name = context.user_data.get("multibot_name")
    greeting = context.user_data.get("multibot_greeting")
    
    if not all([token, name, greeting]):
        await update.message.reply_text(
            "<b>❌ Missing data. Please start again with /addmultibot.</b>",
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END
    
    # Create directory
    if not os.path.exists(MULTIBOTS_DIR):
        os.makedirs(MULTIBOTS_DIR)
    
    bot_dir = os.path.join(MULTIBOTS_DIR, name)
    os.makedirs(bot_dir, exist_ok=True)
    
    # Save greeting file
    greeting_path = os.path.join(bot_dir, "greetings.txt")
    with open(greeting_path, "w") as f:
        f.write(greeting)
    
    # Copy the main bot script to the directory
    main_script = __file__
    bot_script = os.path.join(bot_dir, "bot.py")
    shutil.copy(main_script, bot_script)
    
    # Create a modified bot script with the new token
    with open(bot_script, "r") as f:
        bot_code = f.read()
    
    # Replace the token placeholder
    bot_code = bot_code.replace('token("YOUR_BOT_TOKEN_HERE")', f'token("{token}")')
    
    with open(bot_script, "w") as f:
        f.write(bot_code)
    
    # Save to multibots registry
    multibots = load_multibots()
    
    # Start the bot in background using subprocess
    try:
        # Use Popen to start the bot in background without blocking
        process = subprocess.Popen(
            [sys.executable, bot_script],
            cwd=bot_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True  # Detach from parent process
        )
        
        # Give it a moment to start
        await asyncio.sleep(2)
        
        # Check if process is still running
        if process.poll() is None:
            # Store process info
            multibots[name] = {
                "token": token,
                "directory": bot_dir,
                "greeting_file": greeting_path,
                "pid": process.pid,
                "status": "running"
            }
            save_multibots(multibots)
            
            await update.message.reply_text(
                f"<b>✅ Multi-bot '{name}' deployed and started successfully!</b>\n\n"
                f"<b>Directory:</b> <code>{bot_dir}</code>\n"
                f"<b>Process ID:</b> <code>{process.pid}</code>\n"
                f"<b>Status:</b> <code>Running</code>\n\n"
                "<i>Bot is now running in the background!</i>",
                parse_mode=ParseMode.HTML
            )
        else:
            raise Exception("Process terminated immediately after start")
            
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        await update.message.reply_text(
            f"<b>⚠️ Bot deployed but failed to start automatically.</b>\n\n"
            f"<b>Error:</b> <code>{str(e)}</code>\n"
            f"<b>Directory:</b> <code>{bot_dir}</code>\n\n"
            "<i>You can start it manually from its directory.</i>",
            parse_mode=ParseMode.HTML
        )
        
        multibots[name] = {
            "token": token,
            "directory": bot_dir,
            "greeting_file": greeting_path,
            "status": "stopped"
        }
        save_multibots(multibots)
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END

async def rmmultibot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    
    multibots = load_multibots()
    if not multibots:
        await update.message.reply_text("<b>No multi-bots to remove.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    
    bot_list = list(multibots.keys())
    numbered = "\n".join([f"{i+1}. <code>{name}</code>" for i, name in enumerate(bot_list)])
    
    context.user_data["multibot_list"] = bot_list
    
    await update.message.reply_text(
        f"<b>Select a bot to remove (send number):</b>\n\n{numbered}",
        parse_mode=ParseMode.HTML
    )
    return ASK_SESSION_REMOVE  # Reusing state

async def rmmultibot_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_list = context.user_data.get("multibot_list", [])
    text = update.message.text.strip()
    
    try:
        idx = int(text) - 1
        if 0 <= idx < len(bot_list):
            bot_name = bot_list[idx]
        else:
            await update.message.reply_text("<b>Invalid number. Try again or /cancel.</b>", parse_mode=ParseMode.HTML)
            return ASK_SESSION_REMOVE
    except:
        await update.message.reply_text("<b>Please send a number.</b>", parse_mode=ParseMode.HTML)
        return ASK_SESSION_REMOVE
    
    # Remove the bot
    multibots = load_multibots()
    bot_data = multibots.get(bot_name)
    
    if bot_data:
        # Try to kill the process if running
        pid = bot_data.get("pid")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                await asyncio.sleep(1)
                # Force kill if still running
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass
        
        # Delete directory
        bot_dir = bot_data["directory"]
        if os.path.exists(bot_dir):
            shutil.rmtree(bot_dir)
        
        # Remove from registry
        multibots.pop(bot_name)
        save_multibots(multibots)
        
        await update.message.reply_text(
            f"<b>✅ Multi-bot '{bot_name}' removed successfully!</b>",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("<b>❌ Bot not found.</b>", parse_mode=ParseMode.HTML)
    
    return ConversationHandler.END

# --- Bonus Commands: Stop and Kill Multi-bots ---
async def stopmultibot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    
    multibots = load_multibots()
    if not multibots:
        await update.message.reply_text("<b>No multi-bots deployed.</b>", parse_mode=ParseMode.HTML)
        return
    
    bot_list = []
    for i, (name, data) in enumerate(multibots.items()):
        pid = data.get('pid', 'N/A')
        status = data.get('status', 'unknown')
        
        # Check if process is actually running
        if pid != 'N/A':
            try:
                os.kill(pid, 0)  # Check if process exists
                actual_status = "🟢 Running"
            except ProcessLookupError:
                actual_status = "🔴 Stopped"
                # Update status in registry
                data['status'] = 'stopped'
                data.pop('pid', None)
        else:
            actual_status = "🔴 Stopped"
        
        bot_list.append(f"{i+1}. <code>{name}</code> - {actual_status} (PID: {pid})")
    
    # Save updated statuses
    save_multibots(multibots)
    
    bot_list_str = "\n".join(bot_list)
    
    await update.message.reply_text(
        f"<b>📋 Running Multi-Bots:</b>\n\n{bot_list_str}\n\n"
        "<i>To stop a bot, use: /killbot &lt;number&gt;</i>",
        parse_mode=ParseMode.HTML
    )

async def killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    
    if not context.args:
        await update.message.reply_text("Usage: /killbot <number>")
        return
    
    try:
        idx = int(context.args[0]) - 1
        multibots = load_multibots()
        bot_list = list(multibots.keys())
        
        if 0 <= idx < len(bot_list):
            bot_name = bot_list[idx]
            bot_data = multibots[bot_name]
            pid = bot_data.get("pid")
            
            if pid:
                try:
                    # Try graceful termination first
                    os.kill(pid, signal.SIGTERM)
                    await asyncio.sleep(2)
                    
                    # Check if still running
                    try:
                        os.kill(pid, 0)
                        # Still running, force kill
                        os.kill(pid, signal.SIGKILL)
                        await update.message.reply_text(
                            f"<b>✅ Bot '{bot_name}' force-stopped (was not responding to graceful shutdown).</b>",
                            parse_mode=ParseMode.HTML
                        )
                    except ProcessLookupError:
                        # Process terminated gracefully
                        await update.message.reply_text(
                            f"<b>✅ Bot '{bot_name}' stopped successfully!</b>",
                            parse_mode=ParseMode.HTML
                        )
                    
                    # Update registry
                    bot_data["status"] = "stopped"
                    bot_data.pop("pid", None)
                    multibots[bot_name] = bot_data
                    save_multibots(multibots)
                    
                except ProcessLookupError:
                    await update.message.reply_text(
                        f"<b>⚠️ Process not found. Bot '{bot_name}' might have already stopped.</b>",
                        parse_mode=ParseMode.HTML
                    )
                    # Update registry
                    bot_data["status"] = "stopped"
                    bot_data.pop("pid", None)
                    multibots[bot_name] = bot_data
                    save_multibots(multibots)
            else:
                await update.message.reply_text("<b>No PID found for this bot. It's not running.</b>", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("<b>Invalid bot number.</b>", parse_mode=ParseMode.HTML)
    except ValueError:
        await update.message.reply_text("Please provide a valid number.")

# --- Check command ---
async def check_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    
    sessions = load_sessions()
    if not sessions:
        await update.message.reply_text("<b>No sessions found.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    
    session_list = list(sessions.keys())
    numbered = "\n".join([f"{i+1}. <code>{name}</code>" for i, name in enumerate(session_list)])
    
    context.user_data["session_list"] = session_list
    
    await update.message.reply_text(
        f"<b>Select a session to check (send number):</b>\n\n{numbered}",
        parse_mode=ParseMode.HTML
    )
    return CHECK_CHOOSE_SESSION

async def check_choose_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_list = context.user_data.get("session_list", [])
    text = update.message.text.strip()
    
    try:
        idx = int(text) - 1
        if 0 <= idx < len(session_list):
            session_name = session_list[idx]
        else:
            await update.message.reply_text("<b>Invalid number. Try again or /cancel.</b>", parse_mode=ParseMode.HTML)
            return CHECK_CHOOSE_SESSION
    except:
        await update.message.reply_text("<b>Please send a number.</b>", parse_mode=ParseMode.HTML)
        return CHECK_CHOOSE_SESSION
    
    # Get session string
    sessions = load_sessions()
    string_session = sessions.get(session_name)
    
    if not string_session:
        await update.message.reply_text("<b>❌ Session not found.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    
    await update.message.reply_text(f"<b>Checking groups for session '{session_name}'...</b>", parse_mode=ParseMode.HTML)
    
    try:
        async with Client(session_name, session_string=string_session) as client:
            owned_groups = []
            async for dialog in client.get_dialogs():
                if dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
                    # Check if user is owner/creator
                    try:
                        member = await client.get_chat_member(dialog.chat.id, "me")
                        if member.status in [enums.ChatMemberStatus.OWNER]:
                            owned_groups.append(dialog.chat.title)
                    except:
                        pass
            
            if owned_groups:
                groups_text = "\n".join([f"• {g}" for g in owned_groups])
                await update.message.reply_text(
                    f"<b>✅ Groups owned by '{session_name}':</b>\n\n{groups_text}\n\n"
                    f"<b>Total:</b> <code>{len(owned_groups)}</code>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await update.message.reply_text(
                    f"<b>No groups owned by session '{session_name}'.</b>",
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        logger.error(f"Error checking groups: {e}")
        await update.message.reply_text("<b>❌ Error checking groups.</b>", parse_mode=ParseMode.HTML)
    
    return ConversationHandler.END

# --- Sendadmin command ---
async def sendadmin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    
    await update.message.reply_text(
        "<b>📤 Send Session Strings to Admin</b>\n\n"
        "Send the username to send session strings to (e.g., <code>@username</code>):",
        parse_mode=ParseMode.HTML
    )
    return SENDADMIN_ASK_USERNAME

async def sendadmin_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    
    sessions = load_sessions()
    if not sessions:
        await update.message.reply_text("<b>No sessions found.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    
    await update.message.reply_text(f"<b>Sending session strings to {username}...</b>", parse_mode=ParseMode.HTML)
    
    success_count = 0
    failed_count = 0
    
    for session_name, string_session in sessions.items():
        try:
            async with Client(session_name, session_string=string_session) as client:
                # Get saved messages (chat with yourself)
                async for message in client.get_chat_history("me", limit=100):
                    if message.text and "pyrogram" in message.text.lower():
                        # Forward this message to the target username
                        try:
                            await client.send_message(username, message.text)
                            await asyncio.sleep(random.randint(2, 5))
                            success_count += 1
                            break
                        except Exception as e:
                            logger.error(f"Error sending to {username}: {e}")
                            failed_count += 1
                            break
        except Exception as e:
            logger.error(f"Error with session {session_name}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"<b>✅ Completed!</b>\n\n"
        f"<b>Sent:</b> <code>{success_count}</code>\n"
        f"<b>Failed:</b> <code>{failed_count}</code>",
        parse_mode=ParseMode.HTML
    )
    
    return ConversationHandler.END

# --- Ping command ---
async def ping_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    
    await update.message.reply_text(
        "<b>👋 Ping Command</b>\n\n"
        "Send the username to ping (e.g., <code>@username</code>):",
        parse_mode=ParseMode.HTML
    )
    return PING_ASK_USERNAME

async def ping_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    
    sessions = load_sessions()
    if not sessions:
        await update.message.reply_text("<b>No sessions found.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    
    await update.message.reply_text(f"<b>Pinging {username} from all sessions...</b>", parse_mode=ParseMode.HTML)
    
    success_count = 0
    failed_count = 0
    
    for session_name, string_session in sessions.items():
        try:
            async with Client(session_name, session_string=string_session) as client:
                await client.send_message(username, "hello")
                await asyncio.sleep(random.randint(2, 5))
                success_count += 1
        except Exception as e:
            logger.error(f"Error pinging from {session_name}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"<b>✅ Ping completed!</b>\n\n"
        f"<b>Success:</b> <code>{success_count}</code>\n"
        f"<b>Failed:</b> <code>{failed_count}</code>",
        parse_mode=ParseMode.HTML
    )
    
    return ConversationHandler.END

# --- Joinchat command (FIXED) ---
async def joinchat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    
    await update.message.reply_text(
        "<b>➕ Join Chat</b>\n\n"
        "Send the chat link or username (e.g., <code>https://t.me/chatname</code> or <code>@chatname</code>):",
        parse_mode=ParseMode.HTML
    )
    return JOINCHAT_ASK_LINK

async def joinchat_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    
    sessions = load_sessions()
    if not sessions:
        await update.message.reply_text("<b>No sessions found.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    
    await update.message.reply_text(f"<b>Joining chat from all sessions...</b>", parse_mode=ParseMode.HTML)
    
    success_count = 0
    failed_count = 0
    
    for session_name, string_session in sessions.items():
        try:
            async with Client(session_name, session_string=string_session) as client:
                try:
                    await client.join_chat(link)
                    await asyncio.sleep(random.randint(2, 5))
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error joining chat {link} from {session_name}: {e}")
                    failed_count += 1
        except Exception as e:
            logger.error(f"Error with session {session_name}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"<b>✅ Join completed!</b>\n\n"
        f"<b>Success:</b> <code>{success_count}</code>\n"
        f"<b>Failed:</b> <code>{failed_count}</code>",
        parse_mode=ParseMode.HTML
    )
    
    return ConversationHandler.END

# --- Leavechat command (FIXED) ---
async def leavechat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    
    await update.message.reply_text(
        "<b>➖ Leave Chat</b>\n\n"
        "Send the chat link or username (e.g., <code>https://t.me/chatname</code> or <code>@chatname</code>):",
        parse_mode=ParseMode.HTML
    )
    return LEAVECHAT_ASK_LINK

async def leavechat_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    
    sessions = load_sessions()
    if not sessions:
        await update.message.reply_text("<b>No sessions found.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    
    await update.message.reply_text(f"<b>Leaving chat from all sessions...</b>", parse_mode=ParseMode.HTML)
    
    success_count = 0
    failed_count = 0
    
    for session_name, string_session in sessions.items():
        try:
            async with Client(session_name, session_string=string_session) as client:
                # Resolve the chat first to get proper chat_id
                try:
                    chat = await client.get_chat(link)
                    await client.leave_chat(chat.id)
                    await asyncio.sleep(random.randint(2, 5))
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error leaving chat {link} from {session_name}: {e}")
                    failed_count += 1
        except Exception as e:
            logger.error(f"Error with session {session_name}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"<b>✅ Leave completed!</b>\n\n"
        f"<b>Success:</b> <code>{success_count}</code>\n"
        f"<b>Failed:</b> <code>{failed_count}</code>",
        parse_mode=ParseMode.HTML
    )
    
    return ConversationHandler.END

# --- Clearall command (MODIFIED - includes channels, shorter delays) ---
async def clearall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    
    sessions = load_sessions()
    if not sessions:
        await update.message.reply_text("<b>No sessions found.</b>", parse_mode=ParseMode.HTML)
        return
    
    await update.message.reply_text("<b>🧹 Clearing non-owned groups and channels from all sessions...</b>", parse_mode=ParseMode.HTML)
    
    total_left = 0
    
    for session_name, string_session in sessions.items():
        try:
            async with Client(session_name, session_string=string_session) as client:
                async for dialog in client.get_dialogs():
                    # Process both groups, supergroups, and channels
                    if dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
                        try:
                            member = await client.get_chat_member(dialog.chat.id, "me")
                            # Leave if not owner/admin
                            if member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                                await client.leave_chat(dialog.chat.id)
                                # Shorter delay: 1-3 seconds
                                await asyncio.sleep(random.uniform(1, 3))
                                total_left += 1
                                logger.info(f"Left {dialog.chat.title} from {session_name}")
                        except Exception as e:
                            logger.error(f"Error processing chat {dialog.chat.id} in {session_name}: {e}")
                            # Try to leave anyway if we can't check status
                            try:
                                await client.leave_chat(dialog.chat.id)
                                await asyncio.sleep(random.uniform(1, 3))
                                total_left += 1
                            except:
                                pass
        except Exception as e:
            logger.error(f"Error with session {session_name}: {e}")
    
    await update.message.reply_text(
        f"<b>✅ Clearall completed!</b>\n\n"
        f"<b>Total groups/channels left:</b> <code>{total_left}</code>",
        parse_mode=ParseMode.HTML
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cancel group creation if running for this user
    user_id = update.effective_user.id
    cancel_token = group_creation_tasks.get(user_id)
    if cancel_token:
        cancel_token["cancelled"] = True
        await update.message.reply_text("<b>❌ Cancelling group creation. Please wait...</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("<b>Cancelled.</b>", parse_mode=ParseMode.HTML)
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END

async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    await update.message.reply_text("<b>♻️ Restarting bot...</b>", parse_mode=ParseMode.HTML)
    logger.info("Bot restarting by admin command.")
    os.execv(sys.executable, [sys.executable] + sys.argv)

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    await update.message.reply_text("<b>🛑 Stopping bot process.</b>", parse_mode=ParseMode.HTML)
    logger.info("Bot stopped by admin command.")
    sys.exit(0)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    data = load_data()
    sessions = load_sessions()
    multibots = load_multibots()
    
    # Count running multibots
    running_count = 0
    for name, bot_data in multibots.items():
        pid = bot_data.get('pid')
        if pid:
            try:
                os.kill(pid, 0)
                running_count += 1
            except ProcessLookupError:
                pass
    
    text = (
        "<b>📊 Bot Stats:</b>\n"
        f"<b>Registered Groups:</b> <code>{len(data['groups'])}</code>\n"
        f"<b>Authorized Users:</b> <code>{len(data['authorized'])}</code>\n"
        f"<b>Sessions:</b> <code>{len(sessions)}</code>\n"
        f"<b>Multi-Bots:</b> <code>{len(multibots)}</code>\n"
        f"<b>Running Multi-Bots:</b> <code>{running_count}</code>\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    config = load_config()
    text = (
        "<b>ℹ️ Bot Info & Config:</b>\n"
        f"<b>DG:</b> <code>{config['DG']}</code>\n"
        f"<b>DM:</b> <code>{config['DM']}</code>\n"
        f"<b>Base Name:</b> <code>{config['base']}</code>\n"
        f"<b>Counter:</b> <code>{config['counter']}</code>\n"
        "<b>Super Admins:</b> <code>{}</code>\n".format(','.join(str(i) for i in SUPER_ADMIN_IDS))
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def getlogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return await reject(update, context)
    if os.path.exists(LOG_FILE):
        await update.message.reply_document(document=open(LOG_FILE, "rb"), caption="Bot Log File")
    else:
        await update.message.reply_text("No log file found.")

def main():
    # Set your bot token here!
    app = ApplicationBuilder().token("YOUR_BOT_TOKEN_HERE").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("config", config_command))
    app.add_handler(CommandHandler("addauth", add_auth))
    app.add_handler(CommandHandler("removeauth", remove_auth))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("checkgroups", check_groups))
    app.add_handler(CommandHandler("addsession", addsession))
    app.add_handler(CommandHandler("RG", RG))
    app.add_handler(CommandHandler("drg", drg))
    app.add_handler(CommandHandler("removegrps", removegrps))
    app.add_handler(CommandHandler("restart", restart_bot))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("getlogs", getlogs))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("multibot", multibot_menu))
    app.add_handler(CommandHandler("clearall", clearall))
    app.add_handler(CommandHandler("stopmultibot", stopmultibot))
    app.add_handler(CommandHandler("killbot", killbot))
    
    # Help menu callbacks
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^help_(basic|users|sessions|groups|multibot|advanced|stats|system)$"))
    app.add_handler(CallbackQueryHandler(help_main_callback, pattern="^help_main$"))
    app.add_handler(CallbackQueryHandler(multibot_callback, pattern="^mb_"))

    # Conversation handlers
    cgroups_conv = ConversationHandler(
        entry_points=[CommandHandler("cgroups", cgroups_start)],
        states={
            CHOOSE_CLIENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cgroups_choose_clients)],
            ASK_GROUP_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cgroups_ask_group_count)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(cgroups_conv)

    removesession_conv = ConversationHandler(
        entry_points=[CommandHandler("removesession", removesession_start)],
        states={
            ASK_SESSION_REMOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, removesession_choose)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(removesession_conv)
    
    addmultibot_conv = ConversationHandler(
        entry_points=[CommandHandler("addmultibot", addmultibot_start)],
        states={
            MULTIBOT_ASK_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, addmultibot_token)],
            MULTIBOT_ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, addmultibot_name)],
            MULTIBOT_ASK_GREETING: [MessageHandler(filters.Document.ALL, addmultibot_greeting)],
            MULTIBOT_DEPLOY: [CommandHandler("deploy", deploy_multibot)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(addmultibot_conv)
    
    rmmultibot_conv = ConversationHandler(
        entry_points=[CommandHandler("rmmultibot", rmmultibot_start)],
        states={
            ASK_SESSION_REMOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, rmmultibot_choose)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(rmmultibot_conv)
    
    check_conv = ConversationHandler(
        entry_points=[CommandHandler("check", check_start)],
        states={
            CHECK_CHOOSE_SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_choose_session)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(check_conv)
    
    sendadmin_conv = ConversationHandler(
        entry_points=[CommandHandler("sendadmin", sendadmin_start)],
        states={
            SENDADMIN_ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, sendadmin_username)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(sendadmin_conv)
    
    ping_conv = ConversationHandler(
        entry_points=[CommandHandler("ping", ping_start)],
        states={
            PING_ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ping_username)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(ping_conv)
    
    joinchat_conv = ConversationHandler(
        entry_points=[CommandHandler("joinchat", joinchat_start)],
        states={
            JOINCHAT_ASK_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, joinchat_link)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(joinchat_conv)
    
    leavechat_conv = ConversationHandler(
        entry_points=[CommandHandler("leavechat", leavechat_start)],
        states={
            LEAVECHAT_ASK_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, leavechat_link)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(leavechat_conv)

    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.ChatType.GROUPS,
        join_group
    ))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
