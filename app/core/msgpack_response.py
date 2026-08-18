from typing import Any

import msgpack
from fastapi import Response


class MsgPackResponse(Response):
    """FastAPI Response class for MessagePack binary serialization.

    Serializes Python dictionaries or Pydantic models directly into MessagePack bytes
    with media_type="application/x-msgpack".
    """

    media_type = "application/x-msgpack"

    def render(self, content: Any) -> bytes:
        if isinstance(content, bytes):
            return content
        return msgpack.packb(content, use_bin_type=True)
