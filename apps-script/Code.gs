/**
 * 도타 2 인하우스 리그 서버 (Google Apps Script)
 *
 * 하는 일
 *  - 선수 등록 페이지에서 받은 정보를 이 구글 시트에 저장한다 (시트는 운영진 계정에만 보인다)
 *    시즌마다 '선수등록 (시즌 이름)' 탭을 따로 쓰고, 지난 시즌에 등록했던 선수는 스팀 프로필과 포지션 순서만으로 다시 등록할 수 있다
 *  - 운영진 키가 있는 사람에게만 등록 명단을 돌려주고, 승인 상태와 등록 기간을 바꾸고 새 시즌을 시작하게 한다
 *  - 리그 매니저가 올린 경기 기록을 받아, 개인 정보를 뺀 공개용 기록으로 내보낸다
 *  - 디스코드 봇이 올린 참가 명단을 보관했다가 리그 매니저에 넘겨준다
 *
 * 처음 설치는 README.md의 "1. 구글 시트 서버 만들기"를 따라 하세요.
 * 코드를 고친 뒤에는 배포 → 배포 관리 → 수정(연필) → 버전: 새 버전 → 배포 를 눌러야 반영됩니다.
 */

const SERVER_VERSION = 6;                                // 서버를 고칠 때마다 올린다. 상태 응답에 실려서 새 버전이 배포됐는지 밖에서 확인할 수 있다
const SHEET_NAME = '선수등록';                             // 등록 탭 이름의 앞부분. 시즌마다 '선수등록 (시즌 이름)' 탭을 따로 쓴다
const HEADERS = ['등록시각', '수정시각', '상태', '닉네임', '스팀프로필', '스팀키', '디스코드', 'MMR', '1지망', '2지망', '3지망', '4지망', '비고'];
const COL = HEADERS.reduce((o, h, i) => (o[h] = i, o), {});
const PREF_LABELS = ['캐리', '미드', '오프', '서폿'];          // 지망 번호 1~4
const STATUSES = ['대기', '승인', '제외'];
const MAX_MMR = 15000;
const MAX_ROWS = 3000;
const ROSTER_MAX = 60;
const STEAM_TRIES = 4;                                     // 스팀 조회를 몇 번까지 시도할지
const LEAGUE_MAX = 8000000;                                // 리그 기록의 최대 크기(글자 수)

/* =========================================================
   설치: 편집기에서 setup 을 한 번 실행하세요
   ========================================================= */
function setup() {
  const props = PropertiesService.getScriptProperties();
  let key = props.getProperty('ADMIN_KEY');
  if (!key) {
    key = (Utilities.getUuid() + Utilities.getUuid()).replace(/-/g, '');
    props.setProperty('ADMIN_KEY', key);
  }
  if (props.getProperty('REG_OPEN') === null) props.setProperty('REG_OPEN', 'true');
  if (props.getProperty('SEASON') === null) props.setProperty('SEASON', '시즌 1');   // 첫 시즌의 이름. 그 뒤로는 SEASONS 에 적는다
  const sheet = getSheet_();
  recordsFile_();                                   // 공개 기록 파일을 미리 만들어 권한을 받아 둔다
  const moved = migrateSteamKeys_();                // 스팀에 물어보는 권한도 여기서 함께 받는다
  if (moved.changed) Logger.log('스팀 사용자 지정 주소로 저장돼 있던 ' + moved.changed + '명을 고유 번호로 바꿨습니다.');
  if (moved.failed.length) Logger.log('스팀에서 찾지 못해 그대로 둔 선수: ' + moved.failed.join(', ') + ' (시트의 스팀프로필 칸을 직접 확인해 주세요)');
  if (moved.duplicates.length) Logger.log('같은 스팀 계정이 여러 줄에 있습니다: ' + moved.duplicates.join(', ') + ' (시트에서 한 줄만 남겨 주세요)');
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
      case 'rejoin': return rejoin_(body);
      case 'ping': requireAdmin_(body); return adminStatus_();
      case 'adminList': requireAdmin_(body); return { players: listRegistrations_() };
      case 'adminSetStatus': requireAdmin_(body); return setStatus_(body);
      case 'adminConfig': requireAdmin_(body); return setConfig_(body);
      case 'adminNewSeason': requireAdmin_(body); return newSeason_(body);
      case 'publishRecords': requireAdmin_(body); return publishRecords_(body);
      case 'pushRoster': requireAdmin_(body); return pushRoster_(body);
      case 'adminRoster': requireAdmin_(body); return { roster: getRoster_() };
      case 'adminLeague': requireAdmin_(body); return getLeague_();
      case 'adminLeagueRev': requireAdmin_(body); return { rev: leagueRev_() };
      case 'saveLeague': requireAdmin_(body); return saveLeague_(body);
      case 'pushLineup': requireAdmin_(body); return pushLineup_(body);
      case 'adminLineup': requireAdmin_(body); return { lineup: getLineup_() };
      default: fail_('알 수 없는 요청입니다');
    }
  });
}

function respond_(fn) {
  let out;
  try {
    ready_();
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
  const list = seasons_();
  return {
    open: props.getProperty('REG_OPEN') !== 'false',
    season: list[list.length - 1].name,
    registered: Math.max(0, getSheet_().getLastRow() - 1),
    returning: list.length > 1,                            // 지난 시즌이 있으면 등록 페이지가 간편 등록을 함께 보여 준다
    recordsAt: props.getProperty('RECORDS_AT') || '',
    version: SERVER_VERSION
  };
}

// 운영진 페이지에는 지난 시즌 이름도 함께 준다 (오래된 시즌이 앞)
function adminStatus_() {
  return Object.assign(statusInfo_(), { pastSeasons: seasons_().slice(0, -1).map(s => s.name) });
}

function setConfig_(body) {
  if (typeof body.open === 'boolean') PropertiesService.getScriptProperties().setProperty('REG_OPEN', String(body.open));
  if (typeof body.season === 'string') renameSeason_(body.season);
  return adminStatus_();
}

/* =========================================================
   시즌
   ========================================================= */
// 시즌마다 등록 탭을 따로 둔다. 스크립트 속성 SEASONS 에 [{name, id}] 로 적는다. 오래된 시즌이 앞이고 맨 뒤가 지금 시즌이다.
// id 는 탭의 고유 번호(gid)라, 시트에서 탭 이름을 바꾸거나 순서를 옮겨도 그 시즌의 탭을 찾는다.
function seasons_() {
  let list = null;
  try { list = JSON.parse(PropertiesService.getScriptProperties().getProperty('SEASONS') || 'null'); } catch (err) { /* 깨졌으면 다시 만든다 */ }
  return Array.isArray(list) && list.length ? list : initSeasons_();
}

function saveSeasons_(list) {
  PropertiesService.getScriptProperties().setProperty('SEASONS', JSON.stringify(list));
}

// 처음 한 번: 시즌별 탭이 없던 때(버전 5까지)의 '선수등록' 탭을 지금 시즌의 탭으로 삼고, 탭 이름에 시즌 이름을 붙인다.
// 새로 설치한 시트면 첫 시즌의 탭을 만든다.
function initSeasons_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const name = seasonName_(PropertiesService.getScriptProperties().getProperty('SEASON'));
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (sheet) nameTab_(ss, sheet, name);
  else sheet = ss.getSheetByName(tabName_(name)) || ss.insertSheet(tabName_(name), 0);
  prepareSheet_(sheet);
  const list = [{ name, id: sheet.getSheetId() }];
  saveSeasons_(list);
  return list;
}

// 요청을 처리하기 전에 시즌 목록이 있는지 본다. 없으면(버전 6으로 올린 뒤 첫 요청) 한 번에 하나씩만 만들게 잠근다.
function ready_() {
  if (!PropertiesService.getScriptProperties().getProperty('SEASONS')) withLock_(() => { seasons_(); });
}

function seasonName_(v) {
  return String(v == null ? '' : v).replace(/[\u0000-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim().slice(0, 30);
}

// 같은 시즌 이름인지: 공백과 대소문자는 무시한다
function seasonKey_(name) {
  return String(name).toLowerCase().replace(/\s+/g, '');
}

// 시즌의 탭 이름. 시트 탭 이름에 쓸 수 없는 글자( : \ / ? * [ ] )는 뺀다
function tabName_(season) {
  const s = String(season || '').replace(/[:\\\/?*\[\]]/g, ' ').replace(/\s+/g, ' ').trim();
  return s ? SHEET_NAME + ' (' + s + ')' : SHEET_NAME;
}

// 아직 쓰이지 않은 탭 이름. 같은 이름의 다른 탭이 있으면 뒤에 번호를 붙인다. own 은 이름을 바꾸려는 탭 자신이다
function freeTabName_(ss, season, own) {
  const want = tabName_(season);
  for (let n = 1; ; n++) {
    const name = n === 1 ? want : want + ' ' + n;
    const other = ss.getSheetByName(name);
    if (!other || (own && other.getSheetId() === own.getSheetId())) return name;
  }
}

// 탭 이름을 시즌 이름에 맞춘다. 이름은 보기 좋으라고 붙이는 것이라, 못 바꿔도 넘어간다
function nameTab_(ss, sheet, season) {
  try {
    const name = freeTabName_(ss, season, sheet);
    if (sheet.getName() !== name) sheet.setName(name);
  } catch (err) {
    console.warn('탭 이름을 바꾸지 못했습니다: ' + err);
  }
}

function sheetById_(ss, id) {
  return ss.getSheets().filter(s => s.getSheetId() === id)[0] || null;
}

// 지금 시즌의 이름만 고친다. 명단과 탭은 그대로이고 탭 이름만 따라 바뀐다
function renameSeason_(v) {
  const name = seasonName_(v);
  withLock_(() => {
    const list = seasons_();
    const cur = list[list.length - 1];
    if (cur.name === name) return;
    if (list.slice(0, -1).some(s => seasonKey_(s.name) === seasonKey_(name)))
      fail_('지난 시즌과 같은 이름은 쓸 수 없습니다. 다른 이름을 넣어 주세요.', 'season');
    cur.name = name;
    saveSeasons_(list);
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = sheetById_(ss, cur.id);
    if (sheet) nameTab_(ss, sheet, name);
  });
}

// 새 시즌을 시작한다: 새 탭을 만들어 등록을 처음부터 받는다. 지난 시즌의 명단은 그 시즌의 탭에 그대로 남는다
function newSeason_(body) {
  const name = seasonName_(body.season);
  if (!name) fail_('새 시즌의 이름을 넣어 주세요', 'season');
  return withLock_(() => {
    const list = seasons_();
    if (list.some(s => seasonKey_(s.name) === seasonKey_(name)))
      fail_('이미 있는 시즌 이름입니다. 다른 이름을 넣어 주세요.', 'season');
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.insertSheet(freeTabName_(ss, name), 0);     // 지금 시즌의 탭이 맨 앞에 오게 한다
    prepareSheet_(sheet);
    list.push({ name, id: sheet.getSheetId() });
    saveSeasons_(list);
    return adminStatus_();
  });
}

/* =========================================================
   선수 등록
   ========================================================= */
function register_(body) {
  // 사람 눈에 보이지 않는 칸이 채워져 있으면 자동 입력 프로그램으로 보고, 성공한 척만 한다
  if (body.website) return { updated: false };
  if (PropertiesService.getScriptProperties().getProperty('REG_OPEN') === 'false') fail_('지금은 선수 등록 기간이 아닙니다', 'closed');

  const nickname = cleanNickname_(body.nickname);
  const discord = normDiscord_(body.discord);
  const mmr = parseMmr_(body.mmr);
  const prefs = parsePrefs_(body.prefs);
  const steam = resolveSteam_(parseSteam_(body.steam));     // 스팀에 물어봐야 해서 다른 칸을 모두 확인한 뒤에 한다

  // 같은 스팀 프로필로 너무 자주 보내는 것을 막는다
  const cache = CacheService.getScriptCache();
  const rlKey = 'rl:' + steam.key;
  if (cache.get(rlKey)) fail_('방금 제출했습니다. 30초 뒤에 다시 시도해 주세요.', 'rate');

  const result = withLock_(() => {
    const sheet = getSheet_();
    const rows = readRows_(sheet);
    if (rows.length >= MAX_ROWS) fail_('등록 인원이 가득 찼습니다. 운영진에게 문의해 주세요.');

    // 예전에 사용자 지정 주소로 저장된 줄(id:이름)도 같은 사람으로 알아본다
    const mine = rows.find(r => r.steamKey === steam.key) || (steam.legacyKey ? rows.find(r => r.steamKey === steam.legacyKey) : undefined);
    const nickKey = nickname.toLowerCase().replace(/\s+/g, '');
    const nickOwner = rows.find(r => r.nickname.toLowerCase().replace(/\s+/g, '') === nickKey);
    const discordOwner = rows.find(r => r.discord === discord);

    if (mine && mine.discord !== discord)
      fail_('이 스팀 프로필은 다른 디스코드 계정으로 이미 등록돼 있습니다. 디스코드 계정이 바뀌었다면 운영진에게 알려 주세요.', 'conflict');
    if (!mine && discordOwner)
      fail_('이 디스코드 계정은 다른 스팀 프로필로 이미 등록돼 있습니다. 스팀 프로필이 바뀌었다면 운영진에게 알려 주세요.', 'conflict');
    // 운영진이 승인하거나 제외한 등록은 본인이 고칠 수 없다. 운영진이 상태를 대기로 돌리면 다시 고칠 수 있다.
    if (mine && mine.status !== '대기')
      fail_('운영진이 확인을 마친 등록이라 직접 고칠 수 없습니다. 바꿀 내용이 있으면 운영진에게 알려 주세요.', 'locked');
    if (nickOwner && nickOwner !== mine)
      fail_('다른 선수가 이미 쓰고 있는 닉네임입니다. 다른 닉네임을 넣어 주세요.', 'nickname');

    const now = new Date();
    const prefCells = prefs.map(n => PREF_LABELS[n - 1]);
    if (mine) {
      const line = mine.raw.slice();
      line[COL['수정시각']] = now;
      line[COL['상태']] = mine.status;
      line[COL['닉네임']] = text_(nickname);
      line[COL['스팀프로필']] = text_(steam.url);
      line[COL['스팀키']] = text_(steam.key);
      line[COL['디스코드']] = text_(mine.discord);
      line[COL['MMR']] = mmr;
      prefCells.forEach((v, i) => { line[COL['1지망'] + i] = v; });
      line[COL['비고']] = '';                              // 본인이 모두 새로 적어 냈으니 '지난 시즌에서 가져옴' 표시는 지운다
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

// 지난 시즌에 등록했던 선수의 간편 등록. 스팀 프로필과 포지션 순서만 받고,
// 닉네임·디스코드·MMR은 그 선수가 가장 최근에 등록한 시즌의 줄에서 가져와 지금 시즌에 새 줄(대기)로 넣는다.
function rejoin_(body) {
  if (body.website) return { nickname: '', from: '' };     // 자동 입력 프로그램에는 성공한 척만 한다
  if (PropertiesService.getScriptProperties().getProperty('REG_OPEN') === 'false') fail_('지금은 선수 등록 기간이 아닙니다', 'closed');

  const prefs = parsePrefs_(body.prefs);
  const p = parseSteam_(body.steam);
  // 숫자 주소는 시트에서 바로 찾을 수 있어 스팀에 묻지 않는다. 사용자 지정 주소만 스팀에서 고유 번호를 알아 온다
  const steam = p.id ? { key: 's:' + p.id, url: 'https://steamcommunity.com/profiles/' + p.id, legacyKey: '' } : resolveSteam_(p);

  const cache = CacheService.getScriptCache();
  const rlKey = 'rl:' + steam.key;
  if (cache.get(rlKey)) fail_('방금 제출했습니다. 30초 뒤에 다시 시도해 주세요.', 'rate');

  const result = withLock_(() => {
    const list = seasons_();
    const sheet = getSheet_();
    const rows = readRows_(sheet);
    if (rows.length >= MAX_ROWS) fail_('등록 인원이 가득 찼습니다. 운영진에게 문의해 주세요.');
    const same = r => r.steamKey === steam.key || (!!steam.legacyKey && r.steamKey === steam.legacyKey);

    const mine = rows.find(same);
    if (mine) fail_(mine.status === '대기'
      ? '이번 시즌에 이미 등록돼 있습니다. 운영진의 확인을 기다려 주세요. 고칠 내용이 있으면 "처음 등록해요"에서 같은 스팀 프로필과 디스코드로 다시 제출하면 됩니다.'
      : '이번 시즌에 이미 등록돼 있습니다. 바꿀 내용이 있으면 운영진에게 알려 주세요.', 'already');

    // 가장 최근 시즌부터 거슬러 올라가며 이 선수의 줄을 찾는다
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let old = null, from = '';
    for (let i = list.length - 2; i >= 0 && !old; i--) {
      const past = sheetById_(ss, list[i].id);
      if (!past) continue;                                 // 탭이 지워진 시즌은 건너뛴다
      old = readRows_(past).filter(same)[0] || null;
      from = list[i].name;
    }
    if (!old || !old.nickname || !old.discord)
      fail_('지난 시즌에 이 스팀 프로필로 등록한 기록을 찾지 못했습니다. "처음 등록해요"로 등록해 주세요.', 'notfound');

    const nickKey = old.nickname.toLowerCase().replace(/\s+/g, '');
    if (rows.some(r => r.nickname.toLowerCase().replace(/\s+/g, '') === nickKey))
      fail_('지난 시즌에 쓰던 닉네임을 이번 시즌에 다른 선수가 쓰고 있습니다. "처음 등록해요"에서 다른 닉네임으로 등록해 주세요.', 'conflict');
    if (rows.some(r => r.discord === old.discord))
      fail_('지난 시즌에 등록한 디스코드 계정이 이번 시즌에 다른 스팀 프로필로 등록돼 있습니다. 운영진에게 알려 주세요.', 'conflict');

    const now = new Date();
    const line = new Array(HEADERS.length).fill('');
    line[COL['등록시각']] = now;
    line[COL['수정시각']] = now;
    line[COL['상태']] = '대기';
    line[COL['닉네임']] = text_(old.nickname);
    line[COL['스팀프로필']] = text_(steam.url);
    line[COL['스팀키']] = text_(steam.key);
    line[COL['디스코드']] = text_(old.discord);
    line[COL['MMR']] = old.mmr;
    prefs.forEach((n, i) => { line[COL['1지망'] + i] = PREF_LABELS[n - 1]; });
    // 운영진이 알아보게 적어 둔다. 지난 시즌에 승인되지 않았던 선수면 그때 상태도 함께 적는다
    line[COL['비고']] = text_('재참가' + (from ? ' · ' + from : '') + (old.status === '승인' ? '' : ' (그때 ' + old.status + ')'));
    sheet.appendRow(line);
    return { nickname: old.nickname, from };
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

// 스팀 프로필 주소의 모양을 읽는다.
// steamcommunity.com/profiles/7656… 는 고유 번호, steamcommunity.com/id/이름 은 사용자 지정 주소다.
function parseSteam_(v) {
  const s = String(v == null ? '' : v).trim();
  let m = s.match(/^(?:https?:\/\/)?(?:www\.)?steamcommunity\.com\/profiles\/(7656\d{13})\/?(?:[?#].*)?$/i) || s.match(/^(7656\d{13})$/);
  if (m) return { id: m[1], vanity: '' };
  m = s.match(/^(?:https?:\/\/)?(?:www\.)?steamcommunity\.com\/id\/([A-Za-z0-9_-]{2,64})\/?(?:[?#].*)?$/i);
  if (m) return { id: '', vanity: m[1] };
  fail_('스팀 프로필 주소를 확인해 주세요. 예) https://steamcommunity.com/profiles/76561197990650432', 'steam');
}

// 같은 사람을 가리키는 키는 언제나 스팀 고유 번호로 만든다.
// 사용자 지정 주소는 본인이 스팀에서 바꿀 수 있어서, 그대로 키로 쓰면 링크가 끊기거나 같은 계정이 두 번 등록될 수 있다.
function resolveSteam_(p) {
  const found = lookupSteamId_(p.id ? 'profiles/' + p.id : 'id/' + p.vanity);
  if (found === '') fail_('스팀에서 이 프로필을 찾지 못했습니다. 주소를 다시 확인해 주세요.', 'steam');
  if (found === null && !p.id)
    fail_('스팀에서 프로필을 확인하지 못했습니다. 잠시 후 다시 시도하거나 steamcommunity.com/profiles/숫자 모양의 주소를 넣어 주세요.', 'steam');
  const id = found || p.id;                              // 스팀이 답하지 않아도 숫자 주소는 그대로 받는다
  return {
    key: 's:' + id,
    url: 'https://steamcommunity.com/profiles/' + id,
    legacyKey: p.vanity ? 'id:' + p.vanity.toLowerCase() : ''
  };
}

// 스팀 공개 프로필에서 고유 번호(steamID64)를 읽는다. 돌려주는 값: 고유 번호, 그런 프로필이 없으면 '', 스팀이 답하지 않으면 null
function lookupSteamId_(path) {
  const cache = CacheService.getScriptCache();
  const cacheKey = 'steam:' + path.toLowerCase();
  const hit = cache.get(cacheKey);
  if (hit) return hit === 'none' ? '' : hit;
  // 스팀은 구글 서버에서 오는 요청을 가끔 거절한다(실제 배포에서 열 번에 세 번꼴). 그래서 몇 번 다시 물어본다.
  for (let attempt = 1; attempt <= STEAM_TRIES; attempt++) {
    if (attempt > 1) Utilities.sleep(300);
    let text = '';
    try {
      const res = UrlFetchApp.fetch('https://steamcommunity.com/' + path + '/?xml=1', { muteHttpExceptions: true });
      if (res.getResponseCode() !== 200) { console.warn('스팀 조회 실패(' + attempt + '번째): HTTP ' + res.getResponseCode()); continue; }
      text = res.getContentText();
    } catch (err) {
      console.warn('스팀 조회 실패(' + attempt + '번째): ' + err);
      continue;
    }
    const m = text.match(/<steamID64>(7656\d{13})<\/steamID64>/);
    if (!m && !/<error>/.test(text)) continue;           // 점검 화면처럼 알 수 없는 답
    try { cache.put(cacheKey, m ? m[1] : 'none', m ? 600 : 120); } catch (err) { /* 캐시는 없어도 된다 */ }
    return m ? m[1] : '';
  }
  return null;
}

// 예전에는 사용자 지정 주소(steamcommunity.com/id/이름)를 그대로 키로 저장했다. 그런 줄을 스팀 고유 번호로 바꾼다. setup 이 부른다.
function migrateSteamKeys_() {
  const out = { changed: 0, failed: [], duplicates: [] };
  withLock_(() => {
    const sheet = getSheet_();
    readRows_(sheet).forEach(r => {
      if (r.steamKey.indexOf('id:') !== 0) return;
      const id = lookupSteamId_('id/' + r.steamKey.slice(3));
      if (!id) { out.failed.push(r.nickname); return; }
      sheet.getRange(r.rowNumber, COL['스팀프로필'] + 1, 1, 2)
        .setValues([[text_('https://steamcommunity.com/profiles/' + id), text_('s:' + id)]]);
      out.changed++;
    });
    const seen = {};
    readRows_(sheet).forEach(r => {
      if (!r.steamKey) return;
      if (seen[r.steamKey]) out.duplicates.push(seen[r.steamKey] + ' / ' + r.nickname);
      else seen[r.steamKey] = r.nickname;
    });
  });
  return out;
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
      prefs: [0, 1, 2, 3].map(i2 => prefCode_(d[COL['1지망'] + i2])),
      note: d[COL['비고']].trim()
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
    prefs: r.prefs,
    note: r.note
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

// 예전 방식: 매니저가 공개할 칸만 골라 올린다. 서버가 리그 기록의 원본을 갖게 된 뒤로는 받지 않는다.
// 새로 고치지 않은 예전 매니저가 뒤처진 기록으로 순위 페이지를 덮어쓰는 것을 막기 위해서다.
function publishRecords_(body) {
  if (leagueRev_() > 0) fail_('리그 매니저가 예전 버전입니다. 매니저를 새로 고침해 주세요.', 'outdated');
  const clean = sanitizeRecords_(body.records);
  return withLock_(() => writePublic_(clean));
}

// 공개 기록을 드라이브 파일과 캐시에 쓴다 (잠금을 잡은 상태에서 부른다)
function writePublic_(clean) {
  const at = new Date().toISOString();
  clean.publishedAt = at;
  const text = JSON.stringify(clean);
  recordsFile_().setContent(text);
  PropertiesService.getScriptProperties().setProperty('RECORDS_AT', at);
  putCache_('records', text);
  return { publishedAt: at, players: clean.players.length, matches: clean.matches.length };
}

/* =========================================================
   리그 기록 (원본)
   ========================================================= */
// 선수의 인하우스 MMR·전적, 경기 기록, 설정 전체. 리그 매니저와 디스코드 봇이 함께 읽고 쓴다.
// 공개 기록과 달리 거르지 않고 드라이브의 비공개 파일에 그대로 두며, 운영진 키가 있어야만 돌려준다.
// 쓸 때마다 번호(rev)를 하나 올린다. 올리는 쪽은 자기가 보고 고친 번호(baseRev)를 함께 보내고, 그사이 번호가 바뀌었으면 받지 않는다.
// 매니저와 봇이 서로의 변경을 모르고 덮어쓰는 일을 막기 위해서다.
function leagueRev_() {
  return Number(PropertiesService.getScriptProperties().getProperty('LEAGUE_REV')) || 0;
}

function leagueText_(league) {
  if (!league || typeof league !== 'object' || !Array.isArray(league.players) || !Array.isArray(league.matches)) fail_('리그 기록 형식이 잘못됐습니다');
  const text = JSON.stringify({ players: league.players, matches: league.matches, settings: league.settings || {} });
  if (text.length > LEAGUE_MAX) fail_('리그 기록이 너무 큽니다');
  return text;
}

function getLeague_() {
  const props = PropertiesService.getScriptProperties();
  const rev = leagueRev_();
  const id = props.getProperty('LEAGUE_FILE_ID');
  let text = '';
  if (rev && id) {
    try { text = DriveApp.getFileById(id).getBlob().getDataAsString('UTF-8') || ''; } catch (err) { /* 파일이 지워졌으면 없는 것으로 본다 */ }
  }
  return { league: text ? JSON.parse(text) : null, rev, leagueAt: text ? (props.getProperty('LEAGUE_AT') || '') : '' };
}

// 리그 기록을 받아 원본으로 둔다. 받은 기록으로 공개 기록(순위 페이지)과 시트의 순위·경기 기록 탭도 다시 쓴다.
function saveLeague_(body) {
  const text = leagueText_(body.league);
  const league = JSON.parse(text);
  const clean = sanitizeRecords_(league);
  const base = Number(body.baseRev) || 0;
  return withLock_(() => {
    const props = PropertiesService.getScriptProperties();
    const rev = leagueRev_();
    if (base !== rev && body.force !== true)
      fail_('서버에 더 새로운 기록이 있습니다. 서버 기록을 먼저 불러와 주세요.', 'conflict');
    const out = writePublic_(clean);
    driveFile_('LEAGUE_FILE_ID', '인하우스_리그기록.json').setContent(text);
    props.setProperty('LEAGUE_AT', out.publishedAt);
    props.setProperty('LEAGUE_REV', String(rev + 1));
    writeMirror_(league);
    return Object.assign(out, { rev: rev + 1 });
  });
}

/* ---- 시트의 순위·경기 기록 탭 ----
   운영진이 시트에서 바로 볼 수 있게, 리그 기록이 바뀔 때마다 두 탭을 통째로 다시 쓴다. 원본은 위의 리그 기록이고 이 탭은 보기용이다.
   MMR과 전적은 경기마다 이어서 계산한 값이라, 시트에서 숫자를 고치거나 줄을 지워도 다시 계산되지 않는다. 그래서 여기서는 읽기만 한다. */
const MIRROR_NOTE = '이 탭은 봇이나 리그 매니저가 기록을 바꿀 때마다 자동으로 다시 씁니다. 여기서 고친 내용은 지워지니, 고칠 때는 리그 매니저를 쓰세요.';
const ROLE_LABELS = ['캐리', '미드', '오프', '서폿', '서폿'];

function writeMirror_(league) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    mirrorTab_(ss, '순위', rankRows_(league));
    mirrorTab_(ss, '경기 기록', matchRows_(league));
  } catch (err) {                                          // 보기용 탭을 못 써도 기록 저장은 끝낸다
    console.warn('시트의 순위·경기 기록 탭을 쓰지 못했습니다: ' + err);
  }
}

// rows 의 첫 줄은 머리글이다. 맨 위에 안내 한 줄을 두고 그 아래에 쓴다.
function mirrorTab_(ss, name, rows) {
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    try { sheet.protect().setWarningOnly(true); } catch (err) { /* 고치려 할 때 경고만 띄운다. 못 걸어도 괜찮다 */ }
  }
  const width = rows[0].length;
  const table = [[MIRROR_NOTE].concat(new Array(width - 1).fill(''))].concat(rows);
  sheet.clearContents();
  if (sheet.getMaxRows() < table.length) sheet.insertRowsAfter(sheet.getMaxRows(), table.length - sheet.getMaxRows());
  if (sheet.getMaxColumns() < width) sheet.insertColumnsAfter(sheet.getMaxColumns(), width - sheet.getMaxColumns());
  sheet.getRange(1, 1, table.length, width).setValues(table);
  sheet.getRange(2, 1, 1, width).setFontWeight('bold');
  sheet.setFrozenRows(2);
}

// 순위 페이지와 같은 순서: 승이 많은 순, 같으면 패가 적은 순, 승패가 같으면 공동 순위. 경기를 치르지 않은 선수는 순위 없이 아래에 둔다.
function rankRows_(league) {
  const n = v => Number(v) || 0;
  const played = p => n(p.wins) + n(p.losses) > 0;
  const list = league.players.slice().sort((a, b) => (played(b) - played(a)) || (n(b.wins) - n(a.wins)) || (n(a.losses) - n(b.losses)) ||
    (n(b.mmr) - n(a.mmr)) || String(a.name).localeCompare(String(b.name), 'ko'));
  const rows = [['순위', '닉네임', '인하우스 MMR', '시작 MMR', '변동', '승', '패', '승률', '연속', '1지망', '2지망', '3지망', '4지망',
    '캐리 판수', '미드 판수', '오프 판수', '4번 서폿 판수', '5번 서폿 판수', '디스코드']];
  let rank = 0, prev = '';
  list.forEach((p, i) => {
    const w = n(p.wins), l = n(p.losses), key = w + ':' + l;
    if (played(p) && key !== prev) { rank = i + 1; prev = key; }
    const base = p.baseMMR == null ? n(p.mmr) : n(p.baseMMR), streak = n(p.streak);
    const prefs = Array.isArray(p.prefs) ? p.prefs : [], roles = Array.isArray(p.roleCount) ? p.roleCount : [];
    rows.push([played(p) ? rank : '-', text_(p.name), n(p.mmr), base, n(p.mmr) - base, w, l,
      played(p) ? Math.round(w / (w + l) * 100) + '%' : '-',
      streak > 0 ? streak + '연승' : streak < 0 ? (-streak) + '연패' : '-']
      .concat([0, 1, 2, 3].map(k => PREF_LABELS[prefs[k] - 1] || '-'))
      .concat([0, 1, 2, 3, 4].map(k => n(roles[k])))
      .concat([text_(p.discord || '')]));
  });
  return rows;
}

// 한 경기에 열 줄(래디언트 1~5번, 다이어 1~5번). 최근 경기가 위에 온다.
function matchRows_(league) {
  const n = v => Number(v) || 0;
  const rows = [['경기 시각', '경기', '이긴 팀', '진영', '자리', '닉네임', '결과', '이전 MMR', '변동', '이후 MMR']];
  const total = league.matches.length;
  league.matches.forEach((m, i) => {
    if (!m || !Array.isArray(m.rows)) return;
    const when = text_(Utilities.formatDate(new Date(m.at), 'Asia/Seoul', 'yyyy-MM-dd HH:mm'));
    m.rows.slice().sort((a, b) => (a.side === b.side ? n(a.role) - n(b.role) : a.side === 'r' ? -1 : 1)).forEach(r => {
      rows.push([when, total - i, m.winner === 'r' ? '래디언트' : '다이어', r.side === 'r' ? '래디언트' : '다이어',
        n(r.role) + '번 ' + (ROLE_LABELS[n(r.role) - 1] || ''), text_(r.name), r.side === m.winner ? '승' : '패',
        n(r.before), n(r.delta), n(r.before) + n(r.delta)]);
    });
  });
  return rows;
}

/* =========================================================
   봇이 짠 팀
   ========================================================= */

// 봇이 짠 팀. 매니저가 불러와 그대로 보드에 올리고 결과를 기록한다. lineup 이 null 이면 비운다.
function pushLineup_(body) {
  const props = PropertiesService.getScriptProperties();
  const l = body.lineup;
  if (l === null) { props.setProperty('LINEUP', ''); return { cleared: true }; }
  const id = v => String(v == null ? '' : v).slice(0, 40);
  const lanes = l && Array.isArray(l.lanes) ? l.lanes.map(x => ({ role: Number(x && x.role), r: id(x && x.r), d: id(x && x.d) })) : [];
  const ids = lanes.reduce((a, x) => a.concat(x.r, x.d), []);
  if (lanes.length !== 5 || lanes.some((x, i) => x.role !== i + 1) || ids.some(x => !x) || new Set(ids).size !== 10)
    fail_('팀 편성 형식이 잘못됐습니다');
  const lineup = {
    at: new Date().toISOString(),
    post: String(l.post || '').slice(0, 200),
    lanes,
    bench: (Array.isArray(l.bench) ? l.bench : []).slice(0, ROSTER_MAX).map(id).filter(Boolean)
  };
  props.setProperty('LINEUP', JSON.stringify(lineup));
  return { at: lineup.at };
}

function getLineup_() {
  const raw = PropertiesService.getScriptProperties().getProperty('LINEUP');
  return raw ? JSON.parse(raw) : null;
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
  return driveFile_('RECORDS_FILE_ID', '인하우스_공개기록.json');
}

// 스크립트 속성에 적어 둔 드라이브 파일. 없거나 지워졌으면 빈 기록으로 새로 만든다.
function driveFile_(prop, name) {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty(prop);
  if (id) {
    try { return DriveApp.getFileById(id); } catch (err) { /* 지워졌으면 새로 만든다 */ }
  }
  const file = DriveApp.createFile(name, JSON.stringify({ players: [], matches: [] }), 'application/json');
  props.setProperty(prop, file.getId());
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
// 지금 시즌의 등록 탭
function getSheet_() {
  const list = seasons_();
  const cur = list[list.length - 1];
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = sheetById_(ss, cur.id);
  if (!sheet) {                                            // 탭이 지워졌으면 빈 탭을 새로 만든다
    sheet = ss.insertSheet(freeTabName_(ss, cur.name), 0);
    cur.id = sheet.getSheetId();
    saveSeasons_(list);
  }
  if (sheet.getLastRow() === 0) prepareSheet_(sheet);       // 머리글까지 지워졌으면 다시 쓴다
  return sheet;
}

// 등록 탭의 머리글과 칸 모양을 갖춘다
function prepareSheet_(sheet) {
  if (sheet.getMaxColumns() < HEADERS.length) sheet.insertColumnsAfter(sheet.getMaxColumns(), HEADERS.length - sheet.getMaxColumns());
  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
    sheet.setFrozenRows(1);
    // 스팀키·디스코드 ID처럼 긴 숫자가 지수 표기나 반올림으로 바뀌지 않게 글자 칸으로 둔다
    ['스팀프로필', '스팀키', '디스코드', '닉네임', '비고'].forEach(h => {
      sheet.getRange(1, COL[h] + 1, sheet.getMaxRows(), 1).setNumberFormat('@');
    });
  } else if (sheet.getRange(1, HEADERS.length).getDisplayValue() === '') {
    // 버전 5까지 만든 탭에는 비고 칸의 머리글이 없다
    sheet.getRange(1, HEADERS.length).setValue(HEADERS[HEADERS.length - 1]).setFontWeight('bold');
  }
}
