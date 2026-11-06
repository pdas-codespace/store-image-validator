"""Resolve approved Blob image references before any model or tool invocation."""
from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from copy import copy
from urllib.parse import quote, urlsplit

from agent_framework import AgentContext, Content, agent_middleware

from siv.images import MAX_BYTES, image_bytes_to_data_url


async def download_blob_image(filename: str) -> str:
    from azure.identity.aio import ManagedIdentityCredential, WorkloadIdentityCredential
    from azure.storage.blob.aio import BlobClient

    base = os.environ.get("MICROSOFT_EVAL_IMAGE_CONTAINER_URL", "")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path.strip("/") \
            or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("Set MICROSOFT_EVAL_IMAGE_CONTAINER_URL to an HTTPS container URL without credentials or query.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", filename):
        raise ValueError("blob_name must be a basename, not a path or URL.")
    if os.environ.get("AZURE_FEDERATED_TOKEN_FILE"):
        credential = WorkloadIdentityCredential()
    else:
        credential = ManagedIdentityCredential(client_id=os.environ.get("AZURE_CLIENT_ID"))
    async with credential, BlobClient.from_blob_url(
        f"{base.rstrip('/')}/{quote(filename, safe='')}", credential=credential
    ) as blob:
        stream = await blob.download_blob(offset=0, length=MAX_BYTES + 1)
        data = await stream.readall()
    return await asyncio.to_thread(image_bytes_to_data_url, data)


@agent_middleware
async def resolve_blob_images(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
    context.messages = list(context.messages)
    for index, message in enumerate(context.messages):
        if message.role != "user":
            continue
        try:
            request = json.loads(message.text)
        except json.JSONDecodeError:
            continue  # Ordinary chat and existing inline-image requests are unchanged.
        if not isinstance(request, dict) or not isinstance(request.get("images"), list):
            continue
        images = request["images"]
        if not any(isinstance(image, dict) and "blob_name" in image for image in images):
            continue
        if not 1 <= len(images) <= 5 or any(
            not isinstance(image, dict) or not isinstance(image.get("blob_name"), str) for image in images
        ):
            raise ValueError("Blob requests require one to five image entries, each with a blob_name.")
        contents = []
        for image in images:
            contents.append(Content.from_uri(await download_blob_image(image["blob_name"]), media_type="image/jpeg"))
        request["images"] = [{key: value for key, value in image.items() if key != "blob_name"} for image in images]
        resolved = copy(message)
        resolved.contents = [Content.from_text(json.dumps(request)),
                             *(content for content in message.contents if content.type != "text"), *contents]
        context.messages[index] = resolved
    await call_next()
