"""動画からDeepgramの生発話(utterance分割そのまま、結合ロジック適用前)を採取し、
`naturalness_check_ab_test.py` / `naturalness_score_distribution.py` が読める
`{"raw_utterances": [...]}`形式で`experiments/segments/`に保存する。

`experiments/segments/20260824_2d07bb74_v2_clip1_raw_unmerged.json`が
`add_subtitles.py`の`extract_audio()`/`transcribe_audio()`を使ってアドホックに
作られたものだったため(同ファイルの`note`参照)、再現性のためのスクリプトとして
切り出した。同じ設定(model=nova-2-general, language=en, smart_format+punctuate+
utterances=true, utt_split=0.8。DeepgramキーワードブーストはDICTIONARY_PATH設定時
デフォルトで有効=`add_subtitles.py`本番と同一)。

使い方:
    python evaluation/capture_raw_utterances.py clips/2d07bb74_v2_clip3.mp4
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from add_subtitles import extract_audio, transcribe_audio  # noqa: E402


def main(video_path: Path, note: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = str(Path(tmpdir) / "audio.wav")
        extract_audio(str(video_path), audio_path)
        raw_utterances = transcribe_audio(audio_path)

    out = {
        "date": date.today().isoformat(),
        "video": f"clips/{video_path.name}",
        "note": note,
        "raw_utterances": raw_utterances,
    }

    out_name = f"{date.today().strftime('%Y%m%d')}_{video_path.stem}_raw_unmerged.json"
    out_path = Path(__file__).parent.parent / "experiments" / "segments" / out_name
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(raw_utterances)}件の生発話を保存: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="動画からDeepgramの生発話を採取する")
    parser.add_argument("video", type=Path, help="動画ファイルパス")
    parser.add_argument(
        "--note",
        default="Deepgramの生発話(utterance分割そのまま、utterance結合の補正は適用していない状態)。"
        "model=nova-2-general, language=en, smart_format+punctuate+utterances=true, utt_split=0.8。"
        "add_subtitles.py の extract_audio()/transcribe_audio() で取得。",
    )
    args = parser.parse_args()

    if not args.video.exists():
        print(f"エラー: ファイルが見つかりません: {args.video}")
        sys.exit(1)

    main(args.video, args.note)
