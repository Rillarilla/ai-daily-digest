
import os
import re
import json
import asyncio
import aiohttp
from datetime import datetime

class FeishuPublisher:
    """Publish content to Feishu (Lark) Cloud Documents."""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self):
        self.app_id = os.environ.get("FEISHU_APP_ID")
        self.app_secret = os.environ.get("FEISHU_APP_SECRET")
        self.folder_token = os.environ.get("FEISHU_FOLDER_TOKEN")
        self._tenant_access_token = None
        self._token_expiry = 0

    def is_configured(self) -> bool:
        """Check if Feishu credentials are present."""
        return bool(self.app_id and self.app_secret)

    async def _get_tenant_access_token(self) -> str:
        """Get or refresh tenant access token."""
        if self._tenant_access_token and datetime.now().timestamp() < self._token_expiry:
            return self._tenant_access_token

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    raise Exception(f"Feishu Auth Failed: {await response.text()}")

                data = await response.json()
                if data.get("code") != 0:
                    raise Exception(f"Feishu Auth Error: {data.get('msg')}")

                self._tenant_access_token = data["tenant_access_token"]
                # Expires in 2 hours, refresh slightly earlier
                self._token_expiry = datetime.now().timestamp() + data["expire"] - 300
                return self._tenant_access_token

    async def create_document(self, title: str) -> str:
        """Create a new Docx and return its document_id."""
        token = await self._get_tenant_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        # If folder_token is set, create in folder using Drive API
        if self.folder_token:
            url = f"{self.BASE_URL}/drive/v1/files/create_docx"
            payload = {
                "folder_token": self.folder_token,
                "title": title
            }
        else:
            # Create in root using Docx API
            url = f"{self.BASE_URL}/docx/v1/documents"
            payload = {
                "title": title
            }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                data = await response.json()
                if data.get("code") != 0:
                    raise Exception(f"Create Doc Error: {data.get('msg')}")

                # Drive API returns 'file_token' inside 'file', Docx API returns 'document_id' inside 'document'
                # Both are nested inside 'data'
                res_data = data.get("data", {})
                if "file" in res_data: # Drive API response
                    # For Docx created via Drive API, file_token == document_id
                    return res_data["file"]["token"]
                elif "document" in res_data: # Docx API response
                    return res_data["document"]["document_id"]
                else:
                    raise Exception(f"Unknown response format: {data}")

    def _markdown_to_blocks(self, content: str) -> list[dict]:
        """Parse simple Markdown to Feishu Block structure."""
        blocks = []
        lines = content.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Heading 1 (##) - Map to Heading 2 in Feishu for aesthetics
            if line.startswith("## "):
                text = line[3:]
                blocks.append(self._create_block(text, block_type=4)) # Heading 2

            # Heading 2 (###) - Map to Heading 3
            elif line.startswith("### "):
                text = line[4:]
                blocks.append(self._create_block(text, block_type=5)) # Heading 3

            # Bullet list
            elif line.startswith("- ") or line.startswith("* "):
                text = line[2:]
                blocks.append(self._create_block(text, block_type=12)) # Bullet

            # Numbered list (simple regex)
            elif re.match(r'^\d+\.\s', line):
                text = re.sub(r'^\d+\.\s', '', line)
                blocks.append(self._create_block(text, block_type=13)) # Numbered

            # Default text
            else:
                blocks.append(self._create_block(line, block_type=2)) # Text

        return blocks

    def _create_block(self, text: str, block_type: int) -> dict:
        """Create a block object with text elements handling links."""
        # Simple link parsing: [text](url)
        elements = []

        # Split by link pattern
        pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        parts = re.split(pattern, text)
        matches = re.findall(pattern, text)

        current_match_idx = 0

        for part in parts:
            if not part: continue

            # Check if this part matches a link text or url we just extracted
            # This is a bit tricky with re.split, let's just rebuild elements linearly
            pass

        # Better approach: Iterate and find links
        last_idx = 0
        for match in re.finditer(pattern, text):
            # Text before link
            if match.start() > last_idx:
                elements.append({
                    "text_element": {
                        "content": text[last_idx:match.start()]
                    }
                })

            # Link
            link_text = match.group(1)
            link_url = match.group(2)
            elements.append({
                "text_element": {
                    "content": link_text,
                    "text_run": {
                        "style": {
                            "link": {"url": link_url}
                        }
                    }
                }
            })

            last_idx = match.end()

        # Remaining text
        if last_idx < len(text):
            elements.append({
                "text_element": {
                    "content": text[last_idx:]
                }
            })

        # Default block structure
        block = {
            "block_type": block_type,
            "text": {
                "elements": elements
            }
        }

        # Adjust structure based on block type (Feishu API idiosyncrasies)
        # Actually for v1 API, the key is specific to block type name, e.g. "heading1", "ordered"
        # But wait, create_docx_block_children API uses a specific structure.
        # Let's double check the structure.

        # Re-checking documentation from memory/search:
        # POST /docx/v1/documents/:document_id/blocks/:block_id/children
        # Payload: {"children": [{ "block_type": 2, "text": { "elements": [...] } }]}
        # Actually keys are: "text", "heading1", "heading2", "bullet", "ordered"
        # Not generic "text" for all.

        type_mapping = {
            2: "text",
            3: "heading1",
            4: "heading2",
            5: "heading3",
            12: "bullet",
            13: "ordered"
        }

        type_name = type_mapping.get(block_type, "text")

        return {
            "block_type": block_type,
            type_name: {
                "elements": elements
            }
        }

    async def write_content(self, document_id: str, blocks: list[dict]):
        """Append blocks to the document."""
        token = await self._get_tenant_access_token()
        url = f"{self.BASE_URL}/docx/v1/documents/{document_id}/blocks/{document_id}/children"
        headers = {"Authorization": f"Bearer {token}"}

        # Feishu has limits on block creation (e.g. 50 at a time)
        batch_size = 50
        for i in range(0, len(blocks), batch_size):
            batch = blocks[i:i+batch_size]
            payload = {"children": batch}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    data = await response.json()
                    if data.get("code") != 0:
                        print(f"Error writing blocks batch {i}: {data.get('msg')}")

    async def publish(self, title: str, markdown_content: str) -> str:
        """Main method: Create doc and write content."""
        if not self.is_configured():
            print("Feishu publisher not configured (missing APP_ID/SECRET)")
            return None

        try:
            print(f"Creating Feishu document: {title}...")
            doc_id = await self.create_document(title)

            print("Parsing content...")
            blocks = self._markdown_to_blocks(markdown_content)

            print(f"Writing {len(blocks)} blocks to document...")
            await self.write_content(doc_id, blocks)

            doc_url = f"https://open.feishu.cn/docs/{doc_id}" # Or appropriate tenant domain
            print(f"✅ Published to Feishu: {doc_url}")
            return doc_url

        except Exception as e:
            print(f"❌ Feishu Publish Error: {e}")
            return None
