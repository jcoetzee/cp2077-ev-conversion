"""Extract the game's cooked audio metadata (vehicle sound definitions) for inspection."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rdar  # noqa: E402

ARC = "/Applications/Cyberpunk 2077/archive/Mac/content/audio_1_general.archive"
OUT = os.path.join(os.path.dirname(HERE), "extracted", "audio")
FILES = {
    "base\\sound\\metadata\\cooked_metadata.audio_metadata": "cooked_metadata.audio_metadata",
    "base\\sound\\event\\eventsmetadata.json": "eventsmetadata.json",
}

os.makedirs(OUT, exist_ok=True)
idx = rdar.read_index(ARC)
for depot, name in FILES.items():
    data = rdar.extract(ARC, depot, idx)
    open(os.path.join(OUT, name), "wb").write(data)
    print(name, len(data), data[:4])
