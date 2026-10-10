/**
 * 도타 2 인하우스 리그 서버 (Google Apps Script)
 *
 * 하는 일
 *  - 선수 등록 페이지에서 받은 정보를 이 구글 시트에 저장한다 (시트는 시트를 만든 사람의 구글 계정에만 보인다)
 *    시즌마다 '선수등록 (시즌 이름)' 탭을 따로 쓴다. 지난 시즌에 승인됐던 선수가 같은 스팀 프로필과 디스코드로 다시 등록하면
 *    그 시즌이 끝났을 때의 인하우스 MMR을 이어받는다
 *  - 리그 관리자 키가 있는 사람에게만 등록 명단을 돌려주고, 승인 상태와 등록 기간을 바꾸고 새 시즌을 시작하게 한다
 *    리그 관리자는 선수 승인처럼 리그를 관리하는 사람이다(주인 키를 가진 사람과, 키를 따로 받은 사람).
 *    디스코드에서 봇 명령어로 내전을 열고 결과를 기록하는 리그 운영진은 키를 쓰지 않는다(봇이 자기 키로 대신 한다)
 *    (새 시즌을 시작하면 끝난 시즌의 리그 기록을 따로 보관하고, 새 시즌은 빈 기록에서 시작한다)
 *  - 리그 관리자가 승인한 선수를 리그 기록의 선수단에 바로 넣는다 (봇이 그 선수로 팀을 짤 수 있게)
 *  - 리그 매니저가 올린 경기 기록을 받아, 개인 정보를 뺀 공개용 기록으로 내보낸다
 *  - 디스코드 봇이 올린 참가 명단을 보관했다가 리그 매니저에 넘겨준다
 *
 * 처음 설치는 README.md의 "1. 구글 시트 서버 만들기"를 따라 하세요.
 * 코드를 고친 뒤에는 배포 → 배포 관리 → 수정(연필) → 버전: 새 버전 → 배포 를 눌러야 반영됩니다.
 */

const SERVER_VERSION = 14;                          // 서버를 고칠 때마다 올린다. 상태 응답에 실려서 새 버전이 배포됐는지 밖에서 확인할 수 있다
const SHEET_NAME = '선수등록';                             // 등록 탭 이름의 앞부분. 시즌마다 '선수등록 (시즌 이름)' 탭을 따로 쓴다
// 칸을 더할 때는 맨 뒤에 붙이고 LAYOUT 을 올린다. 이미 있는 탭에는 ready_ 가 새 머리글을 채워 넣는다
// 처리자·처리시각: 그 등록의 상태(승인·제외·대기)를 마지막으로 바꾼 리그 관리자와 그 시각 (버전 11)
const HEADERS = ['등록시각', '수정시각', '상태', '닉네임', '스팀프로필', '스팀키', '디스코드', 'MMR', '1지망', '2지망', '3지망', '4지망', '비고', '최고MMR', '처리자', '처리시각'];
const LAYOUT = '3';
const COL = HEADERS.reduce((o, h, i) => (o[h] = i, o), {});
const PREF_LABELS = ['캐리', '미드', '오프', '서폿'];          // 지망 번호 1~4
const STATUSES = ['대기', '승인', '제외'];
const MAX_MMR = 15000;
const MAX_ROWS = 3000;
const ROSTER_MAX = 60;
const STEAM_TRIES = 4;                                     // 스팀 조회를 몇 번까지 시도할지
const DRIVE_TRIES = 3;                                     // 드라이브 파일을 몇 번까지 다시 읽어 볼지
const LEAGUE_MAX = 8000000;                                // 리그 기록의 최대 크기(글자 수)
const SEASON_WORD = '시즌 변경';                            // 새 시즌을 시작할 때 리그 관리자가 직접 입력해야 하는 확인 문구
const LINKED = '1';                                        // 승인한 선수를 선수단에 넣기 시작했다는 표시 (버전 10). ready_ 가 처음 한 번 맞춘다
const OWNER_NAME = '주인';                                 // 주인 키(ADMIN_KEY)로 한 일에 남기는 이름
const STAFF_MAX = 30;                                      // 키를 따로 받는 리그 관리자의 최대 인원
const LOG_TAB = '운영 기록';                                // 누가 무엇을 했는지 남기는 탭
const LOG_HEADERS = ['시각', '시즌', '리그 관리자', '한 일', '대상', '내용'];
let ACTOR = null;                                          // 이번 요청을 보낸 리그 관리자 {owner, id, name}. requireAdmin_ 이 채운다
let PAST_ROWS = null;                                      // 이번 요청에서 읽은 끝난 시즌들의 등록 명단 {시즌 번호: 줄들} (pastRows_)

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
  Logger.log('주인 키: ' + key);
  Logger.log('이 키는 리그 관리자 페이지·리그 매니저·디스코드 봇에 넣습니다. 다른 사람에게 보이지 않게 보관하세요.');
}

/** 주인 키가 새어 나갔을 때 실행하면 새 키를 만듭니다. 리그 관리자 페이지·매니저·봇에 넣어 둔 주인 키도 바꿔야 합니다. */
function resetAdminKey() {
  const key = (Utilities.getUuid() + Utilities.getUuid()).replace(/-/g, '');
  PropertiesService.getScriptProperties().setProperty('ADMIN_KEY', key);
  Logger.log('새 주인 키: ' + key);
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
      case 'adminSyncPlayers': requireAdmin_(body); return syncNow_();
      case 'adminSetPrefs': requireAdmin_(body); return setPrefs_(body);
      case 'adminConfig': requireAdmin_(body); return setConfig_(body);
      // 되돌릴 수 없는 일(새 시즌 시작)과 리그 관리자를 늘리고 줄이는 일은 주인 키로만 한다
      case 'adminNewSeason': requireOwner_(body); return newSeason_(body);
      case 'adminStaff': requireOwner_(body); return staffList_();
      case 'adminStaffAdd': requireOwner_(body); return staffAdd_(body);
      case 'adminStaffRemove': requireOwner_(body); return staffRemove_(body);
      case 'publishRecords': requireAdmin_(body); return publishRecords_(body);
      case 'pushRoster': requireAdmin_(body); return pushRoster_(body);
      case 'adminRoster': requireAdmin_(body); return { roster: getRoster_() };
      case 'adminLeague':
        requireAdmin_(body);
        // 봇은 팀을 짜기 직전에 sync 를 붙여 받는다. 승인됐는데 선수단에 빠져 있는 선수가 있으면 그때 채워진다. 맞추지 못해도 기록은 돌려준다
        if (body.sync === true) { try { syncNow_(); } catch (err) { console.warn('선수단을 맞추지 못한 채 기록을 돌려줍니다: ' + err); } }
        return getLeague_();
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
  ACTOR = null;
  PAST_ROWS = null;
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

// 리그 관리자 키를 확인하고, 누가 보낸 요청인지 돌려준다(ACTOR 에도 적어 둔다).
// 키는 두 가지다: 주인 키(ADMIN_KEY, 운영자와 봇이 쓴다)와 리그 관리자마다 따로 만들어 준 키(버전 11, 아래 "리그 관리자" 절).
function requireAdmin_(body) {
  const key = PropertiesService.getScriptProperties().getProperty('ADMIN_KEY');
  const given = typeof body.key === 'string' ? body.key : '';
  if (key && given && given === key) return (ACTOR = { owner: true, id: '', name: OWNER_NAME });
  if (given.length >= 32 && given.length <= 200) {         // 리그 관리자 키는 64자다. 터무니없이 짧거나 긴 값은 지문을 내 보지도 않는다
    const hash = keyHash_(given);
    const me = staff_().filter(s => s.hash === hash)[0];
    if (me) {
      touchStaff_(me);
      return (ACTOR = { owner: false, id: me.id, name: me.name });
    }
  }
  fail_('리그 관리자 키가 맞지 않습니다', 'auth');
}

function requireOwner_(body) {
  const who = requireAdmin_(body);
  if (!who.owner) fail_('이 일은 주인 키로만 할 수 있습니다. 주인 키를 가진 리그 관리자에게 부탁해 주세요.', 'owner');
  return who;
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

// 리그 관리자에게는 등록 인원 수와 지난 시즌 이름도 함께 준다 (오래된 시즌이 앞).
// role 과 name 은 지금 쓰는 키가 누구의 것인지다. 리그 관리자 페이지가 주인 키로만 할 수 있는 칸을 가릴 때 본다
function adminStatus_() {
  return Object.assign(statusInfo_(), {
    registered: Math.max(0, getSheet_().getLastRow() - 1),
    pastSeasons: seasons_().slice(0, -1).map(s => s.name),
    role: ACTOR && !ACTOR.owner ? 'staff' : 'owner',
    name: ACTOR ? ACTOR.name : OWNER_NAME
  });
}

function setConfig_(body) {
  const props = PropertiesService.getScriptProperties();
  if (typeof body.open === 'boolean') {
    const was = props.getProperty('REG_OPEN') !== 'false';
    props.setProperty('REG_OPEN', String(body.open));
    if (was !== body.open) logAlone_(body.open ? '등록 열기' : '등록 닫기', '', '');
  }
  if (typeof body.season === 'string') {
    const old = seasons_().slice(-1)[0].name;
    renameSeason_(body.season);
    const now = seasons_().slice(-1)[0].name;
    if (old !== now) logAlone_('시즌 이름 고침', now, old + ' → ' + now);
  }
  return adminStatus_();
}

/* =========================================================
   리그 관리자 (버전 11)
   ========================================================= */
// 리그 관리자마다 키를 따로 준다. 전에는 모두가 주인 키 하나를 같이 써서, 한 사람만 빼려면 키를 새로 만들어 모두에게 다시 돌려야 했고
// 누가 무엇을 했는지도 알 수 없었다(운영자가 2026-10-08에 "다른 리그 관리자를 편하게 추가·제거"할 방법을 골랐다).
//  - 주인 키(ADMIN_KEY)는 그대로다. 운영자와 봇이 쓴다. 리그 관리자를 늘리고 줄이는 일과 새 시즌 시작은 주인 키로만 한다.
//  - 리그 관리자의 키는 만들 때 한 번만 돌려주고, 서버에는 지문(SHA-256)만 둔다. 스크립트 속성을 들여다봐도 키를 알 수 없다.
//    키는 244비트 난수라 지문에서 거꾸로 찾을 수 없다. 잃어버리면 그 리그 관리자를 끊고 새로 추가한다.
//  - 스크립트 속성 STAFF 에 [{id, name, hash, createdAt}] 로 적는다. 마지막으로 쓴 날은 STAFF_SEEN_<id> 에 따로 둔다
//    (목록을 고치는 요청과 겹쳐 서로 덮어쓰지 않게).
function staff_() {
  try {
    const list = JSON.parse(PropertiesService.getScriptProperties().getProperty('STAFF') || '[]');
    return Array.isArray(list) ? list.filter(s => s && typeof s === 'object' && s.id && s.hash && s.name) : [];
  } catch (err) {
    console.warn('리그 관리자 목록을 읽지 못했습니다: ' + err);
    return [];
  }
}

function keyHash_(key) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, key, Utilities.Charset.UTF_8)
    .map(b => ('0' + (b & 0xff).toString(16)).slice(-2)).join('');
}

function today_() {
  return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm').slice(0, 10);
}

// 그 리그 관리자가 마지막으로 키를 쓴 날(한국 날짜)을 적어 둔다. 하루에 한 번만 쓴다
function touchStaff_(me) {
  try {
    const props = PropertiesService.getScriptProperties(), day = today_();
    if (props.getProperty('STAFF_SEEN_' + me.id) !== day) props.setProperty('STAFF_SEEN_' + me.id, day);
  } catch (err) { /* 못 적어도 요청은 그대로 처리한다 */ }
}

function staffName_(v) {
  const s = String(v == null ? '' : v).replace(/[\u0000-\u001f\u007f<>]/g, '').replace(/\s+/g, ' ').trim();
  if (!s) fail_('리그 관리자의 이름을 넣어 주세요', 'name');
  if (s.length > 20) fail_('이름은 20자 이내로 넣어 주세요', 'name');
  return s;
}

function staffList_() {
  const props = PropertiesService.getScriptProperties();
  return { staff: staff_().map(s => ({ id: s.id, name: s.name, createdAt: s.createdAt || '', lastDay: props.getProperty('STAFF_SEEN_' + s.id) || '' })) };
}

// 리그 관리자를 추가하고 그 사람의 키를 돌려준다. 키는 이 답에만 실리고 서버에는 남지 않는다
function staffAdd_(body) {
  const name = staffName_(body.name);
  return withLock_(() => {
    const list = staff_();
    if (list.length >= STAFF_MAX) fail_('리그 관리자는 ' + STAFF_MAX + '명까지 둘 수 있습니다. 쓰지 않는 리그 관리자를 먼저 끊어 주세요.', 'name');
    if (nameKey_(name) === nameKey_(OWNER_NAME) || list.some(s => nameKey_(s.name) === nameKey_(name)))
      fail_('이미 있는 이름입니다. 다른 이름을 넣어 주세요.', 'name');
    const key = (Utilities.getUuid() + Utilities.getUuid()).replace(/-/g, '');
    let id = '';
    for (let n = 0; !id || list.some(s => s.id === id); n++) id = 'a' + Date.now().toString(36) + n.toString(36);
    list.push({ id: id, name: name, hash: keyHash_(key), createdAt: new Date().toISOString() });
    PropertiesService.getScriptProperties().setProperty('STAFF', JSON.stringify(list));
    log_('리그 관리자 추가', name, '');
    return Object.assign(staffList_(), { key: key, name: name });
  });
}

// 리그 관리자를 끊는다. 그 사람의 키는 바로 쓸 수 없게 된다
function staffRemove_(body) {
  const id = String(body.id || '');
  return withLock_(() => {
    const props = PropertiesService.getScriptProperties();
    const list = staff_();
    const me = list.filter(s => s.id === id)[0];
    if (!me) fail_('그런 리그 관리자가 없습니다. 목록을 새로 고쳐 주세요.', 'staff');
    props.setProperty('STAFF', JSON.stringify(list.filter(s => s !== me)));
    try { props.deleteProperty('STAFF_SEEN_' + id); } catch (err) { /* 남아 있어도 쓰이지 않는다 */ }
    log_('리그 관리자 끊기', me.name, '');
    return staffList_();
  });
}

/* ---- 운영 기록 ----
   누가 무엇을 했는지를 시트의 '운영 기록' 탭에 한 줄씩 남긴다(등록 승인·제외·대기, 등록 열고 닫기, 시즌, 리그 관리자 추가·끊기).
   기록을 남기지 못해도 하던 일은 그대로 끝낸다. */
function log_(what, target, detail) {
  logRows_([[what, target, detail]]);
}

// 잠금을 잡지 않은 곳에서 남길 때 쓴다. 두 요청이 같은 줄에 겹쳐 쓰지 않게 잠근 뒤에 적고, 잠그지 못하면 기록만 건너뛴다
function logAlone_(what, target, detail) {
  try { withLock_(() => log_(what, target, detail)); }
  catch (err) { console.warn('운영 기록을 남기지 못했습니다: ' + err); }
}

function logRows_(rows) {
  if (!rows.length) return;
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName(LOG_TAB);
    if (!sheet) {
      sheet = ss.insertSheet(LOG_TAB);
      sheet.getRange(1, 1, 1, LOG_HEADERS.length).setValues([LOG_HEADERS]).setFontWeight('bold');
      sheet.setFrozenRows(1);
    } else if (String(sheet.getRange(1, 3, 1, 1).getDisplayValues()[0][0]) === '운영진') {
      sheet.getRange(1, 3, 1, 1).setValues([[LOG_HEADERS[2]]]);   // 버전 13에서 이름을 바꿨다 (운영진 → 리그 관리자)
    }
    const list = seasons_(), now = new Date(), who = ACTOR ? ACTOR.name : '';
    const season = list[list.length - 1].name;
    const table = rows.map(r => [now, text_(season), text_(who), text_(r[0]), text_(r[1]), text_(r[2])]);
    const at = sheet.getLastRow() + 1, need = at + table.length - 1;
    if (sheet.getMaxRows() < need) sheet.insertRowsAfter(sheet.getMaxRows(), need - sheet.getMaxRows());
    sheet.getRange(at, 1, table.length, LOG_HEADERS.length).setValues(table);
  } catch (err) {
    console.warn('운영 기록을 남기지 못했습니다: ' + err);
  }
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
// 버전 10으로 올린 뒤 첫 요청에서는 그때까지 승인돼 있던 선수를 선수단에 넣는다.
function ready_() {
  const props = PropertiesService.getScriptProperties();
  const raw = props.getProperty('SEASONS') || '';
  const pending = raw.indexOf('"leaguePending":true') >= 0;      // 새 시즌을 시작하다 리그 기록을 비우지 못한 채 남은 경우
  if (raw && !pending && props.getProperty('LAYOUT') === LAYOUT && props.getProperty('LINKED') === LINKED) return;
  withLock_(() => {
    const list = seasons_();
    if (props.getProperty('LAYOUT') !== LAYOUT) {
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      list.forEach(s => { const sheet = sheetById_(ss, s.id); if (sheet) prepareSheet_(sheet); });
      props.setProperty('LAYOUT', LAYOUT);
    }
    try { finishSeason_(list); }
    catch (err) { console.error('리그 기록을 새로 시작하지 못했습니다. 다음 요청에서 다시 합니다: ' + (err && err.stack || err)); }
    if (props.getProperty('LINKED') !== LINKED) {
      // 한 번만 해 본다. 여기서 못 해도 다음에 누군가를 승인할 때나 리그 관리자 페이지의 "선수단 다시 맞추기"로 채워진다
      props.setProperty('LINKED', LINKED);
      linkPlayers_(readRows_(getSheet_()), [], []);
    }
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

// 새 시즌을 시작한다. 버전 14부터 선수는 이어 가고 순위만 새로 센다
// (운영자가 2026-10-09에 정함: "한 번 등록하면 제외되지 않고서야 계속 선수", "시즌이 바뀌면 이번 시즌의 랭킹만 초기화").
//  - 등록: 새 시즌의 탭을 만들고 지난 탭의 명단을 상태(승인·대기·제외) 그대로 옮겨 적는다. 선수는 다시 등록하지 않는다.
//    지난 시즌의 명단은 그 시즌의 탭에 그대로 남는다.
//  - 리그 기록: 끝나는 시즌의 기록(선수의 인하우스 MMR·전적, 경기)을 드라이브 파일로 따로 보관하고, 새 시즌은 승인된 선수를 그대로 둔 채
//    승·패·연속·자리별 판수와 경기만 비운다(설정은 그대로, carryPlayers_).
//  - 인하우스 MMR은 이어 간다. body.mmr 이 'reset' 이면 끝나는 시즌을 시작했을 때의 값으로 되돌린다(시험 삼아 치른 시즌의 변동을 버릴 때).
//  - 옮겨 적는 승인된 줄의 MMR 칸에는 그 선수가 새 시즌을 시작하는 MMR을 적는다. 승인을 풀었다 다시 승인해도 그 값에서 시작하게 하려는 것이다
//    (syncPlayers_ 는 경기를 치르지 않은 선수의 MMR을 등록 탭의 값으로 맞춘다).
function newSeason_(body) {
  const name = seasonName_(body.season);
  if (!name) fail_('새 시즌의 이름을 넣어 주세요', 'season');
  // 되돌릴 수 없는 일이라, 리그 관리자 페이지에서 바뀌는 것들을 보고 확인 문구를 직접 입력한 요청만 받는다
  if (body.confirm !== SEASON_WORD)
    fail_('새 시즌을 시작하려면 확인 문구("' + SEASON_WORD + '")를 입력해야 합니다. 리그 관리자 페이지를 새로 고친 뒤 다시 해 주세요.', 'confirm');
  const reset = body.mmr === 'reset';
  return withLock_(() => {
    const props = PropertiesService.getScriptProperties();
    const list = seasons_();
    if (list.some(s => seasonKey_(s.name) === seasonKey_(name)))
      fail_('이미 있는 시즌 이름입니다. 다른 이름을 넣어 주세요.', 'season');
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const cur = list[list.length - 1];

    // 보관이 먼저다. 여기서 실패하면 아무것도 바뀌지 않는다.
    // 있어야 할 기록을 읽지 못했을 때(드라이브가 잠깐 답하지 않을 때)는 "기록이 없다"로 치지 않고 멈춘다.
    // 그대로 가면 보관도 초기화도 하지 않은 채 시즌만 넘어가서, 지난 시즌의 선수와 경기가 새 시즌의 기록에 남는다
    let ended;
    try { ended = readLeague_(); }
    catch (err) {
      console.error('새 시즌: 리그 기록을 읽지 못했습니다: ' + (err && err.stack || err));
      fail_('지금 시즌의 리그 기록을 읽지 못해 새 시즌을 시작하지 않았습니다. 잠시 뒤에 다시 해 주세요. ' +
        '계속 안 되면 리그 매니저를 열어 서버에 기록을 한 번 올린 뒤 다시 해 주세요.', 'league');
    }
    // 옮겨 적을 명단을 먼저 만든다. 여기까지는 아무것도 바꾸지 않는다
    const old = sheetById_(ss, cur.id);
    const rows = old ? readRows_(old) : [];
    const players = ended ? carryPlayers_(ended, rows, reset) : [];
    const lines = rows.map(r => carriedLine_(r, players));

    if (ended) {
      const label = String(cur.name || '이름 없는 시즌').replace(/[\\\/:*?"<>|]/g, ' ').replace(/\s+/g, ' ').trim();
      cur.league = DriveApp.createFile('인하우스_리그기록_' + label + '.json', JSON.stringify(ended), 'application/json').getId();
    }
    cur.endedAt = new Date().toISOString();
    delete cur.leaguePending;                                    // 끝나는 시즌에 남아 있던 표시는 더 볼 일이 없다 (남겨 두면 ready_ 가 요청마다 잠금을 잡는다)
    delete cur.mmrReset;

    const sheet = ss.insertSheet(freeTabName_(ss, name), 0);     // 지금 시즌의 탭이 맨 앞에 오게 한다
    try {
      prepareSheet_(sheet);
      if (lines.length) sheet.getRange(2, 1, lines.length, HEADERS.length).setValues(lines);
    } catch (err) {
      // 명단을 옮겨 적지 못했으면 시즌을 넘기지 않는다(시즌 목록을 아직 쓰지 않았다). 만들다 만 탭은 지운다
      try { ss.deleteSheet(sheet); } catch (e) { /* 못 지워도 쓰이지 않는 탭 하나가 남을 뿐이다 */ }
      throw err;
    }
    const next = { name, id: sheet.getSheetId() };
    if (ended) {
      next.leaguePending = true;
      if (reset) next.mmrReset = true;                           // 기록을 바로 비우지 못해 다음 요청에서 이어 할 때도 같은 방식으로 하게 적어 둔다
    }
    list.push(next);
    saveSeasons_(list);
    props.setProperty('ROSTER', '');                             // 지난 시즌에 받은 참가 명단과 짠 팀은 새 시즌으로 가져가지 않는다
    props.setProperty('LINEUP', '');

    const approved = rows.filter(r => r.status === '승인').length;
    log_('새 시즌 시작', name, (cur.name || '이름 없는 시즌') + ' → ' + name + ' · 명단 ' + rows.length + '명(승인 ' + approved + '명)을 이어 감' +
      (reset ? ' · 인하우스 MMR은 시즌을 시작했을 때의 값으로 되돌림' : ''));

    // 시즌은 이미 바뀌었다. 리그 기록을 비우다 실패해도 여기서 멈추지 않고, 다음 요청 때 ready_ 가 이어서 한다
    try { finishSeason_(list); }
    catch (err) { console.error('리그 기록을 새로 시작하지 못했습니다. 다음 요청에서 다시 합니다: ' + (err && err.stack || err)); }
    return Object.assign(adminStatus_(), { carried: { rows: rows.length, approved, mmr: reset ? 'reset' : 'keep' } });
  });
}

// 새 시즌의 리그 기록을 아직 새로 시작하지 못했으면(leaguePending) 시작한다. 잠금을 잡은 상태에서 부른다
function finishSeason_(list) {
  const cur = list[list.length - 1];
  if (!cur.leaguePending) return;
  // 끝난 시즌을 보관해 둔 파일(시즌을 넘길 때 만든 사본)에서 선수단과 설정을 읽고, 읽지 못하면 아직 지난 시즌의 기록인 지금 파일에서 읽는다.
  // 지금 파일만 보면, 그 파일을 잠깐 읽지 못한 순간에 설정이 기본값으로 돌아간다
  const prev = list.length > 1 ? list[list.length - 2] : null;
  const kept = (prev && archivedLeague_(prev)) || getLeague_().league;
  const rows = readRows_(getSheet_());
  // 둘 다 읽지 못하면 빈 선수단에서 시작하고, 바로 아래에서 승인된 줄로 다시 채운다. 그 줄의 MMR 칸에 새 시즌을 시작하는 MMR이
  // 이미 적혀 있어서(newSeason_) MMR은 이어진다. 매니저에서 고친 이름·지망과 손으로 넣은 선수만 잃는다
  startLeague_(kept && kept.settings, prev ? prev.name : '', kept ? carryPlayers_(kept, rows, cur.mmrReset === true) : []);
  delete cur.leaguePending;
  delete cur.mmrReset;
  saveSeasons_(list);
  // 승인됐는데 선수단에 없는 선수(기록을 새로 시작하지 못하고 있던 사이에 승인한 선수 등)를 넣는다
  linkPlayers_(rows, [], []);
}

// 새 시즌으로 이어 갈 선수단 (버전 14). league 는 끝난 시즌의 리그 기록, rows 는 등록 명단이다.
//  - 승인이 아닌 등록(대기로 돌렸거나 제외한 줄)에 맞는 선수만 빼고 모두 이어 간다. 지난 시즌에 경기를 치러 남겨 뒀던 선수가 이때 빠진다.
//    등록 줄이 없는 선수(매니저에서 손으로 넣은 선수)는 남긴다.
//  - id·이름·지망·디스코드·스팀은 그대로 두고(매니저에서 고친 값을 지킨다) 승·패·연속·자리별 판수만 0으로 한다.
//  - 인하우스 MMR은 반올림해 이어 가고, 그 값이 새 시즌의 출발점(baseMMR)이 된다. reset 이면 끝난 시즌을 시작했을 때의 값(baseMMR)으로 되돌린다.
// 이미 새로 시작한 기록에 다시 돌려도 결과가 같다(기록을 쓰다 만 뒤에 다시 할 때).
function carryPlayers_(league, rows, reset) {
  const marks = rows.map(r => ({ np: playerFromRow_(r), approved: r.status === '승인' }));
  const out = [];
  (Array.isArray(league.players) ? league.players : []).forEach(p => {
    if (!p || typeof p !== 'object') return;
    const mine = marks.filter(m => rowIsPlayer_(m.np, p));
    if (mine.length && !mine.some(m => m.approved)) return;
    const now = Math.round(Number(p.mmr)), base = Math.round(Number(p.baseMMR));
    let start = reset && Number.isFinite(base) ? base : now;
    if (!Number.isFinite(start)) start = Number.isFinite(base) ? base : 0;
    start = Math.max(0, Math.min(MAX_MMR, start));
    out.push(Object.assign({}, p, { baseMMR: start, mmr: start, wins: 0, losses: 0, streak: 0, roleCount: [0, 0, 0, 0, 0] }));
  });
  return out;
}

// 지난 시즌의 등록 한 줄을 새 시즌의 탭에 옮겨 적을 모양으로 만든다. 날짜와 숫자는 값 그대로 두고 글자 칸은 글자로 감싼다.
// 승인된 줄의 MMR 칸은 그 선수가 새 시즌을 시작하는 인하우스 MMR로 바꾼다(선수단에서 찾지 못한 줄은 그대로 둔다)
function carriedLine_(r, players) {
  const line = r.raw.slice(0, HEADERS.length);
  while (line.length < HEADERS.length) line.push('');
  const t = v => v ? text_(v) : '';
  line[COL['상태']] = r.status;
  line[COL['닉네임']] = t(r.nickname);
  line[COL['스팀프로필']] = t(r.steamUrl);
  line[COL['스팀키']] = t(r.steamKey);
  line[COL['디스코드']] = t(r.discord);
  line[COL['비고']] = t(r.note);
  line[COL['처리자']] = t(r.by);
  if (r.status === '승인') {
    const np = playerFromRow_(r);
    const p = players.filter(q => rowIsPlayer_(np, q))[0];
    if (p) line[COL['MMR']] = p.mmr;
  }
  return line;
}

// 새 시즌의 리그 기록을 시작한다: 이어 가는 선수단(players)과 설정만 남기고 경기를 비운다. 번호를 올려서 매니저가 새 기록을 받아 가게 한다.
function startLeague_(settings, endedSeason, players) {
  const props = PropertiesService.getScriptProperties();
  const league = { players: players || [], matches: [], settings: settings || {} };
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
    const league = JSON.parse(readFile_(season.league));
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

    // 예전에 사용자 지정 주소로 저장된 줄(id:이름)도 같은 사람으로 알아본다
    const mine = rows.find(r => sameSteam_(r, steam));
    if (!mine && rows.length >= MAX_ROWS) fail_('등록 인원이 가득 찼습니다. 리그 관리자에게 문의해 주세요.');   // 이미 등록한 사람의 수정은 가득 차도 받는다
    const nickOwner = rows.find(r => nameKey_(r.nickname) === nameKey_(nickname));
    const discordOwner = rows.find(r => r.discord === discord);

    if (mine && mine.discord !== discord)
      fail_('이 스팀 프로필은 다른 디스코드 계정으로 이미 등록돼 있습니다. 디스코드 계정이 바뀌었다면 리그 관리자에게 알려 주세요.', 'conflict');
    if (!mine && discordOwner)
      fail_('이 디스코드 계정은 다른 스팀 프로필로 이미 등록돼 있습니다. 스팀 프로필이 바뀌었다면 리그 관리자에게 알려 주세요.', 'conflict');
    // 리그 관리자가 승인하거나 제외한 등록은 본인이 고칠 수 없다. 리그 관리자가 상태를 대기로 돌리면 다시 고칠 수 있다.
    if (mine && mine.status !== '대기')
      fail_('리그 관리자가 확인을 마친 등록이라 직접 고칠 수 없습니다. 바꿀 내용이 있으면 리그 관리자에게 알려 주세요.', 'locked');
    if (nickOwner && nickOwner !== mine)
      fail_('다른 선수가 이미 쓰고 있는 닉네임입니다. 다른 닉네임을 넣어 주세요.', 'nickname');
    // 지난 시즌에 다른 선수가 쓰던 닉네임도 그 선수만 다시 쓸 수 있다(버전 12, nickHeld_).
    // 이미 내 등록에 쓰고 있는 닉네임을 그대로 둔 채 다른 칸만 고치는 경우에는 다시 묻지 않는다
    if (!(mine && nameKey_(mine.nickname) === nameKey_(nickname)) && nickHeld_(nickname, steam, discord))
      fail_('지난 시즌에 다른 선수가 쓰던 닉네임입니다. 다른 닉네임을 넣어 주세요. 본인이 쓰던 닉네임이라면 그때와 같은 스팀 프로필과 디스코드로 등록해 주세요.', 'nickname');

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
      line[COL['처리자']] = mine.by ? text_(mine.by) : '';    // 글자 칸은 다시 쓸 때마다 글자로 감싼다 (=로 시작하는 이름이 수식이 되지 않게)
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
      // 지난 시즌에 등록은 했지만 승인되지 않았던 사람. 처음 온 선수처럼 받되, 리그 관리자가 알아보게 적어 둔다
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
  let waiting = null;
  for (let i = list.length - 2; i >= 0; i--) {
    const rows = pastRows_(list, i).filter(r => sameSteam_(r, steam) || r.discord === discord);   // 탭이 지워진 시즌은 빈 명단이다
    const approved = rows.filter(r => r.status === '승인');
    const both = approved.filter(r => sameSteam_(r, steam) && r.discord === discord)[0];
    if (both) return { row: both, season: list[i].name, index: i, approved: true };
    if (approved.length) {
      if (!strict) return null;
      fail_(approved.some(r => sameSteam_(r, steam))
        ? '이 스팀 프로필은 지난 시즌에 다른 디스코드 계정으로 등록돼 있었습니다. 디스코드 사용자명을 다시 확인해 주세요. 계정이 바뀌었다면 리그 관리자에게 알려 주세요.'
        : '이 디스코드 계정은 지난 시즌에 다른 스팀 프로필로 등록돼 있었습니다. 스팀 프로필 주소를 다시 확인해 주세요. 계정이 바뀌었다면 리그 관리자에게 알려 주세요.', 'conflict');
    }
    if (!waiting) {
      const same = rows.filter(r => sameSteam_(r, steam) && r.discord === discord)[0];
      if (same) waiting = { row: same, season: list[i].name, index: i, approved: false };
    }
  }
  return waiting;
}

// 끝난 시즌(list 의 i 번째)의 등록 명단. 한 요청 안에서는 탭을 한 번만 읽는다(재참가 확인과 닉네임 확인이 함께 쓴다).
// 탭이 지워졌으면 빈 명단이다
function pastRows_(list, i) {
  if (!PAST_ROWS) PAST_ROWS = {};
  if (!PAST_ROWS[i]) {
    const sheet = sheetById_(SpreadsheetApp.getActiveSpreadsheet(), list[i].id);
    PAST_ROWS[i] = sheet ? readRows_(sheet) : [];
  }
  return PAST_ROWS[i];
}

// 지난 시즌에 다른 선수가 쓰던 닉네임인지 (버전 12. 운영자가 2026-10-08에 "지난 시즌 닉네임도 원래 주인만 쓸 수 있게" 해 달라고 함).
// 이번 시즌 안에서 겹치는 닉네임은 register_ 가 따로 막는다. 여기서는 끝난 시즌들을 본다.
//  - 승인됐던 등록의 닉네임만 묶는다. 등록만 하고 승인되지 않은 닉네임까지 묶으면, 아무나 등록만 해서 남의 닉네임을 잡아 둘 수 있다.
//  - 그 닉네임으로 승인됐던 사람(스팀이나 디스코드가 같은 사람)은 다시 쓸 수 있다. 시즌마다 다른 사람이 썼던 닉네임이면 그들 모두 쓸 수 있다.
//  - 견주는 기준은 이번 시즌과 같다: 공백과 대소문자는 무시한다.
// 떠난 선수의 닉네임을 풀어 주려면, 운영자가 그 시즌 탭에서 그 줄의 닉네임 칸을 고친다.
function nickHeld_(nickname, steam, discord) {
  const list = seasons_(), key = nameKey_(nickname);
  let held = false;
  for (let i = list.length - 2; i >= 0; i--) {
    const users = pastRows_(list, i).filter(r => r.status === '승인' && nameKey_(r.nickname) === key);
    if (users.some(r => sameSteam_(r, steam) || r.discord === discord)) return false;      // 내가 쓰던 닉네임이다
    if (users.length) held = true;
  }
  return held;
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
// 이름 부분에 아무 글자나 들어갈 수 있어서 리그 관리자 화면이나 디스코드 메시지에 그대로 실리면 위험하다.
function normDiscord_(v) {
  const s = String(v == null ? '' : v).trim().replace(/^@/, '').toLowerCase();
  if (/^\d{17,20}$/.test(s)) return s;
  if (/^[a-z0-9_.]{2,32}$/.test(s) && !/\.\./.test(s)) return s;
  if (/#\d{4}$/.test(s))
    fail_('이름#1234 모양은 이제 쓰이지 않습니다. 디스코드 프로필에 보이는 지금 사용자명을 넣어 주세요.', 'discord');
  // 닉네임(표시 이름)을 적어 내는 선수가 많다. 무엇을 넣어야 하는지를 함께 알려 준다
  fail_('디스코드 사용자명을 확인해 주세요. 닉네임이 아니라 디스코드 설정 → 내 계정에 있는 사용자명입니다. 영문 소문자·숫자·밑줄(_)·마침표(.)로만 되어 있습니다.', 'discord');
}

function parseMmr_(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0 || n > MAX_MMR || Math.round(n) !== n) fail_('MMR은 0부터 ' + MAX_MMR + ' 사이의 정수로 넣어 주세요', 'mmr');
  return n;
}

// 최고 MMR(도타 2를 하면서 가장 높았던 MMR)은 리그 관리자가 참고만 하는 값이다. 인하우스 MMR에는 쓰지 않는다.
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
   리그 관리자: 등록 명단
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
      peak: d[COL['최고MMR']].trim() === '' ? null : (Number(String(d[COL['최고MMR']]).replace(/[^\d.]/g, '')) || 0),
      by: d[COL['처리자']].trim(),
      byAt: toIso_(raw[COL['처리시각']])
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
    note: r.note,
    by: r.by,
    byAt: r.byAt
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
    const rows = readRows_(sheet);
    const fresh = [], gone = [];                           // 방금 승인한 줄, 방금 승인을 푼 줄
    const who = ACTOR ? ACTOR.name : '', now = new Date(), logs = [];
    let changed = 0;
    rows.forEach(r => {
      if (!want.has(r.steamKey)) return;
      sheet.getRange(r.rowNumber, COL['상태'] + 1).setValue(status);
      changed++;
      if (r.status !== status) {
        // 누가 바꿨는지 그 줄에 적고(처리자·처리시각), 운영 기록 탭에도 한 줄 남긴다
        sheet.getRange(r.rowNumber, COL['처리자'] + 1, 1, 2).setValues([[text_(who), now]]);
        logs.push([status, r.nickname, r.status + ' → ' + status]);
        if (status === '승인') fresh.push(r);
        else if (r.status === '승인') gone.push(r);
        r.status = status;
        r.by = who;
        r.byAt = now.toISOString();
      }
    });
    logRows_(logs);
    const out = { changed, by: who };
    // 승인이 바뀌었으면 선수단도 맞춘다. 맞추지 못해도 상태는 이미 바뀌었으니 실패로 돌려주지 않고, league.ok 로 알린다
    if (fresh.length || gone.length) out.league = linkPlayers_(rows, fresh, gone);
    return out;
  });
}

/* =========================================================
   승인한 선수를 선수단에 넣기 (버전 10)
   ========================================================= */
// 리그 관리자가 등록을 승인하면 그 선수를 리그 기록의 선수단에 바로 넣는다. 전에는 리그 관리자가 명단 파일을 받아 리그 매니저에 불러와야 했고,
// 그 일을 빠뜨리면 봇이 그 선수를 몰라 팀을 짜지 못했다. 리그 매니저가 명단 파일을 "같은 선수면 갱신"으로 불러올 때와 같은 기준으로 한다.
//  - 같은 선수인지는 디스코드 → 스팀 → 닉네임 순서로 본다. 닉네임이 같아도 디스코드가 서로 다르면 다른 사람이다.
//  - 방금 승인한 선수(fresh): 선수단에 없으면 넣는다. 있으면 닉네임·디스코드·스팀·등록 MMR·지망을 등록한 값으로 맞춘다.
//    경기를 치른 선수의 인하우스 MMR과 전적은 건드리지 않는다.
//  - 그 밖의 승인된 선수: 선수단에 없을 때만 넣는다. 이미 있으면 그대로 두고(매니저에서 고친 값을 덮어쓰지 않으려고) 비어 있는 디스코드·스팀만 채운다.
//    전에 넣지 못했던 선수(드라이브가 잠깐 답하지 않았거나, 매니저가 예전 기록으로 서버를 덮어쓴 경우)가 이때 함께 들어간다.
//  - 방금 승인을 푼 선수(gone): 아직 경기를 치르지 않았으면 선수단에서 뺀다. 경기를 치른 선수는 전적과 경기 기록이 이어지게 남겨 둔다.
// rows 는 지금 시즌의 등록 명단(바뀐 상태까지 반영한 것)이다. 잠금을 잡은 상태에서 부른다.
// 돌려주는 값(선수 이름들): added 방금 승인해 넣은 선수, filled 전부터 승인돼 있었는데 빠져 있어 넣은 선수, updated 방금 승인했는데 이미 있어 정보를 맞춘 선수,
// removed 승인을 풀어 뺀 선수, kept 승인을 풀었지만 경기를 치러 남긴 선수, skipped 닉네임이 없어 넣지 못한 줄. players 는 선수단 인원, rev 는 기록 번호.
// 바뀐 것이 없으면 기록을 다시 쓰지 않는다.
function syncPlayers_(rows, fresh, gone) {
  const out = { added: [], filled: [], updated: [], removed: [], kept: [], skipped: [] };
  const approved = rows.filter(r => r.status === '승인');
  if (!approved.length && !gone.length) return out;         // 넣을 선수도 뺄 선수도 없으면 기록을 읽지도 않는다
  const list = seasons_();
  if (list[list.length - 1].leaguePending)
    fail_('새 시즌의 리그 기록을 아직 준비하지 못했습니다. 잠시 뒤에 다시 해 주세요.', 'pending');

  const league = readLeague_() || { players: [], matches: [], settings: {} };
  const players = league.players;
  const item = p => !!p && typeof p === 'object';
  const games = p => (Number(p.wins) || 0) + (Number(p.losses) || 0);
  const inMatch = {}, taken = {};
  league.matches.forEach(m => { if (m && Array.isArray(m.rows)) m.rows.forEach(x => { if (x && x.id) inMatch[x.id] = true; }); });
  players.forEach(p => { if (item(p)) taken[p.id] = true; });
  const nameUsed = (name, own) => players.some(p => item(p) && p !== own && p.name === name);
  const steamUsed = (key, own) => players.some(p => item(p) && p !== own && steamKeyOf_(p.steam) === key);
  let dirty = false;

  const add = (np, names) => {
    // 다른 사람인데 닉네임이 같으면 뒤에 번호를 붙인다. 매니저는 선수단 안에서 이름이 겹치지 않는다고 보고 움직인다
    const base = np.name;
    for (let k = 2; nameUsed(np.name, null); k++) np.name = base + ' (' + k + ')';
    np.id = newPlayerId_(taken);
    players.push(np);
    names.push(np.name);
    dirty = true;
  };

  gone.forEach(r => {
    const np = playerFromRow_(r);
    // 빼는 일은 넣는 일보다 조심스럽게: 디스코드나 스팀이 같은 선수만 찾고, 이름으로는 둘 다 적혀 있지 않은 선수만 찾는다
    const old = players.filter(item).filter(p => rowIsPlayer_(np, p))[0];
    if (!old) return;
    if (games(old) > 0 || inMatch[old.id]) { out.kept.push(old.name); return; }
    players.splice(players.indexOf(old), 1);
    out.removed.push(old.name);
    dirty = true;
  });

  const justApproved = {};
  fresh.forEach(r => { justApproved[r.rowNumber] = true; });
  approved.forEach(r => {
    const np = playerFromRow_(r);
    if (!np.name) { out.skipped.push(r.discord || r.steamKey || (r.rowNumber + '번째 줄')); return; }   // 시트에서 닉네임을 지운 줄. 이름 없는 선수는 매니저가 받지 않는다
    const old = samePlayer_(players.filter(item), np);
    if (!old) { add(np, justApproved[r.rowNumber] ? out.added : out.filled); return; }
    const before = JSON.stringify(old);
    const sk = steamKeyOf_(np.steam);
    if (justApproved[r.rowNumber]) {
      if (np.name !== old.name && !nameUsed(np.name, old)) old.name = np.name;
      if (np.discord) old.discord = np.discord;
      if (np.steam && !steamUsed(sk, old)) old.steam = np.steam;
      old.baseMMR = np.baseMMR;
      if (games(old) === 0) old.mmr = np.baseMMR;            // 경기를 치른 선수의 인하우스 MMR은 되돌리지 않는다
      old.prefs = np.prefs;
    } else {
      if (np.discord && !discordKey_(old.discord)) old.discord = np.discord;
      if (np.steam && !steamKeyOf_(old.steam) && !steamUsed(sk, old)) old.steam = np.steam;
    }
    if (JSON.stringify(old) !== before) { if (justApproved[r.rowNumber]) out.updated.push(old.name); dirty = true; }
  });

  if (dirty) storeLeague_(league, leagueText_(league), sanitizeRecords_(league));
  out.players = players.filter(item).length;
  out.rev = leagueRev_();
  return out;
}

// 상태를 바꾼 뒤(또는 서버를 올린 뒤 처음, 봇이 팀을 짜기 전)에 선수단을 맞춘다. 여기서는 실패해도 멈추지 않는다:
// 이미 바꾼 승인 상태는 그대로 두고, 무슨 일이 있었는지만 돌려준다. 잠금을 잡은 상태에서 부른다
function linkPlayers_(rows, fresh, gone) {
  try {
    return Object.assign({ ok: true }, syncPlayers_(rows, fresh, gone));
  } catch (err) {
    if (err && err.userFacing) return { ok: false, error: err.message, code: err.code || '' };
    console.error('선수단을 맞추지 못했습니다: ' + (err && err.stack || err));
    return { ok: false, error: '서버의 리그 기록을 읽거나 쓰지 못했습니다.', code: '' };
  }
}

// 리그 관리자 페이지의 "선수단 다시 맞추기": 승인돼 있는데 선수단에 없는 선수를 모두 넣는다. 이미 있는 선수는 건드리지 않는다
function syncNow_() {
  return withLock_(() => ({ league: linkPlayers_(readRows_(getSheet_()), [], []) }));
}

// 등록한 줄을 선수단의 선수 모양으로 바꾼다. 리그 매니저가 새 선수를 만들 때(newPlayer)와 같은 칸, 같은 순서다.
// 매니저는 서버에서 받은 기록의 모양이 하나라도 어긋나면 통째로 받지 않으므로(backupProblem), 값의 모양을 여기서 맞춰 둔다
function playerFromRow_(r) {
  const mmr = Math.max(0, Math.min(MAX_MMR, Math.round(Number(r.mmr) || 0)));
  const prefs = [];
  (Array.isArray(r.prefs) ? r.prefs : []).concat([1, 2, 3, 4]).forEach(v => {     // 읽지 못한 지망은 남은 번호 순으로 뒤에 채운다
    if (Number.isInteger(v) && v >= 1 && v <= 4 && prefs.indexOf(v) < 0) prefs.push(v);
  });
  const id64 = String(r.steamKey || '').match(/^s:(7656\d{13})$/);
  return {
    id: '',
    name: String(r.nickname || '').trim().slice(0, 40),
    baseMMR: mmr,
    mmr: mmr,
    prefs: prefs,
    wins: 0, losses: 0, streak: 0, roleCount: [0, 0, 0, 0, 0],
    discord: discordKey_(r.discord),
    steam: String(r.steamUrl || (id64 ? 'https://steamcommunity.com/profiles/' + id64[1] : '')).trim().slice(0, 200)
  };
}

// 선수단에서 이 등록과 같은 선수를 찾는다. 리그 매니저의 명단 불러오기(sameAs)와 같은 순서다
function samePlayer_(players, np) {
  if (np.discord) {
    const a = players.filter(p => discordKey_(p.discord) === np.discord)[0];
    if (a) return a;
  }
  const sk = steamKeyOf_(np.steam);
  if (sk) {
    const b = players.filter(p => steamKeyOf_(p.steam) === sk)[0];
    if (b) return b;
  }
  const c = players.filter(p => p.name === np.name)[0];
  return c && !(np.discord && discordKey_(c.discord) && discordKey_(c.discord) !== np.discord) ? c : null;   // 이름은 같아도 디스코드가 다르면 다른 사람
}

// 등록 줄(playerFromRow_ 로 바꾼 np)과 선수단의 선수 p 가 틀림없이 같은 사람인지. 선수단에서 빼거나 시즌을 넘길 때처럼 조심해야 하는 곳에서 쓴다:
// 디스코드나 스팀이 같으면 같은 사람이고, 이름으로는 디스코드와 스팀이 모두 적혀 있지 않은 선수만 맞춘다
function rowIsPlayer_(np, p) {
  const sk = steamKeyOf_(np.steam);
  return !!((np.discord && discordKey_(p.discord) === np.discord) || (sk && steamKeyOf_(p.steam) === sk) ||
    (np.name && p.name === np.name && !discordKey_(p.discord) && !steamKeyOf_(p.steam)));
}

/* =========================================================
   포지션 순서 바꾸기 (버전 14)
   ========================================================= */
// 선수가 디스코드에서 봇의 /포지션변경 으로 자기 포지션 순서를 바꾼다(운영자가 2026-10-11에 요청).
// 봇이 그 사람의 디스코드 계정(숫자 ID와 사용자명)을 discord 에 실어 보내고, 그 계정으로 등록한 줄을 찾는다.
// 등록 탭의 지망 칸과 리그 기록의 선수(prefs)를 함께 고친다. 한쪽만 고치면 승인을 풀었다 다시 승인할 때 예전 순서로 돌아간다.
//  - 제외된 등록은 고치지 않는다. 대기 중인 등록은 등록 탭만 고친다(아직 선수단에 없다).
//  - 리그 기록을 먼저 고친다. 거기서 실패하면 아무것도 바꾸지 않고 멈춰서, 다시 입력하면 된다.
function setPrefs_(body) {
  const prefs = parsePrefs_(body.prefs);
  const ids = (Array.isArray(body.discord) ? body.discord : [body.discord]).map(discordKey_).filter(Boolean).slice(0, 4);
  if (!ids.length) fail_('디스코드 계정이 없습니다', 'discord');
  return withLock_(() => {
    const sheet = getSheet_();
    const mine = readRows_(sheet).filter(r => r.discord && ids.indexOf(r.discord) >= 0);
    const row = mine.filter(r => r.status === '승인')[0] || mine.filter(r => r.status === '대기')[0] || mine[0];
    if (!row) fail_('이 디스코드 계정으로 등록한 선수를 찾지 못했습니다.', 'unknown');
    if (row.status === '제외') fail_('제외된 등록이라 포지션 순서를 바꿀 수 없습니다.', 'locked');

    let inLeague = false;
    if (row.status === '승인') {
      const list = seasons_();
      if (list[list.length - 1].leaguePending)
        fail_('새 시즌의 리그 기록을 아직 준비하지 못했습니다. 잠시 뒤에 다시 해 주세요.', 'pending');
      let league;
      try { league = readLeague_(); }
      catch (err) {
        console.error('포지션 순서: 리그 기록을 읽지 못했습니다: ' + (err && err.stack || err));
        fail_('서버의 리그 기록을 읽지 못해 바꾸지 못했습니다. 잠시 뒤에 다시 해 주세요.', 'league');
      }
      const np = playerFromRow_(row);
      const p = league ? league.players.filter(q => q && typeof q === 'object' && rowIsPlayer_(np, q))[0] : null;
      // 선수단에 아직 없는 선수는 등록 탭만 고친다. 다음에 선수단을 맞출 때 그 순서로 들어간다
      if (p) {
        inLeague = true;
        if (JSON.stringify(p.prefs) !== JSON.stringify(prefs)) {
          p.prefs = prefs.slice();
          storeLeague_(league, leagueText_(league), sanitizeRecords_(league));
        }
      }
    }
    sheet.getRange(row.rowNumber, COL['1지망'] + 1, 1, 4).setValues([prefs.map(n => PREF_LABELS[n - 1])]);
    sheet.getRange(row.rowNumber, COL['수정시각'] + 1).setValue(new Date());
    return { nickname: row.nickname, status: row.status, prefs, was: row.prefs, inLeague, rev: leagueRev_() };
  });
}

// 리그 매니저의 normDiscordId 와 같다: 앞의 @와 대소문자 차이는 같은 사람으로 본다
function discordKey_(v) {
  return String(v == null ? '' : v).trim().replace(/^@/, '').toLowerCase().slice(0, 40);
}

// 리그 매니저의 steamKeyOf 와 같다: 스팀 프로필 주소에서 같은 계정을 가리키는 키를 뽑는다
function steamKeyOf_(v) {
  const t = String(v == null ? '' : v).trim();
  if (!t) return '';
  let m = t.match(/steamcommunity\.com\/profiles\/(\d{17})/i) || t.match(/^(7656\d{13})$/);
  if (m) return 's:' + m[1];
  m = t.match(/steamcommunity\.com\/id\/([A-Za-z0-9_-]+)/i);
  if (m) return 'id:' + m[1].toLowerCase();
  return 'x:' + t.toLowerCase();
}

// 새 선수의 ID. 매니저가 만드는 ID(p + 시각 + 순번)와 같은 영숫자 모양이고, 선수단 안에서 겹치지 않게 한다.
// 스팀 번호 같은 개인 정보로 만들지 않는다: 선수 ID는 공개 기록에도 실린다
function newPlayerId_(taken) {
  for (let n = 0; ; n++) {
    const id = 'ps' + Date.now().toString(36) + n.toString(36);
    if (!taken[id]) { taken[id] = true; return id; }
  }
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
// 공개 기록과 달리 거르지 않고 드라이브의 비공개 파일에 그대로 두며, 리그 관리자 키가 있어야만 돌려준다.
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
    // 몇 번을 해도 읽지 못하면 파일이 지워진 것으로 보고 없는 것으로 돌려준다(그러면 리그 매니저가 자기 기록을 다시 올려 되살릴 수 있다).
    // 드라이브가 잠깐 답하지 않은 것을 "없다"로 돌려주면 매니저가 뒤처진 기록으로 서버를 덮어쓸 수 있어서, readFile_ 이 먼저 몇 번 다시 읽어 본다
    try { text = readFile_(id); } catch (err) { console.warn('리그 기록 파일을 읽지 못해 없는 것으로 돌려줍니다: ' + err); }
  }
  return { league: text ? JSON.parse(text) : null, rev, leagueAt: text ? (props.getProperty('LEAGUE_AT') || '') : '' };
}

// 서버가 직접 고치려고 읽는 리그 기록. 한 번도 올라온 적이 없으면 null 이다.
// getLeague_ 와 달리, 있어야 할 기록을 읽지 못하면 없는 것으로 치지 않고 멈춘다(오류를 낸다).
// 드라이브가 잠깐 답하지 않은 것을 "기록이 없다"로 알고 새로 써 버리면 선수와 경기가 통째로 사라지기 때문이다.
function readLeague_() {
  const id = PropertiesService.getScriptProperties().getProperty('LEAGUE_FILE_ID');
  if (!leagueRev_() || !id) return null;
  const league = JSON.parse(readFile_(id));
  if (!league || typeof league !== 'object' || !Array.isArray(league.players) || !Array.isArray(league.matches))
    throw new Error('리그 기록의 모양이 다릅니다');
  return league;
}

// 드라이브 파일의 글을 읽는다. 드라이브는 가끔 잠깐 답하지 않으므로 몇 번 다시 읽어 본 뒤에야 못 읽은 것으로 친다(오류를 낸다).
// 휴지통에 있으면 도로 꺼낸다(alive_)
function readFile_(id) {
  let last = null;
  for (let n = 0; n < DRIVE_TRIES; n++) {
    if (n) Utilities.sleep(400 * n);
    try { return alive_(DriveApp.getFileById(id)).getBlob().getDataAsString('UTF-8') || ''; }
    catch (err) { last = err; }
  }
  throw last;
}

// 리그 기록을 받아 원본으로 둔다. 받은 기록으로 공개 기록(순위 페이지)과 시트의 순위·경기 기록 탭도 다시 쓴다.
function saveLeague_(body) {
  const text = leagueText_(body.league);
  const league = JSON.parse(text);
  const clean = sanitizeRecords_(league);
  const base = Number(body.baseRev) || 0;
  return withLock_(() => {
    const rev = leagueRev_();
    if (base !== rev && body.force !== true)
      fail_('서버에 더 새로운 기록이 있습니다. 서버 기록을 먼저 불러와 주세요.', 'conflict');
    // 서버의 더 새로운 기록을 일부러 덮어쓴 경우는 남겨 둔다 (매니저의 "이 기록으로 서버 덮어쓰기")
    if (base !== rev) log_('리그 기록 덮어쓰기', '', '선수 ' + clean.players.length + '명, 경기 ' + clean.matches.length + '판으로 덮어씀');
    return storeLeague_(league, text, clean);
  });
}

// 리그 기록을 원본으로 쓰고 번호를 하나 올린다. 공개 기록과 시트의 순위·경기 기록 탭도 이 기록으로 다시 쓴다.
// text 는 leagueText_ 로 만든 글, clean 은 sanitizeRecords_ 로 거른 공개 기록이다. 잠금을 잡은 상태에서 부른다
function storeLeague_(league, text, clean) {
  const props = PropertiesService.getScriptProperties();
  const rev = leagueRev_();
  const out = writePublic_(clean);
  driveFile_('LEAGUE_FILE_ID', '인하우스_리그기록.json').setContent(text);
  props.setProperty('LEAGUE_AT', out.publishedAt);
  props.setProperty('LEAGUE_REV', String(rev + 1));
  writeMirror_(league);
  return Object.assign(out, { rev: rev + 1 });
}

/* ---- 시트의 순위·경기 기록 탭 ----
   리그 관리자가 시트에서 바로 볼 수 있게, 리그 기록이 바뀔 때마다 두 탭을 통째로 다시 쓴다. 원본은 위의 리그 기록이고 이 탭은 보기용이다.
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

// 순위 페이지가 읽는 공개 기록. 캐시 → 공개 기록 파일 → (파일을 읽지 못하면) 리그 기록의 원본에서 다시 걸러 낸 것.
// 전에는 파일을 읽지 못하면 빈 파일을 새로 만들어 돌려줬다. 드라이브가 잠깐 답하지 않았을 뿐인데 순위 페이지가 텅 비고,
// 그 빈 기록이 캐시에 남아 다음 경기가 기록될 때까지 그대로 보였다.
function publicRecords_() {
  const cached = CacheService.getScriptCache().get('records');
  if (cached) return JSON.parse(cached);
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('RECORDS_FILE_ID');
  let data = null;
  if (!id) data = { players: [], matches: [] };            // 아직 한 번도 쓴 적이 없다
  else {
    try { const text = readFile_(id); data = text ? JSON.parse(text) : { players: [], matches: [] }; }
    catch (err) { console.warn('공개 기록 파일을 읽지 못했습니다. 리그 기록에서 다시 만듭니다: ' + err); }
  }
  if (!data) {
    const league = readLeague_();                          // 이것도 읽지 못하면 오류로 답한다(순위 페이지는 보고 있던 기록을 그대로 둔다)
    if (!league) throw new Error('공개 기록을 읽지 못했습니다');
    data = sanitizeRecords_(league);
    data.publishedAt = props.getProperty('LEAGUE_AT') || '';
  }
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
