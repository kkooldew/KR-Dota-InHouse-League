"""
오라클 봇: 내전의 승부 예측 (포인트 걸기)

퍼그나봇(bot.py)과 같은 프로그램 안에서 돌지만, 디스코드에서는 봇 계정을 하나 더 쓴다(운영자가 2026-10-13에 정함:
"디스코드에서만 봇을 쪼개고, 돌아가는 배치 파일은 하나로"). config.json 에 oracle_token 이 없으면 꺼져 있고 퍼그나봇만 돈다.

- 리그 선수는 한 주에 한 번 1000 포인트를 받는다(월요일 0시, 한국 시간에 새 주가 시작된다. 처음 켠 주에도 한 번 받는다).
  저절로 주지 않고 본인이 '포인트 받기'를 눌러야 받는다(관심 없는 사람은 받지 않게). 받지 않은 주의 포인트는 사라지고, 받은 포인트는 쌓인다.
- 퍼그나봇이 팀을 짜서 알리면 그 글 바로 아래에 승부 예측을 연다. 20분 동안 래디언트·다이어 가운데 이길 팀에 포인트를 건다(버튼).
  그 경기에 뛰는 선수는 걸 수 없다. 한 경기에 한 번 걸고, 마감 전에는 바꾸거나 취소할 수 있다.
- 20분이 지나면 마감하고 배당률과, 건 사람마다 이기면 얻고 지면 잃는 포인트를 알린다. 봇이 꺼져 있던 사이에 20분이 지났으면 켜자마자 마감한다.
  건 포인트를 모두 모아 이긴 쪽이 건 만큼 나눠 갖는다(많이 건 사람이 많이 딴다). 한쪽에만 걸렸으면 모두 돌려준다.
- 퍼그나봇의 /승리 로 결과가 기록되면 정산한다. /승리취소 면 정산을 되돌리고(그사이 딴 포인트를 써 버렸으면 0보다 적어질 수 있다),
  다시 /승리 하면 다시 정산한다. 경기가 없던 일이 되면(/취소·/재모집·다시 열기·경기 안 함) 건 포인트를 돌려준다.
- 포인트를 받은 적이 있는 사람들의 순위를 리그 서버에 올린다(saveOracle, 서버 버전 17). rank/oracle.html(승부의 신 랭킹)이 그것을 보여 준다.
- 주인이 리그 관리자 페이지에서 켜고 끈다(서버 버전 18, 운영자가 2026-10-13에 요청). 처음에는 꺼져 있고, 켜 두었는지는 리그 서버에 5분마다 물어본다.
  꺼져 있으면 새 승부 예측을 열지 않고 포인트 받기와 걸기를 받지 않는다. 이미 받던 판은 끝까지 처리한다(마감, 정산, 돌려주기).
- 참가 포인트(서버 버전 19, 운영자가 2026-10-13에 요청): 결과가 기록되면 그 판에 뛴 선수 열 명이 승패와 상관없이 포인트를 받는다.
  처음에는 한 판에 100이고 주인이 리그 관리자 페이지에서 바꾼다(0이면 주지 않는다). /승리취소 면 거두고, 다시 기록되면 다시 준다.

이 파일은 bot.py 를 불러오지 않는다(bot.py 가 이 파일을 불러와 setup 으로 필요한 것을 넘겨준다). 그래서 따로 시험할 수 있다(tests/oracle.test.py).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands

KST = timezone(timedelta(hours=9))
WEEKLY_POINTS = 1000      # 한 주에 받는 포인트
BET_SECONDS = 20 * 60     # 팀을 짜서 알린 뒤 이만큼 동안 걸 수 있다
TICK_SECONDS = 10         # 마감할 판과 새 주를 이만큼마다 확인한다
BOOK_TTL = 2 * 86400      # 결과가 기록되지 않은 채 이만큼 지나면 건 포인트를 돌려준다 (퍼그나봇이 짠 팀을 기억하는 시간과 같다)
KEEP_SECONDS = 7 * 86400  # 끝난 판을 이만큼 기억한다
POST_RETRY = 600          # 올리지 못한 글을 이만큼 뒤에 다시 올려 본다
PUBLISH_GAP = 20          # 순위를 서버에 올린 뒤 이만큼은 다시 올리지 않는다 (포인트 받기가 몰릴 때 한 번에 올리려고)
PUBLISH_RETRY = 600       # 서버에 올리지 못했으면 이만큼 뒤에 다시 올린다
SWITCH_POLL = 300         # 주인이 켜 두었는지를 리그 서버에 이만큼마다 물어본다
PLAY_POINTS = 100         # 참가 포인트의 처음 값: 결과가 기록되면 그 판에 뛴 선수가 승패와 상관없이 받는다 (주인이 리그 관리자 페이지에서 바꾼다)
PLAY_MAX = 10000          # 참가 포인트로 받아들이는 가장 큰 값 (리그 서버와 같다)
AMOUNTS = (100, 300, 500, 1000)  # 금액 버튼
MESSAGE_LIMIT = 1900      # 디스코드 메시지는 2000자까지라 조금 남겨 두고 나눈다
SIDES = {"r": "🟢 래디언트", "d": "🔴 다이어"}
QUIET = discord.AllowedMentions.none()  # 오라클 봇의 글은 멘션 알림을 울리지 않는다
PLAYER_ONLY = "리그 선수만 쓸 수 있어요. 선수 등록을 하고 승인을 받으면 쓸 수 있어요."
RESTING = "지금은 오라클 봇이 쉬고 있어요. 다시 켜지면 포인트를 받고 걸 수 있어요."  # 주인이 꺼 둔 동안의 답


class State:
    """오라클 봇이 기억하는 것. 포인트와 승부 예측은 oracle.json 에 적어 두어 봇을 껐다 켜도 이어진다."""

    def __init__(self) -> None:
        self.token = ""                 # 오라클 봇의 토큰 (config.json 의 oracle_token)
        self.page = ""                  # 승부의 신 랭킹(포인트 순위) 페이지의 주소 (config.json 의 oracle_page). 정산 글에 적는다
        self.path: Path | None = None   # 상태 파일
        self.host = None                # 퍼그나봇이 넘겨준 것들 (setup)
        self.client = None              # 오라클 봇의 디스코드 연결
        self.ready = False              # 로그인해서 글을 올릴 수 있는지
        self.on = False                 # 주인이 리그 관리자 페이지에서 켜 두었는지 (리그 서버가 알려 준다. 알기 전에는 꺼진 것으로 둔다)
        self.asked = 0.0                # 켜 두었는지를 마지막으로 물어본(또는 들은) 시각
        self.play = PLAY_POINTS         # 참가 포인트: 한 판에 얼마 (리그 서버가 알려 준다. 0이면 주지 않는다)
        self.loaded = False             # 상태 파일을 읽었는지 (못 읽었으면 켤 때 서버의 사본을 받아 본다)
        self.lock = asyncio.Lock()      # 마감·정산·되돌리기의 글이 뒤섞이지 않게 한 번에 하나씩 한다
        self.task: asyncio.Task | None = None
        self.channel_id = 0             # 매주 '포인트 받기' 글을 올리는 채널 (/오라클설정)
        self.round: dict | None = None  # 이번 주 {"start": 주가 시작한 시각, "message_id", "channel_id", "prev": 지울 앞 글 [채널, 글]}
        self.accounts: dict[str, dict] = {}  # 디스코드 ID(글자) → {"points", "claimed", "week", "name", "username", "nick", "bets", "hits", "profit", "played", "earned"}
        self.books: list[dict] = []     # 승부 예측 한 판씩 (open → closed → settled, 또는 void)
        self.dirty = False              # 서버에 올려야 할 바뀐 순위가 있는지
        self.publish_at = 0.0           # 이 시각 전에는 서버에 올리지 않는다
        self.notes: set[str] = set()    # 창에 한 번 찍은 문제. 같은 문제를 되풀이해 찍지 않는다


S = State()


def now() -> float:
    return time.time()


def enabled() -> bool:
    """오라클 봇을 쓰는지 (토큰을 넣어 두었는지)"""
    return bool(S.token)


def setup(token: str, path: Path, host, page: str = "") -> None:
    """퍼그나봇이 켜질 때 한 번 부른다. host 에는 퍼그나봇의 것들이 들어 있다:
    guild(서버), admin_channel_id(운영진 채널), signup_channel_id(참여 신청 채널),
    can_play(user) → 리그 선수 이상인가(비동기), is_manager(user) → 리그 관리자인가,
    nickname(디스코드 ID, 사용자명) → 리그 닉네임(모르면 None), server(요청) → 리그 서버의 답(비동기. 서버 설정이 없으면 None)"""
    S.token, S.page, S.path, S.host = str(token or "").strip(), str(page or "").strip(), path, host
    S.loaded = load()


def note(text: str) -> None:
    """문제를 창에 알린다. 같은 글은 한 번만 찍는다"""
    if text not in S.notes:
        S.notes.add(text)
        print(text)


def num(n: int) -> str:
    """1,234 / −300 (음수는 긴 빼기표로)"""
    return f"−{-n:,}" if n < 0 else f"{n:,}"


def signed(n: int) -> str:
    return f"+{n:,}" if n > 0 else num(n)


# ── 상태 파일 ─────────────────────────────────────────────────
def snapshot() -> dict:
    return {"on": S.on, "play": S.play, "channel_id": S.channel_id, "round": S.round, "accounts": S.accounts, "books": S.books, "dirty": S.dirty}


def save() -> None:
    if S.path is None:
        return
    try:
        tmp = S.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot(), ensure_ascii=False), encoding="utf-8")
        for attempt in range(3):
            try:
                os.replace(tmp, S.path)
                break
            except PermissionError:  # 윈도우에서 다른 프로그램이 그 파일을 잠깐 잡고 있을 때가 있다
                if attempt == 2:
                    raise
                time.sleep(0.05)
    except (OSError, TypeError, ValueError) as e:
        print(f"오라클: 포인트 기록을 저장하지 못했습니다: {e}")


def whole(v, default: int = 0) -> int:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def play_amount(v) -> int | None:
    """참가 포인트로 쓸 수 있는 값이면 그 값(0 ~ PLAY_MAX 의 정수), 아니면 None"""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and not v.is_integer()):
        return None
    return int(v) if 0 <= v <= PLAY_MAX else None


def adopt(data: dict) -> None:
    """파일(또는 서버의 사본)에서 읽은 상태를 받아들인다. 모양이 맞지 않는 것은 버린다"""
    S.on = data.get("on") is True  # 마지막으로 알던 값. 켠 뒤 곧 리그 서버에 다시 물어본다
    amount = play_amount(data.get("play"))
    S.play = PLAY_POINTS if amount is None else amount
    S.channel_id = whole(data.get("channel_id"))
    r = data.get("round")
    S.round = ({"start": whole(r.get("start")), "message_id": whole(r.get("message_id")), "channel_id": whole(r.get("channel_id")),
                "prev": r.get("prev") if isinstance(r.get("prev"), list) and len(r.get("prev")) == 2 else None}
               if isinstance(r, dict) and whole(r.get("start")) else None)
    accounts = data.get("accounts") if isinstance(data.get("accounts"), dict) else {}
    books = data.get("books") if isinstance(data.get("books"), list) else []
    S.accounts = {}
    for uid, a in accounts.items():
        if str(uid).isdigit() and isinstance(a, dict):
            S.accounts[str(uid)] = {"points": whole(a.get("points")), "claimed": whole(a.get("claimed")), "week": whole(a.get("week")),
                                    "name": str(a.get("name") or ""), "username": str(a.get("username") or ""), "nick": str(a.get("nick") or ""),
                                    "bets": whole(a.get("bets")), "hits": whole(a.get("hits")), "profit": whole(a.get("profit")),
                                    "played": whole(a.get("played")), "earned": whole(a.get("earned"))}
    S.books = []
    for b in books:
        if not (isinstance(b, dict) and b.get("key") and b.get("state") in ("open", "closed", "settled", "void")):
            continue
        bets = {str(uid): {"side": x["side"], "amount": whole(x.get("amount")), "at": float(x.get("at") or 0)}
                for uid, x in (b.get("bets") or {}).items() if isinstance(x, dict) and x.get("side") in SIDES and whole(x.get("amount")) > 0}
        S.books.append({"key": str(b["key"]), "place_id": whole(b.get("place_id")), "opened": float(b.get("opened") or 0),
                        "closes": float(b.get("closes") or 0), "ended": float(b.get("ended") or 0), "state": b["state"],
                        "players": [whole(x) for x in b.get("players") or []], "bets": bets, "message_id": whole(b.get("message_id")),
                        "winner": b.get("winner") if b.get("winner") in SIDES else None,
                        "paid": {str(uid): whole(v) for uid, v in (b.get("paid") or {}).items()},
                        "play": {str(uid): whole(v) for uid, v in (b.get("play") or {}).items() if whole(v) > 0}, "off": b.get("off") is True})
    S.dirty = bool(data.get("dirty"))


def load() -> bool:
    """상태 파일을 읽는다. 읽었으면 True"""
    if S.path is None:
        return False
    try:
        data = json.loads(S.path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    adopt(data)
    return True


# ── 켜고 끄기 (주인이 리그 관리자 페이지에서) ───────────────────
def hear(value, play=None) -> None:
    """리그 서버가 알려 준 값: 주인이 오라클 봇을 켜 두었는지(value)와 참가 포인트(play). 퍼그나봇이 팀을 짜기 직전에 받는 리그 기록에도 실려 온다.
    그 값이 실려 있지 않은 답(예전 서버)으로는 바꾸지 않는다"""
    amount = play_amount(play)
    if amount is not None and amount != S.play:
        S.play = amount
        save()
        print(f"[{datetime.fromtimestamp(now(), KST):%m-%d %H:%M}] 오라클 봇: 리그 관리자 페이지에서 참가 포인트를 "
              + (f"한 판에 {amount:,} 포인트로 정했습니다." if amount else "주지 않기로 했습니다(0)."))
    if not isinstance(value, bool):
        return
    S.asked = now()
    if value != S.on:
        S.on = value
        save()
        print(f"[{datetime.fromtimestamp(now(), KST):%m-%d %H:%M}] 오라클 봇: 리그 관리자 페이지에서 "
              + ("켰습니다. 승부 예측을 받습니다." if value else "껐습니다. 새 승부 예측을 열지 않습니다(받던 판은 끝까지 처리합니다)."))


async def check_switch(force: bool = False) -> None:
    """주인이 오라클 봇을 켜 두었는지 리그 서버에 물어본다(5분마다). 서버는 이때 봇이 다녀간 시각을 적어 두어 리그 관리자 페이지에 보여 준다.
    답을 받지 못하면 알고 있던 대로 둔다"""
    if S.host is None or S.host.server is None or (not force and now() - S.asked < SWITCH_POLL):
        return
    S.asked = now()
    try:
        got = await S.host.server({"action": "adminOracle", "brief": True})
    except Exception as e:
        note(f"오라클: 리그 서버에서 켜 두었는지 확인하지 못했습니다. 알고 있던 대로 둡니다. ({e})")
        return
    if isinstance(got.get("oracleOn"), bool):
        hear(got["oracleOn"], got.get("oraclePlay"))
    else:  # 예전 서버(버전 17까지)는 이 값을 모른다
        note("오라클: 리그 서버가 오라클 봇을 켜 두었는지 알려 주지 않습니다(서버 버전 18부터). Code.gs 를 새 버전으로 배포하기 전에는 꺼진 채로 둡니다.")


# ── 포인트 ────────────────────────────────────────────────────
def week_start(at: float | None = None) -> int:
    """그 시각이 든 주가 시작한 때: 월요일 0시 (한국 시간)"""
    day = datetime.fromtimestamp(now() if at is None else at, KST)
    monday = (day - timedelta(days=day.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(monday.timestamp())


def account(uid: int) -> dict:
    return S.accounts.setdefault(str(uid), {"points": 0, "claimed": 0, "week": 0, "name": "", "username": "", "nick": "",
                                            "bets": 0, "hits": 0, "profit": 0, "played": 0, "earned": 0})


def remember(uid: int, user) -> dict:
    """그 사람의 포인트 기록. 순위 페이지에 적을 이름(서버 별명, 사용자명)을 지금 것으로 맞춘다"""
    acc = account(uid)
    acc["name"] = str(getattr(user, "display_name", "") or acc["name"])
    acc["username"] = str(getattr(user, "name", "") or acc["username"])
    return acc


def points_of(uid: int) -> int:
    """보유 포인트 (포인트를 받은 적이 없으면 0)"""
    acc = S.accounts.get(str(uid))
    return acc["points"] if acc else 0


def staked(uid: int) -> int:
    """아직 정산되지 않은 판에 걸어 둔 포인트"""
    return sum(b["bets"][str(uid)]["amount"] for b in S.books if b["state"] in ("open", "closed") and str(uid) in b["bets"])


def claim(uid: int, user=None) -> tuple[bool, str]:
    """이번 주 포인트를 받는다. 한 주에 한 번"""
    week = week_start()
    acc = remember(uid, user)
    if acc["week"] == week:
        return False, (f"이번 주 포인트는 이미 받았어요. 다음 포인트는 <t:{week + 7 * 86400}:F>부터 받을 수 있어요.\n"
                       f"보유 포인트는 **{num(acc['points'])}**이에요.")
    acc["points"] += WEEKLY_POINTS
    acc["claimed"] += 1
    acc["week"] = week
    S.dirty = True
    save()
    return True, (f"✅ **{WEEKLY_POINTS:,} 포인트**를 받았어요. 보유 포인트는 **{num(acc['points'])}**이에요.\n"
                  "내전의 팀 편성이 올라오면 그 아래에서 이길 팀에 걸 수 있어요.")


def claim_place() -> str:
    """이번 주 포인트를 받는 곳을 가리키는 말: /오라클설정 으로 정한 채널('포인트 받기' 글이 있는 곳). 정해 두지 않았으면 /포인트"""
    return f"<#{S.channel_id}> 채널의 **포인트 받기**로" if S.channel_id else "`/포인트` 로"


def no_points() -> str:
    """걸 포인트가 없는 사람에게 하는 답"""
    return f"걸 수 있는 포인트가 없어요. {claim_place()} 이번 주 포인트를 받았는지 확인해 보세요."


def points_text(uid: int) -> str:
    """내 포인트 (/포인트 와 '내 포인트' 버튼)"""
    acc = S.accounts.get(str(uid))
    if not acc or not (acc["claimed"] or acc["played"] or acc["points"]):
        return f"아직 포인트를 받은 적이 없어요. **포인트 받기**를 누르면 이번 주 {WEEKLY_POINTS:,} 포인트를 받아요." if S.on else RESTING
    week, out = week_start(), staked(uid)
    lines = [f"🔮 보유 포인트는 **{num(acc['points'])}**이에요." + (f" 걸어 둔 포인트 {out:,}은 뺀 값이에요." if out else ""),
             f"승부 예측 {acc['bets']}번 가운데 {acc['hits']}번 맞혔고, 손익은 {signed(acc['profit'])} 포인트예요."]
    lines.append(RESTING if not S.on
                 else f"이번 주 포인트는 받았어요. 다음 포인트는 <t:{week + 7 * 86400}:F>부터 받을 수 있어요." if acc["week"] == week
                 else "이번 주 포인트를 아직 받지 않았어요. **포인트 받기**를 눌러 받으세요.")
    if not acc["claimed"]:  # 참가 포인트만 받은 사람: 랭킹에는 본인이 한 번이라도 '포인트 받기'를 눌러야 나온다
        lines.append("승부의 신 랭킹에는 **포인트 받기**를 한 번이라도 누른 뒤부터 이름이 올라가요.")
    if S.page:
        lines.append(f"승부의 신 랭킹: <{S.page}>")
    return "\n".join(lines)


# ── 승부 예측 한 판 ────────────────────────────────────────────
def book_key(entry: dict) -> str:
    """퍼그나봇이 짠 팀(편성)마다 하나씩인 이름. 같은 글을 다시 열어 팀을 새로 짜면 다른 판이다"""
    return f"{entry.get('message_id') or 0}:{int(float(entry.get('at') or 0) * 1000)}"


def find_book(key: str) -> dict | None:
    return next((b for b in S.books if b["key"] == key), None)


def book_at(place_id: int, live: bool = False) -> dict | None:
    """그 글에서 연 승부 예측(가장 나중 것). live 면 지금 걸 수 있는 것만"""
    here = [b for b in S.books if b["place_id"] == place_id and (b["state"] == "open" or not live)]
    return here[-1] if here else None


def pools(book: dict) -> dict:
    """양쪽에 걸린 포인트와 사람 수"""
    out = {"r": 0, "d": 0, "nr": 0, "nd": 0}
    for bet in book["bets"].values():
        out[bet["side"]] += bet["amount"]
        out["n" + bet["side"]] += 1
    return out


def payout(book: dict, bet: dict) -> int:
    """그 사람이 건 쪽이 이기면 돌려받는 포인트: 건 포인트를 모두 모아 이긴 쪽이 건 만큼 나눈다. 소수점 아래는 버린다"""
    p = pools(book)
    return bet["amount"] * (p["r"] + p["d"]) // p[bet["side"]]


def bet_block(book: dict | None, uid: int) -> str:
    """걸 수 없는 까닭. 걸 수 있으면 빈 글"""
    if book is None or book["state"] != "open" or now() >= book["closes"]:
        return "이 경기의 승부 예측은 마감됐어요."
    if uid in book["players"]:
        return "이 경기에 뛰는 선수는 걸 수 없어요." + play_promise()
    return ""


def spendable(book: dict, uid: int) -> int:
    """이 판에 걸 수 있는 포인트: 보유 포인트에, 이 판에 이미 걸어 둔 것을 더한 값 (바꿔 걸 수 있다)"""
    old = book["bets"].get(str(uid))
    return points_of(uid) + (old["amount"] if old else 0)


def place(book: dict | None, uid: int, side: str, amount: int, user=None) -> tuple[bool, str]:
    """포인트를 건다. 이미 걸어 두었으면 바꾼다. 건 포인트는 바로 보유 포인트에서 빠진다(여러 판에 겹쳐 쓰지 못하게)"""
    why = bet_block(book, uid)
    if why:
        return False, why
    have = spendable(book, uid)
    if have <= 0:
        return False, no_points()
    if amount < 1:
        return False, "1 포인트 이상 걸어 주세요."
    if amount > have:
        return False, f"포인트가 모자라요. 걸 수 있는 포인트는 **{have:,}**이에요."
    acc = remember(uid, user)
    acc["points"] = have - amount
    book["bets"][str(uid)] = {"side": side, "amount": amount, "at": now()}
    save()
    end = int(book["closes"])
    return True, (f"✅ {SIDES[side]}에 **{amount:,} 포인트**를 걸었어요. 남은 포인트는 {num(acc['points'])}이에요.\n"
                  f"<t:{end}:t>(<t:{end}:R>)에 마감해요. 그때까지 바꾸거나 취소할 수 있어요.")


def cancel(book: dict | None, uid: int) -> tuple[bool, str]:
    """건 것을 취소한다 (마감 전에만)"""
    if book is None or book["state"] != "open" or now() >= book["closes"]:
        return False, "이 경기의 승부 예측은 마감돼서 취소할 수 없어요."
    bet = book["bets"].pop(str(uid), None)
    if bet is None:
        return False, "이 경기에는 걸어 둔 포인트가 없어요."
    acc = account(uid)
    acc["points"] += bet["amount"]
    save()
    return True, f"건 포인트 {bet['amount']:,}을 돌려받았어요. 보유 포인트는 {num(acc['points'])}이에요."


def refund(book: dict) -> None:
    for uid, bet in book["bets"].items():
        account(int(uid))["points"] += bet["amount"]


def close_book(book: dict) -> str:
    """마감한다. 돌려주는 값: "ok"(양쪽에 걸렸다. 결과를 기다린다), "onesided"(한쪽에만 걸려 모두 돌려줬다), "empty"(아무도 걸지 않았다)"""
    book["state"], book["ended"] = "closed", now()
    p = pools(book)
    if p["r"] and p["d"]:
        return "ok"
    refund(book)
    book["state"] = "void"
    return "onesided" if book["bets"] else "empty"


def settle(book: dict, winner: str) -> None:
    """이긴 팀이 정해졌다. 맞힌 사람에게 포인트를 나눠 준다(틀린 사람의 포인트는 걸 때 이미 빠져 있다)"""
    paid = {}
    for uid, bet in book["bets"].items():
        acc = account(int(uid))
        acc["bets"] += 1
        if bet["side"] == winner:
            paid[uid] = payout(book, bet)
            acc["points"] += paid[uid]
            acc["hits"] += 1
            acc["profit"] += paid[uid] - bet["amount"]
        else:
            paid[uid] = 0
            acc["profit"] -= bet["amount"]
    book.update(state="settled", winner=winner, paid=paid, ended=now())
    S.dirty = True


def unsettle(book: dict) -> list[int]:
    """정산을 되돌린다 (/승리취소). 나눠 준 포인트를 도로 가져오고 결과를 기다리는 상태로 돌아간다.
    그사이 그 포인트를 다른 판에 걸어 잃었으면 0보다 적어질 수 있다(운영자가 허용했다). 돌려주는 값: 0보다 적어진 사람들"""
    winner = book["winner"]
    for uid, bet in book["bets"].items():
        acc, got = account(int(uid)), book["paid"].get(uid, 0)
        acc["bets"] -= 1
        acc["points"] -= got
        if bet["side"] == winner:
            acc["hits"] -= 1
            acc["profit"] -= got - bet["amount"]
        else:
            acc["profit"] += bet["amount"]
    book.update(state="closed", winner=None, paid={})
    S.dirty = True
    return [int(uid) for uid in book["bets"] if points_of(int(uid)) < 0]


def play_promise() -> str:
    """그 경기에 뛰는 선수에게 하는 말: 걸 수는 없지만 참가 포인트를 받는다. 주지 않기로 했으면 빈 글"""
    return f" 대신 결과가 기록되면 참가 포인트로 **{S.play:,} 포인트**를 받아요." if S.play > 0 else ""


def grant(book: dict) -> int:
    """참가 포인트: 결과가 기록된 판에 뛴 선수들에게 승패와 상관없이 준다. 준 사람 수를 돌려준다.
    포인트를 받은 적이 없는 선수에게도 쌓인다(랭킹에는 본인이 '포인트 받기'를 한 번이라도 눌러야 나온다).
    얼마를 줬는지 판에 적어 두어, 되돌릴 때는 그사이 금액이 바뀌었어도 준 만큼 그대로 거둔다"""
    if S.play <= 0 or book["off"] or book["play"]:
        return 0
    for uid in book["players"]:
        acc = account(uid)
        acc["points"] += S.play
        acc["played"] += 1
        acc["earned"] += S.play
        book["play"][str(uid)] = S.play
    if book["play"]:
        S.dirty = True
    return len(book["play"])


def ungrant(book: dict) -> None:
    """준 참가 포인트를 거둔다 (/승리취소, 그 판이 없던 일이 됐을 때). 이미 써 버렸으면 0보다 적어질 수 있다(건 포인트의 정산을 되돌릴 때와 같다)"""
    given, book["play"] = book["play"], {}
    for uid, amount in given.items():
        acc = account(int(uid))
        acc["points"] -= amount
        acc["played"] -= 1
        acc["earned"] -= amount
    if given:
        S.dirty = True


def void(book: dict) -> bool:
    """이 판을 없던 일로 하고 건 포인트를 돌려준다(준 참가 포인트는 거둔다). 돌려준 포인트가 있으면 True"""
    if book["state"] == "settled":  # 정산한 판이 없던 일이 됐다. 정산부터 되돌린다
        unsettle(book)
    ungrant(book)
    book["off"], book["winner"] = True, None  # 없던 일이 된 판에는 참가 포인트를 주지 않는다
    if book["state"] not in ("open", "closed"):
        return False
    refund(book)
    book.update(state="void", ended=now())
    return bool(book["bets"])


# ── 글 ────────────────────────────────────────────────────────
def open_text(book: dict) -> str:
    end = int(book["closes"])
    return ("🔮 **승부 예측** — 이 경기에서 이길 팀에 포인트를 걸어 보세요.\n"
            f"⏰ **<t:{end}:t>까지** 걸 수 있어요. (<t:{end}:R> 마감) 마감하면 배당률을 알려 드려요.\n"
            "이 경기에 뛰는 선수는 걸 수 없어요." + (play_promise() + "\n" if S.play > 0 else " ")
            + f"포인트가 없으면 {claim_place()} 이번 주 포인트를 먼저 받으세요.\n"
            f"지금까지 **{len(book['bets'])}명**이 걸었어요.")


def closed_text(kind: str, count: int) -> str:
    """마감한 뒤에, 버튼이 있던 글을 이렇게 고친다"""
    return "🔮 **승부 예측** — " + {
        "ok": f"마감했어요. {count}명이 걸었고, 배당률은 아래에 있어요.",
        "onesided": "마감했어요. 한쪽 팀에만 걸려서 성립하지 않았어요.",
        "empty": "마감했어요. 건 사람이 없었어요.",
        "void": "이 경기가 없던 일이 돼서 취소했어요.",
    }[kind]


def odds(book: dict, side: str) -> str:
    p = pools(book)
    return f"{(p['r'] + p['d']) / p[side]:.2f}배"


def odds_text(book: dict) -> str:
    """마감하고 올리는 글: 양쪽에 걸린 포인트와 배당률, 건 사람마다 이기면 얻고 지면 잃는 포인트"""
    p = pools(book)
    lines = [f"🔮 **승부 예측 마감** — {len(book['bets'])}명이 걸었어요.",
             f"🟢 래디언트 **{p['r']:,}** 포인트 ({p['nr']}명) · 배당 **{odds(book, 'r')}**",
             f"🔴 다이어 **{p['d']:,}** 포인트 ({p['nd']}명) · 배당 **{odds(book, 'd')}**",
             "-# 건 포인트를 모두 모아, 이긴 쪽이 건 만큼 나눠 가져요. 소수점 아래는 버려요."]
    for side in ("r", "d"):
        lines += ["", f"{SIDES[side]}에 건 사람"]
        mine = sorted(((uid, b) for uid, b in book["bets"].items() if b["side"] == side), key=lambda x: (-x[1]["amount"], x[1]["at"]))
        lines += [f"<@{uid}> {b['amount']:,} → 이기면 **+{payout(book, b) - b['amount']:,}** / 지면 −{b['amount']:,}" for uid, b in mine]
    return "\n".join(lines)


def result_text(book: dict) -> str:
    """정산하고 올리는 글"""
    w = book["winner"]
    lines = [f"🔮 **승부 예측 결과** — {SIDES[w]} 승리! (배당 {odds(book, w)})"]
    rows = sorted(book["bets"].items(), key=lambda x: (-x[1]["amount"], x[1]["at"]))
    won = [f"<@{uid}> **+{book['paid'].get(uid, 0) - b['amount']:,}** · 보유 {num(points_of(int(uid)))}" for uid, b in rows if b["side"] == w]
    lost = [f"<@{uid}> −{b['amount']:,} · 보유 {num(points_of(int(uid)))}" for uid, b in rows if b["side"] != w]
    lines += ["", "🎉 **맞힌 사람**"] + won + ["", "💸 **틀린 사람**"] + lost
    if book["play"]:
        lines += ["", play_line(book)]
    if S.page:
        lines += ["", f"📊 승부의 신 랭킹: <{S.page}>"]
    return "\n".join(lines)


def play_line(book: dict) -> str:
    """참가 포인트를 줬다고 알리는 한 줄"""
    return f"🎮 **참가 포인트** — 이 경기에 뛴 선수 {len(book['play'])}명이 **{max(book['play'].values()):,} 포인트**씩 받았어요."


def play_text(book: dict) -> str:
    """정산할 것이 없는 판(건 사람이 없었거나 한쪽에만 걸린 판)에서 참가 포인트만 알리는 글"""
    return play_line(book) + (f"\n\n📊 승부의 신 랭킹: <{S.page}>" if S.page else "")


def round_text() -> str:
    """매주 올리는 '포인트 받기' 글"""
    until = S.round["start"] + 7 * 86400
    return ("🔮 **이번 주 포인트를 받으세요**\n"
            f"리그 선수는 아래 **포인트 받기**를 눌러 **{WEEKLY_POINTS:,} 포인트**를 받을 수 있어요. 한 주에 한 번, <t:{until}:F> 전까지 받을 수 있어요.\n"
            "받은 포인트로 내전의 팀 편성 아래에서 이길 팀에 걸 수 있어요. 받지 않은 주의 포인트는 사라지고, 받은 포인트는 계속 쌓여요.")


def mine_text(book: dict | None, uid: int) -> str:
    """이 경기에 내가 건 것 ('내 베팅' 버튼)"""
    have = num(points_of(uid))
    bet = book["bets"].get(str(uid)) if book else None
    if not bet:
        return f"이 경기에는 걸지 않았어요. 보유 포인트는 {have}이에요."
    mine = f"{SIDES[bet['side']]}에 **{bet['amount']:,} 포인트**"
    if book["state"] == "open":
        end = int(book["closes"])
        return f"{mine}를 걸어 두었어요. <t:{end}:R> 마감하고, 그때까지 바꾸거나 취소할 수 있어요. 보유 포인트는 {have}이에요."
    if book["state"] == "closed":
        return (f"{mine}를 걸었어요. 이기면 **+{payout(book, bet) - bet['amount']:,}**, 지면 −{bet['amount']:,}이에요. "
                f"경기 결과를 기다리고 있어요. 보유 포인트는 {have}이에요.")
    if book["state"] == "settled":
        got = book["paid"].get(str(uid), 0)
        return (f"{mine}를 걸어 " + (f"맞혔어요. **+{got - bet['amount']:,}** 포인트를 얻었어요." if bet["side"] == book["winner"]
                                  else f"틀렸어요. {bet['amount']:,} 포인트를 잃었어요.") + f" 보유 포인트는 {have}이에요.")
    return f"이 경기의 승부 예측은 성립하지 않아서, 건 포인트 {bet['amount']:,}을 돌려받았어요. 보유 포인트는 {have}이에요."


def chunks(text: str) -> list[str]:
    """긴 글을 줄 단위로 나눈다 (건 사람이 많으면 한 메시지에 다 들어가지 않는다)"""
    out, cur = [], ""
    for line in text.split("\n"):
        if cur and len(cur) + 1 + len(line) > MESSAGE_LIMIT:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    return out + [cur] if cur.strip() else out


# ── 디스코드에 올리기 (오라클 봇의 이름으로) ──────────────────────
async def send(place_id: int, text: str, view: discord.ui.View | None = None) -> int:
    """글을 올린다. 길면 나눠 올리고 버튼은 마지막 글에 단다. 돌려주는 값: 버튼을 단(마지막) 글의 번호. 올리지 못하면 0"""
    if not S.ready or not place_id:
        return 0
    place = S.client.get_partial_messageable(int(place_id))
    parts, last = chunks(text), 0
    try:
        for i, part in enumerate(parts):
            more = {"view": view} if view is not None and i == len(parts) - 1 else {}
            last = int((await place.send(part, allowed_mentions=QUIET, **more)).id)
    except discord.HTTPException as e:
        print(f"오라클: 글을 올리지 못했습니다: {e}")
        return 0
    return last


async def edit(place_id: int, message_id: int, text: str, view: discord.ui.View | None = None) -> bool:
    """올려 둔 글을 고친다. view 를 주지 않으면 버튼을 뗀다"""
    if not S.ready or not place_id or not message_id:
        return False
    try:
        message = S.client.get_partial_messageable(int(place_id)).get_partial_message(int(message_id))
        await message.edit(content=text, view=view, allowed_mentions=QUIET)
        return True
    except discord.HTTPException as e:
        print(f"오라클: 글을 고치지 못했습니다: {e}")
        return False


async def remove(place_id: int, message_id: int) -> None:
    if not S.ready or not place_id or not message_id:
        return
    try:
        await S.client.get_partial_messageable(int(place_id)).get_partial_message(int(message_id)).delete()
    except discord.HTTPException as e:
        print(f"오라클: 앞의 글을 지우지 못했습니다: {e}")


async def announce_open(book: dict) -> None:
    """팀 편성 아래에 승부 예측 글과 버튼을 올린다"""
    posted = await send(book["place_id"], open_text(book), BetView())
    if posted:
        book["message_id"] = posted
        save()


async def refresh_open(book: dict) -> None:
    """건 사람 수가 바뀌었다. 버튼이 있는 글을 고친다"""
    if book["state"] == "open" and book["message_id"]:
        await edit(book["place_id"], book["message_id"], open_text(book), BetView())


async def finish(book: dict) -> None:
    """마감하고 배당률을 알린다 (S.lock 을 잡은 채 부른다)"""
    kind = close_book(book)
    save()
    await edit(book["place_id"], book["message_id"], closed_text(kind, len(book["bets"])))
    if kind == "ok":
        await send(book["place_id"], odds_text(book))
    elif kind == "onesided":
        p = pools(book)
        side = "r" if p["r"] else "d"
        await send(book["place_id"], f"🔮 승부 예측을 마감했어요. {SIDES[side]}에만 걸려서({p['n' + side]}명, {p[side]:,} 포인트) 성립하지 않았어요. "
                                     "건 포인트는 모두 돌려드렸어요.")


async def call_off(book: dict, why: str) -> None:
    """이 판을 없던 일로 한다 (S.lock 을 잡은 채 부른다)"""
    was_open, took = book["state"] == "open", bool(book["play"])
    back = void(book)
    save()
    if was_open:
        await edit(book["place_id"], book["message_id"], closed_text("void", 0))
    if back:
        await send(book["place_id"], f"🔮 {why} 승부 예측을 취소했어요. 건 포인트는 모두 돌려드렸어요." + (" 참가 포인트는 거뒀어요." if took else ""))
    elif took:
        await send(book["place_id"], f"🔮 {why} 참가 포인트를 거뒀어요.")


# ── 퍼그나봇이 알려 주는 일들 ───────────────────────────────────
# 퍼그나봇의 흐름(마감, /승리 등)을 멈추면 안 되므로, 여기서 생긴 문제는 창에 찍고 넘어간다.
async def on_lineup(entry: dict) -> None:
    """퍼그나봇이 팀을 짜서 알렸다. 그 글 아래에 승부 예측을 연다 (주인이 꺼 두었으면 열지 않는다)"""
    if not enabled() or not S.on:
        return
    try:
        who = entry.get("who") or {}
        players = sorted({int(who[pid]) for pid in entry.get("ids") or [] if pid in who})  # 그 경기에 뛰는 열 명의 디스코드 ID
        book = {"key": book_key(entry), "place_id": int(entry.get("place_id") or 0), "opened": now(), "closes": now() + BET_SECONDS, "ended": 0.0,
                "state": "open", "players": players, "bets": {}, "message_id": 0, "winner": None, "paid": {}, "play": {}, "off": False}
        S.books.append(book)
        save()
        await announce_open(book)
    except Exception as e:
        print(f"오라클: 승부 예측을 열지 못했습니다: {e!r}")


async def on_result(entry: dict, winner: str) -> None:
    """/승리 로 결과가 기록됐다. 정산하고, 그 판에 뛴 선수들에게 참가 포인트를 준다"""
    if not enabled() or winner not in SIDES:
        return
    try:
        async with S.lock:
            book = find_book(book_key(entry))
            if book is None or book["off"] or book["winner"] is not None:  # 없던 일이 된 판, 이미 결과를 받은 판
                return
            if book["state"] == "open":  # 20분이 되기 전에 결과가 나왔다. 마감부터 한다
                await finish(book)
            bets = book["state"] == "closed"  # 양쪽에 걸려 결과를 기다리던 판. 아니면(건 사람이 없었거나 한쪽에만 걸렸으면) 정산할 것이 없다
            if bets:
                settle(book, winner)
            book["winner"] = winner
            given = grant(book)
            save()
            if bets or given:
                await send(book["place_id"], result_text(book) if bets else play_text(book))
    except Exception as e:
        print(f"오라클: 승부 예측을 정산하지 못했습니다: {e!r}")


async def on_undo(entry: dict) -> None:
    """/승리취소 로 결과가 취소됐다. 정산을 되돌리고, 준 참가 포인트를 거둔다"""
    if not enabled():
        return
    try:
        async with S.lock:
            book = find_book(book_key(entry))
            if book is None or book["winner"] is None:
                return
            settled, took = book["state"] == "settled", bool(book["play"])
            people = ([int(uid) for uid in book["bets"]] if settled else []) + [int(uid) for uid in book["play"]]
            if settled:
                unsettle(book)
            ungrant(book)
            book["winner"] = None
            save()
            if not settled and not took:
                return
            minus = [uid for uid in dict.fromkeys(people) if points_of(uid) < 0]
            what = ("승부 예측의 정산을 되돌리고 참가 포인트를 거뒀어요. 결과가 다시 기록되면 그때 다시 정산하고 다시 드려요." if settled and took
                    else "승부 예측의 정산을 되돌렸어요. 결과가 다시 기록되면 그때 다시 정산해요." if settled
                    else "참가 포인트를 거뒀어요. 결과가 다시 기록되면 그때 다시 드려요.")
            await send(book["place_id"], "🔮 경기 결과가 취소돼서 " + what
                       + ("\n포인트가 0보다 적어진 사람: " + ", ".join(f"<@{uid}> ({num(points_of(uid))})" for uid in minus) if minus else ""))
    except Exception as e:
        print(f"오라클: 승부 예측의 정산을 되돌리지 못했습니다: {e!r}")


async def on_void(entry: dict) -> None:
    """그 팀 편성이 없던 일이 됐다 (/취소, /재모집, 마감한 모집을 다시 열기, 경기 안 함, 시즌이 끝난 뒤의 경기). 건 포인트를 돌려준다"""
    if not enabled():
        return
    try:
        async with S.lock:
            book = find_book(book_key(entry))
            if book is not None:
                await call_off(book, "이 경기가 없던 일이 돼서")
    except Exception as e:
        print(f"오라클: 승부 예측을 취소하지 못했습니다: {e!r}")


# ── 이번 주 '포인트 받기' 글 ────────────────────────────────────
def roll_round() -> bool:
    """새 주가 시작됐으면 이번 주로 넘긴다. 넘겼으면 True"""
    week = week_start()
    if S.round is not None and S.round["start"] == week:
        return False
    old = S.round
    S.round = {"start": week, "message_id": 0, "channel_id": 0,
               "prev": [old["channel_id"], old["message_id"]] if old and old.get("message_id") else None}
    save()
    return True


async def post_round(force: bool = False) -> None:
    """이번 주의 '포인트 받기' 글을 정해 둔 채널에 올린다. 앞의 글은 지워서 글은 늘 하나다. force 면 이미 올렸어도 새로 올린다(채널을 바꿨을 때)"""
    r = S.round
    if not S.ready or not S.on or not S.channel_id or r is None:
        return
    if not force and ((r["message_id"] and r["channel_id"] == S.channel_id) or now() - r.get("tried", 0) < POST_RETRY):
        return
    posted = await send(S.channel_id, round_text(), ClaimView())
    if not posted:
        r["tried"] = now()  # 조금 뒤에 다시 올려 본다
        return
    gone = [x for x in (r.get("prev"), [r["channel_id"], r["message_id"]] if r["message_id"] else None) if x]
    r.update(message_id=posted, channel_id=S.channel_id, prev=None)
    r.pop("tried", None)
    save()
    for channel_id, message_id in gone:
        await remove(channel_id, message_id)


# ── 포인트 순위를 리그 서버에 올리기 ────────────────────────────
def board() -> dict:
    """순위 페이지에 보일 것: 포인트를 받은 적이 있는 사람들. 보유 포인트에는 아직 정산되지 않은 판에 걸어 둔 포인트도 넣는다
    (경기가 끝나기 전에는 순위가 바뀌지 않게). 이름은 리그 닉네임이고, 모르면 디스코드 서버 별명이다. 디스코드 ID는 싣지 않는다"""
    rows = []
    for uid, acc in S.accounts.items():
        if not acc["claimed"]:
            continue
        nick = S.host.nickname(int(uid), acc["username"]) if S.host is not None else None
        if nick:
            acc["nick"] = str(nick)
        rows.append({"name": acc["nick"] or acc["name"] or "이름 없음", "points": acc["points"] + staked(int(uid)), "profit": acc["profit"],
                     "bets": acc["bets"], "hits": acc["hits"], "claimed": acc["claimed"]})
    rows.sort(key=lambda x: (-x["points"], -x["profit"], x["name"]))
    return {"updatedAt": datetime.fromtimestamp(now(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "weekly": WEEKLY_POINTS, "play": S.play, "players": rows}


async def publish() -> None:
    """바뀐 순위를 리그 서버에 올린다(순위 페이지가 읽는다). 포인트 기록도 사본으로 함께 올려, 이 PC의 파일을 잃어도 되살릴 수 있게 한다"""
    if not S.dirty or S.host is None or S.host.server is None or now() < S.publish_at:
        return
    try:
        await S.host.server({"action": "saveOracle", "board": board(), "state": snapshot()})
    except Exception as e:
        S.publish_at = now() + PUBLISH_RETRY
        note(f"오라클: 포인트 순위를 리그 서버에 올리지 못했습니다. 10분 뒤에 다시 올려 봅니다. ({e})")
        return
    S.dirty = False
    S.publish_at = now() + PUBLISH_GAP
    save()


async def restore() -> None:
    """켤 때 한 번: 이 PC에 포인트 기록이 없으면(파일을 잃었거나 봇을 다른 PC로 옮겼으면) 리그 서버에 올려 둔 사본을 받아 온다"""
    if S.loaded or S.host is None or S.host.server is None:
        return
    S.loaded = True
    try:
        state = (await S.host.server({"action": "adminOracle"})).get("state")
    except Exception as e:
        print(f"오라클: 리그 서버에서 포인트 기록의 사본을 확인하지 못했습니다. 새로 시작합니다. ({e})")
        return
    if isinstance(state, dict) and state.get("accounts") and not S.accounts and not S.books:
        adopt(state)
        save()
        print(f"오라클: 이 PC에 포인트 기록이 없어 리그 서버의 사본을 받아 왔습니다. ({len(S.accounts)}명)")


# ── 주기적으로 확인 ────────────────────────────────────────────
async def tick() -> None:
    """마감할 판을 마감하고, 새 주가 시작됐으면 '포인트 받기' 글을 올리고, 바뀐 순위를 서버에 올린다.
    주인이 꺼 둔 동안에도 받던 판은 여기서 끝까지 처리한다"""
    await check_switch()
    roll_round()
    await post_round()
    for book in list(S.books):
        async with S.lock:
            if book["state"] == "open" and now() >= book["closes"]:
                await finish(book)  # 봇이 꺼져 있던 사이에 20분이 지났으면 켜자마자 여기서 마감한다
            elif book["state"] == "open" and not book["message_id"]:
                await announce_open(book)  # 오라클 봇이 로그인하기 전에 짜인 팀
            if book["state"] in ("open", "closed") and now() - book["opened"] > BOOK_TTL:
                await call_off(book, "결과가 기록되지 않은 채 이틀이 지나서")
    keep_from = now() - KEEP_SECONDS
    kept = [b for b in S.books if b["state"] in ("open", "closed") or b["ended"] >= keep_from]
    if len(kept) != len(S.books):
        S.books = kept
        save()
    await publish()


async def loop() -> None:
    while True:
        try:
            await tick()
        except Exception as e:  # 디스코드나 서버가 잠깐 답하지 않아도 다음 차례에 다시 한다
            print(f"오라클: 이번 확인을 마치지 못했습니다. 다음 차례에 다시 합니다. ({e!r})")
        await asyncio.sleep(TICK_SECONDS)


# ── 버튼과 명령어 ──────────────────────────────────────────────
async def reply(interaction: discord.Interaction, text: str, view: discord.ui.View | None = None) -> None:
    """본인에게만 보이는 답"""
    more = {"view": view} if view is not None else {}
    await interaction.response.send_message(text, ephemeral=True, **more)


async def claim_points(interaction: discord.Interaction) -> None:
    """'포인트 받기' 버튼"""
    if not await S.host.can_play(interaction.user):
        await reply(interaction, PLAYER_ONLY)
        return
    if not S.on:
        await reply(interaction, RESTING)
        return
    _, text = claim(interaction.user.id, interaction.user)
    await reply(interaction, text)


async def show_points(interaction: discord.Interaction) -> None:
    """/포인트 와 '내 포인트' 버튼: 내 포인트를 본다. 이번 주 포인트를 아직 받지 않았으면 받기 버튼을 함께 보여 준다"""
    if not await S.host.can_play(interaction.user):
        await reply(interaction, PLAYER_ONLY)
        return
    acc = S.accounts.get(str(interaction.user.id))
    waiting = S.on and (not acc or acc["week"] != week_start())
    await reply(interaction, points_text(interaction.user.id), ClaimView() if waiting else None)


async def pick_side(interaction: discord.Interaction, side: str) -> None:
    """래디언트·다이어 버튼: 얼마를 걸지 고르는 버튼을 본인에게만 보여 준다"""
    uid = interaction.user.id
    if not await S.host.can_play(interaction.user):
        await reply(interaction, PLAYER_ONLY)
        return
    if not S.on:
        await reply(interaction, RESTING)
        return
    book = book_at(interaction.channel_id, live=True)
    why = bet_block(book, uid)
    if why:
        await reply(interaction, why)
        return
    have = spendable(book, uid)
    if have <= 0:
        await reply(interaction, no_points())
        return
    old = book["bets"].get(str(uid))
    text = f"{SIDES[side]}에 얼마를 걸까요? 걸 수 있는 포인트는 **{have:,}**이에요."
    if old:
        text += f"\n지금은 {SIDES[old['side']]}에 {old['amount']:,} 포인트를 걸어 두었어요. 새로 고르면 그것으로 바뀌어요."
    await reply(interaction, text, AmountView(book["key"], side, have))


async def put_amount(interaction: discord.Interaction, key: str, side: str, amount: int) -> None:
    """금액 버튼(또는 직접 입력): 건다. 금액을 고르던 글을 결과로 바꾼다"""
    if not await S.host.can_play(interaction.user):
        await interaction.response.edit_message(content=PLAYER_ONLY, view=None)
        return
    if not S.on:
        await interaction.response.edit_message(content=RESTING, view=None)
        return
    book = find_book(key)
    ok, text = place(book, interaction.user.id, side, amount, interaction.user)
    await interaction.response.edit_message(content=text, view=MineView(key) if ok else None)
    if ok:
        await refresh_open(book)


async def show_mine(interaction: discord.Interaction) -> None:
    """'내 베팅' 버튼"""
    book = book_at(interaction.channel_id)
    uid = interaction.user.id
    mine = bool(book and book["state"] == "open" and str(uid) in book["bets"])
    await reply(interaction, mine_text(book, uid), MineView(book["key"]) if mine else None)


async def cancel_bet(interaction: discord.Interaction, key: str) -> None:
    """'베팅 취소' 버튼"""
    book = find_book(key)
    ok, text = cancel(book, interaction.user.id)
    await interaction.response.edit_message(content=text, view=None)
    if ok:
        await refresh_open(book)


class Buttons(discord.ui.View):
    """오라클 봇의 버튼 묶음. 처리하다 생긴 문제는 창에 찍는다"""

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        print(f"오라클: 버튼 처리 오류: {error!r}")
        if not interaction.response.is_done():
            await interaction.response.send_message("처리하다 문제가 생겼어요. 잠시 뒤에 다시 눌러 주세요.", ephemeral=True)


class ClaimView(Buttons):
    """매주 올리는 '포인트 받기' 글의 버튼. 봇을 껐다 켜도 눌리게 시간 제한을 두지 않는다(켤 때 다시 등록한다)"""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="포인트 받기", style=discord.ButtonStyle.success, custom_id="oracle:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await claim_points(interaction)

    @discord.ui.button(label="내 포인트", style=discord.ButtonStyle.secondary, custom_id="oracle:points")
    async def points(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await show_points(interaction)


class BetView(Buttons):
    """팀 편성 아래에 올리는 승부 예측 글의 버튼. 어느 판인지는 버튼을 누른 글(내전의 글)로 안다"""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="래디언트", emoji="🟢", style=discord.ButtonStyle.success, custom_id="oracle:bet:r")
    async def radiant(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await pick_side(interaction, "r")

    @discord.ui.button(label="다이어", emoji="🔴", style=discord.ButtonStyle.danger, custom_id="oracle:bet:d")
    async def dire(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await pick_side(interaction, "d")

    @discord.ui.button(label="내 베팅", style=discord.ButtonStyle.secondary, custom_id="oracle:mine")
    async def mine(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await show_mine(interaction)


class AmountButton(discord.ui.Button):
    def __init__(self, key: str, side: str, amount: int, label: str) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.key, self.side, self.amount = key, side, amount

    async def callback(self, interaction: discord.Interaction) -> None:
        await put_amount(interaction, self.key, self.side, self.amount)


class TypeButton(discord.ui.Button):
    def __init__(self, key: str, side: str, have: int) -> None:
        super().__init__(label="직접 입력", style=discord.ButtonStyle.secondary)
        self.key, self.side, self.have = key, side, have

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AmountModal(self.key, self.side, self.have))


class AmountModal(discord.ui.Modal):
    """걸 포인트를 숫자로 적는 창"""

    def __init__(self, key: str, side: str, have: int) -> None:
        super().__init__(title="걸 포인트")
        self.key, self.side = key, side
        self.amount = discord.ui.TextInput(label=f"걸 포인트 (1 ~ {have:,})", placeholder="예: 250", max_length=9)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = str(self.amount.value).replace(",", "").strip()
        if not raw.isdigit():
            await interaction.response.edit_message(content="걸 포인트는 숫자로 적어 주세요. 진영 버튼을 다시 눌러 주세요.", view=None)
            return
        await put_amount(interaction, self.key, self.side, int(raw))


class AmountView(Buttons):
    """얼마를 걸지 고르는 버튼 (누른 사람에게만 보이는 글에 단다). 5분 동안만 눌린다"""

    def __init__(self, key: str, side: str, have: int) -> None:
        super().__init__(timeout=300)
        for amount in AMOUNTS:
            if amount <= have:
                self.add_item(AmountButton(key, side, amount, f"{amount:,}"))
        self.add_item(AmountButton(key, side, have, f"전부 ({have:,})"))
        self.add_item(TypeButton(key, side, have))


class CancelButton(discord.ui.Button):
    def __init__(self, key: str) -> None:
        super().__init__(label="베팅 취소", style=discord.ButtonStyle.secondary)
        self.key = key

    async def callback(self, interaction: discord.Interaction) -> None:
        await cancel_bet(interaction, self.key)


class MineView(Buttons):
    """건 사람에게만 보이는 '베팅 취소' 버튼"""

    def __init__(self, key: str) -> None:
        super().__init__(timeout=300)
        self.add_item(CancelButton(key))


async def cmd_points(interaction: discord.Interaction) -> None:
    await show_points(interaction)


@app_commands.rename(channel="채널")
@app_commands.describe(channel="매주 '포인트 받기' 글을 올릴 채널. 비우면 지금 설정을 보여 줍니다")
async def cmd_setup(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
    """/오라클설정: '포인트 받기' 글을 올릴 채널을 정한다 (리그 관리자 전용, 운영진 채널에서)"""
    if not S.host.is_manager(interaction.user):
        await reply(interaction, "이 명령어를 사용할 권한이 없어요. 리그 관리자만 쓸 수 있는 명령어예요.")
        return
    if interaction.channel_id != S.host.admin_channel_id:
        await reply(interaction, "이 명령어는 운영진 채널에서만 쓸 수 있어요.")
        return
    actor = f"<@{interaction.user.id}>"
    if channel is None:
        await interaction.response.defer()
        await check_switch(force=True)  # 리그 관리자 페이지에서 방금 켜고 껐으면 여기서 바로 반영된다
        where = f"<#{S.channel_id}>" if S.channel_id else "정하지 않음 (정하면 그 채널에 이번 주 글을 올려요)"
        got = sum(1 for a in S.accounts.values() if a["claimed"])
        await interaction.followup.send(f"{actor}님, 오라클 봇의 설정이에요.\n"
                                        f"승부 예측: {'**켜짐**' if S.on else '**꺼짐**'} (주인이 리그 관리자 페이지에서 켜고 꺼요. 바꾸면 5분 안에 반영돼요)\n"
                                        f"참가 포인트: {f'한 판에 **{S.play:,}**' if S.play else '**주지 않음**'} "
                                        "(결과가 기록되면 그 판에 뛴 선수가 받아요. 주인이 리그 관리자 페이지에서 바꿔요)\n"
                                        f"'포인트 받기' 글을 올리는 채널: {where}\n포인트를 받은 적이 있는 사람: {got}명", allowed_mentions=QUIET)
        return
    S.channel_id = channel.id
    save()
    await interaction.response.send_message(f"{actor}님이 '포인트 받기' 글을 올릴 채널을 <#{channel.id}> 로 정했어요. "
                                            + ("이번 주 글을 그 채널에 올려요." if S.on else "오라클 봇이 켜지면 그 채널에 올려요."), allowed_mentions=QUIET)
    roll_round()
    await post_round(force=True)


class OracleBot(discord.Client):
    def __init__(self) -> None:
        # 서버의 채널과 역할만 알면 된다(누가 버튼을 눌렀는지는 그 요청에 실려 온다). 특권 인텐트는 쓰지 않는다
        super().__init__(intents=discord.Intents(guilds=True), allowed_mentions=QUIET)
        self.tree = app_commands.CommandTree(self)
        self.started = False

    async def setup_hook(self) -> None:
        # 버튼은 봇을 껐다 켠 뒤에도 눌려야 한다. 켤 때마다 다시 등록해 둔다
        self.add_view(ClaimView())
        self.add_view(BetView())
        add_commands(self.tree, S.host.guild)
        await self.tree.sync(guild=S.host.guild)  # 서버 단위로 등록하면 명령어가 바로 보인다

    async def on_ready(self) -> None:
        print(f"오라클 봇 로그인 완료: {self.user}")
        if self.started:  # 연결이 끊겼다 다시 붙을 때는 다시 하지 않는다
            return
        self.started = True
        await restore()
        await check_switch(force=True)  # 주인이 켜 두었는지부터 물어본다
        S.ready = True
        for line in status():
            print(line)
        S.task = asyncio.create_task(loop())


def add_commands(tree: app_commands.CommandTree, guild) -> None:
    """오라클 봇의 명령어 둘을 등록한다"""
    tree.command(name="포인트", description="내 포인트를 보고, 이번 주 포인트를 받습니다 (리그 선수)", guild=guild)(cmd_points)
    tree.command(name="오라클설정", description="매주 '포인트 받기' 글을 올릴 채널을 정합니다 (리그 관리자 전용)", guild=guild)(cmd_setup)
    tree.error(on_command_error)


async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    print(f"오라클: 명령어 오류: {error!r}")
    if not interaction.response.is_done():
        await interaction.response.send_message("명령어를 처리하다 문제가 생겼어요. 잠시 뒤에 다시 해 주세요.", ephemeral=True)


def status() -> list[str]:
    """지금 설정을 몇 줄로 (켤 때 창에 찍는다)"""
    guild = S.client.get_guild(S.host.guild.id)
    if guild is None:
        return ["[확인 필요] 오라클 봇이 디스코드 서버에 들어와 있지 않습니다. 초대 링크로 서버에 넣어 주세요."]

    def missing(channel, wanted: dict) -> str:
        perms = channel.permissions_for(guild.me)
        lack = [name for attr, name in wanted.items() if not getattr(perms, attr)]
        return f" [확인 필요] 오라클 봇에 없는 권한: {', '.join(lack)}" if lack else " - 권한 확인"

    signup = guild.get_channel(S.host.signup_channel_id)
    lines = ["오라클 봇: " + ("켜짐 (승부 예측을 받습니다)" if S.on
                           else "꺼짐 (주인이 리그 관리자 페이지에서 오라클 봇을 켜면 5분 안에 승부 예측을 받습니다)"),
             "오라클 참가 포인트(결과가 기록되면 그 판에 뛴 선수에게 줍니다): " + (f"한 판에 {S.play:,}" if S.play else "주지 않음 (0)"),
             "오라클 승부 예측(팀 편성 아래에 올립니다): " + (
        f"#{signup.name}" + missing(signup, {"view_channel": "채널 보기", "send_messages_in_threads": "스레드에서 메시지 보내기"}
                                    if isinstance(signup, discord.ForumChannel) else {"view_channel": "채널 보기", "send_messages": "메시지 보내기"})
        if signup is not None else "[확인 필요] 오라클 봇이 참여 신청 채널을 볼 수 없습니다. 그 채널에 오라클 봇을 넣어 주세요.")]
    channel = guild.get_channel(S.channel_id) if S.channel_id else None
    lines.append("오라클 '포인트 받기' 글: " + (
        f"#{channel.name}" + missing(channel, {"view_channel": "채널 보기", "send_messages": "메시지 보내기"}) if channel is not None
        else "[확인 필요] 정해 둔 채널을 찾지 못했습니다. `/오라클설정` 으로 다시 정해 주세요." if S.channel_id
        else "채널을 정하지 않음 (리그 관리자가 운영진 채널에서 `/오라클설정` 으로 정하면 올립니다. `/포인트` 로는 지금도 받을 수 있습니다)"))
    lines.append("오라클 승부의 신 랭킹: " + ((S.page or "페이지 주소를 정하지 않음 (config.json 의 oracle_page)")
                                    + ("" if S.host.server is not None else " [확인 필요] 리그 서버 설정(sync_url, sync_key)이 없어 순위를 올리지 못합니다")))
    return lines


def status_line() -> str:
    """퍼그나봇이 켤 때 창에 찍는 한 줄"""
    return "켜는 중 (로그인하면 아래에 따로 알립니다)" if enabled() else "꺼짐 (config.json 에 oracle_token 을 넣으면 켜집니다)"


async def run() -> None:
    """오라클 봇을 켠다. 퍼그나봇과 같은 프로그램 안에서 함께 돈다. 켜지 못해도 퍼그나봇은 그대로 돈다"""
    S.client = OracleBot()
    try:
        async with S.client:
            await S.client.start(S.token)
    except discord.LoginFailure:
        print("[확인 필요] 오라클 봇이 로그인하지 못했습니다. config.json 의 oracle_token 이 맞는지 확인하세요. 퍼그나봇은 그대로 돕니다.")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[확인 필요] 오라클 봇이 멈췄습니다. 퍼그나봇은 그대로 돕니다. ({e!r})")
    finally:
        S.ready = False
