"""翻訳にかかる時間（話し終わり → 訳文表示）を区間ごとに計測する。

時刻はすべて `time.monotonic()`（秒）。1文ごとに次の時刻を記録する。

    話し終わり ─①─ 文字確定 ─②─ 文末判定完了 ─③─ 翻訳キュー投入
              ─④─ 翻訳開始 ─⑤─ 翻訳完了 ─⑥─ 画面表示

①音声認識  : Deepgram が最後の単語を確定（is_final）するまで。endpointing の無音待ちを含む
②文末判定  : 文末判定・不自然度チェック（LLM、設定で有効な場合）と文の結合処理
③Whisper再検証: 既知用語の再文字起こし（設定で有効な場合）
④翻訳待ち  : 前の文の翻訳が終わるまでキューで待った時間
⑤翻訳API   : Gemini/OpenAI の応答時間
⑥画面表示  : 翻訳完了から画面へ反映されるまで（Gradio の更新間隔ぶん待つ）

「話し終わり」は Deepgram の単語タイムスタンプ（音声の先頭からの秒数）を、
その音声を Deepgram へ送った時刻に換算して求める（`AudioClock`）。ブラウザ → サーバー
の転送時間は測れないため含まない。

ほかに参考値として「結合待ち」（文の先頭部分が確定してから文全体が確定するまで）を
記録する。文の先頭を話し終えた人から見た待ち時間で、合計には含めない。
"""

from __future__ import annotations

import bisect
import csv
import io
import statistics
from dataclasses import dataclass
from datetime import datetime

BYTES_PER_SECOND = 16000 * 2  # 16kHz・16bit・モノラル PCM

# (キー, 画面・CSV での名前)
STAGES: list[tuple[str, str]] = [
    ("asr", "音声認識"),
    ("endpoint", "文末判定"),
    ("reverify", "Whisper再検証"),
    ("queue", "翻訳待ち"),
    ("llm", "翻訳API"),
    ("display", "画面表示"),
]
STAGE_LABELS = dict(STAGES)


class AudioClock:
    """音声ストリーム上の時刻（秒）を、その音声を送った時刻（monotonic）に換算する。

    送信のたびに「ここまでの累計秒数」と送信時刻を記録しておき、ある音声時刻 t を
    含むチャンクの送信時刻から、チャンク内での t より後ろの長さを引いて
    「t の音声が実際に発話された時刻」を推定する。リアルタイムの音声（マイク）なら
    チャンクの末尾が送信時刻とほぼ同時に話されているためこの推定が成り立つ。
    実時間より速く流し込む音声ファイル処理では、前のチャンクの送信時刻より前には
    さかのぼらないよう制限する。
    """

    def __init__(self, max_marks: int = 50000) -> None:
        self._ends: list[float] = []  # 各チャンク送信後の累計音声秒数
        self._sent: list[float] = []  # 各チャンクの送信時刻
        self._total = 0.0
        self._max_marks = max_marks
        # 古い記録を捨てたとき、捨てた最後のチャンクの (累計秒数, 送信時刻)
        self._dropped_end = 0.0
        self._dropped_sent: float | None = None

    def record(self, nbytes: int, sent_at: float) -> None:
        if nbytes <= 0:
            return
        self._total += nbytes / BYTES_PER_SECOND
        self._ends.append(self._total)
        self._sent.append(sent_at)
        if len(self._ends) > self._max_marks:
            drop = len(self._ends) - self._max_marks
            self._dropped_end = self._ends[drop - 1]
            self._dropped_sent = self._sent[drop - 1]
            del self._ends[:drop]
            del self._sent[:drop]

    def to_wall(self, audio_time: float) -> float | None:
        """音声時刻 → 発話時刻（monotonic）。範囲外（未送信・記録を捨てた古い音声）なら None。"""
        if audio_time < self._dropped_end:
            return None
        i = bisect.bisect_left(self._ends, audio_time)
        if i >= len(self._ends):
            return None
        sent = self._sent[i]
        behind = self._ends[i] - audio_time
        prev_sent = self._sent[i - 1] if i > 0 else self._dropped_sent
        if prev_sent is not None:
            behind = min(behind, max(0.0, sent - prev_sent))
        return sent - behind


@dataclass
class SegmentTiming:
    """1文ぶんの各時点の時刻（monotonic 秒）。未計測は None。"""

    text: str = ""
    speech_end: float | None = None
    first_asr_final: float | None = None
    asr_final: float | None = None
    endpoint_done: float | None = None
    queued: float | None = None
    translate_start: float | None = None
    translate_end: float | None = None
    displayed: float | None = None
    recorded_at: datetime | None = None

    def _span(self, a: float | None, b: float | None) -> float | None:
        if a is None or b is None:
            return None
        return max(0.0, b - a)

    def stages(self) -> dict[str, float | None]:
        return {
            "asr": self._span(self.speech_end, self.asr_final),
            "endpoint": self._span(self.asr_final, self.endpoint_done),
            "reverify": self._span(self.endpoint_done, self.queued),
            "queue": self._span(self.queued, self.translate_start),
            "llm": self._span(self.translate_start, self.translate_end),
            "display": self._span(self.translate_end, self.displayed),
        }

    @property
    def total(self) -> float | None:
        """話し終わり → 画面表示。"""
        return self._span(self.speech_end, self.displayed)

    @property
    def merge_wait(self) -> float | None:
        """参考: 文の先頭部分の確定 → 文全体の確定。"""
        return self._span(self.first_asr_final, self.asr_final)


def percentile(values: list[float], q: float) -> float:
    """線形補間のパーセンタイル（q は 0〜100）。"""
    if not values:
        raise ValueError("empty")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q / 100
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


@dataclass(frozen=True)
class StageStats:
    label: str
    count: int
    median: float
    p95: float
    max: float


class LatencyTracker:
    """セッション中の全文の計測結果を保持し、集計・CSV 出力する。"""

    def __init__(self, max_records: int = 10000) -> None:
        self.records: list[SegmentTiming] = []
        self._max_records = max_records

    def add(self, timing: SegmentTiming) -> None:
        if timing.recorded_at is None:
            timing.recorded_at = datetime.now()
        self.records.append(timing)
        if len(self.records) > self._max_records:
            del self.records[: len(self.records) - self._max_records]

    def __len__(self) -> int:
        return len(self.records)

    def summary(self) -> list[StageStats]:
        """区間ごと + 合計 + 結合待ち（参考）の 中央値 / p95 / 最大。"""
        columns: list[tuple[str, list[float]]] = []
        for key, label in STAGES:
            values = [v for r in self.records if (v := r.stages()[key]) is not None]
            columns.append((label, values))
        columns.append(
            (
                "合計（話し終わり→表示）",
                [t for r in self.records if (t := r.total) is not None],
            )
        )
        columns.append(
            (
                "参考: 結合待ち",
                [w for r in self.records if (w := r.merge_wait) is not None],
            )
        )
        return [
            StageStats(label, len(v), statistics.median(v), percentile(v, 95), max(v))
            for label, v in columns
            if v
        ]

    def latest_total(self) -> float | None:
        for r in reversed(self.records):
            if r.total is not None:
                return r.total
        return None

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(
            ["no", "recorded_at", "text"]
            + [f"{label}_s" for _, label in STAGES]
            + ["合計_話し終わり→表示_s", "参考_結合待ち_s"]
        )
        for i, r in enumerate(self.records, 1):
            stages = r.stages()
            writer.writerow(
                [
                    i,
                    r.recorded_at.isoformat(timespec="seconds")
                    if r.recorded_at
                    else "",
                    r.text,
                ]
                + [_fmt(stages[key]) for key, _ in STAGES]
                + [_fmt(r.total), _fmt(r.merge_wait)]
            )
        return buf.getvalue()

    def summary_markdown(self) -> str:
        rows = self.summary()
        if not rows:
            return ""
        lines = [
            f"| 区間（{len(self.records)}文） | 中央値 | p95 | 最大 |",
            "|---|---:|---:|---:|",
        ]
        for s in rows:
            lines.append(
                f"| {s.label} | {s.median:.2f}秒 | {s.p95:.2f}秒 | {s.max:.2f}秒 |"
            )
        return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.3f}"


class StepTimer:
    """動画字幕など、工程ごとの所要時間を記録する。"""

    def __init__(self, clock=None) -> None:
        import time

        self._clock = clock or time.perf_counter
        self._started = self._clock()
        self._step_start: float | None = None
        self._step_name = ""
        self.steps: list[tuple[str, float]] = []

    def start(self, name: str) -> None:
        self._step_name = name
        self._step_start = self._clock()

    def stop(self) -> float:
        if self._step_start is None:
            return 0.0
        elapsed = self._clock() - self._step_start
        self.steps.append((self._step_name, elapsed))
        self._step_start = None
        return elapsed

    @property
    def elapsed(self) -> float:
        return self._clock() - self._started

    def summary_lines(self, media_seconds: float | None = None) -> list[str]:
        total = self.elapsed
        lines = ["⏱ 工程ごとの所要時間"]
        for name, sec in self.steps:
            share = f"（{sec / total * 100:.0f}%）" if total > 0 else ""
            lines.append(f"  - {name}: {sec:.1f}秒{share}")
        lines.append(f"  - 合計: {total:.1f}秒")
        if media_seconds:
            lines.append(
                f"  - 動画 {media_seconds:.1f}秒 に対して {total / media_seconds:.2f}倍の時間"
            )
        return lines
