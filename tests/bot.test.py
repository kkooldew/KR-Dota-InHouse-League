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
from datetime import datetime
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
    def __init__(self, mod, forum=True, sync=None):
        self.mod = mod
        self.thread = Mock()
        self.thread.id = 300
        self.thread.send = AsyncMock()
        self.thread.edit = AsyncMock()
        self.message = Mock()
        self.message.edit = AsyncMock()
        self.message.jump_url = "https://discord.com/channels/1/300/300"
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
        self.place = self.thread if forum else self.signup
        self.place_id = 300 if forum else 200

        async def get_channel(cid):
            return {100: self.admin, 200: self.signup}[cid]

        self.pushed = []

        async def push_roster(rec, clear=False):
            self.pushed.append("clear" if clear else list(rec.participants))
            return sync

        mod.get_channel = get_channel
        mod.push_roster = push_roster
        mod.bot.lock = asyncio.Lock()
        mod.bot.current = None

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


async def run(cmd, channel_id, u):
    i = inter(channel_id, u)
    await cmd.callback(i)
    return said(i), i


async def main():
    mod = load()
    KST = mod.KST
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
    check(out == ["관리자 채널: #운영진 (일반 채널) - 권한 확인", "참여 신청 채널: #내전모집 (포럼) - 권한 확인"], "켤 때 확인: 정상")
    named(w.signup, "내전모집", view_channel=True, send_messages=False, send_messages_in_threads=True, manage_threads=False)
    out = await startup(w)
    check(out[1] == "참여 신청 채널: #내전모집 (포럼) [확인 필요] 봇에 없는 권한: 글 올리기, 스레드 관리(글 잠그기)", "켤 때 확인: 없는 권한 안내")

    async def missing_channel(cid):
        raise discord.NotFound(Mock(status=404, reason="Not Found"), "Unknown Channel")

    mod.get_channel = missing_channel
    out = await startup(w)
    check(len(out) == 2 and out[0].startswith("[확인 필요] 관리자 채널(100)을 찾지 못했습니다."), "켤 때 확인: 채널을 못 찾을 때")

    for task in asyncio.all_tasks() - {asyncio.current_task()}:
        task.cancel()
    shutil.rmtree(HERE, ignore_errors=True)
    print(f"\n실패 {failed}건")
    sys.exit(1 if failed else 0)


asyncio.run(main())
