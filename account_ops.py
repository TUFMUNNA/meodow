#!/usr/bin/env python3
"""
account_ops.py

Standalone account management bot module. This file is self-contained and runs its own
telegram.ext.Application (you can run it directly). It expects a sessions.json file
in the same directory (sessions.json must be a mapping: session_name -> session_string).

Features included:
- /changename   : change display names for selected sessions
- /changedps    : change profile pictures for selected sessions
- /change2step  : collection scaffold for 2-step password change (asks before executing)

Important:
- This file intentionally does NOT import anything from your main bot.
- Place this file in the same folder as sessions.json.
- Set BOT_TOKEN below (or use the BOT_TOKEN environment variable).
- Configure SUPER_ADMIN_IDS with your Telegram user ids.
- Install requirements: pip install python-telegram-bot pyrogram tgcrypto
- Run: python account_ops.py

Security note:
- Storing BOT_TOKEN and session strings in plain files is convenient but risky.
  Consider using environment variables and encrypted storage in production.

"""
import os
import json
import tempfile
import asyncio
import logging
from typing import List, Dict, Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)
from pyrogram import Client

# -------------------------
# Configuration - EDIT ME
# -------------------------
# You may optionally set BOT_TOKEN as env var BOT_TOKEN. If not set, replace the placeholder.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "REPLACE_WITH_YOUR_BOT_TOKEN")
# List of Telegram user IDs allowed to use these commands:
SUPER_ADMIN_IDS: List[int] = [7574652791, 5689759292]

# Sessions file (same folder)
SESSIONS_FILE = "sessions.json"
# Batch size consistent with your cgroups logic
MAX_MULTI_CLIENTS = 10

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# -------------------------
# Conversation states
# -------------------------
(
    SELECT_SESSIONS,
    CHANGENAME_MODE,
    CHANGENAME_INPUT,
    CHANGEDPS_MODE,
    CHANGEDPS_COLLECTING,
    CHANGE2STEP_COLLECT,
    CONFIRM_ACTION,
) = range(7)

# -------------------------
# Helpers
# -------------------------
def load_sessions() -> Dict[str, str]:
    if not os.path.exists(SESSIONS_FILE):
        return {}
    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sessions_atomic(sessions: Dict[str, str]) -> None:
    fd, tmp_path = tempfile.mkstemp(prefix="sessions_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tf:
            json.dump(sessions, tf, indent=2, ensure_ascii=False)
        os.replace(tmp_path, SESSIONS_FILE)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def format_session_list(session_list: List[str]) -> str:
    return "\n".join([f"{i+1}. <code>{name}</code>" for i, name in enumerate(session_list)])


def parse_selection(text: str, available_count: int) -> List[int]:
    text = text.strip().lower()
    if text == "all":
        return list(range(available_count))
    parts = [p.strip() for p in text.split(",") if p.strip()]
    idxs = []
    for p in parts:
        if p.isdigit():
            i = int(p) - 1
            if 0 <= i < available_count:
                idxs.append(i)
    seen = set()
    out = []
    for i in idxs:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def is_super_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMIN_IDS


def is_authorized(user_id: int) -> bool:
    return is_super_admin(user_id)


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("You are not authorized to use this command.")

# -------------------------
# Generic session selection
# -------------------------
async def select_sessions_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    sessions = load_sessions()
    if not sessions:
        await update.message.reply_text("<b>No sessions found. Add sessions.json entries first.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    session_list = list(sessions.keys())
    context.user_data["session_list"] = session_list
    msg = (
        "<b>Select session(s):</b>\n"
        f"{format_session_list(session_list)}\n\n"
        f"<b>Reply:</b> all (will be processed in batches of {MAX_MULTI_CLIENTS} if needed), or list e.g. 1,3,5 or a single number."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return SELECT_SESSIONS


async def select_sessions_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    session_list = context.user_data.get("session_list", [])
    chosen_idxs = parse_selection(text, len(session_list))
    if not chosen_idxs:
        await update.message.reply_text("<b>No valid client indices.</b>", parse_mode=ParseMode.HTML)
        return SELECT_SESSIONS
    context.user_data["chosen_idxs"] = chosen_idxs
    context.user_data["chosen_sessions"] = [session_list[i] for i in chosen_idxs]
    cmd = context.user_data.get("account_command")
    if cmd == "changename":
        await update.message.reply_text("<b>Do you want to provide names per session, or a single template for all?</b>\nReply: per OR template", parse_mode=ParseMode.HTML)
        return CHANGENAME_MODE
    elif cmd == "changedps":
        await update.message.reply_text("<b>Choose mode:</b>\nReply: one_per (upload N photos) OR apply_all (send one photo to be used for all selected sessions)", parse_mode=ParseMode.HTML)
        return CHANGEDPS_MODE
    elif cmd == "change2step":
        context.user_data["change2step_state"] = {"index": 0, "sub": "current", "results": {}}
        chosen_sessions = context.user_data["chosen_sessions"]
        first_name = chosen_sessions[0]
        await update.message.reply_text(f"<b>Change 2-step for session:</b> <code>{first_name}</code>\nReply with current password (or 'skip' to skip).", parse_mode=ParseMode.HTML)
        return CHANGE2STEP_COLLECT
    else:
        await update.message.reply_text("Unknown command flow.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

# -------------------------
# /changename flow
# -------------------------
async def changename_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    context.user_data["account_command"] = "changename"
    return await select_sessions_start(update, context)


async def changename_mode_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text not in ("per", "template"):
        await update.message.reply_text("<b>Reply 'per' or 'template'.</b>", parse_mode=ParseMode.HTML)
        return CHANGENAME_MODE
    context.user_data["changename_mode"] = text
    chosen = context.user_data.get("chosen_sessions", [])
    if text == "per":
        await update.message.reply_text(f"<b>Send {len(chosen)} names in one message, each name on its own line, in the same order as the sessions listed earlier.</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("<b>Send a single name template to apply to all sessions. You may use placeholders: {idx} and {session_name}.</b>", parse_mode=ParseMode.HTML)
    return CHANGENAME_INPUT


async def changename_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    mode = context.user_data.get("changename_mode")
    chosen_sessions = context.user_data.get("chosen_sessions", [])
    if mode == "per":
        names = [line.strip() for line in text.splitlines() if line.strip()]
        if len(names) != len(chosen_sessions):
            await update.message.reply_text(f"<b>Expected {len(chosen_sessions)} names, got {len(names)}. Please send names again (one per line).</b>", parse_mode=ParseMode.HTML)
            return CHANGENAME_INPUT
        context.user_data["changename_names"] = names
    else:
        template = text
        names = []
        for i, sname in enumerate(chosen_sessions, start=1):
            try:
                name = template.format(idx=i, session_name=sname)
            except Exception:
                name = template
            names.append(name)
        context.user_data["changename_names"] = names

    summary_lines = [f"<code>{s}</code> -> <b>{n}</b>" for s, n in zip(chosen_sessions, context.user_data["changename_names"])]
    await update.message.reply_text("<b>About to change the following:</b>\n" + "\n".join(summary_lines) + "\n\nReply 'yes' to proceed or 'cancel' to abort.", parse_mode=ParseMode.HTML)
    return CONFIRM_ACTION


async def changename_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text not in ("yes", "y"):
        await update.message.reply_text("<b>Cancelled.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    sessions_map = load_sessions()
    chosen_sessions = context.user_data["chosen_sessions"]
    names = context.user_data["changename_names"]
    chosen_idxs = context.user_data.get("chosen_idxs", [])
    results = []

    batches = [chosen_idxs[i:i+MAX_MULTI_CLIENTS] for i in range(0, len(chosen_idxs), MAX_MULTI_CLIENTS)]

    for batch in batches:
        async def do_one(idx):
            session_list = context.user_data["session_list"]
            session_name = session_list[idx]
            session_str = sessions_map.get(session_name)
            pos = chosen_idxs.index(idx)
            desired_name = names[pos]
            first = desired_name
            last = None
            if " " in desired_name:
                parts = desired_name.split(" ", 1)
                first, last = parts[0], parts[1]
            try:
                async with Client(session_name, session_string=session_str) as app:
                    await app.update_profile(first_name=first, last_name=last)
                return (session_name, True, "")
            except Exception as e:
                logger.exception("changename error")
                return (session_name, False, str(e))

        tasks = [do_one(idx) for idx in batch]
        res = await asyncio.gather(*tasks, return_exceptions=False)
        results.extend(res)

    ok = [f"{name}" for (name, success, _) in results if success]
    failed = [(name, err) for (name, success, err) in results if not success]
    msg = f"<b>Done.</b>\n<b>Successful:</b> <code>{len(ok)}</code>\n"
    if failed:
        msg += "<b>Failed:</b>\n" + "\n".join([f"<code>{n}</code>: {e}" for n, e in failed])
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

# -------------------------
# /changedps flow
# -------------------------
async def changedps_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    context.user_data["account_command"] = "changedps"
    return await select_sessions_start(update, context)


async def changedps_mode_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text not in ("one_per", "apply_all"):
        await update.message.reply_text("<b>Reply 'one_per' or 'apply_all'.</b>", parse_mode=ParseMode.HTML)
        return CHANGEDPS_MODE
    context.user_data["changedps_mode"] = text
    chosen = context.user_data.get("chosen_sessions", [])
    if text == "one_per":
        await update.message.reply_text(f"<b>Upload {len(chosen)} photos one by one. Send each photo as a separate message. When finished, send the word 'done'.</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("<b>Send a single photo that will be applied to all selected sessions.</b>", parse_mode=ParseMode.HTML)
    context.user_data["dp_photos"] = []
    return CHANGEDPS_COLLECTING


async def changedps_collect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        context.user_data.setdefault("dp_photos", []).append(file_id)
        await update.message.reply_text(f"<b>Photo received ({len(context.user_data['dp_photos'])}). Send next or 'done'.</b>", parse_mode=ParseMode.HTML)
        return CHANGEDPS_COLLECTING

    text = (update.message.text or "").strip().lower()
    if text == "done":
        if not context.user_data.get("dp_photos"):
            await update.message.reply_text("<b>No photos received. Cancelled.</b>", parse_mode=ParseMode.HTML)
            return ConversationHandler.END
        photos = context.user_data["dp_photos"]
        await update.message.reply_text(f"<b>Collected {len(photos)} photos. Reply 'yes' to apply, or 'cancel' to abort.</b>", parse_mode=ParseMode.HTML)
        return CONFIRM_ACTION

    await update.message.reply_text("<b>Please send a photo or 'done' when finished.</b>", parse_mode=ParseMode.HTML)
    return CHANGEDPS_COLLECTING


async def changedps_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text not in ("yes", "y"):
        await update.message.reply_text("<b>Cancelled.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    photos = context.user_data.get("dp_photos", [])
    mode = context.user_data.get("changedps_mode")
    chosen_sessions = context.user_data.get("chosen_sessions", [])
    sessions_map = load_sessions()

    if mode == "apply_all":
        if not photos:
            await update.message.reply_text("<b>No photo received. Cancelled.</b>", parse_mode=ParseMode.HTML)
            return ConversationHandler.END
        photo_map = {s: photos[0] for s in chosen_sessions}
    else:
        if len(photos) != len(chosen_sessions):
            await update.message.reply_text(f"<b>Expected {len(chosen_sessions)} photos, got {len(photos)}. Cancelled.</b>", parse_mode=ParseMode.HTML)
            return ConversationHandler.END
        photo_map = {s: photos[i] for i, s in enumerate(chosen_sessions)}

    results = []
    for sname in chosen_sessions:
        file_id = photo_map.get(sname)
        try:
            tf = tempfile.NamedTemporaryFile(prefix="dp_", suffix=".jpg", delete=False)
            temp_path = tf.name
            tf.close()
            file_obj = await context.bot.get_file(file_id)
            await file_obj.download_to_drive(custom_path=temp_path)
        except Exception as e:
            logger.exception("failed to download photo")
            results.append((sname, False, f"download error: {e}"))
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            continue

        session_str = sessions_map.get(sname)
        try:
            async with Client(sname, session_string=session_str) as app:
                await app.set_profile_photo(photo=temp_path)
            results.append((sname, True, ""))
        except Exception as e:
            logger.exception("pyrogram set_profile_photo failed")
            results.append((sname, False, str(e)))
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    ok = [n for (n, ok, _) in results if ok]
    failed = [(n, e) for (n, ok, e) in results if not ok]
    msg = f"<b>Profile picture update complete.</b>\n<b>Successful:</b> <code>{len(ok)}</code>\n"
    if failed:
        msg += "<b>Failed:</b>\n" + "\n".join([f"<code>{n}</code>: {e}" for n, e in failed])
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

# -------------------------
# /change2step scaffold
# -------------------------
async def change2step_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await reject(update, context)
    context.user_data["account_command"] = "change2step"
    return await select_sessions_start(update, context)


async def change2step_collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("change2step_state", {})
    idx = state.get("index", 0)
    chosen_sessions = context.user_data.get("chosen_sessions", [])
    if idx >= len(chosen_sessions):
        await update.message.reply_text("<b>All sessions processed. Reply 'yes' to execute password changes, or 'cancel'.</b>", parse_mode=ParseMode.HTML)
        return CONFIRM_ACTION

    session_name = chosen_sessions[idx]
    substate = state.get("sub", "current")
    text = (update.message.text or "").strip()
    if substate == "current":
        if text.lower() == "skip":
            state["results"][session_name] = {"skip": True}
            state["index"] = idx + 1
            state["sub"] = "current"
            context.user_data["change2step_state"] = state
            if state["index"] < len(chosen_sessions):
                next_s = chosen_sessions[state["index"]]
                await update.message.reply_text(f"<b>Session:</b> <code>{next_s}</code>\nReply with current password (or 'skip').", parse_mode=ParseMode.HTML)
                return CHANGE2STEP_COLLECT
            else:
                await update.message.reply_text("<b>All sessions processed. Reply 'yes' to execute password changes, or 'cancel'.</b>", parse_mode=ParseMode.HTML)
                return CONFIRM_ACTION
        state.setdefault("results", {})[session_name] = {"current": text}
        state["sub"] = "new"
        context.user_data["change2step_state"] = state
        await update.message.reply_text(f"<b>Session:</b> <code>{session_name}</code>\nReply with NEW password.", parse_mode=ParseMode.HTML)
        return CHANGE2STEP_COLLECT

    elif substate == "new":
        state["results"][session_name]["new"] = text
        state["sub"] = "retype"
        context.user_data["change2step_state"] = state
        await update.message.reply_text(f"<b>Session:</b> <code>{session_name}</code>\nRetype NEW password.", parse_mode=ParseMode.HTML)
        return CHANGE2STEP_COLLECT

    elif substate == "retype":
        new = state["results"][session_name].get("new")
        if text != new:
            state["sub"] = "new"
            await update.message.reply_text("<b>New password and retype did not match. Reply with NEW password again.</b>", parse_mode=ParseMode.HTML)
            return CHANGE2STEP_COLLECT
        state["index"] = idx + 1
        state["sub"] = "current"
        context.user_data["change2step_state"] = state
        if state["index"] < len(chosen_sessions):
            next_s = chosen_sessions[state["index"]]
            await update.message.reply_text(f"<b>Session:</b> <code>{next_s}</code>\nReply with current password (or 'skip').", parse_mode=ParseMode.HTML)
            return CHANGE2STEP_COLLECT
        else:
            await update.message.reply_text("<b>All sessions processed. Reply 'yes' to execute password changes, or 'cancel'.</b>", parse_mode=ParseMode.HTML)
            return CONFIRM_ACTION

    await update.message.reply_text("<b>Unexpected input. Cancelled.</b>", parse_mode=ParseMode.HTML)
    return ConversationHandler.END


async def change2step_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text not in ("yes", "y"):
        await update.message.reply_text("<b>Cancelled. No passwords changed.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    await update.message.reply_text(
        "<b>Important:</b> I have collected the passwords. Changing 2-step programmatically requires raw API calls and careful handling (may require email confirmation). "
        "Reply 'proceed-2step' to allow an attempted change now, or 'abort' to cancel and discard collected passwords.",
        parse_mode=ParseMode.HTML,
    )
    return CONFIRM_ACTION


async def change2step_execute_requested(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().lower()
    if not context.user_data.get("change2step_state"):
        return  # ignore unrelated messages

    if text == "abort":
        context.user_data.pop("change2step_state", None)
        await update.message.reply_text("<b>Aborted. Collected passwords discarded.</b>", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    if text != "proceed-2step":
        await update.message.reply_text("<b>Unknown command. Reply 'proceed-2step' to attempt changes or 'abort' to cancel.</b>", parse_mode=ParseMode.HTML)
        return CONFIRM_ACTION

    state = context.user_data.get("change2step_state", {})
    collected = state.get("results", {})
    sessions_map = load_sessions()
    chosen_sessions = context.user_data.get("chosen_sessions", [])
    results = []

    for sname in chosen_sessions:
        info = collected.get(sname)
        if not info or info.get("skip"):
            results.append((sname, "skipped"))
            continue
        current = info.get("current")
        new = info.get("new")
        try:
            session_str = sessions_map.get(sname)
            async with Client(sname, session_string=session_str) as app:
                from pyrogram.raw import functions, types
                pwd = await app.invoke(functions.account.GetPasswordRequest())
                if not isinstance(pwd, types.account.Password):
                    results.append((sname, "no-password-set"))
                    continue
                results.append((sname, "pending-implementation - SRP required"))
        except Exception as e:
            logger.exception("change2step execution error")
            results.append((sname, f"error: {e}"))

    msg_lines = [f"<code>{s}</code>: {r}" for s, r in results]
    await update.message.reply_text("<b>Execution attempted (summary):</b>\n" + "\n".join(msg_lines), parse_mode=ParseMode.HTML)
    await update.message.reply_text("<i>Note: actual SRP-based password change is not fully implemented here. Reply 'implement-2step' if you want me to add the SRP flow and run it after you review the code.</i>", parse_mode=ParseMode.HTML)
    return ConversationHandler.END

# -------------------------
# Fallback / cancel
# -------------------------
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

# -------------------------
# Register handlers
# -------------------------
def register_account_handlers(app):
    # changename conv
    changename_conv = ConversationHandler(
        entry_points=[CommandHandler("changename", changename_start)],
        states={
            SELECT_SESSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_sessions_choice)],
            CHANGENAME_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, changename_mode_choice)],
            CHANGENAME_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, changename_input)],
            CONFIRM_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, changename_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True,
    )
    app.add_handler(changename_conv)

    # changedps conv
    changedps_conv = ConversationHandler(
        entry_points=[CommandHandler("changedps", changedps_start)],
        states={
            SELECT_SESSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_sessions_choice)],
            CHANGEDPS_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, changedps_mode_choice)],
            CHANGEDPS_COLLECTING: [
                MessageHandler(filters.PHOTO, changedps_collect_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, changedps_collect_photo),
            ],
            CONFIRM_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, changedps_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True,
    )
    app.add_handler(changedps_conv)

    # change2step conv
    change2step_conv = ConversationHandler(
        entry_points=[CommandHandler("change2step", change2step_start)],
        states={
            SELECT_SESSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_sessions_choice)],
            CHANGE2STEP_COLLECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, change2step_collect)],
            CONFIRM_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, change2step_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True,
    )
    app.add_handler(change2step_conv)

    # catch proceed/abort messages for 2step
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, change2step_execute_requested))

    logger.info("Registered account handlers.")


# -------------------------
# Run as a standalone bot
# -------------------------
def main():
    if BOT_TOKEN == "REPLACE_WITH_YOUR_BOT_TOKEN":
        logger.error("BOT_TOKEN is not set. Edit account_ops.py or set BOT_TOKEN env var.")
        print("Please set BOT_TOKEN in the file or as environment variable BOT_TOKEN.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    register_account_handlers(app)
    logger.info("Account ops bot running. Super admins: %s", SUPER_ADMIN_IDS)
    app.run_polling()


if __name__ == "__main__":
    main()
