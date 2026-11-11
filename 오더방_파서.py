# ocr.ps1 출력("x y 텍스트" 줄)에서 [레몬하우스 …문의] 글을 찾아 리마인드 문구를 만든다.
# 사용: powershell -File ocr.ps1 -Path 캡처.png | python -I 오더방_파서.py
import re
import sys

HEADER = re.compile(r"^\[\s*레몬하우스\s*([^\]]*)\]?")   # '[레몬하우스'로 시작하는 글은 전부 추적 대상(제목에 '문의'가 없어도)


def kind_of(m) -> str:
    """제목 괄호 안의 종류. '견적 문의' → '견적', '사무실 상담' → '사무실상담', 비어 있으면 '기타'"""
    return re.sub(r"문의$", "", m[1].replace(" ", "")) or "기타"
FIELD = re.compile(r"^(현장.|평형대|전화번호|경로)\s*[:.•·\s]+\s*(.*)$")
TIME = re.compile(r"^(?:\d\s+)?(오전|오후)\s*\d{1,2}:?\d{2}$")
ADDR_END = re.compile(r"(특별시|광역시|도|시|군|구|읍|면|동|리|가|로|길|을)$")  # '을'은 OCR이 '읍'을 잘못 읽은 경우

# OCR이 자주 틀리는 글자 보정 (단지명에만 적용)
FIXES = [(re.compile(r"(\d)자"), r"\1차"), (re.compile(r"0H"), "애"), (re.compile(r"센덤"), "센텀"),
         (re.compile(r"EI"), "타")]


def complex_name(site: str) -> str:
    s = re.sub(r"\s+", " ", site).strip()
    s = re.sub(r"\s*\((빌라|오피스텔|주택|상가|아파트)\)\s*$", "", s)   # 끝의 '(빌라)' 같은 건물 유형
    if ")" in s:                       # '… 가촌리 (1271-1) 양우내안애2차아파트' → 괄호 뒤
        s = s[s.rindex(")") + 1:].strip()
    else:                              # 괄호가 없으면 앞쪽 지명 단어를 버린다
        words = s.split(" ")
        while len(words) > 1 and ADDR_END.search(words[0]):
            words.pop(0)
        s = " ".join(words)
    s = re.sub(r"\s*\d+\s*동\s*\d+\s*호.*$", "", s)        # 101동 702호
    s = re.sub(r"\s*\d+-\d*$|\s*\d+-$|\s+\d+$", "", s)       # 101-702, 307-
    s = s.replace(" ", "")
    for pat, rep in FIXES:
        s = pat.sub(rep, s)
    return re.sub(r"아파트$", "", s) or site


def parse(lines):
    """OCR 줄 목록 → 문의 글 목록 [{kind, phone, site, size, time}]"""
    items, cur, field = [], None, None
    for raw in lines:
        parts = raw.rstrip("\n").split(" ", 2)
        if len(parts) < 3:
            continue
        text = parts[2].strip()
        if m := HEADER.match(text):
            cur, field = {"kind": kind_of(m), "phone": "", "site": "", "size": "", "time": ""}, None
            items.append(cur)
            continue
        if cur is None:
            continue
        if TIME.match(text):
            t = re.sub(r"^\d\s+", "", text)
            cur["time"] = re.sub(r"(\d{1,2}?)(\d{2})$", r"\1:\2", t) if ":" not in t else t  # OCR이 ':'를 빠뜨림
            cur, field = None, None
            continue
        if m := FIELD.match(text):
            key = {"전화번호": "phone", "평형대": "size", "경로": None}.get(m[1], "site")
            field = key
            if key:
                cur[key] = m[2].strip()
            continue
        if field == "site" and text and not text.startswith(("평형", "상담", "공사", "입주")):
            cur["site"] += text  # 현장명 줄바꿈 이어붙이기
        else:
            field = None
    return items


def reminder(item, title: str = "점장님") -> str:
    """title: 오더방_목록.md의 호칭 칸. '' 또는 '(생략)'이면 호칭 없이 시작한다(담당자 2명 이상인 방)."""
    size = re.sub(r"\D", "", item["size"])
    name = complex_name(item["site"]) + (f" {size}평" if size else "") if item["site"] else ""
    head = "" if title in ("", "(생략)") else f"{title}, "
    what = f"[{name}] 문의건" if name else "위 문의건"          # 현장명이 없는 글(제목만 [레몬하우스…]인 공지성 글 등)
    return f"{head}{what} 통화하셨을까요? 피드백 부탁드립니다. (AI)"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    seen = set()
    for it in parse(sys.stdin.readlines()):
        key = (it["phone"], it["site"])
        if key in seen:      # 답장 안에 인용된 같은 문의는 한 번만
            continue
        seen.add(key)
        print(f"- 종류: {it['kind']}문의 | 전화: {it['phone']} | 시각: {it['time'] or '?'}")
        print(f"  현장명(OCR): {it['site']}")
        print(f"  문구: {reminder(it)}")
