# 설치 마법사: 이 PC의 카카오톡을 스캔해 오더방 목록·담당자·알림 방을 만든다.
#
#   python -I -X utf8 설치.py            (설치하기.bat 을 더블클릭해도 된다)
#
# 하는 일
#   1) 카톡 채팅 목록을 읽어 방 이름을 보여 주고, 오더방으로 쓸 방을 고르게 한다.
#   2) 고른 방을 화면 밖에서 하나씩 열어 (실제 창 제목 · 최근 대화의 보낸 사람)을 읽는다. 방은 읽음 처리된다.
#   3) 문의 글을 올리는 사람 = 본사 직원, 그 밖에 자주 말하는 사람 = 지점 담당자 후보로 제안한다. 사용자가 고친다.
#   4) 미회신이 확인되면 알림을 올릴 카톡방을 고르게 한다.
#   5) 설정.json · 오더방_목록.md · 알림설정.json 을 만든다(기존 파일은 .bak-시각 으로 백업).
# 키보드·마우스·클립보드는 쓰지 않는다(감시와 같은 창 메시지 방식). 설치하는 동안 카톡 창에 글자를 입력하지 마세요.
import argparse
import collections
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

os.environ["ORDER_SETUP"] = "1"                              # 설정.json 이 아직 없어도 오더방_감시.py 를 가져올 수 있게
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import 오더방_감시 as M  # noqa: E402

PROGRESS = BASE / "설치_진행.json"                           # 방 스캔 결과 캐시(중간에 끊겨도 이어서)
WHEN = re.compile(r"^(오전|오후)\s*\d{1,2}\D?\d{2}$|^어제$|^\d{4}-\d{2}-\d{2}$|^\d{1,2}월\s*\d{1,2}일$")   # 목록 오른쪽 시각
NOISE = re.compile(r"[가-힣]{2,}")                            # 한글 두 글자 이상이 있어야 사람 이름으로 본다 (OCR 잡음 거르기)
TITLES = r"\(.*?\)|대표님|본부장님|점장님|실장님|지점장님|지점장|점장|실장|팀장님|팀장|과장님|과장|주임님|주임|대표|본부장"


def say(msg=""):
    print(msg, flush=True)


def ask(prompt: str, default: str = "") -> str:
    try:
        v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    except EOFError:
        sys.exit("\n입력이 끊겨 중단합니다. 다시 실행하면 이어서 합니다.")
    return v or default


def yes(prompt: str, default: bool = True) -> bool:
    v = ask(f"{prompt} ({'Y/n' if default else 'y/N'})").lower()
    return default if not v else v.startswith("y") or v in ("ㅛ", "예", "네")


def parse_numbers(text: str, limit: int) -> list[int]:
    """'1-3, 7' → [1,2,3,7] (1부터, limit 이하만)"""
    out = []
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            continue
        a, b = int(m[1]), int(m[2] or m[1])
        out += [n for n in range(min(a, b), max(a, b) + 1) if 1 <= n <= limit and n not in out]
    return out


def person(sender: str) -> str:
    """'박대표 (대표님)' → '박대표' (직함·괄호 제거). 이름이 못 되면 글자만 남긴다"""
    n = re.sub(TITLES, "", sender)
    n = re.sub(r"[^가-힣A-Za-z]", "", n)
    return n if 2 <= len(n) <= 4 else re.sub(r"[^가-힣A-Za-z0-9]", "", sender)


# ---------- 1) 채팅 목록 ----------
def read_chat_list(pages: int) -> list[dict]:
    byp = {}
    for line in M.run_ps("-Action", "list", "-Pages", str(pages)):
        if line.startswith("L\t"):
            _, p, x, y, text = line.split("\t", 4)
            byp.setdefault(int(p), []).append((int(x), int(y), text))
    rows, seen = [], set()
    for p in sorted(byp):
        ls = byp[p]
        for x, y, text in sorted(ls, key=lambda l: l[1]):
            if not 160 <= x <= 200:
                continue
            when = next((t for xx, yy, t in ls if xx >= 560 and abs(yy - y) <= 12), "")
            if not WHEN.match(when.strip()):                # 시각이 없는 줄 = 미리보기 줄
                continue
            title = re.sub(r"^0(?=\D)", "", re.sub(r"\s+\d{1,3}(\s.*)?$", "", text.strip())).strip()
            prev = next((t for xx, yy, t in ls if 160 <= xx <= 200 and 12 < yy - y <= 40), "").strip()
            key = M.norm(title)
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append({"raw": title, "when": when.strip(), "preview": prev, "head": bool(M.HEADER.match(prev))})
    return rows


# ---------- 2) 방 열어 읽기 ----------
def probe(raw_title: str, max_pages: int, tries: int = 8, ticks: int = 6) -> dict:
    """방을 화면 밖에서 열어 (실제 제목, 메시지 목록)을 읽는다. 카톡이 사용 중이면 잠시 기다렸다 다시 한다"""
    for i in range(tries):
        try:
            lines = M.run_ps("-Action", "probe", "-Title", raw_title, "-MaxPages", str(max_pages), "-Ticks", str(ticks))
            break
        except RuntimeError as e:
            if "사용 중" in str(e) and i < tries - 1:
                say(f"    카톡을 쓰는 중이라 15초 뒤 다시 합니다 ({i + 1}/{tries - 1})")
                time.sleep(15)
                continue
            if "열리지 않음" in str(e) and i < 2:                # 검색 결과가 늦게 뜬 경우 등 일시적인 실패
                say("    방이 열리지 않아 다시 시도합니다")
                time.sleep(3)
                continue
            raise
    title = next((l.split("\t", 1)[1] for l in lines if l.startswith("T\t")), "")
    if not title:
        raise RuntimeError("방 창 제목을 읽지 못함")
    msgs = M.parse_scan(lines, dt.date.today())
    senders, posters = collections.Counter(), collections.Counter()
    for m in msgs:
        s = re.sub(r"\s+", " ", m["sender"] or "").strip()
        if not s or s == "나" or not NOISE.search(s):
            continue
        senders[s] += 1
        if M.inquiry_of(m):
            posters[s] += 1
    return {"title": title, "senders": merge_variants(senders), "posters": merge_variants(posters), "msgs": len(msgs)}


def merge_variants(c: collections.Counter) -> list[list]:
    """OCR 한두 글자 오류로 갈라진 이름을 합친다 → [[이름, 횟수], ...] 많은 순"""
    out: list[list] = []
    for s, n in c.most_common():
        for o in out:
            if M.sim(M.norm(s), M.norm(o[0])) >= 0.8:
                o[1] += n
                break
        else:
            out.append([s, n])
    return sorted(out, key=lambda o: -o[1])


def load_progress() -> dict:
    try:
        return json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


# ---------- 3) 본사·담당자 추정 ----------
def guess_hq(results: dict) -> list[str]:
    rooms_of = collections.defaultdict(set)
    for raw, r in results.items():
        for s, _ in r["posters"]:
            rooms_of[person(s)].add(raw)
    need = 2 if len(results) >= 2 else 1
    return sorted((n for n, rs in rooms_of.items() if len(rs) >= need and n), key=lambda n: -len(rooms_of[n]))


def honor_of(managers: list[str]) -> str:
    if len(managers) != 1:
        return "(생략)"
    t = managers[0]
    if "대표" in t:
        return "대표님"
    if "본부장" in t:
        return "본부장님"
    if "실장" in t and "점장" not in t:
        return "실장님"
    return "점장님"


def room_plan(r: dict, hq: list[str]) -> dict:
    """한 방의 담당자 제안: {title, managers, sure(2회 이상 말한 사람), maybe(1회), posters(게시자)}"""
    M.HQ[:] = hq
    posters = [s for s, _ in r["posters"] if person(s) not in hq and not any(h in M.norm(s) for h in hq)]
    room = {"managers": [], "posters": posters}
    sure, maybe = [], []
    for s, n in r["senders"]:
        if M.who(s, room) != "other":
            continue
        (sure if n >= 2 else maybe).append(s)
    if not sure and maybe:                                 # 한 사람만 보였다면 그 사람을 담당자로 제안한다
        sure.append(maybe.pop(0))
    return {"title": r["title"], "managers": sure, "maybe": maybe, "posters": posters}


# ---------- 4) 파일 쓰기 ----------
def backup(path: Path):
    if path.exists():
        shutil.copy2(path, path.with_name(f"{path.name}.bak-{dt.datetime.now():%Y%m%d-%H%M%S}"))


def write_files(out: Path, hq: list[str], plans: list[dict], rows_by_raw: dict, alert: str | None):
    for name in ("설정.json", "오더방_목록.md", "알림설정.json"):
        backup(out / name)
    (out / "설정.json").write_text(json.dumps(
        {"설명": "본사_이름 = 오더방에서 보낸 사람 이름에 들어 있으면 본사 직원으로 보는 이름(회신 담당자로 세지 않음). OCR이 자주 잘못 읽는 변형이 있으면 추가한다.",
         "본사_이름": hq}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    head = ["# 오더방 목록 (설치.py가 만듦 — 직접 고쳐도 된다)", "",
            "- 방 이름: 방을 열었을 때 창 제목과 글자 하나까지 같아야 한다(아이콘·띄어쓰기 포함). 설치 때 실제 창 제목으로 적었다.",
            "- 담당자: 그 방에서 회신해야 하는 지점 담당자. 여러 명이면 ` / `로 구분한다. 한 사람만 회신해도 회신으로 인정한다.",
            "- 게시자: 문의를 직접 올리는 사람이 담당자 쪽(대표님·점장 등)인 방은 `게시자:홍길동 (대표님)`으로 적는다. 본사처럼 취급해 회신 의무가 없다.",
            "- 호칭: `점장님`(기본), `대표님`, `실장님`, `본부장님`. 담당자가 2명 이상이면 `(생략)`.",
            "- 감시: O = 리마인드 대상, X = 제외.", "",
            "| # | 방 이름 | 마지막 글 | 담당자 | 호칭 | 감시 |", "|---|---|---|---|---|---|"]
    body = []
    for i, p in enumerate(plans, 1):
        who = [f"게시자:{s}" for s in p["posters"]] + p["managers"]
        watch = "O" if p["managers"] and p.get("watch", True) else "X"
        when = rows_by_raw.get(p["raw"], {}).get("when", "")
        body.append(f"| {i} | {p['title'].replace('|', '/')} | {when} | {' / '.join(who)} | {honor_of(p['managers'])} | {watch} |")
    (out / "오더방_목록.md").write_text("\n".join(head + body) + "\n", encoding="utf-8")
    (out / "알림설정.json").write_text(json.dumps(
        {"설명": "카톡방_알림 = true 이면 '회신 필요' 알림을 PC 알림 대신 아래 카톡방에 남긴다. 끄려면 false 또는 이 파일 삭제.",
         "카톡방_알림": bool(alert), "방": alert or ""}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def holiday_warning() -> str:
    years = {m[1] for l in (BASE / "공휴일.txt").read_text(encoding="utf-8").splitlines() if (m := re.match(r"\s*(\d{4})-", l))}
    y = str(dt.date.today().year)
    return "" if y in years else f"공휴일.txt 에 {y}년 공휴일이 없습니다. 한 줄에 YYYY-MM-DD 로 추가하세요(없으면 공휴일에도 영업일로 계산합니다)."


# ---------- 본체 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=BASE, help="설정 파일을 쓸 폴더(시험용)")
    ap.add_argument("--list-pages", type=int, default=40, help="채팅 목록을 최대 몇 화면 읽을지")
    ap.add_argument("--room-pages", type=int, default=8, help="방마다 몇 화면 읽을지(많을수록 담당자를 더 잘 찾지만 느림)")
    ap.add_argument("--fresh", action="store_true", help="이전 스캔 결과를 무시")
    a = ap.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.version_info < (3, 10):
        sys.exit("Python 3.10 이상이 필요합니다.")

    say("== 카톡 오더방 리마인드 설치 ==")
    say("준비: ① 카카오톡 PC에 로그인  ② 메인 창을 채팅 탭의 '전체'로 두기  ③ 설치하는 동안 카톡 창에 글자 입력 금지")
    say("방은 화면 밖에서 열었다 닫으며, 열린 방은 읽음 처리됩니다. 키보드·마우스·클립보드는 쓰지 않습니다.\n")
    ask("준비되면 Enter")

    # 1) 채팅 목록
    say("\n[1/5] 채팅 목록을 읽는 중…")
    try:
        rows = read_chat_list(a.list_pages)
    except RuntimeError as e:
        sys.exit(f"목록을 읽지 못했습니다: {e}\n카톡이 켜져 있고 메인 창이 채팅 탭인지, Windows 한국어 OCR(텍스트 인식)이 설치됐는지 확인하세요.")
    if not rows:
        sys.exit("채팅 목록에서 방을 찾지 못했습니다. 메인 창이 채팅 탭의 '전체'인지 확인하세요.")
    for i, r in enumerate(rows, 1):
        say(f"  {i:>3}. {r['raw']}  ({r['when']}){'  ← [레몬하우스…] 문의가 보임' if r['head'] else ''}")
    suggest = [i for i, r in enumerate(rows, 1) if r["head"] or "오더" in r["raw"]]
    say(f"\n오더방으로 쓰는 방 번호를 입력하세요. 예: 1-5, 8, 12   (Enter = 추천 {len(suggest)}개: {', '.join(map(str, suggest)) or '없음'})")
    sel_text = ask("선택")
    chosen = parse_numbers(sel_text, len(rows)) if sel_text else suggest
    if not chosen:
        sys.exit("고른 방이 없어 중단합니다.")
    rows_by_raw = {r["raw"]: r for r in rows}

    # 2) 방 읽기
    say(f"\n[2/5] 방 {len(chosen)}개를 읽습니다(방마다 약 20~30초). 카톡 창에 입력하지 마세요.")
    results = {} if a.fresh else {k: v for k, v in load_progress().items() if k in {rows[i - 1]["raw"] for i in chosen}}
    failed = []
    for n, idx in enumerate(chosen, 1):
        raw = rows[idx - 1]["raw"]
        if raw in results:
            say(f"  ({n}/{len(chosen)}) {raw}: 이전 결과 사용")
            continue
        say(f"  ({n}/{len(chosen)}) {raw}")
        try:
            results[raw] = probe(raw, a.room_pages)
            r = results[raw]
            say(f"      창 제목: {r['title']} / 메시지 {r['msgs']}개 / 보낸 사람 {len(r['senders'])}명")
            PROGRESS.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            failed.append((raw, str(e)))
            say(f"      실패: {e}")
    if failed:
        say("\n읽지 못한 방: " + ", ".join(f"{r}" for r, _ in failed) + "\n(나중에 다시 실행하면 이 방만 다시 읽습니다)")
    if not results:
        sys.exit("읽은 방이 없어 중단합니다.")

    # 3) 본사 직원
    say("\n[3/5] 본사 직원 이름")
    guess = guess_hq(results)
    seen_posters = {person(s): n for r in results.values() for s, n in r["posters"]}
    say("  문의 글을 올린 사람(2개 이상 방에 올린 사람을 본사 직원으로 추정): " + (", ".join(f"{n}" for n in guess) or "없음"))
    say(f"  (참고) 문의를 올린 사람 전체: {', '.join(f'{k}({v}건)' for k, v in sorted(seen_posters.items(), key=lambda kv: -kv[1])) or '없음'}")
    v = ask("본사 직원 이름을 쉼표로 입력 (Enter = 추정 그대로)", ", ".join(guess))
    hq = [re.sub(r"\s+", "", x) for x in re.split(r"[,，]", v) if x.strip()]
    if not hq:
        sys.exit("본사 직원 이름이 없으면 회신 판정이 안 됩니다. 다시 실행하세요.")

    # 4) 담당자
    say("\n[4/5] 방별 담당자 (그 방에서 회신해야 하는 지점 사람)")
    plans = []
    for raw, r in results.items():
        p = room_plan(r, hq)
        p["raw"] = raw
        plans.append(p)

    def show():
        for i, p in enumerate(plans, 1):
            ppl = ", ".join(p["managers"]) or "(찾지 못함 → 감시 제외)"
            extra = f"   게시자: {', '.join(p['posters'])}" if p["posters"] else ""
            maybe = f"   (1회만 말한 사람: {', '.join(p['maybe'])})" if p["maybe"] else ""
            say(f"  {i:>3}. {p['title']}\n        담당자: {ppl}  호칭: {honor_of(p['managers'])}{extra}{maybe}")
    show()
    while True:
        fix = ask("\n고칠 방 번호 (Enter = 모두 맞음)")
        if not fix:
            break
        for i in parse_numbers(fix, len(plans)):
            p = plans[i - 1]
            say(f"  [{i}] {p['title']}\n      지금: {' / '.join(p['managers']) or '없음'}")
            v = ask("      담당자를 ' / '로 구분해 입력 (Enter = 그대로, - = 이 방 감시 제외)")
            if v == "-":
                p["managers"], p["watch"] = [], False
            elif v:
                p["managers"] = [x.strip() for x in v.split("/") if x.strip()]
        show()

    # 5) 알림 방
    say("\n[5/5] 미회신이 확인되면 알림을 올릴 카톡방")
    say("  0. 카톡방에 올리지 않고 PC 알림만 쓰기")
    for i, r in enumerate(rows, 1):
        say(f"  {i:>3}. {r['raw']}")
    alert = None
    pick = ask("방 번호 (본인이 있는 방. 오더방 자체는 피하세요)", "0")
    if pick.isdigit() and 1 <= int(pick) <= len(rows):
        raw = rows[int(pick) - 1]["raw"]
        say("  방 제목을 확인하는 중…")
        try:
            alert = probe(raw, 1)["title"]
            say(f"  알림 방: {alert}")
            if any(p["title"] == alert for p in plans):
                say("  ※ 이 방은 감시 대상 오더방입니다. 알림이 오더방에 올라갑니다.")
            if yes("  시험 메시지를 이 방에 한 번 보낼까요?", False):
                ok, out = M.send_kakao(alert, "(오더 미회신 모니터링) 설치 확인용 시험 메시지입니다.")
                say(f"  결과: {out}")
        except Exception as e:  # noqa: BLE001
            say(f"  방 제목을 읽지 못했습니다({e}). 카톡방 알림 없이 설치합니다. 나중에 알림설정.json 에서 고칠 수 있습니다.")
    write_files(a.out, hq, plans, rows_by_raw, alert)
    PROGRESS.unlink(missing_ok=True)

    say(f"\n완료: {a.out} 에 설정.json · 오더방_목록.md · 알림설정.json 을 만들었습니다(기존 파일은 .bak-시각 으로 보관).")
    if w := holiday_warning():
        say(f"※ {w}")
    say("다음 단계")
    say("  1) 시험 실행(보내지 않음):  python -I 오더방_감시.py")
    say("  2) 매일 돌리기(5분마다):   powershell -ExecutionPolicy Bypass -File 작업등록.ps1")


if __name__ == "__main__":
    main()
