from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Project:
    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    repository_url: Optional[str] = None
    default_branch: str = "main"
    language_stack: str = "python"
    created_at: Optional[datetime] = None
