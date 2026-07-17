import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, BigInteger, Text, select, update, delete, func
from sqlalchemy.dialects.postgresql import insert
from app import config
import redis.asyncio as redis

Base = declarative_base()

# Models
class User(Base):
    __tablename__ = 'users'
    user_id = Column(BigInteger, primary_key=True)
    is_banned = Column(Boolean, default=False)

class UserActivity(Base):
    __tablename__ = 'user_activity'
    user_id = Column(BigInteger, primary_key=True)
    messages_count = Column(Integer, default=0)
    filters_asked_count = Column(Integer, default=0)

class Filter(Base):
    __tablename__ = 'filters'
    keyword = Column(String, primary_key=True)
    reply_text = Column(Text, nullable=False)
    file_id = Column(String, nullable=True)

class AutoIndex(Base):
    __tablename__ = 'auto_index'
    message_id = Column(BigInteger, primary_key=True)
    file_name = Column(Text)
    caption = Column(Text)
    message_url = Column(Text)


class Topic(Base):
    """Forum topic ↔ anime series (cover sticker + classic filter links)."""
    __tablename__ = 'topics'
    thread_id = Column(BigInteger, primary_key=True)  # message_thread_id / forum topic id
    title = Column(String, nullable=False)
    keyword = Column(String, nullable=False, index=True)
    cover_message_id = Column(BigInteger, nullable=True)
    cover_url = Column(Text, nullable=True)
    sticker_file_id = Column(String, nullable=True)
    photo_file_id = Column(String, nullable=True)  # bot photo file_id fallback
    description = Column(Text, nullable=True)
    gaco_url = Column(Text, nullable=True)
    download_url = Column(Text, nullable=True)


class Broadcast(Base):
    __tablename__ = 'broadcasts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(Text, nullable=False)
    sent_at = Column(String, nullable=False)
    sent_by = Column(BigInteger, nullable=False)

class BroadcastSentMessage(Base):
    __tablename__ = 'broadcast_sent_messages'
    broadcast_id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, primary_key=True)
    message_id = Column(BigInteger, nullable=False)

# Database Setup
engine = None
AsyncSessionLocal = None
redis_client = None

async def init_db():
    global engine, AsyncSessionLocal, redis_client
    
    db_url = config.DATABASE_URL
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set. Please set it to a valid Postgres URI.")
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    from sqlalchemy.pool import NullPool
    engine = create_async_engine(db_url, echo=False, poolclass=NullPool)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    if config.REDIS_URL:
        redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
        logging.info("Connected to Redis")

async def get_session():
    async with AsyncSessionLocal() as session:
        return session

# User Management
async def add_user(user_id: int):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = insert(User).values(user_id=user_id).on_conflict_do_nothing()
            await session.execute(stmt)
            # Init activity too
            stmt_act = insert(UserActivity).values(user_id=user_id).on_conflict_do_nothing()
            await session.execute(stmt_act)

async def is_user_banned(user_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User.is_banned).where(User.user_id == user_id))
        val = res.scalar()
        return bool(val)

async def ban_user(user_id: int, banned: bool):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(update(User).where(User.user_id == user_id).values(is_banned=banned))

async def get_all_users():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User.user_id))
        return [r[0] for r in res.fetchall()]

async def get_total_users():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(func.count(User.user_id)))
        return res.scalar()

# Filter Management
async def add_filter(keyword: str, reply_text: str, file_id: str = None, keep_existing_file_id: bool = False):
    keyword = keyword.lower().strip()
    if keep_existing_file_id and not file_id:
        existing = await get_filter(keyword)
        if existing and existing.get("file_id"):
            file_id = existing["file_id"]

    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = insert(Filter).values(keyword=keyword, reply_text=reply_text, file_id=file_id)
            if engine.dialect.name == 'postgresql':
                stmt = stmt.on_conflict_do_update(
                    index_elements=['keyword'],
                    set_=dict(reply_text=reply_text, file_id=file_id)
                )
            else:
                # SQLite fallback
                await session.execute(delete(Filter).where(Filter.keyword == keyword))
                stmt = insert(Filter).values(keyword=keyword, reply_text=reply_text, file_id=file_id)
            await session.execute(stmt)
    
    if redis_client:
        await redis_client.hset(f"filter:{keyword}", mapping={
            "reply_text": reply_text,
            "file_id": file_id or ""
        })

async def get_filter(keyword: str):
    keyword = keyword.lower().strip()
    if redis_client:
        cached = await redis_client.hgetall(f"filter:{keyword}")
        if cached:
            return {"reply_text": cached["reply_text"], "file_id": cached["file_id"] or None}

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Filter).where(Filter.keyword == keyword))
        row = res.scalar()
        if row:
            data = {"reply_text": row.reply_text, "file_id": row.file_id}
            if redis_client:
                await redis_client.hset(f"filter:{keyword}", mapping={
                    "reply_text": row.reply_text,
                    "file_id": row.file_id or ""
                })
            return data
    return None

async def delete_filter(keyword: str) -> bool:
    keyword = keyword.lower().strip()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            res = await session.execute(delete(Filter).where(Filter.keyword == keyword))
            success = res.rowcount > 0
    if redis_client:
        await redis_client.delete(f"filter:{keyword}")
    return success

async def get_all_filter_keywords():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Filter.keyword))
        return [r[0] for r in res.fetchall()]

# Activity Tracking
async def log_activity(user_id: int, type: str):
    """type: 'message' or 'filter'"""
    if user_id in config.ADMINS: return
    async with AsyncSessionLocal() as session:
        async with session.begin():
            if type == 'message':
                await session.execute(
                    update(UserActivity).where(UserActivity.user_id == user_id).values(messages_count=UserActivity.messages_count + 1)
                )
            elif type == 'filter':
                await session.execute(
                    update(UserActivity).where(UserActivity.user_id == user_id).values(filters_asked_count=UserActivity.filters_asked_count + 1)
                )

async def get_leaderboard(limit=10):
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(UserActivity).order_by((UserActivity.messages_count + UserActivity.filters_asked_count).desc()).limit(limit)
        )
        return res.scalars().all()

# Broadcasts
async def save_broadcast_and_get_id(text: str, sent_by: int) -> int:
    from datetime import datetime
    async with AsyncSessionLocal() as session:
        async with session.begin():
            b = Broadcast(text=text, sent_at=datetime.now().strftime("%Y-%m-%d %H:%M"), sent_by=sent_by)
            session.add(b)
            await session.flush()
            return b.id

async def save_sent_broadcast_message(broadcast_id: int, user_id: int, message_id: int):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = insert(BroadcastSentMessage).values(broadcast_id=broadcast_id, user_id=user_id, message_id=message_id)
            if engine.dialect.name == 'postgresql':
                stmt = stmt.on_conflict_do_update(
                    index_elements=['broadcast_id', 'user_id'],
                    set_=dict(message_id=message_id)
                )
            await session.execute(stmt)

async def get_broadcasts(page: int, per_page: int):
    async with AsyncSessionLocal() as session:
        total = await session.execute(select(func.count(Broadcast.id)))
        res = await session.execute(
            select(Broadcast).order_by(Broadcast.id.desc()).limit(per_page).offset(page * per_page)
        )
        return res.scalars().all(), total.scalar()

async def get_broadcast(bid: int):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Broadcast).where(Broadcast.id == bid))
        return res.scalar()

async def update_broadcast(bid: int, text: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(update(Broadcast).where(Broadcast.id == bid).values(text=text))

async def delete_broadcast(bid: int):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(delete(Broadcast).where(Broadcast.id == bid))
            await session.execute(delete(BroadcastSentMessage).where(BroadcastSentMessage.broadcast_id == bid))

async def get_sent_broadcast_messages(bid: int):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BroadcastSentMessage.user_id, BroadcastSentMessage.message_id).where(BroadcastSentMessage.broadcast_id == bid))
        return res.fetchall()

# Auto Index
async def add_auto_index(message_id: int, file_name: str, caption: str, message_url: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = insert(AutoIndex).values(message_id=message_id, file_name=file_name, caption=caption, message_url=message_url)
            if engine.dialect.name == 'postgresql':
                stmt = stmt.on_conflict_do_update(
                    index_elements=['message_id'],
                    set_=dict(file_name=file_name, caption=caption, message_url=message_url)
                )
            await session.execute(stmt)

async def search_auto_index(query: str):
    async with AsyncSessionLocal() as session:
        # Simple ILIKE search for PostgreSQL, LIKE for SQLite
        if engine.dialect.name == 'postgresql':
            res = await session.execute(
                select(AutoIndex).where(
                    (AutoIndex.file_name.ilike(f"%{query}%")) | (AutoIndex.caption.ilike(f"%{query}%"))
                ).limit(20)
            )
        else:
            res = await session.execute(
                select(AutoIndex).where(
                    (AutoIndex.file_name.like(f"%{query}%")) | (AutoIndex.caption.like(f"%{query}%"))
                ).limit(20)
            )
        rows = res.scalars().all()
        return [{"file_name": r.file_name, "url": r.message_url} for r in rows]


async def get_all_auto_index():
    """Return every auto_index row (used by the rule-based catalogue builder)."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(AutoIndex).order_by(AutoIndex.message_id.desc())
        )
        rows = res.scalars().all()
        return [
            {
                "message_id": r.message_id,
                "file_name": r.file_name or "",
                "caption": r.caption or "",
                "message_url": r.message_url or "",
                "url": r.message_url or "",
            }
            for r in rows
        ]


# Topics (forum covers)
def _topic_to_dict(r: Topic) -> dict:
    return {
        "thread_id": r.thread_id,
        "title": r.title,
        "keyword": r.keyword,
        "cover_message_id": r.cover_message_id,
        "cover_url": r.cover_url,
        "sticker_file_id": r.sticker_file_id,
        "photo_file_id": r.photo_file_id,
        "description": r.description,
        "gaco_url": r.gaco_url,
        "download_url": r.download_url,
    }


async def upsert_topic(
    thread_id: int,
    title: str,
    keyword: str,
    cover_message_id: int = None,
    cover_url: str = None,
    sticker_file_id: str = None,
    photo_file_id: str = None,
    description: str = None,
    gaco_url: str = None,
    download_url: str = None,
):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            existing = await session.execute(select(Topic).where(Topic.thread_id == thread_id))
            row = existing.scalar()
            if row:
                row.title = title or row.title
                row.keyword = keyword or row.keyword
                if cover_message_id is not None:
                    row.cover_message_id = cover_message_id
                if cover_url is not None:
                    row.cover_url = cover_url
                if sticker_file_id is not None:
                    row.sticker_file_id = sticker_file_id
                if photo_file_id is not None:
                    row.photo_file_id = photo_file_id
                if description is not None:
                    row.description = description
                if gaco_url is not None:
                    row.gaco_url = gaco_url
                if download_url is not None:
                    row.download_url = download_url
            else:
                session.add(Topic(
                    thread_id=thread_id,
                    title=title,
                    keyword=keyword,
                    cover_message_id=cover_message_id,
                    cover_url=cover_url,
                    sticker_file_id=sticker_file_id,
                    photo_file_id=photo_file_id,
                    description=description,
                    gaco_url=gaco_url,
                    download_url=download_url,
                ))


async def get_topic(thread_id: int):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Topic).where(Topic.thread_id == thread_id))
        row = res.scalar()
        return _topic_to_dict(row) if row else None


async def get_topic_by_keyword(keyword: str):
    keyword = keyword.lower().strip()
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Topic).where(Topic.keyword == keyword))
        row = res.scalar()
        return _topic_to_dict(row) if row else None


async def get_all_topics():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Topic).order_by(Topic.title.asc()))
        return [_topic_to_dict(r) for r in res.scalars().all()]


async def count_topics() -> int:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(func.count(Topic.thread_id)))
        return res.scalar() or 0
