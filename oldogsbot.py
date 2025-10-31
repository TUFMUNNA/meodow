import json
import os
import random
import asyncio
import re
import sys
import logging
from telegram import Update, Chat, Message
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from pyrogram import Client

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

def parse_greetings():
    if not os.path.exists(GREETINGS_FILE):
        return []
    with open(GREETINGS_FILE, "r") as f:
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
    text = (
        "<b>🛠️ <u>Bot Command Menu</u>:</b>\n"
        "\n"
        "<b>/start</b> — <i>Show welcome message</i>\n"
        "<b>/help</b> — <i>Show this help menu</i>\n"
        "<b>/config [option] [value]</b> — <i>Set config</i>\n"
        "<b>/addauth &lt;user_id&gt;</b> — <i>Authorize user</i>\n"
        "<b>/removeauth &lt;user_id&gt;</b> — <i>Remove authorized user</i>\n"
        "<b>/addsession &lt;name&gt; &lt;string_session&gt;</b> — <i>Add Pyrogram session</i>\n"
        "<b>/removesession</b> — <i>Remove Pyrogram session(s)</i>\n"
        "<b>/cgroups</b> — <i>Create groups via session(s)</i>\n"
        "<b>/broadcast &lt;msg&gt;</b> — <i>Broadcast to all groups</i> (or reply to a message/post and /broadcast to broadcast it)\n"
        "<b>/checkgroups</b> — <i>Show live/removed groups</i>\n"
        "<b>/removegrps</b> — <i>Remove all registered group data</i>\n"
        "<b>/drg</b> — <i>Deregister/remove this group (run in group)</i>\n"
        "<b>/stats</b> — <i>Show bot stats</i>\n"
        "<b>/info</b> — <i>Show config and info</i>\n"
        "<b>/getlogs</b> — <i>Send log file</i>\n"
        "<b>/restart</b> — <i>Restart the bot</i>\n"
        "<b>/stop</b> — <i>Stop the bot</i>\n"
        "<b>/cancel</b> — <i>Cancel current task</i>\n"
        "<b>/RG</b> — <i>Register group for broadcast (run in group)</i>\n"
        "\n"
        f"<i>⚡ You can run multiple sessions. Maximum concurrent sessions per batch: {MAX_MULTI_CLIENTS}.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

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
# For cancellation
group_creation_tasks = {}

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
        f"<b>Reply:</b> all (will be processed in batches of {MAX_MULTI_CLIENTS}), or list e.g. 1,3,5 or a single number."
    )
    context.user_data["session_list"] = session_list
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return CHOOSE_CLIENTS

async def cgroups_choose_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    session_list = context.user_data["session_list"]
    chosen_idxs = []
    if text == "all":
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

async def send_greetings_pyrogram(client, group_id, config):
    greetings = parse_greetings()
    for msg in greetings:
        try:
            await client.send_message(group_id, msg)
            await asyncio.sleep(random.randint(*config["DM"]))
        except Exception as e:
            logger.error(f"Error sending greeting: {e}")

async def create_supergroups(session_name, string_session, gcount, config, cancel_token):
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
                await send_greetings_pyrogram(client, chat.id, config)
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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cancel group creation if running for this user
    user_id = update.effective_user.id
    cancel_token = group_creation_tasks.get(user_id)
    if cancel_token:
        cancel_token["cancelled"] = True
        await update.message.reply_text("<b>❌ Cancelling group creation. Please wait...</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("<b>Cancelled.</b>", parse_mode=ParseMode.HTML)
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
    text = (
        "<b>📊 Bot Stats:</b>\n"
        f"<b>Registered Groups:</b> <code>{len(data['groups'])}</code>\n"
        f"<b>Authorized Users:</b> <code>{len(data['authorized'])}</code>\n"
        f"<b>Sessions:</b> <code>{len(sessions)}</code>\n"
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
    app = ApplicationBuilder().token("5764888114:REPLACE_WITH_YOUR_TOKEN").build()

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

    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.ChatType.GROUPS,
        join_group
    ))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()