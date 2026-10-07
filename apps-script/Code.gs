/**
 * 도타 2 인하우스 리그 서버 (Google Apps Script)
 *
 * 하는 일
 *  - 선수 등록 페이지에서 받은 정보를 이 구글 시트에 저장한다 (시트는 운영진 계정에만 보인다)
 *    시즌마다 '선수등록 (시즌 이름)' 탭을 따로 쓴다. 지난 시즌에 승인됐던 선수가 같은 스팀 프로필과 디스코드로 다시 등록하면
 *    그 시즌이 끝났을 때의 인하우스 MMR을 이어받는다
 *  - 운영진 키가 있는 사람에게만 등록 명단을 돌려주고, 승인 상태와 등록 기간을 바꾸고 새 시즌을 시작하게 한다
 *    (새 시즌을 시작하면 끝난 시즌의 리그 기록을 따로 보관하고, 새 시즌은 빈 기록에서 시작한다)
 *  - 리그 매니저가 올린 경기 기록을 받아, 개인 정보를 뺀 공개용 기록으로 내보낸다
 *  - 디스코드 봇이 올린 참가 명단을 보관했다가 리그 매니저에 넘겨준다
 *
 * 처음 설치는 README.md의 "1. 구글 시트 서버 만들기"를 따라 하세요.
 * 코드를 고친 뒤에는 배포 → 배포 관리 → 수정(연필) → 버전: 새 버전 → 배포 를 눌러야 반영됩니다.
 */

const SERVER_VERSION = 9;                              // 서버를 고칠 때마다 올린다. 상태 응답에 실려서 새 버전이 배포됐는지 밖에서 확인할 수 있다
const SHEET_NAME = '선수등록';                             // 등록 탭 이름의 앞부분. 시즌마다 '선수등록 (시즌 이름)' 탭을 따로 쓴다
// 칸을 더할 때는 맨 뒤에 붙이고 LAYOUT 을 올린다. 이미 있는 탭에는 ready_ 가 새 머리글을 채워 넣는다
const HEADERS = ['등록시각', '수정시각', '상태', '닉네임', '스팀프로필', '스팀키', '디스코드', 'MMR', '1지망', '2지망', '3지망', '4지망', '비고', '최고MMR'];
const LAYOUT = '2';
const COL = HEADERS.reduce((o, h, i) => (o[h] = i, o), {});
const PREF_LABELS = ['캐리', '미드', '오프', '서폿'];          // 지망 번호 1~4
const STATUSES = ['대기', '승인', '제외'];
const MAX_MMR = 15000;
const MAX_ROWS = 3000;
const ROSTER_MAX = 60;
const STEAM_TRIES = 4;                                     // 스팀 조회를 몇 번까지 시도할지
const LEAGUE_MAX = 8000000;                                // 리그 기록의 최대 크기(글자 수)
const SEASON_WORD = '시즌 변경';                            // 새 시즌을 시작할 때 운영진이 직접 입력해야 하는 확인 문구

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
    const raw = (e && e.postData && e.postData.contents) || '';
    if (raw.length > LEAGUE_MAX + 1000000) fail_('요청이 너무 큽니다');   // 가장 큰 요청(리그 기록 올리기)보다 큰 것은 읽지도 않는다
    try { body = JSON.parse(raw); }
    catch (err) { fail_('요청 형식이 잘못됐습니다'); }
    if (!body || typeof body !== 'object') fail_('요청 형식이 잘못됐습니다');

    switch (body.action) {
      case 'register': return register_(body);
      case 'ping': requireAdmin_(body); return adminStatus_();
      case 'adminList': requireAdmin_(body); return listSeason_(body);
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
// 누구나 볼 수 있는 상태. 등록한 인원 수는 여기에 싣지 않는다(운영자가 공개하지 않기로 했다)
function statusInfo_() {
  const props = PropertiesService.getScriptProperties();
  const list = seasons_();
  return {
    open: props.getProperty('REG_OPEN') !== 'false',
    season: list[list.length - 1].name,
    recordsAt: props.getProperty('RECORDS_AT') || '',
    version: SERVER_VERSION
  };
}

// 운영진에게는 등록 인원 수와 지난 시즌 이름도 함께 준다 (오래된 시즌이 앞)
function adminStatus_() {
  return Object.assign(statusInfo_(), {
    registered: Math.max(0, getSheet_().getLastRow() - 1),
    pastSeasons: seasons_().slice(0, -1).map(s => s.name)
  });
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
// 끝난 시즌에는 league(그 시즌의 리그 기록을 보관한 드라이브 파일)와 endedAt 이 붙는다.
// 지금 시즌의 leaguePending 은 새 시즌을 시작하면서 리그 기록을 아직 비우지 못했다는 표시다(finishSeason_).
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

// 요청을 처리하기 전에 시트가 지금 버전의 모양인지 본다. 서버를 새 버전으로 올린 뒤 첫 요청에서만 일이 있고,
// 그때는 한 번에 하나씩만 하게 잠근다: 시즌 목록이 없으면 만들고, 칸이 늘었으면 모든 시즌 탭에 새 머리글을 채운다.
function ready_() {
  const props = PropertiesService.getScriptProperties();
  const raw = props.getProperty('SEASONS') || '';
  const pending = raw.indexOf('"leaguePending":true') >= 0;      // 새 시즌을 시작하다 리그 기록을 비우지 못한 채 남은 경우
  if (raw && !pending && props.getProperty('LAYOUT') === LAYOUT) return;
  withLock_(() => {
    const list = seasons_();
    if (props.getProperty('LAYOUT') !== LAYOUT) {
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      list.forEach(s => { const sheet = sheetById_(ss, s.id); if (sheet) prepareSheet_(sheet); });
      props.setProperty('LAYOUT', LAYOUT);
    }
    try { finishSeason_(list); }
    catch (err) { console.error('리그 기록을 새로 시작하지 못했습니다. 다음 요청에서 다시 합니다: ' + (err && err.stack || err)); }
  });
}

function seasonName_(v) {
  return String(v == null ? '' : v).replace(/[\u0000-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim().slice(0, 30);
}

// 같은 시즌 이름인지: 공백과 대소문자는 무시한다
function seasonKey_(name) {
  return String(name).toLowerCase().replace(/\s+/g, '');
}

// 시즌의 탭 이름. 시트 탭 이름에 쓸 수 없는 글자( : \ / ? * [ ] )는 뺀다. base 는 탭의 종류(선수등록, 순위, 경기 기록)
function tabName_(season, base) {
  const s = String(season || '').replace(/[:\\\/?*\[\]]/g, ' ').replace(/\s+/g, ' ').trim();
  return s ? (base || SHEET_NAME) + ' (' + s + ')' : (base || SHEET_NAME);
}

// 아직 쓰이지 않은 탭 이름. 같은 이름의 다른 탭이 있으면 뒤에 번호를 붙인다. own 은 이름을 바꾸려는 탭 자신이다
function freeTabName_(ss, season, own, base) {
  const want = tabName_(season, base);
  for (let n = 1; ; n++) {
    const name = n === 1 ? want : want + ' ' + n;
    const other = ss.getSheetByName(name);
    if (!other || (own && other.getSheetId() === own.getSheetId())) return name;
  }
}

// 탭 이름을 시즌 이름에 맞춘다. 이름은 보기 좋으라고 붙이는 것이라, 못 바꿔도 넘어간다
function nameTab_(ss, sheet, season, base) {
  try {
    const name = freeTabName_(ss, season, sheet, base);
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

// 새 시즌을 시작한다.
//  - 등록: 새 탭을 만들어 빈 명단에서 다시 받는다. 지난 시즌의 명단은 그 시즌의 탭에 그대로 남는다.
//  - 리그 기록: 끝나는 시즌의 기록(선수의 인하우스 MMR·전적, 경기)을 드라이브 파일로 따로 보관하고, 새 시즌은 선수와 경기가 없는 기록으로 시작한다(설정은 그대로).
//    지난 시즌에 승인됐던 선수가 다시 등록하면, 보관해 둔 기록에서 시즌이 끝났을 때의 인하우스 MMR을 찾아 이어받는다(register_).
function newSeason_(body) {
  const name = seasonName_(body.season);
  if (!name) fail_('새 시즌의 이름을 넣어 주세요', 'season');
  // 되돌릴 수 없는 일이라, 운영진 페이지에서 바뀌는 것들을 보고 확인 문구를 직접 입력한 요청만 받는다
  if (body.confirm !== SEASON_WORD)
    fail_('새 시즌을 시작하려면 확인 문구("' + SEASON_WORD + '")를 입력해야 합니다. 운영진 페이지를 새로 고친 뒤 다시 해 주세요.', 'confirm');
  return withLock_(() => {
    const props = PropertiesService.getScriptProperties();
    const list = seasons_();
    if (list.some(s => seasonKey_(s.name) === seasonKey_(name)))
      fail_('이미 있는 시즌 이름입니다. 다른 이름을 넣어 주세요.', 'season');
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const cur = list[list.length - 1];

    // 보관이 먼저다. 여기서 실패하면 아무것도 바뀌지 않는다
    const ended = getLeague_().league;
    if (ended) {
      const label = String(cur.name || '이름 없는 시즌').replace(/[\\\/:*?"<>|]/g, ' ').replace(/\s+/g, ' ').trim();
      cur.league = DriveApp.createFile('인하우스_리그기록_' + label + '.json', JSON.stringify(ended), 'application/json').getId();
    }
    cur.endedAt = new Date().toISOString();
    delete cur.leaguePending;                                    // 끝나는 시즌에 남아 있던 표시는 더 볼 일이 없다 (남겨 두면 ready_ 가 요청마다 잠금을 잡는다)

    const sheet = ss.insertSheet(freeTabName_(ss, name), 0);     // 지금 시즌의 탭이 맨 앞에 오게 한다
    prepareSheet_(sheet);
    list.push(ended ? { name, id: sheet.getSheetId(), leaguePending: true } : { name, id: sheet.getSheetId() });
    saveSeasons_(list);
    props.setProperty('ROSTER', '');                             // 지난 시즌의 참가 명단과 짠 팀은 새 시즌의 선수와 맞지 않는다
    props.setProperty('LINEUP', '');

    // 시즌은 이미 바뀌었다. 리그 기록을 비우다 실패해도 여기서 멈추지 않고, 다음 요청 때 ready_ 가 이어서 한다
    try { finishSeason_(list); }
    catch (err) { console.error('리그 기록을 새로 시작하지 못했습니다. 다음 요청에서 다시 합니다: ' + (err && err.stack || err)); }
    return adminStatus_();
  });
}

// 새 시즌의 리그 기록을 아직 비우지 못했으면(leaguePending) 비운다. 잠금을 잡은 상태에서 부른다
function finishSeason_(list) {
  const cur = list[list.length - 1];
  if (!cur.leaguePending) return;
  const live = getLeague_().league;                              // 아직 지난 시즌의 기록이다. 설정만 이어받는다
  startLeague_(live && live.settings, list.length > 1 ? list[list.length - 2].name : '');
  delete cur.leaguePending;
  saveSeasons_(list);
}

// 리그 기록을 선수와 경기가 없는 상태로 새로 시작한다. 번호를 올려서 매니저가 새 기록을 받아 가게 한다.
function startLeague_(settings, endedSeason) {
  const props = PropertiesService.getScriptProperties();
  const league = { players: [], matches: [], settings: settings || {} };
  const out = writePublic_(sanitizeRecords_(league));
  driveFile_('LEAGUE_FILE_ID', '인하우스_리그기록.json').setContent(JSON.stringify(league));
  props.setProperty('LEAGUE_AT', out.publishedAt);
  props.setProperty('LEAGUE_REV', String(leagueRev_() + 1));
  keepMirror_(endedSeason);                                      // 여기부터는 보기용 탭이라 실패해도 넘어간다
  writeMirror_(league);
}

// 보관해 둔 지난 시즌의 리그 기록. 없거나 읽지 못하면 null
function archivedLeague_(season) {
  if (!season.league) return null;
  try {
    const league = JSON.parse(alive_(DriveApp.getFileById(season.league)).getBlob().getDataAsString('UTF-8'));
    return league && Array.isArray(league.players) ? league : null;
  } catch (err) {
    console.warn('보관해 둔 리그 기록을 읽지 못했습니다 (' + season.name + '): ' + err);
    return null;
  }
}

/* =========================================================
   선수 등록
   ========================================================= */
// 등록 양식은 하나다. 처음 온 선수와 지난 시즌에 뛴 선수가 같은 칸을 채워 낸다.
// 지난 시즌에 승인됐던 선수(스팀 프로필과 디스코드가 모두 같은 사람)는 여기서 알아보고 인하우스 MMR을 이어받게 한다:
//  - 닉네임, 포지션 순서, 최고 MMR은 이번에 적어 낸 값으로 한다
//  - MMR 칸에는 적어 낸 현재 MMR 대신, 지난 시즌이 끝났을 때의 인하우스 MMR을 넣는다 (carriedMmr_)
// 승인한 명단을 리그 매니저로 불러올 때 이 MMR 칸이 새 시즌 인하우스 MMR의 출발점이 된다.
function register_(body) {
  // 사람 눈에 보이지 않는 칸이 채워져 있으면 자동 입력 프로그램으로 보고, 성공한 척만 한다
  if (body.website) return { updated: false };
  if (PropertiesService.getScriptProperties().getProperty('REG_OPEN') === 'false') fail_('지금은 선수 등록 기간이 아닙니다', 'closed');

  const nickname = cleanNickname_(body.nickname);
  const discord = normDiscord_(body.discord);
  const mmr = parseMmr_(body.mmr);
  const peak = parsePeak_(body.peak, mmr);
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
    const mine = rows.find(r => sameSteam_(r, steam));
    const nickOwner = rows.find(r => nameKey_(r.nickname) === nameKey_(nickname));
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

    // 지난 시즌에 승인됐던 선수인지 본다. 이번 시즌에 처음 내는 것이면, 스팀과 디스코드 가운데 한쪽만 지난 기록과 같은 경우를 여기서 거절한다
    const past = findPast_(steam, discord, !mine);
    const back = !!(past && past.approved);
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
      if (!back) line[COL['MMR']] = mmr;                   // 재참가 선수의 MMR은 처음 낼 때 이어받은 값 그대로 둔다
      prefCells.forEach((v, i) => { line[COL['1지망'] + i] = v; });
      line[COL['비고']] = mine.note ? text_(mine.note) : '';
      if (peak !== null) line[COL['최고MMR']] = peak;
      sheet.getRange(mine.rowNumber, 1, 1, HEADERS.length).setValues([line]);
      return { updated: true, returning: back, mmr: back ? mine.mmr : mmr };
    }

    // from 은 선수에게 알려 줄 시즌 이름: 인하우스 MMR을 이어받았으면 그 MMR이 나온 시즌, 아니면 승인됐던 시즌
    const label = s => s || '지난 시즌';
    let start = mmr, from = '', inhouse = false, note = '';
    if (back) {
      const got = carriedMmr_(past, steam, discord);
      start = got.mmr;
      inhouse = got.inhouse;
      from = got.inhouse ? got.season : past.season;
      note = '재참가 · ' + label(past.season) + (got.inhouse
        ? ' · ' + (got.season === past.season ? '' : label(got.season) + ' ') + '인하우스 MMR 이어받음'
        : ' · 그때 등록한 MMR 이어받음');
    } else if (past) {
      // 지난 시즌에 등록은 했지만 승인되지 않았던 사람. 처음 온 선수처럼 받되, 운영진이 알아보게 적어 둔다
      note = label(past.season) + '에도 등록함 (그때 ' + past.row.status + ')';
    }
    const line = new Array(HEADERS.length).fill('');
    line[COL['등록시각']] = now;
    line[COL['수정시각']] = now;
    line[COL['상태']] = '대기';
    line[COL['닉네임']] = text_(nickname);
    line[COL['스팀프로필']] = text_(steam.url);
    line[COL['스팀키']] = text_(steam.key);
    line[COL['디스코드']] = text_(discord);
    line[COL['MMR']] = start;
    prefCells.forEach((v, i) => { line[COL['1지망'] + i] = v; });
    line[COL['비고']] = note ? text_(note) : '';
    line[COL['최고MMR']] = peak === null ? '' : peak;
    sheet.appendRow(line);
    return { updated: false, returning: back, from, inhouse, mmr: start };
  });

  cache.put(rlKey, '1', 30);
  return result;
}

// 이름을 견줄 때 쓰는 모양: 공백과 대소문자는 무시한다
function nameKey_(v) {
  return String(v == null ? '' : v).toLowerCase().replace(/\s+/g, '');
}

function sameSteam_(row, steam) {
  return row.steamKey === steam.key || (!!steam.legacyKey && row.steamKey === steam.legacyKey);
}

// 지난 시즌의 등록 탭에서 이 사람을 찾는다 (가장 최근 시즌부터).
// 승인됐던 등록만 본인 확인이 끝난 것으로 본다. 스팀과 디스코드가 모두 같은 승인 기록이 있으면 재참가 선수다.
// 한쪽만 같은 승인 기록이 있으면 잘못 적었거나 계정이 바뀐 것이라, strict 일 때는 다시 확인하도록 거절한다
// (그대로 받으면 디스코드를 잘못 적은 선수가 지난 시즌의 인하우스 MMR을 잃고 새 선수가 된다).
// 돌려주는 값: { row, season, index, approved } 또는 null. approved 가 false 면 등록만 하고 승인되지 않았던 기록이다.
function findPast_(steam, discord, strict) {
  const list = seasons_();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let waiting = null;
  for (let i = list.length - 2; i >= 0; i--) {
    const sheet = sheetById_(ss, list[i].id);
    if (!sheet) continue;                                  // 탭이 지워진 시즌은 건너뛴다
    const rows = readRows_(sheet).filter(r => sameSteam_(r, steam) || r.discord === discord);
    const approved = rows.filter(r => r.status === '승인');
    const both = approved.filter(r => sameSteam_(r, steam) && r.discord === discord)[0];
    if (both) return { row: both, season: list[i].name, index: i, approved: true };
    if (approved.length) {
      if (!strict) return null;
      fail_(approved.some(r => sameSteam_(r, steam))
        ? '이 스팀 프로필은 지난 시즌에 다른 디스코드 계정으로 등록돼 있었습니다. 디스코드 사용자명을 다시 확인해 주세요. 계정이 바뀌었다면 운영진에게 알려 주세요.'
        : '이 디스코드 계정은 지난 시즌에 다른 스팀 프로필로 등록돼 있었습니다. 스팀 프로필 주소를 다시 확인해 주세요. 계정이 바뀌었다면 운영진에게 알려 주세요.', 'conflict');
    }
    if (!waiting) {
      const same = rows.filter(r => sameSteam_(r, steam) && r.discord === discord)[0];
      if (same) waiting = { row: same, season: list[i].name, index: i, approved: false };
    }
  }
  return waiting;
}

// 재참가 선수가 이어받을 MMR: 지난 시즌이 끝났을 때의 인하우스 MMR.
// 새 시즌을 시작할 때 보관해 둔 리그 기록(newSeason_)을 최근 시즌부터 찾아본다. 지난 시즌의 기록은 그때의 계산 방식으로
// 정산된 값 그대로 쓴다. 계산 방식은 시즌마다 달라질 수 있으니 다시 계산하지 않는다.
// 기록에서 선수를 찾는 순서: 스팀 고유 번호 → 디스코드 → (둘 다 적혀 있지 않은 선수에 한해) 그 시즌에 등록한 닉네임.
// 어느 시즌의 기록에도 없으면(승인만 되고 선수단에 들어간 적이 없는 경우) 그때 등록한 MMR을 쓴다.
function carriedMmr_(past, steam, discord) {
  const list = seasons_();
  const id64 = steam.key.slice(2);
  for (let i = list.length - 2; i >= 0; i--) {
    const league = archivedLeague_(list[i]);
    if (!league) continue;
    const nick = i === past.index ? nameKey_(past.row.nickname) : '';
    const players = league.players.filter(p => p && typeof p === 'object');
    const found = players.filter(p => leagueSteamId_(p.steam) === id64)[0]
      || players.filter(p => p.discord && nameKey_(String(p.discord).replace(/^@/, '')) === discord)[0]
      || (nick ? players.filter(p => !p.steam && !p.discord && nameKey_(p.name) === nick)[0] : undefined);
    const mmr = found ? Math.round(Number(found.mmr)) : NaN;
    if (Number.isFinite(mmr)) return { mmr: Math.max(0, mmr), inhouse: true, season: list[i].name };
  }
  return { mmr: past.row.mmr, inhouse: false, season: past.season };
}

// 리그 기록에 적힌 스팀 프로필 주소에서 고유 번호를 읽는다. 없으면 ''
function leagueSteamId_(v) {
  const m = String(v == null ? '' : v).match(/7656\d{13}/);
  return m ? m[0] : '';
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

// 디스코드 사용자명(영문 소문자·숫자·밑줄·마침표) 또는 숫자로 된 사용자 ID를 받는다.
// 예전 방식(이름#1234)은 받지 않는다(버전 9). 지금의 디스코드 계정에는 없는 모양이라 봇이 그 선수를 찾지 못하고,
// 이름 부분에 아무 글자나 들어갈 수 있어서 운영진 화면이나 디스코드 메시지에 그대로 실리면 위험하다.
function normDiscord_(v) {
  const s = String(v == null ? '' : v).trim().replace(/^@/, '').toLowerCase();
  if (/^\d{17,20}$/.test(s)) return s;
  if (/^[a-z0-9_.]{2,32}$/.test(s) && !/\.\./.test(s)) return s;
  if (/#\d{4}$/.test(s))
    fail_('이름#1234 모양은 이제 쓰이지 않습니다. 디스코드 프로필에 보이는 지금 사용자명을 넣어 주세요.', 'discord');
  fail_('디스코드 사용자명을 확인해 주세요. 영문 소문자·숫자·밑줄(_)·마침표(.)만 쓸 수 있습니다.', 'discord');
}

function parseMmr_(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0 || n > MAX_MMR || Math.round(n) !== n) fail_('MMR은 0부터 ' + MAX_MMR + ' 사이의 정수로 넣어 주세요', 'mmr');
  return n;
}

// 최고 MMR(도타 2를 하면서 가장 높았던 MMR)은 운영진이 참고만 하는 값이다. 인하우스 MMR에는 쓰지 않는다.
// 이 칸이 없던 때의 등록 페이지는 값을 보내지 않으므로, 비어 있으면 빈칸으로 둔다(null).
function parsePeak_(v, mmr) {
  if (v === undefined || v === null || v === '') return null;
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0 || n > MAX_MMR || Math.round(n) !== n) fail_('최고 MMR은 0부터 ' + MAX_MMR + ' 사이의 정수로 넣어 주세요', 'peak');
  if (n < mmr) fail_('최고 MMR은 현재 MMR보다 낮을 수 없습니다. 지금이 가장 높다면 현재 MMR과 같은 값을 넣어 주세요.', 'peak');
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
      note: d[COL['비고']].trim(),
      peak: d[COL['최고MMR']].trim() === '' ? null : (Number(String(d[COL['최고MMR']]).replace(/[^\d.]/g, '')) || 0)
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

// 등록 명단. 보통은 지금 시즌의 것이고, seasonNo(시즌 번호: 첫 시즌이 0)를 주면 그 시즌의 명단을 돌려준다.
// 시즌 번호는 시즌 이름을 고치거나 탭을 다시 만들어도 바뀌지 않는다. 봇이 시즌이 넘어간 것을 알아보고,
// 끝난 시즌의 선수에게서 역할을 거둘 때 쓴다.
function listSeason_(body) {
  const list = seasons_();
  const last = list.length - 1;
  const no = body.seasonNo === undefined || body.seasonNo === null ? last : Number(body.seasonNo);
  if (!Number.isInteger(no) || no < 0 || no > last) fail_('그런 시즌이 없습니다', 'season');
  const sheet = no === last ? getSheet_() : sheetById_(SpreadsheetApp.getActiveSpreadsheet(), list[no].id);
  return { players: sheet ? listRegistrations_(sheet) : [], season: list[no].name, seasonNo: no, current: last };
}

function listRegistrations_(sheet) {
  return readRows_(sheet).map(r => ({
    registeredAt: r.registeredAt,
    updatedAt: r.updatedAt,
    status: r.status,
    nickname: r.nickname,
    steamUrl: r.steamUrl,
    steamKey: r.steamKey,
    discord: r.discord,
    mmr: r.mmr,
    peak: r.peak,
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
  const item = x => !!x && typeof x === 'object';       // 모양이 깨진 항목은 버린다
  const players = r.players.slice(0, 1000).filter(item).map(p => ({
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
      rows: m.rows.slice(0, 10).filter(item).map(x => ({
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
    try { text = alive_(DriveApp.getFileById(id)).getBlob().getDataAsString('UTF-8') || ''; } catch (err) { /* 파일이 지워졌으면 없는 것으로 본다 */ }
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

// 끝난 시즌의 순위·경기 기록 탭에 시즌 이름을 붙여 남겨 둔다. 새 시즌의 탭은 writeMirror_ 가 다시 만든다
function keepMirror_(season) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const label = season || '지난 시즌';
    ['순위', '경기 기록'].forEach(base => {
      const sheet = ss.getSheetByName(base);
      if (!sheet) return;
      nameTab_(ss, sheet, label, base);
      if (sheet.getLastRow() > 0) sheet.getRange(1, 1).setValue(text_('끝난 시즌(' + label + ')의 기록입니다. 보관해 둔 것이라 더 바뀌지 않습니다.'));
    });
  } catch (err) {
    console.warn('지난 시즌의 순위·경기 기록 탭을 남기지 못했습니다: ' + err);
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
    try { return alive_(DriveApp.getFileById(id)); } catch (err) { /* 지워졌으면 새로 만든다 */ }
  }
  const file = DriveApp.createFile(name, JSON.stringify({ players: [], matches: [] }), 'application/json');
  props.setProperty(prop, file.getId());
  return file;
}

// 휴지통에 들어간 드라이브 파일은 30일 뒤에 영영 지워진다. 그때까지는 이 스크립트가 아무 일 없이 읽고 쓰므로,
// 운영자가 드라이브를 정리하다 기록 파일을 버린 것을 모르고 지내다 기록을 통째로 잃을 수 있다. 쓰는 파일이 휴지통에 있으면 도로 꺼내 둔다.
function alive_(file) {
  try {
    if (file.isTrashed()) {
      file.setTrashed(false);
      console.warn('휴지통에 있던 기록 파일을 도로 꺼냈습니다: ' + file.getName());
    }
  } catch (err) {
    console.warn('기록 파일이 휴지통에 있는지 확인하지 못했습니다: ' + err);
  }
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
  } else {
    // 예전 버전에서 만든 탭에는 나중에 생긴 칸(비고, 최고MMR)의 머리글이 없다. 비어 있는 머리글만 채운다
    const head = sheet.getRange(1, 1, 1, HEADERS.length).getDisplayValues()[0];
    HEADERS.forEach((h, i) => { if (head[i] === '') sheet.getRange(1, i + 1).setValue(h).setFontWeight('bold'); });
  }
}
