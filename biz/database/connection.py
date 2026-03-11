#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 数据库连接管理
"""

import os
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from ..models.base import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # 默认数据库路径：项目根目录/data/app.db
            project_root = Path(__file__).parent.parent.parent
            db_dir = project_root / "data"
            db_dir.mkdir(exist_ok=True)
            db_path = db_dir / "app.db"

        self.db_path = str(db_path)
        self.db_url = f"sqlite+aiosqlite:///{self.db_path}"

        # 创建异步引擎
        self.engine = create_async_engine(
            self.db_url,
            echo=False,  # 设为True可以看到SQL日志
            poolclass=StaticPool,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
        )

        # 创建会话工厂
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info(f"数据库管理器初始化完成: {self.db_path}")

    async def create_tables(self):
        """创建所有表"""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                if self.engine.url.get_backend_name() == "sqlite":
                    result = await conn.exec_driver_sql(
                        "PRAGMA table_info(media_tasks)"
                    )
                    columns = {row[1] for row in result}
                    if "cover" not in columns:
                        await conn.exec_driver_sql(
                            "ALTER TABLE media_tasks ADD COLUMN cover VARCHAR(500)"
                        )
            logger.info("数据库表创建成功")
        except Exception as e:
            logger.error(f"创建数据库表失败: {e}")
            raise

    async def drop_tables(self):
        """删除所有表（谨慎使用）"""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            logger.info("数据库表删除成功")
        except Exception as e:
            logger.error(f"删除数据库表失败: {e}")
            raise

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """获取数据库会话（上下文管理器）"""
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self):
        """关闭数据库连接"""
        await self.engine.dispose()
        logger.info("数据库连接已关闭")


# 全局数据库管理器实例
_db_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """获取数据库管理器实例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（FastAPI依赖注入用）"""
    db_manager = get_database_manager()
    async with db_manager.get_session() as session:
        yield session


async def init_database():
    """初始化数据库"""
    db_manager = get_database_manager()
    await db_manager.create_tables()
    logger.info("数据库初始化完成")


async def close_database():
    """关闭数据库"""
    global _db_manager
    if _db_manager:
        await _db_manager.close()
        _db_manager = None
