from __future__ import annotations

from suitcode.core.models import FileInfo
from suitcode.core.models.nodes import StrictModel


class OwnedNodeInfo(StrictModel):
    id: str
    kind: str
    name: str


class FileOwnerInfo(StrictModel):
    file_info: FileInfo
    owner: OwnedNodeInfo
