"""Deepgramキーワードブースト有効化後の再比較(vs faster-whisper)。

report.txtの「Deepgram vs faster-whisperで既知誤認識9箇所中8箇所でfaster-whisperが
正確」という結論は、Deepgramのキーワードブースト機能(`deepgram_keyword_boost_enabled`、
2026-08-11導入)が実装される前に行われた比較だった(README「未検証」ログ参照、
`transcription/deepgram_client.py`のdocstring参照)。つまり元の比較ではDeepgram側が
ブースト無しの不利な条件だった可能性がある。

本スクリプトは同じclip2/clip3音声(`clips/2d07bb74_clip2.mp4`, `clip3.mp4`)に対し、
Deepgramを(a)ブースト無し(元の比較と同条件の再現)、(b)本番と同じブーストON
(`dictionary.csv`のkeep_as_is_terms、`config.deepgram_keyword_boost_enabled`が
実際に配線している内容と同じ)の2条件で再文字起こしし、faster-whisper(small.en、
元の比較と同条件)と3者比較する。既知の誤認識パターン(T5→TIFINE/TFI/TIFI、
PaLM→Parm、PaLM 2→PARM two/PARAM two、GPT-3→g p three/g p g three/GPG3、
memory wall→memory war)が各条件で解消されているかを判定する。

注記: memory wallはdictionary.csv上で`memory wall,メモリウォール`(訳語ペア)であり
`keep_as_is_terms()`(source==targetのみ抽出)の対象外のため、ブーストキーワードには
含まれない。boost有無で差が出ないはずの対照項目として扱う。

使い方:
    python evaluation/deepgram_keyword_boost_rematch.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from deepgram import DeepgramClient
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from real_time_translation.transcription.whisper_client import transcribe_with_whisper
from real_time_translation.translation.dictionary import TermDictionary

CLIPS = ["clips/2d07bb74_clip2.mp4", "clips/2d07bb74_clip3.mp4"]

# (正しい用語, [既知の誤認識パターン...])
KNOWN_TERMS: list[tuple[str, list[str]]] = [
    ("T5", ["TIFINE", "TFI", "TIFI"]),
    ("PaLM 2", ["PARM two", "PARAM two"]),
    ("PaLM", ["Parm"]),
    ("GPT-3", ["g p three", "g p g three", "GPG3"]),
    ("memory wall", ["memory war"]),
]

_ASCII_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-.]*$")


def _contains_word(haystack: str, term: str) -> bool:
    """termがhaystack中に単語として出現するか(前後が英数字でないこと)を判定する。"""
    if _ASCII_RE.match(term):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
        return re.search(pattern, haystack, re.IGNORECASE) is not None
    return term.lower() in haystack.lower()


def transcribe_deepgram(client: DeepgramClient, audio_path: str, keywords: list[str]) -> str:
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    kwargs: dict = {}
    if keywords:
        kwargs["keywords"] = keywords
    response = client.listen.v1.media.transcribe_file(
        request=audio_data,
        model="nova-2-general",  # config.pyの本番デフォルトと同じモデル
        language="en",
        smart_format=True,
        punctuate=True,
        **kwargs,
    )
    return response.results.channels[0].alternatives[0].transcript


def judge(transcript: str, correct: str, wrong_patterns: list[str]) -> str:
    has_correct = _contains_word(transcript, correct)
    has_wrong = any(_contains_word(transcript, w) for w in wrong_patterns)
    if has_wrong:
        return "NG(誤認識のまま)"
    if has_correct:
        return "OK"
    return "?(該当なし)"


def main() -> None:
    load_dotenv()
    api_key = os.environ["DEEPGRAM_API_KEY"]
    client = DeepgramClient(api_key=api_key)

    dictionary = TermDictionary()
    dictionary.load_csv(Path(__file__).parent.parent / "dictionary.csv")
    boosted_keywords = dictionary.as_asr_keywords(boost=2.0)
    print(f"boost keywords ({len(boosted_keywords)}件): {boosted_keywords}\n")

    for clip in CLIPS:
        print("=" * 78)
        print(f"clip: {clip}")
        print("=" * 78)

        dg_plain = transcribe_deepgram(client, clip, keywords=[])
        dg_boosted = transcribe_deepgram(client, clip, keywords=boosted_keywords)
        whisper_segments = transcribe_with_whisper(clip, model_size="small.en")
        whisper_transcript = " ".join(seg["transcript"] for seg in whisper_segments)

        header = f"{'用語':12s} | {'Deepgram(無boost)':22s} | {'Deepgram(boost ON)':22s} | {'whisper':s}"
        print(header)
        print("-" * len(header))
        for correct, wrong_patterns in KNOWN_TERMS:
            r_plain = judge(dg_plain, correct, wrong_patterns)
            r_boosted = judge(dg_boosted, correct, wrong_patterns)
            r_whisper = judge(whisper_transcript, correct, wrong_patterns)
            print(f"{correct:12s} | {r_plain:22s} | {r_boosted:22s} | {r_whisper}")
        print()

        print("--- Deepgram(無boost) transcript ---")
        print(dg_plain)
        print("\n--- Deepgram(boost ON) transcript ---")
        print(dg_boosted)
        print("\n--- whisper(small.en) transcript ---")
        print(whisper_transcript)
        print()


if __name__ == "__main__":
    main()
