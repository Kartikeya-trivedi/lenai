import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv(".env")
DATABASE_URL = os.getenv("DATABASE_URL")

async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT key_prefix, name, is_active FROM api_keys;"))
        keys = result.fetchall()
        print("KEYS IN DB:")
        for k in keys:
            print(k)

asyncio.run(check())
