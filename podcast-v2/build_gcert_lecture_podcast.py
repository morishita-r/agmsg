#!/usr/bin/env python3
from __future__ import annotations
import asyncio, csv, hashlib, json, re, shutil, subprocess, time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "podcast-v2" / "G検定模試1_問題1-145.csv"
OUT = ROOT / "lecture-podcast-output"
SEG = OUT / "segments"
EPS = OUT / "episodes"
TRANSCRIPT = OUT / "G検定模試1_講義Podcast_台本.txt"
MANIFEST = OUT / "G検定模試1_講義Podcast_manifest.json"
REPORT = OUT / "G検定模試1_講義Podcast_検証結果.txt"
FULL = OUT / "G検定模試1_講義Podcast_全編.mp3"

FEMALE_VOICE="ja-JP-NanamiNeural"
MALE_VOICE="ja-JP-KeitaNeural"
FEMALE_RATE="+5%"
MALE_RATE="+1%"

CATEGORY_ORDER = [
    "人工知能（AI）とは",
    "人工知能をめぐる動向",
    "AIに必要な数理‧統計知識",
    "機械学習の概要‧具体的手法",
    "ディープラーニングの概要",
    "ディープラーニングの要素技術",
    "ディープラーニングの応用例",
    "AIの社会実装に向けて",
    "AIに関する法律と契約",
    "AI倫理‧AIガバナンス",
]
CATEGORY_TITLES = {
    "人工知能（AI）とは":"AIとは何か――まず言葉の地図を作る",
    "人工知能をめぐる動向":"AI史と探索――ブームの理由を流れで理解する",
    "AIに必要な数理‧統計知識":"数理・統計――式より先に意味をつかむ",
    "機械学習の概要‧具体的手法":"機械学習――学習の種類と代表手法を見分ける",
    "ディープラーニングの概要":"ディープラーニング基礎――学習が進む仕組み",
    "ディープラーニングの要素技術":"要素技術――CNNからTransformerまでをつなぐ",
    "ディープラーニングの応用例":"応用――画像・言語・生成AIをタスクで整理する",
    "AIの社会実装に向けて":"社会実装――PoCで終わらせず運用まで設計する",
    "AIに関する法律と契約":"法律と契約――データ・権利・責任の境界線",
    "AI倫理‧AIガバナンス":"倫理とガバナンス――安全・公平・透明性をどう守るか",
}
OPENERS = {
    "人工知能（AI）とは":"この章は、AIという言葉の射程をそろえる回です。強いAIと弱いAI、生成AI、AI効果のように、似て見えて前提の違う概念を区別できることが土台になります。",
    "人工知能をめぐる動向":"この章は年号の暗記ではなく、何ができるようになって期待が膨らみ、どこで限界に当たり、次の技術へ移ったのかという因果で見ます。",
    "AIに必要な数理‧統計知識":"この章は計算問題の回ではありません。確率、分布、評価指標、ベクトルが何を測っているのかを言葉で説明できる状態を作ります。",
    "機械学習の概要‧具体的手法":"この章の中心は、データに正解があるのか、何を予測したいのか、どんな構造を見つけたいのか。この三点から手法を選び分けることです。",
    "ディープラーニングの概要":"この章はニューラルネットワークがどう学習し、なぜ学習が失敗するのかを一つの流れで見ます。損失、勾配、初期化、正規化、過学習がつながれば強いです。",
    "ディープラーニングの要素技術":"この章は部品の名前をばらばらに覚えないのがコツです。画像なら畳み込み、系列なら注意機構というように、何を解決する部品かで整理します。",
    "ディープラーニングの応用例":"この章はモデル名よりタスクで整理します。分類、検出、セグメンテーション、生成、言語処理など、入力と出力の形から見分けます。",
    "AIの社会実装に向けて":"この章では、精度の高いモデルを作ることと、価値のあるAIシステムを運用することは別だと捉えます。問題設定、データ品質、監視、再学習までが一続きです。",
    "AIに関する法律と契約":"この章は、AIなら自由に使えるという発想を捨てるところから始めます。著作権、個人情報、契約、営業秘密など、対象ごとに確認すべき権利が違います。",
    "AI倫理‧AIガバナンス":"この章は抽象論ではなく、AIの誤りが誰にどんな不利益を与えるかを起点に、安全性、公平性、透明性、人間の監督を整理します。",
}
HOST_QUESTIONS = [
    "今の話、試験で迷ったときは何を手掛かりに切り分ければいいですか？",
    "ここまでを一段抽象化すると、共通して見ている軸は何でしょう？",
    "用語だけ覚えると混ざりそうです。違いを一言で残すならどうなりますか？",
    "実務の場面に置き換えると、どこを見落とすと危ないですか？",
]
@dataclass
class Q:
    qid:int; category:str; prompt:str; choices:dict[str,str]; answer:str; explanation:str
@dataclass
class Turn:
    speaker:str; text:str; pause:float=0.45; kind:str="dialogue"

def run(cmd):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

def load():
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rs=list(csv.DictReader(f))
    assert len(rs)==145 and [r["ID"] for r in rs]==[str(i) for i in range(1,146)]
    qs=[]
    for r in rs:
        qs.append(Q(int(r["ID"]),r["カテゴリ"].strip(),r["問題文"].strip(),
                    {k:r.get("選択肢"+k,"").strip() for k in "ABCD"},
                    r.get("正解","").strip().upper(),r.get("解説文","").strip()))
    return qs

def label(q:Q):
    m=re.search(r"「([^」]+)」", q.prompt)
    if m and "間違えた問題" not in m.group(1): return m.group(1)
    a=q.choices.get(q.answer,"")
    if a and len(a)<=34: return a
    x=re.sub(r"として.*","",q.prompt)
    x=re.sub(r"に関する.*","",x)
    x=x.replace("最も適切なものはどれか。","")
    return x[:34].strip("。、 ")

def compact(s:str):
    return re.sub(r"\s+"," ",s).strip()

def anchor(q:Q):
    a=q.choices.get(q.answer,"")
    return compact(a) if a else ""

def lecture_turn(block:list[Q], idx:int):
    parts=[]
    starters=["まず","次に","そして"]
    for i,q in enumerate(block):
        parts.append(f"{starters[min(i,2)]}、{label(q)}。{compact(q.explanation)}")
    if len(block)>=2:
        parts.append("ここは個別用語として切り離すより、何を入力として、何を判断・生成・評価しているのかという役割でつなぐと覚えやすくなります。")
    return Turn("male"," ".join(parts),0.55,"lecture")

def exam_lens(block:list[Q]):
    items=[]
    for q in block:
        a=anchor(q)
        if a:
            items.append(f"{label(q)}は『{a}』が核")
    return "。".join(items[:3])+"。"

def build_episode(ep:int, cat:str, qs:list[Q]):
    title=CATEGORY_TITLES[cat]
    turns=[
        Turn("female",f"G検定・講義ポッドキャスト、第{ep}講。テーマは『{title}』です。今回は問題を一問ずつ解くのではなく、このカテゴリの考え方を一本の流れで理解します。",0.6,"intro"),
        Turn("male",OPENERS[cat],0.6,"overview"),
    ]
    for bi in range(0,len(qs),3):
        block=qs[bi:bi+3]
        turns.append(lecture_turn(block,bi//3))
        turns.append(Turn("female",HOST_QUESTIONS[(bi//3)%len(HOST_QUESTIONS)],0.35,"host-question"))
        turns.append(Turn("male","見分け方を短く置いておきます。"+exam_lens(block),0.6,"exam-lens"))
        if ((bi//3)+1)%2==0:
            targets=[q for q in block if q.answer]
            if targets:
                q=targets[-1]
                turns.append(Turn("female",f"ここで30秒チェックです。{label(q)}について、正解の核を自分の言葉で一つ言ってみてください。",2.8,"recall"))
                turns.append(Turn("male",f"確認です。{anchor(q)}。{compact(q.explanation)}",0.6,"recall-answer"))
    last=[q for q in qs[-3:] if q.answer]
    recap=" ".join(f"{label(q)}は、{anchor(q)}。" for q in last)
    turns += [
        Turn("female","最後に、この講義を三つの視点でまとめましょう。用語名ではなく、何を見分けるための概念だったかを思い出してください。",0.4,"summary-cue"),
        Turn("male",f"この章のまとめです。{recap} そして、迷ったときは定義だけでなく、入力、出力、目的、リスクのどこを問われているかに戻ってください。",0.7,"summary"),
        Turn("female",f"第{ep}講はここまでです。次に進む前に、今日出た概念を三つだけ声に出して説明できるか確認してみてください。",0.9,"outro"),
    ]
    return turns

def speech_text(t):
    t=t.replace("‧","・").replace("αβ","アルファベータ").replace("A*","エースター")
    reps={
      "LLM":"エルエルエム","RAG":"ラグ","CNN":"シーエヌエヌ","RNN":"アールエヌエヌ",
      "LSTM":"エルエスティーエム","GRU":"ジーアールユー","GAN":"ギャン","VAE":"ブイエーイー",
      "SVM":"エスブイエム","PCA":"ピーシーエー","MSE":"エムエスイー","XAI":"エックスエーアイ",
      "BERT":"バート","GPT":"ジーピーティー","PoC":"ピーオーシー","API":"エーピーアイ",
      "NDA":"エヌディーエー","OECD":"オーイーシーディー","EU":"イーユー","AI":"エーアイ",
      "Self-Attention":"セルフアテンション","Multi-Head Attention":"マルチヘッドアテンション",
      "Attention":"アテンション","Transformer":"トランスフォーマー","Word2Vec":"ワードツーベック",
      "Softmax":"ソフトマックス","ReLU":"レルー","Zero-shot":"ゼロショット",
    }
    for k,v in sorted(reps.items(), key=lambda x:-len(x[0])): t=t.replace(k,v)
    t=re.sub(r"\s+"," ",t)
    return t

def key(turn:Turn):
    return hashlib.sha256((turn.speaker+"|"+turn.text).encode()).hexdigest()[:20]

async def synth(turn:Turn, path:Path, sem):
    if path.exists() and path.stat().st_size>1000:return
    import edge_tts
    async with sem:
        voice=FEMALE_VOICE if turn.speaker=="female" else MALE_VOICE
        rate=FEMALE_RATE if turn.speaker=="female" else MALE_RATE
        for attempt in range(5):
            try:
                comm=edge_tts.Communicate(speech_text(turn.text),voice=voice,rate=rate)
                await comm.save(str(path))
                if path.exists() and path.stat().st_size>1000:return
            except Exception:
                if attempt==4: raise
                await asyncio.sleep(1.5*(attempt+1))

def concat(inputs:list[Path], output:Path):
    lst=output.with_suffix(".concat.txt")
    lst.write_text("\n".join("file '"+str(p).replace("'","'\\''")+"'" for p in inputs),encoding="utf-8")
    run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i",str(lst),"-c:a","libmp3lame","-b:a","64k","-ar","24000","-ac","1",str(output)])

def duration(p:Path):
    x=run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(p)])
    return float(x.stdout.strip())

async def main():
    OUT.mkdir(exist_ok=True); SEG.mkdir(exist_ok=True); EPS.mkdir(exist_ok=True)
    qs=load()
    missing=[q for q in qs if not q.answer]
    usable=[q for q in qs if q.answer and q.category in CATEGORY_ORDER]
    episodes=[]
    all_turns=[]
    transcript=["G検定模試1 講義Podcast 改訂版\n",
                "設計: カテゴリ別講義。選択肢の逐次読み上げをやめ、講師が概念をつなげ、女性ホストが疑問・要約・確認を担当。\n",
                f"元CSV: 145行。音声で扱う問題由来の論点: {len(usable)}件。問題2は元資料未掲載のため音声内容には推測で補完しない。\n\n"]
    for ep,cat in enumerate(CATEGORY_ORDER,1):
        cqs=[q for q in usable if q.category==cat]
        turns=build_episode(ep,cat,cqs)
        episodes.append((ep,cat,cqs,turns))
        transcript.append(f"\n===== 第{ep}講 {CATEGORY_TITLES[cat]} =====\n")
        for t in turns:
            transcript.append(("女性ホスト" if t.speaker=="female" else "男性講師")+": "+t.text+"\n")
        all_turns.extend(turns)
    TRANSCRIPT.write_text("".join(transcript),encoding="utf-8")
    sem=asyncio.Semaphore(8)
    unique={key(t):t for t in all_turns}
    await asyncio.gather(*[synth(t,SEG/f"{k}.mp3",sem) for k,t in unique.items()])
    ep_files=[]
    manifest={"source_rows":145,"covered_source_questions":[q.qid for q in usable],"missing_source_question_ids":[q.qid for q in missing],"episodes":[]}
    for ep,cat,cqs,turns in episodes:
        inputs=[]
        for t in turns:
            audio=SEG/f"{key(t)}.mp3"; inputs.append(audio)
            if t.pause>0:
                pause=SEG/f"pause_{int(t.pause*1000)}.mp3"
                if not pause.exists():
                    run(["ffmpeg","-y","-v","error","-f","lavfi","-i","anullsrc=r=24000:cl=mono","-t",str(t.pause),"-c:a","libmp3lame","-b:a","64k",str(pause)])
                inputs.append(pause)
        out=EPS/f"G検定模試1_講義Podcast_第{ep:02d}講.mp3"
        concat(inputs,out); ep_files.append(out)
        d=duration(out)
        manifest["episodes"].append({"episode":ep,"category":cat,"title":CATEGORY_TITLES[cat],"source_question_ids":[q.qid for q in cqs],"duration_seconds":round(d,2),"bytes":out.stat().st_size,"sha256":hashlib.sha256(out.read_bytes()).hexdigest()})
    concat(ep_files,FULL)
    full_d=duration(FULL)
    manifest["full"]={"duration_seconds":round(full_d,2),"bytes":FULL.stat().st_size,"sha256":hashlib.sha256(FULL.read_bytes()).hexdigest()}
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    for p in ep_files+[FULL]:
        run(["ffmpeg","-v","error","-i",str(p),"-f","null","-"])
    REPORT.write_text(
        "G検定模試1 講義Podcast 改訂版 検証結果\n"
        f"- 元CSV: 145行\n- 音声に反映した問題由来論点: {len(usable)}件\n"
        f"- 元資料未掲載: {[q.qid for q in missing]}\n- エピソード: {len(ep_files)}本\n"
        f"- 全編再生時間: {full_d/60:.1f}分\n- 全MP3: ffmpegデコード検証成功\n"
        f"- 全編SHA-256: {manifest['full']['sha256']}\n",
        encoding="utf-8")
    print(json.dumps({"episodes":len(ep_files),"minutes":round(full_d/60,1),"covered":len(usable)},ensure_ascii=False))

if __name__=="__main__":
    asyncio.run(main())
