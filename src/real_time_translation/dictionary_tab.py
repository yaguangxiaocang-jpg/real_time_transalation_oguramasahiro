"""Gradio の「📖 辞書」タブ。

辞書（dictionary.csv）の閲覧・編集・保存と、用語候補の抽出・登録をまとめた画面。
ロジックは `translation.dictionary_assist` にあり、ここは画面の組み立てと配線だけ。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import gradio as gr

from real_time_translation.translation.dictionary_assist import (
    CANDIDATE_HEADERS,
    extract_term_candidates,
    extract_text_from_file,
    llm_extract_terms,
    llm_suggest_targets,
    merge_candidates_into_rows,
    normalize_rows,
    read_dictionary_rows,
    review_translation_pairs,
    rows_to_dictionary,
    write_dictionary_rows,
)

DICTIONARY_HEADERS = ["原語", "訳語", "メモ"]
MISS_HEADERS = ["原語", "辞書の訳語", "実際の訳（原文 → 訳文）"]

# 翻訳パイプラインと同じ環境変数を読む（.env の既定は dictionary.csv）。
DEFAULT_DICTIONARY_PATH = os.environ.get("DICTIONARY_PATH") or "dictionary.csv"
ASSIST_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _language_name(display_name: str) -> str:
    """ "Japanese (日本語)" → "Japanese"（LLMプロンプト用）。"""
    return display_name.split(" (")[0].strip() or display_name


def _rows(table: Any) -> list[list[Any]]:
    """gr.Dataframe(type="array") の値を行リストにする（空表は [] / None になりうる）。"""
    if table is None:
        return []
    if isinstance(table, dict):  # {"headers": [...], "data": [...]} 形式
        return [list(r) for r in table.get("data") or []]
    if hasattr(table, "to_numpy"):  # pandas.DataFrame で来た場合
        return table.to_numpy().tolist()
    return [list(r) for r in table]


def _candidate_rows(table: Any) -> list[list[Any]]:
    return [r for r in _rows(table) if len(r) >= 2 and str(r[1] or "").strip()]


def _entry_count(rows: list[list[Any]]) -> int:
    return sum(
        1 for r in normalize_rows(rows) if not r[0].lstrip().startswith("#") and r[1]
    )


def _active_note(path: str) -> str:
    if os.environ.get("DICTIONARY_PATH"):
        return "保存した内容は、次に **Start / Process File / 字幕を生成する** を押したときから翻訳に使われます。"
    return (
        "⚠️ `.env` に `DICTIONARY_PATH` が設定されていないため、この辞書は翻訳に使われていません。"
        f"`.env` に `DICTIONARY_PATH={path}` を追加して再起動してください。"
    )


# ---------------------------------------------------------------------------
# 辞書の読み込み・保存・追加
# ---------------------------------------------------------------------------


def load_dictionary(path: str) -> tuple[list[list[str]], str]:
    path = (path or DEFAULT_DICTIONARY_PATH).strip()
    try:
        rows = read_dictionary_rows(path)
    except Exception as exc:
        return [], f"❌ 読み込みに失敗しました: {exc}"
    if not Path(path).exists():
        return (
            [],
            f"📄 `{path}` はまだありません。用語を追加して保存すると作成されます。\n\n{_active_note(path)}",
        )
    return (
        rows,
        f"📖 `{path}` を読み込みました（{_entry_count(rows)}語）。\n\n{_active_note(path)}",
    )


def save_dictionary(path: str, table: Any) -> tuple[list[list[str]], str]:
    path = (path or DEFAULT_DICTIONARY_PATH).strip()
    rows = _rows(table)
    try:
        report = write_dictionary_rows(path, rows)
    except Exception as exc:
        return normalize_rows(rows), f"❌ 保存に失敗しました: {exc}"
    lines = [f"💾 `{path}` に {report.saved}語を保存しました。"]
    if report.backup_path:
        lines.append(f"（保存前の内容は `{report.backup_path.name}` に退避）")
    if report.skipped_incomplete:
        lines.append(
            "⚠️ 原語か訳語が空のため保存しなかった行: "
            + ", ".join(t or "（空）" for t in report.skipped_incomplete)
        )
    if report.duplicates:
        lines.append(
            "⚠️ 重複している原語（後の行が使われます）: " + ", ".join(report.duplicates)
        )
    lines.append(_active_note(path))
    return read_dictionary_rows(path), "\n\n".join(lines)


def add_single_entry(
    path: str, table: Any, source: str, target: str, notes: str
) -> tuple[list[list[str]], str, str, str, str]:
    source, target, notes = source.strip(), target.strip(), notes.strip()
    rows = _rows(table)
    if not source or not target:
        return rows, "⚠️ 原語と訳語の両方を入力してください。", source, target, notes
    existing = rows_to_dictionary(rows).get(source)
    if existing is not None:
        return (
            rows,
            f"⚠️ `{source}` は登録済みです（訳語: {existing.target_term}）。表で直接編集してください。",
            source,
            target,
            notes,
        )
    new_rows, status = save_dictionary(
        path, normalize_rows(rows) + [[source, target, notes]]
    )
    return (
        new_rows,
        f"➕ `{source} → {target}` を追加しました。\n\n{status}",
        "",
        "",
        "",
    )


# ---------------------------------------------------------------------------
# 用語候補
# ---------------------------------------------------------------------------


def _latest_pairs(
    state: Any, assist_store: dict | None
) -> tuple[list[tuple[str, str]], str]:
    """直近の翻訳結果（実行中のマイク/音声ファイル → 停止したセッション・動画の順）。"""
    history = getattr(state, "history", None)
    if history:
        return list(history), "実行中のセッション"
    if assist_store and assist_store.get("pairs"):
        return list(assist_store["pairs"]), assist_store.get("label", "直近の翻訳")
    return [], ""


def review_latest(
    state: Any, assist_store: dict | None, table: Any, min_count: int
) -> tuple[list[list[str]], list[list[Any]], str]:
    pairs, label = _latest_pairs(state, assist_store)
    if not pairs:
        return (
            [],
            [],
            "ℹ️ まだ翻訳結果がありません。マイク・音声ファイル・動画字幕のいずれかで翻訳してから押してください。",
        )
    review = review_translation_pairs(
        pairs, rows_to_dictionary(_rows(table)), min_count=int(min_count)
    )
    status = (
        f"🔍 {label}（{len(pairs)}文）を確認しました。"
        f"用語漏れ {len(review.misses)}件 / 未登録の用語候補 {len(review.candidates)}件。"
    )
    if review.misses:
        status += (
            "\n\n用語漏れは、辞書にあるのに訳文で使われなかった用語です。"
            "表記揺れ（例: メモリウォール / メモリーウォール）なら辞書の訳語を直してください。"
        )
    return review.misses, [c.to_row() for c in review.candidates], status


def _gather_text(files: Any, pasted: str) -> tuple[str, list[str]]:
    texts: list[str] = []
    errors: list[str] = []
    for f in files or []:
        path = getattr(f, "name", f)
        try:
            texts.append(extract_text_from_file(path))
        except Exception as exc:
            errors.append(f"{Path(str(path)).name}: {exc}")
    if pasted and pasted.strip():
        texts.append(pasted)
    return "\n".join(texts), errors


def extract_from_material(
    files: Any, pasted: str, table: Any, min_count: int
) -> tuple[list[list[Any]], str]:
    text, errors = _gather_text(files, pasted)
    if not text.strip():
        msg = "ℹ️ 講義資料（PDF / テキスト / 字幕）をアップロードするか、テキストを貼り付けてください。"
        if errors:
            msg += "\n\n❌ " + " / ".join(errors)
        return [], msg
    candidates = extract_term_candidates(
        text, rows_to_dictionary(_rows(table)), min_count=int(min_count)
    )
    msg = (
        f"🔍 {len(text):,}文字から未登録の候補を {len(candidates)}件見つけました"
        "（頭字語・モデル名・固有名詞）。小文字の専門用語は「Geminiで抽出」で拾えます。"
    )
    if errors:
        msg += "\n\n❌ 読めなかったファイル: " + " / ".join(errors)
    return [c.to_row() for c in candidates], msg


def _google_key(google_key: str) -> str:
    return (google_key or "").strip() or os.environ.get("GOOGLE_API_KEY", "")


async def extract_with_gemini(
    files: Any,
    pasted: str,
    table: Any,
    google_key: str,
    source_lang: str,
    target_lang: str,
    domain: str,
) -> tuple[list[list[Any]], str]:
    text, errors = _gather_text(files, pasted)
    if not text.strip():
        return [], "ℹ️ 講義資料をアップロードするか、テキストを貼り付けてください。"
    api_key = _google_key(google_key)
    if not api_key:
        return (
            [],
            "❌ Google AI API Key が未設定です（上の API Keys か .env の GOOGLE_API_KEY）。",
        )
    try:
        candidates = await llm_extract_terms(
            text,
            rows_to_dictionary(_rows(table)),
            api_key=api_key,
            model=ASSIST_GEMINI_MODEL,
            source_language=_language_name(source_lang),
            target_language=_language_name(target_lang),
            domain=domain,
        )
    except Exception as exc:
        return [], f"❌ Gemini の呼び出しに失敗しました: {exc}"
    msg = f"✨ Gemini（{ASSIST_GEMINI_MODEL}）が未登録の専門用語を {len(candidates)}件提案しました。訳語を確認してから追加してください。"
    if len(text) > 30000:
        msg += "\n\n⚠️ 資料が長いため、先頭の30,000文字だけを渡しました。"
    if errors:
        msg += "\n\n❌ 読めなかったファイル: " + " / ".join(errors)
    return [c.to_row(checked=True) for c in candidates], msg


async def suggest_targets(
    candidates: Any,
    google_key: str,
    source_lang: str,
    target_lang: str,
    domain: str,
) -> tuple[list[list[Any]], str]:
    rows = _candidate_rows(candidates)
    empty = [str(r[1]).strip() for r in rows if not str(r[2] or "").strip()]
    if not empty:
        return rows, "ℹ️ 訳語が空の候補はありません。"
    api_key = _google_key(google_key)
    if not api_key:
        return (
            rows,
            "❌ Google AI API Key が未設定です（上の API Keys か .env の GOOGLE_API_KEY）。",
        )
    try:
        suggestions = await llm_suggest_targets(
            empty,
            api_key=api_key,
            model=ASSIST_GEMINI_MODEL,
            source_language=_language_name(source_lang),
            target_language=_language_name(target_lang),
            domain=domain,
        )
    except Exception as exc:
        return rows, f"❌ Gemini の呼び出しに失敗しました: {exc}"
    filled = 0
    for r in rows:
        if not str(r[2] or "").strip():
            target = suggestions.get(str(r[1]).strip().lower(), "")
            if target:
                r[2] = target
                filled += 1
    return (
        rows,
        f"✨ {filled}/{len(empty)}件の訳語を提案しました。確認してから追加してください。",
    )


def set_all_checked(candidates: Any, checked: bool) -> list[list[Any]]:
    rows = _candidate_rows(candidates)
    for r in rows:
        r[0] = checked
    return rows


def add_checked_candidates(
    path: str, table: Any, candidates: Any
) -> tuple[list[list[str]], list[list[Any]], str]:
    cand_rows = _candidate_rows(candidates)
    merged, added, missing = merge_candidates_into_rows(_rows(table), cand_rows)
    if not added:
        msg = "ℹ️ 追加する候補がありません。「追加」列にチェックを入れてください。"
        if missing:
            msg += "\n\n⚠️ 訳語が空のため追加できません: " + ", ".join(missing)
        return normalize_rows(_rows(table)), cand_rows, msg
    new_rows, status = save_dictionary(path, merged)
    added_keys = {a.lower() for a in added}
    remaining = [r for r in cand_rows if str(r[1]).strip().lower() not in added_keys]
    msg = f"✅ {len(added)}語を辞書に追加しました: " + ", ".join(added)
    if missing:
        msg += "\n\n⚠️ 訳語が空のため追加しなかった候補: " + ", ".join(missing)
    return new_rows, remaining, f"{msg}\n\n{status}"


# ---------------------------------------------------------------------------
# 画面
# ---------------------------------------------------------------------------


def build_dictionary_tab(
    demo: gr.Blocks,
    state: gr.State,
    assist_store: gr.State,
    google_key_input: gr.Textbox,
    source_lang_input: gr.Dropdown,
    target_lang_input: gr.Dropdown,
    domain_input: gr.Dropdown,
) -> None:
    """`gr.Tabs()` の中で呼ぶ。"""
    with gr.TabItem("📖 辞書"):
        gr.Markdown(
            "専門用語の訳し方を固定する辞書です。訳語を原語と同じにすると「そのまま使う」用語"
            "（例: `GPT-3,GPT-3`）、誤認識された形を原語にすると補正用（例: `TIFINE,T5`）になります。"
        )
        with gr.Row():
            path_input = gr.Textbox(
                value=DEFAULT_DICTIONARY_PATH,
                label="辞書ファイル",
                scale=4,
            )
            reload_btn = gr.Button("🔄 読み込み", scale=1)
        dict_status = gr.Markdown()

        with gr.Row():
            new_source = gr.Textbox(
                label="原語", placeholder="例: mixture of experts", scale=3
            )
            new_target = gr.Textbox(
                label="訳語", placeholder="例: 混合エキスパート", scale=3
            )
            new_notes = gr.Textbox(
                label="メモ（任意）", placeholder="例: MoE の正式名称", scale=3
            )
            add_btn = gr.Button("➕ 追加", variant="primary", scale=1)

        dict_table = gr.Dataframe(
            headers=DICTIONARY_HEADERS,
            datatype="str",
            type="array",
            column_count=3,
            interactive=True,
            show_search="filter",
            max_height=420,
            wrap=True,
            label="辞書（セルを直接編集できます。`#` で始まる行は見出しコメント）",
        )
        save_btn = gr.Button("💾 表の内容を保存", variant="primary")

        gr.Markdown("### 🔍 辞書に足りない用語を探す")
        min_count_input = gr.Slider(
            1,
            5,
            value=2,
            step=1,
            label="固有名詞は何回以上出たら候補にするか（頭字語・モデル名は1回でも候補にします）",
        )
        with gr.Tabs():
            with gr.TabItem("直近の翻訳結果から"):
                gr.Markdown(
                    "マイク・音声ファイル・動画字幕で翻訳した結果を見て、"
                    "①辞書にあるのに訳文で使われなかった用語（用語漏れ）と、②辞書にない用語を出します。"
                )
                review_btn = gr.Button("🔍 直近の翻訳結果を確認", variant="primary")
                miss_table = gr.Dataframe(
                    headers=MISS_HEADERS,
                    datatype="str",
                    type="array",
                    column_count=3,
                    interactive=False,
                    wrap=True,
                    max_height=240,
                    label="用語漏れ（辞書の訳語が使われなかった用語）",
                )
            with gr.TabItem("講義資料・テキストから"):
                material_files = gr.File(
                    label="講義資料（PDF / TXT / MD / SRT / VTT、複数可）",
                    file_count="multiple",
                    file_types=[".pdf", ".txt", ".md", ".srt", ".vtt"],
                )
                material_text = gr.Textbox(
                    label="またはテキストを貼り付け（文字起こし・スライド原稿など）",
                    lines=5,
                )
                with gr.Row():
                    rule_btn = gr.Button(
                        "🔍 抽出（無料・すぐ終わる）", variant="primary"
                    )
                    llm_btn = gr.Button("✨ Geminiで抽出（訳語も提案）")

        assist_status = gr.Markdown()
        candidate_table = gr.Dataframe(
            headers=CANDIDATE_HEADERS,
            datatype=["bool", "str", "str", "number", "str", "str"],
            type="array",
            column_count=6,
            interactive=True,
            wrap=True,
            max_height=420,
            static_columns=[3, 4, 5],
            label="用語候補（「追加」にチェックし、訳語を確認・編集してから追加してください）",
        )
        with gr.Row():
            check_all_btn = gr.Button("☑ すべてチェック")
            uncheck_all_btn = gr.Button("☐ すべて外す")
            suggest_btn = gr.Button("✨ 空の訳語をGeminiで提案")
            add_candidates_btn = gr.Button(
                "✅ チェックした候補を辞書に追加", variant="primary"
            )

        lang_inputs = [
            google_key_input,
            source_lang_input,
            target_lang_input,
            domain_input,
        ]

        demo.load(
            load_dictionary, inputs=[path_input], outputs=[dict_table, dict_status]
        )
        reload_btn.click(
            load_dictionary, inputs=[path_input], outputs=[dict_table, dict_status]
        )
        save_btn.click(
            save_dictionary,
            inputs=[path_input, dict_table],
            outputs=[dict_table, dict_status],
        )
        add_btn.click(
            add_single_entry,
            inputs=[path_input, dict_table, new_source, new_target, new_notes],
            outputs=[dict_table, dict_status, new_source, new_target, new_notes],
        )
        review_btn.click(
            review_latest,
            inputs=[state, assist_store, dict_table, min_count_input],
            outputs=[miss_table, candidate_table, assist_status],
        )
        rule_btn.click(
            extract_from_material,
            inputs=[material_files, material_text, dict_table, min_count_input],
            outputs=[candidate_table, assist_status],
        )
        llm_btn.click(
            extract_with_gemini,
            inputs=[material_files, material_text, dict_table, *lang_inputs],
            outputs=[candidate_table, assist_status],
        )
        check_all_btn.click(
            lambda c: set_all_checked(c, True),
            inputs=[candidate_table],
            outputs=[candidate_table],
        )
        uncheck_all_btn.click(
            lambda c: set_all_checked(c, False),
            inputs=[candidate_table],
            outputs=[candidate_table],
        )
        suggest_btn.click(
            suggest_targets,
            inputs=[candidate_table, *lang_inputs],
            outputs=[candidate_table, assist_status],
        )
        add_candidates_btn.click(
            add_checked_candidates,
            inputs=[path_input, dict_table, candidate_table],
            outputs=[dict_table, candidate_table, assist_status],
        )
