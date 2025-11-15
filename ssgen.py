# ============================================
# TELEGRAM PYROGRAM SESSION STRING GENERATOR
# ============================================
#
# DESCRIPTION:
# This app generates a Pyrogram Session String and sends it to
# Saved Messages of your Telegram account
# Features:
# - Create new sessions
# - Delete existing sessions
# - List all sessions
# - Save exported session strings into sessions.json
# - Move .session files into a sessions/ directory
# - Interactive menu interface
#
# REQUIREMENTS:
# - Python 3.7+
# - Pyrogram library
# - TgCrypto library
#
# INSTALLATION:
# pip install pyrogram tgcrypto
#
# HOW TO GET TELEGRAM API KEY:
# Visit: https://my.telegram.org/apps
# Create an app and get your API ID and API HASH
#
# ============================================
# MAIN CODE (telegram_pyrogram_manager.py)
# ============================================

"""Generate Pyrogram Session String and send it to
Saved Messages of your Telegram account

requirements:
- Pyrogram
- TgCrypto

Get your Telegram API Key from:
https://my.telegram.org/apps
"""
import asyncio
import json
import os
import shutil
import time
from typing import Dict, Optional
from pyrogram import Client

SESSIONS_DIR = "sessions"
SESSIONS_JSON = "sessions.json"

# You can set these defaults here. If left as None / empty string,
# the script will require you to enter them manually.
# Example:
#   DEFAULT_API_ID = 123456
#   DEFAULT_API_HASH = "0123456789abcdef0123456789abcdef"
DEFAULT_API_ID: Optional[int] = None
DEFAULT_API_HASH: str = ""


def list_sessions():
    """List all .session files in the current directory and sessions/ directory"""
    files = []
    # look in current directory
    files.extend([f for f in os.listdir('.') if f.endswith('.session')])
    # also look in sessions directory if present
    if os.path.isdir(SESSIONS_DIR):
        for f in os.listdir(SESSIONS_DIR):
            if f.endswith('.session'):
                files.append(os.path.join(SESSIONS_DIR, f))
    return files


def delete_session(session_path):
    """Delete a session file (path or filename)."""
    if os.path.exists(session_path):
        os.remove(session_path)
        print(f"✓ Session '{session_path}' deleted successfully!")
        return True
    else:
        print(f"✗ Session '{session_path}' not found!")
        return False


def load_sessions_json() -> Dict[str, str]:
    """Load sessions.json if exists, otherwise return empty dict"""
    if os.path.exists(SESSIONS_JSON):
        try:
            with open(SESSIONS_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"✗ Failed to read {SESSIONS_JSON}: {e}")
            return {}
    return {}


def save_sessions_json(data: Dict[str, str]):
    """Write the sessions.json file atomically"""
    tmp = f"{SESSIONS_JSON}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SESSIONS_JSON)
        print(f"✓ {SESSIONS_JSON} updated.")
    except Exception as e:
        print(f"✗ Failed to write {SESSIONS_JSON}: {e}")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def ensure_sessions_dir():
    """Ensure the sessions directory exists"""
    if not os.path.isdir(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR, exist_ok=True)


def move_session_file_to_dir(session_name: str):
    """
    If a .session file with session_name exists in cwd, move it into sessions/ directory.
    session_name parameter may be given as the session name used when creating the Client.
    """
    # pyrogram creates a file named "<session_name>.session" when session_name is not ":memory:"
    filename = f"{session_name}.session"
    if os.path.exists(filename):
        ensure_sessions_dir()
        dest = os.path.join(SESSIONS_DIR, filename)
        # If destination already exists, append timestamp to avoid overwrite
        if os.path.exists(dest):
            base, ext = os.path.splitext(filename)
            dest = os.path.join(SESSIONS_DIR, f"{base}_{int(time.time())}{ext}")
        try:
            shutil.move(filename, dest)
            print(f"✓ Moved '{filename}' -> '{dest}'")
            return dest
        except Exception as e:
            print(f"✗ Failed to move session file: {e}")
            return None
    else:
        # nothing to move
        return None


async def create_new_session():
    """Create a new session, send session string to Saved Messages and optionally save to sessions.json and sessions/ dir"""
    print("\n=== Create New Session ===")

    # API ID prompt with default option
    if DEFAULT_API_ID is not None:
        api_id_prompt = f"API ID (press Enter to use default {DEFAULT_API_ID}): "
    else:
        api_id_prompt = "API ID: "

    api_id_input = input(api_id_prompt).strip()
    if not api_id_input:
        if DEFAULT_API_ID is not None:
            api_id = DEFAULT_API_ID
            print(f"Using default API ID: {api_id}")
        else:
            print("✗ API ID must be provided.")
            return
    else:
        try:
            api_id = int(api_id_input)
        except ValueError:
            print("✗ API ID must be an integer.")
            return

    # API HASH prompt with default option
    if DEFAULT_API_HASH:
        api_hash_prompt = "API HASH (press Enter to use default): "
    else:
        api_hash_prompt = "API HASH: "

    api_hash_input = input(api_hash_prompt).strip()
    if not api_hash_input:
        if DEFAULT_API_HASH:
            api_hash = DEFAULT_API_HASH
            print("Using default API HASH.")
        else:
            print("✗ API HASH must be provided.")
            return
    else:
        api_hash = api_hash_input

    session_name = input("Session name (or press Enter for in-memory session): ").strip()

    if not session_name:
        session_name = ":memory:"
        print("Using in-memory session (won't be saved to disk)")

    # start client and export session string
    try:
        async with Client(session_name, api_id=api_id, api_hash=api_hash) as app:
            session_string = await app.export_session_string()
            # send to Saved Messages
            await app.send_message(
                "me",
                "**Pyrogram Session String**:\n\n"
                f"`{session_string}`"
            )
            print(
                "✓ Done! Your Pyrogram session string has been sent to "
                "Saved Messages of your Telegram account!"
            )
    except Exception as e:
        print(f"✗ Failed to create client or export session string: {e}")
        return

    # Ask user if they want to save exported session into sessions.json
    # Changed behavior: Press Enter to save (default), type 'n' to skip.
    save_json = input("Press Enter to save this session string into sessions.json (type 'n' to skip): ").strip().lower()
    if save_json == "n":
        print("Skipped saving to sessions.json.")
    else:
        sessions_data = load_sessions_json()
        # Ask for the key/label to store under
        default_label = session_name if session_name != ":memory:" else f"session_{int(time.time())}"
        label = input(f"Enter label/key to store in {SESSIONS_JSON} (press Enter to use '{default_label}'): ").strip()
        if not label:
            label = default_label

        # If the label exists, confirm overwrite
        if label in sessions_data:
            confirm = input(f"Label '{label}' already exists in {SESSIONS_JSON}. Overwrite? (y/N): ").strip().lower()
            if confirm != "y":
                print("✗ Aborted saving to sessions.json.")
            else:
                sessions_data[label] = session_string
                save_sessions_json(sessions_data)
        else:
            sessions_data[label] = session_string
            save_sessions_json(sessions_data)

    # If a file-backed session was created, move it to sessions/ directory
    if session_name != ":memory:":
        moved = move_session_file_to_dir(session_name)
        if moved:
            print(f"✓ Session file saved to '{moved}'")
        else:
            # It's possible pyrogram didn't create a file (e.g. when using custom file name or weird error)
            print("Note: no .session file was found to move.")


async def main():
    while True:
        print("\n" + "=" * 50)
        print("TELEGRAM PYROGRAM SESSION MANAGER")
        print("=" * 50)
        print("1. Create new session")
        print("2. Delete existing session")
        print("3. List all sessions")
        print("4. Exit")
        print("=" * 50)

        choice = input("Select an option (1-4): ").strip()

        if choice == "1":
            await create_new_session()

        elif choice == "2":
            sessions = list_sessions()
            if not sessions:
                print("\n✗ No session files found!")
            else:
                print("\n=== Available Sessions ===")
                for i, session in enumerate(sessions, 1):
                    print(f"{i}. {session}")

                try:
                    session_choice = input("\nEnter session number to delete (or 'c' to cancel): ").strip()
                    if session_choice.lower() == "c":
                        continue
                    session_idx = int(session_choice) - 1
                    if 0 <= session_idx < len(sessions):
                        confirm = input(f"Are you sure you want to delete '{sessions[session_idx]}'? (y/n): ").strip().lower()
                        if confirm == "y":
                            delete_session(sessions[session_idx])
                    else:
                        print("✗ Invalid selection!")
                except ValueError:
                    print("✗ Invalid input!")

        elif choice == "3":
            sessions = list_sessions()
            if not sessions:
                print("\n✗ No session files found!")
            else:
                print("\n=== Available Sessions ===")
                for i, session in enumerate(sessions, 1):
                    print(f"{i}. {session}")

        elif choice == "4":
            print("\nGoodbye!")
            break

        else:
            print("\n✗ Invalid option! Please select 1-4.")


if __name__ == "__main__":
    asyncio.run(main())
