"""
도타 2 인하우스 내전 모집 봇

- 관리자 채널에서 /내전생성  → 참여 신청 채널에 모집 글을 올리고 모집 시작
  (참여 신청 채널이 포럼이면 내전마다 새 글을 만들고, 일반 채널이면 공지 메시지를 올림)
  · /내전생성 마감:2026-10-07-21-30 처럼 마감 시각(한국 시간)을 적으면 그 시각에 마감
  · 비우면 모집 시간(기본 5분) 뒤를 분 단위로 올림한 시각. 12:00:30 에 만들면 12:06:00 마감
- 모집 글(일반 채널이면 그 채널)에서 /참여, /참여취소
- 마감 시각이 되면 참여 명단을 공지하고, 리그 매니저와 같은 로직으로 팀을 짜서 알림 (matchmaker.js, Node 필요)
  · 팀 편성 공지에는 선수별 인하우스 MMR과 이기면·지면 바뀌는 점수, 팀 평균과 같은 자리·라인끼리의 MMR 차이가 함께 나감
- 관리자 채널에서 /마감 (지금 인원으로 바로 마감), /연장 (마감을 5분 뒤로, 마감한 뒤에도 가능), /취소 (내전 취소)
- 경기가 끝나면 관리자 채널에서 /승리 (이긴 팀을 골라 결과 기록과 MMR 정산), /승리취소 (방금 기록한 결과 되돌리기)
  · 정산도 리그 매니저의 로직 그대로 한다. 리그 기록의 원본은 서버에 있고, 봇은 받아서 고친 뒤 다시 올린다
- 경기를 시작할 때 관리자 채널에서 /시작 (로비 음성 채널에 있는 선수를 배정된 팀의 음성 채널로 옮김), 끝나면 /종료 (팀 음성 채널의 모두를 로비로)
  · 음성 채널은 /시작 의 로비·래디언트·다이어 칸에서 한 번 고르면 기억한다. 봇에 멤버 이동 권한이 있어야 한다
- 운영진 명령어로 봇이 올리는 글은 모두 그 명령어를 쓴 운영진의 멘션으로 시작한다 (본인에게만 보이는 안내는 빼고)
- 관리자 채널에는 리그 매니저에 붙여넣을 명단(디스코드 ID·사용자명·별명)을 함께 올림
- 서버 주소(sync_url)와 운영진 키(sync_key)를 적어 두면, 명단과 짠 팀을 리그 서버에도 올려
  매니저의 "봇이 올린 명단 불러오기", "봇이 짠 팀 불러오기"로 바로 받을 수 있음
- 관리자 채널에서 /선수역할 로 역할을 정해 두면, 운영진 페이지에서 승인한 선수에게 그 역할을 주고 제외한 선수에게서는 뺌
  (등록 명단을 1분마다 읽어 맞춘다. 봇에 역할 관리 권한이 있고, 봇의 역할이 그 역할보다 위에 있어야 한다)
- 진행 중인 모집과 역할 설정은 state.json 에 적어 두어, 봇을 껐다 켜도 이어짐

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
# 승인한 선수에게 줄 역할. 보통은 비워 두고 디스코드에서 /선수역할 로 정한다(그 값은 state.json 에 남는다)
PLAYER_ROLE_ID = int(config.get("player_role_id", 0) or 0)
ROLE_POLL_SECONDS = 60  # 등록 명단의 승인·제외를 이만큼마다 확인한다
ROLE_RETRY_SECONDS = 600  # 서버에서 찾지 못한 사람은 이만큼 지난 뒤에 다시 찾아본다
ROLE_BATCH = 30  # 한 번에 찾아볼 사람 수. 디스코드에 몰아서 묻지 않게 나눠 한다
PLAYERS_NEEDED = 10  # 5 vs 5
KST = timezone(timedelta(hours=9))  # 마감 시각 입력과 모집 글 제목에 쓰는 한국 시간
DAY_STARTS_AT = 6  # 하루는 한국 시간 오전 6시에 바뀐다 (매니저의 팀 편성과 같은 기준)
ROLE_NAMES = ["캐리", "미드", "오프", "서폿", "서폿"]
# /시작·/종료 가 쓰는 음성 채널 세 곳. 고른 적이 없으면 이름에 이 낱말이 든 음성 채널을 찾아본다
VOICE_ROOMS = {"lobby": ("로비", "lobby"), "radiant": ("래디언트", "radiant"), "dire": ("다이어", "dire")}
DEADLINE_FORMAT = re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})")
DEADLINE_EXAMPLE = "`2026-10-07-21-30` (연-월-일-시-분, 한국 시간, 24시간제)"
MESSAGE_LIMIT = 1900  # 디스코드 메시지는 2000자까지라 조금 남겨 두고 나눈다
THREAD_ARCHIVED = 50083  # 디스코드 오류 번호: 보관된(접힌) 스레드에는 글을 올리거나 고칠 수 없다


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
        # 봇이 보내는 글로는 @everyone 과 역할 멘션 알림이 절대 울리지 않게 한다 (닉네임 같은 남의 글이 섞여 들어가도 안전하도록)
        super().__init__(intents=discord.Intents.default(), allowed_mentions=discord.AllowedMentions(everyone=False, roles=False))
        self.tree = app_commands.CommandTree(self)
        self.current: Recruitment | None = None  # 모집 중이거나 가장 최근에 마감한 내전
        self.lock: asyncio.Lock | None = None
        # 오늘 짠 팀 [{"at": 시각, "ids": 선수 id, "message_id": 모집 글}]. 결과를 아직 기록하지 않은 판도 오늘 뛴 것으로 치는 데 쓴다
        self.lineups: list[dict] = []
        self.restored = False
        # 참여 선수 역할 자동 부여. player_role_id 가 0이면 꺼져 있다.
        # role_seen 은 등록마다 마지막으로 맞춘 내용 {스팀키: {"status", "discord", "ok", "tried"}}, role_season 은 그때의 시즌 이름이다
        self.player_role_id = PLAYER_ROLE_ID
        self.role_seen: dict[str, dict] = {}
        self.role_season = ""
        # 마지막으로 맞춘 시즌의 번호(서버가 알려 준다. 아직 모르면 None). 서버의 번호가 더 크면 시즌이 넘어간 것이라 역할을 거둔다.
        # role_revoke 는 거두는 중인 일 {"to": 새 시즌 번호, "left": [아직 확인하지 않은 디스코드], "removed": 거둔 수, "total": 전체}
        self.role_season_no: int | None = None
        self.role_revoke: dict | None = None
        self.role_note = ""  # 마지막으로 관리자 채널에 알린 문제. 같은 문제를 1분마다 다시 알리지 않으려고 적어 둔다
        self.role_lock: asyncio.Lock | None = None
        self.role_task: asyncio.Task | None = None
        # /시작 에서 골라 둔 음성 채널 {"lobby": 채널 ID, "radiant": …, "dire": …}. 없는 것은 이름으로 찾는다
        self.voice: dict[str, int] = {}

    async def setup_hook(self) -> None:
        # 생성·마감·연장·취소가 겹치지 않게 한 번에 하나씩 처리한다
        self.lock = asyncio.Lock()
        self.role_lock = asyncio.Lock()
        # 서버 단위로 등록하면 슬래시 명령어가 즉시 반영됨
        await self.tree.sync(guild=GUILD)

    async def on_ready(self) -> None:
        print(f"로그인 완료: {self.user} (ID: {self.user.id})")
        await check_setup()
        if not self.restored:  # 연결이 끊겼다 다시 붙을 때는 다시 읽지 않는다
            self.restored = True
            async with self.lock:
                try:
                    await restore_state()
                except Exception as e:  # 상태 파일의 모양이 어긋나 있어도 봇은 켜져야 한다 (역할 맞추기도 여기서 시작한다)
                    print(f"꺼지기 전의 상태를 이어받지 못해 새로 시작합니다. ({e!r})")
            print(f"참여 선수 역할 자동 부여: {await role_status()}")
            print(f"음성 채널 이동(/시작·/종료): {await voice_status()}")
            self.role_task = asyncio.create_task(role_loop())


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


def split_message(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """디스코드 메시지 한도에 맞게 글을 나눈다. 빈 줄 → 줄바꿈 → 쉼표 순으로 끊을 곳을 찾고, 그래도 길면 글자 수로 자른다."""
    def pack(text: str, seps: tuple[str, ...]) -> list[str]:
        if len(text) <= limit:
            return [text]
        if not seps:
            return [text[i:i + limit] for i in range(0, len(text), limit)]
        sep, out, cur = seps[0], [], ""
        for piece in text.split(sep):
            if cur and len(cur) + len(sep) + len(piece) <= limit:
                cur += sep + piece
                continue
            if cur:
                out.append(cur)
            *full, cur = pack(piece, seps[1:])  # 한 덩이가 한도를 넘으면 더 잘게 나눈다
            out += full
        return out + [cur]

    return [chunk for chunk in pack(text, ("\n\n", "\n", ", ")) if chunk.strip()]


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
    # 본문은 메시지 하나라 2000자를 넘으면 고쳐지지 않는다. 참여자가 아주 많으면 이름은 앞에서부터 들어가는 만큼만 적는다
    shown, used = [], 0
    for v in rec.participants.values():
        name = safe_name(v["name"])
        if used + len(name) + 2 > 1200:
            break
        shown.append(name)
        used += len(name) + 2
    names = (", ".join(shown) + (f" 외 {count - len(shown)}명" if len(shown) < count else "")) or "아직 없음"
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
    return f"<@{rec.host_id}>님이 내전 모집을 열었어요.\n{ANNOUNCEMENT}\n\n{status}\n👥 참여자 ({count}명): {names}"


async def awake(thread, action):
    """포럼 글에 글을 올리거나 고친다. 글이 한동안 조용해서 접혀(보관돼) 있으면 다시 편 뒤에 한 번 더 한다.
    잠근 글은 저절로 펴지지 않아서, 며칠 뒤가 마감인 모집이나 경기가 끝난 뒤의 결과 공지가 여기에 걸릴 수 있다."""
    try:
        return await action()
    except discord.HTTPException as e:
        if thread is None or getattr(e, "code", 0) != THREAD_ARCHIVED:
            raise
        await thread.edit(archived=False)
        return await action()


async def refresh_announcement(rec: Recruitment) -> None:
    """모집 글의 마감 시각과 참여자 현황을 최신 상태로 수정"""
    if rec.message is None:
        return
    async with rec.edit_lock:  # 동시에 여러 명이 참여해도 마지막 상태가 반영되도록 순서대로 수정
        try:
            await awake(rec.thread, lambda: rec.message.edit(content=announcement_text(rec)))
        except discord.HTTPException as e:
            print(f"공지 수정 실패: {e}")


async def open_signup(rec: Recruitment, title_ts: float | None = None) -> None:
    """참여 신청 채널에 모집 글을 올린다. 포럼이면 새 글을 만들고, 일반 채널이면 메시지를 보낸다."""
    signup = await get_channel(SIGNUP_CHANNEL_ID)
    options = {"allowed_mentions": discord.AllowedMentions.none()}  # 본문 맨 앞에 모집을 연 운영진을 적는다. 알림은 울리지 않는다
    if isinstance(signup, discord.ForumChannel):
        if signup.flags.require_tag and signup.available_tags:
            options["applied_tags"] = signup.available_tags[:1]  # 태그가 필수인 포럼이면 첫 태그를 붙인다
        created = await signup.create_thread(name=post_title(title_ts), content=announcement_text(rec), **options)
        rec.thread, rec.message = created.thread, created.message
    else:
        rec.message = await signup.send(announcement_text(rec), **options)


async def post(rec: Recruitment, text: str, quiet: bool = False, skip: int | None = None) -> None:
    """모집 글(포럼) 또는 참여 신청 채널에 메시지를 보낸다. quiet 면 멘션 알림을 보내지 않는다. 실패해도 모집 처리는 계속한다.
    skip 은 글에 멘션돼 있어도 알림은 보내지 않을 사람이다 (글 맨 앞에 적는, 명령어를 쓴 운영진).
    글이 길면 여러 메시지로 나눠 보낸다."""
    try:
        place = rec.thread or await get_channel(SIGNUP_CHANNEL_ID)
        for chunk in split_message(text):
            options = {}
            if quiet:
                options["allowed_mentions"] = discord.AllowedMentions.none()
            elif skip is not None:  # 이 메시지에 멘션된 사람 가운데 skip 만 빼고 알린다 (한 메시지에 100명까지라 메시지마다 따로 센다)
                ids = sorted({int(x) for x in re.findall(r"<@(\d+)>", chunk)} - {skip})
                options["allowed_mentions"] = discord.AllowedMentions(everyone=False, roles=False, users=[discord.Object(id=i) for i in ids])
            await awake(rec.thread, lambda: place.send(chunk, **options))
    except discord.HTTPException as e:
        print(f"참여 신청 채널 전송 실패: {e}")


async def tell_admins(text: str) -> None:
    try:
        admin = await get_channel(ADMIN_CHANNEL_ID)
        for chunk in split_message(text):
            await admin.send(chunk, allowed_mentions=discord.AllowedMentions.none())
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
    keep_from = time.time() - 2 * 86400  # 결과를 다음 날 기록하는 일도 있어 이틀 치를 남긴다
    bot.lineups = [x for x in bot.lineups if x.get("at", 0) >= keep_from]
    try:
        data = {
            "current": cur.to_dict() if cur is not None and cur.message is not None else None,
            "lineups": bot.lineups,
            "roles": {"role_id": bot.player_role_id, "season": bot.role_season, "season_no": bot.role_season_no,
                      "seen": bot.role_seen, "revoke": bot.role_revoke},
            "voice": bot.voice,
        }
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
    if not isinstance(data, dict):
        return
    bot.lineups = [x for x in data.get("lineups") or [] if isinstance(x, dict)]
    roles = data.get("roles")
    if isinstance(roles, dict):  # /선수역할 로 정한 역할과, 누구까지 맞췄는지
        bot.player_role_id = int(roles.get("role_id") or 0) or PLAYER_ROLE_ID
        bot.role_season = str(roles.get("season") or "")
        bot.role_season_no = roles.get("season_no") if isinstance(roles.get("season_no"), int) else None
        bot.role_seen = {k: v for k, v in (roles.get("seen") or {}).items() if isinstance(v, dict)}
        bot.role_revoke = roles.get("revoke") if isinstance(roles.get("revoke"), dict) else None
    voice = data.get("voice")
    if isinstance(voice, dict):  # /시작 에서 골라 둔 음성 채널
        bot.voice = {k: v for k, v in voice.items() if k in VOICE_ROOMS and isinstance(v, int)}
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
# by 는 그 명령어를 쓴 운영진의 디스코드 ID다. 모집 글에 올리는 알림의 맨 앞에 멘션한다(알림은 울리지 않는다).
async def close_recruitment(rec: Recruitment, by: int | None = None) -> None:
    """by 가 없으면 마감 시각이 되어 저절로 마감하는 것이다."""
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
    await post(rec, (f"<@{by}>님이 모집을 마감했어요.\n\n" if by else "") + roster_text, skip=by)

    # 관리자 채널: 같은 명단을 알림 없이 전송하고, 리그 매니저에 붙여넣을 명단을 따로 올린다
    synced = await push_roster(rec) if roster else None
    if synced:
        rec.synced = True
    try:
        admin = await get_channel(ADMIN_CHANNEL_ID)
        for chunk in split_message(f"[모집 종료] 주최: <@{rec.host_id}>\n{roster_text}"):
            await admin.send(chunk, allowed_mentions=discord.AllowedMentions.none())
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


async def extend_recruitment(rec: Recruitment, by: int) -> None:
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
    await post(rec, f"<@{by}>님이 모집을 연장했어요! **{when(rec.end_ts)}까지** `/참여` 로 신청하세요. (<t:{rec.end_ts}:R> 마감)", quiet=True)
    save_state()


async def cancel_recruitment(rec: Recruitment, by: int) -> None:
    rec.closed = True
    rec.cancelled = True
    stop_timer(rec)

    await refresh_announcement(rec)
    mentions = " ".join(f"<@{uid}>" for uid in rec.participants)
    await post(rec, f"<@{by}>님이 이번 내전을 취소했어요." + (f"\n{mentions}" if mentions else ""), skip=by)
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
class ServerError(RuntimeError):
    """리그 서버가 요청을 받지 않았다. code 는 서버가 붙인 까닭('conflict' 등)"""

    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


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
        raise ServerError(result.get("error") or "서버가 요청을 처리하지 못했습니다", result.get("code") or "")
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
    """참가자를 리그 기록의 선수와 맞춘다. 디스코드 사용자 ID → 사용자명 순서로 찾고, 디스코드가 적혀 있지 않은 선수만 이름(서버 별명)으로 찾는다.
    디스코드가 적힌 선수까지 이름으로 찾으면, 서버 별명을 그 선수의 닉네임으로 바꾼 다른 사람이 그 선수의 자리에 들어가
    남의 MMR과 전적으로 경기를 치르게 된다. 리그 매니저는 운영진이 고른 명단을 눈으로 보지만, 봇은 그대로 팀을 짜고 정산한다.
    돌려주는 값: ({선수 id: 디스코드 사용자 ID}, 선수단에서 찾지 못한 참가자의 디스코드 사용자 ID)"""
    def norm(v) -> str:
        return str(v or "").strip().lstrip("@").lower()

    by_discord = {norm(p.get("discord")): p for p in players if norm(p.get("discord"))}
    by_name = {norm(p.get("name")): p for p in players if norm(p.get("name")) and not norm(p.get("discord"))}
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


def signed(v: int) -> str:
    """+12, −12, 0"""
    return "0" if v == 0 else f"{'+' if v > 0 else '−'}{abs(v)}"


def ahead(r: int, d: int) -> str:
    """높은 쪽(🟢 래디언트, 🔴 다이어)과 차이. 같으면 ⚪ 0"""
    return f"{'🟢' if r > d else '🔴'} {abs(r - d)}" if r != d else "⚪ 0"


def lineup_text(result: dict, who: dict[str, int], missing: list[int]) -> str:
    """모집 글에 올릴 팀 편성. who 는 {선수 id: 디스코드 사용자 ID}.
    양식은 운영자가 정했다(2026-10-07): 선수는 닉네임 없이 디스코드 멘션으로만 적고, 열 명 → 쉬는 사람 → MMR 비교(팀 평균, 1~5번, 탑·봇 라인) 순서다.
    값은 리그 매니저의 보드에 보이는 것 그대로다 (matchmaker.js 가 매니저의 계산으로 낸다. 같은 자리끼리의 차이만 여기서 뺀다)."""
    lanes, stats = result["lanes"], result["stats"]
    by_role = {l["role"]: l for l in lanes}

    def at(p: dict) -> str:
        return f"<@{who[p['id']]}>"

    def seat(lane: dict, side: str) -> str:
        p = lane[side]
        return (f"`{lane['role']} {ROLE_NAMES[lane['role'] - 1]}({p['rank'] + 1}지망)` · {at(p)} · {p['mmr']}"
                f" · ({signed(p['win'])} / {signed(p['lose'])})")

    def pair(side: str, roles: list[int]) -> str:
        return " + ".join(at(by_role[r][side]) for r in roles)  # 그 라인에 서는 두 사람

    text = (
        "⚔️ **팀 편성**\n\n"
        f"🟢 **래디언트** (평균 {stats['sR']})\n" + "\n".join(seat(l, "r") for l in lanes) + "\n\n"
        f"🔴 **다이어** (평균 {stats['sD']})\n" + "\n".join(seat(l, "d") for l in lanes) + "\n"
        "-# 괄호 안은 이기면 얻는 점수 / 지면 잃는 점수예요."
    )
    if result["bench"]:
        text += ("\n\n🪑 **이번 판은 쉬어요**: " + ", ".join(at(p) for p in result["bench"])
                 + "\n-# 오늘 아직 안 뛴 사람이 먼저, 그 안에서는 총 판수가 적은 사람이 먼저 출전해요. 판수까지 같으면 지망과 균형으로 정해요.")
    if missing:
        text += "\n\n⚠️ 선수 등록이 확인되지 않아 팀에서 빠졌어요: " + " ".join(f"<@{uid}>" for uid in missing)

    # 팀 평균의 차이는 화면에 보이는 두 평균(반올림한 값)을 뺀 것이다. 매니저의 보드와 같다
    rows = [f"`팀 평균`({ahead(stats['sR'], stats['sD'])}) · 래디언트({stats['sR']}) vs 다이어({stats['sD']})"]
    rows += [f"`{l['role']} {ROLE_NAMES[l['role'] - 1]}`({ahead(l['r']['mmr'], l['d']['mmr'])}) · {at(l['r'])}({l['r']['mmr']}) vs {at(l['d'])}({l['d']['mmr']})"
             for l in lanes]
    rows += [f"`{s['lane']} 라인`({ahead(s['r'], s['d'])}) · {pair('r', s['rRoles'])} ({s['r']}) vs {pair('d', s['dRoles'])} ({s['d']})"
             for s in stats["sides"]]
    return (text + "\n\n📊 **MMR 비교**\n" + "\n".join(rows)
            + "\n-# 🟢는 래디언트가, 🔴는 다이어가 그만큼 높다는 뜻이에요. 팀 평균은 자리별 배율과 지망을 반영한 값이에요.")


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
        await tell_admins("서버의 리그 기록에 선수가 없어 팀을 자동으로 짜지 못했습니다(새 시즌을 막 시작했거나, 매니저를 아직 서버에 연결하지 않은 경우입니다). "
                          "운영진 페이지의 **매니저용 명단 받기**로 받은 파일을 리그 매니저에 불러오고, 데이터 · 설정 탭의 **서버와 자동으로 맞추기**가 켜져 있는지 확인한 뒤 "
                          "`/연장` → `/마감` 하면 다시 짭니다.")
        return

    who, missing = match_players(rec, league["players"])
    if len(who) < PLAYERS_NEEDED:
        await post(rec, f"⚠️ 선수 등록이 확인된 참가자가 {len(who)}명이라 팀을 자동으로 짜지 못했어요. 운영진의 안내를 기다려 주세요.", quiet=True)
        await tell_admins(f"선수단과 맞는 참가자가 {len(who)}명이라 팀을 자동으로 짜지 못했습니다. 선수단에 없는 참가자: "
                          + (" ".join(f"<@{uid}>" for uid in missing) or "없음")
                          + "\n승인한 선수를 리그 매니저에 불러왔는지, 등록한 디스코드 사용자명이 맞는지 확인해 주세요.")
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
    lanes = [{"role": l["role"], "r": l["r"]["id"], "d": l["d"]["id"]} for l in result["lanes"]]
    rec.lineup = True
    bot.lineups.append({
        "at": time.time(),
        "ids": [l[side] for l in lanes for side in ("r", "d")],
        "message_id": rec.message.id if rec.message else 0,
        "place_id": rec.place_id,  # 결과를 알릴 곳 (모집 글)
        "lanes": lanes,
        "who": who,
        "result": None,  # /승리 로 기록하면 {"winner", "match_id"}
    })
    note = ("경기가 끝나면 `/승리` 로 이긴 팀을 골라 결과를 기록하세요. MMR이 정산되고 순위 페이지에 반영됩니다.\n"
            "대타가 뛰었거나 자리를 바꿔 뛰었다면 `/승리` 대신 리그 매니저의 **봇이 짠 팀 불러오기**로 편성을 올린 뒤 고쳐서 기록하세요.")
    try:
        await call_server({"action": "pushLineup", "lineup": {
            "post": getattr(rec.message, "jump_url", ""), "lanes": lanes, "bench": [p["id"] for p in result["bench"]],
        }})
    except Exception as e:
        print(f"짠 팀을 리그 서버에 올리지 못했습니다: {e!r}")
        note += "\n짠 팀을 리그 서버에 올리지 못해서, 매니저의 **봇이 짠 팀 불러오기**는 이번 판에 쓸 수 없습니다."
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


# ── 경기 결과 정산 ────────────────────────────────────────────
def lineup_of(rec: Recruitment) -> dict | None:
    """이 모집으로 짠 팀"""
    message_id = rec.message.id if rec.message else 0
    return next((x for x in bot.lineups if x.get("message_id") == message_id and x.get("lanes")), None)


def settled(rec: Recruitment) -> bool:
    """이 모집으로 짠 팀의 결과를 이미 기록했는지"""
    entry = lineup_of(rec)
    return bool(entry and entry.get("result"))


async def change_league(payload: dict) -> dict:
    """서버의 리그 기록을 받아 matchmaker.js 로 고친 뒤 다시 올린다.
    받아 온 사이에 매니저가 기록을 바꿨으면 서버가 받지 않으므로, 새 기록으로 한 번 더 한다."""
    for attempt in (1, 2):
        got = await call_server({"action": "adminLeague"})
        if not got.get("league"):
            raise RuntimeError("서버에 리그 기록이 없습니다")
        result = await run_matchmaker({**payload, "league": got["league"], "now": int(time.time() * 1000)})
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "알 수 없는 문제")
        try:
            await call_server({"action": "saveLeague", "league": result["league"], "baseRev": got.get("rev", 0)})
            return result
        except ServerError as e:
            if e.code != "conflict" or attempt == 2:
                raise
    raise RuntimeError("기록을 올리지 못했습니다")  # 여기까지 오지 않는다


def result_text(winner: str, changes: list[dict], who: dict) -> str:
    """모집 글에 올릴 경기 결과. 선수마다 MMR이 어떻게 바뀌었는지 보여 준다. who 는 {선수 id: 디스코드 사용자 ID}
    팀 편성 공지처럼 선수는 디스코드 멘션으로만 적는다 (디스코드 계정을 모르는 선수만 닉네임으로)."""
    def line(c: dict) -> str:
        uid = who.get(c["id"])
        return (f"`{c['role']} {ROLE_NAMES[c['role'] - 1]}` · {f'<@{uid}>' if uid else safe_name(c['name'])}"
                f" · {c['before']} → **{c['after']}** ({'+' if c['delta'] >= 0 else '−'}{abs(c['delta'])})")

    def team(side: str) -> str:
        return "\n".join(line(c) for c in sorted((c for c in changes if c["side"] == side), key=lambda c: c["role"]))

    return (
        f"🏆 **{'래디언트' if winner == 'r' else '다이어'} 승리!** MMR을 정산했어요.\n\n"
        f"🟢 **래디언트**{' · 승' if winner == 'r' else ''}\n{team('r')}\n\n"
        f"🔴 **다이어**{' · 승' if winner == 'd' else ''}\n{team('d')}"
    )


async def send_to(place_id: int, text: str) -> None:
    """모집 글(또는 채널)에 알림을 울리지 않고 메시지를 보낸다. 실패해도 넘어간다."""
    try:
        place = await get_channel(place_id)
        thread = place if isinstance(place, discord.Thread) else None
        await awake(thread, lambda: place.send(text, allowed_mentions=discord.AllowedMentions.none()))
    except discord.HTTPException as e:
        print(f"결과 공지 실패: {e}")


# ── 참여 선수 역할 자동 부여 ──────────────────────────────────
# 운영진 페이지에서 승인한 선수에게 역할을 주고, 제외한 선수에게서는 뺀다. 대기는 건드리지 않는다.
# 봇에는 서버가 승인을 알려 올 길이 없어서(봇은 밖에서 들어오는 요청을 받지 않는다) 등록 명단을 주기적으로 읽어 맞춘다.
async def get_guild() -> discord.Guild:
    guild = bot.get_guild(GUILD.id)
    if guild is None:
        guild = await bot.fetch_guild(GUILD.id)
    return guild


def role_problem(guild: discord.Guild, role: discord.Role | None) -> str:
    """봇이 이 역할을 주고 뺄 수 없는 까닭. 할 수 있으면 빈 글."""
    if role is None:
        return "정해 둔 역할을 찾지 못했어요. 지웠다면 `/선수역할` 로 다시 정해 주세요."
    if role.is_default() or role.managed:
        return f"**{role.name}** 역할은 봇이 줄 수 없어요(@everyone 이거나 다른 봇·연동이 관리하는 역할)."
    me = guild.me
    if me is None:
        return ""
    if not me.guild_permissions.manage_roles:
        return "봇에 **역할 관리** 권한이 없어요. 서버 설정 → 역할에서 봇의 역할에 **역할 관리**를 켜 주세요."
    if me.top_role <= role:
        return f"봇의 역할이 **{role.name}** 역할보다 아래에 있어요. 서버 설정 → 역할에서 봇의 역할을 **{role.name}** 위로 끌어 올려 주세요."
    return ""


async def role_status() -> str:
    """지금 설정을 한 줄로 (켤 때 창에 찍고, /선수역할 에 답할 때 쓴다)"""
    if not bot.player_role_id:
        return "꺼짐 (디스코드 관리자 채널에서 `/선수역할` 로 줄 역할을 정하면 켜집니다)"
    if not (SYNC_URL and SYNC_KEY):
        return "꺼짐 (config.json 에 sync_url 과 sync_key 가 있어야 합니다)"
    try:
        guild = await get_guild()
        role = guild.get_role(bot.player_role_id)
    except discord.HTTPException as e:
        return f"[확인 필요] 디스코드 서버를 확인하지 못했습니다 ({e})"
    problem = role_problem(guild, role)
    return f"[확인 필요] {problem}" if problem else f"켜짐 (@{role.name})"


async def find_member(guild: discord.Guild, name: str) -> discord.Member | None:
    """등록할 때 적은 디스코드(사용자명 또는 숫자로 된 사용자 ID)로 서버의 멤버를 찾는다. 서버에 없으면 None"""
    name = str(name or "").strip().lstrip("@").lower()
    if not name:
        return None
    if re.fullmatch(r"\d{17,20}", name):
        try:
            return await guild.fetch_member(int(name))
        except discord.NotFound:
            return None
    base, _, tag = name.partition("#")  # 예전 방식(이름#1234)도 받는다
    if not base:
        return None
    # 이름이나 별명이 이 글자로 시작하는 멤버를 받아, 사용자명이 똑같은 사람만 고른다
    for member in await guild.query_members(query=base, limit=100):
        if member.name.lower() == base and (not tag or member.discriminator == tag):
            return member
    return None


async def sync_roles(force: bool = False) -> dict:
    """등록 명단의 상태에 맞춰 역할을 주고 뺀다. 이미 맞춘 등록은 건너뛰고, 상태나 디스코드가 바뀐 등록만 다시 본다.
    force 면 서버에서 찾지 못했던 사람도 기다리지 않고 다시 찾아본다.
    시즌이 넘어간 것을 알면 먼저 지난 시즌 선수의 역할을 거둔다(봇이 꺼져 있는 동안 넘어갔으면 켠 뒤의 첫 차례에 한다).
    돌려주는 값: {"added": [멤버], "removed": [멤버], "missing": [등록], "problem": 까닭, "left": 다음 차례로 미룬 수, "revoked": 거둔 결과}"""
    out = {"added": [], "removed": [], "missing": [], "problem": "", "left": 0, "revoked": None}
    if not bot.player_role_id or not (SYNC_URL and SYNC_KEY):
        return out
    async with bot.role_lock:
        data = await call_server({"action": "adminList"})
        guild = await get_guild()
        role = guild.get_role(bot.player_role_id)
        out["problem"] = role_problem(guild, role)
        if out["problem"]:
            return out

        season, no = str(data.get("season") or ""), data.get("seasonNo")
        if not isinstance(no, int):  # 시즌 번호를 주지 않는 예전 서버: 이름이 바뀌면 명단을 처음부터 다시 맞추기만 한다
            if season != bot.role_season:
                bot.role_seen = {}
        elif bot.role_season_no is None:  # 처음 본 시즌. 거둘 것은 없다
            bot.role_season_no = no
            save_state()
        elif no < bot.role_season_no:  # 번호가 줄었다: 다른 시트(서버)로 옮긴 경우. 처음부터 다시 맞춘다
            bot.role_season_no, bot.role_seen, bot.role_revoke = no, {}, None
            save_state()
        elif no > bot.role_season_no and bot.role_revoke is None:  # 시즌이 넘어갔다. 끝난 시즌의 선수에게서 역할을 거둔다
            bot.role_revoke = await revoke_plan(bot.role_season_no, no, data)
            save_state()
        bot.role_season = season
        if bot.role_revoke is not None:
            if not await revoke_step(guild, role, out):
                return out  # 다 거둔 뒤에 새 시즌의 승인 선수에게 준다
        seen, now, tried, changed = bot.role_seen, time.time(), 0, False
        for p in data.get("players") or []:
            key, status, name = str(p.get("steamKey") or p.get("discord") or ""), p.get("status"), str(p.get("discord") or "")
            if not key or status not in ("승인", "제외"):
                continue
            last = seen.get(key) or {}
            same = last.get("status") == status and last.get("discord") == name
            if same and last.get("ok"):
                continue
            if same and not force and now - last.get("tried", 0) < ROLE_RETRY_SECONDS:
                continue
            if tried >= ROLE_BATCH:
                out["left"] += 1
                continue
            tried += 1
            done = True
            try:
                member = await find_member(guild, name)
                if member is None:
                    # 제외한 사람이 서버에 없으면 뺄 역할도 없다. 승인한 사람이 없으면 나중에 다시 찾아본다
                    done = status == "제외"
                    if not done and not same:  # 처음 못 찾았을 때만 알린다
                        out["missing"].append(p)
                elif status == "승인" and role not in member.roles:
                    await member.add_roles(role, reason="인하우스 리그 등록 승인")
                    out["added"].append(member)
                elif status == "제외" and role in member.roles:
                    await member.remove_roles(role, reason="인하우스 리그 등록 제외")
                    out["removed"].append(member)
            except discord.Forbidden:
                out["problem"] = "역할을 바꿀 권한이 없어요. 봇에 **역할 관리** 권한이 있는지, 봇의 역할이 그 역할보다 위에 있는지 확인해 주세요."
                break
            except (discord.HTTPException, asyncio.TimeoutError) as e:  # 디스코드가 잠깐 답하지 않았다. 나중에 다시 한다
                print(f"참여 선수 역할: {name} 을(를) 처리하지 못했습니다: {e!r}")
                done = False
            seen[key] = {"status": status, "discord": name, "ok": done, "tried": now}
            changed = True
        if changed:
            save_state()
    return out


async def revoke_plan(old_no: int, new_no: int, current: dict) -> dict:
    """시즌이 넘어갔을 때 역할을 거둘 사람을 모은다: 끝난 시즌들(old_no 부터 new_no 앞까지)의 등록 명단에 있는 사람과, 봇이 역할을 줬던 사람.
    새 시즌에 이미 승인된 사람은 뺀다(거뒀다가 바로 다시 주지 않으려고).
    누가 역할을 갖고 있는지를 디스코드에 물을 수는 없어서(특권 인텐트가 필요하다) 명단으로 찾는다.
    그래서 등록한 적 없이 손으로 역할을 받은 사람은 여기에 들어가지 않는다."""
    keep = {str(p.get("discord") or "") for p in current.get("players") or [] if p.get("status") == "승인"}
    names: list[str] = []

    def add(name) -> None:
        name = str(name or "")
        if name and name not in keep and name not in names:
            names.append(name)

    for k in range(old_no, new_no):
        past = await call_server({"action": "adminList", "seasonNo": k})
        for p in past.get("players") or []:
            add(p.get("discord"))
    for v in bot.role_seen.values():
        add(v.get("discord"))
    return {"to": new_no, "left": names, "removed": 0, "total": len(names), "stuck": 0}


async def revoke_step(guild: discord.Guild, role: discord.Role, out: dict) -> bool:
    """거둘 사람을 한 번에 ROLE_BATCH 명까지 확인해 역할을 뺀다. 다 끝났으면 True (그때 새 시즌으로 넘어간다)."""
    plan = bot.role_revoke
    for _ in range(ROLE_BATCH):
        if not plan["left"]:
            break
        name = plan["left"][0]
        try:
            member = await find_member(guild, name)
            if member is not None and role in member.roles:
                await member.remove_roles(role, reason="인하우스 리그 시즌 종료")
                plan["removed"] += 1
        except discord.Forbidden:
            out["problem"] = "시즌이 바뀌어 역할을 거두려 했지만 권한이 없어요. 봇에 **역할 관리** 권한이 있는지, 봇의 역할이 그 역할보다 위에 있는지 확인해 주세요."
            break
        except (discord.HTTPException, asyncio.TimeoutError) as e:  # 디스코드가 잠깐 답하지 않았다. 다음 차례에 이어서 한다
            print(f"참여 선수 역할: {name} 의 역할을 거두지 못했습니다: {e!r}")
            plan["stuck"] = plan.get("stuck", 0) + 1
            if plan["stuck"] < 5:
                break
        plan["left"].pop(0)  # 다섯 번 내리 실패한 사람은 건너뛴다 (한 사람 때문에 멈춰 있지 않게)
        plan["stuck"] = 0
    if plan["left"]:
        save_state()
        return False
    out["revoked"] = {"removed": plan["removed"], "total": plan["total"]}
    bot.role_season_no, bot.role_seen, bot.role_revoke = plan["to"], {}, None
    save_state()
    return True


def roles_text(out: dict) -> str:
    """역할을 맞춘 결과를 관리자 채널에 알릴 글. 알릴 것이 없으면 빈 글."""
    lines = []
    if out.get("revoked"):
        lines.append(f"🔄 시즌이 바뀌어 지난 시즌 선수의 역할을 거뒀어요: {out['revoked']['removed']}명 (명단 {out['revoked']['total']}명 확인)")
    if out["added"]:
        lines.append("✅ 승인 → 역할을 줬어요: " + ", ".join(m.mention for m in out["added"]))
    if out["removed"]:
        lines.append("🚫 제외 → 역할을 뺐어요: " + ", ".join(m.mention for m in out["removed"]))
    if out["missing"]:
        lines.append("⚠️ 디스코드 서버에서 찾지 못했어요: "
                     + ", ".join(f"{safe_name(str(p.get('nickname') or '?'))} (`{str(p.get('discord') or '').replace('`', '')}`)" for p in out["missing"])
                     + "\n서버에 들어와 있는지, 등록한 디스코드 사용자명이 맞는지 확인해 주세요. 10분마다 다시 찾아봅니다.")
    return ("🎫 **참여 선수 역할**\n" + "\n".join(lines)) if lines else ""


async def role_tick() -> None:
    """등록 명단을 한 번 읽어 역할을 맞추고, 바뀐 것이 있을 때만 관리자 채널에 알린다."""
    out = await sync_roles()
    text = roles_text(out)
    if text:
        await tell_admins(text)
    # 권한 문제는 같은 내용을 되풀이해 알리지 않는다. 풀렸다가 다시 생기면 또 알린다
    if out["problem"] and out["problem"] != bot.role_note:
        await tell_admins("🎫 **참여 선수 역할**을 맞추지 못했어요. " + out["problem"])
    bot.role_note = out["problem"]


async def role_loop() -> None:
    """켜 둔 동안 주기적으로 역할을 맞춘다."""
    while True:
        try:
            await role_tick()
        except Exception as e:  # 서버나 디스코드가 잠깐 답하지 않아도 다음 차례에 다시 한다
            print(f"참여 선수 역할 맞추기 실패: {e!r}")
        await asyncio.sleep(ROLE_POLL_SECONDS)


# ── 음성 채널 이동 (/시작, /종료) ──────────────────────────────
# 경기를 시작할 때 로비 음성 채널에 있는 선수를 배정된 팀의 음성 채널로 옮기고, 끝나면 팀 채널의 모두를 로비로 되돌린다.
# 누가 음성 채널에 있는지는 특권 인텐트 없이 안다(음성 상태는 기본 인텐트에 들어 있다). 옮기려면 봇에 멤버 이동 권한이 있어야 한다.
ROOM_NAMES = {"lobby": "로비", "radiant": "래디언트", "dire": "다이어"}


def voice_rooms(guild: discord.Guild) -> tuple[dict, str]:
    """로비·래디언트·다이어 음성 채널을 찾는다. 돌려주는 값: ({"lobby": 채널, "radiant": 채널, "dire": 채널}, 찾지 못한 까닭)
    /시작 에서 골라 둔 채널이 먼저다. 고른 적이 없는 것은, 이름에 그 낱말이 든 음성 채널이 서버에 하나뿐일 때 그 채널을 쓴다."""
    rooms, unknown = {}, []
    for key, words in VOICE_ROOMS.items():
        channel = guild.get_channel(bot.voice[key]) if bot.voice.get(key) else None
        if not isinstance(channel, discord.VoiceChannel):  # 고른 적이 없거나, 골라 둔 채널이 지워졌다
            named = [c for c in guild.voice_channels if any(w in c.name.lower().replace(" ", "") for w in words)]
            channel = named[0] if len(named) == 1 else None
        if channel is None:
            unknown.append(ROOM_NAMES[key])
        else:
            rooms[key] = channel
    how = "`/시작` 을 입력할 때 **로비**·**래디언트**·**다이어** 칸에서 음성 채널을 골라 주세요. 한 번 고르면 기억합니다."
    if unknown:
        return rooms, f"{'·'.join(unknown)} 음성 채널을 찾지 못했어요. {how}"
    if len({channel.id for channel in rooms.values()}) < len(rooms):
        return rooms, f"로비·래디언트·다이어는 서로 다른 음성 채널이어야 해요. {how}"
    return rooms, ""


def voice_problem(guild: discord.Guild, targets: list) -> str:
    """봇이 사람들을 targets(음성 채널)로 옮길 수 없는 까닭. 옮길 수 있으면 빈 글."""
    me = guild.me
    if me is None:
        return ""
    for channel in targets:
        perms = channel.permissions_for(me)
        if not perms.move_members:
            return "봇에 **멤버 이동** 권한이 없어요. 서버 설정 → 역할에서 봇의 역할에 **멤버 이동**을 켜 주세요."
        if not (perms.view_channel and perms.connect):
            return f"봇이 {channel.mention} 에 들어갈 수 없어요. 그 채널의 권한에서 봇에게 **채널 보기**와 **연결**을 허용해 주세요."
    return ""


async def voice_setup(picked: dict[str, int] | None = None) -> tuple[discord.Guild, dict, str, str]:
    """/시작·/종료 가 쓸 음성 채널을 정한다. picked 는 방금 명령어에서 고른 채널 {"lobby": 채널 ID, …}.
    돌려주는 값: (서버, {"lobby": 채널, …}, 쓸 수 없는 까닭, 채널을 새로 기억했을 때 운영진에게 덧붙일 안내)
    세 곳을 다 찾으면 state.json 에 적어 둔다. 나중에 비슷한 이름의 채널이 생겨도 쓰던 채널을 그대로 쓰게 하려는 것이다."""
    before = dict(bot.voice)
    if picked:
        bot.voice.update(picked)
    guild = await get_guild()
    rooms, problem = voice_rooms(guild)
    if not problem:
        bot.voice = {key: rooms[key].id for key in VOICE_ROOMS}
    note = ""
    if bot.voice != before:
        save_state()
        if not problem:
            note = ("\n음성 채널을 기억했어요: " + " · ".join(f"{ROOM_NAMES[key]} {rooms[key].mention}" for key in VOICE_ROOMS)
                    + ". 바꾸려면 `/시작` 의 로비·래디언트·다이어 칸에서 고르세요.")
    return guild, rooms, problem, note


async def voice_status() -> str:
    """지금 설정을 한 줄로 (켤 때 창에 찍는다)"""
    try:
        guild = await get_guild()
    except discord.HTTPException as e:
        return f"[확인 필요] 디스코드 서버를 확인하지 못했습니다 ({e})"
    rooms, problem = voice_rooms(guild)
    if problem:
        return "음성 채널을 아직 모릅니다 (디스코드에서 `/시작` 을 입력할 때 로비·래디언트·다이어 채널을 고르면 됩니다)"
    problem = voice_problem(guild, list(rooms.values()))
    names = ", ".join(f"{ROOM_NAMES[key]} #{rooms[key].name}" for key in VOICE_ROOMS)
    return f"{names} [확인 필요] {problem}" if problem else f"{names} - 권한 확인"


async def move_people(guild: discord.Guild, moves: list[tuple[int, discord.VoiceChannel]], reason: str) -> tuple[set[int], list[int], bool]:
    """음성 채널에 있는 사람들을 한꺼번에 옮긴다. moves 는 [(디스코드 ID, 옮길 채널)].
    돌려주는 값: (옮긴 사람, 옮기지 못한 사람, 권한이 없어서 못 옮겼는지). 그사이 음성 채널에서 나간 사람은 옮기지 못한 사람에 든다."""
    async def one(uid: int, channel: discord.VoiceChannel) -> None:
        member = guild.get_member(uid) or await guild.fetch_member(uid)
        await member.move_to(channel, reason=reason)

    results = await asyncio.gather(*(one(uid, channel) for uid, channel in moves), return_exceptions=True)
    failed = [uid for (uid, _), r in zip(moves, results) if isinstance(r, BaseException)]
    for r in results:
        if isinstance(r, BaseException) and not isinstance(r, discord.HTTPException):
            print(f"음성 채널 이동 실패: {r!r}")
    return {uid for uid, _ in moves} - set(failed), failed, any(isinstance(r, discord.Forbidden) for r in results)


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


def by(interaction: discord.Interaction) -> str:
    """명령어를 쓴 운영진의 멘션. 운영진 명령어로 봇이 올리는 글은 모두 이 멘션으로 시작한다 (운영자가 정한 규칙, 2026-10-07).
    한 일을 알릴 때는 '@운영진님이 …했어요', 운영진을 대신해 전하는 안내는 '@운영진: …', 운영진에게 하는 말은 '@운영진님, …' 꼴로 쓴다.
    본인에게만 보이는 안내(ephemeral)에는 붙이지 않는다."""
    return f"<@{interaction.user.id}>"


async def answer(interaction: discord.Interaction, text: str) -> None:
    """운영진 명령어에 관리자 채널에서 답한다. 길면 나눠 보내고, 멘션 알림은 울리지 않는다."""
    for chunk in split_message(text):
        await interaction.followup.send(chunk, allowed_mentions=discord.AllowedMentions.none())


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
    actor = by(interaction)

    async with bot.lock:
        # 글을 올리는 사이에 다른 운영진이 먼저 만들었을 수 있으니 다시 확인한다
        if bot.current is not None and not bot.current.closed:
            await answer(interaction, f"{actor}님, " + busy.format(bot.current.end_ts))
            return
        rec = Recruitment(host_id=interaction.user.id, end_ts=end_ts or deadline_after(SIGNUP_SECONDS))
        try:
            await open_signup(rec, title_ts=end_ts)
        except discord.HTTPException as e:
            await answer(interaction, f"{actor}님, 모집 글을 올리지 못했어요. 봇 권한과 채널 ID를 확인해 주세요. ({e})")
            return
        bot.current = rec  # 모집 글이 올라간 뒤에 등록해서, 다른 명령어가 준비되지 않은 모집을 보지 않게 한다
        rec.task = asyncio.create_task(close_when_due(rec))
        save_state()

    waiting = any(x.get("lanes") and not x.get("result") for x in bot.lineups)
    await answer(
        interaction,
        f"{actor}님이 모집을 시작했어요! {rec.message.jump_url}\n마감: {when(rec.end_ts)} (<t:{rec.end_ts}:R>)"
        + ("\n⚠️ 결과를 아직 기록하지 않은 판이 있어요. 끝났다면 `/승리` 로 기록하고, 팀만 짜고 열리지 않은 판이면 `/승리` 에서 **경기 안 함**을 골라 주세요."
           if waiting else ""),
    )


@bot.tree.command(name="마감", description="지금까지 모인 인원으로 모집을 바로 마감합니다 (운영진 전용)", guild=GUILD)
async def close_now(interaction: discord.Interaction) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    actor = by(interaction)
    async with bot.lock:
        rec = bot.current
        if rec is None or rec.closed:
            await answer(interaction, f"{actor}님, 지금은 모집 중인 내전이 없어요.")
            return
        await close_recruitment(rec, by=interaction.user.id)
    await answer(interaction, f"{actor}님이 모집을 마감했어요. (최종 {len(rec.participants)}명)")


@bot.tree.command(
    name="연장",
    description=f"모집 마감을 {minutes_text(EXTEND_SECONDS)} 뒤로 미룹니다. 마감한 뒤에도 다시 열 수 있어요 (운영진 전용)",
    guild=GUILD,
)
async def extend(interaction: discord.Interaction) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    actor = by(interaction)
    async with bot.lock:
        rec = bot.current
        if rec is None or rec.cancelled:
            await answer(interaction, f"{actor}님, 연장할 내전이 없어요. `/내전생성` 으로 새로 모집해 주세요.")
            return
        if settled(rec):
            await answer(interaction, f"{actor}님, 이미 경기 결과를 기록한 내전이에요. 새로 모집하려면 `/내전생성` 을 쓰세요.")
            return
        reopened = rec.closed
        await extend_recruitment(rec, by=interaction.user.id)
    await answer(
        interaction,
        f"{actor}님이 " + ("마감한 모집을 다시 열었어요." if reopened else "모집을 연장했어요.")
        + f" 새 마감: {when(rec.end_ts)} (<t:{rec.end_ts}:R>)",
    )


@bot.tree.command(name="취소", description="이번 내전을 취소합니다 (운영진 전용)", guild=GUILD)
async def cancel(interaction: discord.Interaction) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    actor = by(interaction)
    async with bot.lock:
        rec = bot.current
        if rec is None or rec.cancelled:
            await answer(interaction, f"{actor}님, 취소할 내전이 없어요.")
            return
        if settled(rec):
            await answer(interaction, f"{actor}님, 이미 경기 결과를 기록한 내전이에요. 결과를 되돌리려면 `/승리취소` 를 쓰세요.")
            return
        await cancel_recruitment(rec, by=interaction.user.id)
    await answer(interaction, f"{actor}님이 내전을 취소했어요." + (f" {rec.message.jump_url}" if rec.message else ""))


@bot.tree.command(name="시작", description="로비 음성 채널에 있는 선수를 배정된 팀의 음성 채널로 옮깁니다 (운영진 전용)", guild=GUILD)
@app_commands.rename(lobby="로비", radiant="래디언트", dire="다이어")
@app_commands.describe(lobby="선수들이 모여 있는 음성 채널. 한 번 고르면 기억하니 다음부터는 비워 두세요",
                       radiant="래디언트 팀이 쓸 음성 채널", dire="다이어 팀이 쓸 음성 채널")
async def start_game(interaction: discord.Interaction, lobby: Optional[discord.VoiceChannel] = None,
                     radiant: Optional[discord.VoiceChannel] = None, dire: Optional[discord.VoiceChannel] = None) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    actor = by(interaction)
    sides = (("radiant", "r"), ("dire", "d"))
    async with bot.lock:
        picked = {key: channel.id for key, channel in (("lobby", lobby), ("radiant", radiant), ("dire", dire)) if channel is not None}
        guild, rooms, problem, note = await voice_setup(picked)
        if problem:
            await answer(interaction, f"{actor}님, {problem}")
            return
        # 결과를 아직 기록하지 않은 팀 가운데 가장 나중에 짠 것 (이제 시작할 판)
        entry = next((x for x in reversed(bot.lineups) if x.get("lanes") and not x.get("result")), None)
        if entry is None:
            await answer(interaction, f"{actor}님, 배정된 팀이 없어서 옮길 사람이 없어요. 봇이 팀을 짜서 알린 뒤에 쓸 수 있어요.{note}")
            return
        problem = voice_problem(guild, [rooms["radiant"], rooms["dire"]])
        if problem:
            await answer(interaction, f"{actor}님, {problem}{note}")
            return
        who = entry.get("who") or {}
        seats = {side: [who[lane[s]] for lane in entry["lanes"] if lane[s] in who] for side, s in sides}
        waiting = set(rooms["lobby"].voice_states)  # 로비에 있는 사람
        moves = [(uid, rooms[side]) for side, _ in sides for uid in seats[side] if uid in waiting]
        placed = {uid for side, _ in sides for uid in seats[side] if uid in rooms[side].voice_states}  # 이미 자기 팀 채널에 와 있는 선수
        absent = [uid for side, _ in sides for uid in seats[side] if uid not in waiting and uid not in placed]
        if not moves:
            where = "" if not absent else " 로비에 없는 선수: " + ", ".join(f"<@{uid}>" for uid in absent)
            await answer(interaction, (f"{actor}님, 선수들이 이미 각자의 팀 음성 채널에 있어요." if placed and not absent
                                       else f"{actor}님, {rooms['lobby'].mention} 에 배정된 선수가 없어서 아무도 옮기지 않았어요.{where}") + note)
            return
        entry["started"] = time.time()  # /종료 가 끝났다는 안내를 이 판의 모집 글에 올린다
        entry.pop("ended", None)
        save_state()
        notice = f"{actor}: 게임이 시작되어 선수들을 각자의 음성 채널로 이동시킵니다."
        await send_to(entry["place_id"], notice)
        moved, failed, denied = await move_people(guild, moves, "내전 시작 (/시작)")
    lines = [notice, " · ".join(f"{mark} {rooms[side].mention} {sum(uid in moved for uid in seats[side])}명" for mark, side in (("🟢", "radiant"), ("🔴", "dire")))
             + "을 옮겼어요."]
    if absent:
        lines.append("로비에 없어서 옮기지 못한 선수: " + ", ".join(f"<@{uid}>" for uid in absent))
    if failed:
        lines.append(("⚠️ 봇에 **멤버 이동** 권한이 없어 옮기지 못한 선수: " if denied else "⚠️ 옮기지 못한 선수(그사이 음성 채널에서 나갔을 수 있어요): ")
                     + ", ".join(f"<@{uid}>" for uid in failed))
    await answer(interaction, "\n".join(lines) + note)


@bot.tree.command(name="종료", description="래디언트·다이어 음성 채널에 있는 사람을 모두 로비 음성 채널로 옮깁니다 (운영진 전용)", guild=GUILD)
async def end_game(interaction: discord.Interaction) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    actor = by(interaction)
    async with bot.lock:
        guild, rooms, problem, note = await voice_setup()
        problem = problem or voice_problem(guild, [rooms["lobby"]])
        if problem:
            await answer(interaction, f"{actor}님, {problem}{note}")
            return
        people = [uid for side in ("radiant", "dire") for uid in rooms[side].voice_states]
        if not people:
            await answer(interaction, f"{actor}님, {rooms['radiant'].mention} 와 {rooms['dire'].mention} 에 아무도 없어서 옮길 사람이 없어요.{note}")
            return
        notice = f"{actor}: 게임이 종료되어 모든 선수를 로비로 이동시킵니다."
        entry = next((x for x in reversed(bot.lineups) if x.get("started") and not x.get("ended")), None)  # /시작 으로 시작한 판
        if entry is not None:
            entry["ended"] = time.time()
            save_state()
            await send_to(entry["place_id"], notice)
        moved, failed, denied = await move_people(guild, [(uid, rooms["lobby"]) for uid in people], "내전 종료 (/종료)")
    lines = [notice, f"{rooms['lobby'].mention} 로 {len(moved)}명을 옮겼어요."]
    if failed:
        lines.append(("⚠️ 봇에 **멤버 이동** 권한이 없어 옮기지 못한 사람: " if denied else "⚠️ 옮기지 못한 사람(그사이 음성 채널에서 나갔을 수 있어요): ")
                     + ", ".join(f"<@{uid}>" for uid in failed))
    await answer(interaction, "\n".join(lines) + note)


@bot.tree.command(name="승리", description="봇이 짠 팀의 경기 결과를 기록하고 MMR을 정산합니다 (운영진 전용)", guild=GUILD)
@app_commands.rename(team="팀")
@app_commands.describe(team="이긴 팀. 팀만 짜고 경기를 하지 않은 판이면 '경기 안 함'을 고르세요")
@app_commands.choices(team=[app_commands.Choice(name="래디언트", value="r"), app_commands.Choice(name="다이어", value="d"),
                            app_commands.Choice(name="경기 안 함 (이 판을 기록 없이 정리)", value="x")])
async def record_win(interaction: discord.Interaction, team: str) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    actor = by(interaction)
    async with bot.lock:
        # 결과를 기다리는 팀 가운데 가장 먼저 짠 것 (보통은 방금 끝난 판 하나뿐이다)
        entry = next((x for x in bot.lineups if x.get("lanes") and not x.get("result")), None)
        if entry is None:
            recorded = any(x.get("result") for x in bot.lineups)
            await answer(
                interaction,
                f"{actor}님, 결과를 기다리는 팀이 없어요. 이미 기록한 결과를 고치려면 `/승리취소` 로 되돌린 뒤 다시 기록하세요." if recorded
                else f"{actor}님, 결과를 기록할 팀이 없어요. 봇이 팀을 짜서 알린 뒤에 쓸 수 있어요.",
            )
            return
        waiting = sum(1 for x in bot.lineups if x.get("lanes") and not x.get("result")) - 1  # 이 판 말고 결과를 기다리는 판
        more = f"\n결과를 기다리는 판이 {waiting}개 더 있어요. 이어서 `/승리` 로 정리해 주세요." if waiting else ""
        if team == "x":
            # 팀만 짜고 열리지 않은 판은 기록 없이 치운다. 그대로 두면 다음 /승리 가 이 판에 적용되고, 이 판의 열 명이 오늘 뛴 사람으로 남는다
            newest = entry is bot.lineups[-1]
            bot.lineups.remove(entry)
            cur = bot.current
            if cur is not None and cur.message is not None and cur.message.id == entry.get("message_id"):
                cur.lineup = False
            save_state()
            if newest:  # 서버에 올려 둔 편성이 이 판의 것이다. 매니저가 열리지 않은 판을 불러오지 않게 비운다
                try:
                    await call_server({"action": "pushLineup", "lineup": None})
                except Exception as e:
                    print(f"리그 서버의 팀 편성을 비우지 못했습니다: {e!r}")
            await send_to(entry["place_id"], f"{actor}님이 이 판을 경기 없이 정리했어요. 결과는 기록되지 않습니다.")
            await answer(interaction, f"{actor}님이 <#{entry['place_id']}> 의 판을 경기 없이 정리했어요. 결과와 MMR은 바뀌지 않습니다.{more}")
            return
        try:
            result = await change_league({"mode": "result", "lanes": entry["lanes"], "winner": team})
        except Exception as e:
            print(f"결과 기록 실패: {e!r}")
            await answer(interaction, f"{actor}님, 결과를 기록하지 못했어요. 리그 매니저에서 기록해 주세요. ({e})")
            return
        entry["result"] = {"winner": team, "match_id": result["match"]["id"]}
        save_state()
        text = f"{actor}님이 경기 결과를 기록했어요.\n" + result_text(team, result["changes"], entry.get("who") or {})
        await send_to(entry["place_id"], text)
    await answer(interaction, f"{text}\n\n순위 페이지와 구글 시트에 반영했어요. 잘못 기록했다면 `/승리취소` 로 되돌릴 수 있어요.{more}")


@bot.tree.command(name="승리취소", description="/승리 로 기록한 마지막 결과를 되돌립니다 (운영진 전용)", guild=GUILD)
async def undo_win(interaction: discord.Interaction) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    actor = by(interaction)
    async with bot.lock:
        entry = next((x for x in reversed(bot.lineups) if x.get("result")), None)  # 가장 최근에 결과를 기록한 팀
        if entry is None:
            await answer(interaction, f"{actor}님, 되돌릴 결과가 없어요. `/승리` 로 기록한 결과만 되돌릴 수 있어요.")
            return
        try:
            await change_league({"mode": "undo", "matchId": entry["result"]["match_id"]})
        except Exception as e:
            print(f"결과 되돌리기 실패: {e!r}")
            await answer(interaction, f"{actor}님, 결과를 되돌리지 못했어요. 리그 매니저에서 고쳐 주세요. ({e})")
            return
        entry["result"] = None
        save_state()
        await send_to(entry["place_id"], f"{actor}님이 경기 결과 기록을 취소했어요. MMR과 전적을 기록하기 전으로 되돌렸어요.")
    await answer(interaction, f"{actor}님이 결과 기록을 취소하고 MMR을 되돌렸어요. 다시 기록하려면 `/승리` 를 쓰세요.")


@bot.tree.command(name="선수역할", description="승인한 선수에게 자동으로 줄 역할을 정합니다. 제외한 선수에게서는 뺍니다 (운영진 전용)", guild=GUILD)
@app_commands.rename(role="역할", off="끄기")
@app_commands.describe(role="승인한 선수에게 줄 역할. 비우면 지금 설정을 보여 주고 바로 한 번 맞춥니다", off="자동으로 역할 주기를 끕니다")
async def player_role(interaction: discord.Interaction, role: Optional[discord.Role] = None, off: Optional[bool] = None) -> None:
    if not await admin_only(interaction):
        return
    await interaction.response.defer()
    actor = by(interaction)
    if off:
        # 꺼 둔 동안 시즌이 넘어가도, 다시 켰을 때 역할을 거두지 않도록 시즌 번호도 잊는다
        bot.player_role_id, bot.role_seen, bot.role_season_no, bot.role_revoke = 0, {}, None, None
        save_state()
        await answer(interaction, f"{actor}님이 참여 선수 역할 자동 부여를 껐어요. 이미 준 역할은 그대로 둡니다. 다시 켜려면 `/선수역할` 에서 역할을 골라 주세요.")
        return
    if role is not None:
        problem = role_problem(await get_guild(), role)
        if problem:
            await answer(interaction, f"{actor}님, {role.mention} 역할로는 켤 수 없어요. {problem}")
            return
        if role.id != bot.player_role_id:
            bot.player_role_id, bot.role_seen, bot.role_revoke = role.id, {}, None  # 역할이 바뀌면 처음부터 다시 맞춘다
            save_state()
    if not bot.player_role_id:
        await answer(interaction, f"{actor}님, 참여 선수 역할 자동 부여가 꺼져 있어요. `/선수역할` 에서 **역할**을 고르면, 운영진 페이지에서 승인한 선수에게 그 역할을 주고 제외한 선수에게서는 뺍니다.")
        return
    if not (SYNC_URL and SYNC_KEY):
        await answer(interaction, f"{actor}님, 역할은 정했지만, 봇이 등록 명단을 읽을 수 없어요. `config.json` 에 `sync_url` 과 `sync_key` 를 넣고 봇을 다시 켜 주세요.")
        return
    try:
        out = await sync_roles(force=True)
    except Exception as e:
        print(f"참여 선수 역할 맞추기 실패: {e!r}")
        await answer(interaction, f"{actor}님, 등록 명단을 읽지 못했어요. 잠시 뒤에 다시 해 주세요. ({e})")
        return
    bot.role_note = out["problem"]
    done = roles_text(out).replace("🎫 **참여 선수 역할**\n", "")  # 문제가 생기기 전에 처리한 것이 있으면 그것도 알린다
    if out["problem"]:
        text = f"{actor}님, **참여 선수 역할**을 맞추지 못했어요. " + out["problem"] + (f"\n{done}" if done else "")
    elif bot.role_revoke is not None:  # 시즌이 넘어가 역할을 거두는 중이다. 한 번에 다 하지 못하면 다음 차례에 이어서 한다
        text = (f"{actor}님, 시즌이 바뀌어 지난 시즌 선수의 <@&{bot.player_role_id}> 역할을 거두는 중이에요. "
                f"(남은 사람 {len(bot.role_revoke['left'])}명) 다 거둔 뒤에 새 시즌의 승인 선수에게 줍니다.")
    else:
        head = f"{actor}: 🎫 승인한 선수에게 <@&{bot.player_role_id}> 역할을 자동으로 줍니다. 제외하면 뺍니다. (1분마다 확인)"
        more = f"\n나머지 {out['left']}명은 이어서 처리합니다." if out["left"] else ""
        text = f"{head}\n{done or '지금은 새로 주거나 뺄 사람이 없어요.'}{more}"
    await answer(interaction, text)


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
