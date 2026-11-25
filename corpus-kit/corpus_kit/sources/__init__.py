from .base import CollectedItem, SourceAdapter
from .crawl import CrawlSource
from .local_import import LocalImportSource

ADAPTERS: dict[str, type] = {
    "local": LocalImportSource,
    "crawl": CrawlSource,
}

__all__ = [
    "ADAPTERS",
    "CollectedItem",
    "CrawlSource",
    "LocalImportSource",
    "SourceAdapter",
]
