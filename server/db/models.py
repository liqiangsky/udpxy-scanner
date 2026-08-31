from datetime import datetime
from typing import Optional, Union, List

from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# =============================================================================
# SQLAlchemy ORM 基类
# =============================================================================

class Base(DeclarativeBase):
    pass


# =============================================================================
# SQLAlchemy ORM 模型（列名与现有数据库保持兼容）
# =============================================================================

class Parameter(Base):
    """全局参数表（key-value）"""
    __tablename__ = "parameter"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, default="")


class Config(Base):
    """扫描配置表"""
    __tablename__ = "config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    data_source: Mapped[str] = mapped_column("dataSource", String, nullable=False)
    template_region: Mapped[str] = mapped_column("templateRegion", String, default="")
    template_operator: Mapped[str] = mapped_column("templateOperator", String, default="")
    template_target_name: Mapped[str] = mapped_column("templateTargetName", String, default="")
    template_target_address: Mapped[str] = mapped_column("templateTargetAddress", String, default="")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[int] = mapped_column("createdAt", Integer, default=0)
    updated_at: Mapped[int] = mapped_column("updatedAt", Integer, default=0)


class Subscription(Base):
    """API 订阅表"""
    __tablename__ = "subscription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    uid: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, default="")
    type: Mapped[str] = mapped_column(String, default="api")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    fetch_cron: Mapped[str] = mapped_column("fetchCron", String, default="")
    last_fetch_at: Mapped[Optional[int]] = mapped_column("lastFetchAt", Integer, default=None)
    created_at: Mapped[int] = mapped_column("createdAt", Integer, default=0)
    updated_at: Mapped[int] = mapped_column("updatedAt", Integer, default=0)


class Cache(Base):
    """数据缓存表（游离主机）"""
    __tablename__ = "cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column("sourceType", String, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    geo_region: Mapped[str] = mapped_column("geoRegion", String, default="")
    geo_operator: Mapped[str] = mapped_column("geoOperator", String, default="")
    active: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column("createdAt", Integer, default=0)
    updated_at: Mapped[Optional[int]] = mapped_column("updatedAt", Integer, default=None)


class Host(Base):
    """主机池表"""
    __tablename__ = "host"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host: Mapped[str] = mapped_column(String, nullable=False)
    ip: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column("sourceType", String, default="")
    source_name: Mapped[str] = mapped_column("sourceName", String, default="")
    region: Mapped[str] = mapped_column(String, nullable=False)
    operator: Mapped[str] = mapped_column(String, nullable=False)
    geo_region: Mapped[str] = mapped_column("geoRegion", String, default="")
    geo_operator: Mapped[str] = mapped_column("geoOperator", String, default="")
    delay: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str] = mapped_column(String, nullable=False)
    channel_name: Mapped[str] = mapped_column("channelName", String, nullable=False)
    created_at: Mapped[int] = mapped_column("createdAt", Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column("updatedAt", Integer, nullable=False)


class Notification(Base):
    """通知消息表"""
    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String, nullable=False, default="info")
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="")
    read: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column("createdAt", Integer, nullable=False)


# =============================================================================
# Pydantic 请求/响应模型
# =============================================================================

class GlobalSettingsUpdate(BaseModel):
    concurrency: int = Field(64, ge=1, le=500)
    timeout: int = Field(2000, ge=200, le=10000)
    config_delay: int = Field(3, ge=0, le=300)
    scan_cron: str = ""
    janitor_cron: str = ""
    push_api_key: str = ""


class ConfigCreateOrUpdate(BaseModel):
    name: str
    region: str
    operator: str
    target_name: str = Field(alias="targetName")
    target_address: str = Field(alias="targetAddress")
    data_source: str = Field(alias="dataSource")
    enabled: Optional[bool] = True

    model_config = {"populate_by_name": True}


class SourceCacheDelete(BaseModel):
    ids: Optional[Union[int, List[int]]] = None
    source_types: Optional[Union[str, List[str]]] = Field(None, alias="sourceTypes")

    model_config = {"populate_by_name": True}


class ApiSubscriptionCreate(BaseModel):
    name: str
    uid: str
    url: Optional[str] = ""
    type: str = "api"
    enabled: bool = True
    fetch_cron: str = Field("", alias="fetchCron")

    model_config = {"populate_by_name": True}
