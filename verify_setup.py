"""Verification script for project setup."""

import json
from pathlib import Path


def verify_structure():
    """Verify project structure is created correctly."""
    print("Verifying project structure...")
    
    # Check directories
    required_dirs = [
        "src",
        "src/ingestion",
        "src/userbot",
        "src/parser",
        "src/verifier",
        "src/delivery",
        "tests"
    ]
    
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists() and path.is_dir():
            print(f"✓ Directory exists: {dir_path}")
        else:
            print(f"✗ Directory missing: {dir_path}")
            return False
    
    # Check files
    required_files = [
        "requirements.txt",
        "config.json",
        "config.py",
        "database.py",
        "README.md",
        ".env.example"
    ]
    
    for file_path in required_files:
        path = Path(file_path)
        if path.exists() and path.is_file():
            print(f"✓ File exists: {file_path}")
        else:
            print(f"✗ File missing: {file_path}")
            return False
    
    # Verify config.json is valid JSON
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        print(f"✓ config.json is valid JSON with {len(config)} keys")
    except Exception as e:
        print(f"✗ config.json is invalid: {e}")
        return False
    
    # Verify config.py can be imported
    try:
        import config as cfg
        print(f"✓ config.py can be imported")
        print(f"  - Loaded {len(cfg.config._data)} configuration keys")
    except Exception as e:
        print(f"✗ config.py import failed: {e}")
        return False
    
    print("\n✅ All verification checks passed!")
    return True


if __name__ == "__main__":
    success = verify_structure()
    exit(0 if success else 1)
