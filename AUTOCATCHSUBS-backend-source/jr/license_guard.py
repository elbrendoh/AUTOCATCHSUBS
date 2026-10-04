import os
from pathlib import Path
import threading
from player import Player, current_hwid
from release_config import PUBLIC_KEY, ENDPOINT
_player = None
_lock = threading.Lock()
def require_active():
    global _player
    with _lock:
        if _player is None:
            _player=Player(Path(os.environ['LOCALAPPDATA'])/'AUTOCATCHSUBS-License',PUBLIC_KEY,current_hwid(),ENDPOINT)
        return _player.require_active()
