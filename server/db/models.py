from typing import Optional, Union, List

from pydantic import BaseModel, Field
from sqlalchemy import Integer, String, UniqueConstraint
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
    data_source: Mapped[str] = mapped_column(String, nullable=False)
    template_region: Mapped[str] = mapped_column(String, default="")
    template_operator: Mapped[str] = mapped_column(String, default="")
    template_target_name: Mapped[str] = mapped_column(String, default="")
    template_target_address: Mapped[str] = mapped_column(String, default="")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class Subscription(Base):
    """API 订阅表"""
    __tablename__ = "subscription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    uid: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, default="")
    type: Mapped[str] = mapped_column(String, default="api")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    fetch_cron: Mapped[str] = mapped_column(String, default="")
    last_fetch_at: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    created_at: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class Cache(Base):
    """数据缓存表（游离主机）"""
    __tablename__ = "cache"

    # host 全局唯一：cache_sources 的 upsert 依赖此约束
    #（没有它，SELECT-then-INSERT 在任何绕过进程锁的写路径下会产生重复行）
    __table_args__ = (
        UniqueConstraint('host', name='uq_cache_host'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 来源标识 = subscription.uid（多个订阅可共用同一 uid，如多个 GitHub 镜像）
    uid: Mapped[str] = mapped_column(String, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    geo_region: Mapped[str] = mapped_column(String, default="")
    geo_operator: Mapped[str] = mapped_column(String, default="")
    active: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[Optional[int]] = mapped_column(Integer, default=None)


class Host(Base):
    """主机池表"""
    __tablename__ = "host"

    # 同一主机 + 目标 + 频道唯一，扫描入库的 upsert（ON CONFLICT）依赖此约束
    __table_args__ = (
        UniqueConstraint('host', 'target', 'channel_name', name='uq_host_host_target_channel'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host: Mapped[str] = mapped_column(String, nullable=False)
    ip: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    # 来源标识 = subscription.uid（多个订阅可共用同一 uid）
    uid: Mapped[str] = mapped_column(String, default="")
    region: Mapped[str] = mapped_column(String, nullable=False)
    operator: Mapped[str] = mapped_column(String, nullable=False)
    geo_region: Mapped[str] = mapped_column(String, default="")
    geo_operator: Mapped[str] = mapped_column(String, default="")
    delay: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str] = mapped_column(String, nullable=False)
    channel_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


# =============================================================================
# Pydantic 请求/响应模型
# =============================================================================

class GlobalSettingsUpdate(BaseModel):
    # 三个数值参数都有默认值：前端不传/传空时后端回落到默认值，不再报 422
    # 前端统一传 camelCase，必须配 alias：否则 configDelay/scanCron 等字段会被
    # Pydantic 忽略，接口按默认值覆盖入库（cron/api_key 曾因此被清空）
    concurrency: int = Field(30, ge=20, le=64)
    timeout: int = Field(5, ge=2, le=10)  # 秒（原为毫秒 200-10000，已改为秒）
    config_delay: int = Field(3, ge=1, le=60, alias="configDelay")
    scan_cron: str = Field("", alias="scanCron")
    janitor_cron: str = Field("", alias="janitorCron")
    push_api_key: str = Field("", alias="pushApiKey")

    model_config = {"populate_by_name": True}


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
    uids: Optional[Union[str, List[str]]] = None

    model_config = {"populate_by_name": True}


class ApiSubscriptionCreate(BaseModel):
    name: str
    uid: str
    url: Optional[str] = ""
    type: str = "api"
    enabled: bool = True
    fetch_cron: str = Field("", alias="fetchCron")

    model_config = {"populate_by_name": True}
