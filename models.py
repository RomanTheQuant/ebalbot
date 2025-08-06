from dataclasses import dataclass
from typing import Optional

@dataclass
class UserData:
    id: int
    tg_id: int
    name: str
    pair_code: Optional[str]
    pair_id: Optional[int]

@dataclass
class TaskData:
    id: int
    title: str
    description: str