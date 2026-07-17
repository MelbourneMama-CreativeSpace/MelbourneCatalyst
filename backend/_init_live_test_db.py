"""One-off script: create the trends schema in a local SQLite file for live
demo/testing (no Supabase/Docker available in this environment).
Not part of the app — delete after use.
"""

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from app.db import models  # noqa: F401 — registers Trend on Base.metadata
from app.db.session import Base


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///./live_test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("schema created")


if __name__ == "__main__":
    asyncio.run(main())
