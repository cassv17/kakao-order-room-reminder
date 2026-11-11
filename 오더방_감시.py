# 오더방 미회신 리마인드 감시.  규칙: 오더방_리마인드_규칙.md / 대상·담당자·호칭: 오더방_목록.md
#
#   python -I 오더방_감시.py            테스트 모드: 확인 → 보낼 목록(오더방_보낼목록.json)만 만든다. 전송 안 함
#   python -I 오더방_감시.py --send     보낼 목록의 건을 방을 다시 확인한 뒤 보낸다 (--ids 로 일부만)
#   python -I 오더방_감시.py --auto     확인 + 바로 전송 (자동 1회 단계에서 사용)
#
# 동작: ① 메인 창 채팅 목록에 지금 보이는 화면만 OCR(방은 열지 않음). 미리보기가 [레몬하우스 …문의]인 방을
#          그 시각으로 문의 등록하고 확인 시각(영업일 17시 전 +2시간, 그 밖 다음 영업일 09:30)을 계산한다.
#       ② 확인 시각이 된 문의가 있는 방만 화면 밖에서 열어 대화를 OCR → 담당자 회신 여부 판단 → 닫는다.
#       ③ 회신이 없으면 보낼 목록(테스트) 또는 바로 전송(--auto). 상태: 오더방_상태.json
#  한계: 문의 뒤에 다른 글이 바로 이어져 목록 미리보기에 문의가 한 번도 안 보이면 놓친다(자주 돌릴수록 줄어든다).
import argparse
import datetime as dt
import difflib
import json
import re
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from 오더방_파서 import FIELD, HEADER, complex_name, kind_of, reminder  # noqa: E402

STATE = BASE / "오더방_상태.json"
PENDING = BASE / "오더방_보낼목록.json"
LOG = BASE / "오더방_감시.log"
CONFIG = BASE / "설정.json"


def load_config() -> dict:
    """설정.json: 본사_이름 = 보낸 사람 이름에 들어 있으면 본사 직원으로 보는 이름들 (설정.예시.json 참고)"""
    if not CONFIG.exists():
        sys.exit("설정.json이 없습니다. 설정.예시.json을 복사해 설정.json으로 만들고 본사 직원 이름을 적으세요.")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


HQ = load_config()["본사_이름"]   # OCR이 이름을 잘못 읽는 경우가 있으면 그 변형도 함께 적는다
TIME = re.compile(r"^(?:\d+\s+)?(오전|오후)\s*(\d{1,2}):?(\d{2})$")
DATE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
NOW = dt.datetime.now()


DEFER = [False]                                        # 이번 회차에 카톡 사용 중·탭 불일치로 미뤘는지
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # 예약 실행 때 PowerShell 창이 깜빡이지 않게

def log(msg: str):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        print(line)
    except UnicodeEncodeError:                             # 콘솔 인코딩(cp949)에 없는 글자(🍋 등)
        print(line.encode("cp949", "replace").decode("cp949"))


def notify(title: str, msg: str):
    """Windows 토스트 알림 (알림.ps1 — 확인을 누를 때까지 남음, 실패하면 트레이 풍선으로 대신)"""
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BASE / "알림.ps1"),
                            "-Title", title, "-Message", msg[:250]], capture_output=True, timeout=30,
                           creationflags=NO_WINDOW)
        how = p.stdout.decode("cp949", "replace").strip()
    except Exception as e:  # noqa: BLE001
        how = f"알림 실패: {e}"
    log(f"알림({how}): {title} - {msg}")


def norm(s: str) -> str:
    return re.sub(r"[^가-힣a-zA-Z0-9]", "", s).lower()


def sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


# ---------- 설정 파일 ----------
def load_rooms():
    """오더방_목록.md 표 → [{no, title, managers, honor, watch}]"""
    rooms = []
    path = BASE / "오더방_목록.md"
    if not path.exists():
        sys.exit("오더방_목록.md가 없습니다. 오더방_목록.예시.md를 복사해 오더방_목록.md로 만들고 방 이름·담당자를 적으세요.")
    for line in path.read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in line.split("|")]
        if len(c) != 8 or not c[1].isdigit():
            continue
        mgr = re.sub(r"\([^)]*추가[^)]*\)", "", c[4])
        items = [m.strip() for m in mgr.split(" / ") if m.strip()]
        # "게시자:홍길동 (대표님)" = 이 방에서 문의를 직접 올리는 사람(본사처럼 취급, 회신 의무 없음). 나머지가 회신해야 하는 담당자
        posters = [m[len("게시자:"):].strip() for m in items if m.startswith("게시자:")]
        rooms.append({"no": int(c[1]), "title": c[2], "managers": [m for m in items if not m.startswith("게시자:")],
                      "posters": posters, "honor": c[5], "watch": c[6] == "O"})
    return rooms


def holidays():
    out = set()
    for line in (BASE / "공휴일.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", line)
        if m:
            out.add(dt.date.fromisoformat(m[1]))
    return out


HOLI = holidays()


def is_bday(d: dt.date) -> bool:
    return d.weekday() < 6 and d not in HOLI   # 월~토, 공휴일 제외


def next_bday(d: dt.date) -> dt.date:
    d += dt.timedelta(days=1)
    while not is_bday(d):
        d += dt.timedelta(days=1)
    return d


def prev_bday(d: dt.date) -> dt.date:
    d -= dt.timedelta(days=1)
    while not is_bday(d):
        d -= dt.timedelta(days=1)
    return d


def due_time(posted: dt.datetime) -> dt.datetime:
    """영업일 17시 전 → 2시간 뒤 / 그 밖(17시 이후·일요일·공휴일) → 다음 영업일 09:30"""
    if is_bday(posted.date()) and posted.time() < dt.time(17, 0):
        return posted + dt.timedelta(hours=2)
    return dt.datetime.combine(next_bday(posted.date()), dt.time(9, 30))


# ---------- PowerShell 호출 ----------
def run_ps(*args) -> list[str]:
    out = Path(tempfile.gettempdir()) / f"odr_{dt.datetime.now():%H%M%S%f}.txt"
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BASE / "오더방_창.ps1"), *args, "-Out", str(out)]
    subprocess.run(cmd, capture_output=True, timeout=600, creationflags=NO_WINDOW)
    lines = out.read_text(encoding="utf-8-sig").splitlines() if out.exists() else ["ERR\t출력 파일 없음"]
    out.unlink(missing_ok=True)
    err = [l for l in lines if l.startswith("ERR\t")]
    if err:
        raise RuntimeError(err[0][4:])
    return lines


# ---------- 메인 목록 ----------
def parse_when(t: str) -> dt.datetime | None:
    t = t.strip()
    if m := TIME.match(t):
        h = int(m[2]) % 12 + (12 if m[1] == "오후" else 0)
        return dt.datetime.combine(NOW.date(), dt.time(h, int(m[3])))
    if t == "어제":
        return dt.datetime.combine(NOW.date() - dt.timedelta(days=1), dt.time(23, 59))
    if m := re.match(r"(\d{4})-(\d{2})-(\d{2})$", t):
        return dt.datetime(int(m[1]), int(m[2]), int(m[3]), 23, 59)
    return None


def match_room(text: str, rooms) -> dict | None:
    t = re.sub(r"\s+\d{1,3}(\s.*)?$", "", text)
    n = norm(t)
    if n.startswith("0"):
        n = n[1:]
    best, score = None, 0.0
    for r in rooms:
        s = sim(n, norm(r["title"]))
        if s > score:
            best, score = r, s
    return best if score >= 0.75 else None


def scan_list(rooms, pages: int, no_scroll=False):
    """→ {title: {"sig", "when", "at", "head"}} (목록에 보인 오더방). head: 미리보기가 [레몬하우스 …문의]면 종류"""
    rows, byp = {}, {}
    args = ["-Action", "list"] + (["-NoScroll"] if no_scroll else ["-Pages", str(pages)])
    for line in run_ps(*args):
        if line.startswith("L\t"):
            _, p, x, y, text = line.split("\t", 4)
            byp.setdefault(int(p), []).append((int(x), int(y), text))
    for p, ls in byp.items():
        titles = [(y, text) for x, y, text in ls if 160 <= x <= 200]
        for y, text in titles:
            r = match_room(text, rooms)
            if not r:
                continue
            when = next((t for x, yy, t in ls if x >= 560 and abs(yy - y) <= 12), "")
            prev = next((t for x, yy, t in ls if 160 <= x <= 200 and 12 < yy - y <= 40), "")
            hm = HEADER.match(prev.strip())
            rows[r["title"]] = {"sig": f"{when}|{norm(prev)[:30]}", "when": when, "at": parse_when(when),
                                "head": kind_of(hm) if hm else ""}
    return rows


# ---------- 방 대화 ----------
def page_messages(lines, top, bottom):
    """한 화면의 OCR 줄 → [('date', date) | ('msg', {...})]. 위아래가 잘린 메시지는 버린다."""
    lines = sorted(lines, key=lambda l: (l[1], l[0]))
    notice = [y for x, y, t in lines if t.startswith("(공지)")]
    lo = (notice[0] + 60) if notice else top
    out, cur, last_sender = [], None, None
    for x, y, t in lines:
        t = t.strip()
        m = DATE.search(t)
        if y < (top if m else lo) or y > bottom:          # 날짜 구분선은 공지 바로 아래에 걸려도 읽는다
            continue
        if m:
            cur = None
            out.append(("date", dt.date(int(m[1]), int(m[2]), int(m[3]))))
            continue
        if 78 <= x <= 89 and len(norm(t)) >= 3 and not TIME.match(t):   # 보낸 사람 줄
            cur = {"sender": re.sub(r"^0\s*", "", t), "lines": [], "reply": False}
            continue
        if cur is None and len(norm(t)) <= 2:              # 말풍선 아래 공감 아이콘 등
            continue
        if m := TIME.match(t):
            if cur and cur["lines"]:
                h = int(m[2]) % 12 + (12 if m[1] == "오후" else 0)
                cur["time"] = dt.time(h, int(m[3]))
                out.append(("msg", cur))
                last_sender = cur["sender"]
            cur = None
            continue
        if re.fullmatch(r"\d{1,2}", t):                   # 안 읽은 사람 수
            continue
        if x >= 140:                                       # 오른쪽 말풍선 = 내가 보낸 글
            if not cur or cur["sender"] != "나":
                cur = {"sender": "나", "lines": [], "reply": False}
        elif cur is None:
            if last_sender is None:
                continue                                   # 위가 잘린 메시지
            cur = {"sender": last_sender, "lines": [], "reply": False}
        if "에게 답장" in t and not cur["lines"]:
            cur["reply"] = True
            continue
        cur["lines"].append(t)
    return out


def scan_room(room, stop_date: dt.date, last_date: dt.date):
    """방을 읽어 날짜가 붙은 메시지 목록을 돌려준다(오래된 것부터)."""
    meta, pages = (0, 99999), {}
    for line in run_ps("-Action", "scan", "-Title", room["title"], "-StopDate", stop_date.isoformat(), "-MaxPages", "60"):
        if line.startswith("M\t"):
            _, a, b, _ = line.split("\t")
            meta = (int(a), int(b))
        elif line.startswith("P\t"):
            _, p, x, y, text = line.split("\t", 4)
            pages.setdefault(int(p), []).append((int(x), int(y), text))
    merged, seen = [], set()
    for p in sorted(pages, reverse=True):                  # 가장 위 화면부터
        for kind, v in page_messages(pages[p], *meta):
            key = ("d", v) if kind == "date" else (norm(v["sender"])[:6], v["time"], norm(" ".join(v["lines"][:2]))[:40])
            if key in seen:
                continue
            seen.add(key)
            merged.append((kind, v))
    has_date = any(k == "date" for k, _ in merged)
    cur = None if has_date else last_date
    msgs = []
    for kind, v in merged:
        if kind == "date":
            cur = v
        elif cur:
            v["at"] = dt.datetime.combine(cur, v["time"])
            v["text"] = "\n".join(v["lines"])
            msgs.append(v)
    return msgs


HQ_CONTACT = re.compile(r"유선|전화|연락|통화|문자|전달")
NOT_NAME = {"레몬", "점장", "지점장", "실장", "팀장", "대표님", "본부장님", "점장님", "직원", "추가", "그때", "결정"}


def person_names(entry: str) -> list[str]:
    """담당자 항목("레몬 명지점 김철수 (실장)")에서 사람 이름(한글 3글자, 지점명·직함 제외)을 뽑는다"""
    out = []
    for t in re.findall(r"[가-힣]+", entry):
        if len(t) == 3 and t not in NOT_NAME and not t.endswith(("점", "방")):
            out.append(t)
    return out


def who(sender: str, room) -> str:
    s = norm(sender)
    if sender == "나" or any(h in s for h in HQ):
        return "hq"
    if any(n in s for p in room.get("posters", []) for n in person_names(p)):   # 이 방의 게시자(예: 직접 문의를 올리는 대표님)
        return "hq"
    if len(s) <= 6 and any(sim(s[:3], h) >= 0.66 for h in HQ):   # 짧은 이름의 OCR 한 글자 오류 (예: 윤→유)
        return "hq"
    if any(sim(s, norm(m)) >= 0.7 or (len(norm(m)) >= 4 and norm(m) in s) for m in room["managers"]):
        return "mgr"
    if any(n in s for m in room["managers"] for n in person_names(m)):   # 지점명을 OCR이 틀리게 읽어도(명지점→영지점) 사람 이름으로 잡는다
        return "mgr"
    return "other"


def inquiry_of(msg):
    if msg["reply"]:
        return None
    start = next((i for i, t in enumerate(msg["lines"][:3]) if HEADER.match(t)), None)
    if start is None:
        return None
    m = HEADER.match(msg["lines"][start])
    item = {"kind": kind_of(m), "phone": "", "site": "", "size": ""}
    field = None
    for t in msg["lines"][start + 1:]:
        if f := FIELD.match(t):
            key = {"전화번호": "phone", "평형대": "size", "경로": None}.get(f[1], "site")
            field = key
            if key:
                item[key] = f[2].strip()
        elif field == "site" and not t.startswith(("평형", "상담", "공사", "입주")):
            item["site"] += t
        else:
            field = None
    return item


def mentions(text: str, inq) -> bool:
    """글에 그 문의의 전화번호(OCR 한두 자리 오차 허용)나 단지명이 들어 있는가"""
    phone = re.sub(r"\D", "", inq["phone"])
    if len(phone) >= 10:
        for run in re.findall(r"0\d[\d\- .]{7,14}\d", text):
            d = re.sub(r"\D", "", run)
            if d == phone or (abs(len(d) - len(phone)) <= 1 and sim(d, phone) >= 0.85):
                return True
    cn = norm(complex_name(inq["site"])) if inq["site"] else ""
    return len(cn) >= 4 and cn in norm(text)


# ---------- 상태 ----------
def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"created": NOW.isoformat(timespec="minutes"), "rooms": {}, "inquiries": {}}


def save_state(st):
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def same_inquiry(q, room, at: dt.datetime, inq) -> bool:
    """같은 방, 올린 시각 3분 이내, 전화번호가 같거나(OCR 한두 자리 오차 허용) 한쪽이 비어 있으면 같은 문의"""
    if q["no"] != room["no"] or abs(dt.datetime.fromisoformat(q["posted"]) - at) > dt.timedelta(minutes=3):
        return False
    a, b = re.sub(r"\D", "", q["phone"]), re.sub(r"\D", "", inq["phone"])
    return not a or not b or sim(a, b) >= 0.8


def update_room(st, room, msgs):
    """새 문의 등록 + 대기 중인 문의의 회신 여부 갱신"""
    for i, m in enumerate(msgs):
        if who(m["sender"], room) != "hq" or not (inq := inquiry_of(m)):
            continue
        ident = re.sub(r"\D", "", inq["phone"]) or norm(inq["site"])[:20] or f'{m["at"]:%H%M}'
        iid = f'{room["no"]}|{m["at"]:%Y-%m-%d}|{ident}'
        seen = NOW.isoformat(timespec="minutes")
        same = next((q for q in st["inquiries"].values() if same_inquiry(q, room, m["at"], inq)), None)
        if same:                                           # 이미 아는 문의 → 이번 확인에서 글을 다시 찾았다고 표시
            if same.get("seed"):                           # 목록에서 먼저 본 문의 → 방에서 읽은 내용으로 채운다
                same.update(inq, seed=False)
            same["seen"] = seen
            continue
        if iid not in st["inquiries"]:
            st["inquiries"][iid] = {**inq, "seen": seen, "room": room["title"], "no": room["no"],
                                    "posted": m["at"].isoformat(timespec="minutes"),
                                    "due": due_time(m["at"]).isoformat(timespec="minutes"),
                                    "status": "pending", "note": ""}
            if due_time(m["at"]) < NOW - STALE_AFTER:       # 이미 하루 넘게 지난 글: 기록만 하고 추적하지 않는다
                st["inquiries"][iid]["status"], st["inquiries"][iid]["note"] = "old", "하루 넘게 지남(추적 안 함)"
            else:
                log(f'새 문의 [{room["title"]}] {inq["kind"]} {inq["phone"]} {m["at"]:%m/%d %H:%M}')
    for iid, q in st["inquiries"].items():
        if q["no"] != room["no"] or q["status"] not in ("pending", "ask"):
            continue
        posted = dt.datetime.fromisoformat(q["posted"])
        direct = next((m for m in msgs if who(m["sender"], room) == "hq" and not m["reply"] and not inquiry_of(m)
                       and posted < m["at"] <= posted + dt.timedelta(minutes=10) and HQ_CONTACT.search(m["text"])
                       and any(n in m["text"] for mm in room["managers"] for n in person_names(mm))), None)
        if direct:                                         # 본사가 문의 직후 담당자에게 직접 연락했다고 남긴 글 ("홍길동 점장님께 유선 연락드렸습니다")
            q["status"], q["note"] = "handled", f'본사 {direct["sender"]} 직접 연락 {direct["at"]:%m/%d %H:%M}'
            continue
        for m in msgs:
            if m["at"] < posted or (m["at"] == posted and inquiry_of(m)) or not mentions(m["text"], q):
                continue
            w = who(m["sender"], room)
            if w == "mgr":
                q["status"], q["note"] = "replied", f'{m["sender"]} {m["at"]:%m/%d %H:%M}'
                break
            if w == "hq" and m["reply"]:
                q["status"], q["note"] = "handled", f'본사 {m["sender"]} {m["at"]:%m/%d %H:%M}'
                break
            if w == "other":
                q["status"], q["note"] = "ask", f'목록에 없는 사람 회신: {m["sender"]} {m["at"]:%m/%d %H:%M}'
    # 목록에서 먼저 본 문의(seed)의 원문을 방에서 못 읽었어도(스캔 범위 맨 위에서 잘림 등), 그 뒤에 담당자가 아직 모르는 전화번호를 인용해
    # 회신했다면 그 회신이 이 문의에 대한 것으로 본다 (예: 원문 09:33은 못 읽었지만 12:04에 점장이 그 번호로 회신)
    known = [re.sub(r"\D", "", x["phone"]) for x in st["inquiries"].values() if x["no"] == room["no"] and x["phone"]]
    for q in st["inquiries"].values():
        if q["no"] != room["no"] or not q.get("seed") or q["status"] not in ("pending", "ask"):
            continue
        posted = dt.datetime.fromisoformat(q["posted"])
        for m in msgs:
            if not (m["reply"] and posted <= m["at"] <= posted + dt.timedelta(hours=12) and who(m["sender"], room) == "mgr"):
                continue
            nums = [re.sub(r"\D", "", r) for r in re.findall(r"0\d[\d\- .]{7,14}\d", m["text"])]
            fresh = next((n for n in nums if len(n) >= 10 and not any(sim(n, k) >= 0.8 for k in known)), None)
            if fresh:
                q["status"], q["note"] = "replied", f'{m["sender"]} {m["at"]:%m/%d %H:%M} (원문은 못 읽고 인용 회신으로 확인)'
                q["phone"] = q["phone"] or fresh
                known.append(fresh)
                break


STALE_AFTER = dt.timedelta(hours=24)


def stale(st, q) -> bool:
    """추적하지 않을 건: 감시를 시작하기 전에 이미 기한이 지난 건, 또는 확인 기한이 지난 지 하루가 넘은 건
    (하루 넘게 지난 문의는 이제 알려도 소용없다. 기준은 올린 시각이 아니라 기한이다 — 17시 이후·일요일 글은 기한이 다음 영업일이다)"""
    due = dt.datetime.fromisoformat(q["due"])
    return due < dt.datetime.fromisoformat(st["created"]) or due < NOW - STALE_AFTER


def candidates(st, rooms):
    honor = {r["title"]: r["honor"] for r in rooms}
    out = []
    for iid, q in sorted(st["inquiries"].items(), key=lambda kv: kv[1]["posted"]):
        if (q["status"] == "pending" and dt.datetime.fromisoformat(q["due"]) <= NOW and not stale(st, q)
                and q.get("seen")):                         # 화면을 못 읽었으면(잠금·빈 캡처) 보내지 않는다
            out.append({"id": iid, "room": q["room"], "posted": q["posted"], "due": q["due"],
                        "phone": q["phone"], "site": q["site"], "text": reminder(q, honor.get(q["room"], "점장님"))})
    return out


# ---------- 실행 ----------
def watch_list(st, rooms):
    """메인 창 채팅 목록(지금 보이는 화면)만 읽어 미리보기가 [레몬하우스 …문의]인 방을 문의로 등록한다. 방은 열지 않는다."""
    rows = scan_list(rooms, 1, no_scroll=True)
    for r in rooms:
        if not r["watch"] or r["title"] not in rows:
            continue
        row = rows[r["title"]]
        if not row["head"] or not row["at"]:
            continue
        posted = row["at"].replace(second=0, microsecond=0)
        if any(q["no"] == r["no"] and abs(dt.datetime.fromisoformat(q["posted"]) - posted) <= dt.timedelta(minutes=3)
               for q in st["inquiries"].values()):
            continue
        iid = f'{r["no"]}|{posted:%Y-%m-%d %H:%M}|목록'
        st["inquiries"][iid] = {"kind": row["head"], "phone": "", "site": "", "size": "", "seed": True,
                                "room": r["title"], "no": r["no"], "posted": posted.isoformat(timespec="minutes"),
                                "due": due_time(posted).isoformat(timespec="minutes"), "status": "pending", "note": ""}
        log(f'새 문의(목록) [{r["title"]}] {row["head"]} {posted:%m/%d %H:%M} → 확인 {due_time(posted):%m/%d %H:%M}')
    save_state(st)


def check(st, rooms, only=None):
    """기한이 된 문의가 있는 방만 (화면 밖에서) 열어 회신을 확인한다. only: 이 방들만 확인."""
    by_no = {r["no"]: r for r in rooms}
    due_rooms = {}
    for q in st["inquiries"].values():
        if q["status"] in ("pending", "ask") and stale(st, q):   # 오래된 건은 확인·알림·전송하지 않는다
            q["status"], q["note"] = "old", "하루 넘게 지남(추적 안 함)"
            log(f'오래된 건 제외 [{q["room"]}] {q["posted"]} {q["phone"]}')
        if q["status"] not in ("pending", "ask"):
            continue
        if only is not None:
            if q["room"] in only:
                due_rooms.setdefault(q["no"], []).append(q)
        elif dt.datetime.fromisoformat(q["due"]) <= NOW and q["status"] == "pending":
            due_rooms.setdefault(q["no"], []).append(q)
    for no, qs in due_rooms.items():
        r = by_no.get(no)
        if not r or not r["watch"]:
            continue
        stop = min(dt.datetime.fromisoformat(q["posted"]).date() for q in qs)
        for q in qs:
            q["seen"] = ""                                 # 이번 확인에서 문의 글을 다시 찾아야만 보낼 수 있다
        try:
            msgs = scan_room(r, stop, NOW.date())
        except Exception as e:  # noqa: BLE001
            if "사용 중" in str(e):                          # 사용자가 카톡을 쓰는 중 → 다음 회차에 다시
                log(f'미룸 [{r["title"]}]: {e}')
                DEFER[0] = True
                break
            log(f'방 읽기 실패 [{r["title"]}]: {e}')
            continue
        update_room(st, r, msgs)
        for q in qs:
            if q.get("seed"):                              # 방에서 해당 문의 글을 못 찾음
                q["status"], q["note"] = "ask", "목록에서 본 문의 글을 방에서 찾지 못함"
        st["rooms"][r["title"]] = {"scanned": NOW.isoformat(timespec="minutes")}
        save_state(st)
    save_state(st)
    log(f"확인 끝: 연 방 {len(due_rooms)}개")


def send(st, rooms, items):
    for it in items:
        q = st["inquiries"].get(it["id"])
        if not q or q["status"] != "pending":
            log(f'건너뜀(이미 처리됨) {it["room"]} {it["text"]}')
            continue
        check(st, rooms, only={q["room"]})                 # 보내기 직전에 회신이 왔는지 다시 확인
        if st["inquiries"][it["id"]]["status"] != "pending":
            log(f'건너뜀(회신 확인됨) {it["room"]}: {st["inquiries"][it["id"]]["note"]}')
            continue
        if not q.get("seen"):
            log(f'건너뜀(방에서 문의 글을 다시 찾지 못함 — 화면 캡처 실패 가능) {it["room"]}')
            continue
        p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BASE / "카톡보내기.ps1"),
                            "-Room", q["room"], "-Text", it["text"]], capture_output=True, timeout=120,
                           creationflags=NO_WINDOW)
        out = p.stdout.decode("cp949", "replace").strip()
        if p.returncode == 0 and "전송함" in out:
            q["status"], q["note"] = "sent", NOW.isoformat(timespec="minutes")
            log(f'전송 [{q["room"]}] {it["text"]}')
            notify("오더방 리마인드 보냄", f'{q["room"].lstrip("🍋 ")}: {it["text"]}')
        else:
            log(f'전송 실패 [{q["room"]}]: {out or p.stderr.decode("cp949", "replace")}')
        save_state(st)


def single_instance():
    """동시에 하나만 실행 (예약 실행이 겹쳐 두 번 보내는 것을 막는다). 프로세스가 끝나면 잠금이 저절로 풀린다."""
    import msvcrt
    f = open(BASE / "오더방_감시.lock", "a+")
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("이미 실행 중이라 이번 회차는 건너뜀")
        sys.exit(0)
    return f


def main():
    if sys.stdout is None:                                 # pythonw(예약 실행)는 콘솔이 없다
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--ids", nargs="*")
    a = ap.parse_args()
    _lock = single_instance()  # noqa: F841
    rooms, st = load_rooms(), load_state()
    if a.send:
        items = json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else []
        if a.ids:
            items = [i for i in items if i["id"] in a.ids]
        send(st, rooms, items)
        PENDING.write_text(json.dumps(candidates(st, rooms), ensure_ascii=False, indent=1), encoding="utf-8")
        return
    try:
        watch_list(st, rooms)
        check(st, rooms)
        st["fails"] = 0
        st.pop("fail_notified", None)
    except Exception as e:  # noqa: BLE001  카톡 꺼짐·종료·채팅 탭 아님 등
        busy = "사용 중" in str(e)
        DEFER[0] = DEFER[0] or busy
        if busy:                                           # 창은 정상으로 찾았다는 뜻 → 실패 횟수를 지운다 (미룸은 실패가 아님)
            st["fails"] = 0
            st.pop("fail_notified", None)
            log(f"미룸: {e}")
        else:
            st["fails"] = st.get("fails", 0) + 1
            log(f'감시 실패 ({st["fails"]}회 연속): {e}')
            if st["fails"] >= 3 and not st.get("fail_notified"):   # 3회 연속 실패하면 한 번만 알린다
                notify("오더방 감시가 멈춤", f"3회 연속 실패: {e}")
                st["fail_notified"] = NOW.isoformat(timespec="minutes")
        save_state(st)
    if DEFER[0]:                                           # 이번 회차에 미뤘으면 시작 시각을 기록, 60분 넘게 계속 밀리면 한 번 알린다
        st.setdefault("busy_since", NOW.isoformat(timespec="minutes"))
        mins = int((NOW - dt.datetime.fromisoformat(st["busy_since"])).total_seconds() // 60)
        if mins >= 60 and not st.get("busy_notified"):
            notify("오더방 확인 밀림", f"{mins}분째 확인을 못 했습니다. 카톡 검색창에 글자가 남아 있거나 전체·안읽음 탭이 아닌 탭을 보고 있는지 확인해 주세요.")
            st["busy_notified"] = NOW.isoformat(timespec="minutes")
    else:
        st.pop("busy_since", None); st.pop("busy_notified", None)
    cands = candidates(st, rooms)
    fresh = [c for c in cands if not st["inquiries"][c["id"]].get("notified")]
    new_asks = [q for q in st["inquiries"].values() if q["status"] == "ask" and not q.get("notified")]
    if fresh and not a.auto:
        notify(f"오더방 리마인드 {len(fresh)}건 확인 필요", " / ".join(f'{c["room"].lstrip("🍋 ")}: {c["text"][:30]}' for c in fresh))
    if new_asks:
        notify("오더방 확인 필요", " / ".join(f'{q["room"].lstrip("🍋 ")}: {q["note"]}' for q in new_asks))
    for c in fresh:
        st["inquiries"][c["id"]]["notified"] = NOW.isoformat(timespec="minutes")
    for q in new_asks:
        q["notified"] = NOW.isoformat(timespec="minutes")
    save_state(st)
    PENDING.write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    asks = [q for q in st["inquiries"].values() if q["status"] == "ask"]
    print(f"\n보낼 건 {len(cands)}개 (오더방_보낼목록.json)")
    for c in cands:
        print(f'- [{c["room"]}] 올림 {c["posted"][5:].replace("T", " ")} → {c["text"]}')
    for q in asks:
        print(f'? [{q["room"]}] {q["phone"]} {q["note"]}')
    print("\n추적 중인 문의")
    for q in sorted(st["inquiries"].values(), key=lambda q: q["posted"]):
        print(f'  {q["status"]:8} {q["posted"][5:].replace("T", " ")} [{q["room"]}] {q["kind"]} {q["phone"]} '
              f'{complex_name(q["site"]) if q["site"] else ""} {q["size"]}  {q["note"]}')
    if a.auto and cands:
        send(st, rooms, cands)


if __name__ == "__main__":
    main()
