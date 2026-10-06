"""
봇 로직 테스트: bot/bot.py 를 가짜 디스코드 객체로 돌려 본다 (실제 디스코드에는 연결하지 않는다).

    python tests/bot.test.py

bot.py 는 불러올 때 같은 폴더의 config.json 을 읽으므로, 임시 폴더에 가짜 설정과 함께 복사해서 불러온다.
"""
import asyncio
import collections
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import discord

SRC = Path(__file__).resolve().parent.parent / "bot" / "bot.py"
HERE = Path(tempfile.mkdtemp(prefix="inhouse-bot-test-"))
failed = 0


def check(cond, label):
    global failed
    if cond:
        print("ok  ", label)
    else:
        failed += 1
        print("FAIL", label)


def load():
    shutil.copy(SRC, HERE / "bot.py")
    (HERE / "config.json").write_text(json.dumps({
        "token": "x", "guild_id": 1, "admin_channel_id": 100, "signup_channel_id": 200,
        "admin_role_id": 0, "signup_minutes": 5, "announcement": "공지", "sync_url": "", "sync_key": "",
    }, ensure_ascii=False), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("botmod", HERE / "bot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


Created = collections.namedtuple("Created", "thread message")


class World:
    """가짜 디스코드 서버와 가짜 리그 서버. league 를 주면 자동 팀 편성이 켜진 것으로 본다."""

    def __init__(self, mod, forum=True, sync=None, league=None):
        self.mod = mod
        self.thread = Mock()
        self.thread.id = 300
        self.thread.send = AsyncMock()
        self.thread.edit = AsyncMock()
        self.message = Mock()
        self.message.id = 300
        self.message.edit = AsyncMock()
        self.message.jump_url = "https://discord.com/channels/1/300/300"
        self.thread.get_partial_message = Mock(return_value=self.message)
        self.admin = Mock()
        self.admin.send = AsyncMock()
        if forum:
            self.signup = Mock(spec=discord.ForumChannel)
            self.signup.flags = Mock(require_tag=False)
            self.signup.available_tags = []
            self.signup.create_thread = AsyncMock(return_value=Created(self.thread, self.message))
        else:
            self.signup = Mock(spec=discord.TextChannel)
            self.signup.send = AsyncMock(return_value=self.message)
            self.signup.get_partial_message = Mock(return_value=self.message)
        self.place = self.thread if forum else self.signup
        self.place_id = 300 if forum else 200

        async def get_channel(cid):
            return {100: self.admin, 200: self.signup, 300: self.thread}[cid]

        self.pushed = []

        async def push_roster(rec, clear=False):
            self.pushed.append("clear" if clear else list(rec.participants))
            return sync

        self.league = league
        self.rev = 1              # 서버의 리그 기록 번호
        self.server = []          # 리그 서버로 보낸 요청
        self.fail = set()         # 실패하게 만들 요청 이름
        self.conflicts = 0        # 이 횟수만큼, 봇이 받아 간 사이에 매니저가 기록을 바꾼 것처럼 군다

        async def call_server(payload):
            self.server.append(payload)
            action = payload["action"]
            if action in self.fail:
                raise RuntimeError("서버 오류")
            if action == "adminLeague":
                return {"ok": True, "league": self.league, "rev": self.rev}
            if action == "saveLeague":
                if self.conflicts > 0:
                    self.conflicts -= 1
                    self.rev += 1
                if payload.get("baseRev") != self.rev:
                    raise mod.ServerError("서버에 더 새로운 기록이 있습니다", "conflict")
                self.rev += 1
                self.league = payload["league"]
            return {"ok": True}

        mod.get_channel = get_channel
        mod.push_roster = push_roster
        mod.call_server = call_server
        mod.match_problem = (lambda: "") if league is not None else (lambda: "꺼짐 (테스트)")
        mod.when = lambda ts: f"<t:{ts}:t>"      # 자정 무렵에 돌려도 결과가 같게, 날짜 표시는 따로 확인한다
        mod.bot.lock = asyncio.Lock()
        mod.bot.current = None
        mod.bot.lineups = []
        mod.STATE_PATH.unlink(missing_ok=True)

    def texts(self, mock):
        return [c.args[0] for c in mock.call_args_list]


def user(uid, name, admin=False):
    u = Mock(spec=discord.Member)
    u.id = uid
    u.display_name = name
    u.name = "u" + str(uid)
    u.mention = f"<@{uid}>"
    u.guild_permissions = Mock(administrator=admin)
    u.roles = []
    return u


def inter(channel_id, u):
    i = Mock()
    i.channel_id = channel_id
    i.user = u
    i.response = Mock()
    i.response.send_message = AsyncMock()
    i.response.defer = AsyncMock()
    i.response.is_done = Mock(return_value=False)
    i.followup = Mock()
    i.followup.send = AsyncMock()
    return i


def said(i):
    calls = i.response.send_message.call_args_list + i.followup.send.call_args_list
    return calls[-1].args[0] if calls else ""


async def run(cmd, channel_id, u, *args):
    i = inter(channel_id, u)
    await cmd.callback(i, *args)
    return said(i), i


async def main():
    mod = load()
    KST = mod.KST
    real_when, real_problem = mod.when, mod.match_problem
    ADMIN = user(1, "운영자", admin=True)
    A, B, C = user(11, "가"), user(12, "나*별"), user(13, "다")

    # ── 마감 시각 계산 ──
    at = lambda h, m, s: datetime(2026, 10, 6, h, m, s, tzinfo=KST).timestamp()
    check(mod.deadline_after(300, at(12, 0, 30)) == at(12, 6, 0), "12:00:30 생성 → 12:06:00 마감")
    check(mod.deadline_after(300, at(12, 0, 0)) == at(12, 5, 0), "12:00:00 생성 → 12:05:00 마감")
    check(mod.deadline_after(300, at(12, 0, 1)) == at(12, 6, 0), "12:00:01 생성 → 12:06:00 마감")
    check(mod.deadline_after(300, at(23, 57, 59)) == datetime(2026, 10, 7, 0, 3, 0, tzinfo=KST).timestamp(), "자정을 넘겨도 분 단위 올림")
    check(mod.minutes_text(300) == "5분" and mod.minutes_text(150) == "2.5분", "분 표기")
    check(re.fullmatch(r"\d+월 \d+일\([월화수목금토일]\) \d\d:\d\d 내전 모집", mod.post_title()) is not None, "글 제목 형식: " + mod.post_title())

    # ── 포럼 ──
    w = World(mod, forum=True)
    t, _ = await run(mod.create_inhouse, 999, ADMIN)
    check("관리자 채널에서만" in t and mod.bot.current is None, "다른 채널의 /내전생성 거절")
    for cmd, nm in ((mod.close_now, "마감"), (mod.extend, "연장"), (mod.cancel, "취소")):
        t, _ = await run(cmd, 300, ADMIN)
        check("관리자 채널에서만" in t, f"다른 채널의 /{nm} 거절")
    t, _ = await run(mod.close_now, 100, ADMIN)
    check("모집 중인 내전이 없어요" in t, "모집이 없을 때 /마감")
    t, _ = await run(mod.extend, 100, ADMIN)
    check("연장할 내전이 없어요" in t, "모집이 없을 때 /연장")
    t, _ = await run(mod.cancel, 100, ADMIN)
    check("취소할 내전이 없어요" in t, "모집이 없을 때 /취소")
    t, _ = await run(mod.join, 300, A)
    check("모집 중인 내전이 없어요" in t, "모집이 없을 때 /참여")

    before = time.time()
    t, _ = await run(mod.create_inhouse, 100, ADMIN)
    rec = mod.bot.current
    check(rec is not None and w.signup.create_thread.await_count == 1, "/내전생성 → 포럼 글 생성")
    kw = w.signup.create_thread.call_args.kwargs
    check(re.fullmatch(r"\d+월 \d+일\(.\) \d\d:\d\d 내전 모집", kw["name"]) is not None and "applied_tags" not in kw, "글 제목, 태그 없음")
    check(f"**<t:{rec.end_ts}:t>까지** 참여 신청" in kw["content"] and f"<t:{rec.end_ts}:R> 마감)" in kw["content"], "본문에 마감 시각")
    check("여기에서 `/참여`" in kw["content"] and "참여자 (0명): 아직 없음" in kw["content"], "본문에 참여 방법과 명단")
    check(rec.end_ts % 60 == 0 and 300 <= rec.end_ts - before <= 361, "마감은 5~6분 뒤의 정각 분")
    check(w.message.jump_url in t and f"<t:{rec.end_ts}:t>" in t, "운영진에게 글 링크와 마감 시각 안내")
    check(rec.task is not None and not rec.task.done(), "자동 마감 대기 중")

    t, _ = await run(mod.create_inhouse, 100, ADMIN)
    check("이미 모집 중" in t and w.signup.create_thread.await_count == 1, "모집 중 /내전생성 거절")

    t, _ = await run(mod.join, 200, A)
    check(t == "<#300> 에서 입력해 주세요." and not rec.participants, "모집 글 밖의 /참여 는 글로 안내")
    for u in (A, B, C):
        t, _ = await run(mod.join, 300, u)
    check(list(rec.participants) == [11, 12, 13] and "3번째" in t, "모집 글 안에서 /참여 세 명")
    body = w.message.edit.call_args.kwargs["content"]
    check("참여자 (3명): 가, 나\\*별, 다" in body, "본문 명단 갱신(마크다운 문자 처리)")
    t, _ = await run(mod.join, 300, A)
    check("이미 참여했어요! (1번째)" in t, "중복 /참여")
    t, _ = await run(mod.leave, 300, C)
    check(list(rec.participants) == [11, 12] and "취소했어요" in t, "/참여취소")
    t, _ = await run(mod.leave, 300, C)
    check("기록이 없어요" in t, "신청하지 않은 사람의 /참여취소")

    old_end, old_task = rec.end_ts, rec.task
    t, _ = await run(mod.extend, 100, ADMIN)
    await asyncio.sleep(0)
    check(rec.end_ts == old_end + 300 and not rec.closed and rec.extended, "모집 중 /연장 → 마감 5분 뒤로")
    check(old_task.cancelled() and rec.task is not old_task and not rec.task.done(), "자동 마감 시각도 옮겨짐")
    check("모집을 연장했어요." in t and f"<t:{rec.end_ts}:t>" in t, "운영진에게 새 마감 안내")
    check(any("연장했어요" in x and f"<t:{rec.end_ts}:t>까지" in x for x in w.texts(w.thread.send)), "모집 글에 연장 알림")
    check("연장됨" in w.message.edit.call_args.kwargs["content"] and w.thread.edit.await_count == 0, "본문에 연장 표시, 잠금 변화 없음")

    task = rec.task
    t, _ = await run(mod.close_now, 100, ADMIN)
    await asyncio.sleep(0)
    check(rec.closed and not rec.cancelled and mod.bot.current is rec, "/마감 → 즉시 마감, 기록은 남겨 둠")
    check(task.cancelled() and rec.task is None, "자동 마감 대기 중지")
    roster = [x for x in w.texts(w.thread.send) if "내전 참여 명단" in x]
    check(len(roster) == 1 and "1. <@11>\n2. <@12>" in roster[0] and "8명 부족" in roster[0], "모집 글에 명단 공지")
    check("모집 마감** — 최종 2명" in w.message.edit.call_args.kwargs["content"], "본문이 마감 상태로 바뀜")
    adm = w.texts(w.admin.send)
    check(adm[0].startswith("[모집 종료] 주최: <@1>") and "```\n11 u11 가\n12 u12 나*별\n```" in adm[1], "관리자 채널에 명단과 매니저용 블록")
    check(any("`/연장` 으로 5분 더" in x for x in adm), "인원 부족 시 연장·취소 안내")
    check(w.thread.edit.call_args.kwargs == {"locked": True, "archived": False}, "모집 글 잠금")
    check("마감했어요. (최종 2명)" in t, "운영진에게 마감 안내")
    t, _ = await run(mod.join, 300, C)
    check("모집 중인 내전이 없어요" in t and 13 not in rec.participants, "마감 뒤 /참여 거절")
    t, _ = await run(mod.close_now, 100, ADMIN)
    check("모집 중인 내전이 없어요" in t, "마감 뒤 /마감")

    now = time.time()
    t, _ = await run(mod.extend, 100, ADMIN)
    check(not rec.closed and rec.end_ts % 60 == 0 and 300 <= rec.end_ts - now <= 361, "마감 뒤 /연장 → 지금부터 5분(분 단위 올림)")
    check(w.thread.edit.call_args.kwargs == {"locked": False, "archived": False}, "모집 글 잠금 해제")
    check("다시 열었어요" in t and "까지** 참여 신청" in w.message.edit.call_args.kwargs["content"], "본문이 모집 중으로 돌아옴")
    t, _ = await run(mod.join, 300, C)
    check(list(rec.participants) == [11, 12, 13], "다시 연 뒤 /참여")

    # 자동 마감: 마감 시각을 0.3초 뒤로 당겨서 확인
    mod.stop_timer(rec)
    rec.end_ts = time.time() + 0.3
    rec.task = asyncio.create_task(mod.close_when_due(rec))
    await asyncio.sleep(0.8)
    roster = [x for x in w.texts(w.thread.send) if "내전 참여 명단" in x]
    check(rec.closed and len(roster) == 2 and "3. <@13>" in roster[1] and rec.task is None, "시간이 되면 자동 마감, 새 명단 공지")

    t, _ = await run(mod.cancel, 100, ADMIN)
    check(rec.cancelled and "취소했어요" in t and w.message.jump_url in t, "마감 뒤 /취소")
    check(w.texts(w.thread.send)[-1] == "❌ **이번 내전은 취소됐어요.**\n<@11> <@12> <@13>", "취소 알림에 참여자 멘션")
    check("취소됐어요" in w.message.edit.call_args.kwargs["content"], "본문이 취소 상태로 바뀜")
    t, _ = await run(mod.extend, 100, ADMIN)
    check("연장할 내전이 없어요" in t and rec.closed, "취소 뒤 /연장 거절")
    t, _ = await run(mod.cancel, 100, ADMIN)
    check("취소할 내전이 없어요" in t, "취소 뒤 /취소")

    t, _ = await run(mod.create_inhouse, 100, ADMIN)
    rec2 = mod.bot.current
    check(rec2 is not rec and not rec2.closed and w.signup.create_thread.await_count == 2, "취소 뒤 새 /내전생성")
    await run(mod.join, 300, A)
    task = rec2.task
    await run(mod.cancel, 100, ADMIN)
    await asyncio.sleep(0)
    check(rec2.cancelled and task.cancelled() and w.texts(w.thread.send)[-1].endswith("<@11>"), "모집 중 /취소 → 자동 마감도 중지")
    check("clear" not in w.pushed, "서버에 올린 적이 없으면 명단 비우기도 없음")

    # 마감과 자동 마감이 동시에 와도 명단은 한 번만 나간다
    w = World(mod, forum=True)
    await run(mod.create_inhouse, 100, ADMIN)
    rec = mod.bot.current
    await run(mod.join, 300, A)
    mod.stop_timer(rec)
    rec.end_ts = time.time()
    rec.task = asyncio.create_task(mod.close_when_due(rec))
    await asyncio.gather(run(mod.close_now, 100, ADMIN), asyncio.sleep(0.2))
    check(len([x for x in w.texts(w.thread.send) if "내전 참여 명단" in x]) == 1, "/마감과 자동 마감이 겹쳐도 명단은 한 번")

    # 태그가 필수인 포럼, 글 올리기 실패
    w = World(mod, forum=True)
    w.signup.flags = Mock(require_tag=True)
    w.signup.available_tags = ["태그1", "태그2"]
    await run(mod.create_inhouse, 100, ADMIN)
    check(w.signup.create_thread.call_args.kwargs.get("applied_tags") == ["태그1"], "태그 필수 포럼이면 첫 태그 사용")
    mod.stop_timer(mod.bot.current)
    w = World(mod, forum=True)
    w.signup.create_thread = AsyncMock(side_effect=discord.HTTPException(Mock(status=403, reason="Forbidden"), "Missing Permissions"))
    t, _ = await run(mod.create_inhouse, 100, ADMIN)
    check("모집 글을 올리지 못했어요" in t and mod.bot.current is None, "글 올리기 실패 시 안내, 모집은 만들어지지 않음")
    w = World(mod, forum=True)
    w.thread.edit = AsyncMock(side_effect=discord.HTTPException(Mock(status=403, reason="Forbidden"), "Missing Permissions"))
    await run(mod.create_inhouse, 100, ADMIN)
    await run(mod.join, 300, A)
    t, _ = await run(mod.close_now, 100, ADMIN)
    check("마감했어요" in t and mod.bot.current.closed, "잠금 권한이 없어도 마감은 끝까지 진행")

    # ── 서버 연결을 쓸 때 ──
    w = World(mod, forum=True, sync=True)
    await run(mod.create_inhouse, 100, ADMIN)
    rec = mod.bot.current
    await run(mod.join, 300, A)
    await run(mod.close_now, 100, ADMIN)
    check(w.pushed == [[11]] and rec.synced and any("리그 서버에 명단을 올렸습니다" in x for x in w.texts(w.admin.send)), "마감 때 서버에 명단 올림")
    await run(mod.extend, 100, ADMIN)
    check(w.pushed == [[11], "clear"] and not rec.synced, "다시 열면 서버의 명단 비움")
    await run(mod.join, 300, B)
    await run(mod.close_now, 100, ADMIN)
    await run(mod.cancel, 100, ADMIN)
    check(w.pushed == [[11], "clear", [11, 12], "clear"], "다시 마감하면 새 명단, 취소하면 비움")

    # ── 일반 채팅 채널 ──
    w = World(mod, forum=False)
    t, _ = await run(mod.create_inhouse, 100, ADMIN)
    rec = mod.bot.current
    check(rec.thread is None and w.signup.send.await_count == 1 and "까지** 참여 신청" in w.signup.send.call_args.args[0], "일반 채널이면 공지 메시지")
    t, _ = await run(mod.join, 300, A)
    check(t == "<#200> 에서 입력해 주세요.", "일반 채널: 다른 곳의 /참여 는 채널로 안내")
    for n in range(12):
        await run(mod.join, 200, user(100 + n, f"선수{n}"))
    await run(mod.extend, 100, ADMIN)
    t, _ = await run(mod.close_now, 100, ADMIN)
    msgs = w.texts(w.signup.send)
    check(len(rec.participants) == 12 and "인원이 모였어요" in msgs[-1] and "12. <@111>" in msgs[-1], "일반 채널: 12명 마감 명단")
    check(not any("`/연장` 으로" in x for x in w.texts(w.admin.send)), "인원이 차면 연장 안내 없음")
    await run(mod.extend, 100, ADMIN)
    check(not rec.closed, "일반 채널: 마감 뒤 /연장")
    await run(mod.cancel, 100, ADMIN)
    check(rec.cancelled and "취소됐어요" in w.texts(w.signup.send)[-1], "일반 채널: /취소")

    # ── 켤 때 채널·권한 확인 ──
    import contextlib
    import io

    async def startup(world):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            await mod.check_setup()
        return buf.getvalue().splitlines()

    def named(ch, name, **perms):
        ch.name = name
        ch.guild = Mock()
        ch.permissions_for = Mock(return_value=Mock(**perms))

    w = World(mod, forum=True)
    named(w.admin, "운영진", view_channel=True, send_messages=True)
    named(w.signup, "내전모집", view_channel=True, send_messages=True, send_messages_in_threads=True, manage_threads=True)
    out = await startup(w)
    check(out[:2] == ["관리자 채널: #운영진 (일반 채널) - 권한 확인", "참여 신청 채널: #내전모집 (포럼) - 권한 확인"], "켤 때 확인: 정상")
    check(out[2] == "자동 팀 편성: 꺼짐 (테스트)", "켤 때 확인: 자동 팀 편성 상태")
    check(real_problem().startswith("꺼짐 (config.json 에 sync_url"), "서버 연결 설정이 없으면 자동 팀 편성은 꺼짐")
    named(w.signup, "내전모집", view_channel=True, send_messages=False, send_messages_in_threads=True, manage_threads=False)
    out = await startup(w)
    check(out[1] == "참여 신청 채널: #내전모집 (포럼) [확인 필요] 봇에 없는 권한: 글 올리기, 스레드 관리(글 잠그기)", "켤 때 확인: 없는 권한 안내")

    async def missing_channel(cid):
        raise discord.NotFound(Mock(status=404, reason="Not Found"), "Unknown Channel")

    mod.get_channel = missing_channel
    out = await startup(w)
    check(len(out) == 3 and out[0].startswith("[확인 필요] 관리자 채널(100)을 찾지 못했습니다."), "켤 때 확인: 채널을 못 찾을 때")

    # ── 마감 시각을 정해서 만들기 ──
    kst = lambda *a: int(datetime(*a, tzinfo=KST).timestamp())
    check(mod.parse_deadline("2026-10-07-21-30") == kst(2026, 10, 7, 21, 30) and mod.parse_deadline(" 2027-01-01-00-00 ") == kst(2027, 1, 1, 0, 0), "마감 시각 읽기 (한국 시간)")
    wrong = ["2026-10-07 21:30", "2026-10-7-21-30", "26-10-07-21-30", "2026-10-07-21", "2026-13-01-00-00", "2026-02-30-10-00", "2026-10-07-24-00", "2026-10-07-21-60", "내일 9시", "2026-10-07-21-30-00"]
    check(all(mod.parse_deadline(x) is None for x in wrong), "형식이 다르거나 없는 날짜·시각은 읽지 않는다")
    today = datetime.now(KST)
    noon = int(today.replace(hour=12, minute=0, second=0, microsecond=0).timestamp())
    check(real_when(noon) == f"<t:{noon}:t>" and real_when(noon + 86400) == f"<t:{noon + 86400}:f>", "마감이 오늘이면 시각만, 다른 날이면 날짜까지 보여 준다")

    w = World(mod, forum=True)
    later = datetime.now(KST) + timedelta(days=2)
    text = f"{later:%Y-%m-%d}-21-30"
    want = kst(later.year, later.month, later.day, 21, 30)
    t, _ = await run(mod.create_inhouse, 100, ADMIN, text)
    rec = mod.bot.current
    kw = w.signup.create_thread.call_args.kwargs
    check(rec is not None and rec.end_ts == want and f"<t:{want}:t>까지** 참여 신청" in kw["content"], "/내전생성 마감 시각 → 그 시각에 마감")
    check(kw["name"] == f"{later.month}월 {later.day}일({'월화수목금토일'[later.weekday()]}) 21:30 내전 모집", "글 제목에 정한 시각: " + kw["name"])
    check(f"<t:{want}:t>" in t and not rec.task.done(), "운영진에게 마감 시각 안내, 그때까지 기다림")
    await run(mod.cancel, 100, ADMIN)
    for bad, why in (("2026-10-07 21:30", "형식이 맞지 않아"), ("2020-01-01-00-00", "이미 지난 시각"), ("오늘 밤", "형식이 맞지 않아")):
        w = World(mod, forum=True)
        t, _ = await run(mod.create_inhouse, 100, ADMIN, bad)
        check(why in t and mod.bot.current is None and w.signup.create_thread.await_count == 0, f"/내전생성 {bad} → 만들지 않음")
    w = World(mod, forum=True)
    before = time.time()
    await run(mod.create_inhouse, 100, ADMIN, "  ")
    check(mod.bot.current is not None and 300 <= mod.bot.current.end_ts - before <= 361, "마감 시각을 비우면 5분 뒤")
    await run(mod.cancel, 100, ADMIN)

    # ── 봇을 껐다 켜도 이어 가기 ──
    w = World(mod, forum=True)
    await run(mod.create_inhouse, 100, ADMIN)
    await run(mod.join, 300, A)
    await run(mod.join, 300, B)
    rec = mod.bot.current
    saved = json.loads(mod.STATE_PATH.read_text(encoding="utf-8"))
    check(saved["current"]["participants"] == [[11, "가", "u11"], [12, "나*별", "u12"]] and saved["current"]["thread_id"] == 300 and not saved["current"]["closed"], "모집 상태를 파일에 적어 둔다")
    mod.stop_timer(rec)
    mod.bot.current = None                                   # 봇이 꺼졌다 켜진 것처럼
    await mod.restore_state()
    back = mod.bot.current
    check(back is not rec and list(back.participants) == [11, 12] and back.end_ts == rec.end_ts and back.thread is w.thread and back.host_id == 1, "켜면 하던 모집을 이어받는다")
    check(back.task is not None and not back.task.done(), "이어받은 모집도 마감 시각을 기다린다")
    t, _ = await run(mod.join, 300, C)
    check(list(back.participants) == [11, 12, 13] and "참여자 (3명)" in w.message.edit.call_args.kwargs["content"], "이어받은 모집에 /참여")
    await run(mod.close_now, 100, ADMIN)
    mod.bot.current = None
    await mod.restore_state()
    check(mod.bot.current.closed and mod.bot.current.task is None, "마감한 모집도 이어받는다 (자동 마감은 다시 걸지 않음)")
    t, _ = await run(mod.extend, 100, ADMIN)
    check("다시 열었어요" in t and not mod.bot.current.closed, "이어받은 뒤 /연장")
    await run(mod.cancel, 100, ADMIN)

    w = World(mod, forum=True)                               # 꺼져 있는 사이에 마감 시각이 지난 경우
    await run(mod.create_inhouse, 100, ADMIN)
    await run(mod.join, 300, A)
    rec = mod.bot.current
    mod.stop_timer(rec)
    rec.end_ts = int(time.time()) - 60
    mod.save_state()
    mod.bot.current = None
    await mod.restore_state()
    await asyncio.sleep(0.4)
    check(mod.bot.current.closed and any("내전 참여 명단" in x for x in w.texts(w.thread.send)), "꺼진 사이 마감 시각이 지났으면 켜자마자 마감")
    mod.STATE_PATH.write_text("깨진 파일", encoding="utf-8")
    mod.bot.current = None
    await mod.restore_state()
    check(mod.bot.current is None, "상태 파일이 깨져 있으면 새로 시작")

    # ── 자동 팀 편성 ──
    FIRSTS = [1, 1, 2, 2, 3, 3, 4, 4, 4, 4, 1, 2]

    def league_of(n):
        players = []
        for k in range(n):
            f = FIRSTS[k]
            players.append({"id": f"p{k}", "name": f"선수{k}", "baseMMR": 3000 + k * 150, "mmr": 3000 + k * 150,
                            "prefs": [f] + [x for x in (1, 2, 3, 4) if x != f], "wins": 2, "losses": 2, "streak": 0,
                            "roleCount": [0, 0, 0, 0, 0], "discord": f"u{100 + k}", "steam": ""})
        players[0]["discord"] = "100"                         # 디스코드 사용자 ID로 등록한 선수
        players[1]["discord"] = ""                            # 디스코드를 적지 않아 이름으로 맞추는 선수
        return {"players": players, "matches": [], "settings": {}}

    async def gather(world, n, extra=()):
        await run(mod.create_inhouse, 100, ADMIN)
        for k in range(n):
            await run(mod.join, 300, user(100 + k, f"선수{k}"))
        for u in extra:
            await run(mod.join, 300, u)
        return mod.bot.current

    # 가짜 편성. 래디언트 MMR 3000~3400, 다이어 3100·3150·3200·3250·3300 (3번 자리는 서로 같고 둘 다 2지망)
    def fake_result(ids, bench=()):
        def seat(pid, side, k):
            mine = side == "r"
            return {"id": pid, "name": side.upper() + pid, "mmr": 3000 + 100 * k + (0 if mine else 50 * (2 - k)), "rank": 1 if k == 2 else 0,
                    "win": (18 if mine else 22) + k, "lose": -((22 if mine else 18) + k)}
        return {"ok": True,
                "lanes": [{"role": k + 1, "r": seat(ids[k], "r", k), "d": seat(ids[k + 5], "d", k)} for k in range(5)],
                "bench": [{"id": b, "name": "B" + b} for b in bench],
                "stats": {"rawR": 3500, "rawD": 3480, "sR": 3510, "sD": 3470, "diff": 40, "lead": "r", "chanceR": 52, "below": 0, "firsts": 8,
                          "sides": [{"lane": "탑", "r": 6500, "d": 6400, "rRoles": [3, 4], "dRoles": [1, 5]},
                                    {"lane": "봇", "r": 6400, "d": 6450, "rRoles": [1, 5], "dRoles": [3, 4]}]}}
    asked = []

    async def fake_matchmaker(payload):
        asked.append(payload)
        league = payload["league"]
        if payload.get("mode") == "result":                  # 이긴 팀은 +20, 진 팀은 −20
            mid = "m%d" % (len(league["matches"]) + 1)
            gain = lambda side: 20 if side == payload["winner"] else -20
            changes = [{"id": l[side], "name": side.upper() + l[side], "side": side, "role": k + 1, "before": 3000, "delta": gain(side), "after": 3000 + gain(side)}
                       for k, l in enumerate(payload["lanes"]) for side in ("r", "d")]
            return {"ok": True, "league": dict(league, matches=[{"id": mid}] + league["matches"]), "match": {"id": mid, "at": "", "winner": payload["winner"]}, "changes": changes}
        if payload.get("mode") == "undo":
            if not league["matches"] or league["matches"][0]["id"] != payload["matchId"]:
                return {"ok": False, "error": "그 뒤에 다른 경기가 기록돼 있어 되돌리지 않았습니다"}
            return {"ok": True, "league": dict(league, matches=league["matches"][1:]), "match": league["matches"][0], "changes": []}
        ids = payload["participants"]
        return fake_result(ids[:10], ids[10:])

    real_matchmaker = mod.run_matchmaker
    mod.run_matchmaker = fake_matchmaker

    w = World(mod, forum=True, league=league_of(12))
    stranger = user(999, "미등록")
    rec = await gather(w, 12, extra=[stranger])
    t, _ = await run(mod.close_now, 100, ADMIN)
    posts = w.texts(w.thread.send)
    lineup = posts[-1]
    check(len(asked) == 1 and sorted(asked[0]["participants"]) == sorted(f"p{k}" for k in range(12)) and asked[0]["busy"] == [], "마감하면 선수단과 맞는 참가자로 팀 편성을 요청")
    check("내전 참여 명단" in posts[-2] and lineup.startswith("⚔️ **팀 편성**"), "명단 공지 다음에 팀 편성 공지")
    check("🟢 **래디언트** · 평균 MMR **3510** (그대로 계산하면 3500)" in lineup and "🔴 **다이어** · 평균 MMR **3470** (그대로 계산하면 3480)" in lineup,
          "팀마다 평균 MMR (매니저와 같은 계산 값과 그대로 낸 값)")
    check("`1 캐리` Rp0 <@100> · 3000 · 1지망" in lineup and "`3 오프` Rp2 <@102> · 3200 · 2지망" in lineup and "`5 서폿` Dp9 <@109> · 3300 · 1지망" in lineup
          and lineup.count("<@") == 13, "자리마다 선수 이름, 디스코드 계정, 인하우스 MMR, 몇 지망인지")
    check("🪑 이번 판은 쉬어요: Bp10 <@110>, Bp11 <@111>" in lineup and "등록이 확인되지 않아 팀에서 빠졌어요: <@999>" in lineup, "쉬는 사람과 등록되지 않은 참가자 안내")
    check("총 판수가 적은 사람이 먼저" in lineup and lineup.index("🪑") < lineup.index("⚠️") < lineup.index("📊"), "출전 순서 안내, 그리고 MMR 비교는 맨 아래")
    check("`팀 평균` 3510 대 3470 · 🟢 +40" in lineup, "MMR 비교: 팀 평균 차이와 앞선 팀")
    check(all(row in lineup for row in ("`1 캐리` 3000 대 3100 · 🔴 +100", "`2 미드` 3100 대 3150 · 🔴 +50", "`3 오프` 3200 대 3200 · 같음",
                                         "`4 서폿` 3300 대 3250 · 🟢 +50", "`5 서폿` 3400 대 3300 · 🟢 +100")), "MMR 비교: 같은 자리끼리의 차이")
    check("`탑 라인` 6500 대 6400 · 🟢 +100 (래디언트 3·4번 대 다이어 1·5번의 합)" in lineup
          and "`봇 라인` 6400 대 6450 · 🔴 +50 (래디언트 1·5번 대 다이어 3·4번의 합)" in lineup, "MMR 비교: 라인에서 만나는 두 사람의 합")
    check("🎯 **기대 승률** 🟢 52% · 🔴 48%" in lineup and "🟢 래디언트: 이기면 MMR +18~+22 · 지면 −22~−26" in lineup
          and "🔴 다이어: 이기면 MMR +22~+26 · 지면 −18~−22" in lineup, "기대 승률과 이기면·지면 바뀌는 MMR")
    check(len(lineup) < 2000 and len(posts) == 2, "보통은 메시지 하나에 다 들어간다")

    # 쉬는 사람이 아주 많아 글이 길어지면 여러 메시지로 나눠 보낸다 (디스코드는 2000자가 넘는 메시지를 받지 않는다)
    crowd = [f"p{k}" for k in range(10, 130)]
    long_text = mod.lineup_text(fake_result([f"p{k}" for k in range(10)], crowd), {f"p{k}": 10**17 + k for k in range(130)}, [])
    parts = mod.split_message(long_text)
    joined = "\n".join(parts)
    check(len(long_text) > 4000 and len(parts) > 2 and all(len(p) <= mod.MESSAGE_LIMIT for p in parts), "긴 글은 한도에 맞게 나눈다")
    check(parts[0].startswith("⚔️ **팀 편성**") and joined.index("🔴 **다이어**") < joined.index("🪑") < joined.index("📊") and "🎯 **기대 승률**" in parts[-1],
          "나눠도 순서는 그대로")
    check(all(f"Bp{k} <@{10**17 + k}>" in joined for k in range(10, 130)) and sum(p.count("<@") for p in parts) == 130
          and all(p.count("<@") == p.count(">") for p in parts), "한 줄이 한도를 넘으면 쉼표에서 끊어, 이름과 멘션이 중간에 잘리지 않는다")
    sent = w.thread.send.call_count
    await mod.post(rec, long_text, quiet=True)
    check(w.texts(w.thread.send)[sent:] == parts, "나눈 순서대로 보낸다")
    check(mod.split_message("짧은 글") == ["짧은 글"] and mod.split_message("가" * 4000) == ["가" * 1900, "가" * 1900, "가" * 200], "짧은 글은 그대로, 끊을 곳이 없으면 글자 수로")
    paras = "\n\n".join(["나" * 900] * 3)
    check(mod.split_message(paras) == ["나" * 900 + "\n\n" + "나" * 900, "나" * 900], "되도록 빈 줄에서 끊는다")
    check(w.thread.send.call_args.kwargs.get("allowed_mentions") is not None, "팀 편성 공지는 알림을 다시 울리지 않는다")
    pushed = [p for p in w.server if p["action"] == "pushLineup"]
    check(len(pushed) == 1 and [l["role"] for l in pushed[0]["lineup"]["lanes"]] == [1, 2, 3, 4, 5] and pushed[0]["lineup"]["lanes"][0] == {"role": 1, "r": "p0", "d": "p5"}
          and pushed[0]["lineup"]["bench"] == ["p10", "p11"] and pushed[0]["lineup"]["post"] == w.message.jump_url, "짠 팀을 서버에 올린다")
    check(any("봇이 짠 팀 불러오기" in x and "⚔️ **팀 편성**" in x for x in w.texts(w.admin.send)), "관리자 채널에도 편성과 다음 할 일 안내")
    check(rec.lineup and len(mod.bot.lineups) == 1 and len(mod.bot.lineups[0]["ids"]) == 10, "오늘 짠 팀을 기억한다")

    await run(mod.extend, 100, ADMIN)                        # 다시 열면 짠 팀은 없던 일
    check(not rec.lineup and mod.bot.lineups == [] and w.server[-1] == {"action": "pushLineup", "lineup": None}, "다시 열면 짠 팀을 서버에서 비운다")
    await run(mod.close_now, 100, ADMIN)
    check(rec.lineup and len(asked) == 2 and len(mod.bot.lineups) == 1, "다시 마감하면 팀도 다시 짠다")
    first_ten = list(mod.bot.lineups[0]["ids"])

    w.message.id = 301                                       # 다음 판은 다른 모집 글이다
    await run(mod.create_inhouse, 100, ADMIN)                # 같은 날 다음 판: 앞 판에 뛴 사람을 오늘 뛴 사람으로 넘긴다
    for k in range(12):
        await run(mod.join, 300, user(100 + k, f"선수{k}"))
    await run(mod.close_now, 100, ADMIN)
    check(len(asked) == 3 and asked[2]["busy"] == sorted(first_ten) and len(mod.bot.lineups) == 2, "아직 기록하지 않은 앞 판에 뛴 사람을 오늘 뛴 사람으로 넘긴다")
    await run(mod.cancel, 100, ADMIN)
    check(len(mod.bot.lineups) == 1 and w.server[-1] == {"action": "pushLineup", "lineup": None}, "취소하면 그 판의 팀만 지운다")

    w = World(mod, forum=True, league=league_of(12))
    await gather(w, 9, extra=[stranger])                     # 열 명이 왔지만 등록된 선수는 아홉
    n = len(asked)
    await run(mod.close_now, 100, ADMIN)
    check(len(asked) == n and "선수 등록이 확인된 참가자가 9명" in w.texts(w.thread.send)[-1] and any("선수단에 없는 참가자: <@999>" in x for x in w.texts(w.admin.send)), "등록된 선수가 열 명이 안 되면 짜지 않고 알린다")

    w = World(mod, forum=True, league=league_of(12))
    w.league = None
    await gather(w, 10)
    await run(mod.close_now, 100, ADMIN)
    check(len(asked) == n and any("서버에 리그 기록이 없어" in x for x in w.texts(w.admin.send)) and not any("팀 편성" in x for x in w.texts(w.thread.send)), "서버에 리그 기록이 없으면 관리자에게 알린다")

    w = World(mod, forum=True, league=league_of(12))
    w.fail.add("adminLeague")
    await gather(w, 10)
    t, _ = await run(mod.close_now, 100, ADMIN)
    check("마감했어요" in t and any("기록을 받지 못해" in x for x in w.texts(w.admin.send)), "서버가 답하지 않아도 마감은 끝까지 진행")

    w = World(mod, forum=True, league=league_of(12))
    w.fail.add("pushLineup")
    rec = await gather(w, 10)
    await run(mod.close_now, 100, ADMIN)
    check(rec.lineup and any("리그 서버에 올리지 못해서" in x for x in w.texts(w.admin.send)) and w.texts(w.thread.send)[-1].startswith("⚔️"), "짠 팀을 서버에 못 올려도 디스코드에는 공지")

    async def broken(payload):
        raise RuntimeError("node 없음")

    mod.run_matchmaker = broken
    w = World(mod, forum=True, league=league_of(12))
    rec = await gather(w, 10)
    t, _ = await run(mod.close_now, 100, ADMIN)
    check("마감했어요" in t and not rec.lineup and any("팀을 자동으로 짜지 못했습니다" in x and "node 없음" in x for x in w.texts(w.admin.send)), "팀 편성이 실패하면 관리자에게 알리고 넘어간다")

    w = World(mod, forum=True, league=league_of(12))         # 아홉 명이면 팀을 짜려 하지 않는다
    await gather(w, 9)
    await run(mod.close_now, 100, ADMIN)
    check(not any(p["action"] == "adminLeague" for p in w.server), "열 명이 안 되면 리그 기록도 묻지 않는다")

    # ── 경기 결과 기록: /승리, /승리취소 ──
    mod.run_matchmaker = fake_matchmaker
    w = World(mod, forum=True, league=league_of(12))
    t, _ = await run(mod.record_win, 100, ADMIN, "r")
    check("결과를 기록할 팀이 없어요" in t and not any(p["action"] == "saveLeague" for p in w.server), "팀을 짜기 전의 /승리")
    t, _ = await run(mod.undo_win, 100, ADMIN)
    check("되돌릴 결과가 없어요" in t, "기록한 결과가 없을 때의 /승리취소")
    t, _ = await run(mod.record_win, 300, ADMIN, "r")
    check("관리자 채널에서만" in t, "다른 채널의 /승리 거절")
    t, _ = await run(mod.undo_win, 300, ADMIN)
    check("관리자 채널에서만" in t, "다른 채널의 /승리취소 거절")

    rec = await gather(w, 10)
    await run(mod.close_now, 100, ADMIN)
    entry = mod.bot.lineups[0]
    check(entry["lanes"][0] == {"role": 1, "r": "p0", "d": "p5"} and entry["who"]["p0"] == 100 and entry["place_id"] == 300 and entry["result"] is None, "짠 팀을 결과 기록에 쓸 수 있게 적어 둔다")
    t, i = await run(mod.record_win, 100, ADMIN, "r")
    check(asked[-1]["mode"] == "result" and asked[-1]["winner"] == "r" and asked[-1]["lanes"] == entry["lanes"] and len(asked[-1]["league"]["players"]) == 12, "/승리 → 공지한 팀 그대로 정산")
    saves = [p for p in w.server if p["action"] == "saveLeague"]
    check(len(saves) == 1 and saves[0]["baseRev"] == 1 and w.rev == 2 and w.league["matches"] == [{"id": "m1"}], "정산한 기록을 서버에 올린다 (보고 고친 번호와 함께)")
    shown = w.texts(w.thread.send)[-1]
    check(shown.startswith("🏆 **래디언트 승리!**") and "🟢 **래디언트** · 승\n" in shown and "🔴 **다이어**\n" in shown, "모집 글에 경기 결과")
    check("`1 캐리` Rp0 <@100>  3000 → **3020** (+20)" in shown and "`5 서폿` Dp9 <@109>  3000 → **2980** (−20)" in shown, "선수별 MMR 변동")
    check(w.thread.send.call_args.kwargs.get("allowed_mentions") is not None and shown in t and "/승리취소" in t and i.followup.send.call_args.kwargs.get("allowed_mentions") is not None,
          "결과 공지는 알림을 울리지 않고, 운영진에게 되돌리는 방법도 알린다")
    check(entry["result"] == {"winner": "r", "match_id": "m1"} and json.loads(mod.STATE_PATH.read_text(encoding="utf-8"))["lineups"][0]["result"]["winner"] == "r", "기록한 결과를 적어 둔다")
    t, _ = await run(mod.record_win, 100, ADMIN, "d")
    check("결과를 기다리는 팀이 없어요" in t and "/승리취소" in t and w.rev == 2, "같은 판을 두 번 기록하지 않는다")
    t, _ = await run(mod.extend, 100, ADMIN)
    check("이미 경기 결과를 기록한 내전" in t and rec.closed and rec.lineup, "결과를 기록한 내전은 다시 열지 않는다")
    t, _ = await run(mod.cancel, 100, ADMIN)
    check("이미 경기 결과를 기록한 내전" in t and not rec.cancelled, "결과를 기록한 내전은 취소하지 않는다")

    t, _ = await run(mod.undo_win, 100, ADMIN)
    check(asked[-1]["mode"] == "undo" and asked[-1]["matchId"] == "m1" and entry["result"] is None and w.rev == 3 and w.league["matches"] == [], "/승리취소 → 그 경기를 되돌려 서버에 올린다")
    check("결과 기록을 취소" in t and "경기 결과 기록을 취소했어요" in w.texts(w.thread.send)[-1], "되돌린 것을 모집 글과 운영진에게 알린다")
    t, _ = await run(mod.record_win, 100, ADMIN, "d")
    check(t.startswith("🏆 **다이어 승리!**") and "🔴 **다이어** · 승" in t and entry["result"]["winner"] == "d" and "`1 캐리` Dp5 <@105>  3000 → **3020** (+20)" in t, "되돌린 뒤 다시 기록")

    mod.bot.current, mod.bot.lineups = None, []              # 봇이 꺼졌다 켜져도 결과 기록 여부를 기억한다
    await mod.restore_state()
    check(len(mod.bot.lineups) == 1 and mod.bot.lineups[0]["result"]["winner"] == "d" and mod.bot.lineups[0]["who"]["p0"] == 100, "껐다 켜도 짠 팀과 기록한 결과를 기억한다")
    t, _ = await run(mod.undo_win, 100, ADMIN)
    check("결과 기록을 취소" in t and mod.bot.lineups[0]["result"] is None, "껐다 켠 뒤에도 /승리취소")
    t, _ = await run(mod.record_win, 100, ADMIN, "r")
    check(t.startswith("🏆 **래디언트 승리!**"), "껐다 켠 뒤에도 /승리")

    w = World(mod, forum=True, league=league_of(12))         # 결과를 기록하지 않고 다음 판을 만들면 알려 준다
    await gather(w, 10)
    await run(mod.close_now, 100, ADMIN)
    w.message.id = 301
    t, _ = await run(mod.create_inhouse, 100, ADMIN)
    check("결과를 아직 기록하지 않은 판" in t and "/승리" in t, "앞 판의 결과가 없으면 다음 /내전생성 때 알린다")
    t, _ = await run(mod.record_win, 100, ADMIN, "r")
    check(t.startswith("🏆") and mod.bot.lineups[0]["result"]["winner"] == "r", "다음 모집이 열려 있어도 앞 판의 결과를 기록한다")
    await run(mod.cancel, 100, ADMIN)
    t, _ = await run(mod.create_inhouse, 100, ADMIN)
    check("결과를 아직 기록하지 않은 판" not in t, "결과를 모두 기록했으면 알리지 않는다")
    await run(mod.cancel, 100, ADMIN)

    w = World(mod, forum=True, league=league_of(12))         # 봇이 기록을 받아 간 사이에 매니저가 기록을 바꾼 경우
    await gather(w, 10)
    await run(mod.close_now, 100, ADMIN)
    w.conflicts = 1
    t, _ = await run(mod.record_win, 100, ADMIN, "r")
    got = [p for p in w.server if p["action"] in ("adminLeague", "saveLeague")]
    check(t.startswith("🏆") and [p["action"] for p in got[-4:]] == ["adminLeague", "saveLeague", "adminLeague", "saveLeague"] and got[-1]["baseRev"] == 2 and w.rev == 3,
          "그사이 서버 기록이 바뀌었으면 새 기록을 받아 다시 정산한다")

    w = World(mod, forum=True, league=league_of(12))
    await gather(w, 10)
    await run(mod.close_now, 100, ADMIN)
    w.fail.add("saveLeague")
    t, _ = await run(mod.record_win, 100, ADMIN, "r")
    check("결과를 기록하지 못했어요" in t and "서버 오류" in t and mod.bot.lineups[0]["result"] is None and not w.texts(w.thread.send)[-1].startswith("🏆"), "서버에 올리지 못하면 기록하지 않은 것으로 둔다")
    w.fail.clear()
    w.league = dict(w.league, players=w.league["players"][:5])

    async def refusing(payload):
        return {"ok": False, "error": "팀에 있던 선수 5명이 지금 선수단에 없습니다. 매니저에서 기록해 주세요"}

    mod.run_matchmaker = refusing
    t, _ = await run(mod.record_win, 100, ADMIN, "r")
    check("결과를 기록하지 못했어요" in t and "선수단에 없습니다" in t and mod.bot.lineups[0]["result"] is None, "정산할 수 없으면 까닭을 알린다")

    # 실제 Node 와 실제 매니저 파일로 끝까지
    mod.run_matchmaker = real_matchmaker
    mod.MATCHMAKER = SRC.parent / "matchmaker.js"
    mod.MANAGER_FILE = SRC.parent.parent / "manager" / "InhouseLeagueManager_v0_18.html"
    if shutil.which(mod.NODE_PATH) is None:
        print("skip 실제 팀 편성 (Node 가 없어 건너뜀)")
    else:
        w = World(mod, forum=True, league=league_of(12))
        rec = await gather(w, 12)
        await run(mod.close_now, 100, ADMIN)
        lineup = w.texts(w.thread.send)[-1]
        seats = re.findall(r"`(\d) (캐리|미드|오프|서폿)` (선수\d+) <@(\d+)> · (\d+) · (\d)지망", lineup)
        check(lineup.startswith("⚔️ **팀 편성**") and len(seats) == 10 and len({s[2] for s in seats}) == 10, "실제 매니저 로직으로 열 명을 두 팀에 배치")
        check([s[0] for s in seats] == list("12345") * 2 and all(int(s[3]) - 100 == int(s[2][2:]) for s in seats), "자리 순서와 디스코드 계정이 맞다")
        check(all(int(s[4]) == 3000 + int(s[2][2:]) * 150 for s in seats), "선수마다 인하우스 MMR을 보여 준다")
        check(lineup.count("이번 판은 쉬어요") == 1 and len(re.findall(r"선수\d+ <@\d+>", lineup.split("쉬어요: ")[1].split("\n")[0])) == 2, "열두 명이면 두 명이 쉰다")
        check(len(w.server[-1]["lineup"]["lanes"]) == 5 and len(w.server[-1]["lineup"]["bench"]) == 2, "실제 편성을 서버에 올린다")
        rad, dire = [int(s[4]) for s in seats[:5]], [int(s[4]) for s in seats[5:]]
        gap = lambda r, d: "같음" if r == d else f"{'🟢' if r > d else '🔴'} +{abs(r - d)}"
        check(all(f"`{k + 1} {seats[k][1]}` {rad[k]} 대 {dire[k]} · {gap(rad[k], dire[k])}" in lineup for k in range(5)), "실제 편성: 같은 자리끼리의 MMR 차이")
        top, bottom = (rad[2] + rad[3], dire[0] + dire[4]), (rad[0] + rad[4], dire[2] + dire[3])
        check(f"`탑 라인` {top[0]} 대 {top[1]} · {gap(*top)} (래디언트 3·4번 대 다이어 1·5번의 합)" in lineup
              and f"`봇 라인` {bottom[0]} 대 {bottom[1]} · {gap(*bottom)} (래디언트 1·5번 대 다이어 3·4번의 합)" in lineup, "실제 편성: 라인에서 만나는 두 사람의 합")
        avg = re.search(r"`팀 평균` (\d+) 대 (\d+) · (🟢|🔴) \+(\d+)", lineup)
        odds = re.search(r"기대 승률\*\* 🟢 (\d+)% · 🔴 (\d+)%", lineup)
        check(avg and abs(abs(int(avg[1]) - int(avg[2])) - int(avg[4])) <= 1 and (avg[3] == "🟢") == (int(avg[1]) > int(avg[2]))
              and f"평균 MMR **{avg[1]}** (그대로 계산하면 {round(sum(rad) / 5)})" in lineup, "실제 편성: 팀 평균과 그 차이")
        check(odds and int(odds[1]) + int(odds[2]) == 100 and (int(odds[1]) >= 50 if avg[3] == "🟢" else int(odds[1]) <= 50), "실제 편성: 기대 승률은 평균이 높은 팀이 높다 (차이가 작으면 반올림해 50%)")
        told = {side: [int(x) for x in re.search(rf"{side}: 이기면 MMR \+(\d+)~\+(\d+) · 지면 −(\d+)~−(\d+)", lineup).groups()] for side in ("래디언트", "다이어")}

        start = json.dumps(league_of(12), ensure_ascii=False, sort_keys=True)
        entry = mod.bot.lineups[0]
        t, _ = await run(mod.record_win, 100, ADMIN, "d")
        after = w.league
        mmr = {p["id"]: p for p in after["players"]}
        won, lost = [l["d"] for l in entry["lanes"]], [l["r"] for l in entry["lanes"]]
        check(t.startswith("🏆 **다이어 승리!**") and len(after["matches"]) == 1 and after["matches"][0]["winner"] == "d" and len(after["matches"][0]["rows"]) == 10, "실제 정산: 경기가 기록된다")
        check(all(mmr[i]["wins"] == 3 and mmr[i]["mmr"] > 3000 + int(i[1:]) * 150 for i in won) and all(mmr[i]["losses"] == 3 and mmr[i]["mmr"] < 3000 + int(i[1:]) * 150 for i in lost),
              "실제 정산: 이긴 팀은 승과 MMR이 오르고 진 팀은 패와 MMR이 내린다")
        check(len(re.findall(r"\d+ → \*\*\d+\*\* \([+−]\d+\)", t)) == 10 and t.count("(+") == 5 and t.count("(−") == 5, "실제 정산: 열 명의 MMR 변동을 보여 준다")
        gains, drops = [int(x) for x in re.findall(r"\(\+(\d+)\)", t)], [int(x) for x in re.findall(r"\(−(\d+)\)", t)]
        check([min(gains), max(gains)] == told["다이어"][:2] and [min(drops), max(drops)] == told["래디언트"][2:], "실제 정산: 팀을 짤 때 알린 이기면·지면 범위와 같다")
        bench = [p["id"] for p in after["players"] if p["id"] not in won + lost]
        check(len(bench) == 2 and all(mmr[i]["wins"] == 2 and mmr[i]["losses"] == 2 for i in bench), "실제 정산: 쉰 사람의 전적은 그대로")
        t, _ = await run(mod.undo_win, 100, ADMIN)
        check("결과 기록을 취소" in t and json.dumps(w.league, ensure_ascii=False, sort_keys=True) == start, "실제 되돌리기: 기록하기 전과 똑같아진다")

    for task in asyncio.all_tasks() - {asyncio.current_task()}:
        task.cancel()
    shutil.rmtree(HERE, ignore_errors=True)
    print(f"\n실패 {failed}건")
    sys.exit(1 if failed else 0)


asyncio.run(main())
