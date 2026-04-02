"""Utility to retrieve Telegram login code for userbot session creation."""

import asyncio
from pyrogram import Client
from pathlib import Path


async def get_login_code():
    """Interactive utility to get Telegram login code."""
    print("=" * 50)
    print("Telegram Userbot Session Creator")
    print("=" * 50)
    print()
    
    # Get API credentials
    print("Enter your Telegram API credentials:")
    print("(Get them from https://my.telegram.org/apps)")
    print()
    
    api_id = input("API ID: ").strip()
    api_hash = input("API Hash: ").strip()
    
    if not api_id or not api_hash:
        print("\nERROR: API ID and Hash are required")
        return
    
    # Get session name
    print()
    session_name = input("Session name (e.g., userbot1): ").strip()
    if not session_name:
        session_name = "userbot_session"
    
    # Create sessions directory
    sessions_dir = Path("sessions")
    sessions_dir.mkdir(exist_ok=True)
    
    session_path = sessions_dir / session_name
    
    print()
    print(f"Creating session: {session_path}.session")
    print()
    
    # Create client
    app = Client(
        str(session_path),
        api_id=int(api_id),
        api_hash=api_hash
    )
    
    try:
        print("Starting authentication...")
        print("You will receive a code via Telegram.")
        print()
        
        await app.start()
        
        me = await app.get_me()
        print()
        print("=" * 50)
        print("✓ Authentication successful!")
        print(f"✓ Logged in as: {me.first_name} (@{me.username})")
        print(f"✓ Session saved: {session_path}.session")
        print("=" * 50)
        print()
        print("You can now add this session to the system:")
        print(f"  Session file: {session_path}.session")
        print()
        
        await app.stop()
        
    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nAuthentication failed. Please try again.")


if __name__ == "__main__":
    asyncio.run(get_login_code())
