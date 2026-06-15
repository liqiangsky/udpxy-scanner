from pydantic import BaseModel, Field
from typing import Optional, Union, List

class GlobalSettingsUpdate(BaseModel):
    concurrency: int = Field(64, ge=1, le=500)
    timeout: int = Field(2000, ge=200, le=10000)
    configDelay: int = Field(3, ge=0, le=300)
    scanCron: str = ""
    janitorCron: str = ""
    pushApiKey: str = ""

class ConfigCreateOrUpdate(BaseModel):
    name: str
    region: str
    operator: str
    targetName: str
    targetAddress: str
    dataSource: str
    enabled: Optional[bool] = True

class SourceCacheDelete(BaseModel):
    ids: Optional[Union[int, List[int]]] = None
    sourceTypes: Optional[Union[str, List[str]]] = None

class ApiSubscriptionCreate(BaseModel):
    name: str
    uid: str
    url: str
    enabled: bool = True
    fetchCron: str = ""
