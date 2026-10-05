"""
도타 2 인하우스 내전 모집 봇

- 관리자 채널에서 /내전생성  → 참여 신청 채널에 모집 글을 올리고 모집 시작
  (참여 신청 채널이 포럼이면 내전마다 새 글을 만들고, 일반 채널이면 공지 메시지를 올림)
- 모집 글(일반 채널이면 그 채널)에서 /참여, /참여취소
- 마감 시각은 모집 시간(기본 5분) 뒤를 분 단위로 올림한 시각. 12:00:30 에 만들면 12:06:00 마감
- 마감 시각이 되면 참여 명단을 자동으로 공지
- 관리자 채널에서 /마감 (지금 인원으로 바로 마감), /연장 (마감을 5분 뒤로, 마감한 뒤에도 가능), /취소 (내전 취소)
- 관리자 채널에는 리그 매니저에 붙여넣을 명단(디스코드 ID·사용자명·별명)을 함께 올림
- 서버 주소(sync_url)와 운영진 키(sync_key)를 적어 두면, 명단을 리그 서버에도 올려
  매니저의 "봇이 올린 명단 불러오기"로 바로 받을 수 있음

설정은 같은 폴더의 config.json 에서 바꿉니다. (config.example.json 을 복사해 만드세요)
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
import discord
from discord import app_commands

# ── 설정 불러오기 ─────────────────────────────────────────────
CONFIG_PATH = Path(__file__).with_name("config.json")
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
PLAYERS_NEEDED = 10  # 5 vs 5
KST = timezone(timedelta(hours=9))  # 모집 글 제목에 쓰는 한국 시간


# ── 모집 상태 ────────────────────────────────────────────────
class Recruitment:
    """내전 모집 1건. 마감한 뒤에도 /연장·/취소를 받을 수 있게 다음 모집이 생길 때까지 남겨 둔다."""

    def __init__(self, host: discord.abc.User, end_ts: int) -> None:
        self.host = host
        self.end_ts = end_ts
        # user_id -> {"name": 서버 별명, "username": 디스코드 사용자명}
        # dict 는 넣은 순서를 유지하므로 신청 순서가 보존됨
        self.participants: dict[int, dict[str, str]] = {}
        self.message: discord.Message | None = None  # 모집 글 본문(포럼) 또는 공지 메시지(일반 채널)
        self.thread: discord.Thread | None = None  # 참여 신청 채널이 포럼일 때 이 내전의 글
        self.task: asyncio.Task | None = None
        self.closed = False
        self.cancelled = False
        self.extended = False
        self.synced = False  # 리그 서버에 명단이 올라가 있는지
        self.edit_lock = asyncio.Lock()

    @property
    def place_id(self) -> int:
        """참가자가 /참여 를 입력하는 곳: 포럼이면 모집 글, 일반 채널이면 그 채널"""
        return self.thread.id if self.thread else SIGNUP_CHANNEL_ID


class InhouseBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.current: Recruitment | None = None  # 모집 중이거나 가장 최근에 마감한 내전
        self.lock: asyncio.Lock | None = None

    async def setup_hook(self) -> None:
        # 생성·마감·연장·취소가 겹치지 않게 한 번에 하나씩 처리한다
        self.lock = asyncio.Lock()
        # 서버 단위로 등록하면 슬래시 명령어가 즉시 반영됨
        await self.tree.sync(guild=GUILD)

    async def on_ready(self) -> None:
        print(f"로그인 완료: {self.user} (ID: {self.user.id})")
        await check_setup()


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


def post_title() -> str:
    """포럼 모집 글 제목. 예) 10월 6일(화) 21:30 내전 모집"""
    now = datetime.now(KST)
    return f"{now.month}월 {now.day}일({'월화수목금토일'[now.weekday()]}) {now:%H:%M} 내전 모집"


def announcement_text(rec: Recruitment) -> str:
    count = len(rec.participants)
    names = ", ".join(safe_name(v["name"]) for v in rec.participants.values()) or "아직 없음"
    if rec.cancelled:
        status = "❌ **이 내전은 취소됐어요.**"
    elif rec.closed:
        status = f"🔒 **모집 마감** — 최종 {count}명"
    else:
        # <t:…:t> 는 보는 사람의 시간대에 맞춰 '오후 12:06' 처럼 보인다
        status = (
            f"⏰ **<t:{rec.end_ts}:t>까지** 참여 신청을 받아요. "
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


async def open_signup(rec: Recruitment) -> None:
    """참여 신청 채널에 모집 글을 올린다. 포럼이면 새 글을 만들고, 일반 채널이면 메시지를 보낸다."""
    signup = await get_channel(SIGNUP_CHANNEL_ID)
    if isinstance(signup, discord.ForumChannel):
        options = {}
        if signup.flags.require_tag and signup.available_tags:
            options["applied_tags"] = signup.available_tags[:1]  # 태그가 필수인 포럼이면 첫 태그를 붙인다
        created = await signup.create_thread(name=post_title(), content=announcement_text(rec), **options)
        rec.thread, rec.message = created.thread, created.message
    else:
        rec.message = await signup.send(announcement_text(rec))


async def post(rec: Recruitment, text: str) -> None:
    """모집 글(포럼) 또는 참여 신청 채널에 메시지를 보낸다. 실패해도 모집 처리는 계속한다."""
    try:
        place = rec.thread or await get_channel(SIGNUP_CHANNEL_ID)
        await place.send(text)
    except discord.HTTPException as e:
        print(f"참여 신청 채널 전송 실패: {e}")


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
    await asyncio.sleep(max(0, rec.end_ts - time.time()))
    async with bot.lock:
        await close_recruitment(rec)


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
            f"[모집 종료] 주최: {rec.host.mention}\n{roster_text}",
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

    await set_locked(rec, True)


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
    await refresh_announcement(rec)
    await post(rec, f"⏩ 모집을 연장했어요! **<t:{rec.end_ts}:t>까지** `/참여` 로 신청하세요. (<t:{rec.end_ts}:R> 마감)")


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
    await set_locked(rec, True)


def manager_blocks(rec: Recruitment) -> list[str]:
    """리그 매니저 '디스코드 참가 명단으로 고르기'에 붙여넣을 글. 한 줄에 '사용자ID 사용자명 별명'."""
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


async def push_roster(rec: Recruitment, clear: bool = False) -> bool | None:
    """리그 서버(Apps Script)에 명단을 올린다. 설정이 없으면 None, 성공하면 True. clear 면 빈 명단으로 비운다."""
    if not (SYNC_URL and SYNC_KEY):
        return None
    payload = {
        "action": "pushRoster",
        "key": SYNC_KEY,
        "roster": {"entries": [] if clear else [
            {"id": str(uid), "username": v["username"], "name": v["name"]} for uid, v in rec.participants.items()
        ]},
    }
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Apps Script 는 결과를 다른 주소로 넘겨 주므로 리다이렉트를 따라간다
            async with session.post(SYNC_URL, data=json.dumps(payload),
                                    headers={"Content-Type": "text/plain;charset=utf-8"}) as resp:
                text = await resp.text()
        result = json.loads(text)
        if not result.get("ok"):
            print(f"리그 서버가 명단을 받지 않았습니다: {result.get('error')}")
            return False
        return True
    except Exception as e:  # 서버 문제로 모집 마감이 멈추면 안 된다
        print(f"리그 서버에 명단을 올리지 못했습니다: {e!r}")
        return False


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
async def create_inhouse(interaction: discord.Interaction) -> None:
    if not await admin_only(interaction):
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
        rec = Recruitment(host=interaction.user, end_ts=deadline_after(SIGNUP_SECONDS))
        try:
            await open_signup(rec)
        except discord.HTTPException as e:
            await interaction.followup.send(f"모집 글을 올리지 못했어요. 봇 권한과 채널 ID를 확인해 주세요. ({e})")
            return
        bot.current = rec  # 모집 글이 올라간 뒤에 등록해서, 다른 명령어가 준비되지 않은 모집을 보지 않게 한다
        rec.task = asyncio.create_task(close_when_due(rec))

    await interaction.followup.send(
        f"✅ 모집을 시작했어요! {rec.message.jump_url}\n마감: <t:{rec.end_ts}:t> (<t:{rec.end_ts}:R>)"
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
        + f" 새 마감: <t:{rec.end_ts}:t> (<t:{rec.end_ts}:R>)"
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
