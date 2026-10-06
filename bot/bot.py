"""
도타 2 인하우스 내전 모집 봇

- 관리자 채널에서 /내전생성  → 참여 신청 채널에 모집 글을 올리고 모집 시작
  (참여 신청 채널이 포럼이면 내전마다 새 글을 만들고, 일반 채널이면 공지 메시지를 올림)
  · /내전생성 마감:2026-10-07-21-30 처럼 마감 시각(한국 시간)을 적으면 그 시각에 마감
  · 비우면 모집 시간(기본 5분) 뒤를 분 단위로 올림한 시각. 12:00:30 에 만들면 12:06:00 마감
- 모집 글(일반 채널이면 그 채널)에서 /참여, /참여취소
- 마감 시각이 되면 참여 명단을 공지하고, 리그 매니저와 같은 로직으로 팀을 짜서 알림 (matchmaker.js, Node 필요)
- 관리자 채널에서 /마감 (지금 인원으로 바로 마감), /연장 (마감을 5분 뒤로, 마감한 뒤에도 가능), /취소 (내전 취소)
- 관리자 채널에는 리그 매니저에 붙여넣을 명단(디스코드 ID·사용자명·별명)을 함께 올림
- 서버 주소(sync_url)와 운영진 키(sync_key)를 적어 두면, 명단과 짠 팀을 리그 서버에도 올려
  매니저의 "봇이 올린 명단 불러오기", "봇이 짠 팀 불러오기"로 바로 받을 수 있음
- 진행 중인 모집은 state.json 에 적어 두어, 봇을 껐다 켜도 이어짐

설정은 같은 폴더의 config.json 에서 바꿉니다. (config.example.json 을 복사해 만드세요)
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiohttp
import discord
from discord import app_commands

# ── 설정 불러오기 ─────────────────────────────────────────────
CONFIG_PATH = Path(__file__).with_name("config.json")
STATE_PATH = Path(__file__).with_name("state.json")  # 진행 중인 모집. 봇을 껐다 켜도 이어 가려고 적어 둔다
MATCHMAKER = Path(__file__).with_name("matchmaker.js")  # 리그 매니저의 팀 편성 로직을 그대로 실행한다
MANAGER_FILE = Path(__file__).resolve().parent.parent / "manager" / "InhouseLeagueManager_v0_18.html"
with CONFIG_PATH.open(encoding="utf-8-sig") as f:  # 메모장이 파일 앞에 붙이는 표시(BOM)가 있어도 읽는다
    config = json.load(f)

TOKEN = config["token"]
GUILD = discord.Object(id=int(config["guild_id"]))
ADMIN_CHANNEL_ID = int(config["admin_channel_id"])
SIGNUP_CHANNEL_ID = int(config["signup_channel_id"])
ADMIN_ROLE_ID = int(config.get("admin_role_id", 0))
SIGNUP_SECONDS = int(float(config.get("signup_minutes", 5)) * 60)
EXTEND_SECONDS = int(float(config.get("extend_minutes", 5)) * 60)
ANNOUNCEMENT = config["announcement"]
SYNC_URL = str(config.get("sync_url", "")).strip()
SYNC_KEY = str(config.get("sync_key", "")).strip()
AUTO_MATCH = bool(config.get("auto_match", True))  # 마감하면 팀을 짜서 알릴지 (sync_url·sync_key 와 Node 가 있어야 한다)
NODE_PATH = str(config.get("node_path", "") or "node").strip()
PLAYERS_NEEDED = 10  # 5 vs 5
KST = timezone(timedelta(hours=9))  # 마감 시각 입력과 모집 글 제목에 쓰는 한국 시간
DAY_STARTS_AT = 6  # 하루는 한국 시간 오전 6시에 바뀐다 (매니저의 팀 편성과 같은 기준)
ROLE_NAMES = ["캐리", "미드", "오프", "서폿", "서폿"]
DEADLINE_FORMAT = re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})")
DEADLINE_EXAMPLE = "`2026-10-07-21-30` (연-월-일-시-분, 한국 시간, 24시간제)"


# ── 모집 상태 ────────────────────────────────────────────────
class Recruitment:
    """내전 모집 1건. 마감한 뒤에도 /연장·/취소를 받을 수 있게 다음 모집이 생길 때까지 남겨 둔다."""

    def __init__(self, host_id: int, end_ts: int) -> None:
        self.host_id = host_id
        self.end_ts = end_ts
        # user_id -> {"name": 서버 별명, "username": 디스코드 사용자명}
        # dict 는 넣은 순서를 유지하므로 신청 순서가 보존됨
        self.participants: dict[int, dict[str, str]] = {}
        self.message: discord.Message | discord.PartialMessage | None = None  # 모집 글 본문(포럼) 또는 공지 메시지(일반 채널)
        self.thread: discord.Thread | None = None  # 참여 신청 채널이 포럼일 때 이 내전의 글
        self.task: asyncio.Task | None = None
        self.closed = False
        self.cancelled = False
        self.extended = False
        self.synced = False  # 리그 서버에 명단이 올라가 있는지
        self.lineup = False  # 팀을 짜서 알렸는지
        self.edit_lock = asyncio.Lock()

    @property
    def place_id(self) -> int:
        """참가자가 /참여 를 입력하는 곳: 포럼이면 모집 글, 일반 채널이면 그 채널"""
        return self.thread.id if self.thread else SIGNUP_CHANNEL_ID

    def to_dict(self) -> dict:
        return {
            "host_id": self.host_id,
            "end_ts": self.end_ts,
            "participants": [[uid, v["name"], v["username"]] for uid, v in self.participants.items()],
            "message_id": self.message.id if self.message else None,
            "thread_id": self.thread.id if self.thread else None,
            "closed": self.closed,
            "cancelled": self.cancelled,
            "extended": self.extended,
            "synced": self.synced,
            "lineup": self.lineup,
        }


class InhouseBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.current: Recruitment | None = None  # 모집 중이거나 가장 최근에 마감한 내전
        self.lock: asyncio.Lock | None = None
        # 오늘 짠 팀 [{"at": 시각, "ids": 선수 id, "message_id": 모집 글}]. 결과를 아직 기록하지 않은 판도 오늘 뛴 것으로 치는 데 쓴다
        self.lineups: list[dict] = []
        self.restored = False

    async def setup_hook(self) -> None:
        # 생성·마감·연장·취소가 겹치지 않게 한 번에 하나씩 처리한다
        self.lock = asyncio.Lock()
        # 서버 단위로 등록하면 슬래시 명령어가 즉시 반영됨
        await self.tree.sync(guild=GUILD)

    async def on_ready(self) -> None:
        print(f"로그인 완료: {self.user} (ID: {self.user.id})")
        await check_setup()
        if not self.restored:  # 연결이 끊겼다 다시 붙을 때는 다시 읽지 않는다
            self.restored = True
            async with self.lock:
                await restore_state()


bot = InhouseBot()


# ── 유틸 ────────────────────────────────────────────────────
async def get_channel(channel_id: int):
    channel = bot.get_channel(channel_id)
    if channel is None:
        channel = await bot.fetch_channel(channel_id)
    return channel


async def check_setup() -> None:
    """켤 때 채널 ID와 봇 권한을 확인해서, 고칠 곳이 있으면 모집을 시작하기 전에 알려 준다."""
    for label, channel_id in (("관리자 채널", ADMIN_CHANNEL_ID), ("참여 신청 채널", SIGNUP_CHANNEL_ID)):
        try:
            channel = await get_channel(channel_id)
        except discord.HTTPException as e:
            print(f"[확인 필요] {label}({channel_id})을 찾지 못했습니다. ID가 맞는지, 봇이 그 채널을 볼 수 있는지 확인하세요. ({e})")
            continue
        forum = isinstance(channel, discord.ForumChannel)
        wanted = {"view_channel": "채널 보기", "send_messages": "글 올리기" if forum else "메시지 보내기"}
        if forum:
            wanted.update(send_messages_in_threads="스레드에서 메시지 보내기", manage_threads="스레드 관리(글 잠그기)")
        perms = channel.permissions_for(channel.guild.me)
        missing = [name for attr, name in wanted.items() if not getattr(perms, attr)]
        print(f"{label}: #{channel.name} ({'포럼' if forum else '일반 채널'})"
              + (f" [확인 필요] 봇에 없는 권한: {', '.join(missing)}" if missing else " - 권한 확인"))
    print(f"자동 팀 편성: {match_problem() or '켜짐'}")


def match_problem() -> str:
    """자동 팀 편성을 할 수 없는 까닭. 할 수 있으면 빈 글."""
    if not AUTO_MATCH:
        return "꺼짐 (config.json 의 auto_match 가 false)"
    if not (SYNC_URL and SYNC_KEY):
        return "꺼짐 (config.json 에 sync_url 과 sync_key 가 있어야 합니다)"
    if shutil.which(NODE_PATH) is None:
        return "[확인 필요] Node 를 찾지 못했습니다. Node 를 설치하거나 config.json 의 node_path 를 확인하세요."
    if not (MATCHMAKER.exists() and MANAGER_FILE.exists()):
        return f"[확인 필요] {MATCHMAKER.name} 또는 리그 매니저 파일({MANAGER_FILE})이 없습니다."
    return ""


def is_admin(user: discord.abc.User) -> bool:
    if not isinstance(user, discord.Member):
        return False
    if user.guild_permissions.administrator:
        return True
    if ADMIN_ROLE_ID == 0:
        # 운영진 역할을 지정하지 않았으면 관리자 채널 접근 권한만으로 판단
        return True
    return any(role.id == ADMIN_ROLE_ID for role in user.roles)


def safe_name(name: str) -> str:
    """닉네임에 들어간 마크다운/멘션 문자가 공지를 깨뜨리지 않게 처리"""
    return discord.utils.escape_mentions(discord.utils.escape_markdown(name))


def minutes_text(seconds: int) -> str:
    return f"{seconds / 60:g}분"


def deadline_after(seconds: int, start: float | None = None) -> int:
    """start(기본: 지금)에서 seconds 초 뒤를 분 단위로 올림한 시각. 12:00:30 에 5분이면 12:06:00."""
    start = time.time() if start is None else start
    return math.ceil((start + seconds) / 60) * 60


def parse_deadline(text: str) -> int | None:
    """'2026-10-07-21-30'(한국 시간)을 마감 시각으로 읽는다. 형식이 다르거나 없는 날짜·시각이면 None."""
    m = DEADLINE_FORMAT.fullmatch(text.strip())
    if m is None:
        return None
    try:
        return int(datetime(*map(int, m.groups()), tzinfo=KST).timestamp())
    except ValueError:  # 13월, 25시 같은 값
        return None


def when(ts: int) -> str:
    """마감 시각 표시. 오늘이면 '오후 9:30', 다른 날이면 날짜까지. <t:…> 는 보는 사람의 시간대에 맞춰 보인다."""
    today = datetime.fromtimestamp(ts, KST).date() == datetime.now(KST).date()
    return f"<t:{ts}:t>" if today else f"<t:{ts}:f>"


def day_start(now: float | None = None) -> float:
    """오늘이 시작한 시각 (한국 시간 오전 6시)"""
    now = time.time() if now is None else now
    shift = (9 - DAY_STARTS_AT) * 3600
    return math.floor((now + shift) / 86400) * 86400 - shift


def post_title(ts: float | None = None) -> str:
    """포럼 모집 글 제목. 예) 10월 6일(화) 21:30 내전 모집. 마감 시각을 정해 만든 모집은 그 시각을, 아니면 만든 시각을 적는다."""
    at = datetime.fromtimestamp(ts, KST) if ts else datetime.now(KST)
    return f"{at.month}월 {at.day}일({'월화수목금토일'[at.weekday()]}) {at:%H:%M} 내전 모집"


def announcement_text(rec: Recruitment) -> str:
    count = len(rec.participants)
    names = ", ".join(safe_name(v["name"]) for v in rec.participants.values()) or "아직 없음"
    if rec.cancelled:
        status = "❌ **이 내전은 취소됐어요.**"
    elif rec.closed:
        status = f"🔒 **모집 마감** — 최종 {count}명"
    else:
        status = (
            f"⏰ **{when(rec.end_ts)}까지** 참여 신청을 받아요. "
            f"(<t:{rec.end_ts}:R> 마감{', 연장됨' if rec.extended else ''})\n"
            f"👉 여기에서 `/참여` 를 입력하세요. 취소는 `/참여취소`"
        )
    return f"{ANNOUNCEMENT}\n\n{status}\n👥 참여자 ({count}명): {names}"


async def refresh_announcement(rec: Recruitment) -> None:
    """모집 글의 마감 시각과 참여자 현황을 최신 상태로 수정"""
    if rec.message is None:
        return
    async with rec.edit_lock:  # 동시에 여러 명이 참여해도 마지막 상태가 반영되도록 순서대로 수정
        try:
            await rec.message.edit(content=announcement_text(rec))
        except discord.HTTPException as e:
            print(f"공지 수정 실패: {e}")


async def open_signup(rec: Recruitment, title_ts: float | None = None) -> None:
    """참여 신청 채널에 모집 글을 올린다. 포럼이면 새 글을 만들고, 일반 채널이면 메시지를 보낸다."""
    signup = await get_channel(SIGNUP_CHANNEL_ID)
    if isinstance(signup, discord.ForumChannel):
        options = {}
        if signup.flags.require_tag and signup.available_tags:
            options["applied_tags"] = signup.available_tags[:1]  # 태그가 필수인 포럼이면 첫 태그를 붙인다
        created = await signup.create_thread(name=post_title(title_ts), content=announcement_text(rec), **options)
        rec.thread, rec.message = created.thread, created.message
    else:
        rec.message = await signup.send(announcement_text(rec))


async def post(rec: Recruitment, text: str, quiet: bool = False) -> None:
    """모집 글(포럼) 또는 참여 신청 채널에 메시지를 보낸다. quiet 면 멘션 알림을 보내지 않는다. 실패해도 모집 처리는 계속한다."""
    try:
        place = rec.thread or await get_channel(SIGNUP_CHANNEL_ID)
        if quiet:
            await place.send(text, allowed_mentions=discord.AllowedMentions.none())
        else:
            await place.send(text)
    except discord.HTTPException as e:
        print(f"참여 신청 채널 전송 실패: {e}")


async def tell_admins(text: str) -> None:
    try:
        admin = await get_channel(ADMIN_CHANNEL_ID)
        await admin.send(text, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException as e:
        print(f"관리자 채널 전송 실패: {e}")


async def set_locked(rec: Recruitment, locked: bool) -> None:
    """포럼 모집 글을 잠그거나 다시 연다. 일반 채널이면 아무 일도 하지 않는다."""
    if rec.thread is None:
        return
    try:
        await rec.thread.edit(locked=locked, archived=False)
    except discord.HTTPException as e:  # 스레드 관리 권한이 없으면 잠그지 못할 뿐, 모집은 그대로 진행한다
        print(f"모집 글 잠금 변경 실패: {e}")


def stop_timer(rec: Recruitment) -> None:
    if rec.task is not None and rec.task is not asyncio.current_task():
        rec.task.cancel()
    rec.task = None


async def close_when_due(rec: Recruitment) -> None:
    # 며칠 뒤 마감일 수도 있고 컴퓨터가 잠들었다 깰 수도 있어서, 길게 한 번 자지 않고 시계를 봐 가며 기다린다
    while time.time() < rec.end_ts:
        await asyncio.sleep(min(30, max(0.05, rec.end_ts - time.time())))
    async with bot.lock:
        await close_recruitment(rec)


# ── 봇을 껐다 켜도 모집을 이어 가기 ───────────────────────────
def save_state() -> None:
    """진행 중인 모집과 오늘 짠 팀을 파일에 적는다. 실패해도 모집은 계속한다."""
    cur = bot.current
    start = day_start()
    bot.lineups = [x for x in bot.lineups if x.get("at", 0) >= start]
    try:
        data = {"current": cur.to_dict() if cur is not None and cur.message is not None else None, "lineups": bot.lineups}
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, STATE_PATH)
    except (OSError, TypeError, ValueError) as e:
        print(f"모집 상태를 저장하지 못했습니다: {e}")


async def restore_state() -> None:
    """켤 때 한 번: 꺼지기 전에 하던 모집을 이어받는다. 그사이 마감 시각이 지났으면 바로 마감한다."""
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    bot.lineups = [x for x in data.get("lineups") or [] if isinstance(x, dict)]
    cur = data.get("current")
    if not cur or not cur.get("message_id"):
        return
    rec = Recruitment(int(cur["host_id"]), int(cur["end_ts"]))
    rec.participants = {int(uid): {"name": name, "username": username} for uid, name, username in cur.get("participants", [])}
    rec.closed, rec.cancelled, rec.extended = bool(cur.get("closed")), bool(cur.get("cancelled")), bool(cur.get("extended"))
    rec.synced, rec.lineup = bool(cur.get("synced")), bool(cur.get("lineup"))
    try:
        place = await get_channel(int(cur.get("thread_id") or SIGNUP_CHANNEL_ID))
    except discord.HTTPException as e:
        print(f"꺼지기 전에 하던 모집을 이어받지 못했습니다. 모집 글이 지워졌을 수 있습니다. ({e})")
        return
    if cur.get("thread_id"):
        rec.thread = place
    rec.message = place.get_partial_message(int(cur["message_id"]))
    bot.current = rec
    if rec.closed:
        return
    rec.task = asyncio.create_task(close_when_due(rec))
    print(f"꺼지기 전에 하던 모집을 이어받았습니다. 참여자 {len(rec.participants)}명, "
          f"마감 {datetime.fromtimestamp(rec.end_ts, KST):%m월 %d일 %H:%M}")


# ── 마감 · 연장 · 취소 (bot.lock 을 잡은 상태에서 부른다) ─────────
async def close_recruitment(rec: Recruitment) -> None:
    if rec.closed:
        return
    rec.closed = True
    stop_timer(rec)

    await refresh_announcement(rec)

    roster = list(rec.participants)
    count = len(roster)
    lines = [f"{i}. <@{uid}>" for i, uid in enumerate(roster, start=1)]

    if count == 0:
        summary = "참여자가 없어서 이번 내전은 열리지 않아요."
    elif count < PLAYERS_NEEDED:
        summary = f"⚠️ {PLAYERS_NEEDED}명에서 {PLAYERS_NEEDED - count}명 부족해요."
    else:
        summary = "✅ 인원이 모였어요! 로비 안내를 기다려 주세요."

    roster_text = f"📋 **내전 참여 명단** (총 {count}명)\n"
    if lines:
        roster_text += "\n".join(lines) + "\n"
    roster_text += f"\n{summary}"

    # 모집 글(참여 신청 채널): 참여자들에게 알림(멘션)이 가도록 전송
    await post(rec, roster_text)

    # 관리자 채널: 같은 명단을 알림 없이 전송하고, 리그 매니저에 붙여넣을 명단을 따로 올린다
    synced = await push_roster(rec) if roster else None
    if synced:
        rec.synced = True
    try:
        admin = await get_channel(ADMIN_CHANNEL_ID)
        await admin.send(
            f"[모집 종료] 주최: <@{rec.host_id}>\n{roster_text}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        if roster:
            for chunk in manager_blocks(rec):
                await admin.send(chunk, allowed_mentions=discord.AllowedMentions.none())
        if synced is not None:
            await admin.send("리그 서버에 명단을 올렸습니다. 매니저에서 '봇이 올린 명단 불러오기'를 누르세요."
                             if synced else "리그 서버에 명단을 올리지 못했습니다. 위 명단을 복사해 붙여넣어 주세요.")
        if count < PLAYERS_NEEDED:
            await admin.send(f"`/연장` 으로 {minutes_text(EXTEND_SECONDS)} 더 모집하거나 `/취소` 로 이번 내전을 취소할 수 있어요.")
    except discord.HTTPException as e:
        print(f"관리자 채널 전송 실패: {e}")

    if count >= PLAYERS_NEEDED and not match_problem():
        await auto_match(rec)

    await set_locked(rec, True)
    save_state()


async def extend_recruitment(rec: Recruitment) -> None:
    """마감을 뒤로 미룬다. 모집 중이면 지금 마감 시각에서, 마감한 뒤면 지금부터 센다."""
    reopened = rec.closed
    rec.end_ts = deadline_after(EXTEND_SECONDS, None if reopened else rec.end_ts)
    rec.closed = False
    rec.extended = True
    stop_timer(rec)
    rec.task = asyncio.create_task(close_when_due(rec))

    if reopened:
        await set_locked(rec, False)
        if rec.synced:  # 마감 때 올린 명단은 더 이상 최종이 아니므로 비워 둔다
            await push_roster(rec, clear=True)
            rec.synced = False
        await drop_lineup(rec)
    await refresh_announcement(rec)
    await post(rec, f"⏩ 모집을 연장했어요! **{when(rec.end_ts)}까지** `/참여` 로 신청하세요. (<t:{rec.end_ts}:R> 마감)")
    save_state()


async def cancel_recruitment(rec: Recruitment) -> None:
    rec.closed = True
    rec.cancelled = True
    stop_timer(rec)

    await refresh_announcement(rec)
    mentions = " ".join(f"<@{uid}>" for uid in rec.participants)
    await post(rec, "❌ **이번 내전은 취소됐어요.**" + (f"\n{mentions}" if mentions else ""))
    if rec.synced:  # 매니저가 취소된 내전의 명단을 불러오지 않게 서버의 명단을 비운다
        await push_roster(rec, clear=True)
        rec.synced = False
    await drop_lineup(rec)
    await set_locked(rec, True)
    save_state()


def manager_blocks(rec: Recruitment) -> list[str]:
    """리그 매니저 팀 편성 탭의 '디스코드 봇의 참가 명단·짠 팀 불러오기'에 붙여넣을 글. 한 줄에 '사용자ID 사용자명 별명'."""
    lines = []
    for uid, v in rec.participants.items():
        name = v["name"].replace("`", "'").replace("\n", " ")
        lines.append(f"{uid} {v['username']} {name}")
    # 디스코드 메시지는 2000자까지라 길면 나눠 보낸다
    blocks, cur = [], []
    for line in lines:
        if sum(len(x) + 1 for x in cur) + len(line) > 1800:
            blocks.append(cur)
            cur = []
        cur.append(line)
    if cur:
        blocks.append(cur)
    head = "매니저 붙여넣기용 (코드 블록 안을 복사하세요)\n"
    return [(head if i == 0 else "") + "```\n" + "\n".join(b) + "\n```" for i, b in enumerate(blocks)]


# ── 리그 서버 ────────────────────────────────────────────────
async def call_server(payload: dict) -> dict:
    """리그 서버(Apps Script)에 운영진 요청을 보낸다. 실패하면 예외를 낸다."""
    timeout = aiohttp.ClientTimeout(total=40)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Apps Script 는 결과를 다른 주소로 넘겨 주므로 리다이렉트를 따라간다
        async with session.post(SYNC_URL, data=json.dumps({**payload, "key": SYNC_KEY}),
                                headers={"Content-Type": "text/plain;charset=utf-8"}) as resp:
            text = await resp.text()
    result = json.loads(text)
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "서버가 요청을 처리하지 못했습니다")
    return result


async def push_roster(rec: Recruitment, clear: bool = False) -> bool | None:
    """리그 서버에 명단을 올린다. 설정이 없으면 None, 성공하면 True. clear 면 빈 명단으로 비운다."""
    if not (SYNC_URL and SYNC_KEY):
        return None
    entries = [] if clear else [
        {"id": str(uid), "username": v["username"], "name": v["name"]} for uid, v in rec.participants.items()
    ]
    try:
        await call_server({"action": "pushRoster", "roster": {"entries": entries}})
        return True
    except Exception as e:  # 서버 문제로 모집 마감이 멈추면 안 된다
        print(f"리그 서버에 명단을 올리지 못했습니다: {e!r}")
        return False


# ── 자동 팀 편성 ──────────────────────────────────────────────
def match_players(rec: Recruitment, players: list[dict]) -> tuple[dict[str, int], list[int]]:
    """참가자를 리그 기록의 선수와 맞춘다. 매니저의 '명단대로 고르기'와 같은 순서: 디스코드 사용자 ID → 사용자명 → 이름.
    돌려주는 값: ({선수 id: 디스코드 사용자 ID}, 선수단에서 찾지 못한 참가자의 디스코드 사용자 ID)"""
    def norm(v) -> str:
        return str(v or "").strip().lstrip("@").lower()

    by_discord = {norm(p.get("discord")): p for p in players if norm(p.get("discord"))}
    by_name = {norm(p.get("name")): p for p in players if norm(p.get("name"))}
    found: dict[str, int] = {}
    missing: list[int] = []
    for uid, v in rec.participants.items():
        p = by_discord.get(str(uid)) or by_discord.get(norm(v["username"])) or by_name.get(norm(v["name"]))
        if p is None or p["id"] in found:
            missing.append(uid)
        else:
            found[p["id"]] = uid
    return found, missing


async def run_matchmaker(payload: dict) -> dict:
    """matchmaker.js(Node)에 리그 기록과 참가자를 넘겨 팀을 받는다."""
    proc = await asyncio.create_subprocess_exec(
        NODE_PATH, str(MATCHMAKER), str(MANAGER_FILE),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(json.dumps(payload).encode("utf-8")), timeout=90)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("팀을 짜는 데 너무 오래 걸렸습니다")
    if not out:
        raise RuntimeError(err.decode("utf-8", "replace").strip()[-300:] or "matchmaker.js 가 답하지 않았습니다")
    return json.loads(out.decode("utf-8"))


def lineup_text(result: dict, who: dict[str, int], missing: list[int]) -> str:
    """모집 글에 올릴 팀 편성. who 는 {선수 id: 디스코드 사용자 ID}"""
    def seat(p: dict) -> str:
        return f"{safe_name(p['name'])} <@{who[p['id']]}>"

    def team(side: str) -> str:
        return "\n".join(f"`{l['role']} {ROLE_NAMES[l['role'] - 1]}` {seat(l[side])}" for l in result["lanes"])

    stats = result["stats"]
    text = (
        "⚔️ **팀 편성**\n\n"
        f"🟢 **래디언트** · 평균 MMR {stats['rawR']}\n{team('r')}\n\n"
        f"🔴 **다이어** · 평균 MMR {stats['rawD']}\n{team('d')}"
    )
    if result["bench"]:
        text += ("\n\n🪑 이번 판은 쉬어요: " + ", ".join(seat(p) for p in result["bench"])
                 + "\n오늘 아직 안 뛴 사람, 그다음은 총 판수가 적은 사람 순으로 출전해요.")
    if missing:
        text += "\n\n⚠️ 선수 등록이 확인되지 않아 팀에서 빠졌어요: " + " ".join(f"<@{uid}>" for uid in missing)
    return text


async def auto_match(rec: Recruitment) -> None:
    """마감한 모집의 참가자로 팀을 짜서 모집 글과 관리자 채널에 알리고, 매니저가 불러올 수 있게 서버에 올린다.
    어디서 막히든 모집 마감은 끝까지 가야 하므로, 문제는 관리자 채널에 알리고 넘어간다."""
    try:
        league = (await call_server({"action": "adminLeague"})).get("league")
    except Exception as e:
        print(f"리그 기록을 받지 못했습니다: {e!r}")
        await tell_admins("리그 서버에서 기록을 받지 못해 팀을 자동으로 짜지 못했습니다. 매니저에서 직접 짜 주세요.")
        return
    if not league or not league.get("players"):
        await tell_admins("리그 매니저가 서버에 올린 기록이 없어 팀을 자동으로 짜지 못했습니다. "
                          "매니저의 데이터 · 설정 탭에서 **지금 올리기**를 누른 뒤 `/연장` → `/마감` 하면 다시 짭니다.")
        return

    who, missing = match_players(rec, league["players"])
    if len(who) < PLAYERS_NEEDED:
        await post(rec, f"⚠️ 선수 등록이 확인된 참가자가 {len(who)}명이라 팀을 자동으로 짜지 못했어요. 운영진의 안내를 기다려 주세요.", quiet=True)
        await tell_admins(f"선수단과 맞는 참가자가 {len(who)}명이라 팀을 자동으로 짜지 못했습니다. 선수단에 없는 참가자: "
                          + (" ".join(f"<@{uid}>" for uid in missing) or "없음")
                          + "\n승인한 선수를 매니저에 불러와 **지금 올리기**를 했는지, 등록한 디스코드 사용자명이 맞는지 확인해 주세요.")
        return

    start = day_start()
    busy = sorted({pid for x in bot.lineups if x.get("at", 0) >= start for pid in x.get("ids", [])})
    try:
        result = await run_matchmaker({"league": league, "participants": list(who), "busy": busy, "now": int(time.time() * 1000)})
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "알 수 없는 문제")
    except Exception as e:
        print(f"팀 편성 실패: {e!r}")
        await tell_admins(f"팀을 자동으로 짜지 못했습니다. 매니저에서 직접 짜 주세요. ({e})")
        return

    text = lineup_text(result, who, missing)
    await post(rec, text, quiet=True)  # 방금 명단 공지로 알림이 갔으니 한 번 더 울리지 않는다
    playing = [l[side]["id"] for l in result["lanes"] for side in ("r", "d")]
    rec.lineup = True
    bot.lineups.append({"at": time.time(), "ids": playing, "message_id": rec.message.id if rec.message else 0})
    try:
        await call_server({"action": "pushLineup", "lineup": {
            "post": getattr(rec.message, "jump_url", ""),
            "lanes": [{"role": l["role"], "r": l["r"]["id"], "d": l["d"]["id"]} for l in result["lanes"]],
            "bench": [p["id"] for p in result["bench"]],
        }})
        note = "매니저의 팀 편성 탭에서 **봇이 짠 팀 불러오기**를 누르면 이 편성이 그대로 올라옵니다. 경기가 끝나면 이긴 팀만 눌러 주세요."
    except Exception as e:
        print(f"짠 팀을 리그 서버에 올리지 못했습니다: {e!r}")
        note = "짠 팀을 리그 서버에 올리지 못했습니다. 매니저에서 위 편성대로 자리를 맞춰 주세요."
    await tell_admins(f"{text}\n\n{note}")


async def drop_lineup(rec: Recruitment) -> None:
    """이 모집으로 짠 팀을 없던 일로 한다 (다시 열거나 취소할 때)."""
    if not rec.lineup:
        return
    rec.lineup = False
    message_id = rec.message.id if rec.message else 0
    bot.lineups = [x for x in bot.lineups if x.get("message_id") != message_id]
    try:
        await call_server({"action": "pushLineup", "lineup": None})
    except Exception as e:
        print(f"리그 서버의 팀 편성을 비우지 못했습니다: {e!r}")


# ── 슬래시 명령어: 운영진 ─────────────────────────────────────
async def admin_only(interaction: discord.Interaction) -> bool:
    """운영진 명령어 공통 확인: 관리자 채널에서, 운영진이 입력했는지"""
    if interaction.channel_id != ADMIN_CHANNEL_ID:
        await interaction.response.send_message("이 명령어는 관리자 채널에서만 쓸 수 있어요.", ephemeral=True)
        return False
    if not is_admin(interaction.user):
        await interaction.response.send_message("운영진만 쓸 수 있는 명령어예요.", ephemeral=True)
        return False
    return True


@bot.tree.command(name="내전생성", description="내전 참여자 모집을 시작합니다 (운영진 전용)", guild=GUILD)
@app_commands.rename(deadline="마감")
@app_commands.describe(deadline=f"참여 신청을 마감할 시각(한국 시간). 예) 2026-10-07-21-30  비우면 {minutes_text(SIGNUP_SECONDS)} 뒤에 마감")
async def create_inhouse(interaction: discord.Interaction, deadline: Optional[str] = None) -> None:
    if not await admin_only(interaction):
        return
    end_ts = None
    if deadline is not None and deadline.strip():
        end_ts = parse_deadline(deadline)
        if end_ts is None:
            await interaction.response.send_message(
                f"마감 시각의 형식이 맞지 않아 모집을 만들지 않았어요. 이렇게 적어 주세요: {DEADLINE_EXAMPLE}", ephemeral=True
            )
            return
        if end_ts <= time.time():
            await interaction.response.send_message(
                f"<t:{end_ts}:f> 은 이미 지난 시각이라 모집을 만들지 않았어요. 앞으로 올 시각을 적어 주세요: {DEADLINE_EXAMPLE}", ephemeral=True
            )
            return
    busy = "이미 모집 중인 내전이 있어요. (마감 <t:{}:R>)"
    if bot.current is not None and not bot.current.closed:
        await interaction.response.send_message(busy.format(bot.current.end_ts), ephemeral=True)
        return
    await interaction.response.defer()

    async with bot.lock:
        # 글을 올리는 사이에 다른 운영진이 먼저 만들었을 수 있으니 다시 확인한다
        if bot.current is not None and not bot.current.closed:
            await interaction.followup.send(busy.format(bot.current.end_ts))
            return
        rec = Recruitment(host_id=interaction.user.id, end_ts=end_ts or deadline_after(SIGNUP_SECONDS))
        try:
            await open_signup(rec, title_ts=end_ts)
        except discord.HTTPException as e:
            await interaction.followup.send(f"모집 글을 올리지 못했어요. 봇 권한과 채널 ID를 확인해 주세요. ({e})")
            return
        bot.current = rec  # 모집 글이 올라간 뒤에 등록해서, 다른 명령어가 준비되지 않은 모집을 보지 않게 한다
        rec.task = asyncio.create_task(close_when_due(rec))
        save_state()

    await interaction.followup.send(
        f"✅ 모집을 시작했어요! {rec.message.jump_url}\n마감: {when(rec.end_ts)} (<t:{rec.end_ts}:R>)"
    )


@bot.tree.command(name="마감", description="지금까지 모인 인원으로 모집을 바로 마감합니다 (운영진 전용)", guild=GUILD)
async def close_now(interaction: discord.Interaction) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    async with bot.lock:
        rec = bot.current
        if rec is None or rec.closed:
            await interaction.followup.send("지금은 모집 중인 내전이 없어요.")
            return
        await close_recruitment(rec)
    await interaction.followup.send(f"🔒 모집을 마감했어요. (최종 {len(rec.participants)}명)")


@bot.tree.command(
    name="연장",
    description=f"모집 마감을 {minutes_text(EXTEND_SECONDS)} 뒤로 미룹니다. 마감한 뒤에도 다시 열 수 있어요 (운영진 전용)",
    guild=GUILD,
)
async def extend(interaction: discord.Interaction) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    async with bot.lock:
        rec = bot.current
        if rec is None or rec.cancelled:
            await interaction.followup.send("연장할 내전이 없어요. `/내전생성` 으로 새로 모집해 주세요.")
            return
        reopened = rec.closed
        await extend_recruitment(rec)
    await interaction.followup.send(
        ("⏩ 마감한 모집을 다시 열었어요." if reopened else "⏩ 모집을 연장했어요.")
        + f" 새 마감: {when(rec.end_ts)} (<t:{rec.end_ts}:R>)"
    )


@bot.tree.command(name="취소", description="이번 내전을 취소합니다 (운영진 전용)", guild=GUILD)
async def cancel(interaction: discord.Interaction) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    async with bot.lock:
        rec = bot.current
        if rec is None or rec.cancelled:
            await interaction.followup.send("취소할 내전이 없어요.")
            return
        await cancel_recruitment(rec)
    await interaction.followup.send("❌ 내전을 취소했어요." + (f" {rec.message.jump_url}" if rec.message else ""))


# ── 슬래시 명령어: 참가자 ─────────────────────────────────────
async def open_recruitment(interaction: discord.Interaction) -> Recruitment | None:
    """/참여·/참여취소 공통 확인: 모집 중이고, 모집 글(일반 채널이면 그 채널)에서 입력했는지"""
    rec = bot.current
    if rec is None or rec.closed:
        await interaction.response.send_message("지금은 모집 중인 내전이 없어요.", ephemeral=True)
        return None
    if interaction.channel_id != rec.place_id:
        await interaction.response.send_message(f"<#{rec.place_id}> 에서 입력해 주세요.", ephemeral=True)
        return None
    return rec


@bot.tree.command(name="참여", description="진행 중인 내전 모집에 참여합니다", guild=GUILD)
async def join(interaction: discord.Interaction) -> None:
    rec = await open_recruitment(interaction)
    if rec is None:
        return

    uid = interaction.user.id
    if uid in rec.participants:
        order = list(rec.participants).index(uid) + 1
        await interaction.response.send_message(f"이미 참여했어요! ({order}번째)", ephemeral=True)
        return

    rec.participants[uid] = {"name": interaction.user.display_name, "username": interaction.user.name}
    save_state()
    await interaction.response.send_message(
        f"✅ 참여 완료! {len(rec.participants)}번째 참여자예요. 마감 <t:{rec.end_ts}:R>", ephemeral=True
    )
    await refresh_announcement(rec)


@bot.tree.command(name="참여취소", description="내전 참여 신청을 취소합니다", guild=GUILD)
async def leave(interaction: discord.Interaction) -> None:
    rec = await open_recruitment(interaction)
    if rec is None:
        return
    if rec.participants.pop(interaction.user.id, None) is None:
        await interaction.response.send_message("참여 신청 기록이 없어요.", ephemeral=True)
        return

    save_state()
    await interaction.response.send_message("참여를 취소했어요.", ephemeral=True)
    await refresh_announcement(rec)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    print(f"명령어 오류: {error!r}")
    msg = "명령어 처리 중 오류가 발생했어요. 운영진에게 알려 주세요."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


if __name__ == "__main__":
    bot.run(TOKEN)
