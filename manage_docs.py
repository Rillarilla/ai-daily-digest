#!/usr/bin/env python3
"""
Manage Feishu documents created by AI Daily Digest.

Usage:
    python manage_docs.py list          # List all documents
    python manage_docs.py delete <token> # Delete a specific document
    python manage_docs.py cleanup       # Interactive cleanup of old documents
"""

import asyncio
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from publishers.feishu_publisher import FeishuPublisher


async def list_documents():
    """List all documents created by the app."""
    publisher = FeishuPublisher()

    if not publisher.is_configured():
        print("❌ Feishu not configured")
        return

    print("\n📄 Fetching documents...\n")
    docs = await publisher.list_app_documents()

    if not docs:
        print("No documents found.")
        return

    print(f"Found {len(docs)} documents:\n")
    print(f"{'No.':<4} {'Title':<50} {'Token':<30} {'Created'}")
    print("-" * 100)

    for i, doc in enumerate(docs, 1):
        title = doc.get("name", "Untitled")[:48]
        token = doc.get("token", "")
        created = doc.get("created_time", 0)
        if created:
            created_str = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M")
        else:
            created_str = "Unknown"

        print(f"{i:<4} {title:<50} {token:<30} {created_str}")


async def delete_document(token: str):
    """Delete a specific document."""
    publisher = FeishuPublisher()

    if not publisher.is_configured():
        print("❌ Feishu not configured")
        return

    print(f"\n🗑️ Deleting document: {token}")
    success = await publisher.delete_document(token)

    if success:
        print("✅ Document deleted successfully")
    else:
        print("❌ Failed to delete document")


async def cleanup_interactive():
    """Interactive cleanup of documents."""
    publisher = FeishuPublisher()

    if not publisher.is_configured():
        print("❌ Feishu not configured")
        return

    print("\n📄 Fetching documents...\n")
    docs = await publisher.list_app_documents()

    if not docs:
        print("No documents found.")
        return

    print(f"Found {len(docs)} documents:\n")

    for i, doc in enumerate(docs, 1):
        title = doc.get("name", "Untitled")
        token = doc.get("token", "")
        created = doc.get("created_time", 0)
        if created:
            created_str = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M")
        else:
            created_str = "Unknown"

        print(f"\n{i}. {title}")
        print(f"   Token: {token}")
        print(f"   Created: {created_str}")

        choice = input("   Delete this document? [y/N/q(quit)]: ").strip().lower()

        if choice == 'q':
            print("\nCleanup cancelled.")
            break
        elif choice == 'y':
            await publisher.delete_document(token)

    print("\n✅ Cleanup complete")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()

    if command == "list":
        asyncio.run(list_documents())
    elif command == "delete":
        if len(sys.argv) < 3:
            print("Usage: python manage_docs.py delete <token>")
            return
        token = sys.argv[2]
        asyncio.run(delete_document(token))
    elif command == "cleanup":
        asyncio.run(cleanup_interactive())
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
