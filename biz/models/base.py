#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 数据库基类
"""

from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, DateTime, Text, JSON
from datetime import datetime
import uuid

Base = declarative_base()


class BaseModel(Base):
    """数据库模型基类"""

    __abstract__ = True

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    def to_dict(self):
        """转换为字典"""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result

    def update_from_dict(self, data: dict):
        """从字典更新属性"""
        for key, value in data.items():
            if hasattr(self, key) and key not in ["id", "created_at"]:
                setattr(self, key, value)
