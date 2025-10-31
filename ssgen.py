#!/usr/bin/env python3
"""
ssgen.py - Pyrogram Session String Generator (CLI)

Standalone terminal tool to create Pyrogram session strings one-by-one
and save them into sessions.json in the same directory (same format expected by account_ops.py).

Usage:
- Place this file next to sessions.json (or it will create sessions.json).
- Run: python ssgen.py
- Follow the interactive prompts (API ID, API HASH, phone, code).
- After successful login you can Save / Skip / Exit. Saved sessions are written into sessions.json.

Requirements:
  pip install pyrogram tgcrypto

Security:
- This script uses an in-memory Pyrogram client and only saves the exported session string.
- It does not save or log codes / passwords.

"""
import asyncio
import json
import os
import sys
import tempfile
from typing import Dict, Optional

from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, ApiIdInvalid, PhoneNumberInvalid

SESSIONS_JSON = "sessions.json"


def load_saved_sessions() -> Dict[str, str]:
    if not os.path.exists(SESSIONS_JSON):
        return {}
    with open(SESSIONS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sessions_atomic(sessions: Dict[str, str]) -> None:
    fd, tmp_path = tempfile.mkstemp(prefix="sessions_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tf:
            json.dump(sessions, tf, indent=2, ensure_ascii=False)
        os.replace(tmp_path, SESSIONS_JSON)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def list_sessions_cli():
    sessions = load_saved_sessions()
    if not sessions:
        print("\n✗ No saved sessions (sessions.json is empty or missing).")
        return
    print("\n=== Saved sessions ===")
    for i, name in enumerate(sessions.keys(), 1):
        print(f"{i}. {name}")


def delete_session_cli():
    sessions = load_saved_sessions()
    if not sessions:
        print("\n✗ No saved sessions to delete.")
        return
    names = list(sessions.keys())
    print("\n=== Saved sessions ===")
    for i, name in enumerate(names, 1):
        print(f"{i}. {name}")
    choice = input("\nEnter session number to delete (or 'c' to cancel): ").strip()
    if choice.lower() == "c":
        print("Cancelled.")
        return
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(names):
            name = names[idx]
            confirm = input(f"Delete session '{name}' from {SESSIONS_JSON}? (y/N): ").strip().lower()
            if confirm == "y":
                sessions.pop(name, None)
                save_sessions_atomic(sessions)
                print(f"✓ Deleted '{name}'.")
            else:
                print("Cancelled.")
        else:
            print("✗ Invalid selection.")
    except ValueError:
        print("✗ Invalid input.")


async def create_session_interactive(api_id: int, api_hash: str, phone: str) -> Optional[str]:
    phone = phone.strip()
    if not phone:
        print("✗ Empty phone number.")
        return None

    try:
        async with Client(":memory:", api_id=api_id, api_hash=api_hash) as app:
            try:
                sent = await app.send_code(phone)
            except PhoneNumberInvalid:
                print("✗ Phone number is invalid.")
                return None
            except ApiIdInvalid:
                print("✗ api_id/api_hash invalid.")
                return None
            except Exception as e:
                print(f"✗ Error sending code: {e}")
                return None

            code = input("Enter the code you received (or 'c' to cancel): ").strip()
            if code.lower() == "c":
                print("Cancelled by user.")
                return None

            try:
                await app.sign_in(phone_number=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeeded:
                pw = input("Two-step verification password required. Enter password (or 'c' to cancel): ")
                if pw.strip().lower() == "c":
                    print("Cancelled by user.")
                    return None
                try:
                    await app.check_password(pw)
                except Exception as e:
                    print(f"✗ Password check failed: {e}")
                    return None
            except PhoneCodeInvalid:
                print("✗ The code you entered is invalid.")
                return None
            except PhoneCodeExpired:
                print("✗ The code you entered is expired.")
                return None
            except Exception as e:
                print(f"✗ Sign-in failed: {e}")
                return None

            try:
                session_str = await app.export_session_string()
                return session_str
            except Exception as e:
                print(f"✗ Failed to export session string: {e}")
                return None
    except Exception as e:
        print(f"✗ Pyrogram client error: {e}")
        return None


async def flow_create_single():
    print("\n=== Create a new session ===")
    try:
        api_id = int(input("API ID: ").strip())
    except ValueError:
        print("✗ API ID must be a number.")
        return
    api_hash = input("API HASH: ").strip()
    phone = input("Phone number (in international format, e.g. +1234567890): ").strip()
    if not phone:
        print("✗ Phone required.")
        return

    print("\nRequesting code and signing in...")
    session_str = await create_session_interactive(api_id, api_hash, phone)
    if not session_str:
        print("✗ Session creation failed or cancelled.")
        return

    print("\n✓ Session string generated.")
    default_name = phone.replace("+", "")
    name = input(f"Session name to save as (default: {default_name}): ").strip()
    if not name:
        name = default_name

    sessions = load_saved_sessions()
    if name in sessions:
        confirm = input(f"A session named '{name}' already exists. Overwrite? (y/N): ").strip().lower()
        if confirm != "y":
            print("Skipped saving.")
            return

    sessions[name] = session_str
    save_sessions_atomic(sessions)
    print(f"✓ Saved session '{name}' into {SESSIONS_JSON}.")


async def flow_from_file():
    print("\n=== Create sessions from a phone list file ===")
    try:
        api_id = int(input("API ID: ").strip())
    except ValueError:
        print("✗ API ID must be a number.")
        return
    api_hash = input("API HASH: ").strip()

    path = input("Path to phone list file (one phone per line, international format): ").strip()
    if not os.path.exists(path):
        print("✗ File not found.")
        return

    with open(path, "r", encoding="utf-8") as f:
        phones = [line.strip() for line in f if line.strip()]

    if not phones:
        print("✗ No phone numbers found in file.")
        return

    print(f"\nFound {len(phones)} numbers. Processing one-by-one. For each generated session you'll be asked: Save / Skip / Exit.")
    sessions = load_saved_sessions()

    for i, phone in enumerate(phones, start=1):
        print("\n" + "-" * 50)
        print(f"({i}/{len(phones)}) Processing: {phone}")
        session_str = await create_session_interactive(api_id, api_hash, phone)
        if not session_str:
            print("Session creation failed or cancelled for this number.")
            action = input("Type 's' to skip to next, or 'x' to exit: ").strip().lower()
            if action == "x":
                print("Exiting batch process.")
                break
            else:
                continue

        print("\n✓ Session generated.")
        default_name = phone.replace("+", "")
        while True:
            action = input("Choose: [1] Save  [2] Skip  [3] Exit   (enter 1/2/3) : ").strip()
            if action == "1":
                name = input(f"Session name to save as (default: {default_name}): ").strip()
                if not name:
                    name = default_name
                if name in sessions:
                    confirm = input(f"Session '{name}' exists. Overwrite? (y/N): ").strip().lower()
                    if confirm != "y":
                        print("Not overwritten. Choose another name or skip.")
                        continue
                sessions[name] = session_str
                save_sessions_atomic(sessions)
                print(f"✓ Saved session '{name}' into {SESSIONS_JSON}.")
                break
            elif action == "2":
                print("Skipped saving this session.")
                break
            elif action == "3":
                print("Exiting batch processing by user request.")
                return
            else:
                print("Invalid choice. Enter 1, 2, or 3.")

    print("\nBatch processing finished.")


def main_menu():
    loop = asyncio.get_event_loop()
    while True:
        print("\n" + "=" * 60)
        print("Pyrogram Session String Generator - ssgen")
        print("=" * 60)
        print("1. Create a new session (interactive)")
        print("2. Create sessions from phone list file (one-by-one, interactive save/skip)")
        print("3. List saved sessions (sessions.json)")
        print("4. Delete saved session (from sessions.json)")
        print("5. Exit")
        print("=" * 60)
        choice = input("Select an option (1-5): ").strip()
        if choice == "1":
            loop.run_until_complete(flow_create_single())
        elif choice == "2":
            loop.run_until_complete(flow_from_file())
        elif choice == "3":
            list_sessions_cli()
        elif choice == "4":
            delete_session_cli()
        elif choice == "5":
            print("Goodbye.")
            return
        else:
            print("✗ Invalid option. Choose 1-5.")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nInterrupted. Exiting.")
        sys.exit(0)
