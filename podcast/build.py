#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "podcast" / "G検定模試1_問題1-145.csv"
OUT = ROOT / "podcast-output"
SEGMENTS = OUT / "segments"
EPISODES = OUT / "episodes"
FULL_MP3 = OUT / "G検定模試1_Podcast教材音声_全編.mp3"
TRANSCRIPT = OUT / "G検定模試1_Podcast台本.txt"
MANIFEST = OUT / "G検定模試1_Podcast_manifest.json"
REPORT = OUT / "G検定模試1_Podcast検証結果.txt"

FEMALE = "ja-JP-NanamiNeural"
MALE = "ja-JP-KeitaNeural"
RANGES = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75),
          (76, 90), (91, 105), (106, 120), (121, 135), (136, 145)]

# Longer phrases first. These substitutions improve Japanese TTS pronunciation.
PRONUNCIATION = [
    ("Human-in-the-loop", "ヒューマン・イン・ザ・ループ"),
    ("Multi-Head Attention", "マルチヘッド・アテンション"),
    ("Global Average Pooling", "グローバル・アベレージ・プーリング"),
    ("Layer Normalization", "レイヤー・ノーマライゼーション"),
    ("Batch Normalization", "バッチ・ノーマライゼーション"),
    ("Contrastive Learning", "コントラスティブ・ラーニング"),
    ("Prompt Engineering", "プロンプト・エンジニアリング"),
    ("Foundation Model", "ファウンデーション・モデル"),
    ("Object Detection", "オブジェクト・ディテクション"),
    ("Fraud Detection", "フロード・ディテクション"),
    ("Early Stopping", "アーリー・ストッピング"),
    ("Residual Connection", "レジデュアル・コネクション"),
    ("Skip Connection", "スキップ・コネクション"),
    ("Self-Attention", "セルフ・アテンション"),
    ("Causal Mask", "コーザル・マスク"),
    ("Chain-of-Thought", "チェイン・オブ・ソート"),
    ("Few-shot Learning", "フューショット・ラーニング"),
    ("Zero-shot", "ゼロショット"),
    ("Word2Vec", "ワード・ツー・ベック"),
    ("Transformer", "トランスフォーマー"),
    ("Attention", "アテンション"),
    ("Softmax", "ソフトマックス"),
    ("AlexNet", "アレックスネット"),
    ("ResNet", "レズネット"),
    ("GoogleNet", "グーグルネット"),
    ("ImageNet", "イメージネット"),
    ("Deep Blue", "ディープ・ブルー"),
    ("DeepMind", "ディープマインド"),
    ("AlphaGo", "アルファ碁"),
    ("MLflow", "エムエルフロー"),
    ("ML4ow", "エムエルフロー"),
    ("MLUow", "エムエルフロー"),
    ("ILSVRC", "アイエルエスブイアールシー"),
    ("OECD", "オーイーシーディー"),
    ("MYCIN", "マイシン"),
    ("ROC-AUC", "アールオーシー・エーユーシー"),
    ("ReLU", "レルー"),
    ("Xavier", "ザビエル"),
    ("LSTM", "エルエスティーエム"),
    ("GRU", "ジーアールユー"),
    ("CNN", "シーエヌエヌ"),
    ("RNN", "アールエヌエヌ"),
    ("LLM", "エルエルエム"),
    ("RAG", "ラグ"),
    ("GAN", "ギャン"),
    ("VAE", "ブイエーイー"),
    ("SVM", "エスブイエム"),
    ("PCA", "ピーシーエー"),
    ("MSE", "エムエスイー"),
    ("XAI", "エックスエーアイ"),
    ("BERT", "バート"),
    ("GPT", "ジーピーティー"),
    ("PoC", "ピーオーシー"),
    ("API", "エーピーアイ"),
    ("NDA", "エヌディーエー"),
    ("AUC", "エーユーシー"),
    ("ROC", "アールオーシー"),
    ("KL", "ケーエル"),
    ("EU", "イーユー"),
    ("AI", "エーアイ"),
]


def run(*args: str) -> str:
    result = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    return result.stdout.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def duration(path: Path) -> float:
    return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(path)))


def speakable(text: str) -> str:
    text = re.sub(r"\s+", " ", text.replace("‧", "・").replace("`", "")).strip()
    text = text.replace("TP/(TP+FN)", "ティーピー割る、ティーピー足すエフエヌ")
    text = text.replace("TP/(TP+FP)", "ティーピー割る、ティーピー足すエフピー")
    text = text.replace("P(A∩B) = P(A)P(B)", "ピー、エーかつビー、イコール、ピーエーかけるピービー")
    text = text.replace("P(A|B)", "ピー、エー、条件、ビー")
    text = text.replace("A*", "エースター").replace("αβ", "アルファベータ")
    text = text.replace("k-means", "ケー・ミーンズ").replace("p値", "ピー値")
    for source, target in PRONUNCIATION:
        text = text.replace(source, target)
    return text


def load_questions() -> list[dict[str, object]]:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 145, len(rows)
    assert [r["ID"] for r in rows] == [str(i) for i in range(1, 146)]
    questions = []
    for row in rows:
        questions.append({
            "id": int(row["ID"]),
            "category": row["カテゴリ"].strip(),
            "prompt": row["問題文"].strip(),
            "choices": {letter: row[f"選択肢{letter}"].strip() for letter in "ABCD"},
            "answer": row["正解"].strip().upper(),
            "explanation": row["解説文"].strip(),
        })
    return questions


def turn(speaker: str, text: str, pause: float = 0.45, kind: str = "dialogue") -> dict[str, object]:
    return {"speaker": speaker, "text": text, "pause": pause, "kind": kind}


def point(q: dict[str, object]) -> str:
    answer = str(q["answer"])
    choices = q["choices"]
    assert isinstance(choices, dict)
    return f"問題{q['id']}は、{choices.get(answer, '')}"


def episode_turns(ep: int, qs: list[dict[str, object]]) -> list[dict[str, object]]:
    start, end = qs[0]["id"], qs[-1]["id"]
    turns = [
        turn("female", f"G検定模試ラジオ、第{ep}回です。今回は問題{start}から問題{end}まで。"
             "私、女性進行役のミナが問題と選択肢を読み、男性解説役のケンが正解と理由を説明します。"
             "問題の後には考える時間を入れます。では、始めましょう。", 0.5, "intro"),
        turn("male", "解説役のケンです。正解の文字だけではなく、なぜその選択肢なのかを短く整理します。"
             "迷った問題は、解説のキーワードを耳で拾ってください。", 0.7, "intro-response"),
    ]
    recent: list[dict[str, object]] = []
    for index, q in enumerate(qs):
        choices = q["choices"]
        assert isinstance(choices, dict)
        answer = str(q["answer"])
        if not answer or not any(str(v) for v in choices.values()):
            turns.append(turn("female", f"続いて問題{q['id']}です。この問題は元のPDFで正解済みだったため、"
                              "復習欄に問題文と選択肢が掲載されていません。内容は推測せず、欠番として次へ進みます。",
                              0.8, "missing"))
            continue
        lead = "最初の問題です" if index == 0 else "前のポイントを押さえて、次の問題です"
        option_text = "。".join(f"選択肢{letter}、{choices[letter]}" for letter in "ABCD")
        turns.append(turn("female", f"{lead}。問題{q['id']}。カテゴリは、{q['category']}。"
                          f"{q['prompt']}。{option_text}。答えを一つ選んでください。", 3.0, "question"))
        turns.append(turn("male", f"正解は、{answer}、{choices[answer]}です。そうですね。解説します。"
                          f"{q['explanation']}", 0.65, "answer"))
        recent.append(q)
        if len(recent) == 5:
            summary = "。".join(point(item) for item in recent)
            turns.append(turn("female", f"ここで小まとめです。{summary}。"
                              "用語と役割の対応を、自分の言葉で言い直してみましょう。", 0.85, "checkpoint"))
            recent = []
    if recent:
        summary = "。".join(point(item) for item in recent)
        turns.append(turn("female", f"最後の小まとめです。{summary}。", 0.8, "checkpoint"))
    valid = [q for q in qs if str(q["answer"])]
    picks = [valid[0], valid[len(valid) // 2], valid[-1]] if valid else []
    final_points = "。".join(point(q) for q in dict.fromkeys(map(id, picks))) if False else "。".join(point(q) for q in picks)
    turns.extend([
        turn("male", "今回の解説は以上です。最後に、ミナさんから重要ポイントをまとめてもらいましょう。",
             0.45, "handoff"),
        turn("female", f"今回の最終まとめです。{final_points}。"
             "答えの記号だけでなく、正解選択肢の意味まで説明できる状態を目指してください。"
             f"G検定模試ラジオ、第{ep}回はここまでです。", 1.0, "outro"),
    ])
    return turns


def key_for(t: dict[str, object]) -> str:
    raw = f"{t['speaker']}|{t['kind']}|{t['text']}".encode()
    return hashlib.sha256(raw).hexdigest()[:20]


async def synthesize(t: dict[str, object], path: Path, sem: asyncio.Semaphore) -> None:
    if path.exists() and path.stat().st_size > 1000:
        return
    voice = FEMALE if t["speaker"] == "female" else MALE
    rate = "+4%" if t["speaker"] == "female" else "+0%"
    pitch = "+1Hz" if t["speaker"] == "female" else "-2Hz"
    async with sem:
        for attempt in range(1, 7):
            tmp = path.with_suffix(".tmp.mp3")
            tmp.unlink(missing_ok=True)
            try:
                await edge_tts.Communicate(speakable(str(t["text"])), voice,
                                           rate=rate, pitch=pitch).save(str(tmp))
                if tmp.stat().st_size < 1000:
                    raise RuntimeError("undersized TTS output")
                tmp.replace(path)
                return
            except Exception as exc:
                tmp.unlink(missing_ok=True)
                if attempt == 6:
                    raise RuntimeError(f"TTS failed after retries: {path.name}: {exc}") from exc
                await asyncio.sleep(min(30, (2 ** attempt) + random.random()))


async def synthesize_all(turns: list[dict[str, object]]) -> None:
    unique = {key_for(t): t for t in turns}
    sem = asyncio.Semaphore(2)
    tasks = [asyncio.create_task(synthesize(t, SEGMENTS / f"{key}.mp3", sem))
             for key, t in unique.items()]
    total = len(tasks)
    for done, task in enumerate(asyncio.as_completed(tasks), 1):
        await task
        if done % 20 == 0 or done == total:
            print(f"TTS {done}/{total}", flush=True)


def silence(seconds: float) -> Path:
    path = SEGMENTS / f"silence-{str(seconds).replace('.', '_')}.mp3"
    if not path.exists():
        run("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "anullsrc=r=24000:cl=mono", "-t", str(seconds), "-c:a", "libmp3lame", "-b:a", "64k", str(path))
    return path


def concat(paths: list[Path], output: Path) -> None:
    listing = output.with_suffix(".concat.txt")
    with listing.open("w", encoding="utf-8") as f:
        for path in paths:
            f.write("file '" + str(path.resolve()).replace("'", "'\\''") + "'\n")
    run("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(listing), "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", str(output))
    listing.unlink(missing_ok=True)
    if output.stat().st_size < 100_000:
        raise RuntimeError(f"audio output is too small: {output}")


def main() -> None:
    for command in ("ffmpeg", "ffprobe"):
        if shutil.which(command) is None:
            raise RuntimeError(f"missing command: {command}")
    OUT.mkdir(exist_ok=True)
    SEGMENTS.mkdir(exist_ok=True)
    EPISODES.mkdir(exist_ok=True)
    questions = load_questions()
    by_id = {int(q["id"]): q for q in questions}
    episode_data = []
    all_turns: list[dict[str, object]] = []
    for ep, (start, end) in enumerate(RANGES, 1):
        qs = [by_id[i] for i in range(start, end + 1)]
        turns = episode_turns(ep, qs)
        episode_data.append((ep, start, end, turns))
        all_turns.extend(turns)

    transcript_lines = [
        "G検定模試1 Podcast教材音声 台本", "",
        f"女性: {FEMALE}（問題・進行・まとめ）",
        f"男性: {MALE}（正解・解説）",
        "問題2は元PDFの復習欄に未掲載のため、推測せず欠番として扱う。", "",
    ]
    for ep, start, end, turns in episode_data:
        transcript_lines += ["=" * 72, f"第{ep}回　問題{start}〜{end}", "=" * 72]
        for t in turns:
            label = "女性" if t["speaker"] == "female" else "男性"
            transcript_lines.append(f"[{label}/{t['kind']}] {t['text']}")
            if float(t["pause"]) >= 1.0:
                transcript_lines.append(f"[無音 {float(t['pause']):.1f}秒]")
        transcript_lines.append("")
    TRANSCRIPT.write_text("\n".join(transcript_lines), encoding="utf-8")

    asyncio.run(synthesize_all(all_turns))
    episode_files: list[Path] = []
    episodes_manifest = []
    for ep, start, end, turns in episode_data:
        pieces: list[Path] = []
        for t in turns:
            pieces.append(SEGMENTS / f"{key_for(t)}.mp3")
            if float(t["pause"]) > 0:
                pieces.append(silence(float(t["pause"])))
        out = EPISODES / f"G検定模試1_Podcast_第{ep:02d}回_問題{start:03d}-{end:03d}.mp3"
        concat(pieces, out)
        episode_files.append(out)
        episodes_manifest.append({"episode": ep, "questions": f"{start}-{end}",
                                  "file": out.name, "durationSeconds": round(duration(out), 2),
                                  "sizeBytes": out.stat().st_size, "sha256": sha256(out)})
        print(f"episode {ep}/10 completed", flush=True)
    concat(episode_files, FULL_MP3)

    data = {
        "state": "completed",
        "title": "G検定模試1 Podcast教材音声",
        "sourceRows": len(questions),
        "answeredQuestions": sum(bool(q["answer"]) for q in questions),
        "missingQuestionIds": [q["id"] for q in questions if not q["answer"]],
        "femaleVoice": FEMALE,
        "maleVoice": MALE,
        "fullFile": FULL_MP3.name,
        "fullDurationSeconds": round(duration(FULL_MP3), 2),
        "fullSizeBytes": FULL_MP3.stat().st_size,
        "fullSha256": sha256(FULL_MP3),
        "episodes": episodes_manifest,
    }
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "G検定模試1 Podcast教材音声 検証結果",
        "state: completed",
        f"source_rows: {data['sourceRows']}",
        f"answered_questions: {data['answeredQuestions']}",
        f"missing_question_ids: {data['missingQuestionIds']}",
        f"episode_count: {len(episodes_manifest)}",
        f"full_duration_seconds: {data['fullDurationSeconds']}",
        f"full_duration_minutes: {data['fullDurationSeconds'] / 60:.2f}",
        f"full_size_bytes: {data['fullSizeBytes']}",
        f"full_sha256: {data['fullSha256']}",
    ]
    for ep in episodes_manifest:
        lines.append(f"episode_{ep['episode']:02d}: {ep['questions']}, {ep['durationSeconds'] / 60:.2f} min, "
                     f"{ep['sizeBytes']} bytes, sha256={ep['sha256']}")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.rmtree(SEGMENTS, ignore_errors=True)
    print(json.dumps(data, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        raise
