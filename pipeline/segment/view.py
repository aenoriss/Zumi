"""The viewing geometry every layer shares: the panel camera's field of view, assumed on the box's long side (comics
have no camera), and the reading distance d at which every frame's window stands; all depths are shares of d."""
from __future__ import annotations

import numpy as np

FOV = 55.0       # degrees, on the box's long side
WINDOW_Z = 1.0   # the frames' windows stand at the reading distance; every layer lies behind, the bubbles at it


def focal(w: int, h: int, fov: float = FOV) -> float:
    """The camera's focal length in box pixels."""
    return max(w, h) / (2 * np.tan(np.radians(fov / 2)))
