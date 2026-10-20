"""【実験用】Deepgramの話者分離（diarize）で「話者A／話者B」が正しく付くかを確認する。

本番の動画字幕（`add_subtitles.py`）・utterance結合（`utterance_merge.py`）には
一切手を入れず、このスクリプト内だけで話者分離を試す。結果が良ければ本番へ
取り込むかどうかを判断する（マイクのリアルタイム翻訳への展開はその後）。

Deepgramの設定は`add_subtitles.py`の`transcribe_audio()`と同じ
（model=nova-2-general, smart_format+punctuate+utterances=true, utt_split=0.8）に
`diarize=True`だけを足している。キーワードブーストは使わない。

utterance結合は本番と同じ`merge_incomplete_utterances`を使うが、
**話者が変わる位置では結合しない**ように、同一話者が連続する区間ごとに
分けてから適用する（本番の結合ロジックは話者を区別しないため）。

区切り方は2通り（`--split`）:
    word       単語レベルの話者番号が変わる位置で区切り直す（既定。あいづちを分離できる）
    utterance  Deepgramのutterance単位の話者番号をそのまま使う（比較用）

出力（`experiments/diarization/`）:
    YYYYMMDD_<動画名>_split-<区切り方>.json         単語単位の話者番号付き生データ・結合後セグメント・話者別集計
    YYYYMMDD_<動画名>_split-<区切り方>_speakers.srt 「[話者A] ...」形式のSRT（動画と並べて再生して確認する）

使い方:
    python evaluation/diarization_check.py clips/sample.mp4
    python evaluation/diarization_check.py clips/sample.mp4 --translate   # 日本語訳も付ける
    python evaluation/diarization_check.py clips/sample.mp4 --no-merge    # 結合せず生utteranceのまま
    python evaluation/diarization_check.py clips/sample.mp4 --no-snap     # 話者切り替わり位置の補正をしない（比較用）
    python evaluation/diarization_check.py clips/sample.mp4 --translate --burn  # 話者ラベル付き日本語字幕を焼き込む
    python evaluation/diarization_check.py clips/sample.mp4 --from-json <保存済みJSON> --translate --burn  # Deepgramを呼ばない
"""

from __future__ import annotations

import argparse
import asyncio
import json
import string
import sys
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from add_subtitles import (  # noqa: E402
    DEEPGRAM_API_KEY,
    SOURCE_LANGUAGE,
    extract_audio,
    seconds_to_srt_time,
)
from real_time_translation.transcription.utterance_merge import (  # noqa: E402
    merge_incomplete_utterances,
)

OUTPUT_DIR = Path(__file__).parent.parent / "experiments" / "diarization"


def speaker_label(speaker: int | None) -> str:
    """Deepgramの話者番号（0始まり）を「話者A」「話者B」…に変換する。"""
    if speaker is None:
        return "話者?"
    if speaker < len(string.ascii_uppercase):
        return f"話者{string.ascii_uppercase[speaker]}"
    return f"話者{speaker + 1}"


def transcribe_with_diarization(audio_path: str) -> list[dict]:
    """Deepgramで話者分離付きの文字起こしを行い、speaker付きutteranceを返す。"""
    from deepgram import DeepgramClient

    print("Deepgramで文字起こし中（diarize=True）...")
    client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
    with open(audio_path, "rb") as f:
        audio_data = f.read()

    response = client.listen.v1.media.transcribe_file(
        request=audio_data,
        model="nova-2-general",
        language=SOURCE_LANGUAGE,
        smart_format=True,
        punctuate=True,
        utterances=True,
        utt_split=0.8,
        diarize=True,
    )

    utterances = getattr(response.results, "utterances", None) or []
    result = [
        {
            "start": u.start,
            "end": u.end,
            "speaker": u.speaker,
            "transcript": u.transcript,
            "words": [
                {
                    "word": w.punctuated_word or w.word,
                    "start": w.start,
                    "end": w.end,
                    "speaker": w.speaker,
                    "speaker_confidence": w.speaker_confidence,
                }
                for w in (u.words or [])
            ],
        }
        for u in utterances
        if u.transcript
    ]
    print(f"文字起こし完了: {len(result)} utterance")
    return result


def split_by_word_speaker(
    utterances: list[dict], snap: bool = True
) -> tuple[list[dict], int]:
    """utterance内で単語レベルの話者番号が変わる位置で区切り直す。

    Deepgramはutterance単位では話者番号を1つしか付けないため、相手の短い
    あいづち（"Yes." "Oh."）が話している側のutteranceに吸収される。単語には
    個別の話者番号が付いているので、それが変わる位置で分割する。

    snap=True のときは、文の途中に来てしまった話者の切り替わり位置を
    文の切れ目へ寄せる（`snap_speaker_boundaries`）。

    Returns:
        (区切り直した区間, 切り替わり位置を動かした数)
    """
    runs: list[list[dict]] = []
    # 単語情報のないutterance（runsの位置 → そのまま出力）
    passthrough: dict[int, dict] = {}
    for u in utterances:
        words = u.get("words") or []
        if not words:
            passthrough[len(runs)] = {k: v for k, v in u.items() if k != "words"}
            runs.append([])
            continue
        run: list[dict] = [words[0]]
        for w in words[1:]:
            if w["speaker"] != run[-1]["speaker"]:
                runs.append(run)
                run = []
            run.append(w)
        runs.append(run)

    snapped = snap_speaker_boundaries(runs) if snap else 0

    segments = [
        passthrough[i] if i in passthrough else _words_to_segment(run)
        for i, run in enumerate(runs)
        if run or i in passthrough
    ]
    return segments, snapped


# 話者の切り替わり位置を動かすときに、隣へ移してよい最大の単語数。
# これより長い食い違いはDeepgramの判定を優先する（本当の割り込みの可能性がある）。
MAX_SNAP_WORDS = 2
# 移す単語と移し先の間の無音がこれより長ければ動かさない（別の発話とみなす）
MAX_SNAP_GAP_SEC = 1.0
_SENTENCE_END = (".", "?", "!")


def _ends_sentence(word: dict) -> bool:
    return word["word"].endswith(_SENTENCE_END)


def _is_continuation(word: dict) -> bool:
    """小文字で始まる単語は前の文の続き（"talk about ..." など）。"""
    return word["word"][:1].islower()


def snap_speaker_boundaries(runs: list[list[dict]]) -> int:
    """文の途中にある話者の切り替わりを、文の切れ目まで1〜2語ずらす（runsを直接書き換える）。

    単語レベルの話者番号は切り替わり付近で1〜2語ずれやすい。実データ
    （harari_utada 全編、2026-10-20）では "Yes. To | talk about art ..." の "To"、
    "... appreciate that | or not." の "or not." のように、文の頭や尻尾だけが
    隣の話者に付き、訳が「ええ。To」のように崩れていた。

    話者の違う隣り合う区間 X|Y の境目が文の途中（Xの最後が文末記号で終わらない、
    またはYの最初が小文字）なら、次の2案のうち移す単語が少ない方を採る:
      (a) Xの最後の文末記号より後ろの単語をYへ移す
      (b) Yの最初の文末記号までの単語をXへ移す（Yが小文字で始まるときだけ）
    どちらも MAX_SNAP_WORDS を超えるときは動かさない。(b)を小文字始まりに限るのは、
    相手のあいづち（"Yes." "Mhmm."）が話し手の文の途中に入ったとき、それを話し手の
    文に吸収してしまわないため（初版ではこの誤りが17件中3件あった）。

    Returns:
        動かした境目の数
    """
    snapped = 0
    i = 0
    while i < len(runs) - 1:
        x, y = runs[i], runs[i + 1]
        if (
            not x
            or not y
            or x[-1]["speaker"] == y[0]["speaker"]
            or (_ends_sentence(x[-1]) and not _is_continuation(y[0]))
            or y[0]["start"] - x[-1]["end"] > MAX_SNAP_GAP_SEC
        ):
            i += 1
            continue

        tail = 0  # (a) Xの尻尾の、文末記号より後ろの単語数
        while tail < len(x) and not _ends_sentence(x[-1 - tail]):
            tail += 1
        head = 0  # (b) Yの頭の、最初の文末記号までの単語数
        while head < len(y):
            head += 1
            if _ends_sentence(y[head - 1]):
                break

        a_ok = 0 < tail <= MAX_SNAP_WORDS
        b_ok = _is_continuation(y[0]) and head <= MAX_SNAP_WORDS
        if a_ok and (not b_ok or tail <= head):
            moved, runs[i] = x[-tail:], x[:-tail]
            runs[i + 1] = [{**w, "speaker": y[0]["speaker"]} for w in moved] + y
        elif b_ok:
            moved, runs[i + 1] = y[:head], y[head:]
            runs[i] = x + [{**w, "speaker": x[-1]["speaker"]} for w in moved]
        else:
            i += 1
            continue
        snapped += 1
        i += 1
    return snapped


def _words_to_segment(words: list[dict]) -> dict:
    return {
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "speaker": words[0]["speaker"],
        "transcript": " ".join(w["word"] for w in words),
    }


def merge_within_speaker(utterances: list[dict]) -> list[dict]:
    """同一話者が連続する区間ごとに、本番と同じ結合ロジックを適用する。"""
    merged: list[dict] = []
    run: list[dict] = []
    for u in utterances:
        if run and u["speaker"] != run[-1]["speaker"]:
            merged.extend(_merge_run(run))
            run = []
        run.append(u)
    if run:
        merged.extend(_merge_run(run))
    return merged


def _merge_run(run: list[dict]) -> list[dict]:
    speaker = run[0]["speaker"]
    return [{**m, "speaker": speaker} for m in merge_incomplete_utterances(run)]


def summarize_speakers(segments: list[dict]) -> dict:
    """話者ごとのセグメント数・合計発話時間・話者交代回数を集計する。"""
    counts: dict[str, int] = defaultdict(int)
    durations: dict[str, float] = defaultdict(float)
    for seg in segments:
        label = speaker_label(seg["speaker"])
        counts[label] += 1
        durations[label] += seg["end"] - seg["start"]
    turns = sum(
        1 for prev, cur in zip(segments, segments[1:]) if prev["speaker"] != cur["speaker"]
    )
    return {
        "num_speakers": len(counts),
        "speaker_turns": turns,
        "per_speaker": {
            label: {"segments": counts[label], "seconds": round(durations[label], 1)}
            for label in sorted(counts)
        },
    }


def write_speaker_srt(segments: list[dict], srt_path: Path) -> None:
    """「[話者A] 原文」（--translate時は次の行に日本語訳）形式のSRTを書き出す。"""
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(
            f"{seconds_to_srt_time(seg['start'])} --> {seconds_to_srt_time(seg['end'])}"
        )
        lines.append(f"[{speaker_label(seg['speaker'])}] {seg['transcript']}")
        if seg.get("japanese"):
            lines.append(seg["japanese"])
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


# 焼き込み字幕の話者ごとの色（SRTの<font>タグ。ffmpegのsubtitlesフィルタ（libass）が解釈する）
SPEAKER_COLORS = ["#FFE066", "#7FD4FF", "#A8F0A0", "#FFA8C8"]


def write_burn_srt(segments: list[dict], srt_path: Path) -> None:
    """焼き込み用SRT。「話者A: 日本語訳」を話者ごとに色分けする（訳がなければ原文）。"""
    lines = []
    for i, seg in enumerate(segments, 1):
        speaker = seg["speaker"]
        color = SPEAKER_COLORS[speaker % len(SPEAKER_COLORS)] if speaker is not None else "#FFFFFF"
        text = seg.get("japanese") or seg["transcript"]
        lines.append(str(i))
        lines.append(
            f"{seconds_to_srt_time(seg['start'])} --> {seconds_to_srt_time(seg['end'])}"
        )
        lines.append(f'<font color="{color}">{speaker_label(speaker)}: {text}</font>')
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def burn(video_path: Path, segments: list[dict], output_path: Path) -> None:
    """本番と同じ`burn_subtitles`（ffmpeg）で話者ラベル付き字幕を焼き込む。"""
    from add_subtitles import burn_subtitles

    # ffmpegのsubtitlesフィルタはパス中の日本語・空白に弱いため一時ファイルに書く
    with tempfile.TemporaryDirectory() as tmpdir:
        srt_path = Path(tmpdir) / "speakers.srt"
        write_burn_srt(segments, srt_path)
        burn_subtitles(str(video_path), str(srt_path), str(output_path))


async def translate(segments: list[dict]) -> None:
    """本番と同じ`translate_segments`で翻訳し、各セグメントに`japanese`を付ける。"""
    from add_subtitles import translate_segments

    translated, _report = await translate_segments(segments)
    # translate_segments は入力と同じ順序・件数で返す
    for seg, tr in zip(segments, translated):
        seg["japanese"] = tr["japanese"]


async def main(
    video_path: Path,
    merge: bool,
    do_translate: bool,
    split: str,
    from_json: Path | None,
    do_burn: bool = False,
    snap: bool = True,
) -> None:
    if from_json is not None:
        # 保存済みのDeepgram出力を再利用する（APIを呼ばずに区切り方だけ比較できる）
        raw_utterances = json.loads(from_json.read_text(encoding="utf-8"))["raw_utterances"]
        if split == "word" and not any(u.get("words") for u in raw_utterances):
            print("このJSONには単語レベルの話者番号が含まれていません。--from-json なしで再実行してください。")
            sys.exit(1)
        print(f"保存済みのDeepgram出力を再利用: {from_json}")
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = str(Path(tmpdir) / "audio.wav")
            extract_audio(str(video_path), audio_path)
            raw_utterances = await asyncio.to_thread(transcribe_with_diarization, audio_path)

    if not raw_utterances:
        print("文字起こし結果が空です。")
        sys.exit(1)

    if split == "word":
        units, snapped = split_by_word_speaker(raw_utterances, snap=snap)
        print(f"単語レベルの話者で区切り直し: {len(raw_utterances)} → {len(units)} 区間")
        if snap:
            print(f"文の途中の話者切り替わりを文の切れ目へ移動: {snapped} 箇所")
    else:
        snapped = 0
        units = [{k: v for k, v in u.items() if k != "words"} for u in raw_utterances]

    segments = merge_within_speaker(units) if merge else units
    print(f"utterance結合（話者内のみ）: {len(units)} → {len(segments)} セグメント")

    if do_translate:
        await translate(segments)

    summary = summarize_speakers(segments)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prefix = f"{date.today().strftime('%Y%m%d')}_{video_path.stem}_split-{split}"
    if split == "word" and not snap:
        prefix += "_nosnap"
    json_path = OUTPUT_DIR / f"{prefix}.json"
    srt_path = OUTPUT_DIR / f"{prefix}_speakers.srt"

    record = {
        "date": date.today().isoformat(),
        "video": video_path.name,
        "deepgram": {"model": "nova-2-general", "diarize": True, "utt_split": 0.8},
        "split": split,
        "snap_boundaries": split == "word" and snap,
        "snapped_boundaries": snapped,
        "merge_within_speaker": merge,
        "summary": summary,
        "segments": [{**seg, "speaker_label": speaker_label(seg["speaker"])} for seg in segments],
        "raw_utterances": raw_utterances,
    }
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    write_speaker_srt(segments, srt_path)

    print("\n--- 話者別集計 ---")
    print(f"検出話者数: {summary['num_speakers']} / 話者交代: {summary['speaker_turns']}回")
    for label, stats in summary["per_speaker"].items():
        print(f"  {label}: {stats['segments']}セグメント, {stats['seconds']}秒")

    print("\n--- タイムライン（最初の15件） ---")
    for seg in segments[:15]:
        print(f"[{seconds_to_srt_time(seg['start'])}] {speaker_label(seg['speaker'])}: {seg['transcript']}")
        if seg.get("japanese"):
            print(f"    → {seg['japanese']}")

    print(f"\nJSON: {json_path}")
    print(f"SRT : {srt_path}")

    if do_burn:
        # 動画は大きいので experiments/ ではなく元動画の隣（clips/ は .gitignore 済み）に出力する
        output_path = video_path.parent / f"{video_path.stem}_speakers_subtitled.mp4"
        burn(video_path, segments, output_path)
        print(f"字幕付き動画: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video", type=Path)
    parser.add_argument("--no-merge", action="store_true", help="utterance結合をしない")
    parser.add_argument("--translate", action="store_true", help="日本語訳も付ける（Gemini APIを使う）")
    parser.add_argument(
        "--split",
        choices=["word", "utterance"],
        default="word",
        help="word: 単語レベルの話者番号で区切り直す（既定） / utterance: Deepgramのutterance単位のまま",
    )
    parser.add_argument(
        "--no-snap",
        action="store_true",
        help="--split word のとき、文の途中の話者切り替わりを文の切れ目へ寄せる補正をしない（比較用）",
    )
    parser.add_argument(
        "--from-json", type=Path, help="保存済みJSONのDeepgram出力を再利用する（APIを呼ばない）"
    )
    parser.add_argument(
        "--burn",
        action="store_true",
        help="「話者A: 訳文」を話者ごとに色分けして動画に焼き込む（--translate なしなら原文）",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.video.resolve(),
            merge=not args.no_merge,
            do_translate=args.translate,
            split=args.split,
            from_json=args.from_json,
            do_burn=args.burn,
            snap=not args.no_snap,
        )
    )
