"""
오라클 봇(승부 예측) 테스트: bot/oracle.py 를 가짜 디스코드 객체와 가짜 리그 서버로 돌려 본다 (실제 디스코드에는 연결하지 않는다).

    python tests/oracle.test.py

oracle.py 는 bot.py 를 불러오지 않으므로 그대로 불러와, 퍼그나봇이 넘겨주는 것(host)을 가짜로 넣어 준다.
"""
import asyncio
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord

SRC = Path(__file__).resolve().parent.parent / "bot" / "oracle.py"
HERE = Path(tempfile.mkdtemp(prefix="inhouse-oracle-test-"))
KST = timezone(timedelta(hours=9))
failed = 0


def check(cond, label):
    global failed
    if cond:
        print("ok  ", label)
    else:
        failed += 1
        print("FAIL", label)


def load():
    spec = importlib.util.spec_from_file_location("oraclemod", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Msg:
    """가짜 메시지. 고치고 지운 것을 적어 둔다"""

    def __init__(self, mid, text="", view=None):
        self.id, self.text, self.view, self.edits, self.deleted = mid, text, view, [], False
        self.stuck, self.missing, self.tries = False, False, 0     # stuck: 지우지 못한다. missing: 이미 지워졌다. tries: 지우려 한 횟수

    async def edit(self, **kw):
        self.edits.append(kw)
        self.text, self.view = kw.get("content", self.text), kw.get("view")

    async def delete(self):
        self.tries += 1
        if self.missing:
            self.deleted = True
            raise discord.NotFound(Mock(status=404, reason="Not Found"), "Unknown Message")
        if self.stuck:
            raise discord.HTTPException(Mock(status=500, reason="Server Error"), "서버 오류")
        self.deleted = True


class Place:
    """가짜 채널(또는 내전의 글). 올린 글을 차례로 적어 둔다"""

    def __init__(self, world, cid):
        self.world, self.id, self.sent, self.broken = world, cid, [], False

    async def send(self, text, **kw):
        if self.broken:
            raise discord.Forbidden(Mock(status=403, reason="Forbidden"), "Missing Permissions")
        self.world.count += 1
        m = Msg(self.world.count, text, kw.get("view"))
        self.sent.append(m)
        self.world.messages[m.id] = m
        return m

    def get_partial_message(self, mid):
        return self.world.messages[mid]

    def texts(self):
        return [m.text for m in self.sent]


class World:
    """가짜 디스코드와 가짜 리그 서버, 그리고 시계"""

    def __init__(self, mod, path, at, server=True):
        self.mod, self.count, self.messages, self.places = mod, 5000, {}, {}
        self.at = at                      # 지금 시각 (mod.now 가 돌려준다)
        self.players = set()              # 리그 선수 역할이 있는 사람들
        self.nicks = {}                   # 디스코드 ID → 리그 닉네임
        self.asked, self.fail, self.backup = [], False, None
        self.switch = True                # 주인이 리그 관리자 페이지에서 오라클 봇을 켜 두었는지. None 이면 그 값을 모르는 예전 서버처럼 군다
        self.polls, self.deaf = 0, False  # 봇이 켜 두었는지 물어본 횟수. deaf 면 그 물음에 답하지 않는다
        self.play = None                  # 리그 서버가 알려 주는 참가 포인트. None 이면 그 값을 모르는 예전 서버처럼 군다
        self.reset = None                 # 리그 서버가 알려 주는 '포인트를 초기화하라'는 표시. None 이면 그 값을 모르는 예전 서버처럼 군다
        self.first = None                 # 리그 서버가 알려 주는 그날의 첫 내전의 참가 포인트. None 이면 그 값을 모르는 예전 서버처럼 군다
        self.grants = None                # 리그 서버가 알려 주는 시간 등록 포인트(넣어 달라는 것들). None 이면 싣지 않는다
        self.acks, self.ack_fail = [], False   # 넣었다고 알려 온 것들. ack_fail 이면 그 알림에 답하지 않는다

        async def can_play(user):
            return user.id in self.players

        async def ask(payload):
            if payload["action"] == "adminOracle" and payload.get("brief"):   # 켜 두었는지 5분마다 물어본다
                self.polls += 1
                if self.deaf:
                    raise RuntimeError("서버가 답하지 않음")
                extra = {} if self.play is None else {"oraclePlay": self.play}
                if self.reset is not None:
                    extra["oracleReset"] = self.reset
                if self.first is not None:
                    extra["oracleFirst"] = self.first
                if self.grants:
                    extra["timeGrants"] = self.grants
                return {"ok": True} if self.switch is None else {"ok": True, "oracleOn": self.switch, **extra}
            if payload["action"] == "adminTimeAck":
                if self.ack_fail:
                    raise RuntimeError("서버가 답하지 않음")
                self.acks.append(payload["grants"])
                self.grants = [g for g in self.grants or [] if not (isinstance(g, dict) and g.get("g") in payload["grants"])]
                return {"ok": True, "left": len(self.grants)}
            self.asked.append(payload)
            if self.fail:
                raise RuntimeError("서버 오류")
            if payload["action"] == "saveOracle" and self.reset is not None and payload.get("reset") != self.reset:
                return {"ok": True, "stale": True, "oracleReset": self.reset}   # 초기화 전의 순위는 받지 않는다
            return {"ok": True, "state": self.backup} if payload["action"] == "adminOracle" else {"ok": True}

        mod.now = lambda: self.at
        mod.S = mod.State()
        mod.setup(token="x", path=path, page="https://example.invalid/oracle.html", host=SimpleNamespace(
            guild=discord.Object(id=1), admin_channel_id=100, signup_channel_id=200, can_play=can_play,
            is_manager=lambda user: user.id == 1, nickname=lambda uid, username: self.nicks.get(uid), server=ask if server else None))
        self.lookups = []                 # 봇이 이름을 디스코드에 물어본 사람 (fill_names)

        async def fetch_user(uid):
            self.lookups.append(uid)
            return user(uid)

        mod.S.client = SimpleNamespace(get_partial_messageable=self.place, get_guild=lambda gid: None, fetch_user=fetch_user)
        mod.S.ready = True
        mod.S.on = True                   # 주인이 켜 둔 상태에서 본다 (꺼 둔 경우는 따로 본다)
        mod.S.play = 0                    # 참가 포인트는 주지 않는 것으로 두고 본다 (주는 경우는 따로 본다)
        mod.S.first_play = 0              # 그날의 첫 내전의 참가 포인트도 (주는 경우는 따로 본다)

    def place(self, cid):
        if cid not in self.places:
            self.places[cid] = Place(self, cid)
        return self.places[cid]


def user(uid, name=None):
    return SimpleNamespace(id=uid, display_name=name or f"선수{uid}", name=f"u{uid}")


def inter(channel_id, u):
    i = Mock()
    i.channel_id, i.user = channel_id, u
    i.response = Mock()
    i.response.send_message, i.response.edit_message, i.response.send_modal = AsyncMock(), AsyncMock(), AsyncMock()
    i.response.defer = AsyncMock()
    i.response.is_done = Mock(return_value=False)
    i.followup = Mock()
    i.followup.send = AsyncMock()
    return i


def said(i):
    """그 요청에 한 답 (새로 보낸 답이거나, 버튼이 있던 글을 고친 것)"""
    if i.response.send_message.call_args:
        return i.response.send_message.call_args.args[0]
    if i.followup.send.call_args:
        return i.followup.send.call_args.args[0]
    return i.response.edit_message.call_args.kwargs["content"] if i.response.edit_message.call_args else ""


def view_of(i):
    call = i.response.send_message.call_args or i.response.edit_message.call_args
    return call.kwargs.get("view")


def labels(view):
    return [c.label for c in view.children] if view is not None else []


def lineup(n, place=300, at=None):
    """퍼그나봇이 짠 팀(편성). 뛰는 열 명은 디스코드 ID 100~109, 쉬는 사람은 110·111"""
    ids = [f"p{k}" for k in range(10)]
    return {"at": at if at is not None else 1000.5 + n, "ids": ids, "message_id": place, "place_id": place,
            "who": {f"p{k}": 100 + k for k in range(12)}, "lanes": [], "result": None}


async def main():
    mod = load()
    T0 = datetime(2026, 10, 13, 12, 0, 0, tzinfo=KST).timestamp()       # 화요일 낮 12시
    MON = int(datetime(2026, 10, 12, 0, 0, 0, tzinfo=KST).timestamp())   # 그 주의 월요일 0시
    WEEK = 7 * 86400
    path = HERE / "oracle.json"

    # ── 한 주의 시작: 월요일 0시 (한국 시간) ──
    w = World(mod, path, T0)
    check(mod.week_start() == MON and mod.week_start(MON) == MON and mod.week_start(MON - 1) == MON - WEEK and mod.week_start(MON + WEEK - 1) == MON
          and mod.week_start(MON + WEEK) == MON + WEEK, "한 주는 월요일 0시(한국 시간)에 시작한다")
    check(mod.enabled() and mod.num(1234567) == "1,234,567" and mod.num(-300) == "−300" and mod.signed(250) == "+250" and mod.signed(0) == "0"
          and mod.signed(-40) == "−40", "숫자 적는 법")

    # ── 포인트 받기: 리그 선수가 한 주에 한 번, 본인이 눌러야 받는다 ──
    A, B, C, D, GUEST, ADMIN = user(11, "가"), user(12, "나"), user(13, "다"), user(14, "라"), user(99, "손님"), user(1, "운영자")
    w.players = {11, 12, 13, 14, 110, 1} | set(range(100, 110))
    i = inter(400, GUEST)
    await mod.claim_points(i)
    check(said(i) == mod.PLAYER_ONLY and i.response.send_message.call_args.kwargs["ephemeral"] is True and "99" not in mod.S.accounts,
          "포인트 받기: 리그 선수가 아니면 받지 못한다 (본인에게만 알린다)")
    i = inter(400, A)
    await mod.claim_points(i)
    check(said(i).startswith("✅ **1,000 포인트**를 받았어요. 보유 포인트는 **1,000**이에요.") and i.response.send_message.call_args.kwargs["ephemeral"] is True
          and mod.S.accounts["11"] == {"points": 1000, "claimed": 1, "week": MON, "name": "가", "username": "u11", "nick": "", "bets": 0, "hits": 0, "profit": 0,
                                     "played": 0, "earned": 0, "listed": True},
          "포인트 받기: 누르면 1000 포인트를 받는다")
    i = inter(400, A)
    await mod.claim_points(i)
    check(said(i).startswith(f"이번 주 포인트는 이미 받았어요. 다음 포인트는 <t:{MON + WEEK}:F>부터 받을 수 있어요.") and mod.S.accounts["11"]["points"] == 1000,
          "포인트 받기: 한 주에 한 번만 받는다")
    check(json.loads(path.read_text(encoding="utf-8"))["accounts"]["11"]["points"] == 1000 and mod.S.dirty, "받은 포인트를 파일에 적어 둔다")
    w.at = MON + WEEK - 1
    i = inter(400, A)
    await mod.claim_points(i)
    check(mod.S.accounts["11"]["points"] == 1000, "일요일 밤 11시 59분까지는 같은 주다")
    w.at = MON + WEEK
    i = inter(400, A)
    await mod.claim_points(i)
    check(mod.S.accounts["11"]["points"] == 2000 and mod.S.accounts["11"]["claimed"] == 2 and "보유 포인트는 **2,000**" in said(i),
          "다음 월요일 0시부터 또 받을 수 있고, 포인트는 쌓인다")
    w.at = MON + 3 * WEEK
    i = inter(400, A)
    await mod.claim_points(i)
    check(mod.S.accounts["11"]["points"] == 3000 and mod.S.accounts["11"]["claimed"] == 3, "받지 않은 주의 포인트는 사라진다 (한 주를 건너뛰어도 한 번만 받는다)")

    # 내 포인트 ('내 포인트' 버튼). 받기 버튼은 '포인트 받기' 글에만 있다
    i = inter(400, B)
    await mod.show_points(i)
    check(said(i) == "아직 포인트를 받은 적이 없어요. **포인트 받기**를 누르면 이번 주 1,000 포인트를 받아요." and view_of(i) is None
          and i.response.send_message.call_args.kwargs["ephemeral"] is True, "내 포인트: 받은 적이 없으면 그렇게 알려 준다 (본인에게만. 받기 버튼을 따로 달지 않는다)")
    i = inter(400, A)
    await mod.show_points(i)
    check(said(i) == "🔮 보유 포인트는 **3,000**이에요.\n승부 예측 0번 가운데 0번 맞혔고, 손익은 0 포인트예요.\n"
          f"이번 주 포인트는 받았어요. 다음 포인트는 <t:{MON + 4 * WEEK}:F>부터 받을 수 있어요.\n승부의 신 랭킹: <https://example.invalid/oracle.html>"
          and view_of(i) is None, "내 포인트: 보유 포인트와 전적, 랭킹 페이지")
    w.at += WEEK
    i = inter(400, A)
    await mod.show_points(i)
    check("이번 주 포인트를 아직 받지 않았어요. **포인트 받기**를 눌러 받으세요." in said(i) and view_of(i) is None, "내 포인트: 새 주가 되면 아직 받지 않았다고 알려 준다")
    i = inter(400, GUEST)
    await mod.show_points(i)
    check(said(i) == mod.PLAYER_ONLY, "내 포인트: 리그 선수가 아니면 보지 못한다")

    # ── 매주 올리는 '포인트 받기' 글 ──
    w = World(mod, path, T0)                   # 봇을 껐다 켠 것처럼: 파일에서 이어받는다
    check(mod.S.loaded and mod.S.accounts["11"]["points"] == 3000 and mod.S.accounts["11"]["week"] == MON + 3 * WEEK, "봇을 껐다 켜도 포인트가 남는다")
    mod.S.accounts = {}
    w.players = {11, 12, 13, 14, 110, 1} | set(range(100, 110))
    await mod.tick()
    check(mod.S.round == {"start": MON, "message_id": 0, "channel_id": 0, "stale": []} and not w.places, "채널을 정하기 전에는 글을 올리지 않는다")
    i = inter(100, B)
    await mod.cmd_setup(i, None)
    check(said(i) == "이 명령어를 사용할 권한이 없어요. 리그 관리자만 쓸 수 있는 명령어예요.", "/오라클설정: 리그 관리자만 쓴다")
    i = inter(300, ADMIN)
    await mod.cmd_setup(i, None)
    check(said(i) == "이 명령어는 운영진 채널에서만 쓸 수 있어요.", "/오라클설정: 운영진 채널에서만 쓴다")
    i = inter(100, ADMIN)
    await mod.cmd_setup(i, None)
    check(said(i) == "<@1>님, 오라클 봇의 설정이에요.\n승부 예측: **켜짐** (주인이 리그 관리자 페이지에서 켜고 꺼요. 바꾸면 5분 안에 반영돼요)\n"
          "참가 포인트: **주지 않음**, 그날의 첫 내전은 **주지 않음** (결과가 기록되면 그 판에 뛴 선수가 받아요. 주인이 리그 관리자 페이지에서 바꿔요)\n"
          "'포인트 받기' 글을 올리는 채널: 정하지 않음 (정하면 그 채널에 이번 주 글을 올려요)\n승부의 신 랭킹에 오른 사람: 0명",
          "/오라클설정: 비우고 쓰면 지금 설정을 보여 준다 (켜져 있는지도)")
    i = inter(100, ADMIN)
    await mod.cmd_setup(i, SimpleNamespace(id=400))
    post = w.place(400).sent[-1]
    check(said(i) == "<@1>님이 '포인트 받기' 글을 올릴 채널을 <#400> 로 정했어요. 이번 주 글을 그 채널에 올려요." and mod.S.channel_id == 400
          and len(w.place(400).sent) == 1 and post.text.startswith("🔮 **이번 주 포인트를 받으세요**\n리그 선수는 아래 **포인트 받기**를 눌러 **1,000 포인트**를 받을 수 있어요. "
                                                                 f"한 주에 한 번, <t:{MON + WEEK}:F> 전까지 받을 수 있어요.")
          and isinstance(post.view, mod.ClaimView) and post.view.is_persistent() and labels(post.view) == ["포인트 받기", "내 포인트"]
          and mod.S.round["message_id"] == post.id and mod.S.round["channel_id"] == 400,
          "/오라클설정 채널: 그 채널에 이번 주 '포인트 받기' 글과 버튼을 올린다 (봇을 껐다 켜도 눌리는 버튼)")
    await mod.tick()
    await mod.tick()
    check(len(w.place(400).sent) == 1, "같은 주에는 글을 다시 올리지 않는다")
    w.at = MON + WEEK + 5
    await mod.tick()
    check(len(w.place(400).sent) == 2 and post.deleted and mod.S.round["start"] == MON + WEEK and mod.S.round["message_id"] == w.place(400).sent[-1].id
          and f"<t:{MON + 2 * WEEK}:F>" in w.place(400).sent[-1].text, "월요일 0시가 지나면 새 글을 올리고 앞의 글은 지운다 (글은 늘 하나)")
    i = inter(100, ADMIN)
    await mod.cmd_setup(i, SimpleNamespace(id=401))
    check(len(w.place(401).sent) == 1 and w.place(400).sent[-1].deleted and mod.S.round["channel_id"] == 401, "채널을 바꾸면 새 채널에 올리고 앞의 글은 지운다")
    w.at += WEEK
    w.place(401).broken = True
    with contextlib.redirect_stdout(io.StringIO()) as out:
        await mod.tick()
        await mod.tick()
    check(mod.S.round["start"] == MON + 2 * WEEK and not mod.S.round["message_id"] and out.getvalue().count("글을 올리지 못했습니다") == 1,
          "글을 올리지 못하면 조금 뒤에 다시 올려 본다 (10초마다 되풀이하지 않는다)")
    w.place(401).broken = False
    w.at += 601
    await mod.tick()
    check(mod.S.round["message_id"] == w.place(401).sent[-1].id and w.place(401).sent[0].deleted, "다시 올리면 지난 주의 글을 지운다")

    # 그 채널에 누를 수 있는 받기 버튼은 하나뿐이다: 앞의 글을 지우지 못하면 적어 두었다가 다시 지운다
    def buttons(cid):
        return [m for m in w.place(cid).sent if not m.deleted and isinstance(m.view, mod.ClaimView)]
    check(len(buttons(401)) == 1 and mod.S.round["stale"] == [], "채널에 '포인트 받기' 글은 하나뿐이다")
    last = w.place(401).sent[-1]
    last.stuck = True
    w.at += WEEK
    with contextlib.redirect_stdout(io.StringIO()) as out:
        await mod.tick()
        await mod.tick()
    check(len(buttons(401)) == 2 and mod.S.round["stale"] == [[401, last.id]] and last.tries == 1 and out.getvalue().count("앞의 글을 지우지 못했습니다") == 1,
          "앞의 글을 지우지 못하면 적어 둔다 (10초마다 되풀이해 지우지 않는다)")
    check(json.loads(path.read_text(encoding="utf-8"))["round"]["stale"] == [[401, last.id]], "지우지 못한 글은 파일에도 적어 둔다 (봇을 껐다 켜도 잊지 않는다)")
    last.stuck = False
    w.at += 601
    await mod.tick()
    check(last.deleted and len(buttons(401)) == 1 and mod.S.round["stale"] == [], "조금 뒤에 다시 지운다")
    # 주인이 꺼 둔 채로 여러 주가 지나도, 다시 켜면 예전 글을 잊지 않고 지운다
    first = buttons(401)[0]
    w.switch = False
    w.at += 3 * WEEK
    with contextlib.redirect_stdout(io.StringIO()):
        await mod.tick()
    await mod.tick()
    check(buttons(401) == [first] and mod.S.round["stale"] == [[401, first.id]] and not mod.S.round["message_id"], "꺼 둔 동안에는 새 글을 올리지 않고 앞의 글을 그대로 둔다")
    w.at += WEEK
    await mod.tick()
    w.switch = True
    w.at += 300
    with contextlib.redirect_stdout(io.StringIO()):
        await mod.tick()
    check(first.deleted and len(buttons(401)) == 1 and buttons(401)[0].id == mod.S.round["message_id"] and mod.S.round["stale"] == [],
          "꺼 둔 채로 여러 주가 지난 뒤에 켜도 새 글을 올리고 예전 글은 지운다 (버튼은 하나)")
    gone = buttons(401)[0]
    gone.missing = True                                             # 누가 그 글을 손으로 지웠다
    w.at += WEEK
    await mod.tick()
    check(len(buttons(401)) == 1 and buttons(401)[0] is not gone and mod.S.round["stale"] == [] and gone.tries == 1,
          "이미 지워진 글은 지운 것으로 친다 (되풀이해 지우려 하지 않는다)")

    # ── 승부 예측 열기: 퍼그나봇이 팀을 짜서 알리면 그 글 아래에 연다 ──
    w = World(mod, path, T0)
    mod.S.accounts, mod.S.books, mod.S.round, mod.S.channel_id = {}, [], None, 0
    w.players = {11, 12, 13, 14, 110, 1} | set(range(100, 110))
    for u, points in ((A, 1000), (B, 1000), (C, 1000), (D, 0), (user(105), 1000), (user(110), 1000)):
        if points:
            await mod.claim_points(inter(400, u))
    entry = lineup(1)
    await mod.on_lineup(entry)
    book = mod.S.books[0]
    end = int(T0 + 1200)
    first = w.place(300).sent[0]
    check(len(mod.S.books) == 1 and book["key"] == "300:1001500" and book["state"] == "open" and book["closes"] == T0 + 1200 and book["players"] == list(range(100, 110))
          and book["place_id"] == 300, "팀이 짜이면 승부 예측을 연다 (20분 동안. 뛰는 열 명을 적어 둔다)")
    check(first.text == "🔮 **승부 예측** — 이 경기에서 이길 팀에 포인트를 걸어 보세요.\n"
          f"⏰ **<t:{end}:t>까지** 걸 수 있어요. (<t:{end}:R> 마감) 마감하면 배당률을 알려 드려요.\n"
          "이 경기에 뛰는 선수는 걸 수 없어요. 포인트가 없으면 오라클 봇의 **포인트 받기** 글에서 이번 주 포인트를 먼저 받으세요.\n지금까지 **0명**이 걸었어요."
          and isinstance(first.view, mod.BetView) and first.view.is_persistent() and labels(first.view) == ["래디언트", "다이어", "내 베팅"]
          and [c.custom_id for c in first.view.children] == ["oracle:bet:r", "oracle:bet:d", "oracle:mine"] and book["message_id"] == first.id,
          "그 글에 승부 예측 글과 버튼(래디언트·다이어·내 베팅)을 올린다")
    mod.S.channel_id = 400                     # /오라클설정 으로 '포인트 받기' 글의 채널을 정해 두었으면 그 채널을 알려 준다
    check("이 경기에 뛰는 선수는 걸 수 없어요. 포인트가 없으면 <#400> 채널의 **포인트 받기**로 이번 주 포인트를 먼저 받으세요.\n" in mod.open_text(book)
          and "/포인트" not in mod.open_text(book), "승부 예측 글: 포인트가 없으면 '포인트 받기' 글이 있는 채널에서 받으라고 알린다")

    # 진영 버튼 → 금액 버튼
    i = inter(300, GUEST)
    await mod.pick_side(i, "r")
    check(said(i) == mod.PLAYER_ONLY, "베팅: 리그 선수가 아니면 걸 수 없다")
    i = inter(300, user(105))
    await mod.pick_side(i, "r")
    check(said(i) == "이 경기에 뛰는 선수는 걸 수 없어요." and view_of(i) is None, "베팅: 그 경기에 뛰는 선수는 걸 수 없다")
    i = inter(300, D)
    await mod.pick_side(i, "r")
    check(said(i) == "걸 수 있는 포인트가 없어요. <#400> 채널의 **포인트 받기**로 이번 주 포인트를 받았는지 확인해 보세요." and "14" not in mod.S.accounts,
          "베팅: 포인트가 없으면 걸 수 없다 (포인트를 받는 채널을 알려 준다)")
    ok, why = mod.place(book, D.id, "r", 100, D)
    check(not ok and why == said(i), "베팅: 금액을 고른 뒤에 포인트가 없어도 같은 안내를 한다")
    mod.S.channel_id = 0
    i = inter(300, D)
    await mod.pick_side(i, "r")
    check(said(i) == "걸 수 있는 포인트가 없어요. 오라클 봇의 **포인트 받기** 글에서 이번 주 포인트를 받았는지 확인해 보세요." and "14" not in mod.S.accounts,
          "베팅: 채널을 정해 두지 않았으면 '포인트 받기' 글에서 받으라고만 알린다 (/포인트 명령어는 없다)")
    i = inter(300, A)
    await mod.pick_side(i, "r")
    check(said(i) == "🟢 래디언트에 얼마를 걸까요? 걸 수 있는 포인트는 **1,000**이에요." and i.response.send_message.call_args.kwargs["ephemeral"] is True
          and labels(view_of(i)) == ["100", "300", "500", "1,000", "전부 (1,000)", "직접 입력"], "베팅: 진영을 누르면 본인에게만 금액 버튼이 보인다")
    i = inter(300, user(110))
    await mod.pick_side(i, "d")
    check(said(i).startswith("🔴 다이어에 얼마를 걸까요?"), "베팅: 그 판에서 쉬는 사람은 걸 수 있다")

    # 금액 버튼 → 건다
    key = book["key"]
    i = inter(300, A)
    await mod.put_amount(i, key, "r", 500)
    check(said(i) == f"✅ 🟢 래디언트에 **500 포인트**를 걸었어요. 남은 포인트는 500이에요.\n<t:{end}:t>(<t:{end}:R>)에 마감해요. 그때까지 바꾸거나 취소할 수 있어요."
          and labels(view_of(i)) == ["베팅 취소"] and mod.S.accounts["11"]["points"] == 500 and book["bets"]["11"] == {"side": "r", "amount": 500, "at": T0},
          "베팅: 금액을 누르면 걸리고, 건 포인트는 바로 빠진다 (취소 버튼이 보인다)")
    check(first.edits[-1]["content"].endswith("지금까지 **1명**이 걸었어요.") and isinstance(first.edits[-1]["view"], mod.BetView), "건 사람 수를 승부 예측 글에 바로 고친다")
    i = inter(300, A)
    await mod.pick_side(i, "d")
    check(said(i) == "🔴 다이어에 얼마를 걸까요? 걸 수 있는 포인트는 **1,000**이에요.\n지금은 🟢 래디언트에 500 포인트를 걸어 두었어요. 새로 고르면 그것으로 바뀌어요.",
          "베팅: 이미 걸었으면 바꿀 수 있다 (걸어 둔 포인트까지 다시 걸 수 있다)")
    i = inter(300, A)
    await mod.put_amount(i, key, "d", 1200)
    check(said(i) == "포인트가 모자라요. 걸 수 있는 포인트는 **1,000**이에요." and view_of(i) is None and book["bets"]["11"]["amount"] == 500 and mod.S.accounts["11"]["points"] == 500,
          "베팅: 가진 것보다 많이 걸 수 없다 (걸어 둔 것은 그대로)")
    i = inter(300, A)
    await mod.put_amount(i, key, "d", 0)
    check(said(i) == "1 포인트 이상 걸어 주세요.", "베팅: 0은 걸 수 없다")
    i = inter(300, A)
    await mod.put_amount(i, key, "d", 800)
    check(book["bets"]["11"]["side"] == "d" and book["bets"]["11"]["amount"] == 800 and mod.S.accounts["11"]["points"] == 200 and len(book["bets"]) == 1,
          "베팅: 다시 걸면 앞의 것이 바뀐다 (한 경기에 한 번)")
    i = inter(300, A)
    await mod.show_mine(i)
    check(said(i) == f"🔴 다이어에 **800 포인트**를 걸어 두었어요. <t:{end}:R> 마감하고, 그때까지 바꾸거나 취소할 수 있어요. 보유 포인트는 200이에요."
          and labels(view_of(i)) == ["베팅 취소"], "내 베팅: 건 것과 취소 버튼을 본인에게 보여 준다")
    i = inter(300, A)
    await mod.cancel_bet(i, key)
    check(said(i) == "건 포인트 800을 돌려받았어요. 보유 포인트는 1,000이에요." and "11" not in book["bets"] and mod.S.accounts["11"]["points"] == 1000
          and first.edits[-1]["content"].endswith("지금까지 **0명**이 걸었어요."), "베팅 취소: 건 포인트를 돌려받는다")
    i = inter(300, A)
    await mod.cancel_bet(i, key)
    check(said(i) == "이 경기에는 걸어 둔 포인트가 없어요.", "베팅 취소: 걸지 않았으면 알려 준다")
    i = inter(300, B)
    await mod.show_mine(i)
    check(said(i) == "이 경기에는 걸지 않았어요. 보유 포인트는 1,000이에요." and view_of(i) is None, "내 베팅: 걸지 않았을 때")

    # 직접 입력
    side_view = mod.AmountView(key, "r", 1000)
    i = inter(300, A)
    await side_view.children[-1].callback(i)
    modal = i.response.send_modal.call_args.args[0]
    check(isinstance(modal, mod.AmountModal) and modal.title == "걸 포인트" and modal.amount.label == "걸 포인트 (1 ~ 1,000)", "직접 입력: 숫자를 적는 창이 뜬다")
    modal.amount._value = "이백"
    i = inter(300, A)
    await modal.on_submit(i)
    check(said(i) == "걸 포인트는 숫자로 적어 주세요. 진영 버튼을 다시 눌러 주세요." and "11" not in book["bets"], "직접 입력: 숫자가 아니면 걸지 않는다")
    modal.amount._value = " 1,000 "
    i = inter(300, A)
    await modal.on_submit(i)
    check(book["bets"]["11"] == {"side": "r", "amount": 1000, "at": T0} and mod.S.accounts["11"]["points"] == 0, "직접 입력: 적은 만큼 건다 (쉼표가 있어도 된다)")
    i = inter(300, A)
    await side_view.children[0].callback(i)
    check(book["bets"]["11"]["amount"] == 100 and mod.S.accounts["11"]["points"] == 900 and said(i).startswith("✅ 🟢 래디언트에 **100 포인트**"), "금액 버튼을 누르면 그 금액으로 건다")
    check(labels(mod.AmountView(key, "r", 250)) == ["100", "전부 (250)", "직접 입력"], "가진 포인트보다 큰 금액 버튼은 보이지 않는다")

    # ── 20분 뒤 마감: 배당률과, 건 사람마다 이기면 얻고 지면 잃는 포인트 ──
    await mod.put_amount(inter(300, A), key, "r", 500)
    w.at += 60
    await mod.put_amount(inter(300, B), key, "r", 100)
    await mod.put_amount(inter(300, C), key, "d", 300)
    check(mod.board()["players"] == [{"name": "가", "points": 1000, "profit": 0, "bets": 0, "hits": 0, "claimed": 1}, {"name": "나", "points": 1000, "profit": 0, "bets": 0, "hits": 0, "claimed": 1},
                                     {"name": "다", "points": 1000, "profit": 0, "bets": 0, "hits": 0, "claimed": 1}, {"name": "선수105", "points": 1000, "profit": 0, "bets": 0, "hits": 0, "claimed": 1},
                                     {"name": "선수110", "points": 1000, "profit": 0, "bets": 0, "hits": 0, "claimed": 1}],
          "순위에는 걸어 둔 포인트도 보유 포인트로 넣는다 (경기가 끝나기 전에는 순위가 바뀌지 않는다)")
    w.at = T0 + 1199
    await mod.tick()
    check(book["state"] == "open" and len(w.place(300).sent) == 1, "20분이 되기 전에는 마감하지 않는다")
    w.at = T0 + 1200
    i = inter(300, D)
    await mod.pick_side(i, "r")
    check(said(i) == "이 경기의 승부 예측은 마감됐어요.", "20분이 지나면, 마감 글이 올라오기 전이어도 걸 수 없다")
    i = inter(300, B)
    await mod.put_amount(i, key, "d", 50)
    check(said(i) == "이 경기의 승부 예측은 마감됐어요." and book["bets"]["12"] == {"side": "r", "amount": 100, "at": T0 + 60}, "20분이 지나면 바꿀 수도 없다")
    i = inter(300, B)
    await mod.cancel_bet(i, key)
    check(said(i) == "이 경기의 승부 예측은 마감돼서 취소할 수 없어요.", "20분이 지나면 취소할 수도 없다")
    await mod.tick()
    posts = w.place(300).texts()
    check(book["state"] == "closed" and first.text == "🔮 **승부 예측** — 마감했어요. 3명이 걸었고, 배당률은 아래에 있어요." and first.view is None,
          "20분이 지나면 마감한다 (버튼을 뗀다)")
    check(len(posts) == 2 and posts[1] == "🔮 **승부 예측 마감** — 3명이 걸었어요.\n🟢 래디언트 **600** 포인트 (2명) · 배당 **1.50배**\n🔴 다이어 **300** 포인트 (1명) · 배당 **3.00배**\n"
          "-# 건 포인트를 모두 모아, 이긴 쪽이 건 만큼 나눠 가져요. 소수점 아래는 버려요.\n\n🟢 래디언트에 건 사람\n<@11> 500 → 이기면 **+250** / 지면 −500\n<@12> 100 → 이기면 **+50** / 지면 −100\n\n"
          "🔴 다이어에 건 사람\n<@13> 300 → 이기면 **+600** / 지면 −300",
          "마감하면 배당률과, 건 사람마다 이기면 얻고 지면 잃는 포인트를 알린다 (많이 건 사람이 많이 딴다)")
    i = inter(300, A)
    await mod.show_mine(i)
    check(said(i) == "🟢 래디언트에 **500 포인트**를 걸었어요. 이기면 **+250**, 지면 −500이에요. 경기 결과를 기다리고 있어요. 보유 포인트는 500이에요." and view_of(i) is None,
          "내 베팅: 마감한 뒤에는 이기면·지면 얼마인지 보여 준다 (취소 버튼은 없다)")
    await mod.tick()
    check(len(w.place(300).sent) == 2, "마감은 한 번만 한다")

    # ── 정산: /승리 로 결과가 기록되면 ──
    w.asked.clear()
    await mod.on_result(entry, "r")
    acc = mod.S.accounts
    check(book["state"] == "settled" and book["winner"] == "r" and book["paid"] == {"11": 750, "12": 150, "13": 0}
          and (acc["11"]["points"], acc["12"]["points"], acc["13"]["points"]) == (1250, 1050, 700), "정산: 이긴 쪽이 건 만큼 나눠 갖는다 (500 → 750, 100 → 150)")
    check((acc["11"]["bets"], acc["11"]["hits"], acc["11"]["profit"]) == (1, 1, 250) and (acc["13"]["bets"], acc["13"]["hits"], acc["13"]["profit"]) == (1, 0, -300),
          "정산: 맞힌 횟수와 손익을 적어 둔다")
    check(w.place(300).texts()[2] == "🔮 **승부 예측 결과** — 🟢 래디언트 승리! (배당 1.50배)\n\n🎉 **맞힌 사람**\n<@11> **+250** · 보유 1,250\n<@12> **+50** · 보유 1,050\n\n"
          "💸 **틀린 사람**\n<@13> −300 · 보유 700\n\n📊 승부의 신 랭킹: <https://example.invalid/oracle.html>", "정산: 결과와 얻고 잃은 포인트를 그 글에 알린다")
    i = inter(300, A)
    await mod.show_mine(i)
    check(said(i) == "🟢 래디언트에 **500 포인트**를 걸어 맞혔어요. **+250** 포인트를 얻었어요. 보유 포인트는 1,250이에요.", "내 베팅: 정산한 뒤")
    i = inter(300, C)
    await mod.show_mine(i)
    check(said(i) == "🔴 다이어에 **300 포인트**를 걸어 틀렸어요. 300 포인트를 잃었어요. 보유 포인트는 700이에요.", "내 베팅: 틀렸을 때")
    await mod.on_result(entry, "d")
    check(book["winner"] == "r" and acc["11"]["points"] == 1250 and len(w.place(300).sent) == 3, "이미 정산한 판은 다시 정산하지 않는다")

    # ── 순위를 리그 서버에 올리기 (순위 페이지가 읽는다) ──
    w.nicks = {11: "가나다"}
    w.at += 30
    await mod.tick()
    sent = w.asked[-1]
    check(len(w.asked) == 1 and sent["action"] == "saveOracle" and sent["board"]["weekly"] == 1000 and sent["board"]["updatedAt"].endswith("Z")
          and sent["board"]["players"][:3] == [{"name": "가나다", "points": 1250, "profit": 250, "bets": 1, "hits": 1, "claimed": 1},
                                               {"name": "나", "points": 1050, "profit": 50, "bets": 1, "hits": 1, "claimed": 1},
                                               {"name": "선수105", "points": 1000, "profit": 0, "bets": 0, "hits": 0, "claimed": 1}]
          and sent["board"]["players"][-1] == {"name": "다", "points": 700, "profit": -300, "bets": 1, "hits": 0, "claimed": 1}
          and all(set(row) == {"name", "points", "profit", "bets", "hits", "claimed"} for row in sent["board"]["players"]) and set(sent["board"]) == {"updatedAt", "weekly", "play", "first", "players"}
          and not mod.S.dirty,
          "정산한 뒤 포인트 순위를 리그 서버에 올린다 (보유 포인트 순. 이름은 리그 닉네임이고 모르면 서버 별명. 디스코드 ID는 싣지 않는다)")
    check(sent["state"]["accounts"]["11"]["points"] == 1250 and sent["state"]["books"][0]["state"] == "settled", "포인트 기록의 사본도 함께 올린다 (이 PC의 파일을 잃어도 되살릴 수 있게)")
    await mod.tick()
    check(len(w.asked) == 1, "바뀐 것이 없으면 다시 올리지 않는다")

    # ── 승리취소: 정산을 되돌린다. 그사이 딴 포인트를 써 버렸으면 0보다 적어질 수 있다 ──
    entry2 = lineup(2, place=301)
    await mod.on_lineup(entry2)
    book2 = mod.S.books[1]
    await mod.put_amount(inter(301, A), book2["key"], "r", 1250)     # 가: 딴 포인트까지 모두 건다
    await mod.put_amount(inter(301, C), book2["key"], "d", 100)
    w.at += 1200
    await mod.tick()
    await mod.on_result(entry2, "d")
    check(acc["11"]["points"] == 0 and acc["13"]["points"] == 600 + 1350 and book2["paid"] == {"11": 0, "13": 1350}, "둘째 판: 가는 모두 잃고 다는 모두 가져갔다")
    await mod.on_undo(entry)
    check(book["state"] == "closed" and book["winner"] is None and book["paid"] == {} and (acc["11"]["points"], acc["12"]["points"], acc["13"]["points"]) == (-750, 900, 1950)
          and (acc["11"]["bets"], acc["11"]["hits"], acc["11"]["profit"]) == (1, 0, -1250) and (acc["12"]["bets"], acc["12"]["hits"], acc["12"]["profit"]) == (0, 0, 0)
          and (acc["13"]["bets"], acc["13"]["hits"], acc["13"]["profit"]) == (1, 1, 1250),
          "승리취소: 나눠 준 포인트를 도로 가져온다. 이미 다른 판에 써 버렸으면 0보다 적어진다 (허용)")
    check(w.place(300).texts()[-1] == "🔮 경기 결과가 취소돼서 승부 예측의 정산을 되돌렸어요. 결과가 다시 기록되면 그때 다시 정산해요.\n포인트가 0보다 적어진 사람: <@11> (−750)",
          "승리취소: 되돌렸다고 알리고, 0보다 적어진 사람을 적는다")
    i = inter(301, A)
    await mod.pick_side(i, "r")
    check(said(i) == "이 경기의 승부 예측은 마감됐어요.", "마감한 판에는 걸 수 없다")
    await mod.on_undo(entry)
    check(len(w.place(300).sent) == 4 and acc["11"]["points"] == -750, "되돌린 판은 다시 되돌리지 않는다")
    await mod.on_result(entry, "d")
    check(book["state"] == "settled" and book["winner"] == "d" and book["paid"] == {"11": 0, "12": 0, "13": 900}
          and (acc["11"]["points"], acc["12"]["points"], acc["13"]["points"]) == (-750, 900, 2850)
          and (acc["11"]["profit"], acc["12"]["profit"], acc["13"]["profit"]) == (-1750, -100, 1850) and acc["13"]["hits"] == 2,
          "다시 /승리 하면(이번에는 다이어) 다시 정산한다")
    check("🔴 다이어 승리! (배당 3.00배)" in w.place(300).texts()[-1] and "<@13> **+600** · 보유 2,850" in w.place(300).texts()[-1]
          and "<@11> −500 · 보유 −750" in w.place(300).texts()[-1], "다시 정산한 결과를 알린다")
    third = lineup(3, place=302)
    await mod.on_lineup(third)
    i = inter(302, A)
    await mod.pick_side(i, "r")
    check(said(i).startswith("걸 수 있는 포인트가 없어요."), "포인트가 0보다 적으면 걸 수 없다 (다음 주 포인트를 받으면 그만큼 메워진다)")
    w.at = MON + WEEK + 10
    await mod.claim_points(inter(400, A))
    check(acc["11"]["points"] == 250, "0보다 적은 포인트는 다음 주에 받는 1000으로 메워진다")
    w.at = T0 + 3000

    # ── 한쪽에만 걸렸거나 아무도 걸지 않았을 때 ──
    book3 = mod.S.books[2]
    await mod.put_amount(inter(302, B), book3["key"], "r", 200)
    await mod.put_amount(inter(302, C), book3["key"], "r", 50)
    w.at = book3["closes"]
    await mod.tick()
    check(book3["state"] == "void" and acc["12"]["points"] == 900 and acc["13"]["points"] == 2850
          and w.place(302).sent[0].text == "🔮 **승부 예측** — 마감했어요. 한쪽 팀에만 걸려서 성립하지 않았어요."
          and w.place(302).texts()[1] == "🔮 승부 예측을 마감했어요. 🟢 래디언트에만 걸려서(2명, 250 포인트) 성립하지 않았어요. 건 포인트는 모두 돌려드렸어요.",
          "한쪽 팀에만 걸렸으면 성립하지 않고, 건 포인트를 모두 돌려준다")
    i = inter(302, B)
    await mod.show_mine(i)
    check(said(i) == "이 경기의 승부 예측은 성립하지 않아서, 건 포인트 200을 돌려받았어요. 보유 포인트는 900이에요.", "내 베팅: 성립하지 않았을 때")
    await mod.on_result(third, "r")
    check(book3["state"] == "void" and len(w.place(302).sent) == 2 and acc["12"]["points"] == 900, "성립하지 않은 판은 결과가 나와도 정산하지 않는다")
    fourth = lineup(4, place=303)
    await mod.on_lineup(fourth)
    book4 = mod.S.books[3]
    w.at = book4["closes"] + 1
    await mod.tick()
    check(book4["state"] == "void" and len(w.place(303).sent) == 1 and w.place(303).sent[0].text == "🔮 **승부 예측** — 마감했어요. 건 사람이 없었어요."
          and w.place(303).sent[0].view is None, "아무도 걸지 않았으면 글만 고치고 따로 알리지 않는다")

    # ── 20분이 되기 전에 결과가 나오면 마감부터 한다 ──
    fifth = lineup(5, place=304)
    await mod.on_lineup(fifth)
    book5 = mod.S.books[4]
    await mod.put_amount(inter(304, B), book5["key"], "r", 300)
    await mod.put_amount(inter(304, C), book5["key"], "d", 900)
    await mod.on_result(fifth, "r")
    t5 = w.place(304).texts()
    check(book5["state"] == "settled" and len(t5) == 3 and t5[0].startswith("🔮 **승부 예측** — 마감했어요. 2명이 걸었고") and t5[1].startswith("🔮 **승부 예측 마감**")
          and t5[2].startswith("🔮 **승부 예측 결과** — 🟢 래디언트 승리! (배당 4.00배)") and acc["12"]["points"] == 900 - 300 + 1200,
          "20분이 되기 전에 결과가 기록되면 마감하고 바로 정산한다")

    # ── 경기가 없던 일이 되면 건 포인트를 돌려준다 ──
    sixth = lineup(6, place=305)
    await mod.on_lineup(sixth)
    book6 = mod.S.books[5]
    before = acc["12"]["points"], acc["13"]["points"]
    await mod.put_amount(inter(305, B), book6["key"], "r", 300)
    await mod.put_amount(inter(305, C), book6["key"], "d", 400)
    await mod.on_void(sixth)
    check(book6["state"] == "void" and (acc["12"]["points"], acc["13"]["points"]) == before
          and w.place(305).sent[0].text == "🔮 **승부 예측** — 이 경기가 없던 일이 돼서 취소했어요." and w.place(305).sent[0].view is None
          and w.place(305).texts()[1] == "🔮 이 경기가 없던 일이 돼서 승부 예측을 취소했어요. 건 포인트는 모두 돌려드렸어요.",
          "받는 중에 경기가 없던 일이 되면(/취소·/재모집·다시 열기·경기 안 함) 건 포인트를 돌려준다")
    await mod.on_void(sixth)
    check(len(w.place(305).sent) == 2 and (acc["12"]["points"], acc["13"]["points"]) == before, "돌려준 판은 다시 돌려주지 않는다")
    seventh = lineup(7, place=306)
    await mod.on_lineup(seventh)
    book7 = mod.S.books[6]
    await mod.put_amount(inter(306, B), book7["key"], "r", 300)
    await mod.put_amount(inter(306, C), book7["key"], "d", 400)
    w.at = book7["closes"]
    await mod.tick()
    await mod.on_void(seventh)
    check(book7["state"] == "void" and (acc["12"]["points"], acc["13"]["points"]) == before and len(w.place(306).sent) == 3
          and w.place(306).texts()[-1].startswith("🔮 이 경기가 없던 일이 돼서 승부 예측을 취소했어요."), "마감한 뒤에 없던 일이 돼도 돌려준다")
    eighth = lineup(8, place=307)
    await mod.on_lineup(eighth)
    book8 = mod.S.books[7]
    await mod.on_void(eighth)
    check(book8["state"] == "void" and len(w.place(307).sent) == 1 and w.place(307).sent[0].text.endswith("취소했어요."), "건 사람이 없던 판은 글만 고친다")
    await mod.on_void(lineup(99))
    await mod.on_result(lineup(99), "r")
    await mod.on_undo(lineup(99))
    check(len(mod.S.books) == 8, "승부 예측이 없는 편성은 그냥 넘어간다 (오라클을 켜기 전에 짠 팀)")

    # ── 봇을 껐다 켜기: 꺼져 있던 사이에 20분이 지났으면 켜자마자 마감한다 ──
    ninth = lineup(9, place=308)
    await mod.on_lineup(ninth)
    book9 = mod.S.books[8]
    await mod.put_amount(inter(308, B), book9["key"], "r", 100)
    await mod.put_amount(inter(308, C), book9["key"], "d", 100)
    closes, saved_points = book9["closes"], (acc["12"]["points"], acc["13"]["points"])
    old_places = w.places
    w = World(mod, path, closes - 300)                                  # 15분쯤에 다시 켰다
    w.places, w.players, w.count = old_places, {11, 12, 13, 14}, 9000
    for p in w.places.values():
        p.world = w
        w.messages.update({m.id: m for m in p.sent})
    book9 = mod.find_book(book9["key"])
    check(mod.S.loaded and book9 is not None and book9["state"] == "open" and book9["bets"]["12"] == {"side": "r", "amount": 100, "at": closes - 1200}
          and (mod.S.accounts["12"]["points"], mod.S.accounts["13"]["points"]) == saved_points and len(mod.S.books) == 9,
          "봇을 껐다 켜도 받던 승부 예측과 건 포인트가 남는다")
    await mod.tick()
    i = inter(308, A)
    await mod.put_amount(i, book9["key"], "r", 50)
    check(book9["state"] == "open" and said(i).startswith("✅ 🟢 래디언트에 **50 포인트**"), "20분이 지나지 않았으면 켠 뒤에도 이어서 걸 수 있다")
    w = World(mod, path, closes + 3600)                                 # 한 시간 뒤에 다시 켰다
    w.places, w.count = old_places, 9500
    for p in w.places.values():
        p.world = w
        w.messages.update({m.id: m for m in p.sent})
    book9 = mod.find_book(book9["key"])
    await mod.tick()
    check(book9["state"] == "closed" and w.place(308).texts()[-1].startswith("🔮 **승부 예측 마감** — 3명이 걸었어요.") and w.place(308).sent[0].view is None,
          "꺼져 있던 사이에 20분이 지났으면 켜자마자 마감한다")
    # 오라클 봇이 로그인하기 전에 짜인 팀: 로그인한 뒤에 글을 올린다
    mod.S.ready = False
    tenth = lineup(10, place=309)
    await mod.on_lineup(tenth)
    book10 = mod.S.books[-1]
    check(book10["state"] == "open" and book10["message_id"] == 0 and 309 not in w.places, "오라클 봇이 아직 로그인하지 않았으면 판만 열어 둔다")
    mod.S.ready = True
    await mod.tick()
    check(book10["message_id"] == w.place(309).sent[0].id and isinstance(w.place(309).sent[0].view, mod.BetView), "로그인한 뒤에 승부 예측 글을 올린다")

    # ── 결과가 기록되지 않은 채 이틀이 지나면 돌려준다. 끝난 판은 한 주 뒤에 잊는다 ──
    held = mod.S.accounts["12"]["points"]
    w.at = book9["opened"] + 2 * 86400 + 1
    await mod.tick()
    check(book9["state"] == "void" and mod.S.accounts["12"]["points"] == held + 100
          and w.place(308).texts()[-1] == "🔮 결과가 기록되지 않은 채 이틀이 지나서 승부 예측을 취소했어요. 건 포인트는 모두 돌려드렸어요.",
          "결과가 기록되지 않은 채 이틀이 지나면(퍼그나봇이 그 팀을 잊으면) 건 포인트를 돌려준다")
    n = len(mod.S.books)
    w.at += 7 * 86400 + 1
    await mod.tick()
    check(n == 10 and mod.S.books == [], "끝난 판은 한 주 뒤에 잊는다 (포인트와 전적은 그대로)")
    check(mod.S.accounts["13"]["hits"] == 2 and mod.S.accounts["12"]["points"] == held + 100, "판을 잊어도 포인트와 전적은 남는다")

    # ── 리그 서버에 올리지 못할 때, 서버 설정이 없을 때, 이 PC에 기록이 없을 때 ──
    w.fail = True
    mod.S.dirty = True
    w.asked.clear()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        await mod.tick()
        await mod.tick()
    check(len(w.asked) == 1 and mod.S.dirty and out.getvalue().count("포인트 순위를 리그 서버에 올리지 못했습니다") == 1,
          "순위를 서버에 올리지 못하면 10분 뒤에 다시 올린다 (10초마다 되풀이하지 않는다)")
    w.fail = False
    w.at += 601
    await mod.tick()
    check(len(w.asked) == 2 and not mod.S.dirty, "10분 뒤에 다시 올린다")
    saved = json.loads(path.read_text(encoding="utf-8"))
    path.unlink()
    w = World(mod, path, T0, server=False)
    mod.S.dirty = True
    await mod.restore()
    await mod.tick()
    check(not mod.S.accounts and mod.S.dirty, "리그 서버 설정이 없으면 순위를 올리지 않고, 사본도 받지 않는다")
    path.unlink(missing_ok=True)
    w = World(mod, path, T0)
    w.backup = saved
    check(not mod.S.loaded and not mod.S.accounts, "이 PC에 포인트 기록이 없다")
    with contextlib.redirect_stdout(io.StringIO()) as out:
        await mod.restore()
    check(mod.S.accounts["13"]["hits"] == 2 and mod.S.accounts["11"]["claimed"] == 2 and path.exists() and "리그 서버의 사본을 받아 왔습니다. (5명)" in out.getvalue(),
          "이 PC에 포인트 기록이 없으면 리그 서버에 올려 둔 사본을 받아 온다 (파일을 잃었거나 봇을 다른 PC로 옮겼을 때)")
    w.backup = {"accounts": {"1": {"points": 5}}}
    await mod.restore()
    check("1" not in mod.S.accounts, "사본은 켤 때 한 번만 받아 온다")
    mod.save()
    w = World(mod, path, T0)                                         # 기록이 있는 채로 다시 켰다. 바뀐 것은 없다
    w.asked.clear()
    mod.S.dirty = False
    await mod.boot()
    await mod.tick()
    sent = [x for x in w.asked if x["action"] == "saveOracle"]
    check(len(sent) == 1 and len(sent[0]["ledger"]) == 5 and len(sent[0]["board"]["players"]) == 5 and not mod.S.dirty,
          "켤 때 한 번은 바뀐 것이 없어도 순위와 시트에 적을 기록을 올린다 (서버를 새 버전으로 올린 뒤 시트를 채우려고)")
    w.at += 60
    await mod.tick()
    check(len([x for x in w.asked if x["action"] == "saveOracle"]) == 1, "그 뒤로는 바뀐 것이 있을 때만 올린다")

    # ── 켜고 끄기: 주인이 리그 관리자 페이지에서 켜고 끈다. 봇은 리그 서버에 5분마다 물어본다 ──
    path.unlink(missing_ok=True)
    w = World(mod, path, T0)
    w.players = {11, 12, 13}
    mod.S.on = False                                           # 처음에는 꺼져 있다 (리그 서버에 물어보기 전)
    check(mod.status_line() == "켜는 중 (로그인하면 아래에 따로 알립니다)", "토큰이 있으면 오라클 봇은 로그인한다 (승부 예측을 받는지는 주인이 켜 두었는지에 달렸다)")
    w.switch = False
    await mod.tick()
    check(w.polls == 1 and not mod.S.on, "켤 때 리그 서버에 주인이 켜 두었는지 물어본다. 꺼 두었으면 꺼진 채로 있다")
    i = inter(100, ADMIN)
    await mod.cmd_setup(i, SimpleNamespace(id=400))
    check(said(i) == "<@1>님이 '포인트 받기' 글을 올릴 채널을 <#400> 로 정했어요. 오라클 봇이 켜지면 그 채널에 올려요." and 400 not in w.places,
          "꺼져 있는 동안: '포인트 받기' 글을 올리지 않는다")
    i = inter(400, A)
    await mod.claim_points(i)
    check(said(i) == mod.RESTING == "지금은 오라클 봇이 쉬고 있어요. 다시 켜지면 포인트를 받고 걸 수 있어요." and "11" not in mod.S.accounts, "꺼져 있는 동안: 포인트를 받을 수 없다")
    i = inter(400, A)
    await mod.show_points(i)
    check(said(i) == mod.RESTING and view_of(i) is None, "꺼져 있는 동안: 내 포인트도 쉬고 있다고 알린다")
    await mod.on_lineup(lineup(1))
    check(mod.S.books == [] and 300 not in w.places, "꺼져 있는 동안: 팀이 짜여도 승부 예측을 열지 않는다")
    await mod.tick()
    check(w.polls == 1, "5분이 되기 전에는 다시 묻지 않는다")
    w.switch = True
    w.at += 300
    with contextlib.redirect_stdout(io.StringIO()) as out:
        await mod.tick()
    check(w.polls == 2 and mod.S.on and "리그 관리자 페이지에서 켰습니다" in out.getvalue() and len(w.place(400).sent) == 1
          and json.loads(path.read_text(encoding="utf-8"))["on"] is True, "주인이 켜면 5분 안에 알아채고, 그때 이번 주 '포인트 받기' 글을 올린다")
    await mod.claim_points(inter(400, A))
    await mod.claim_points(inter(400, B))
    await mod.claim_points(inter(400, C))
    game = lineup(1)
    await mod.on_lineup(game)
    held = mod.S.books[0]
    await mod.put_amount(inter(300, A), held["key"], "r", 400)
    await mod.put_amount(inter(300, B), held["key"], "d", 100)
    check(held["state"] == "open" and len(held["bets"]) == 2, "켜져 있으면 승부 예측을 연다")
    # 받는 중에 주인이 껐다: 새로 걸 수는 없지만 받던 판은 끝까지 처리한다
    w.switch = False
    i = inter(100, ADMIN)
    with contextlib.redirect_stdout(io.StringIO()) as out:
        await mod.cmd_setup(i, None)
    check(not mod.S.on and "승부 예측: **꺼짐**" in said(i) and "리그 관리자 페이지에서 껐습니다" in out.getvalue() and w.polls == 3,
          "/오라클설정 을 비우고 쓰면 그 자리에서 다시 물어본다 (방금 끈 것이 바로 반영된다)")
    i = inter(300, C)
    await mod.pick_side(i, "r")
    check(said(i) == mod.RESTING and view_of(i) is None, "꺼져 있는 동안: 진영 버튼을 눌러도 걸 수 없다")
    i = inter(300, C)
    await mod.put_amount(i, held["key"], "r", 100)
    check(said(i) == mod.RESTING and "13" not in held["bets"] and mod.S.accounts["13"]["points"] == 1000, "꺼져 있는 동안: 금액 버튼을 눌러도 걸리지 않는다")
    i = inter(400, A)
    await mod.show_points(i)
    check(said(i) == "🔮 보유 포인트는 **600**이에요. 걸어 둔 포인트 400은 뺀 값이에요.\n승부 예측 0번 가운데 0번 맞혔고, 손익은 0 포인트예요.\n" + mod.RESTING
          + "\n승부의 신 랭킹: <https://example.invalid/oracle.html>" and view_of(i) is None, "꺼져 있는 동안: 내 포인트는 볼 수 있다")
    w.at = held["closes"]
    await mod.tick()
    check(held["state"] == "closed" and w.place(300).texts()[-1].startswith("🔮 **승부 예측 마감** — 2명이 걸었어요."), "꺼진 뒤에도 받던 판은 20분에 마감한다")
    await mod.on_result(game, "d")
    check(held["state"] == "settled" and mod.S.accounts["12"]["points"] == 1400 and mod.S.accounts["11"]["points"] == 600
          and w.place(300).texts()[-1].startswith("🔮 **승부 예측 결과** — 🔴 다이어 승리!"), "꺼진 뒤에도 받던 판은 결과가 나오면 정산한다")
    await mod.on_lineup(lineup(2, place=301))
    check(len(mod.S.books) == 1, "꺼진 뒤에 짜인 팀에는 승부 예측을 열지 않는다")
    w.at = MON + WEEK + 5
    n = len(w.place(400).sent)
    await mod.tick()
    check(len(w.place(400).sent) == n and mod.S.round["start"] == MON + WEEK, "꺼져 있는 동안에는 새 주가 돼도 '포인트 받기' 글을 올리지 않는다")
    # 퍼그나봇이 팀을 짜기 직전에 받는 리그 기록에도 그 값이 실려 온다
    with contextlib.redirect_stdout(io.StringIO()):
        mod.hear(True)
    check(mod.S.on and mod.S.asked == w.at, "리그 기록에 실려 온 값으로도 켜진다 (그 판부터 승부 예측을 연다)")
    mod.hear(None)
    mod.hear("true")
    check(mod.S.on, "그 값을 주지 않는 답은 건드리지 않는다")
    # 서버가 답하지 않을 때와, 그 값을 모르는 예전 서버
    w.deaf, w.switch = True, False
    w.at += 300
    with contextlib.redirect_stdout(io.StringIO()) as out:
        await mod.tick()
        w.at += 300
        await mod.tick()
    check(mod.S.on and out.getvalue().count("켜 두었는지 확인하지 못했습니다") == 1, "리그 서버가 답하지 않으면 알고 있던 대로 둔다 (같은 안내를 되풀이하지 않는다)")
    w.deaf, w.switch = False, None
    w.at += 300
    with contextlib.redirect_stdout(io.StringIO()) as out:
        await mod.tick()
    check(mod.S.on and "서버 버전 18부터" in out.getvalue(), "그 값을 모르는 예전 서버의 답으로는 바꾸지 않는다")
    old = World(mod, path, T0)                                 # 봇을 껐다 켠 것처럼: 마지막으로 알던 값을 파일에서 읽는다
    check(json.loads(path.read_text(encoding="utf-8"))["on"] is True, "켜져 있는지를 파일에 적어 둔다")
    mod.S = mod.State()
    mod.setup(token="x", path=path, host=old.mod.S.host if False else SimpleNamespace(guild=discord.Object(id=1), admin_channel_id=100, signup_channel_id=200,
                                                                                    can_play=None, is_manager=None, nickname=lambda uid, username: None, server=None))
    check(mod.S.on is True, "봇을 껐다 켜면 마지막으로 알던 값에서 시작한다 (곧 리그 서버에 다시 물어본다)")
    path.unlink()
    mod.S = mod.State()
    mod.setup(token="x", path=path, host=None)
    check(mod.S.on is False, "기록이 없는 처음에는 꺼진 것으로 시작한다 (리그 서버가 켜 두었다고 알려 줄 때까지)")

    # ── 참가 포인트: 결과가 기록되면 그 판에 뛴 선수 열 명이 승패와 상관없이 받는다 (처음에는 한 판에 100. 주인이 리그 관리자 페이지에서 바꾼다) ──
    path.unlink(missing_ok=True)
    check(mod.State().play == 100 == mod.PLAY_POINTS, "참가 포인트: 처음에는 한 판에 100이다")
    w = World(mod, path, T0)
    mod.S.play = mod.S.first_play = 100   # 그날의 첫 내전도 같은 값으로 두고 본다 (첫 내전에 더 주는 것은 따로 본다)
    w.players = {11, 12, 13} | set(range(100, 112))
    for u in (A, B, C, user(105)):
        await mod.claim_points(inter(400, u))
    acc = mod.S.accounts
    game = lineup(1)
    await mod.on_lineup(game)
    pb = mod.S.books[0]
    end = int(pb["closes"])
    check(w.place(300).sent[0].text == "🔮 **승부 예측** — 이 경기에서 이길 팀에 포인트를 걸어 보세요.\n"
          f"⏰ **<t:{end}:t>까지** 걸 수 있어요. (<t:{end}:R> 마감) 마감하면 배당률을 알려 드려요.\n"
          "이 경기에 뛰는 선수는 걸 수 없어요. 대신 결과가 기록되면 참가 포인트로 **100 포인트**를 받아요.\n"
          "포인트가 없으면 오라클 봇의 **포인트 받기** 글에서 이번 주 포인트를 먼저 받으세요.\n지금까지 **0명**이 걸었어요.",
          "참가 포인트: 승부 예측 글에서, 걸 수 없는 선수에게 참가 포인트를 받는다고 알려 준다")
    i = inter(300, user(105))
    await mod.pick_side(i, "r")
    check(said(i) == "이 경기에 뛰는 선수는 걸 수 없어요. 대신 결과가 기록되면 참가 포인트로 **100 포인트**를 받아요.", "참가 포인트: 걸려고 한 선수에게도 알려 준다")
    await mod.put_amount(inter(300, A), pb["key"], "r", 500)
    await mod.put_amount(inter(300, B), pb["key"], "d", 500)
    w.at = pb["closes"]
    await mod.tick()
    check(acc["105"]["points"] == 1000 and "100" not in acc and pb["play"] == {}, "참가 포인트: 결과가 기록되기 전에는 주지 않는다")
    await mod.on_result(game, "r")
    check(pb["state"] == "settled" and pb["play"] == {str(uid): 100 for uid in range(100, 110)} and acc["105"]["points"] == 1100
          and (acc["100"]["points"], acc["100"]["claimed"], acc["100"]["played"], acc["100"]["earned"]) == (100, 0, 1, 100)
          and "110" not in acc and "111" not in acc and (acc["11"]["points"], acc["11"]["played"], acc["12"]["points"]) == (1500, 0, 500),
          "참가 포인트: 그 판에 뛴 열 명이 승패와 상관없이 받는다 (포인트 받기를 누른 적이 없는 선수에게도 쌓인다. 쉬는 사람과 건 사람은 받지 않는다)")
    check(w.place(300).texts()[-1] == "🔮 **승부 예측 결과** — 🟢 래디언트 승리! (배당 2.00배)\n\n🎉 **맞힌 사람**\n<@11> **+500** · 보유 1,500\n\n💸 **틀린 사람**\n<@12> −500 · 보유 500\n\n"
          "🎮 **참가 포인트** — 이 경기에 뛴 선수 10명이 **100 포인트**씩 받았어요.\n\n📊 승부의 신 랭킹: <https://example.invalid/oracle.html>",
          "참가 포인트: 정산 글에 한 줄로 알린다")
    rows = mod.board()
    check(rows["play"] == 100 and [(r["name"], r["points"]) for r in rows["players"]] == [("가", 1500), ("선수105", 1100), ("다", 1000), ("나", 500)]
          and all(set(r) == {"name", "points", "profit", "bets", "hits", "claimed"} for r in rows["players"]),
          "참가 포인트: 순위에는 포인트를 받았거나 건 적이 있는 사람만 나온다 (한 판에 얼마인지만 싣고, 누가 참가 포인트로 얼마를 받았는지는 싣지 않는다)")
    i = inter(400, user(100))
    await mod.show_points(i)
    check(said(i) == "🔮 보유 포인트는 **100**이에요.\n승부 예측 0번 가운데 0번 맞혔고, 손익은 0 포인트예요.\n"
          "이번 주 포인트를 아직 받지 않았어요. **포인트 받기**를 눌러 받으세요.\n승부의 신 랭킹에는 **포인트 받기**를 누르거나 승부 예측에 한 번이라도 걸면 이름이 올라가요.\n"
          "승부의 신 랭킹: <https://example.invalid/oracle.html>" and view_of(i) is None,
          "참가 포인트: 포인트 받기를 누른 적이 없는 선수도 내 포인트를 볼 수 있다 (랭킹에 어떻게 오르는지 알린다)")
    await mod.claim_points(inter(400, user(100)))
    check(acc["100"]["points"] == 1100 and any(r["name"] == "선수100" and r["points"] == 1100 for r in mod.board()["players"]),
          "참가 포인트: 포인트 받기를 누르면 그때부터 랭킹에 나온다 (쌓인 참가 포인트와 함께)")
    other = lineup(2, place=301)
    other["who"] = {f"p{k}": 200 + k for k in range(12)}             # 다른 열 명이 뛰는 판
    await mod.on_lineup(other)
    ob = mod.S.books[1]
    i = inter(301, user(101))
    await mod.put_amount(i, ob["key"], "r", 100)
    check(said(i).startswith("✅ 🟢 래디언트에 **100 포인트**") and acc["101"]["points"] == 0, "참가 포인트: 받은 포인트로 다른 경기에 걸 수 있다")

    # /승리취소 면 거둔다. 다시 기록하면 다시 준다
    await mod.on_undo(game)
    check(pb["state"] == "closed" and pb["play"] == {} and pb["winner"] is None and acc["105"]["points"] == 1000
          and (acc["100"]["points"], acc["100"]["played"], acc["100"]["earned"]) == (1000, 0, 0) and (acc["101"]["points"], acc["101"]["played"]) == (-100, 0)
          and (acc["11"]["points"], acc["12"]["points"]) == (500, 500),
          "참가 포인트: /승리취소 면 거둔다 (이미 다른 판에 걸었으면 0보다 적어진다. 건 포인트의 정산도 함께 되돌린다)")
    check(w.place(300).texts()[-1] == "🔮 경기 결과가 취소돼서 승부 예측의 정산을 되돌리고 참가 포인트를 거뒀어요. 결과가 다시 기록되면 그때 다시 정산하고 다시 드려요.\n"
          "포인트가 0보다 적어진 사람: <@101> (−100)", "참가 포인트: 거뒀다고 알리고, 0보다 적어진 사람을 적는다")
    with contextlib.redirect_stdout(io.StringIO()) as out:
        mod.hear(None, 50, None, 50)
    check(mod.S.play == 50 == mod.S.first_play and mod.S.on and "참가 포인트를 한 판에 50 포인트로 정했습니다" in out.getvalue()
          and "그날의 첫 내전의 참가 포인트를 50 포인트로 정했습니다" in out.getvalue()
          and json.loads(path.read_text(encoding="utf-8"))["play"] == 50 == json.loads(path.read_text(encoding="utf-8"))["first_play"],
          "참가 포인트: 리그 서버가 알려 준 값으로 바뀐다 (그날의 첫 내전의 값도. 파일에 적어 둔다. 켜 두었는지는 건드리지 않는다)")
    for bad in (-1, 10001, 1.5, "100", True, None, float("nan")):
        mod.hear(None, bad, None, bad)
    check(mod.S.play == 50 == mod.S.first_play, "참가 포인트: 쓸 수 없는 값은 받지 않는다")
    await mod.on_result(game, "d")
    n = len(w.place(300).sent)
    check(pb["state"] == "settled" and pb["play"] == {str(uid): 50 for uid in range(100, 110)} and (acc["101"]["points"], acc["101"]["played"], acc["101"]["earned"]) == (-50, 1, 50)
          and "뛴 선수 10명이 **50 포인트**씩 받았어요." in w.place(300).texts()[-1], "참가 포인트: 다시 기록하면 그때의 값으로 다시 준다")
    await mod.on_result(game, "d")
    check(acc["101"]["points"] == -50 and len(w.place(300).sent) == n, "참가 포인트: 같은 결과에 두 번 주지 않는다")
    w.play = 120
    w.at += 300
    with contextlib.redirect_stdout(io.StringIO()):
        await mod.tick()
    check(mod.S.play == 120, "참가 포인트: 켜 두었는지를 5분마다 물어볼 때 함께 받는다")

    # 건 사람이 없어 정산할 것이 없는 판에도 준다
    quiet = lineup(3, place=302)
    await mod.on_lineup(quiet)
    qb = mod.S.books[2]
    await mod.on_result(quiet, "r")                                  # 20분이 되기 전에 결과가 나왔다: 마감하고(건 사람 없음) 참가 포인트만 준다
    check(qb["state"] == "void" and qb["winner"] == "r" and qb["play"] == {str(uid): 120 for uid in range(100, 110)} and acc["105"]["points"] == 1170
          and w.place(302).texts() == ["🔮 **승부 예측** — 마감했어요. 건 사람이 없었어요.",
                                       "🎮 **참가 포인트** — 이 경기에 뛴 선수 10명이 **120 포인트**씩 받았어요.\n\n📊 승부의 신 랭킹: <https://example.invalid/oracle.html>"],
          "참가 포인트: 건 사람이 없어 정산할 것이 없는 판에도 준다 (참가 포인트만 알린다)")
    await mod.on_result(quiet, "d")
    check(acc["105"]["points"] == 1170 and len(w.place(302).sent) == 2, "참가 포인트: 건 사람이 없던 판에도 두 번 주지 않는다")
    await mod.on_undo(quiet)
    check(qb["play"] == {} and qb["winner"] is None and acc["105"]["points"] == 1050
          and w.place(302).texts()[-1] == "🔮 경기 결과가 취소돼서 참가 포인트를 거뒀어요. 결과가 다시 기록되면 그때 다시 드려요.\n포인트가 0보다 적어진 사람: <@101> (−50)",
          "참가 포인트: 건 사람이 없던 판도 /승리취소 면 거둔다")
    await mod.on_undo(quiet)
    check(len(w.place(302).sent) == 3 and acc["105"]["points"] == 1050, "참가 포인트: 거둔 판에서 다시 거두지 않는다")
    await mod.on_result(quiet, "r")
    await mod.on_void(quiet)
    check(qb["off"] is True and qb["play"] == {} and acc["105"]["points"] == 1050 and w.place(302).texts()[-1] == "🔮 이 경기가 없던 일이 돼서 참가 포인트를 거뒀어요.",
          "참가 포인트: 결과를 기록한 판이 없던 일이 되면 거둔다")
    await mod.on_result(quiet, "r")
    check(qb["play"] == {} and acc["105"]["points"] == 1050, "참가 포인트: 없던 일이 된 판에는 주지 않는다")

    # 0이면 주지 않는다
    with contextlib.redirect_stdout(io.StringIO()) as out:
        mod.hear(None, 0)
    zero = lineup(4, place=303)
    await mod.on_lineup(zero)
    zb = mod.S.books[-1]
    check("참가 포인트를 주지 않기로 했습니다" in out.getvalue() and "참가 포인트" not in w.place(303).sent[0].text
          and "이 경기에 뛰는 선수는 걸 수 없어요. 포인트가 없으면" in w.place(303).sent[0].text, "참가 포인트: 0이면 승부 예측 글에서도 말하지 않는다")
    await mod.on_result(zero, "r")
    check(zb["play"] == {} and zb["winner"] == "r" and acc["105"]["points"] == 1050 and len(w.place(303).sent) == 1,
          "참가 포인트: 0이면 결과가 기록돼도 주지 않는다 (건 사람도 없으면 글을 올리지 않는다)")

    # 주인이 끈 뒤에도, 켜져 있을 때 짠 판은 끝까지 처리한다
    with contextlib.redirect_stdout(io.StringIO()):
        mod.hear(None, 100)
    kept = lineup(5, place=304)
    await mod.on_lineup(kept)
    with contextlib.redirect_stdout(io.StringIO()):
        mod.hear(False)
    await mod.on_result(kept, "r")
    check(acc["105"]["points"] == 1150 and w.place(304).texts()[-1].startswith("🎮 **참가 포인트** — 이 경기에 뛴 선수 10명이 **100 포인트**씩"),
          "참가 포인트: 주인이 끈 뒤에도, 켜져 있을 때 짠 판은 결과가 나오면 준다")
    await mod.on_lineup(lineup(6, place=305))
    await mod.on_result(lineup(6, place=305), "r")
    check(acc["105"]["points"] == 1150 and 305 not in w.places, "참가 포인트: 꺼져 있을 때 짠 판에는 주지 않는다")
    i = inter(400, user(105))
    await mod.show_points(i)
    check(said(i).startswith("🔮 보유 포인트는 **1,150**이에요.") and "참가 포인트" not in said(i) and "랭킹에는" not in said(i),
          "참가 포인트: 내 포인트에는 보유 포인트만 보인다 (참가 포인트로 얼마를 받았는지는 따로 알리지 않는다)")

    # 봇을 껐다 켜도 남는다. /오라클설정 으로 지금 값을 본다
    mod.S = mod.State()
    mod.setup(token="x", path=path, host=None)
    check(mod.S.play == 100 and (mod.S.accounts["100"]["points"], mod.S.accounts["100"]["played"], mod.S.accounts["100"]["earned"]) == (1150, 2, 150)
          and mod.find_book(pb["key"])["play"] == {str(uid): 50 for uid in range(100, 110)} and mod.find_book(pb["key"])["off"] is False
          and mod.find_book(qb["key"])["off"] is True, "참가 포인트: 봇을 껐다 켜도 금액과 준 것이 남는다")
    w = World(mod, path, T0)
    mod.S.play = 100
    w.play, w.first = 80, 300
    i = inter(100, ADMIN)
    with contextlib.redirect_stdout(io.StringIO()):
        await mod.cmd_setup(i, None)
    check("참가 포인트: 한 판에 **80**, 그날의 첫 내전은 **300** (결과가 기록되면 그 판에 뛴 선수가 받아요. 주인이 리그 관리자 페이지에서 바꿔요)\n" in said(i) and mod.S.play == 80,
          "/오라클설정 을 비우고 쓰면 참가 포인트도 보인다 (방금 바꾼 값이 그 자리에서 반영된다)")

    # ── 포인트 초기화: 주인이 리그 관리자 페이지에서 누르면 모든 사람의 포인트와 전적을 지운다 (서버 버전 20) ──
    path.unlink(missing_ok=True)
    w = World(mod, path, T0)
    mod.S.play = mod.S.first_play = 100
    w.reset = ""                                                     # 리그 서버: 초기화한 적이 없다
    w.players = {11, 12, 13} | set(range(100, 112))
    await mod.cmd_setup(inter(100, ADMIN), SimpleNamespace(id=400))
    for u in (A, B, C, user(105)):
        await mod.claim_points(inter(400, u))
    acc = mod.S.accounts
    done = lineup(1)                                                 # 결과까지 받은 판
    await mod.on_lineup(done)
    await mod.put_amount(inter(300, A), mod.S.books[0]["key"], "r", 300)
    await mod.put_amount(inter(300, B), mod.S.books[0]["key"], "d", 300)
    await mod.on_result(done, "r")
    waiting = lineup(2, place=301)                                   # 마감하고 결과를 기다리는 판
    await mod.on_lineup(waiting)
    wb = mod.S.books[1]
    await mod.put_amount(inter(301, A), wb["key"], "r", 200)
    await mod.put_amount(inter(301, C), wb["key"], "d", 200)
    w.at = wb["closes"]
    await mod.tick()
    opened = lineup(3, place=302)                                    # 받는 중인 판
    await mod.on_lineup(opened)
    ob = mod.S.books[2]
    await mod.put_amount(inter(302, B), ob["key"], "r", 100)
    post0 = w.place(400).sent[-1]
    n300 = len(w.place(300).sent)
    check(mod.S.reset == "" and mod.S.reset_wanted is None and len(acc) == 13 and acc["11"]["points"] == 1100 and wb["state"] == "closed" and ob["state"] == "open"
          and len(mod.S.books) == 3, "초기화: 리그 서버가 초기화하라고 하기 전에는 아무것도 지우지 않는다")
    w.reset = "2026-10-13T05:00:00.000Z"                            # 주인이 리그 관리자 페이지에서 눌렀다
    w.at += 300
    w.asked.clear()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        await mod.tick()
    check(mod.S.accounts == {} and mod.S.reset == w.reset and mod.S.reset_wanted is None and "승부 예측 포인트를 초기화했습니다. (13명의 포인트와 전적을 지웠습니다)" in out.getvalue()
          and json.loads(path.read_text(encoding="utf-8"))["reset"] == w.reset, "초기화: 5분마다 묻다가 알게 되면 모든 사람의 포인트와 전적을 지운다 (파일에 적어 둔다)")
    check([b["key"] for b in mod.S.books] == [wb["key"], ob["key"]] and (wb["state"], wb["bets"], wb["winner"], wb["off"]) == ("void", {}, None, False)
          and (ob["state"], ob["bets"]) == ("open", {}), "초기화: 끝난 판은 잊고, 결과를 기다리던 판은 건 포인트만 없던 일로 한다 (받는 중인 판은 그대로 열어 둔다)")
    check(w.place(301).texts()[-1] == "🔮 승부 예측 포인트가 초기화돼서, 이 경기에 건 포인트는 없던 일이 됐어요."
          and w.place(302).texts()[-1] == "🔮 승부 예측 포인트가 초기화돼서, 이 경기에 건 포인트는 없던 일이 됐어요. 마감 전까지 이번 주 포인트를 다시 받아 걸 수 있어요."
          and w.place(302).sent[0].text.endswith("지금까지 **0명**이 걸었어요.") and isinstance(w.place(302).sent[0].view, mod.BetView) and len(w.place(300).sent) == n300,
          "초기화: 걸려 있던 판의 글에 알리고, 받는 중인 판의 글은 0명으로 고친다 (끝난 판의 글에는 알리지 않는다)")
    live = [m for m in w.place(400).sent if not m.deleted and isinstance(m.view, mod.ClaimView)]
    check(post0.deleted and len(live) == 1 and live[0].id == mod.S.round["message_id"] and live[0] is not post0, "초기화: '포인트 받기' 글을 새로 올린다 (앞의 글은 지워 버튼은 하나)")
    sent = [p for p in w.asked if p["action"] == "saveOracle"]
    check(len(sent) == 1 and sent[0]["reset"] == w.reset and sent[0]["board"]["players"] == [] and sent[0]["state"]["reset"] == w.reset and not mod.S.dirty,
          "초기화: 비운 순위를 바로 리그 서버에 올린다 (초기화했다는 표시와 함께)")
    i = inter(400, A)
    await mod.claim_points(i)
    check(said(i).startswith("✅ **1,000 포인트**를 받았어요. 보유 포인트는 **1,000**이에요.") and (acc is not mod.S.accounts) and mod.S.accounts["11"]["claimed"] == 1,
          "초기화: 이번 주에 이미 받았던 사람도 다시 받을 수 있다")
    acc = mod.S.accounts
    i = inter(302, A)
    await mod.put_amount(i, ob["key"], "r", 400)
    check(said(i).startswith("✅ 🟢 래디언트에 **400 포인트**") and acc["11"]["points"] == 600, "초기화: 받는 중이던 판에는 새로 받은 포인트로 다시 걸 수 있다")
    await mod.on_result(waiting, "r")
    check(wb["play"] == {str(uid): 100 for uid in range(100, 110)} and acc["105"] == dict(acc["105"], points=100, claimed=0, played=1)
          and w.place(301).texts()[-1].startswith("🎮 **참가 포인트** — 이 경기에 뛴 선수 10명이 **100 포인트**씩"),
          "초기화: 결과를 기다리던 판은 결과가 기록되면 참가 포인트만 준다 (건 포인트는 정산하지 않는다)")
    await mod.on_undo(done)
    await mod.on_void(done)
    check(len(w.place(300).sent) == n300 and acc["11"]["points"] == 600 and "12" not in acc, "초기화: 그 전에 끝난 판의 /승리취소 는 지운 포인트를 건드리지 않는다")
    w.at += 300
    await mod.tick()
    check(acc is mod.S.accounts and acc["11"]["points"] == 600, "초기화: 같은 초기화를 두 번 하지 않는다")
    # 5분마다 묻기 전에 순위를 올리다가 알게 되는 경우: 서버는 초기화 전의 순위를 받지 않고, 초기화하라고 알려 준다
    w.reset = "2026-10-20T00:00:00.000Z"
    await mod.claim_points(inter(400, B))
    w.at += 21
    w.asked.clear()
    await mod.tick()
    check(mod.S.reset_wanted == w.reset and "12" in mod.S.accounts and mod.S.dirty and len(w.asked) == 1,
          "초기화: 순위를 올리다가 서버가 받지 않으면(그사이 초기화됐다) 초기화하라는 것을 알게 된다")
    w.at += 10
    with contextlib.redirect_stdout(io.StringIO()):
        await mod.tick()
    check(mod.S.accounts == {} and mod.S.reset == w.reset and not mod.S.dirty and w.asked[-1]["reset"] == w.reset and w.asked[-1]["board"]["players"] == [],
          "초기화: 곧 초기화하고 비운 순위를 다시 올린다")
    await mod.claim_points(inter(400, C))
    w2 = World(mod, path, w.at)                                      # 봇을 껐다 켰다
    w2.reset, w2.players = w.reset, {13}
    await mod.tick()
    check(mod.S.reset == w.reset and mod.S.accounts["13"]["points"] == 1000, "초기화: 봇을 껐다 켜도 이미 한 초기화를 다시 하지 않는다")
    w2.reset = None                                                  # 그 값을 모르는 예전 서버(버전 19까지)
    w2.at += 300
    await mod.tick()
    mod.hear(None, None, None)
    mod.hear(None, None, 5)
    check(mod.S.reset == w.reset and mod.S.reset_wanted is None and "13" in mod.S.accounts, "초기화: 그 값을 주지 않는 서버의 답으로는 초기화하지 않는다")

    # ── 그날의 첫 내전: 그날 결과가 가장 먼저 기록된 판에 뛴 선수는 참가 포인트를 300 받는다 (하루는 오전 6시에 바뀐다. 서버 버전 21) ──
    path.unlink(missing_ok=True)
    check(mod.State().first_play == 300 == mod.FIRST_POINTS, "첫 내전: 그날의 첫 내전의 참가 포인트는 처음에 300이다")
    w = World(mod, path, T0)                                         # 화요일 낮 12시
    mod.S.play, mod.S.first_play = 100, 300
    w.players = set(range(100, 112)) | set(range(200, 212))
    g1, g2 = lineup(1), lineup(2, place=301)
    g2["who"] = {f"p{k}": 200 + k for k in range(12)}               # 다른 열 명이 뛰는 판
    await mod.on_lineup(g1)
    await mod.on_lineup(g2)
    b1, b2 = mod.find_book(mod.book_key(g1)), mod.find_book(mod.book_key(g2))
    acc = mod.S.accounts
    check("이 경기에 뛰는 선수는 걸 수 없어요. 대신 결과가 기록되면 참가 포인트로 **100 포인트**를 받아요(오늘의 첫 내전이면 **300 포인트**).\n"
          in w.place(300).sent[0].text, "첫 내전: 승부 예측 글에서, 오늘의 첫 내전이면 300을 받는다고 알린다")
    await mod.on_result(g2, "r")                                     # 나중에 짠 판이 먼저 끝났다
    check(b2["first"] and b2["play"] == {str(u): 300 for u in range(200, 210)} and (acc["200"]["points"], acc["200"]["played"], acc["200"]["earned"]) == (300, 1, 300)
          and w.place(301).texts()[-1] == "🎮 **참가 포인트** — 오늘의 첫 내전이라 이 경기에 뛴 선수 10명이 **300 포인트**씩 받았어요.\n\n"
          "📊 승부의 신 랭킹: <https://example.invalid/oracle.html>",
          "첫 내전: 그날 결과가 가장 먼저 기록된 판에 뛴 선수가 300을 받는다 (먼저 짠 판보다 먼저 끝나도. 알리는 글에도 적는다)")
    i = inter(300, user(105))
    await mod.pick_side(i, "r")
    check(said(i) == "이 경기에 뛰는 선수는 걸 수 없어요. 대신 결과가 기록되면 참가 포인트로 **100 포인트**를 받아요.", "첫 내전: 그날의 첫 내전이 정해진 뒤에는 100만 알린다")
    await mod.on_result(g1, "d")
    check(not b1["first"] and b1["play"] == {str(u): 100 for u in range(100, 110)}
          and w.place(300).texts()[-1].startswith("🎮 **참가 포인트** — 이 경기에 뛴 선수 10명이 **100 포인트**씩"), "첫 내전: 같은 날 그 뒤에 기록된 판은 100을 받는다")
    await mod.on_undo(g2)
    check(not b2["first"] and b2["play"] == {} and acc["200"]["points"] == 0 and acc["100"]["points"] == 100,
          "첫 내전: /승리취소 면 300을 거두고 첫 내전의 자리를 비운다 (이미 100을 받은 판은 그대로)")
    await mod.on_result(g2, "d")
    check(b2["first"] and acc["200"]["points"] == 300, "첫 내전: 다시 기록하면 다시 300을 받는다 (그사이 기록된 판이 없으면)")
    w.at = T0 + 18 * 3600 - 60                                       # 수요일 오전 5시 59분: 아직 화요일
    g3 = lineup(3, place=302)
    await mod.on_lineup(g3)
    await mod.on_result(g3, "r")
    check(not mod.find_book(mod.book_key(g3))["first"] and acc["100"]["points"] == 200, "첫 내전: 오전 6시 전에 짠 판은 그 전날의 내전이다")
    w.at = T0 + 18 * 3600                                            # 수요일 오전 6시
    g4 = lineup(4, place=303)
    await mod.on_lineup(g4)
    await mod.on_result(g4, "r")
    b4 = mod.find_book(mod.book_key(g4))
    check(b4["first"] and acc["100"]["points"] == 500, "첫 내전: 오전 6시부터 새 날이라, 그날 처음 기록된 판이 다시 300을 받는다")
    w.at = T0 + 42 * 3600                                            # 목요일 오전 6시
    mod.S.first_play = 100
    g5 = lineup(5, place=304)
    await mod.on_lineup(g5)
    shown = w.place(304).sent[0].text                                 # 마감하면 이 글은 고쳐진다
    await mod.on_result(g5, "r")
    check("참가 포인트로 **100 포인트**를 받아요.\n" in shown
          and w.place(304).texts()[-1].startswith("🎮 **참가 포인트** — 이 경기에 뛴 선수 10명이 **100 포인트**씩"), "첫 내전: 두 값이 같으면 첫 내전을 따로 말하지 않는다")
    w.at = T0 + 66 * 3600                                            # 금요일 오전 6시
    mod.S.play, mod.S.first_play = 0, 300
    g6, g7 = lineup(6, place=305), lineup(7, place=306)
    await mod.on_lineup(g6)
    check("이 경기에 뛰는 선수는 걸 수 없어요. 대신 오늘의 첫 내전이면 결과가 기록될 때 참가 포인트로 **300 포인트**를 받아요.\n" in w.place(305).sent[0].text,
          "첫 내전: 다른 판에 주지 않을 때(0)는 첫 내전에서만 받는다고 알린다")
    await mod.on_result(g6, "r")
    await mod.on_lineup(g7)
    shown = w.place(306).sent[0].text
    await mod.on_result(g7, "r")
    check(acc["100"]["points"] == 900 and mod.find_book(mod.book_key(g7))["play"] == {} and "참가 포인트" not in shown and "걸 수 없어요. 포인트가 없으면" in shown,
          "첫 내전: 그날의 첫 내전이 지나면 0인 판에는 주지 않는다 (승부 예측 글에서도 말하지 않는다)")
    w.first, w.play = 250, 100
    w.at += 300
    await mod.tick()
    check((mod.S.first_play, mod.S.play) == (250, 100) and mod.board()["first"] == 250, "첫 내전: 리그 서버가 알려 준 값으로 바뀐다 (5분마다 물어볼 때. 순위에도 싣는다)")
    mod.S = mod.State()
    mod.setup(token="x", path=path, host=None)
    check(mod.S.first_play == 250 and mod.find_book(mod.book_key(g4))["first"] is True and mod.find_book(mod.book_key(g3))["first"] is False,
          "첫 내전: 봇을 껐다 켜도 금액과 어느 판이 첫 내전이었는지가 남는다")

    # ── 승부의 신 랭킹에 오르는 사람: 포인트를 받았거나 승부 예측에 한 번이라도 건 사람 (운영자가 2026-10-21에 정함. 그 전에는 포인트를 받은 사람만) ──
    path.unlink(missing_ok=True)
    w = World(mod, path, T0)
    mod.S.play = mod.S.first_play = 100
    w.players = set(range(100, 112))
    w.nicks = {100: "백"}
    game = lineup(1)
    await mod.on_lineup(game)
    await mod.on_result(game, "r")
    acc = mod.S.accounts
    check(acc["100"]["points"] == 100 and not acc["100"]["listed"] and mod.board()["players"] == [],
          "랭킹: 참가 포인트만 받은 사람은 오르지 않는다 (포인트는 그대로 쌓인다)")
    i = inter(400, user(100))
    await mod.show_points(i)
    check("승부의 신 랭킹에는 **포인트 받기**를 누르거나 승부 예측에 한 번이라도 걸면 이름이 올라가요." in said(i), "랭킹: 내 포인트에서 어떻게 오르는지 알려 준다")
    other = lineup(2, place=301)
    other["who"] = {f"p{k}": 200 + k for k in range(12)}
    await mod.on_lineup(other)
    ob = mod.find_book(mod.book_key(other))
    mod.S.dirty = False
    await mod.put_amount(inter(301, user(100)), ob["key"], "r", 60)
    check(acc["100"]["listed"] and mod.board()["players"] == [{"name": "백", "points": 100, "profit": 0, "bets": 0, "hits": 0, "claimed": 0}] and mod.S.dirty,
          "랭킹: 포인트 받기를 누르지 않았어도 승부 예측에 걸면 바로 오른다 (걸어 둔 포인트도 보유 포인트로 친다)")
    await mod.cancel_bet(inter(301, user(100)), ob["key"])
    check(acc["100"]["listed"] and len(mod.board()["players"]) == 1 and acc["100"]["points"] == 100, "랭킹: 건 것을 취소해도 남는다")
    await mod.put_amount(inter(301, user(100)), ob["key"], "d", 40)
    i = inter(400, user(100))
    await mod.show_points(i)
    check("랭킹에는" not in said(i), "랭킹: 오른 뒤에는 내 포인트에서 따로 말하지 않는다")
    w.at += 30
    w.asked.clear()
    await mod.tick()
    sent = w.asked[-1]
    led = {r["id"]: r for r in sent["ledger"]}
    check(sent["action"] == "saveOracle" and sorted(led) == [str(u) for u in range(100, 110)]
          and led["100"] == {"id": "100", "username": "u100", "name": "백", "points": 100, "staked": 40, "profit": 0, "bets": 0, "hits": 0, "claimed": 0,
                             "played": 1, "earned": 100, "listed": True}
          and led["101"] == {"id": "101", "username": "u101", "name": "선수101", "points": 100, "staked": 0, "profit": 0, "bets": 0, "hits": 0, "claimed": 0,
                             "played": 1, "earned": 100, "listed": False}
          and [r["name"] for r in sent["board"]["players"]] == ["백"],
          "랭킹: 리그 서버에는 시트에 적을 모든 사람의 기록을 따로 올린다 (공개 순위에는 오른 사람만. 디스코드 ID는 공개 순위에 싣지 않는다)")
    check(sorted(w.lookups) == list(range(101, 110)) and mod.S.accounts["105"]["username"] == "u105",
          "랭킹: 참가 포인트만 받아 이름을 모르는 사람은 올리기 전에 디스코드에 물어 사용자명을 적는다 (시트의 등록 탭과 맞추려고)")
    mod.S.dirty = True
    w.at += 30
    await mod.tick()
    check(len(w.lookups) == 9, "랭킹: 이름은 한 사람에 한 번만 묻는다")
    mod.adopt({"accounts": {"1": {"points": 5, "claimed": 1}, "2": {"points": 5, "bets": 2}, "3": {"points": 5, "played": 1}, "4": {"points": 5}},
               "books": [{"key": "k", "state": "open", "bets": {"4": {"side": "r", "amount": 10, "at": 0}}}]})
    check([mod.S.accounts[k]["listed"] for k in "1234"] == [True, True, False, True],
          "랭킹: 이 칸이 생기기 전의 기록은 포인트를 받았거나 건 적이 있으면 오른 것으로 본다 (걸어 둔 판이 있는 사람도)")

    # ── 시간 등록 포인트 (서버 버전 22): 리그 서버가 5분마다 알려 주면 넣고, 넣었다고 알린다 ──
    path.unlink(missing_ok=True)
    w = World(mod, path, T0)
    g1 = {"g": "100:first", "id": "100", "u": "u100", "n": "백", "p": 1000, "k": "first", "at": "2026-10-13T03:00:00Z"}
    g2 = {"g": "101:first", "id": "101", "u": "u101", "n": "선수101", "p": 1000, "k": "first"}
    g3 = {"g": "100:e1", "id": "100", "u": "u100", "n": "백", "p": 300, "k": "event"}
    w.grants = [g1, g2, g3, {"g": "", "id": "1", "p": 5}, {"g": "x", "id": "abc", "p": 5}, {"g": "y", "id": "5", "p": -1}, {"g": "z", "id": "6", "p": True}, "junk"]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        await mod.check_switch(force=True)
    acc = mod.S.accounts
    check(acc["100"]["points"] == 1300 and acc["101"]["points"] == 1000 and acc["100"]["username"] == "u100" and acc["100"]["name"] == "백"
          and not acc["100"]["listed"] and acc["100"]["claimed"] == 0 and mod.S.dirty and set(acc) == {"100", "101"},
          "시간 등록 포인트: 리그 서버가 알려 준 포인트를 넣는다 (랭킹에 오르는 기준은 그대로, 모양이 이상한 것은 버린다)")
    check(w.acks == [["100:first", "101:first", "100:e1"]] and all(not isinstance(g, dict) or not g.get("g", "").startswith("10") for g in w.grants) and "시간 등록 포인트를 2명에게 넣었습니다 (모두 2,300 포인트)" in out.getvalue(),
          "시간 등록 포인트: 넣은 것을 서버에 알리고(서버가 지운다) 창에 찍는다")
    w.grants, w.ack_fail = [g1, g2, g3], True
    w.at += mod.SWITCH_POLL
    with contextlib.redirect_stdout(io.StringIO()):
        await mod.check_switch()
    check(acc["100"]["points"] == 1300 and acc["101"]["points"] == 1000 and len(w.acks) == 1 and len(w.grants) == 3,
          "시간 등록 포인트: 서버가 같은 것을 다시 알려 와도 두 번 넣지 않는다 (알리지 못하면 서버에 남는다)")
    w.ack_fail = False
    w.at += mod.SWITCH_POLL
    await mod.check_switch()
    check(acc["100"]["points"] == 1300 and w.acks[-1] == ["100:first", "101:first", "100:e1"] and not w.grants, "시간 등록 포인트: 다음 확인 때 다시 알리기만 한다")
    check(acc["100"]["points"] == 1300 and json.loads(path.read_text(encoding="utf-8"))["granted"].keys() == {"100:first", "101:first", "100:e1"},
          "시간 등록 포인트: 넣은 것은 파일에 적어 둔다")
    w = World(mod, path, w.at)
    check(set(mod.S.granted) == {"100:first", "101:first", "100:e1"} and mod.S.accounts["100"]["points"] == 1300, "시간 등록 포인트: 껐다 켜도 넣은 것을 기억한다")
    g4 = {"g": "102:first", "id": "102", "u": "u102", "n": "선수102", "p": 1000, "k": "first"}
    w.grants, w.switch = [g4], False
    with contextlib.redirect_stdout(io.StringIO()):
        await mod.check_switch(force=True)
    check(not mod.S.on and "102" not in mod.S.accounts and w.acks == [] and w.grants == [g4], "시간 등록 포인트: 주인이 꺼 둔 동안에는 넣지 않고 서버에 남겨 둔다")
    w.switch = True
    w.at += mod.SWITCH_POLL
    with contextlib.redirect_stdout(io.StringIO()):
        await mod.check_switch()
    check(mod.S.on and mod.S.accounts["102"]["points"] == 1000 and w.acks == [["102:first"]], "시간 등록 포인트: 켜진 뒤에 넣는다")
    w.at += 30
    w.asked.clear()
    await mod.tick()
    sent = [x for x in w.asked if x["action"] == "saveOracle"]
    check(sent and {r["id"]: r["points"] for r in sent[-1]["ledger"]} == {"100": 1300, "101": 1000, "102": 1000} and sent[-1]["board"]["players"] == [],
          "시간 등록 포인트: 넣은 포인트는 시트의 기록에 올라가고, 랭킹에는 오르지 않는다")
    mod.S.reset_wanted = "r1"
    with contextlib.redirect_stdout(io.StringIO()):
        await mod.apply_reset()
    w.grants = [g1]
    w.at += mod.SWITCH_POLL
    with contextlib.redirect_stdout(io.StringIO()):
        await mod.check_switch()
    check(mod.S.accounts == {} and "100:first" in mod.S.granted and w.acks[-1] == ["100:first"],
          "시간 등록 포인트: 포인트를 초기화해도 이미 넣은 처음 등록 포인트는 다시 넣지 않는다")
    mod.S.granted["old:first"] = w.at - mod.GRANT_KEEP - 1
    w.grants = [{"g": "103:first", "id": "103", "u": "u103", "n": "선수103", "p": 0, "k": "first"}]
    w.at += mod.SWITCH_POLL
    await mod.check_switch()
    check("old:first" not in mod.S.granted and "103:first" in mod.S.granted and mod.S.accounts["103"]["points"] == 0, "시간 등록 포인트: 오래된 기억은 지운다 (0 포인트도 받아서 지운다)")

    # ── 오라클 봇을 쓰지 않을 때(토큰이 없을 때)는 아무 일도 하지 않는다 ──
    path.unlink(missing_ok=True)
    w = World(mod, path, T0)
    mod.S.token = ""
    await mod.on_lineup(lineup(1))
    await mod.on_result(lineup(1), "r")
    await mod.on_undo(lineup(1))
    await mod.on_void(lineup(1))
    check(not mod.enabled() and mod.S.books == [] and not w.places and mod.status_line() == "꺼짐 (config.json 에 oracle_token 을 넣으면 켜집니다)",
          "오라클 봇의 토큰을 넣지 않았으면 퍼그나봇이 알려 줘도 아무 일도 하지 않는다")
    mod.S.token = "x"
    check(mod.status_line() == "켜는 중 (로그인하면 아래에 따로 알립니다)", "토큰을 넣었으면 켠다")

    # ── 건 사람이 아주 많을 때: 마감 글을 나눠 올린다 ──
    await mod.on_lineup(lineup(1, place=320))
    big = mod.S.books[0]
    for k in range(120):
        uid = 100000000000000000 + k
        mod.S.accounts[str(uid)] = {"points": 0, "claimed": 1, "week": MON, "name": f"선수{k}", "username": f"u{k}", "nick": "", "bets": 0, "hits": 0, "profit": 0,
                                    "played": 0, "earned": 0, "listed": True}
        big["bets"][str(uid)] = {"side": "rd"[k % 2], "amount": 100 + k, "at": T0 + k}
    w.at = big["closes"]
    await mod.tick()
    parts = w.place(320).texts()[1:]
    check(len(parts) > 1 and all(len(p) <= 2000 for p in parts) and sum(p.count("→ 이기면") for p in parts) == 120 and parts[0].startswith("🔮 **승부 예측 마감** — 120명이 걸었어요."),
          f"건 사람이 아주 많으면 마감 글을 나눠 올린다 ({len(parts)}개, 가장 긴 것 {max(len(p) for p in parts)}자)")

    # ── 명령어와 버튼의 모양 ──
    bot = mod.OracleBot()
    mod.add_commands(bot.tree, discord.Object(id=1))
    cmds = {c.name: c for c in bot.tree.get_commands(guild=discord.Object(id=1))}
    check(sorted(cmds) == ["오라클설정"] and [p.display_name for p in cmds["오라클설정"].parameters] == ["채널"] and not cmds["오라클설정"].parameters[0].required
          and not hasattr(mod, "cmd_points"), "오라클 봇의 명령어: /오라클설정 채널 하나뿐이다 (/포인트 는 없다. 포인트는 버튼으로만 받는다)")
    check(bot.intents.guilds and not bot.intents.members and not bot.intents.message_content and bot.allowed_mentions.everyone is False and bot.allowed_mentions.roles is False
          and bot.allowed_mentions.users is False, "오라클 봇은 특권 인텐트를 쓰지 않고, 멘션 알림을 울리지 않는다")
    await bot.close()

    for task in asyncio.all_tasks() - {asyncio.current_task()}:
        task.cancel()
    shutil.rmtree(HERE, ignore_errors=True)
    print(f"\n실패 {failed}건")
    sys.exit(1 if failed else 0)


asyncio.run(main())
