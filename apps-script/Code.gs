/**
 * 도타 2 인하우스 리그 서버 (Google Apps Script)
 *
 * 하는 일
 *  - 선수 등록 페이지에서 받은 정보를 이 구글 시트에 저장한다 (시트는 운영진 계정에만 보인다)
 *  - 운영진 키가 있는 사람에게만 등록 명단을 돌려주고, 승인 상태와 등록 기간을 바꾸게 한다
 *  - 리그 매니저가 올린 경기 기록을 받아, 개인 정보를 뺀 공개용 기록으로 내보낸다
 *  - 디스코드 봇이 올린 참가 명단을 보관했다가 리그 매니저에 넘겨준다
 *
 * 처음 설치는 README.md의 "1. 구글 시트 서버 만들기"를 따라 하세요.
 * 코드를 고친 뒤에는 배포 → 배포 관리 → 수정(연필) → 버전: 새 버전 → 배포 를 눌러야 반영됩니다.
 */

const SHEET_NAME = '선수등록';
const HEADERS = ['등록시각', '수정시각', '상태', '닉네임', '스팀프로필', '스팀키', '디스코드', 'MMR', '1지망', '2지망', '3지망', '4지망'];
const COL = HEADERS.reduce((o, h, i) => (o[h] = i, o), {});
const PREF_LABELS = ['캐리', '미드', '오프', '서폿'];          // 지망 번호 1~4
const STATUSES = ['대기', '승인', '제외'];
const MAX_MMR = 15000;
const MAX_ROWS = 3000;
const ROSTER_MAX = 60;

/* =========================================================
   설치: 편집기에서 setup 을 한 번 실행하세요
   ========================================================= */
function setup() {
  const sheet = getSheet_();
  const props = PropertiesService.getScriptProperties();
  let key = props.getProperty('ADMIN_KEY');
  if (!key) {
    key = (Utilities.getUuid() + Utilities.getUuid()).replace(/-/g, '');
    props.setProperty('ADMIN_KEY', key);
  }
  if (props.getProperty('REG_OPEN') === null) props.setProperty('REG_OPEN', 'true');
  if (props.getProperty('SEASON') === null) props.setProperty('SEASON', '시즌 1');
  recordsFile_();                                   // 공개 기록 파일을 미리 만들어 권한을 받아 둔다
  Logger.log('준비가 끝났습니다. 시트: ' + sheet.getName());
  Logger.log('운영진 키: ' + key);
  Logger.log('이 키는 운영진 페이지·리그 매니저·디스코드 봇에 넣습니다. 다른 사람에게 보이지 않게 보관하세요.');
}

/** 운영진 키가 새어 나갔을 때 실행하면 새 키를 만듭니다. 운영진 페이지·매니저·봇의 키도 바꿔야 합니다. */
function resetAdminKey() {
  const key = (Utilities.getUuid() + Utilities.getUuid()).replace(/-/g, '');
  PropertiesService.getScriptProperties().setProperty('ADMIN_KEY', key);
  Logger.log('새 운영진 키: ' + key);
}

/* =========================================================
   요청 받기
   ========================================================= */
function doGet(e) {
  return respond_(() => {
    const action = (e && e.parameter && e.parameter.action) || 'status';
    if (action === 'records') return { records: publicRecords_() };
    return statusInfo_();
  });
}

// 브라우저가 미리 묻는 요청(OPTIONS)을 피하려고, 모든 쓰기는 text/plain 본문에 JSON을 담아 POST로 받는다.
function doPost(e) {
  return respond_(() => {
    let body;
    try { body = JSON.parse((e && e.postData && e.postData.contents) || ''); }
    catch (err) { fail_('요청 형식이 잘못됐습니다'); }
    if (!body || typeof body !== 'object') fail_('요청 형식이 잘못됐습니다');

    switch (body.action) {
      case 'register': return register_(body);
      case 'ping': requireAdmin_(body); return statusInfo_();
      case 'adminList': requireAdmin_(body); return { players: listRegistrations_() };
      case 'adminSetStatus': requireAdmin_(body); return setStatus_(body);
      case 'adminConfig': requireAdmin_(body); return setConfig_(body);
      case 'publishRecords': requireAdmin_(body); return publishRecords_(body);
      case 'pushRoster': requireAdmin_(body); return pushRoster_(body);
      case 'adminRoster': requireAdmin_(body); return { roster: getRoster_() };
      default: fail_('알 수 없는 요청입니다');
    }
  });
}

function respond_(fn) {
  let out;
  try {
    out = Object.assign({ ok: true }, fn());
  } catch (err) {
    if (err && err.userFacing) out = { ok: false, error: err.message, code: err.code || '' };
    else {
      console.error(err && err.stack || err);
      out = { ok: false, error: '서버에서 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.' };
    }
  }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}

function fail_(message, code) {
  const err = new Error(message);
  err.userFacing = true;
  err.code = code || '';
  throw err;
}

function requireAdmin_(body) {
  const key = PropertiesService.getScriptProperties().getProperty('ADMIN_KEY');
  if (!key || typeof body.key !== 'string' || body.key !== key) fail_('운영진 키가 맞지 않습니다', 'auth');
}

function withLock_(fn) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(15000)) fail_('요청이 몰려 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.');
  try { return fn(); } finally { lock.releaseLock(); }
}

/* =========================================================
   상태
   ========================================================= */
function statusInfo_() {
  const props = PropertiesService.getScriptProperties();
  const sheet = getSheet_();
  return {
    open: props.getProperty('REG_OPEN') !== 'false',
    season: props.getProperty('SEASON') || '',
    registered: Math.max(0, sheet.getLastRow() - 1),
    recordsAt: props.getProperty('RECORDS_AT') || ''
  };
}

function setConfig_(body) {
  const props = PropertiesService.getScriptProperties();
  if (typeof body.open === 'boolean') props.setProperty('REG_OPEN', String(body.open));
  if (typeof body.season === 'string') props.setProperty('SEASON', body.season.trim().slice(0, 30));
  return statusInfo_();
}

/* =========================================================
   선수 등록
   ========================================================= */
function register_(body) {
  // 사람 눈에 보이지 않는 칸이 채워져 있으면 자동 입력 프로그램으로 보고, 성공한 척만 한다
  if (body.website) return { updated: false };
  if (PropertiesService.getScriptProperties().getProperty('REG_OPEN') === 'false') fail_('지금은 선수 등록 기간이 아닙니다', 'closed');

  const nickname = cleanNickname_(body.nickname);
  const steam = parseSteam_(body.steam);
  const discord = normDiscord_(body.discord);
  const mmr = parseMmr_(body.mmr);
  const prefs = parsePrefs_(body.prefs);

  // 같은 스팀 프로필로 너무 자주 보내는 것을 막는다
  const cache = CacheService.getScriptCache();
  const rlKey = 'rl:' + steam.key;
  if (cache.get(rlKey)) fail_('방금 제출했습니다. 30초 뒤에 다시 시도해 주세요.', 'rate');

  const result = withLock_(() => {
    const sheet = getSheet_();
    const rows = readRows_(sheet);
    if (rows.length >= MAX_ROWS) fail_('등록 인원이 가득 찼습니다. 운영진에게 문의해 주세요.');

    const mine = rows.find(r => r.steamKey === steam.key);
    const nickKey = nickname.toLowerCase().replace(/\s+/g, '');
    const nickOwner = rows.find(r => r.nickname.toLowerCase().replace(/\s+/g, '') === nickKey);
    const discordOwner = rows.find(r => r.discord === discord);

    if (mine && mine.discord !== discord)
      fail_('이 스팀 프로필은 다른 디스코드 계정으로 이미 등록돼 있습니다. 디스코드 계정이 바뀌었다면 운영진에게 알려 주세요.', 'conflict');
    if (!mine && discordOwner)
      fail_('이 디스코드 계정은 다른 스팀 프로필로 이미 등록돼 있습니다. 스팀 프로필이 바뀌었다면 운영진에게 알려 주세요.', 'conflict');
    if (nickOwner && nickOwner.steamKey !== steam.key)
      fail_('다른 선수가 이미 쓰고 있는 닉네임입니다. 다른 닉네임을 넣어 주세요.', 'nickname');

    const now = new Date();
    const prefCells = prefs.map(n => PREF_LABELS[n - 1]);
    if (mine) {
      const line = mine.raw.slice();
      line[COL['수정시각']] = now;
      line[COL['상태']] = mine.status;
      line[COL['닉네임']] = text_(nickname);
      line[COL['스팀프로필']] = text_(steam.url);
      line[COL['스팀키']] = text_(mine.steamKey);
      line[COL['디스코드']] = text_(mine.discord);
      line[COL['MMR']] = mmr;
      prefCells.forEach((v, i) => { line[COL['1지망'] + i] = v; });
      sheet.getRange(mine.rowNumber, 1, 1, HEADERS.length).setValues([line]);
      return { updated: true };
    }
    const line = new Array(HEADERS.length).fill('');
    line[COL['등록시각']] = now;
    line[COL['수정시각']] = now;
    line[COL['상태']] = '대기';
    line[COL['닉네임']] = text_(nickname);
    line[COL['스팀프로필']] = text_(steam.url);
    line[COL['스팀키']] = text_(steam.key);
    line[COL['디스코드']] = text_(discord);
    line[COL['MMR']] = mmr;
    prefCells.forEach((v, i) => { line[COL['1지망'] + i] = v; });
    sheet.appendRow(line);
    return { updated: false };
  });

  cache.put(rlKey, '1', 30);
  return result;
}

// 앞에 '를 붙이면 시트가 글자 그대로 둔다. 닉네임이 =로 시작해도 수식이 되지 않고, 긴 숫자 ID도 반올림되지 않는다.
function text_(v) {
  return "'" + String(v);
}

function cleanNickname_(v) {
  const s = String(v == null ? '' : v).replace(/[\u0000-\u001f\u007f<>]/g, '').replace(/\s+/g, ' ').trim();
  if (!s) fail_('닉네임을 넣어 주세요', 'nickname');
  if (s.length > 20) fail_('닉네임은 20자 이내로 넣어 주세요', 'nickname');
  return s;
}

// 스팀 프로필 주소를 읽어 같은 사람을 가리키는 키를 만든다.
// steamcommunity.com/profiles/7656… 는 숫자 ID, steamcommunity.com/id/이름 은 사용자 지정 주소다.
function parseSteam_(v) {
  const s = String(v == null ? '' : v).trim();
  let m = s.match(/^(?:https?:\/\/)?(?:www\.)?steamcommunity\.com\/profiles\/(7656\d{13})\/?(?:[?#].*)?$/i) || s.match(/^(7656\d{13})$/);
  if (m) return { key: 's:' + m[1], url: 'https://steamcommunity.com/profiles/' + m[1] };
  m = s.match(/^(?:https?:\/\/)?(?:www\.)?steamcommunity\.com\/id\/([A-Za-z0-9_-]{2,64})\/?(?:[?#].*)?$/i);
  if (m) return { key: 'id:' + m[1].toLowerCase(), url: 'https://steamcommunity.com/id/' + m[1] };
  fail_('스팀 프로필 주소를 확인해 주세요. 예) https://steamcommunity.com/profiles/76561197990650432', 'steam');
}

// 디스코드 사용자명(영문 소문자·숫자·밑줄·마침표) 또는 숫자로 된 사용자 ID를 받는다
function normDiscord_(v) {
  const s = String(v == null ? '' : v).trim().replace(/^@/, '').toLowerCase();
  if (/^\d{17,20}$/.test(s)) return s;
  if (/^[a-z0-9_.]{2,32}$/.test(s) && !/\.\./.test(s)) return s;
  if (/^[^#\s]{2,32}#\d{4}$/.test(s)) return s;               // 예전 방식(이름#1234)
  fail_('디스코드 사용자명을 확인해 주세요. 영문 소문자·숫자·밑줄(_)·마침표(.)만 쓸 수 있습니다.', 'discord');
}

function parseMmr_(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0 || n > MAX_MMR || Math.round(n) !== n) fail_('MMR은 0부터 ' + MAX_MMR + ' 사이의 정수로 넣어 주세요', 'mmr');
  return n;
}

function parsePrefs_(v) {
  if (!Array.isArray(v) || v.length !== 4) fail_('포지션 순서를 네 개 모두 정해 주세요', 'prefs');
  const nums = v.map(Number);
  const ok = nums.every(n => Number.isInteger(n) && n >= 1 && n <= 4) && new Set(nums).size === 4;
  if (!ok) fail_('포지션 순서가 잘못됐습니다', 'prefs');
  return nums;
}

/* =========================================================
   운영진: 등록 명단
   ========================================================= */
function readRows_(sheet) {
  const last = sheet.getLastRow();
  if (last < 2) return [];
  const range = sheet.getRange(2, 1, last - 1, HEADERS.length);
  const values = range.getValues();
  const shown = range.getDisplayValues();                // 숫자처럼 생긴 ID가 숫자로 바뀌지 않게 글자 그대로 읽는다
  return values.map((raw, i) => {
    const d = shown[i];
    return {
      rowNumber: i + 2,
      raw,
      registeredAt: toIso_(raw[COL['등록시각']]),
      updatedAt: toIso_(raw[COL['수정시각']]),
      status: STATUSES.indexOf(d[COL['상태']].trim()) >= 0 ? d[COL['상태']].trim() : '대기',
      nickname: d[COL['닉네임']].trim(),
      steamUrl: d[COL['스팀프로필']].trim(),
      steamKey: d[COL['스팀키']].trim(),
      discord: d[COL['디스코드']].trim().toLowerCase(),
      mmr: Number(String(d[COL['MMR']]).replace(/[^\d.]/g, '')) || 0,
      prefs: [0, 1, 2, 3].map(i2 => prefCode_(d[COL['1지망'] + i2]))
    };
  }).filter(r => r.nickname || r.steamKey);
}

function prefCode_(v) {
  const s = String(v).trim();
  const i = PREF_LABELS.indexOf(s);
  if (i >= 0) return i + 1;
  const n = Number(s);
  return n >= 1 && n <= 4 ? n : (n === 5 ? 4 : 0);
}

function toIso_(v) {
  return v instanceof Date && !isNaN(v) ? v.toISOString() : '';
}

function listRegistrations_() {
  return readRows_(getSheet_()).map(r => ({
    registeredAt: r.registeredAt,
    updatedAt: r.updatedAt,
    status: r.status,
    nickname: r.nickname,
    steamUrl: r.steamUrl,
    steamKey: r.steamKey,
    discord: r.discord,
    mmr: r.mmr,
    prefs: r.prefs
  }));
}

function setStatus_(body) {
  const status = String(body.status || '');
  if (STATUSES.indexOf(status) < 0) fail_('상태 값이 잘못됐습니다');
  const keys = Array.isArray(body.steamKeys) ? body.steamKeys.map(String) : [String(body.steamKey || '')];
  const want = new Set(keys.filter(Boolean));
  if (!want.size) fail_('바꿀 선수가 없습니다');
  return withLock_(() => {
    const sheet = getSheet_();
    let changed = 0;
    readRows_(sheet).forEach(r => {
      if (!want.has(r.steamKey)) return;
      sheet.getRange(r.rowNumber, COL['상태'] + 1).setValue(status);
      changed++;
    });
    return { changed };
  });
}

/* =========================================================
   공개 기록
   ========================================================= */
// 공개 페이지에 내보내도 되는 칸만 남긴다. 디스코드·스팀 같은 개인 정보는 여기서 모두 빠진다.
function sanitizeRecords_(r) {
  if (!r || typeof r !== 'object' || !Array.isArray(r.players)) fail_('기록 형식이 잘못됐습니다');
  const int = v => { const n = Math.round(Number(v)); return Number.isFinite(n) ? n : 0; };
  const str = (v, max) => String(v == null ? '' : v).slice(0, max);
  const players = r.players.slice(0, 1000).map(p => ({
    id: str(p.id, 40),
    name: str(p.name, 40),
    baseMMR: int(p.baseMMR),
    mmr: int(p.mmr),
    prefs: Array.isArray(p.prefs) ? p.prefs.slice(0, 4).map(int) : [],
    wins: int(p.wins),
    losses: int(p.losses),
    streak: int(p.streak),
    roleCount: Array.isArray(p.roleCount) && p.roleCount.length === 5 ? p.roleCount.map(int) : [0, 0, 0, 0, 0]
  }));
  const matches = (Array.isArray(r.matches) ? r.matches : []).slice(0, 5000)
    .filter(m => m && (m.winner === 'r' || m.winner === 'd') && Array.isArray(m.rows))
    .map(m => ({
      id: str(m.id, 40),
      at: str(m.at, 40),
      winner: m.winner,
      rows: m.rows.slice(0, 10).map(x => ({
        id: str(x.id, 40), name: str(x.name, 40), side: x.side === 'd' ? 'd' : 'r',
        role: int(x.role), rank: int(x.rank), before: int(x.before), delta: int(x.delta)
      }))
    }));
  return { players, matches };
}

function publishRecords_(body) {
  const clean = sanitizeRecords_(body.records);
  const at = new Date().toISOString();
  clean.publishedAt = at;
  const text = JSON.stringify(clean);
  withLock_(() => {
    recordsFile_().setContent(text);
    PropertiesService.getScriptProperties().setProperty('RECORDS_AT', at);
    putCache_('records', text);
  });
  return { publishedAt: at, players: clean.players.length, matches: clean.matches.length };
}

function publicRecords_() {
  const cached = CacheService.getScriptCache().get('records');
  if (cached) return JSON.parse(cached);
  const text = recordsFile_().getBlob().getDataAsString('UTF-8') || '';
  const data = text ? JSON.parse(text) : { players: [], matches: [] };
  putCache_('records', JSON.stringify(data));
  return data;
}

function recordsFile_() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('RECORDS_FILE_ID');
  if (id) {
    try { return DriveApp.getFileById(id); } catch (err) { /* 지워졌으면 새로 만든다 */ }
  }
  const file = DriveApp.createFile('인하우스_공개기록.json', JSON.stringify({ players: [], matches: [] }), 'application/json');
  props.setProperty('RECORDS_FILE_ID', file.getId());
  return file;
}

function putCache_(key, text) {
  try { if (text.length < 95000) CacheService.getScriptCache().put(key, text, 21600); } catch (err) { /* 캐시는 없어도 된다 */ }
}

/* =========================================================
   디스코드 봇 참가 명단
   ========================================================= */
function pushRoster_(body) {
  const r = body.roster;
  if (!r || !Array.isArray(r.entries)) fail_('참가 명단 형식이 잘못됐습니다');
  const roster = {
    at: new Date().toISOString(),
    entries: r.entries.slice(0, ROSTER_MAX).map(x => ({
      id: String(x.id || '').replace(/\D/g, '').slice(0, 20),
      username: String(x.username || '').slice(0, 32),
      name: String(x.name || '').slice(0, 32)
    })).filter(x => x.id)
  };
  PropertiesService.getScriptProperties().setProperty('ROSTER', JSON.stringify(roster));
  return { count: roster.entries.length, at: roster.at };
}

function getRoster_() {
  const raw = PropertiesService.getScriptProperties().getProperty('ROSTER');
  return raw ? JSON.parse(raw) : null;
}

/* =========================================================
   시트
   ========================================================= */
function getSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(SHEET_NAME);
  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
    sheet.setFrozenRows(1);
    // 스팀키·디스코드 ID처럼 긴 숫자가 지수 표기나 반올림으로 바뀌지 않게 글자 칸으로 둔다
    ['스팀프로필', '스팀키', '디스코드', '닉네임'].forEach(h => {
      sheet.getRange(1, COL[h] + 1, sheet.getMaxRows(), 1).setNumberFormat('@');
    });
  }
  return sheet;
}
