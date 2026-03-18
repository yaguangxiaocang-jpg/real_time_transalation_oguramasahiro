"""Hugging Face Spaces entry point."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from real_time_translation.gradio_demo import build_demo

demo = build_demo()
demo.queue()

if __name__ == "__main__":
    demo.launch()
