"""
도타 2 인하우스 내전 모집 봇

사람은 두 갈래다 (2026-10-09에 운영자가 정한 이름):
- 리그 운영진: 디스코드의 운영진 채널(admin_channel_id)에서 봇 명령어로 내전을 열고 결과를 기록하는 사람
- 리그 관리자: 선수 승인처럼 리그를 관리하는 사람(리그 관리자 페이지와 키를 쓴다). 봇의 설정을 바꾸는 /선수역할 은 리그 관리자만 쓴다

- 운영진 채널에서 /내전생성  → 참여 신청 채널에 모집 글을 올리고 모집 시작
  (참여 신청 채널이 포럼이면 내전마다 새 글을 만들고, 일반 채널이면 공지 메시지를 올림)
  · /내전생성 마감:2026-10-07-21-30 처럼 마감 시각(한국 시간)을 적으면 그 시각에 마감
  · 비우면 모집 시간(기본 5분) 뒤를 분 단위로 올림한 시각. 12:00:30 에 만들면 12:06:00 마감
- 모집 글(일반 채널이면 그 채널)에서 /참여, /참여취소
- 마감 시각이 되면 참여 명단을 공지하고, 리그 매니저와 같은 로직으로 팀을 짜서 알림 (matchmaker.js, Node 필요)
  · 팀 편성 공지에는 선수별 인하우스 MMR과 이기면·지면 바뀌는 점수, 팀 평균과 같은 자리·라인끼리의 MMR 차이가 함께 나감
- 내전은 동시에 여러 개(기본 3개까지) 진행할 수 있다. 아래 명령어는 그 내전의 글에서 입력하면 그 내전에 적용한다
  (운영진 채널에서 입력하면 가리키는 내전이 하나뿐일 때만 적용하고, 여러 개면 글에서 입력하라고 알려 준다)
- /마감 (지금 인원으로 바로 마감), /연장 (마감을 5분 뒤로, 마감한 뒤에도 가능), /재모집 (참여 신청을 모두 비우고 5분 동안 다시 모집), /취소 (내전 취소)
- 한 사람은 한 번에 한 내전에만 들어간다: 모집 중인 다른 내전에 신청해 둔 사람과, 결과가 아직 기록되지 않은 판에서 뛰는 사람은 /참여 를 받지 않는다
- 경기가 끝나면 /승리 (이긴 팀을 골라 결과 기록과 MMR 정산), /승리취소 (그 내전에 기록한 결과 되돌리기)
  · 정산도 리그 매니저의 로직 그대로 한다. 리그 기록의 원본은 서버에 있고, 봇은 받아서 고친 뒤 다시 올린다
  · /승리취소 는 그 판의 선수가 그 뒤에 기록된 경기에 뛰지 않았을 때만 된다. 뛰었으면 그 경기부터 되돌리라고 알리고 리그 관리자 역할을 부른다
- 경기를 시작할 때 /시작 (로비 음성 채널에 있는 그 내전의 선수를 팀 음성 채널로 옮김), 끝나면 /종료 (그 내전의 팀 음성 채널에 있는 모두를 로비로)
  · 팀 음성 채널은 내전마다 한 벌(래디언트·다이어)을 쓴다. '래디언트 2'·'다이어 2'처럼 같은 번호를 붙인 채널이 한 벌이고, 비어 있는 벌을 봇이 고른다
  · 로비와 1번 벌은 /시작 의 로비·래디언트·다이어 칸에서 한 번 고르면 기억한다. 봇에 멤버 이동 권한이 있어야 한다
- 리그 운영진 명령어로 봇이 올리는 글은 모두 그 명령어를 쓴 사람의 멘션으로 시작한다 (본인에게만 보이는 안내는 빼고)
- 운영진 채널에는 리그 매니저에 붙여넣을 명단(디스코드 ID·사용자명·별명)을 함께 올림
- 서버 주소(sync_url)와 리그 관리자 키(sync_key)를 적어 두면, 명단과 짠 팀을 리그 서버에도 올려
  매니저의 "봇이 올린 명단 불러오기", "봇이 짠 팀 불러오기"로 바로 받을 수 있음
- 리그 관리자가 운영진 채널에서 /선수역할 로 역할을 정해 두면, 리그 관리자 페이지에서 승인한 선수에게 그 역할을 주고 승인을 푼 선수에게서는 뺌
  (등록 명단을 5분마다 읽어 맞춘다. 봇에 역할 관리 권한이 있고, 봇의 역할이 그 역할보다 위에 있어야 한다)
- 리그 선수가 대화방에서 /내전하자  → 한 시간 동안 "지금 내전을 하고 싶은 사람"으로 남고, 10명이 모이면 대화방에서 리그 운영진 역할을 멘션해 알림
  (대화방과 알릴 역할은 리그 관리자가 /내전하자설정 으로 정한다)
  · 대화방에 모집판(기다리는 사람들과 '참여 희망' 버튼이 있는 글)을 하나 둔다. 버튼을 누르면 /내전하자 와 같고, 누른 사람에게만 '참여 취소' 버튼이 보인다
- /도움말  → 입력한 사람이 쓸 수 있는 명령어만 본인에게 보여 줌
- 리그 관리자 페이지에서 시즌 종료 날짜를 정해 두면, 그날 0시 전에 시작한 경기까지만 결과를 기록한다 (끝난 시각이 그 뒤여도 그 경기는 기록한다)
  · 경기를 시작한 시각은 /시작 을 처음 쓴 때이고, 쓰지 않았으면 팀을 짠 때다. 시즌이 끝난 뒤의 내전은 열 수 있지만 결과는 기록하지 않는다
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
# 리그 관리자 역할. 보통은 비워 두고 디스코드에서 /선수역할 의 관리자역할 칸으로 정한다(그 값은 state.json 에 남는다)
MANAGER_ROLE_ID = int(config.get("manager_role_id", 0) or 0)
SIGNUP_SECONDS = int(float(config.get("signup_minutes", 5)) * 60)
EXTEND_SECONDS = int(float(config.get("extend_minutes", 5)) * 60)
ANNOUNCEMENT = config["announcement"]
SYNC_URL = str(config.get("sync_url", "")).strip()
SYNC_KEY = str(config.get("sync_key", "")).strip()
AUTO_MATCH = bool(config.get("auto_match", True))  # 마감하면 팀을 짜서 알릴지 (sync_url·sync_key 와 Node 가 있어야 한다)
NODE_PATH = str(config.get("node_path", "") or "node").strip()
# 승인한 선수에게 줄 역할. 보통은 비워 두고 디스코드에서 /선수역할 로 정한다(그 값은 state.json 에 남는다)
PLAYER_ROLE_ID = int(config.get("player_role_id", 0) or 0)
ROLE_POLL_SECONDS = 300  # 등록 명단의 승인·제외를 이만큼마다 확인한다. 1분이었는데, 급할 것이 없어 구글 서버에 묻는 횟수를 줄였다(2026-10-11)
ROLE_RETRY_SECONDS = 600  # 서버에서 찾지 못한 사람은 이만큼 지난 뒤에 다시 찾아본다
ROLE_BATCH = 30  # 한 번에 찾아볼 사람 수. 디스코드에 몰아서 묻지 않게 나눠 한다
PLAYERS_NEEDED = 10  # 5 vs 5
# 동시에 진행할 수 있는 내전 수(모집 중이거나, 팀이 짜였는데 결과를 아직 기록하지 않은 내전). 운영자가 팀 음성 채널을 3벌까지 만들기로 했다(2026-10-11).
# 참여 신청 채널이 포럼이 아니면 내전마다 글이 따로 없어 가릴 수 없으므로 한 번에 하나만 모집한다
MAX_GAMES = max(1, int(config.get("max_games", 3) or 3))
# 마감한 모집 글을 잠글지. 잠근 글에는 디스코드가 스레드 관리 권한이 있는 사람에게만 글과 명령어를 허용한다.
# 리그 운영진이 마감 뒤의 명령어(/시작·/승리 등)를 그 글에서 써야 하므로 기본은 잠그지 않는다. 리그 운영진 역할에 그 권한을 준 뒤에 true 로 바꾼다
LOCK_CLOSED = bool(config.get("lock_closed_threads", False))
RESTART_SECONDS = 300  # /재모집: 참여 신청을 모두 비우고 이만큼 뒤에 다시 마감한다
WANT_SECONDS = 3600  # /내전하자 로 알린 상태가 유지되는 시간
WANT_TICK_SECONDS = 30  # 모집판을 이만큼마다 확인해, 한 시간이 지나 빠진 사람과 그사이 모집에 /참여 한 사람을 반영한다
WANT_ALERT_GAP = 600  # 10명이 모였다고 리그 운영진을 부른 뒤 이만큼은 다시 부르지 않는다 (참여 희망·취소를 되풀이해 알림이 거듭 울리지 않게)
WANT_NAMES = 50  # 모집판에 적는 이름 수. 메시지 하나(2000자)에 들어가게 그 뒤는 '외 N명'으로 줄인다
KST = timezone(timedelta(hours=9))  # 마감 시각 입력과 모집 글 제목에 쓰는 한국 시간
DAY_STARTS_AT = 6  # 하루는 한국 시간 오전 6시에 바뀐다 (매니저의 팀 편성과 같은 기준)
ROLE_NAMES = ["캐리", "미드", "오프", "서폿", "서폿"]
# /시작·/종료 가 쓰는 음성 채널 세 곳. 고른 적이 없으면 이름에 이 낱말이 든 음성 채널을 찾아본다
VOICE_ROOMS = {"lobby": ("로비", "lobby"), "radiant": ("래디언트", "radiant"), "dire": ("다이어", "dire")}
DEADLINE_FORMAT = re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})")
DEADLINE_EXAMPLE = "`2026-10-07-21-30` (연-월-일-시-분, 한국 시간, 24시간제)"
MESSAGE_LIMIT = 1900  # 디스코드 메시지는 2000자까지라 조금 남겨 두고 나눈다
THREAD_ARCHIVED = 50083  # 디스코드 오류 번호: 보관된(접힌) 스레드에는 글을 올리거나 고칠 수 없다
OFFSEASON_NOTE = "ℹ️ 시즌이 종료되어 이 내전의 결과는 순위에 기록되지 않습니다."  # 시즌이 끝난 뒤의 내전에 붙이는 안내


# ── 모집 상태 ────────────────────────────────────────────────
class Recruitment:
    """내전 1건(모집부터 결과 기록까지). 마감한 뒤에도 그 내전의 글에서 /연장·/취소·/시작·/승리 등을 받을 수 있게 이틀 동안 남겨 둔다.
    내전은 동시에 여러 개 진행할 수 있다(bot.games). 내전마다 명령어를 한 번에 하나씩 처리하려고 잠금(lock)을 따로 둔다."""

    def __init__(self, host_id: int, end_ts: int) -> None:
        self.host_id = host_id
        self.end_ts = end_ts
        self.lock = asyncio.Lock()  # 이 내전의 마감·연장·취소·재모집이 겹치지 않게 한다. 다른 내전의 명령어는 기다리지 않는다
        self.matching = False  # 마감 처리 중(명단을 올리고 팀을 짜는 몇 초). 그동안은 참가자 모두를 다른 내전에 들어가지 못하게 막는다
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
        self.offseason = False  # 시즌이 끝난 뒤에 만든 내전. 결과를 기록하지 않는다고 모집 글에 적는다
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
            "offseason": self.offseason,
        }


class InhouseBot(discord.Client):
    def __init__(self) -> None:
        # 봇이 보내는 글로는 @everyone 과 역할 멘션 알림이 절대 울리지 않게 한다 (닉네임 같은 남의 글이 섞여 들어가도 안전하도록)
        super().__init__(intents=discord.Intents.default(), allowed_mentions=discord.AllowedMentions(everyone=False, roles=False))
        self.tree = app_commands.CommandTree(self)
        # 진행 중이거나 최근에 끝난 내전들(만든 순서). 끝난 지 이틀이 지나면 잊는다(save_state)
        self.games: list[Recruitment] = []
        self.unrestored: list[dict] = []  # 켤 때 디스코드가 답하지 않아 이어받지 못한 내전(상태 파일에 그대로 남겨 다음에 다시 이어받는다)
        self.lock: asyncio.Lock | None = None  # /내전생성 이 겹치지 않게 한다(동시에 열린 수를 세어야 한다)
        # 리그 기록을 고치는 /승리·/승리취소 는 내전이 달라도 한 번에 하나씩 한다(두 판의 결과가 차례로 들어간다).
        # 음성 채널을 고르는 /시작·/종료 도 한 번에 하나씩 한다(두 내전이 같은 팀 채널을 잡지 않게)
        self.league_lock = asyncio.Lock()
        self.voice_lock = asyncio.Lock()
        # 오늘 짠 팀 [{"at": 시각, "ids": 선수 id, "message_id": 모집 글}]. 결과를 아직 기록하지 않은 판도 오늘 뛴 것으로 치는 데 쓴다
        self.lineups: list[dict] = []
        self.restored = False
        # 리그 선수 역할 자동 부여. player_role_id 가 0이면 꺼져 있다.
        # role_seen 은 등록마다 마지막으로 맞춘 내용 {스팀키: {"status", "discord", "ok", "tried"}}, role_season 은 그때의 시즌 이름이다
        self.player_role_id = PLAYER_ROLE_ID
        self.role_seen: dict[str, dict] = {}
        self.role_season = ""
        # 마지막으로 맞춘 시즌의 번호(서버가 알려 준다. 아직 모르면 None). 서버의 번호가 더 크면 시즌이 넘어간 것이라 역할을 거둔다.
        self.role_season_no: int | None = None
        self.role_note = ""  # 마지막으로 운영진 채널에 알린 문제. 같은 문제를 확인할 때마다 다시 알리지 않으려고 적어 둔다
        self.role_lock: asyncio.Lock | None = None
        self.role_task: asyncio.Task | None = None
        # /시작 에서 골라 둔 음성 채널 {"lobby": 채널 ID, "radiant": …, "dire": …}. 없는 것은 이름으로 찾는다
        self.voice: dict[str, int] = {}
        # 리그 관리자 역할. 0이면 정해 두지 않은 것이라 서버 관리자 권한이 있는 사람만 리그 관리자로 본다
        self.manager_role_id = MANAGER_ROLE_ID
        # /내전하자: 지금 내전을 하고 싶다고 알린 사람 {디스코드 ID: 입력한 시각}. 한 시간 뒤에 저절로 풀리고, 그때까지는 다시 쓸 수 없다.
        # want_joined 는 그 가운데 모집에 /참여 한 사람이다(이미 판에 들어갔으니 기다리는 사람으로 세지 않는다).
        self.wants: dict[int, float] = {}
        self.want_joined: set[int] = set()
        self.want_alerted = False  # 10명이 모였다고 이미 알렸는지. 10명 아래로 내려가면 다시 알릴 수 있다
        self.want_channel_id = 0   # /내전하자 를 쓰는 대화방. 0이면 어느 채널에서나 받고, 알림은 입력한 채널에 올린다
        self.want_role_id = 0      # 10명이 모였을 때 멘션할 리그 운영진 역할 (/내전하자설정 으로 정한다)
        # 모집판: 대화방에 올려 둔, 기다리는 사람들과 참여 희망 버튼이 있는 글 {"channel_id", "message_id", "who": 적어 둔 사람들}. 없으면 None
        self.want_board: dict | None = None
        self.want_alert_at = 0.0   # 마지막으로 리그 운영진을 부른 시각
        self.want_lock = asyncio.Lock()  # 모집판을 올리고 지우는 일이 겹치지 않게 한다
        self.want_seq = 0          # 모집판을 맞춰 달라는 요청의 번호. 기다리던 요청은 가장 나중 것만 한다
        self.want_fresh = False    # 기다리는 요청 가운데 새로 올려 달라는 것이 있는지
        self.want_task: asyncio.Task | None = None
        # 지금 시즌의 번호와 시즌 종료 시각(1970년부터의 초, 정해 두지 않았으면 0). 서버의 답에서 받아 적어 둔다(note_season, 서버 버전 16).
        # 결과를 기록할 때는 그 자리에서 다시 받아 확인하고, 여기 적어 둔 값은 내전을 열 때와 팀을 알릴 때의 안내에 쓴다
        self.season_no: int | None = None
        self.season_end = 0.0

    @property
    def current(self) -> Recruitment | None:
        """가장 나중에 만든 내전. 없으면 None"""
        return self.games[-1] if self.games else None

    @current.setter
    def current(self, rec: Recruitment | None) -> None:
        if rec is None:  # 모두 비운다
            self.games = []
        elif rec not in self.games:
            self.games.append(rec)

    async def setup_hook(self) -> None:
        self.lock = asyncio.Lock()
        self.league_lock = asyncio.Lock()
        self.voice_lock = asyncio.Lock()
        self.role_lock = asyncio.Lock()
        self.want_lock = asyncio.Lock()
        # 모집판의 버튼은 봇을 껐다 켠 뒤에도 눌려야 한다. 켤 때마다 다시 등록해 둔다
        self.add_view(WantBoard())
        self.add_view(WantLeave())
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
            print(f"리그 선수 역할 자동 부여: {await role_status()}")
            print(f"리그 관리자(/선수역할 을 쓸 수 있는 사람): {await manager_status()}")
            print(f"내전하자(/내전하자): {await want_status()}")
            print(f"음성 채널 이동(/시작·/종료): {await voice_status()}")
            self.role_task = asyncio.create_task(role_loop())
            self.want_task = asyncio.create_task(want_loop())


bot = InhouseBot()


# ── 유틸 ────────────────────────────────────────────────────
async def get_channel(channel_id: int):
    channel = bot.get_channel(channel_id)
    if channel is None:
        channel = await bot.fetch_channel(channel_id)
    return channel


async def check_setup() -> None:
    """켤 때 채널 ID와 봇 권한을 확인해서, 고칠 곳이 있으면 모집을 시작하기 전에 알려 준다."""
    for label, channel_id in (("운영진 채널", ADMIN_CHANNEL_ID), ("참여 신청 채널", SIGNUP_CHANNEL_ID)):
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
        # 리그 운영진 역할을 정해 두지 않았으면 운영진 채널을 볼 수 있는 사람이 곧 리그 운영진이다. 그 채널이 모두에게 열려 있으면 누구나 리그 운영진 명령어를 쓸 수 있다
        if channel_id == ADMIN_CHANNEL_ID and ADMIN_ROLE_ID == 0 and channel.permissions_for(channel.guild.default_role).view_channel:
            print("[확인 필요] 운영진 채널을 서버의 모든 사람이 볼 수 있습니다. 지금은 그 채널에 글을 쓸 수 있는 사람이면 누구나 /내전생성·/승리 같은 리그 운영진 명령어를 쓸 수 있습니다. "
                  "디스코드에서 그 채널을 리그 운영진만 보게 바꾸거나, config.json 의 admin_role_id 에 리그 운영진 역할의 ID를 넣어 주세요.")
    print(f"자동 팀 편성: {match_problem() or '켜짐'}")
    print(f"동시에 진행할 수 있는 내전: {MAX_GAMES}개 (참여 신청 채널이 포럼일 때). 마감한 글 잠그기: {'켜짐' if LOCK_CLOSED else '꺼짐'}")


# ── 내전 찾기 ────────────────────────────────────────────────
# 리그 운영진 명령어(/마감·/연장·/취소·/재모집·/시작·/종료·/승리·/승리취소)는 그 내전의 글(스레드)에서 입력하면 그 내전에 적용한다
# (운영자가 2026-10-11에 정함. 그 전에는 내전이 하나뿐이었고 모두 운영진 채널에서 입력했다).
# 다른 곳(운영진 채널)에서 입력했을 때는 가리키는 내전이 하나뿐일 때만 그 내전에 적용하고, 여러 개면 글에서 입력하라고 알려 준다.
def games_at(place_id: int) -> list[Recruitment]:
    """이 글(일반 채널이면 그 채널)에서 모집한 내전들. 만든 순서"""
    return [g for g in bot.games if g.place_id == place_id]


def is_place(channel_id: int) -> bool:
    """내전의 글인지 (모집 글이거나, 봇이 짠 팀이 올라간 곳)"""
    return bool(games_at(channel_id)) or any(x.get("place_id") == channel_id for x in bot.lineups)


def find_game(channel_id: int, fits) -> tuple[Recruitment | None, list[Recruitment]]:
    """명령어를 적용할 내전. 내전의 글에서 입력했으면 그 내전이고(fits 에 맞지 않아도 돌려준다. 까닭은 명령어가 알려 준다),
    다른 곳에서 입력했으면 fits 에 맞는 내전이 하나뿐일 때 그 내전이다. 돌려주는 값: (내전, 여러 개라 고르지 못했을 때의 후보들)"""
    here = games_at(channel_id)
    if here:
        return here[-1], []
    found = [g for g in bot.games if fits(g)]
    return (found[0], []) if len(found) == 1 else (None, found)


def find_entry(channel_id: int, fits, newest: bool = True) -> tuple[dict | None, list[dict]]:
    """명령어를 적용할 편성(봇이 짠 팀). find_game 과 같은 규칙이다. 한 글에 맞는 편성이 여럿이면(일반 채널) newest 에 따라 가장 나중이나 가장 먼저 짠 것"""
    if is_place(channel_id):
        here = [x for x in bot.lineups if x.get("place_id") == channel_id and fits(x)]
        return ((here[-1] if newest else here[0]) if here else None), []
    found = [x for x in bot.lineups if fits(x)]
    return (found[0], []) if len(found) == 1 else (None, found)


def waiting_result(entry: dict) -> bool:
    """팀이 짜였고 결과를 아직 기록하지 않은 판인지"""
    return bool(entry.get("lanes")) and not entry.get("result")


def is_active(rec: Recruitment) -> bool:
    """진행 중인 내전인지: 모집 중이거나, 마감 처리 중이거나, 팀이 짜였는데 결과를 아직 기록하지 않았다"""
    if rec.cancelled:
        return False
    if not rec.closed or rec.matching:
        return True
    entry = lineup_of(rec)
    return bool(entry and not entry.get("result"))


def links(places) -> str:
    """내전의 글들을 가리키는 링크. 같은 글은 한 번만"""
    return ", ".join(f"<#{p}>" for p in dict.fromkeys(places))


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


def is_manager(user: discord.abc.User) -> bool:
    """리그 관리자인가. 선수 승인처럼 리그를 관리하는 사람이고, 봇의 설정을 바꾸는 /선수역할 은 리그 관리자만 쓴다 (운영자가 정함, 2026-10-09).
    디스코드에서는 서버 관리자 권한이 있는 사람과, /선수역할 의 관리자역할 칸으로 정해 둔 역할이 있는 사람이다."""
    if not isinstance(user, discord.Member):
        return False
    if user.guild_permissions.administrator:
        return True
    return bool(bot.manager_role_id) and any(role.id == bot.manager_role_id for role in user.roles)


async def is_admin(user: discord.abc.User, inside: bool) -> bool:
    """리그 운영진인가 (봇 명령어로 내전을 열고 결과를 기록하는 사람). inside 는 운영진 채널에서 명령어를 입력했는지.
    리그 관리자는 리그 운영진이 하는 일도 모두 한다.
    리그 운영진 역할(admin_role_id)을 정해 두지 않았으면 운영진 채널에서 명령어를 쓸 수 있는 사람이 곧 리그 운영진이다.
    그래서 다른 채널에서 입력한 사람은 운영진 채널의 권한(채널 보기, 명령어 사용)을 보고 가린다."""
    if not isinstance(user, discord.Member):
        return False
    if is_manager(user):
        return True
    if ADMIN_ROLE_ID:
        return any(role.id == ADMIN_ROLE_ID for role in user.roles)
    if inside:
        return True
    try:
        perms = (await get_channel(ADMIN_CHANNEL_ID)).permissions_for(user)
    except Exception as e:  # 운영진 채널을 확인하지 못하면 리그 운영진으로 치지 않는다 (운영진 채널에서 입력하면 그대로 된다)
        print(f"운영진 채널의 권한을 확인하지 못했습니다: {e!r}")
        return False
    return bool(perms.view_channel and perms.use_application_commands)


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
    off = f"\n{OFFSEASON_NOTE}" if rec.offseason and not rec.cancelled else ""
    return f"<@{rec.host_id}>님이 내전 모집을 열었어요.\n{ANNOUNCEMENT}{off}\n\n{status}\n👥 참여자 ({count}명): {names}"


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
    options = {"allowed_mentions": discord.AllowedMentions.none()}  # 본문 맨 앞에 모집을 연 리그 운영진을 적는다. 알림은 울리지 않는다
    if isinstance(signup, discord.ForumChannel):
        if signup.flags.require_tag and signup.available_tags:
            options["applied_tags"] = signup.available_tags[:1]  # 태그가 필수인 포럼이면 첫 태그를 붙인다
        created = await signup.create_thread(name=post_title(title_ts), content=announcement_text(rec), **options)
        rec.thread, rec.message = created.thread, created.message
    else:
        rec.message = await signup.send(announcement_text(rec), **options)


async def post(rec: Recruitment, text: str, quiet: bool = False, skip: int | None = None) -> None:
    """모집 글(포럼) 또는 참여 신청 채널에 메시지를 보낸다. quiet 면 멘션 알림을 보내지 않는다. 실패해도 모집 처리는 계속한다.
    skip 은 글에 멘션돼 있어도 알림은 보내지 않을 사람이다 (글 맨 앞에 적는, 명령어를 쓴 리그 운영진).
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
        print(f"운영진 채널 전송 실패: {e}")


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
    async with rec.lock:
        await close_recruitment(rec)


# ── 봇을 껐다 켜도 모집을 이어 가기 ───────────────────────────
def save_state() -> None:
    """진행 중인 내전들과 짠 팀을 파일에 적는다. 실패해도 모집은 계속한다."""
    keep_from = time.time() - 2 * 86400  # 결과를 다음 날 기록하는 일도 있어 이틀 치를 남긴다
    bot.lineups = [x for x in bot.lineups if x.get("at", 0) >= keep_from]
    # 끝난 지 이틀이 지난 내전은 잊는다. 그 글에서는 더 명령어를 받지 않는다
    bot.games = [g for g in bot.games if not (g.closed and g.end_ts < keep_from)]
    bot.unrestored = [x for x in bot.unrestored if not (x.get("closed") and x.get("end_ts", 0) < keep_from)]
    try:
        data = {
            "games": [g.to_dict() for g in bot.games if g.message is not None] + bot.unrestored,
            "lineups": bot.lineups,
            "roles": {"role_id": bot.player_role_id, "season": bot.role_season, "season_no": bot.role_season_no,
                      "seen": bot.role_seen},
            "voice": bot.voice,
            "manager_role_id": bot.manager_role_id,
            "want": {"users": {str(uid): at for uid, at in bot.wants.items()}, "joined": sorted(bot.want_joined), "alerted": bot.want_alerted,
                     "channel_id": bot.want_channel_id, "role_id": bot.want_role_id, "board": bot.want_board, "alert_at": bot.want_alert_at},
        }
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        for attempt in range(3):
            try:
                os.replace(tmp, STATE_PATH)
                break
            except PermissionError:  # 윈도우에서 백신 같은 다른 프로그램이 그 파일을 잠깐 잡고 있을 때가 있다. 조금 뒤에 다시 한다
                if attempt == 2:
                    raise
                time.sleep(0.05)
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
    voice = data.get("voice")
    if isinstance(voice, dict):  # /시작 에서 골라 둔 음성 채널
        bot.voice = {k: v for k, v in voice.items() if k in VOICE_ROOMS and isinstance(v, int)}
    if isinstance(data.get("manager_role_id"), int):  # /선수역할 의 관리자역할 칸으로 정한 리그 관리자 역할
        bot.manager_role_id = data["manager_role_id"] or MANAGER_ROLE_ID
    want = data.get("want")
    if isinstance(want, dict):  # /내전하자 로 알려 둔 사람들과 /내전하자설정 으로 정한 대화방·역할
        users = want.get("users") if isinstance(want.get("users"), dict) else {}
        bot.wants = {int(uid): float(at) for uid, at in users.items() if str(uid).isdigit() and isinstance(at, (int, float))}
        bot.want_joined = {int(uid) for uid in want.get("joined") or [] if isinstance(uid, int)}
        bot.want_alerted = bool(want.get("alerted"))
        bot.want_channel_id = int(want.get("channel_id") or 0)
        bot.want_role_id = int(want.get("role_id") or 0)
        board = want.get("board")  # 대화방에 올려 둔 모집판. 켠 뒤에도 그 글을 고치고 지울 수 있게 이어받는다
        if isinstance(board, dict) and isinstance(board.get("channel_id"), int) and isinstance(board.get("message_id"), int):
            bot.want_board = {"channel_id": board["channel_id"], "message_id": board["message_id"],
                              "who": [x for x in board.get("who") or [] if isinstance(x, int)]}
        bot.want_alert_at = float(want["alert_at"]) if isinstance(want.get("alert_at"), (int, float)) else 0.0
    # 내전들. 예전 상태 파일(내전이 하나뿐이던 때)에는 current 하나가 적혀 있다
    saved = data.get("games") if isinstance(data.get("games"), list) else [data.get("current")]
    bot.games, bot.unrestored, dropped = [], [], False
    for cur in saved:
        if not isinstance(cur, dict) or not cur.get("message_id"):
            continue
        rec = Recruitment(int(cur["host_id"]), int(cur["end_ts"]))
        rec.participants = {int(uid): {"name": name, "username": username} for uid, name, username in cur.get("participants", [])}
        rec.closed, rec.cancelled, rec.extended = bool(cur.get("closed")), bool(cur.get("cancelled")), bool(cur.get("extended"))
        rec.synced, rec.lineup = bool(cur.get("synced")), bool(cur.get("lineup"))
        rec.offseason = bool(cur.get("offseason"))
        try:
            place = await get_channel(int(cur.get("thread_id") or SIGNUP_CHANNEL_ID))
        except discord.NotFound:
            # 모집 글이 지워졌다. 이어받을 것이 없으니 상태 파일에서도 지운다 (그대로 두면 켤 때마다 같은 안내가 뜬다)
            print("꺼지기 전에 하던 모집은 글이 지워져 있어 이어받지 않습니다." if not rec.closed
                  else "꺼지기 전에 마감한 모집은 글이 지워져 있어 이어받지 않습니다. (/연장·/취소 는 새 모집부터 쓸 수 있습니다)")
            dropped = True
            continue
        except discord.HTTPException as e:  # 디스코드가 잠깐 답하지 않은 것일 수 있다. 상태 파일에 그대로 남겨 둔다
            print(f"꺼지기 전에 하던 모집을 이어받지 못했습니다. 봇을 다시 켜면 다시 이어받아 봅니다. ({e})")
            bot.unrestored.append(cur)
            continue
        if cur.get("thread_id"):
            rec.thread = place
        rec.message = place.get_partial_message(int(cur["message_id"]))
        bot.games.append(rec)
        if rec.closed:
            continue
        rec.task = asyncio.create_task(close_when_due(rec))
        print(f"꺼지기 전에 하던 모집을 이어받았습니다. 참여자 {len(rec.participants)}명, "
              f"마감 {datetime.fromtimestamp(rec.end_ts, KST):%m월 %d일 %H:%M}")
    if dropped:
        save_state()


# ── 마감 · 연장 · 취소 · 재모집 (그 내전의 잠금 rec.lock 을 잡은 상태에서 부른다) ─────────
# by 는 그 명령어를 쓴 리그 운영진의 디스코드 ID다. 모집 글에 올리는 알림의 맨 앞에 멘션한다(알림은 울리지 않는다).
async def close_recruitment(rec: Recruitment, by: int | None = None) -> None:
    """by 가 없으면 마감 시각이 되어 저절로 마감하는 것이다."""
    if rec.closed:
        return
    rec.closed = True
    rec.matching = True  # 팀이 나올 때까지는 누가 뛰는지 모른다. 그동안 참가자가 다른 내전에 들어가지 못하게 한다
    stop_timer(rec)
    try:
        await finish_closing(rec, by)
    finally:
        rec.matching = False
    save_state()


async def finish_closing(rec: Recruitment, by: int | None) -> None:
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

    # 운영진 채널: 같은 명단을 알림 없이 전송하고, 리그 매니저에 붙여넣을 명단을 따로 올린다
    synced = await push_roster(rec) if roster else None
    if synced:
        rec.synced = True
    try:
        admin = await get_channel(ADMIN_CHANNEL_ID)
        for chunk in split_message(f"[모집 종료] 주최: <@{rec.host_id}> · <#{rec.place_id}>\n{roster_text}"):
            await admin.send(chunk, allowed_mentions=discord.AllowedMentions.none())
        if roster:
            for chunk in manager_blocks(rec):
                await admin.send(chunk, allowed_mentions=discord.AllowedMentions.none())
        if synced is not None:
            await admin.send("리그 서버에 명단을 올렸습니다. 리그 관리자가 매니저에서 팀을 직접 짤 때는 '봇이 올린 명단 불러오기'로 받습니다."
                             if synced else "리그 서버에 명단을 올리지 못했습니다. 리그 관리자가 매니저에서 팀을 직접 짤 때는 위 명단을 복사해 붙여넣습니다.")
        if count < PLAYERS_NEEDED:
            await admin.send(f"<#{rec.place_id}> 에서 `/연장` 으로 {minutes_text(EXTEND_SECONDS)} 더 모집하거나, `/재모집` 으로 처음부터 다시 받거나, `/취소` 로 이번 내전을 취소할 수 있어요.")
    except discord.HTTPException as e:
        print(f"운영진 채널 전송 실패: {e}")

    if count >= PLAYERS_NEEDED and not match_problem():
        await auto_match(rec)

    # 마감한 글은 기본으로 잠그지 않는다. 잠그면 스레드 관리 권한이 없는 리그 운영진이 그 글에서 /시작·/승리 를 쓰지 못한다 (LOCK_CLOSED)
    if LOCK_CLOSED:
        await set_locked(rec, True)


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
    await set_locked(rec, True)  # 취소한 글에서는 더 할 일이 없으므로 잠근다
    save_state()


async def restart_recruitment(rec: Recruitment, by: int) -> list[int]:
    """모집을 처음부터 다시 받는다(/재모집, 운영자가 2026-10-11에 요청): 지금까지의 참여 신청을 모두 취소로 돌리고 마감을 5분 뒤로 미룬다.
    이미 마감했으면 다시 열고, 짜 둔 팀이 있으면 없던 일로 한다. 돌려주는 값: 참여 신청이 취소된 사람들"""
    reopened = rec.closed
    gone = list(rec.participants)
    rec.participants = {}
    rec.end_ts = deadline_after(RESTART_SECONDS)
    rec.closed = False
    rec.extended = False
    stop_timer(rec)
    rec.task = asyncio.create_task(close_when_due(rec))

    if reopened:
        await set_locked(rec, False)
    if rec.synced:  # 마감 때 올린 명단은 이제 맞지 않으므로 비워 둔다
        await push_roster(rec, clear=True)
        rec.synced = False
    await drop_lineup(rec)
    await refresh_announcement(rec)
    mentions = " ".join(f"<@{uid}>" for uid in gone)
    await post(rec, f"<@{by}>님이 모집을 처음부터 다시 받아요. 지금까지의 참여 신청은 모두 취소됐어요.\n"
                    f"참여하려면 `/참여` 를 다시 입력해 주세요. **{when(rec.end_ts)}까지** 받아요. (<t:{rec.end_ts}:R> 마감)"
                    + (f"\n{mentions}" if mentions else ""), skip=by)
    save_state()
    return gone


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


class ServerGlitch(RuntimeError):
    """리그 서버에서 답을 받지 못했다: 닿지 못했거나, 제때 답이 없거나, 답이 JSON 이 아니다(구글이 가끔 오류 화면을 돌려준다).
    요청이 서버에서 처리됐는지는 알 수 없다."""


# 다시 보내도 결과가 같은 요청(읽기, 통째로 덮어쓰는 명단·편성). 답을 받지 못하면 조금 기다렸다가 몇 번 더 보낸다.
# 리그 기록 올리기(saveLeague)는 넣지 않는다. 처리됐는지 모르는 채 다시 보내면 같은 경기가 두 번 기록될 수 있어서 change_league 가 따로 확인한다.
REPEATABLE = {"adminList", "adminLeague", "adminLeagueRev", "adminRoster", "adminLineup", "pushRoster", "pushLineup", "ping", "adminSetPrefs"}
SERVER_TRIES = 3  # 한 요청을 몇 번까지 보낼지
SERVER_WAIT = 3  # 다시 보내기 전에 기다리는 시간(초). 두 번째는 그 두 배


async def ask_server(payload: dict) -> dict:
    """리그 서버(Apps Script)에 요청을 한 번 보낸다."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40)) as session:
            # Apps Script 는 결과를 다른 주소로 넘겨 주므로 리다이렉트를 따라간다
            async with session.post(SYNC_URL, data=json.dumps({**payload, "key": SYNC_KEY}),
                                    headers={"Content-Type": "text/plain;charset=utf-8"}) as resp:
                status, kind, text = resp.status, resp.content_type, await resp.text(errors="replace")
    except asyncio.TimeoutError:
        raise ServerGlitch("서버가 40초 안에 답하지 않았습니다") from None
    except (aiohttp.ClientError, OSError) as e:
        raise ServerGlitch(f"서버에 연결하지 못했습니다 ({type(e).__name__})") from None
    try:
        result = json.loads(text)
    except ValueError:  # 구글의 오류 화면(HTML)이나 빈 답
        raise ServerGlitch(f"서버가 알아볼 수 없는 답을 보냈습니다 (HTTP {status}, {kind})") from None
    if not isinstance(result, dict):
        raise ServerGlitch("서버가 알아볼 수 없는 답을 보냈습니다")
    if not result.get("ok"):
        raise ServerError(result.get("error") or "서버가 요청을 처리하지 못했습니다", result.get("code") or "")
    if stray_status(result):
        raise ServerGlitch("서버의 답 대신 다른 답이 돌아왔습니다")
    return result


def stray_status(result: dict) -> bool:
    """요청의 답이 아니라 서버의 공개 상태가 대신 돌아온 것인지.
    구글 서버가 요청을 처리하고도 그 답을 전해 주지 못하면, 웹 앱 주소로 되돌려 보내서 요청과 상관없는 공개 상태(ok: true)가 온다
    (2026-10-08에 실제 서버에서 마흔 번에 한 번꼴로 봤다). 공개 상태에는 version 이 있고 리그 관리자에게만 주는 registered 가 없다.
    이것을 진짜 답으로 믿으면 저장되지 않은 경기를 저장됐다고 알리게 되므로, 답을 받지 못한 것(ServerGlitch)으로 친다."""
    return "version" in result and "registered" not in result


async def call_server(payload: dict) -> dict:
    """리그 서버(Apps Script)에 리그 관리자 키가 필요한 요청을 보낸다. 서버가 거절하면 ServerError, 답을 받지 못하면 ServerGlitch 를 낸다.
    구글 서버는 가끔 제때 답하지 않거나 오류 화면을 돌려준다(1분마다 묻는 역할 맞추기에서 저녁 한나절에 아홉 번 봤다, 2026-10-07).
    다시 보내도 되는 요청은 조금 기다렸다가 몇 번 더 보낸다."""
    tries = SERVER_TRIES if payload.get("action") in REPEATABLE else 1
    for n in range(1, tries + 1):
        try:
            return await ask_server(payload)
        except ServerGlitch:
            if n == tries:
                raise
            await asyncio.sleep(SERVER_WAIT * n)
    raise ServerGlitch("서버에서 답을 받지 못했습니다")  # 여기까지 오지 않는다


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
    남의 MMR과 전적으로 경기를 치르게 된다. 리그 매니저는 리그 관리자가 고른 명단을 눈으로 보지만, 봇은 그대로 팀을 짜고 정산한다.
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
    """마감한 모집의 참가자로 팀을 짜서 모집 글과 운영진 채널에 알리고, 매니저가 불러올 수 있게 서버에 올린다.
    어디서 막히든 모집 마감은 끝까지 가야 하므로, 문제는 운영진 채널에 알리고 넘어간다.
    리그 운영진은 리그 관리자 페이지와 매니저를 쓰지 못하므로(키가 없다), 그쪽에서 고쳐야 하는 문제는 리그 관리자에게 알리라고 적는다.
    내전이 여러 개일 수 있어서, 운영진 채널에 올리는 글에는 어느 내전인지(그 글의 링크)를 맨 앞에 적는다."""
    where = f"<#{rec.place_id}> "
    try:
        # sync: 승인돼 있는데 선수단에 빠진 선수가 있으면 서버가 먼저 채워 넣고 기록을 준다(서버 버전 10부터. 예전 서버는 이 값을 모른 채 기록만 준다).
        # 승인한 선수는 승인할 때 선수단에 들어가지만, 그때 드라이브가 답하지 않았거나 매니저가 예전 기록으로 덮어쓴 경우가 여기서 메워진다
        got = await call_server({"action": "adminLeague", "sync": True})
        note_season(got)
        league = got.get("league")
    except Exception as e:
        print(f"리그 기록을 받지 못했습니다: {e!r}")
        await tell_admins(where + "리그 서버에서 기록을 받지 못해 팀을 자동으로 짜지 못했습니다. 잠시 뒤 그 글에서 `/연장` → `/마감` 하면 다시 짭니다. "
                          "그래도 안 되면 리그 관리자에게 리그 매니저로 팀을 짜 달라고 알려 주세요.")
        return
    if not league or not league.get("players"):
        await tell_admins(where + "서버의 선수단에 선수가 없어 팀을 자동으로 짜지 못했습니다. 리그 관리자에게 알려 주세요. "
                          "선수단에는 리그 관리자가 **승인**한 선수가 들어갑니다. "
                          "참가자들의 등록을 승인한 뒤 `/연장` → `/마감` 하면 다시 짭니다. "
                          "승인한 선수가 있는데도 이 글이 나오면 리그 관리자 페이지의 **선수단 다시 맞추기**를 눌러야 합니다.")
        return

    who, missing = match_players(rec, league["players"])
    if len(who) < PLAYERS_NEEDED:
        await post(rec, f"⚠️ 선수 등록이 확인된 참가자가 {len(who)}명이라 팀을 자동으로 짜지 못했어요. 리그 운영진의 안내를 기다려 주세요.", quiet=True)
        await tell_admins(f"{where}선수단과 맞는 참가자가 {len(who)}명이라 팀을 자동으로 짜지 못했습니다. 선수단에 없는 참가자: "
                          + (" ".join(f"<@{uid}>" for uid in missing) or "없음")
                          + "\n리그 관리자에게 알려 주세요. 리그 관리자 페이지에서 그 선수의 등록을 승인했는지, 등록할 때 적은 디스코드 사용자명이 실제 계정과 같은지 확인해야 합니다. "
                            "고친 뒤 `/연장` → `/마감` 하면 다시 짭니다.")
        return

    start = day_start()
    busy = sorted({pid for x in bot.lineups if x.get("at", 0) >= start for pid in x.get("ids", [])})
    try:
        result = await run_matchmaker({"league": league, "participants": list(who), "busy": busy, "now": int(time.time() * 1000)})
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "알 수 없는 문제")
    except Exception as e:
        print(f"팀 편성 실패: {e!r}")
        await tell_admins(f"{where}팀을 자동으로 짜지 못했습니다. 리그 관리자에게 리그 매니저로 팀을 짜 달라고 알려 주세요. ({e})")
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
        "season": bot.season_no,  # 팀을 짠 때의 시즌 번호. 그 뒤에 새 시즌이 시작되면 이 판의 결과는 새 시즌에 기록하지 않는다
        "result": None,  # /승리 로 기록하면 {"winner", "match_id"}
    })
    note = (f"경기가 끝나면 {where}에서 `/승리` 로 이긴 팀을 골라 결과를 기록하세요. MMR이 정산되고 순위 페이지에 반영됩니다.\n"
            "대타가 뛰었거나 자리를 바꿔 뛰었다면 `/승리` 로 기록하지 말고 리그 관리자에게 알려 주세요. "
            "리그 관리자가 리그 매니저의 **봇이 짠 팀 불러오기**로 편성을 올린 뒤 고쳐서 기록합니다.")
    if season_over():  # 시즌이 끝난 뒤에 짠 팀이다. 위의 이기면·지면 점수는 적용되지 않는다고 그 글에 바로 알린다
        await post(rec, f"{OFFSEASON_NOTE} (시즌 종료: <t:{int(bot.season_end)}:f>)", quiet=True)
        note = (f"시즌이 종료돼서(<t:{int(bot.season_end)}:f>) 이 경기의 결과는 기록되지 않습니다. "
                f"경기가 끝나면 {where}에서 `/승리` 를 입력해 이 판을 정리해 주세요(기록하지 않고 정리만 합니다).")
    try:
        await call_server({"action": "pushLineup", "lineup": {
            "post": getattr(rec.message, "jump_url", ""), "lanes": lanes, "bench": [p["id"] for p in result["bench"]],
        }})
    except Exception as e:
        print(f"짠 팀을 리그 서버에 올리지 못했습니다: {e!r}")
        note += "\n짠 팀을 리그 서버에 올리지 못해서, 매니저의 **봇이 짠 팀 불러오기**는 이번 판에 쓸 수 없습니다."
    await tell_admins(f"{where}의 팀 편성\n{text}\n\n{note}")


async def drop_lineup(rec: Recruitment) -> None:
    """이 모집으로 짠 팀을 없던 일로 한다 (다시 열거나 취소할 때)."""
    if not rec.lineup:
        return
    rec.lineup = False
    message_id = rec.message.id if rec.message else 0
    # 서버에는 가장 나중에 짠 팀 하나만 올라가 있다. 그것이 이 내전의 것일 때만 비운다(다른 내전의 팀을 지우지 않게)
    newest = bool(bot.lineups) and bot.lineups[-1].get("message_id") == message_id
    bot.lineups = [x for x in bot.lineups if x.get("message_id") != message_id]
    if not newest:
        return
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


# ── 시즌 종료 (서버 버전 16) ──
# 리그 관리자 페이지에서 시즌 종료 날짜를 정해 두면 그날 0시(한국 시간)에 시즌이 끝난다(운영자가 2026-10-11에 정함):
# "시즌 내의 경기인가는 시즌 종료 날짜 0시 이전에 시작했는가로 판단한다. 종료 시간이 시즌 종료 시간을 넘어가도 해당 매치까지는 유효하다."
#  - 경기를 시작한 시각은 /시작 으로 선수를 처음 옮긴 때다. /시작 을 쓰지 않았으면 팀을 짜서 알린 때로 본다(match_start. 내가 정한 기준이다:
#    봇은 도타 2 안에서 경기가 언제 시작했는지 모른다).
#  - 그 시각이 시즌 종료 시각보다 앞이면 결과를 언제 입력하든 기록한다. 뒤면 /승리 가 기록하지 않고 그 판을 치운다(SeasonOver).
#  - 시즌이 끝난 뒤에도 내전은 열 수 있다. 결과가 기록되지 않는다고 리그 운영진과 모집 글에 알린다.
#  - 팀을 짠 뒤에 새 시즌이 시작됐으면(시즌 번호가 달라졌으면) 그 판의 결과를 새 시즌에 기록하지 않는다. 지난 시즌의 경기가 새 시즌의 순위에 들어가지 않게.
# 시즌 종료 시각은 서버가 알려 준다(adminLeague, adminList 의 답). 예전 서버의 답에는 없고, 그러면 아무것도 막지 않는다.
class SeasonOver(RuntimeError):
    """이 경기는 지금 시즌의 경기가 아니다. why 는 "ended"(시즌 종료 시각 뒤에 시작했다. end 가 그 시각) 또는 "changed"(팀을 짠 뒤에 새 시즌이 시작됐다)"""

    def __init__(self, why: str, end: float = 0) -> None:
        super().__init__(why)
        self.why = why
        self.end = end


def note_season(data: dict) -> None:
    """서버의 답에 실린 지금 시즌의 번호와 종료 시각을 적어 둔다"""
    if isinstance(data.get("seasonNo"), int):
        bot.season_no = data["seasonNo"]
    at = data.get("seasonEndAt")
    if isinstance(at, (int, float)) and not isinstance(at, bool):
        bot.season_end = at / 1000 if at > 0 else 0.0


def season_over(at: float | None = None) -> bool:
    """그 시각(기본: 지금)이 시즌 종료 시각을 지났는가. 종료 날짜를 정해 두지 않았으면 False"""
    return bool(bot.season_end) and (time.time() if at is None else at) >= bot.season_end


def match_start(entry: dict) -> float:
    """그 판의 경기를 시작한 시각: /시작 으로 선수를 처음 옮긴 때, 쓰지 않았으면 팀을 짜서 알린 때"""
    return float(entry.get("began") or entry.get("at") or 0)


async def clear_entry(entry: dict) -> None:
    """짠 팀을 결과 없이 치운다(경기 안 함, 시즌이 끝난 뒤의 경기). 그대로 두면 그 열 명이 오늘 뛴 사람으로 남고 다른 내전에 참여하지 못한다"""
    newest = entry is bot.lineups[-1]
    bot.lineups.remove(entry)
    for g in bot.games:
        if g.message is not None and g.message.id == entry.get("message_id"):
            g.lineup = False
    save_state()
    if newest:  # 서버에 올려 둔 편성이 이 판의 것이다. 매니저가 열리지 않은 판을 불러오지 않게 비운다
        try:
            await call_server({"action": "pushLineup", "lineup": None})
        except Exception as e:
            print(f"리그 서버의 팀 편성을 비우지 못했습니다: {e!r}")


class LaterMatches(RuntimeError):
    """되돌리려는 경기 뒤에, 그 경기에 뛴 선수가 다시 뛴 경기가 기록돼 있다. matches 는 그 경기들의 id(나중 경기가 앞).
    뒤 경기의 점수는 이 경기의 결과 위에서 계산됐으므로, 그 경기부터 차례로 되돌려야 한다."""

    def __init__(self, message: str, matches: list[str]) -> None:
        super().__init__(message)
        self.matches = matches


def match_changes(match: dict) -> list[dict]:
    """서버의 경기 기록 한 판을 /승리 의 답에 쓰는 모양으로 바꾼다 (matchmaker.js 가 돌려주는 changes 와 같다)."""
    return [{"id": r["id"], "name": r.get("name", ""), "side": r["side"], "role": r["role"], "before": r["before"], "delta": r["delta"],
             "after": r["before"] + r["delta"]} for r in match.get("rows") or []]


async def change_league(payload: dict, tried: list | None = None, entry: dict | None = None) -> dict:
    """서버의 리그 기록을 받아 matchmaker.js 로 고친 뒤 다시 올린다.
    받아 온 사이에 매니저가 기록을 바꿨으면 서버가 받지 않으므로(conflict), 새 기록으로 다시 한다.

    올린 뒤 답을 받지 못하면(ServerGlitch) 서버가 그 기록을 받았는지 알 수 없다. 받았는데 모르고 다시 올리면 같은 경기가 두 번 기록된다.
    그래서 올리기 전에 새 경기의 id 를 tried 에 적어 두고(편성에 붙어 state.json 에 남는다), 다시 할 때는 먼저 서버의 기록에 그 경기가 있는지 본다.
    있으면 다시 계산하지 않고 그 경기를 결과로 삼는다. 되돌리기도 같다: 되돌릴 경기가 서버에 이미 없으면 되돌린 것으로 본다.

    entry 는 그 판의 편성이다. 주면 이 시즌의 경기인지 본다(SeasonOver): 팀을 짠 뒤에 새 시즌이 시작됐거나,
    결과를 기록하려는데 경기를 시작한 시각이 시즌 종료 시각보다 뒤면 기록하지 않는다."""
    tried = tried if tried is not None else []
    for attempt in range(1, SERVER_TRIES + 1):
        last = attempt == SERVER_TRIES
        try:
            got = await call_server({"action": "adminLeague"})
        except ServerGlitch:
            if last:
                raise
            continue  # call_server 가 이미 기다려 가며 몇 번 물어봤다
        note_season(got)
        league = got.get("league")
        if not league:
            raise RuntimeError("서버에 리그 기록이 없습니다")
        matches = league.get("matches") or []
        if entry is not None and isinstance(entry.get("season"), int) and isinstance(got.get("seasonNo"), int) and got["seasonNo"] != entry["season"]:
            raise SeasonOver("changed")  # 팀을 짠 뒤에 새 시즌이 시작됐다. 지금 받은 것은 새 시즌의 기록이다
        if payload.get("mode") == "result":
            done = next((m for m in matches if m.get("id") in tried), None)
            if done is not None:  # 앞서 올리고 답을 받지 못한 기록이 서버에 들어가 있다
                return {"ok": True, "league": league, "match": {"id": done["id"], "at": done.get("at"), "winner": done.get("winner")},
                        "changes": match_changes(done)}
            if entry is not None and bot.season_end and match_start(entry) >= bot.season_end:
                raise SeasonOver("ended", bot.season_end)  # 시즌 종료 시각 뒤에 시작한 경기다
        elif payload.get("mode") == "undo" and payload.get("matchId") and all(m.get("id") != payload["matchId"] for m in matches):
            # 되돌릴 경기가 서버에 없다: 앞서 올린 되돌리기가 들어갔거나, 매니저에서 그 경기를 지웠다
            return {"ok": True, "league": league, "match": {"id": payload["matchId"]}, "changes": []}
        result = await run_matchmaker({**payload, "league": league, "now": int(time.time() * 1000)})
        if not result.get("ok"):
            if result.get("code") == "later":  # 되돌리려는 경기 뒤에 같은 선수가 뛴 경기가 기록돼 있다
                raise LaterMatches(result.get("error") or "", [str(b.get("id")) for b in result.get("blockers") or [] if isinstance(b, dict)])
            raise RuntimeError(result.get("error") or "알 수 없는 문제")
        if payload.get("mode") == "result":
            tried.append(result["match"]["id"])
            save_state()
        try:
            saved = await call_server({"action": "saveLeague", "league": result["league"], "baseRev": got.get("rev", 0)})
            if not isinstance(saved.get("rev"), int):  # 올렸다는 답에는 새 번호가 있어야 한다. 없으면 들어갔는지 모르는 것이다
                raise ServerGlitch("서버가 기록을 받았다는 답을 보내지 않았습니다")
            return result
        except ServerError as e:
            if e.code != "conflict" or last:
                raise
        except ServerGlitch:
            if last:
                raise
            await asyncio.sleep(SERVER_WAIT * attempt)
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


async def send_to(place_id: int, text: str, role_id: int = 0) -> None:
    """모집 글(또는 채널)에 알림을 울리지 않고 메시지를 보낸다. 실패해도 넘어간다.
    role_id 를 주면 그 역할의 멘션 알림만 울린다(글에 <@&역할> 이 들어 있어야 한다)."""
    mentions = discord.AllowedMentions(everyone=False, users=False, roles=[discord.Object(id=role_id)]) if role_id else discord.AllowedMentions.none()
    try:
        place = await get_channel(place_id)
        thread = place if isinstance(place, discord.Thread) else None
        for chunk in split_message(text):
            await awake(thread, lambda: place.send(chunk, allowed_mentions=mentions))
    except discord.HTTPException as e:
        print(f"결과 공지 실패: {e}")


# ── 리그 선수 역할 자동 부여 ──────────────────────────────────
# 리그 관리자 페이지에서 승인한 선수에게 역할을 주고, 승인을 푼 선수(대기로 돌렸거나 제외한 선수)에게서는 뺀다.
# 처음부터 대기인 등록(막 등록하고 아직 확인을 기다리는 선수)은 건드리지 않는다.
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


async def manager_status() -> str:
    """리그 관리자를 어떻게 가리는지 한 줄로 (켤 때 창에 찍는다)"""
    if not bot.manager_role_id:
        return "서버 관리자 권한이 있는 사람 (리그 관리자 역할을 따로 정하려면 `/선수역할` 의 관리자역할 칸에서 고릅니다)"
    try:
        role = (await get_guild()).get_role(bot.manager_role_id)
    except discord.HTTPException as e:
        return f"[확인 필요] 디스코드 서버를 확인하지 못했습니다 ({e})"
    if role is None:
        return "[확인 필요] 정해 둔 리그 관리자 역할을 찾지 못했습니다. 지금은 서버 관리자 권한이 있는 사람만 `/선수역할` 을 쓸 수 있습니다."
    return f"@{role.name} 역할이 있는 사람과 서버 관리자 권한이 있는 사람"


async def role_status() -> str:
    """지금 설정을 한 줄로 (켤 때 창에 찍고, /선수역할 에 답할 때 쓴다)"""
    if not bot.player_role_id:
        return "꺼짐 (리그 관리자가 디스코드 운영진 채널에서 `/선수역할` 로 줄 역할을 정하면 켜집니다)"
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
    시즌이 넘어가도 역할은 거두지 않는다: 서버 버전 14부터 선수와 승인 상태가 새 시즌으로 그대로 이어진다
    (운영자가 2026-10-09에 "한 번 등록하면 제외되지 않고서야 계속 선수"로 정했다. 그 전에는 시즌마다 모두 거뒀다가 다시 줬다).
    돌려주는 값: {"added": [멤버], "removed": [멤버], "missing": [등록], "problem": 까닭, "left": 다음 차례로 미룬 수}"""
    out = {"added": [], "removed": [], "missing": [], "problem": "", "left": 0}
    if not bot.player_role_id or not (SYNC_URL and SYNC_KEY):
        return out
    async with bot.role_lock:
        data = await call_server({"action": "adminList"})
        note_season(data)  # 지금 시즌의 종료 시각. 시즌이 끝난 뒤에 여는 내전에 미리 알리려고 5분마다 받아 둔다
        guild = await get_guild()
        role = guild.get_role(bot.player_role_id)
        out["problem"] = role_problem(guild, role)
        if out["problem"]:
            return out

        season, no = str(data.get("season") or ""), data.get("seasonNo")
        if not isinstance(no, int):  # 시즌 번호를 주지 않는 예전 서버: 이름이 바뀌면 명단을 처음부터 다시 맞추기만 한다
            if season != bot.role_season:
                bot.role_seen = {}
        elif bot.role_season_no is None:  # 처음 본 시즌
            bot.role_season_no = no
            save_state()
        elif no < bot.role_season_no:  # 번호가 줄었다: 다른 시트(서버)로 옮긴 경우. 처음부터 다시 맞춘다
            bot.role_season_no, bot.role_seen = no, {}
            save_state()
        elif no > bot.role_season_no:  # 시즌이 넘어갔다. 명단이 그대로 이어지므로 번호만 적어 두고, 아래에서 평소처럼 상태가 바뀐 등록만 본다
            bot.role_season_no = no
            save_state()
        bot.role_season = season
        seen, now, tried, changed = bot.role_seen, time.time(), 0, False
        for p in data.get("players") or []:
            key, status, name = str(p.get("steamKey") or p.get("discord") or ""), p.get("status"), str(p.get("discord") or "")
            if not key or status not in ("승인", "제외", "대기"):
                continue
            last = seen.get(key) or {}
            # 대기는 봇이 승인이나 제외로 본 적이 있는 등록만 본다: 승인했다가 대기로 돌린 선수에게서 역할을 뺀다(운영자가 2026-10-08에 확인한 규칙).
            # 처음부터 대기인 등록은 넘어간다. 등록만 한 사람을 하나하나 디스코드에 물어보지 않고, 리그 관리자가 손으로 준 역할을 빼지도 않으려는 것이다
            if status == "대기" and not last:
                continue
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
                    # 승인을 푼 사람이 서버에 없으면 뺄 역할도 없다. 승인한 사람이 없으면 나중에 다시 찾아본다
                    done = status != "승인"
                    if not done and not same:  # 처음 못 찾았을 때만 알린다
                        out["missing"].append(p)
                elif status == "승인" and role not in member.roles:
                    await member.add_roles(role, reason="인하우스 리그 등록 승인")
                    out["added"].append(member)
                elif status != "승인" and role in member.roles:
                    await member.remove_roles(role, reason="인하우스 리그 등록 " + ("제외" if status == "제외" else "승인 취소(대기)"))
                    out["removed"].append(member)
            except discord.Forbidden:
                out["problem"] = "역할을 바꿀 권한이 없어요. 봇에 **역할 관리** 권한이 있는지, 봇의 역할이 그 역할보다 위에 있는지 확인해 주세요."
                break
            except (discord.HTTPException, asyncio.TimeoutError) as e:  # 디스코드가 잠깐 답하지 않았다. 나중에 다시 한다
                print(f"리그 선수 역할: {name} 을(를) 처리하지 못했습니다: {e!r}")
                done = False
            seen[key] = {"status": status, "discord": name, "ok": done, "tried": now}
            changed = True
        if changed:
            save_state()
    return out


def roles_text(out: dict) -> str:
    """역할을 맞춘 결과를 운영진 채널에 알릴 글. 알릴 것이 없으면 빈 글."""
    lines = []
    if out["added"]:
        lines.append("✅ 승인 → 역할을 줬어요: " + ", ".join(m.mention for m in out["added"]))
    if out["removed"]:
        lines.append("🚫 승인 취소(대기·제외) → 역할을 뺐어요: " + ", ".join(m.mention for m in out["removed"]))
    if out["missing"]:
        lines.append("⚠️ 디스코드 서버에서 찾지 못했어요: "
                     + ", ".join(f"{safe_name(str(p.get('nickname') or '?'))} (`{str(p.get('discord') or '').replace('`', '')}`)" for p in out["missing"])
                     + "\n서버에 들어와 있는지, 등록한 디스코드 사용자명이 맞는지 확인해 주세요. 10분마다 다시 찾아봅니다.")
    return ("🎫 **리그 선수 역할**\n" + "\n".join(lines)) if lines else ""


async def role_tick() -> None:
    """등록 명단을 한 번 읽어 역할을 맞추고, 바뀐 것이 있을 때만 운영진 채널에 알린다."""
    out = await sync_roles()
    text = roles_text(out)
    if text:
        await tell_admins(text)
    # 권한 문제는 같은 내용을 되풀이해 알리지 않는다. 풀렸다가 다시 생기면 또 알린다
    if out["problem"] and out["problem"] != bot.role_note:
        await tell_admins("🎫 **리그 선수 역할**을 맞추지 못했어요. " + out["problem"])
    bot.role_note = out["problem"]


async def role_loop() -> None:
    """켜 둔 동안 주기적으로 역할을 맞춘다."""
    while True:
        try:
            await role_tick()
        except Exception as e:  # 서버나 디스코드가 잠깐 답하지 않아도 다음 차례에 다시 한다
            print(f"[{datetime.now(KST):%m-%d %H:%M}] 리그 선수 역할을 이번에는 맞추지 못했습니다. 다음 차례에 다시 합니다. ({e})")
        await asyncio.sleep(ROLE_POLL_SECONDS)


# ── 음성 채널 이동 (/시작, /종료) ──────────────────────────────
# 경기를 시작할 때 로비 음성 채널에 있는 선수를 배정된 팀의 음성 채널로 옮기고, 끝나면 팀 채널의 모두를 로비로 되돌린다.
# 누가 음성 채널에 있는지는 특권 인텐트 없이 안다(음성 상태는 기본 인텐트에 들어 있다). 옮기려면 봇에 멤버 이동 권한이 있어야 한다.
ROOM_NAMES = {"lobby": "로비", "radiant": "래디언트", "dire": "다이어"}


def room_number(channel) -> int:
    """팀 음성 채널이 몇 번 벌인지. 채널 이름에 번호가 있으면 그 번호('래디언트 2' → 2), 없으면 그 채널이 든 카테고리 이름의 번호
    ('게임 채널 2' 아래의 '래디언트' → 2. 운영자가 2026-10-11에 카테고리마다 래디언트·다이어를 하나씩 두는 모양으로 만들었다), 그것도 없으면 1"""
    for name in (channel.name, getattr(getattr(channel, "category", None), "name", None)):
        m = re.search(r"\d+", name) if isinstance(name, str) else None
        if m:
            return int(m.group())
    return 1


def pair_label(pair: dict) -> str:
    """팀 음성 채널 한 벌을 가리키는 이름: 두 채널이 든 카테고리의 이름. 카테고리가 없거나 서로 다르면 빈 글.
    카테고리마다 같은 이름의 채널을 두면 채널 이름만으로는 어느 벌인지 알 수 없어서, 리그 운영진에게 답할 때 함께 적는다"""
    names = {getattr(getattr(c, "category", None), "name", None) for c in pair.values()}
    name = names.pop() if len(names) == 1 else None
    return name if isinstance(name, str) else ""


def named_rooms(guild: discord.Guild, key: str) -> list:
    """이름에 그 낱말(로비, 래디언트, 다이어)이 든 음성 채널들"""
    return [c for c in guild.voice_channels if any(w in c.name.lower().replace(" ", "") for w in VOICE_ROOMS[key])]


def voice_rooms(guild: discord.Guild) -> tuple[dict, str]:
    """로비·래디언트·다이어 음성 채널을 찾는다. 돌려주는 값: ({"lobby": 채널, "radiant": 채널, "dire": 채널}, 찾지 못한 까닭)
    /시작 에서 골라 둔 채널이 먼저다. 고른 적이 없는 것은 이름으로 찾는다: 로비는 이름에 그 낱말이 든 음성 채널이 하나뿐일 때,
    래디언트·다이어는 그 가운데 1번(room_number: 채널이나 카테고리 이름의 번호가 1이거나 없는 채널)이 하나뿐일 때 그 채널을 쓴다.
    여기서 찾는 래디언트·다이어는 봇이 기억해 두는 한 벌이다. 내전을 동시에 여러 개 진행할 때 쓰는 벌 전체는 team_pairs 가 찾는다."""
    rooms, unknown = {}, []
    for key in VOICE_ROOMS:
        channel = guild.get_channel(bot.voice[key]) if bot.voice.get(key) else None
        if not isinstance(channel, discord.VoiceChannel):  # 고른 적이 없거나, 골라 둔 채널이 지워졌다
            named = [c for c in named_rooms(guild, key) if key == "lobby" or room_number(c) == 1]
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


def team_pairs(guild: discord.Guild, rooms: dict) -> dict[int, dict]:
    """팀 음성 채널의 벌들 {번호: {"radiant": 채널, "dire": 채널}}. 내전마다 한 벌을 쓴다(운영자가 2026-10-11에 3벌까지 만들기로 했다).
    번호(room_number)가 같은 래디언트 채널과 다이어 채널이 하나씩 있으면 한 벌이다: 카테고리 '게임 채널 2' 아래의 '래디언트'·'다이어',
    또는 '래디언트 2'·'다이어 2'. 봇이 기억해 둔 래디언트·다이어(rooms)가 그렇게 찾은 벌이 아니면(이름이 다른 채널을 골라 둔 경우) 그것도 한 벌로 넣는다."""
    found = {key: {} for key in ("radiant", "dire")}
    for key in found:
        for c in named_rooms(guild, key):
            found[key].setdefault(room_number(c), []).append(c)
    pairs = {n: {"radiant": found["radiant"][n][0], "dire": found["dire"][n][0]}
             for n in sorted(set(found["radiant"]) & set(found["dire"])) if len(found["radiant"][n]) == 1 and len(found["dire"][n]) == 1}
    if "radiant" in rooms and "dire" in rooms:
        mine = {"radiant": rooms["radiant"], "dire": rooms["dire"]}
        ids = {c.id for c in mine.values()}
        if not any({p["radiant"].id, p["dire"].id} == ids for p in pairs.values()):
            # 이름으로는 찾을 수 없는 벌이다. 그 채널이 든 다른 벌은 빼고(한 채널을 두 벌이 쓰지 않게) 비어 있는 가장 낮은 번호에 둔다
            pairs = {n: p for n, p in pairs.items() if not ({p["radiant"].id, p["dire"].id} & ids)}
            n = 1
            while n in pairs:
                n += 1
            pairs[n] = mine
    return pairs


def rooms_of(guild: discord.Guild, entry: dict) -> dict | None:
    """이 판이 /시작 때 쓰기로 한 팀 음성 채널 한 벌. 정한 적이 없거나 그 채널이 지워졌으면 None"""
    ids = entry.get("rooms") or {}
    pair = {key: guild.get_channel(ids[key]) if ids.get(key) else None for key in ("radiant", "dire")}
    return pair if all(isinstance(c, discord.VoiceChannel) for c in pair.values()) else None


def pick_rooms(guild: discord.Guild, entry: dict, pairs: dict[int, dict]) -> dict | None:
    """이 판이 쓸 팀 음성 채널 한 벌을 고른다. 이미 쓰기로 한 벌이 있으면 그대로, 아니면 진행 중인 다른 판이 쓰고 있지 않은 벌 가운데 번호가 가장 낮은 것.
    남은 벌이 없으면 None"""
    mine = rooms_of(guild, entry)
    if mine is not None:
        return mine
    busy = set()
    for x in bot.lineups:  # /시작 으로 시작했고 아직 끝나지 않은 다른 판이 쓰는 벌
        if x is not entry and x.get("started") and not x.get("ended") and not x.get("result") and x.get("rooms"):
            busy.add((x["rooms"].get("radiant"), x["rooms"].get("dire")))
    for n in sorted(pairs):
        if (pairs[n]["radiant"].id, pairs[n]["dire"].id) not in busy:
            return pairs[n]
    return None


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
    돌려주는 값: (서버, {"lobby": 채널, …}, 쓸 수 없는 까닭, 채널을 새로 기억했을 때 리그 운영진에게 덧붙일 안내)
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
    pairs = team_pairs(guild, rooms)
    mine = {rooms["radiant"].id, rooms["dire"].id}
    extra = [pairs[n] for n in sorted(pairs) if {pairs[n]["radiant"].id, pairs[n]["dire"].id} != mine]
    problem = voice_problem(guild, list(rooms.values()) + [c for pair in extra for c in pair.values()])
    names = ", ".join(f"{ROOM_NAMES[key]} #{rooms[key].name}" for key in VOICE_ROOMS)
    if extra:  # 내전을 동시에 진행할 때 쓰는 나머지 벌. 카테고리로 나눴으면 카테고리 이름으로 적는다
        names += " / " + " / ".join(pair_label(pair) or f"#{pair['radiant'].name}·#{pair['dire'].name}" for pair in extra) + f" (팀 채널 {len(pairs)}벌)"
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


# ── 슬래시 명령어: 리그 운영진 (/선수역할 은 리그 관리자) ─────────
async def admin_only(interaction: discord.Interaction, manager: bool = False) -> bool:
    """명령어 공통 확인: 쓸 수 있는 사람이, 운영진 채널에서 입력했는지.
    보통은 리그 운영진이면 되고, manager 면(/선수역할) 리그 관리자여야 한다.
    쓸 수 없는 사람에게는 어디에서 입력했든 사용 권한이 없다고만 알린다 (운영자가 정함, 2026-10-08).
    운영진 채널에서 쓰라는 안내는 다른 채널에서 입력한, 쓸 수 있는 사람에게만 한다."""
    inside = interaction.channel_id == ADMIN_CHANNEL_ID
    allowed = is_manager(interaction.user) if manager else await is_admin(interaction.user, inside)
    if not allowed:
        who = "리그 관리자" if manager else "리그 운영진"
        await interaction.response.send_message(f"이 명령어를 사용할 권한이 없어요. {who}만 쓸 수 있는 명령어예요.", ephemeral=True)
        return False
    if not inside:
        await interaction.response.send_message("이 명령어는 운영진 채널에서만 쓸 수 있어요.", ephemeral=True)
        return False
    return True


def by(interaction: discord.Interaction) -> str:
    """명령어를 쓴 사람(리그 운영진)의 멘션. 이 명령어들로 봇이 올리는 글은 모두 이 멘션으로 시작한다 (운영자가 정한 규칙, 2026-10-07).
    한 일을 알릴 때는 '@아무개님이 …했어요', 그 사람을 대신해 전하는 안내는 '@아무개: …', 그 사람에게 하는 말은 '@아무개님, …' 꼴로 쓴다.
    본인에게만 보이는 안내(ephemeral)에는 붙이지 않는다."""
    return f"<@{interaction.user.id}>"


async def answer(interaction: discord.Interaction, text: str) -> None:
    """리그 운영진 명령어에 운영진 채널에서 답한다. 길면 나눠 보내고, 멘션 알림은 울리지 않는다."""
    for chunk in split_message(text):
        await interaction.followup.send(chunk, allowed_mentions=discord.AllowedMentions.none())


async def staff_only(interaction: discord.Interaction) -> bool:
    """내전의 글에서도 쓰는 리그 운영진 명령어(/마감·/연장·/취소·/재모집·/시작·/종료·/승리·/승리취소)의 공통 확인: 리그 운영진인지만 본다.
    어느 채널에서 입력했는지는 따지지 않는다. 그 내전의 글에서 입력하면 그 내전에 적용한다."""
    if await is_admin(interaction.user, interaction.channel_id == ADMIN_CHANNEL_ID):
        return True
    await interaction.response.send_message("이 명령어를 사용할 권한이 없어요. 리그 운영진만 쓸 수 있는 명령어예요.", ephemeral=True)
    return False


async def begin(interaction: discord.Interaction) -> str:
    """리그 운영진 명령어의 답을 준비하고, 명령어를 쓴 사람의 멘션을 돌려준다.
    내전의 글에서 입력했으면 답을 본인에게만 보이게 한다. 그 글에는 봇이 모두가 보는 알림을 따로 올리므로 같은 말이 두 번 보이지 않게 하려는 것이다."""
    await interaction.response.defer(ephemeral=is_place(interaction.channel_id))
    return by(interaction)


def which(actor: str, places, what: str) -> str:
    """내전의 글이 아닌 곳에서 입력했는데 가리키는 내전이 여러 개일 때의 안내"""
    return f"{actor}님, {what} 내전이 여러 개예요. 그 내전의 글에서 입력해 주세요: {links(places)}"


def staff_game(channel_id: int) -> tuple[Recruitment | None, list[Recruitment]]:
    """/연장·/취소·/재모집 을 적용할 내전. 내전의 글에서 입력했으면 그 내전, 다른 곳에서 입력했으면 진행 중인 내전이 하나뿐일 때 그 내전이다.
    진행 중인 내전이 없으면 가장 나중에 만든 내전을 돌려준다(인원이 모자라 마감된 모집을 다시 여는 경우). 까닭은 명령어가 알려 준다."""
    rec, many = find_game(channel_id, is_active)
    if rec is None and not many:
        rec = bot.current
    return rec, many


async def no_room() -> str:
    """내전을 더 만들 수 없는 까닭. 만들 수 있으면 빈 글.
    참여 신청 채널이 포럼이면 진행 중인 내전을 MAX_GAMES 개까지 둔다. 일반 채널이면 내전마다 글이 따로 없어 가릴 수 없으므로 한 번에 하나만 모집한다."""
    opened = [g for g in bot.games if not g.closed]
    try:
        forum = isinstance(await get_channel(SIGNUP_CHANNEL_ID), discord.ForumChannel)
    except discord.HTTPException:
        forum = False
    if not forum:
        return f"이미 모집 중인 내전이 있어요. (마감 <t:{opened[-1].end_ts}:R>)" if opened else ""
    active = [g for g in bot.games if is_active(g)]
    if len(active) < MAX_GAMES:
        return ""
    return (f"지금 진행 중인 내전이 {len(active)}개라 더 만들 수 없어요(동시에 {MAX_GAMES}개까지). "
            f"끝난 판은 그 글에서 `/승리` 로 결과를 기록하고, 열리지 않은 판은 `/취소` 로 정리해 주세요: {links(g.place_id for g in active)}")


@bot.tree.command(name="내전생성", description="내전 참여자 모집을 시작합니다 (리그 운영진 전용)", guild=GUILD)
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
    full = await no_room()
    if full:
        await interaction.response.send_message(full, ephemeral=True)
        return
    await interaction.response.defer()
    actor = by(interaction)

    async with bot.lock:
        # 글을 올리는 사이에 다른 리그 운영진이 먼저 만들었을 수 있으니 다시 확인한다
        full = await no_room()
        if full:
            await answer(interaction, f"{actor}님, {full}")
            return
        rec = Recruitment(host_id=interaction.user.id, end_ts=end_ts or deadline_after(SIGNUP_SECONDS))
        rec.offseason = season_over()  # 시즌이 끝난 뒤의 내전은 열 수 있지만 결과를 기록하지 않는다. 모집 글에 그렇게 적는다
        try:
            await open_signup(rec, title_ts=end_ts)
        except discord.HTTPException as e:
            await answer(interaction, f"{actor}님, 모집 글을 올리지 못했어요. 봇 권한과 채널 ID를 확인해 주세요. ({e})")
            return
        bot.games.append(rec)  # 모집 글이 올라간 뒤에 등록해서, 다른 명령어가 준비되지 않은 모집을 보지 않게 한다
        rec.task = asyncio.create_task(close_when_due(rec))
        save_state()

    waiting = [x.get("place_id") for x in bot.lineups if waiting_result(x)]
    await answer(
        interaction,
        f"{actor}님이 모집을 시작했어요! {rec.message.jump_url}\n마감: {when(rec.end_ts)} (<t:{rec.end_ts}:R>)\n"
        "마감·연장·취소·재모집과 경기 시작·종료·결과 기록은 그 글에서 입력해 주세요."
        + (f"\n⚠️ 시즌이 종료됐어요(<t:{int(bot.season_end)}:f>). 이 내전의 결과는 순위에 기록되지 않아요. 모집 글에도 그렇게 적었어요." if rec.offseason else "")
        + (f"\n⚠️ 결과를 아직 기록하지 않은 판이 있어요: {links(waiting)}. 끝났다면 그 글에서 `/승리` 로 기록하고, "
           "팀만 짜고 열리지 않은 판이면 `/승리` 에서 **경기 안 함**을 골라 주세요. 그 판에서 뛰는 선수는 다른 내전에 참여할 수 없어요."
           if waiting else ""),
    )


@bot.tree.command(name="마감", description="지금까지 모인 인원으로 모집을 바로 마감합니다. 그 내전의 글에서 입력하세요 (리그 운영진 전용)", guild=GUILD)
async def close_now(interaction: discord.Interaction) -> None:
    if not await staff_only(interaction):
        return
    actor = await begin(interaction)
    rec, many = find_game(interaction.channel_id, lambda g: not g.closed)
    if rec is None and many:
        await answer(interaction, which(actor, [g.place_id for g in many], "모집 중인"))
        return
    none = f"{actor}님, 이 내전은 이미 마감했어요." if rec is not None else f"{actor}님, 지금은 모집 중인 내전이 없어요."
    if rec is None or rec.closed:
        await answer(interaction, none)
        return
    async with rec.lock:
        if rec.closed:  # 잠금을 기다리는 사이에 마감 시각이 됐다
            await answer(interaction, none)
            return
        await close_recruitment(rec, by=interaction.user.id)
    await answer(interaction, f"{actor}님이 모집을 마감했어요. (최종 {len(rec.participants)}명)")


@bot.tree.command(
    name="연장",
    description=f"모집 마감을 {minutes_text(EXTEND_SECONDS)} 뒤로 미룹니다. 마감한 뒤에도 다시 열 수 있어요. 그 내전의 글에서 입력하세요 (리그 운영진 전용)",
    guild=GUILD,
)
async def extend(interaction: discord.Interaction) -> None:
    if not await staff_only(interaction):
        return
    actor = await begin(interaction)
    rec, many = staff_game(interaction.channel_id)
    if rec is None and many:
        await answer(interaction, which(actor, [g.place_id for g in many], "진행 중인"))
        return
    if rec is None or rec.cancelled:
        await answer(interaction, f"{actor}님, 연장할 내전이 없어요. `/내전생성` 으로 새로 모집해 주세요.")
        return
    async with rec.lock:
        if rec.cancelled:
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


@bot.tree.command(name="취소", description="이번 내전을 취소합니다. 그 내전의 글에서 입력하세요 (리그 운영진 전용)", guild=GUILD)
async def cancel(interaction: discord.Interaction) -> None:
    if not await staff_only(interaction):
        return
    actor = await begin(interaction)
    rec, many = staff_game(interaction.channel_id)
    if rec is None and many:
        await answer(interaction, which(actor, [g.place_id for g in many], "진행 중인"))
        return
    if rec is None or rec.cancelled:
        await answer(interaction, f"{actor}님, 취소할 내전이 없어요.")
        return
    async with rec.lock:
        if rec.cancelled:
            await answer(interaction, f"{actor}님, 취소할 내전이 없어요.")
            return
        if settled(rec):
            await answer(interaction, f"{actor}님, 이미 경기 결과를 기록한 내전이에요. 결과를 되돌리려면 `/승리취소` 를 쓰세요.")
            return
        await cancel_recruitment(rec, by=interaction.user.id)
    await answer(interaction, f"{actor}님이 내전을 취소했어요." + (f" {rec.message.jump_url}" if rec.message else ""))


@bot.tree.command(
    name="재모집",
    description=f"모인 사람을 모두 참여 취소로 돌리고 {minutes_text(RESTART_SECONDS)} 동안 처음부터 다시 모집합니다. 그 내전의 글에서 입력하세요 (리그 운영진 전용)",
    guild=GUILD,
)
async def restart(interaction: discord.Interaction) -> None:
    if not await staff_only(interaction):
        return
    actor = await begin(interaction)
    rec, many = staff_game(interaction.channel_id)
    if rec is None and many:
        await answer(interaction, which(actor, [g.place_id for g in many], "진행 중인"))
        return
    if rec is None or rec.cancelled:
        await answer(interaction, f"{actor}님, 다시 모집할 내전이 없어요. `/내전생성` 으로 새로 모집해 주세요.")
        return
    async with rec.lock:
        if rec.cancelled:
            await answer(interaction, f"{actor}님, 다시 모집할 내전이 없어요. `/내전생성` 으로 새로 모집해 주세요.")
            return
        if settled(rec):
            await answer(interaction, f"{actor}님, 이미 경기 결과를 기록한 내전이에요. 새로 모집하려면 `/내전생성` 을 쓰세요.")
            return
        gone = await restart_recruitment(rec, by=interaction.user.id)
    await answer(interaction, f"{actor}님이 모집을 처음부터 다시 받게 했어요. 참여 신청 {len(gone)}명을 취소했어요. "
                              f"새 마감: {when(rec.end_ts)} (<t:{rec.end_ts}:R>)")


@bot.tree.command(name="시작", description="로비 음성 채널에 있는 선수를 배정된 팀의 음성 채널로 옮깁니다. 그 내전의 글에서 입력하세요 (리그 운영진 전용)", guild=GUILD)
@app_commands.rename(lobby="로비", radiant="래디언트", dire="다이어")
@app_commands.describe(lobby="선수들이 모여 있는 음성 채널. 한 번 고르면 기억하니 다음부터는 비워 두세요",
                       radiant="래디언트 팀이 쓸 음성 채널 (비우면 비어 있는 팀 채널을 봇이 고릅니다)", dire="다이어 팀이 쓸 음성 채널")
async def start_game(interaction: discord.Interaction, lobby: Optional[discord.VoiceChannel] = None,
                     radiant: Optional[discord.VoiceChannel] = None, dire: Optional[discord.VoiceChannel] = None) -> None:
    if not await staff_only(interaction):
        return
    actor = await begin(interaction)
    sides = (("radiant", "r"), ("dire", "d"))
    async with bot.voice_lock:
        picked = {key: channel.id for key, channel in (("lobby", lobby), ("radiant", radiant), ("dire", dire)) if channel is not None}
        guild, rooms, problem, note = await voice_setup(picked)
        if problem:
            await answer(interaction, f"{actor}님, {problem}")
            return
        # 이 내전의, 결과를 아직 기록하지 않은 팀 (한 곳에 여럿이면 가장 나중에 짠 것: 이제 시작할 판)
        entry, many = find_entry(interaction.channel_id, waiting_result, newest=True)
        if entry is None and many:
            await answer(interaction, which(actor, [x.get("place_id") for x in many], "팀이 짜인") + note)
            return
        if entry is None:
            await answer(interaction, f"{actor}님, 배정된 팀이 없어서 옮길 사람이 없어요. 봇이 팀을 짜서 알린 뒤에 쓸 수 있어요.{note}")
            return
        # 이 판이 쓸 팀 음성 채널 한 벌. 방금 고른 것이 먼저고, 아니면 진행 중인 다른 내전이 쓰지 않는 벌을 봇이 고른다
        team = {"radiant": radiant, "dire": dire} if radiant is not None and dire is not None else pick_rooms(guild, entry, team_pairs(guild, rooms))
        if team is None:
            await answer(interaction, f"{actor}님, 비어 있는 팀 음성 채널이 없어요. 진행 중인 다른 내전이 모두 쓰고 있어요. "
                                      f"끝난 판은 그 글에서 `/종료` 로 정리해 주세요.{note}")
            return
        problem = voice_problem(guild, [team["radiant"], team["dire"]])
        if problem:
            await answer(interaction, f"{actor}님, {problem}{note}")
            return
        who = entry.get("who") or {}
        seats = {side: [who[lane[s]] for lane in entry["lanes"] if lane[s] in who] for side, s in sides}
        waiting = set(rooms["lobby"].voice_states)  # 로비에 있는 사람
        moves = [(uid, team[side]) for side, _ in sides for uid in seats[side] if uid in waiting]
        placed = {uid for side, _ in sides for uid in seats[side] if uid in team[side].voice_states}  # 이미 자기 팀 채널에 와 있는 선수
        absent = [uid for side, _ in sides for uid in seats[side] if uid not in waiting and uid not in placed]
        if not moves:
            where = "" if not absent else " 로비에 없는 선수: " + ", ".join(f"<@{uid}>" for uid in absent)
            await answer(interaction, (f"{actor}님, 선수들이 이미 각자의 팀 음성 채널에 있어요." if placed and not absent
                                       else f"{actor}님, {rooms['lobby'].mention} 에 배정된 선수가 없어서 아무도 옮기지 않았어요.{where}") + note)
            return
        entry["started"] = time.time()  # /종료 가 끝났다는 안내를 이 판의 모집 글에 올린다
        entry.setdefault("began", entry["started"])  # 이 판의 경기를 시작한 시각(처음 옮긴 때). 시즌 종료 시각 전에 시작했는지를 이것으로 본다
        entry.pop("ended", None)
        entry["rooms"] = {side: team[side].id for side, _ in sides}  # /종료 는 이 벌만 비운다
        save_state()
        # 카테고리마다 같은 이름의 채널을 뒀으면 어느 벌인지 카테고리 이름으로 알린다. 모집 글의 안내에도 붙인다:
        # 로비에 없어서 옮겨지지 않은 선수가 어느 카테고리로 들어가야 하는지 알 수 있게 (운영자가 2026-10-11에 붙여 달라고 함)
        label = pair_label(team)
        notice = f"{actor}: 게임이 시작되어 선수들을 각자의 음성 채널로 이동시킵니다." + (f" ({label})" if label else "")
        await send_to(entry["place_id"], notice)
        moved, failed, denied = await move_people(guild, moves, "내전 시작 (/시작)")
    lines = [notice, (f"{label}: " if label else "")
             + " · ".join(f"{mark} {team[side].mention} {sum(uid in moved for uid in seats[side])}명" for mark, side in (("🟢", "radiant"), ("🔴", "dire")))
             + "을 옮겼어요."]
    if absent:
        lines.append("로비에 없어서 옮기지 못한 선수: " + ", ".join(f"<@{uid}>" for uid in absent))
    if failed:
        lines.append(("⚠️ 봇에 **멤버 이동** 권한이 없어 옮기지 못한 선수: " if denied else "⚠️ 옮기지 못한 선수(그사이 음성 채널에서 나갔을 수 있어요): ")
                     + ", ".join(f"<@{uid}>" for uid in failed))
    if season_over(match_start(entry)):
        lines.append(f"⚠️ 시즌 종료(<t:{int(bot.season_end)}:f>) 뒤에 시작한 경기라, 결과는 순위에 기록되지 않아요.")
    await answer(interaction, "\n".join(lines) + note)


@bot.tree.command(name="종료", description="이 내전의 팀 음성 채널에 있는 사람을 모두 로비 음성 채널로 옮깁니다. 그 내전의 글에서 입력하세요 (리그 운영진 전용)", guild=GUILD)
async def end_game(interaction: discord.Interaction) -> None:
    if not await staff_only(interaction):
        return
    actor = await begin(interaction)
    async with bot.voice_lock:
        guild, rooms, problem, note = await voice_setup()
        problem = problem or voice_problem(guild, [rooms["lobby"]])
        if problem:
            await answer(interaction, f"{actor}님, {problem}{note}")
            return
        # /시작 으로 시작했고 아직 끝내지 않은 판. 그 판이 쓰던 팀 음성 채널 한 벌만 비운다(다른 내전의 사람은 건드리지 않는다)
        entry, many = find_entry(interaction.channel_id, lambda x: bool(x.get("started")) and not x.get("ended"), newest=True)
        if entry is None and many:
            await answer(interaction, which(actor, [x.get("place_id") for x in many], "경기 중인") + note)
            return
        team = None
        if entry is not None:
            team = rooms_of(guild, entry)
        elif is_place(interaction.channel_id):
            # 이 내전은 시작한 적이 없거나 이미 끝냈다. 쓰던 벌을 알면 한 번 더 비워 준다
            last = next((x for x in reversed(bot.lineups) if x.get("place_id") == interaction.channel_id and x.get("rooms")), None)
            team = rooms_of(guild, last) if last is not None else None
            if team is None and any(x.get("place_id") != interaction.channel_id and waiting_result(x) for x in bot.lineups):
                await answer(interaction, f"{actor}님, 이 내전은 `/시작` 으로 선수를 옮긴 적이 없어서 어느 팀 음성 채널을 비울지 몰라요. "
                                          f"다른 내전이 진행 중이라 팀 채널을 모두 비우지는 않았어요. 손으로 옮겨 주세요.{note}")
                return
        elif sum(1 for x in bot.lineups if waiting_result(x)) > 1:
            # 내전의 글이 아닌 곳에서 입력했고, 진행 중인 내전이 여럿이다. 다른 내전의 선수를 옮기지 않게 글에서 입력하게 한다
            await answer(interaction, which(actor, [x.get("place_id") for x in bot.lineups if waiting_result(x)], "진행 중인") + note)
            return
        if team is None:
            team = {"radiant": rooms["radiant"], "dire": rooms["dire"]}  # 벌을 정해 둔 적이 없는 판(예전 방식)은 1번 벌
        people = [uid for side in ("radiant", "dire") for uid in team[side].voice_states]
        label = pair_label(team)  # 카테고리마다 같은 이름의 채널을 뒀으면 어느 벌인지 카테고리 이름으로 알린다
        if not people:
            await answer(interaction, f"{actor}님, {f'{label}의 ' if label else ''}{team['radiant'].mention} 와 {team['dire'].mention} 에 아무도 없어서 옮길 사람이 없어요.{note}")
            return
        notice = f"{actor}: 게임이 종료되어 모든 선수를 로비로 이동시킵니다."
        if entry is not None:
            entry["ended"] = time.time()
            save_state()
            await send_to(entry["place_id"], notice)
        moved, failed, denied = await move_people(guild, [(uid, rooms["lobby"]) for uid in people], "내전 종료 (/종료)")
    lines = [notice, f"{f'{label}에서 ' if label else ''}{rooms['lobby'].mention} 로 {len(moved)}명을 옮겼어요."]
    if failed:
        lines.append(("⚠️ 봇에 **멤버 이동** 권한이 없어 옮기지 못한 사람: " if denied else "⚠️ 옮기지 못한 사람(그사이 음성 채널에서 나갔을 수 있어요): ")
                     + ", ".join(f"<@{uid}>" for uid in failed))
    await answer(interaction, "\n".join(lines) + note)


@bot.tree.command(name="승리", description="봇이 짠 팀의 경기 결과를 기록하고 MMR을 정산합니다. 그 내전의 글에서 입력하세요 (리그 운영진 전용)", guild=GUILD)
@app_commands.rename(team="팀")
@app_commands.describe(team="이긴 팀. 팀만 짜고 경기를 하지 않은 판이면 '경기 안 함'을 고르세요")
@app_commands.choices(team=[app_commands.Choice(name="래디언트", value="r"), app_commands.Choice(name="다이어", value="d"),
                            app_commands.Choice(name="경기 안 함 (이 판을 기록 없이 정리)", value="x")])
async def record_win(interaction: discord.Interaction, team: str) -> None:
    if not await staff_only(interaction):
        return
    actor = await begin(interaction)
    async with bot.league_lock:
        # 이 내전의, 결과를 기다리는 팀 (한 곳에 여럿이면 가장 먼저 짠 것)
        entry, many = find_entry(interaction.channel_id, waiting_result, newest=False)
        if entry is None and many:
            await answer(interaction, which(actor, [x.get("place_id") for x in many], "결과를 기다리는"))
            return
        if entry is None:
            recorded = any(x.get("result") for x in bot.lineups)
            await answer(
                interaction,
                f"{actor}님, 결과를 기다리는 팀이 없어요. 이미 기록한 결과를 고치려면 `/승리취소` 로 되돌린 뒤 다시 기록하세요." if recorded
                else f"{actor}님, 결과를 기록할 팀이 없어요. 봇이 팀을 짜서 알린 뒤에 쓸 수 있어요.",
            )
            return
        others = [x.get("place_id") for x in bot.lineups if waiting_result(x) and x is not entry]  # 이 판 말고 결과를 기다리는 판
        more = f"\n결과를 기다리는 판이 {len(others)}개 더 있어요. 그 내전의 글에서 `/승리` 로 정리해 주세요: {links(others)}" if others else ""
        if team == "x":
            # 팀만 짜고 열리지 않은 판은 기록 없이 치운다. 그대로 두면 이 판의 열 명이 오늘 뛴 사람으로 남고, 다른 내전에 참여하지 못한다
            await clear_entry(entry)
            await send_to(entry["place_id"], f"{actor}님이 이 판을 경기 없이 정리했어요. 결과는 기록되지 않습니다.")
            await answer(interaction, f"{actor}님이 <#{entry['place_id']}> 의 판을 경기 없이 정리했어요. 결과와 MMR은 바뀌지 않습니다.{more}")
            return
        try:
            result = await change_league({"mode": "result", "lanes": entry["lanes"], "winner": team}, entry.setdefault("tried", []), entry)
        except SeasonOver as e:  # 이 시즌의 경기가 아니다. 기록하지 않고 이 판을 치운다
            await clear_entry(entry)
            if e.why == "changed":
                public = f"{actor}님이 결과를 입력했지만, 이 경기의 팀을 짠 뒤에 새 시즌이 시작돼서 기록하지 않았어요. 순위와 MMR은 바뀌지 않습니다."
                mine = (f"{actor}님, 이 경기의 팀을 짠 뒤에 새 시즌이 시작돼서 결과를 기록하지 않았어요. 순위와 MMR은 바뀌지 않고, 이 판은 정리했어요. "
                        "지난 시즌의 기록에 넣어야 하는 경기라면 리그 관리자에게 알려 주세요.")
            else:
                end = f"<t:{int(e.end)}:f>"
                public = f"{actor}님이 결과를 입력했지만, 이 경기는 시즌 종료({end}) 뒤에 시작해서 기록하지 않았어요. 순위와 MMR은 바뀌지 않습니다."
                mine = (f"{actor}님, 이 경기는 시즌 종료({end}) 뒤에 시작한 경기라 결과를 기록하지 않았어요. 순위와 MMR은 바뀌지 않고, 이 판은 정리했어요. "
                        "시즌 종료 날짜가 잘못돼 있다면 리그 관리자에게 알려 주세요.")
            await send_to(entry["place_id"], public)
            await answer(interaction, mine + more)
            return
        except ServerGlitch as e:  # 서버가 답하지 않았다. 올린 기록이 들어갔는지 모른다
            print(f"결과 기록 실패: {e!r}")
            await answer(interaction, f"{actor}님, 리그 서버가 답하지 않아 결과가 기록됐는지 확인하지 못했어요. ({e})\n"
                                      "잠시 뒤에 `/승리` 를 다시 입력해 주세요. 앞의 기록이 서버에 들어가 있으면 그것을 쓰므로, 같은 경기가 두 번 기록되지 않습니다.")
            return
        except Exception as e:
            print(f"결과 기록 실패: {e!r}")
            await answer(interaction, f"{actor}님, 결과를 기록하지 못했어요. 리그 관리자에게 리그 매니저로 기록해 달라고 알려 주세요. ({e})")
            return
        # 앞서 올리고 답을 받지 못한 기록이 서버에 들어가 있었으면, 그때 고른 팀이 기록돼 있다
        winner = result["match"].get("winner") if result["match"].get("winner") in ("r", "d") else team
        entry["result"] = {"winner": winner, "match_id": result["match"]["id"]}
        save_state()
        text = f"{actor}님이 경기 결과를 기록했어요.\n" + result_text(winner, result["changes"], entry.get("who") or {})
        await send_to(entry["place_id"], text)
        if winner != team:
            more = ("\n⚠️ 이 판은 앞서 입력한 대로 이미 기록돼 있었어요(그때는 서버의 답을 받지 못했습니다). 지금 고른 팀과 다르니, "
                    "바꾸려면 `/승리취소` 로 되돌린 뒤 다시 기록하세요." + more)
    await answer(interaction, f"{text}\n\n순위 페이지와 구글 시트에 반영했어요. 잘못 기록했다면 `/승리취소` 로 되돌릴 수 있어요.{more}")


async def undo_blocked(interaction: discord.Interaction, actor: str, match_ids: list[str]) -> None:
    """/승리취소 를 할 수 없을 때: 이 경기 뒤에 같은 선수가 뛴 경기가 기록돼 있다.
    어느 경기부터 되돌려야 하는지를 입력한 곳에 모두가 보게 올리고, 리그 관리자 역할을 부른다(운영자가 2026-10-11에 요청)."""
    known = {x["result"].get("match_id"): x for x in bot.lineups if x.get("result")}
    places = [known[m].get("place_id") for m in match_ids if m in known]
    unknown = sum(1 for m in match_ids if m not in known)
    lines = [f"{actor}님, 이 경기는 지금 되돌릴 수 없어요. 이 경기 뒤에 같은 선수가 뛴 경기가 기록돼 있어서, 그 경기부터 되돌려야 해요."]
    if places:
        lines.append(f"먼저 되돌릴 경기: {links(places)}" + (" (나중에 기록한 것부터 차례로)" if len(set(places)) > 1 else ""))
        lines.append("순서: 그 경기의 글에서 `/승리취소` → 이 경기의 글에서 `/승리취소` 한 뒤 `/승리` 로 다시 기록 → 그 경기의 글에서 `/승리` 로 다시 기록")
    if unknown:
        lines.append(f"봇이 모르는 경기가 {unknown}판 있어요(리그 매니저에서 기록했거나 이틀이 지난 경기). 이런 경기는 리그 관리자가 리그 매니저에서 고쳐야 해요.")
    role = bot.manager_role_id
    lines.append(f"<@&{role}> 확인해 주세요." if role
                 else "리그 관리자에게 알려 주세요. (리그 관리자 역할을 정해 두면 봇이 여기서 그 역할을 불러요: `/선수역할` 의 관리자역할 칸)")
    await send_to(interaction.channel_id, "\n".join(lines), role_id=role)
    await answer(interaction, f"{actor}님, 결과를 되돌리지 못했어요. 까닭과 순서를 방금 이 채널에 올렸어요.")


@bot.tree.command(name="승리취소", description="/승리 로 기록한 결과를 되돌립니다. 그 내전의 글에서 입력하세요 (리그 운영진 전용)", guild=GUILD)
async def undo_win(interaction: discord.Interaction) -> None:
    if not await staff_only(interaction):
        return
    actor = await begin(interaction)
    async with bot.league_lock:
        # 이 내전의, 결과를 기록한 팀 (한 곳에 여럿이면 가장 나중에 기록한 것)
        entry, many = find_entry(interaction.channel_id, lambda x: bool(x.get("result")), newest=True)
        if entry is None and many:
            await answer(interaction, which(actor, [x.get("place_id") for x in many], "결과를 기록한"))
            return
        if entry is None:
            await answer(interaction, f"{actor}님, 되돌릴 결과가 없어요. `/승리` 로 기록한 결과만 되돌릴 수 있어요.")
            return
        try:
            await change_league({"mode": "undo", "matchId": entry["result"]["match_id"]}, entry=entry)
        except SeasonOver:  # 팀을 짠 뒤에 새 시즌이 시작됐다. 이 결과는 보관된 지난 시즌의 기록에 있어서 봇이 되돌릴 수 없다
            await answer(interaction, f"{actor}님, 이 결과는 지난 시즌의 기록이라 봇으로는 되돌릴 수 없어요. 고쳐야 한다면 리그 관리자에게 알려 주세요.")
            return
        except LaterMatches as e:  # 이 경기 뒤에 같은 선수가 뛴 경기가 기록돼 있다. 그 경기부터 되돌려야 한다
            await undo_blocked(interaction, actor, e.matches)
            return
        except ServerGlitch as e:  # 서버가 답하지 않았다. 되돌린 것이 들어갔는지 모른다
            print(f"결과 되돌리기 실패: {e!r}")
            await answer(interaction, f"{actor}님, 리그 서버가 답하지 않아 결과를 되돌렸는지 확인하지 못했어요. ({e})\n"
                                      "잠시 뒤에 `/승리취소` 를 다시 입력해 주세요. 이미 되돌려져 있으면 그대로 마무리합니다.")
            return
        except Exception as e:
            print(f"결과 되돌리기 실패: {e!r}")
            await answer(interaction, f"{actor}님, 결과를 되돌리지 못했어요. 리그 관리자에게 리그 매니저로 고쳐 달라고 알려 주세요. ({e})")
            return
        entry["result"] = None
        save_state()
        await send_to(entry["place_id"], f"{actor}님이 경기 결과 기록을 취소했어요. MMR과 전적을 기록하기 전으로 되돌렸어요.")
    await answer(interaction, f"{actor}님이 결과 기록을 취소하고 MMR을 되돌렸어요. 다시 기록하려면 `/승리` 를 쓰세요.")


@bot.tree.command(name="선수역할", description="승인한 선수에게 자동으로 줄 역할을 정합니다. 승인을 풀면(대기·제외) 뺍니다 (리그 관리자 전용)", guild=GUILD)
@app_commands.rename(role="역할", off="끄기", manager_role="관리자역할")
@app_commands.describe(role="승인한 선수에게 줄 역할. 비우면 지금 설정을 보여 주고 바로 한 번 맞춥니다", off="자동으로 역할 주기를 끕니다",
                       manager_role="이 명령어를 쓸 수 있는 리그 관리자 역할을 정합니다 (서버 관리자 권한이 있는 사람만 정할 수 있어요)")
async def player_role(interaction: discord.Interaction, role: Optional[discord.Role] = None, off: Optional[bool] = None,
                      manager_role: Optional[discord.Role] = None) -> None:
    # 봇이 누구에게 어떤 역할을 줄지를 바꾸는 명령어라 리그 관리자만 쓴다. 리그 운영진도 쓸 수 있으면, 역할을 잘못 골랐을 때
    # 승인된 선수 모두에게 그 역할이 간다 (운영자가 2026-10-09에 리그 관리자만 쓰게 해 달라고 함)
    if not await admin_only(interaction, manager=True):
        return
    await interaction.response.defer()
    actor = by(interaction)
    if manager_role is not None:
        # 리그 관리자 역할은 서버 관리자 권한이 있는 사람만 정한다 (리그 관리자가 그 범위를 스스로 넓히지 못하게)
        if not interaction.user.guild_permissions.administrator:
            await answer(interaction, f"{actor}님, 리그 관리자 역할은 서버 관리자 권한이 있는 사람만 정할 수 있어요.")
            return
        if manager_role.is_default() or manager_role.managed:
            await answer(interaction, f"{actor}님, **{manager_role.name}** 역할은 리그 관리자 역할로 정할 수 없어요(@everyone 이거나 봇·연동이 관리하는 역할).")
            return
        bot.manager_role_id = manager_role.id
        save_state()
        await answer(interaction, f"{actor}님이 리그 관리자 역할을 {manager_role.mention} 역할로 정했어요. "
                                  "이제 이 역할이 있는 사람과 서버 관리자 권한이 있는 사람만 `/선수역할` 을 쓸 수 있어요.")
        if role is None and not off:
            return
    if off:
        # 꺼 둔 동안 시즌이 넘어가도, 다시 켰을 때 역할을 거두지 않도록 시즌 번호도 잊는다
        bot.player_role_id, bot.role_seen, bot.role_season_no = 0, {}, None
        save_state()
        await answer(interaction, f"{actor}님이 리그 선수 역할 자동 부여를 껐어요. 이미 준 역할은 그대로 둡니다. 다시 켜려면 `/선수역할` 에서 역할을 골라 주세요.")
        return
    if role is not None:
        problem = role_problem(await get_guild(), role)
        if problem:
            await answer(interaction, f"{actor}님, {role.mention} 역할로는 켤 수 없어요. {problem}")
            return
        if role.id != bot.player_role_id:
            bot.player_role_id, bot.role_seen = role.id, {}  # 역할이 바뀌면 처음부터 다시 맞춘다
            save_state()
    if not bot.player_role_id:
        await answer(interaction, f"{actor}님, 리그 선수 역할 자동 부여가 꺼져 있어요. `/선수역할` 에서 **역할**을 고르면, 리그 관리자 페이지에서 승인한 선수에게 그 역할을 주고 승인을 푼(대기·제외) 선수에게서는 뺍니다.")
        return
    if not (SYNC_URL and SYNC_KEY):
        await answer(interaction, f"{actor}님, 역할은 정했지만, 봇이 등록 명단을 읽을 수 없어요. `config.json` 에 `sync_url` 과 `sync_key` 를 넣고 봇을 다시 켜 주세요.")
        return
    try:
        out = await sync_roles(force=True)
    except Exception as e:
        print(f"리그 선수 역할 맞추기 실패: {e!r}")
        await answer(interaction, f"{actor}님, 등록 명단을 읽지 못했어요. 잠시 뒤에 다시 해 주세요. ({e})")
        return
    bot.role_note = out["problem"]
    done = roles_text(out).replace("🎫 **리그 선수 역할**\n", "")  # 문제가 생기기 전에 처리한 것이 있으면 그것도 알린다
    if out["problem"]:
        text = f"{actor}님, **리그 선수 역할**을 맞추지 못했어요. " + out["problem"] + (f"\n{done}" if done else "")
    else:
        head = f"{actor}: 🎫 승인한 선수에게 <@&{bot.player_role_id}> 역할을 자동으로 줍니다. 승인을 풀면(대기·제외) 뺍니다. ({minutes_text(ROLE_POLL_SECONDS)}마다 확인)"
        more = f"\n나머지 {out['left']}명은 이어서 처리합니다." if out["left"] else ""
        text = f"{head}\n{done or '지금은 새로 주거나 뺄 사람이 없어요.'}{more}"
    await answer(interaction, text)


# ── 슬래시 명령어: 참가자 ─────────────────────────────────────
async def open_recruitment(interaction: discord.Interaction) -> Recruitment | None:
    """/참여·/참여취소 공통 확인: 모집 중인 내전의 글(일반 채널이면 그 채널)에서 입력했는지"""
    here = games_at(interaction.channel_id)
    rec = here[-1] if here else None
    if rec is not None and not rec.closed:
        return rec
    opened = [g.place_id for g in bot.games if not g.closed]
    await interaction.response.send_message(f"{links(opened)} 에서 입력해 주세요." if opened else "지금은 모집 중인 내전이 없어요.", ephemeral=True)
    return None


def busy_elsewhere(uid: int, rec: Recruitment) -> str:
    """이 사람이 rec 에 참여할 수 없는 까닭(다른 내전에 들어 있다). 참여할 수 있으면 빈 글.
    한 사람이 두 내전에 동시에 들어가지 못하게 한다. 문구는 운영자가 정했다(2026-10-11).
     - 모집 중인 다른 내전에 참여 신청을 해 둔 사람
     - 팀이 짜였는데 결과가 아직 기록되지 않은 판에서 뛰는 사람. 그 판에서 쉬는 사람은 막지 않는다.
       마감 처리 중이라 팀이 아직 나오지 않은 내전의 참가자는 누가 뛸지 모르므로 모두 막는다(몇 초다)"""
    for g in bot.games:
        if g is not rec and not g.cancelled and not g.closed and uid in g.participants:
            return f"이미 다른 내전에 참여 신청을 했습니다.\n<#{g.place_id}>"
    mine = rec.message.id if rec.message else 0
    entry = pending_entry(uid)
    if entry is not None and (entry.get("message_id") != mine or entry.get("place_id") != rec.place_id):
        return f"아직 참여 중인 게임의 결과가 기록되지 않아 다음 경기에 참여할 수 없습니다.\n<#{entry.get('place_id')}>"
    for g in bot.games:
        if g is not rec and g.matching and uid in g.participants:
            return f"아직 참여 중인 게임의 결과가 기록되지 않아 다음 경기에 참여할 수 없습니다.\n<#{g.place_id}>"
    return ""


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
    elsewhere = busy_elsewhere(uid, rec)  # 확인하고 명단에 넣기까지 기다리는 곳이 없어서, 두 내전에 동시에 입력해도 한쪽만 들어간다
    if elsewhere:
        await interaction.response.send_message(elsewhere, ephemeral=True)
        return

    rec.participants[uid] = {"name": interaction.user.display_name, "username": interaction.user.name}
    if uid in bot.wants:  # /내전하자 로 기다리던 사람이 판에 들어왔다. 기다리는 사람으로는 더 세지 않는다
        bot.want_joined.add(uid)
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


# ── /내전하자: 지금 내전을 하고 싶다고 알리기 ───────────────────────
# 리그 선수가 대화방에서 /내전하자 를 입력하면(또는 모집판의 참여 희망 버튼을 누르면) 한 시간 동안 "지금 내전을 하고 싶은 사람"으로 남는다.
# 그런 사람이 10명이 되면 대화방에서 리그 운영진 역할을 멘션해 로비(모집)를 만들어 달라고 알린다 (운영자가 2026-10-09에 정한 기능).
# 한 시간이 지난 사람은 명령어가 들어올 때와 모집판을 확인할 때(want_loop) 빼고 센다.
# 모집판(2026-10-11, 운영자가 정함: 본인에게만 답하면 서로 하고 싶은지 몰라 10명이 모이지 않는다):
#  - 대화방에 기다리는 사람들과 '참여 희망' 버튼이 있는 글을 하나 둔다. 버튼을 누르면 /내전하자 를 입력한 것과 같다.
#  - 등록한 사람에게만 보이는 답에 '참여 취소' 버튼을 단다. 이미 등록한 사람이 참여 희망을 다시 눌러도 그 버튼이 보인다.
#  - 사람이 늘 때마다 앞의 글을 지우고 새로 올려 대화방 맨 아래에 오게 한다. 줄 때(참여 취소, 한 시간이 지남, 모집에 /참여)는 그 자리에서 고치고,
#    아무도 없으면 지운다. 이름은 멘션으로 적되 알림은 울리지 않는다. 알림은 지금처럼 10명이 모였을 때 리그 운영진에게만 간다.
def wanting(now: float | None = None) -> list[int]:
    """지금 내전을 기다리는 사람들. 한 시간이 지난 사람은 지우고, 그사이 모집에 /참여 한 사람은 세지 않는다."""
    now = time.time() if now is None else now
    bot.wants = {uid: at for uid, at in bot.wants.items() if now - at < WANT_SECONDS}
    bot.want_joined &= set(bot.wants)
    who = [uid for uid in bot.wants if uid not in bot.want_joined]
    if len(who) < PLAYERS_NEEDED:
        bot.want_alerted = False  # 10명 아래로 내려갔다. 다시 10명이 되면 또 알린다
    return who


def staff_role_id() -> int:
    """리그 운영진 역할. /내전하자설정 으로 정한 역할이 먼저고, 없으면 config.json 의 admin_role_id"""
    return bot.want_role_id or ADMIN_ROLE_ID


async def can_want(user: discord.abc.User) -> bool:
    """리그 선수 이상인가: 리그 선수 역할(/선수역할 로 정한 역할)이 있거나, 리그 운영진·리그 관리자다.
    리그 선수 역할을 정해 두지 않았으면 가릴 수 없으므로 누구나 쓴다."""
    if not isinstance(user, discord.Member):
        return False
    if not bot.player_role_id:
        return True
    mine = {role.id for role in user.roles}
    if bot.player_role_id in mine or (staff_role_id() and staff_role_id() in mine):
        return True
    return await is_admin(user, False)


def want_problem(guild: discord.Guild) -> str:
    """/내전하자 의 알림을 대화방에 올릴 수 없거나, 리그 운영진 역할을 멘션해도 알림이 울리지 않는 까닭. 문제가 없으면 빈 글."""
    me = guild.me
    channel = guild.get_channel(bot.want_channel_id) if bot.want_channel_id else None
    if bot.want_channel_id:
        if channel is None:
            return "정해 둔 대화방을 찾지 못했어요. `/내전하자설정` 의 **대화방** 칸에서 다시 골라 주세요."
        perms = channel.permissions_for(me) if me is not None else None
        if perms is not None and not (perms.view_channel and perms.send_messages):
            return f"봇이 {channel.mention} 에 글을 올릴 수 없어요. 그 채널의 권한에서 봇에게 **채널 보기**와 **메시지 보내기**를 허용해 주세요."
    role_id = staff_role_id()
    if not role_id:
        return "리그 운영진 역할을 정하지 않아, 10명이 모여도 멘션하지 못해요. `/내전하자설정` 의 **운영진역할** 칸에서 골라 주세요."
    role = guild.get_role(role_id)
    if role is None:
        return "정해 둔 리그 운영진 역할을 찾지 못했어요. `/내전하자설정` 의 **운영진역할** 칸에서 다시 골라 주세요."
    if me is not None and not role.mentionable:
        # 누구나 멘션할 수 있게 해 둔 역할이 아니면, 봇에 모든 역할을 멘션하는 권한이 있어야 알림이 울린다
        perms = channel.permissions_for(me) if channel is not None else me.guild_permissions
        if not perms.mention_everyone:
            return (f"봇이 **{role.name}** 역할을 멘션해도 알림이 울리지 않아요. 서버 설정 → 역할에서 그 역할의 "
                    "**누구나 이 역할을 멘션할 수 있도록 허용**을 켜거나, 봇의 역할에 **@everyone, @here, 모든 역할 멘션하기**를 켜 주세요.")
    return ""


async def want_status() -> str:
    """지금 설정을 한 줄로 (켤 때 창에 찍는다)"""
    try:
        guild = await get_guild()
    except discord.HTTPException as e:
        return f"[확인 필요] 디스코드 서버를 확인하지 못했습니다 ({e})"
    channel = guild.get_channel(bot.want_channel_id) if bot.want_channel_id else None
    role = guild.get_role(staff_role_id()) if staff_role_id() else None
    where = f"대화방 #{channel.name}" if channel is not None else "대화방을 정하지 않음(어느 채널에서나 받습니다)"
    who = f"알릴 역할 @{role.name}" if role is not None else "알릴 역할을 정하지 않음"
    problem = want_problem(guild)
    return f"{where}, {who}" + (f" [확인 필요] {problem}" if problem else " - 권한 확인")


async def announce_want(channel_id: int, count: int) -> None:
    """10명이 모였다고 대화방에 알린다. 리그 운영진 역할을 멘션해 알림이 가게 한다 (봇의 다른 글은 역할 알림을 막아 두었다)."""
    role_id = staff_role_id()
    text = (f"<@&{role_id}> " if role_id else "") + f"지금 **{count}명**이 내전에 참여할 준비가 되어 있습니다. 내전 생성이 가능한 리그 운영진은 로비를 만들어 주세요."
    mentions = discord.AllowedMentions(everyone=False, users=False, roles=[discord.Object(id=role_id)] if role_id else False)
    try:
        channel = await get_channel(channel_id)
        await channel.send(text, allowed_mentions=mentions)
    except discord.HTTPException as e:
        print(f"내전하자 알림 전송 실패: {e}")
        await tell_admins(f"`/내전하자` 로 {count}명이 모였는데 <#{channel_id}> 에 알리지 못했어요. 봇이 그 채널에 글을 올릴 수 있는지 확인해 주세요. ({e})")
        return
    if not role_id:
        await tell_admins(f"`/내전하자` 로 {count}명이 모였어요. 리그 운영진 역할을 정해 두지 않아 멘션은 하지 못했어요. "
                          "리그 관리자가 `/내전하자설정` 의 **운영진역할** 칸에서 정해 주세요.")


def board_text(who: list[int]) -> str:
    """모집판의 글. 기다리는 사람은 멘션으로 적는다(알림이 울리지 않게 보낸다). 아주 많으면 앞에서부터 WANT_NAMES 명만 적는다"""
    names = " · ".join(f"<@{uid}>" for uid in who[:WANT_NAMES]) + (f" 외 {len(who) - WANT_NAMES}명" if len(who) > WANT_NAMES else "")
    goal = f"{PLAYERS_NEEDED}명이 모이면 리그 운영진을 부릅니다" if len(who) < PLAYERS_NEEDED else f"{PLAYERS_NEEDED}명이 모였습니다"
    return (f"🙋 지금 내전을 하고 싶어 하는 사람이 **{len(who)}명** 있습니다. ({goal})\n{names}\n"
            "함께하려면 아래 **참여 희망** 버튼을 누르거나 `/내전하자` 를 입력하세요. 한 시간 동안 유지됩니다.")


class WantView(discord.ui.View):
    """모집판에 쓰는 버튼 묶음. 봇을 껐다 켜도 눌리게 시간 제한을 두지 않고 버튼마다 custom_id 를 정해 둔다(켤 때 setup_hook 이 다시 등록한다)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        print(f"버튼 처리 오류: {error!r}")
        msg = "처리 중 오류가 발생했어요. 리그 운영진에게 알려 주세요."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass


class WantBoard(WantView):
    """모집판에 다는 버튼: 참여 희망 (/내전하자 를 입력한 것과 같다)"""

    @discord.ui.button(label="참여 희망", style=discord.ButtonStyle.success, custom_id="want:join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await want_join(interaction)


class WantLeave(WantView):
    """등록한 사람에게만 보이는 답에 다는 버튼: 참여 취소"""

    @discord.ui.button(label="참여 취소", style=discord.ButtonStyle.secondary, custom_id="want:leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await want_leave(interaction)


async def erase_board(board: dict) -> None:
    """모집판 글을 지운다. 이미 지워져 있으면 넘어간다"""
    try:
        channel = await get_channel(board["channel_id"])
        await channel.get_partial_message(board["message_id"]).delete()
    except discord.NotFound:
        pass
    except discord.HTTPException as e:
        print(f"앞의 내전하자 모집판을 지우지 못했습니다: {e}")


async def show_board(channel_id: int = 0, fresh: bool = False) -> None:
    """모집판을 지금 기다리는 사람들에 맞춘다. 실패해도 넘어간다(등록과 취소는 이미 끝났다).
    fresh 면 앞의 글을 지우고 새로 올려 대화방 맨 아래에 오게 한다(사람이 늘었을 때). 아니면 그 자리에서 고친다. 기다리는 사람이 없으면 지운다.
    여러 사람이 한꺼번에 누르면 요청이 겹치는데, 기다리던 요청은 가장 나중 것만 한다(그것이 지금 상태를 그대로 올린다)."""
    bot.want_fresh = bot.want_fresh or fresh
    bot.want_seq += 1
    seq = bot.want_seq
    async with bot.want_lock:
        if seq != bot.want_seq:
            return
        fresh, bot.want_fresh = bot.want_fresh, False
        who, old = wanting(), bot.want_board
        place = channel_id or bot.want_channel_id or (old or {}).get("channel_id") or 0
        quiet = discord.AllowedMentions.none()
        try:
            if not who:
                bot.want_board = None
            elif old and not fresh and old.get("channel_id") == place:
                try:
                    channel = await get_channel(place)
                    await channel.get_partial_message(old["message_id"]).edit(content=board_text(who), view=WantBoard(), allowed_mentions=quiet)
                    old["who"] = who
                    return
                except discord.NotFound:  # 누가 모집판을 지웠다. 새로 올린다
                    old = None
            if who and place:
                channel = await get_channel(place)
                msg = await channel.send(board_text(who), view=WantBoard(), allowed_mentions=quiet)
                bot.want_board = {"channel_id": place, "message_id": int(msg.id), "who": who}
            if old:  # 새 글을 올린 뒤에 앞의 것을 지운다. 올리지 못했으면 앞의 것이 남는다
                await erase_board(old)
        except discord.HTTPException as e:
            print(f"내전하자 모집판을 맞추지 못했습니다: {e}")
        finally:
            save_state()


async def board_tick() -> None:
    """모집판이 지금 기다리는 사람들과 다르면 맞춘다: 한 시간이 지나 빠진 사람, 그사이 모집에 /참여 한 사람"""
    if bot.want_board and wanting() != bot.want_board.get("who"):
        await show_board()


async def want_loop() -> None:
    """모집판을 지금 상태로 맞춰 둔다. 오류가 나도 멈추지 않는다."""
    while True:
        await asyncio.sleep(WANT_TICK_SECONDS)
        try:
            await board_tick()
        except Exception as e:
            print(f"내전하자 모집판 확인 실패: {e!r}")


async def want_join(interaction: discord.Interaction, typed: bool = False) -> None:
    """내전하자에 등록한다. /내전하자 와 모집판의 참여 희망 버튼이 함께 쓴다.
    typed 는 명령어로 입력한 경우다: 대화방에서 입력했는지 본다(버튼은 모집판이 있는 곳에서 누르니 보지 않는다)."""
    if typed and bot.want_channel_id and interaction.channel_id != bot.want_channel_id:
        await interaction.response.send_message(f"이 명령어는 <#{bot.want_channel_id}> 에서 써 주세요.", ephemeral=True)
        return
    if not await can_want(interaction.user):
        await interaction.response.send_message(
            "이 명령어를 사용할 권한이 없어요. 리그 선수만 쓸 수 있는 명령어예요. 선수 등록을 하고 승인을 받으면 쓸 수 있어요.", ephemeral=True)
        return
    uid, now = interaction.user.id, time.time()
    who = wanting(now)
    opened = [g for g in bot.games if not g.closed]  # 지금 모집 중인 내전들
    rec = opened[-1] if opened else None
    hint = f"\n👉 지금 모집 중인 내전이 있습니다. {links(g.place_id for g in opened)} 에서 `/참여` 를 입력하세요." if opened else ""
    if uid in bot.wants:  # 이미 등록했다. 등록한 시각은 그대로 두고, 빠질 수 있게 참여 취소 버튼을 보여 준다
        until = int(bot.wants[uid] + WANT_SECONDS)
        await interaction.response.send_message(
            f"이미 내전하자에 등록했습니다. <t:{until}:t>(<t:{until}:R>)까지 유지됩니다.\n"
            f"지금 내전을 하고 싶어 하는 사람이 **{len(who)}명** 있습니다. 빠지려면 아래 **참여 취소** 버튼을 누르세요.{hint}",
            ephemeral=True, view=WantLeave())
        return

    bot.wants[uid] = now
    if any(uid in g.participants for g in opened):  # 이미 모집에 참여해 있는 사람은 기다리는 사람으로 세지 않는다
        bot.want_joined.add(uid)
    who = wanting(now)
    # 모집이 열려 있는 동안에는 알리지 않는다(이미 로비가 만들어졌다). 그 모집이 끝난 뒤에도 10명이 기다리면 다음 입력 때 알린다.
    # 방금 알렸으면 잠깐은 다시 알리지 않는다: 참여 희망과 취소를 되풀이해 10명을 오르내리면 리그 운영진의 알림이 거듭 울린다
    alert = len(who) >= PLAYERS_NEEDED and not bot.want_alerted and rec is None and now - bot.want_alert_at >= WANT_ALERT_GAP
    if alert:
        bot.want_alerted = True
        bot.want_alert_at = now
    save_state()
    until = int(now + WANT_SECONDS)
    text = (f"✅ 내전하자에 등록했습니다. 지금 내전을 하고 싶어 하는 사람이 **{len(who)}명** 있습니다.\n"
            f"<t:{until}:t>까지 한 시간 동안 유지되고, {PLAYERS_NEEDED}명이 모이면 리그 운영진에게 알립니다. 빠지려면 아래 **참여 취소** 버튼을 누르세요.")
    if alert:
        text += f"\n📣 {len(who)}명이 모여 리그 운영진에게 알렸습니다."
    await interaction.response.send_message(text + hint, ephemeral=True, view=WantLeave())
    place = bot.want_channel_id or interaction.channel_id
    if uid in who:  # 기다리는 사람이 늘었다. 모집판을 새로 올려 대화방 맨 아래에 오게 한다
        await show_board(place, fresh=True)
    if alert:  # 모집판 아래에 글을 하나 더 올려 리그 운영진을 부른다
        await announce_want(place, len(who))


async def want_leave(interaction: discord.Interaction) -> None:
    """참여 취소 버튼: 내전하자 등록을 지운다. 버튼이 달려 있던(본인에게만 보이는) 글을 결과로 바꾼다. 취소한 뒤에는 바로 다시 등록할 수 있다."""
    uid = interaction.user.id
    wanting()
    if bot.wants.pop(uid, None) is None:
        await interaction.response.edit_message(content="내전하자에 등록되어 있지 않습니다. 이미 취소했거나 한 시간이 지났습니다.", view=None)
        return
    bot.want_joined.discard(uid)
    who = wanting()
    save_state()
    await interaction.response.edit_message(
        content=f"내전하자 등록을 취소했습니다. 지금 내전을 하고 싶어 하는 사람이 **{len(who)}명** 있습니다.", view=None)
    await show_board()


@bot.tree.command(name="내전하자", description="지금 내전을 하고 싶다고 알립니다. 한 시간 동안 유지되고, 10명이 모이면 리그 운영진에게 알려요 (리그 선수)", guild=GUILD)
async def want_game(interaction: discord.Interaction) -> None:
    await want_join(interaction, typed=True)


@bot.tree.command(name="내전하자설정", description="/내전하자 를 쓰는 대화방과, 10명이 모였을 때 알릴 리그 운영진 역할을 정합니다 (리그 관리자 전용)", guild=GUILD)
@app_commands.rename(channel="대화방", role="운영진역할")
@app_commands.describe(channel="선수들이 /내전하자 를 입력하는 채널. 10명이 모이면 이 채널에 알립니다. 비우면 지금 설정을 보여 줍니다",
                       role="10명이 모였을 때 멘션할 리그 운영진 역할")
async def want_setup(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, role: Optional[discord.Role] = None) -> None:
    if not await admin_only(interaction, manager=True):
        return
    await interaction.response.defer()
    actor = by(interaction)
    if role is not None and (role.is_default() or role.managed):
        await answer(interaction, f"{actor}님, **{role.name}** 역할은 고를 수 없어요(@everyone 이거나 봇·연동이 관리하는 역할).")
        return
    changed = channel is not None or role is not None
    if channel is not None:
        bot.want_channel_id = channel.id
    if role is not None:
        bot.want_role_id = role.id
    if changed:
        save_state()
    where = f"<#{bot.want_channel_id}>" if bot.want_channel_id else "정하지 않음 (어느 채널에서나 받고, 10명이 모이면 입력한 채널에 알려요)"
    who = f"<@&{staff_role_id()}>" if staff_role_id() else "정하지 않음"
    problem = want_problem(await get_guild())
    await answer(interaction, (f"{actor}님이 `/내전하자` 설정을 바꿨어요." if changed else f"{actor}님, `/내전하자` 설정이에요.")
                 + f"\n- 대화방: {where}\n- 10명이 모이면 알릴 역할: {who}"
                 + f"\n- 지금 기다리는 사람: {len(wanting())}명 (등록하면 한 시간 동안 유지돼요)"
                 + (f"\n⚠️ {problem}" if problem else ""))


# ── /포지션변경: 내 포지션 순서 바꾸기 ───────────────────────────
# 선수가 등록할 때 정한 포지션 순서(1지망~4지망)를 디스코드에서 직접 바꾼다(운영자가 2026-10-11에 요청).
# 전에는 승인된 뒤에는 본인이 고칠 수 없어서, 리그 관리자가 대기로 돌려 주거나 매니저에서 고쳐야 했다.
# 누구의 등록인지는 서버가 디스코드 계정(숫자 ID나 사용자명)으로 찾고, 등록 탭과 선수단을 함께 고친다(adminSetPrefs, 서버 버전 14).
POSITION_NAMES = ["캐리", "미드", "오프", "서폿"]  # 지망 번호 1~4 (등록 양식과 같다. 서폿은 4번과 5번을 함께 뜻한다)
POSITION_CHOICES = [app_commands.Choice(name=n, value=i + 1) for i, n in enumerate(POSITION_NAMES)]


def pending_entry(uid: int) -> dict | None:
    """이 사람이 뛰는, 팀이 짜였고 결과를 아직 기록하지 않은 판. 없으면 None. 그 판에서 쉬는 사람은 뛰는 사람이 아니다"""
    for x in bot.lineups:
        if not waiting_result(x):
            continue
        who = x.get("who") or {}
        if any(who.get(pid) == uid for pid in x.get("ids", [])):
            return x
    return None


def in_pending_lineup(uid: int) -> bool:
    """팀이 짜였고 결과를 아직 기록하지 않은 판에서 뛰는 사람인지.
    그런 사람의 지망을 바꾸면, 팀을 알릴 때 적은 이기면·지면 점수와 실제 정산이 달라진다(정산은 그때의 지망으로 계산한다)."""
    return pending_entry(uid) is not None


@bot.tree.command(name="포지션변경", description="내 포지션 순서를 바꿉니다. 1지망부터 차례로 골라 주세요 (리그 선수)", guild=GUILD)
@app_commands.rename(first="1지망", second="2지망", third="3지망", fourth="4지망")
@app_commands.describe(first="가장 하고 싶은 포지션", second="두 번째로 하고 싶은 포지션", third="세 번째로 하고 싶은 포지션", fourth="네 번째로 하고 싶은 포지션")
@app_commands.choices(first=POSITION_CHOICES, second=POSITION_CHOICES, third=POSITION_CHOICES, fourth=POSITION_CHOICES)
async def change_positions(interaction: discord.Interaction, first: app_commands.Choice[int], second: app_commands.Choice[int],
                           third: app_commands.Choice[int], fourth: app_commands.Choice[int]) -> None:
    user = interaction.user
    prefs = [first.value, second.value, third.value, fourth.value]
    if sorted(prefs) != [1, 2, 3, 4]:
        await interaction.response.send_message(
            "포지션 네 가지를 한 번씩만 골라 주세요. 예) `/포지션변경 1지망:서폿 2지망:캐리 3지망:미드 4지망:오프`", ephemeral=True)
        return
    if not (SYNC_URL and SYNC_KEY):
        await interaction.response.send_message("봇이 리그 서버에 이어져 있지 않아 바꿀 수 없어요. 리그 관리자에게 알려 주세요.", ephemeral=True)
        return
    if in_pending_lineup(user.id):
        await interaction.response.send_message(
            "지금 팀이 짜여 결과를 기다리는 내전에 들어 있어서 바꿀 수 없어요. 경기 결과가 기록된 뒤에 다시 입력해 주세요.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)  # 서버에 다녀오는 데 3초를 넘길 수 있다
    try:
        r = await call_server({"action": "adminSetPrefs", "discord": [str(user.id), str(user.name)], "prefs": prefs})
    except ServerError as e:
        if e.code == "unknown":
            text = (f"등록한 선수를 찾지 못했어요. 선수 등록을 할 때 적은 디스코드 사용자명이 지금 계정(`{str(user.name).replace('`', '')}`)과 같은지 확인해 주세요. "
                    "다르게 적었다면 리그 관리자에게 알려 주세요.")
        elif e.code == "locked":
            text = "제외된 등록이라 포지션 순서를 바꿀 수 없어요."
        elif e.code in ("pending", "league"):
            text = "지금은 바꾸지 못했어요. 잠시 뒤에 다시 입력해 주세요."
        else:  # 이 요청을 모르는 예전 서버 등
            print(f"포지션 순서 바꾸기 실패: {e!r}")
            text = f"바꾸지 못했어요. 리그 관리자에게 알려 주세요. ({e})"
        await interaction.followup.send(text, ephemeral=True)
        return
    except Exception as e:  # 서버가 답하지 않았다. 다시 입력해도 결과는 같다
        print(f"포지션 순서 바꾸기 실패: {e!r}")
        await interaction.followup.send("리그 서버가 답하지 않아 바꿨는지 확인하지 못했어요. 잠시 뒤에 다시 입력해 주세요.", ephemeral=True)
        return
    order = " · ".join(f"{k + 1}지망 **{POSITION_NAMES[n - 1]}**" for k, n in enumerate(prefs))
    if r.get("status") == "승인":
        tail = "다음에 짜는 팀부터 이 순서로 배정해요."
    else:
        tail = "아직 승인 전이라 등록 내용만 고쳤어요. 승인되면 이 순서로 선수단에 들어가요."
    await interaction.followup.send(f"✅ 포지션 순서를 바꿨어요.\n{order}\n{tail}", ephemeral=True)


# ── /도움말: 내가 쓸 수 있는 명령어 ─────────────────────────────
@bot.tree.command(name="도움말", description="내가 쓸 수 있는 퍼그나봇 명령어를 보여 줍니다", guild=GUILD)
async def show_help(interaction: discord.Interaction) -> None:
    """입력한 사람의 자리(리그 관리자, 리그 운영진, 리그 선수, 그 밖)에 맞춰, 쓸 수 있는 명령어만 본인에게 보여 준다."""
    user = interaction.user
    manager = is_manager(user)
    staff = manager or await is_admin(user, interaction.channel_id == ADMIN_CHANNEL_ID)
    player = staff or await can_want(user)
    if manager:
        head = "**리그 관리자**가 쓸 수 있는 명령어예요."
    elif staff:
        head = "**리그 운영진**이 쓸 수 있는 명령어예요."
    elif player:
        head = "**리그 선수**가 쓸 수 있는 명령어예요."
    else:
        head = "지금 쓸 수 있는 명령어예요. 선수 등록을 하고 승인을 받으면 `/내전하자` 도 쓸 수 있어요."
    parts = ["**퍼그나봇 명령어**\n" + head]
    parts.append("**누구나**\n"
                 "`/참여` · `/참여취소` — 내전 모집 글에서 참여를 신청하거나 취소해요.\n"
                 "`/포지션변경` — 등록한 포지션 순서를 바꿔요. 1지망부터 차례로 골라요. (선수 등록을 한 사람)\n"
                 "`/도움말` — 이 안내를 다시 봐요.")
    if player:
        where = f"<#{bot.want_channel_id}> 에서 써요. " if bot.want_channel_id else ""
        parts.append("**리그 선수**\n"
                     f"`/내전하자` — {where}지금 내전을 하고 싶다고 알려요. 대화방의 모집판에 이름이 올라가고 한 시간 동안 유지돼요. "
                     f"모집판의 **참여 희망** 버튼을 눌러도 돼요. {PLAYERS_NEEDED}명이 모이면 리그 운영진에게 알려요.")
    if staff:
        parts.append("**리그 운영진**\n"
                     f"`/내전생성` — <#{ADMIN_CHANNEL_ID}> 에서 써요. 내전 모집을 열어요. **마감** 칸에 마감 시각을 적을 수 있어요. 동시에 {MAX_GAMES}개까지 진행할 수 있어요.\n"
                     "아래 명령어는 **그 내전의 글**에서 써요. 입력한 글의 내전에 적용돼요.\n"
                     "`/마감` — 지금까지 모인 인원으로 바로 마감해요.\n"
                     f"`/연장` — 마감을 {minutes_text(EXTEND_SECONDS)} 뒤로 미뤄요. 마감한 뒤에도 다시 열 수 있어요.\n"
                     f"`/재모집` — 모인 사람을 모두 참여 취소로 돌리고 {minutes_text(RESTART_SECONDS)} 동안 처음부터 다시 받아요.\n"
                     "`/취소` — 이 내전을 취소해요.\n"
                     "`/시작` — 로비 음성 채널에 있는 이 내전의 선수를 팀 음성 채널로 옮겨요.\n"
                     "`/종료` — 이 내전의 팀 음성 채널에 있는 사람을 모두 로비로 옮겨요.\n"
                     "`/승리` — 이긴 팀을 골라 결과를 기록해요. 열리지 않은 판은 **경기 안 함**으로 치워요.\n"
                     "`/승리취소` — 이 내전에 기록한 결과를 되돌려요.")
    if manager:
        parts.append(f"**리그 관리자** (<#{ADMIN_CHANNEL_ID}> 에서 써요)\n"
                     "`/선수역할` — 승인한 선수에게 자동으로 줄 역할을 정해요.\n"
                     "`/내전하자설정` — `/내전하자` 를 쓰는 대화방과, 10명이 모였을 때 알릴 역할을 정해요.")
    await interaction.response.send_message("\n\n".join(parts), ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    print(f"명령어 오류: {error!r}")
    msg = "명령어 처리 중 오류가 발생했어요. 리그 운영진에게 알려 주세요."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


if __name__ == "__main__":
    bot.run(TOKEN)
