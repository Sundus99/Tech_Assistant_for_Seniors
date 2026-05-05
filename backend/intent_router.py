

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

class IntentType(str, Enum):
    voice_command = 'voice_command_category'


@dataclass
class RoutedIntent:
    intent: IntentType