"""Instance configuration (workstream M, ownership rule 16).

One TOML file says which data sources, storage and executors an instance
uses. Code never hard-codes a bucket, a cloud or a sensor's licence. The file
path comes from ``GEOAPPS_CONFIG`` (default ``geoapps.toml``); a missing file
means "no external sources", which is fine for a first run.
"""

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    name: str
    kind: Literal["stac", "folder"] = "stac"
    url: str
    collections: list[str] = Field(default_factory=list)
    mirror: Literal["full", "crop", "reference"] = "reference"
    licence: str = "unspecified"
    description: str = ""


class StorageConfig(BaseModel):
    root: str = "file:///data/geoapps"


class ExecutorConfig(BaseModel):
    default: Literal["local", "docker", "batch"] = "local"


class AuthConfig(BaseModel):
    enabled: bool = False


class InstanceConfig(BaseModel):
    name: str = "geoapps"
    titiler_url: str = "http://localhost:8001"
    storage: StorageConfig = Field(default_factory=StorageConfig)
    sources: list[SourceConfig] = Field(default_factory=list)
    executors: ExecutorConfig = Field(default_factory=ExecutorConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)

    def source(self, name: str) -> SourceConfig:
        for s in self.sources:
            if s.name == name:
                return s
        raise KeyError(f"no source named {name!r}; configured: {[s.name for s in self.sources]}")


def load_config(path: str | os.PathLike | None = None) -> InstanceConfig:
    p = Path(path or os.environ.get("GEOAPPS_CONFIG", "geoapps.toml"))
    data = tomllib.loads(p.read_text()) if p.is_file() else {}
    cfg = InstanceConfig.model_validate(data)
    # environment wins for the one value that differs between host and container
    if url := os.environ.get("GEOAPPS_TITILER_URL"):
        cfg.titiler_url = url
    return cfg
