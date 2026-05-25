import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv
import bcrypt

load_dotenv(".env")
DATABASE_URL = os.getenv("DATABASE_URL")

async def check():
    engine = create_async_engine(DATABASE_URL, connect_args={"statement_cache_size": 0})
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT key_prefix, key_hash FROM api_keys WHERE key_prefix='lenai_sk_dev_tes';"))
        keys = result.fetchall()
        for k in keys:
            print("Found prefix:", k[0])
            raw_key = "lenai_sk_dev_test_key_12345678"
            match = bcrypt.checkpw(raw_key.encode(), k[1].encode())
            print("Matches lenai_sk_dev_test_key_12345678?", match)

asyncio.run(check())
