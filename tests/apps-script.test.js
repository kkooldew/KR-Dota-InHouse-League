const makeEnv = require('./gas-harness');
const { env, grid, props, cache, steam, sheets } = makeEnv();
const post = body => JSON.parse(env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
const get = action => JSON.parse(env.doGet({ parameter: action ? { action } : {} }).text);
const assert = (c, m) => { if(!c){ console.log('FAIL', m); process.exitCode = 1; } else console.log('ok  ', m); };
const clearRL = () => Object.keys(cache).filter(k => k.startsWith('rl:')).forEach(k => delete cache[k]);
const clearSteam = () => Object.keys(cache).filter(k => k.startsWith('steam:')).forEach(k => delete cache[k]);
steam.vanity.myvanity = '76561198000000777';
steam.missing.add('76561198000000404');

env.setup();
const key = props.ADMIN_KEY;
assert(key && key.length >= 32, 'setup creates admin key');
assert(grid[0][3] === '닉네임', 'header row created');
// 버전 5까지의 시트(선수등록 탭 하나)에서 올라온 경우: 그 탭이 지금 시즌의 탭이 되고 이름에 시즌이 붙는다
assert(sheets['선수등록 (시즌 1)'] && sheets['선수등록 (시즌 1)'].grid === grid && !('선수등록' in sheets) && grid[0][12] === '비고',
  'upgrade: the old registration tab becomes the current season tab');

const base = { action:'register', nickname:'불멸의소환사', steam:'steamcommunity.com/profiles/76561197990650432/', discord:'@ZZKim', mmr:'6100', prefs:[2,1,3,4] };
let r = post(base);
assert(r.ok && r.updated === false, 'new registration');
assert(grid[1][5] === 's:76561197990650432' && grid[1][6] === 'zzkim' && grid[1][2] === '대기', 'row stored with normalized keys');
assert(grid[1][8] === '미드' && grid[1][11] === '서폿', 'prefs stored as labels');

r = post(base); assert(!r.ok && r.code === 'rate', 'rate limit blocks immediate resubmit');
clearRL();
r = post({ ...base, mmr: 6300, nickname: '불멸의소환사2' });
assert(r.ok && r.updated === true && grid[1][7] === 6300 && grid[1][3] === '불멸의소환사2' && grid.length === 2, 'same steam+discord updates row');

clearRL();
r = post({ ...base, discord: 'other_user' });
assert(!r.ok && r.code === 'conflict', 'same steam with other discord rejected');

clearRL();
r = post({ ...base, steam: 'https://steamcommunity.com/id/MyVanity', nickname: '새사람' });
assert(!r.ok && r.code === 'conflict', 'same discord with other steam rejected');

clearRL();
r = post({ ...base, steam: 'https://steamcommunity.com/id/MyVanity', discord: '123456789012345678', nickname: '불멸의 소환사2' });
assert(!r.ok && r.code === 'nickname', 'nickname collision (spaces/case-insensitive) rejected');

clearRL();
r = post({ ...base, steam: 'https://steamcommunity.com/id/MyVanity', discord: '123456789012345678', nickname: '=HYPERLINK("x")' });
assert(r.ok, 'numeric discord + vanity steam accepted');
assert(grid[2][6] === '123456789012345678' && typeof grid[2][6] === 'string', 'numeric discord kept as text (no rounding)');
assert(grid[2][3] === '=HYPERLINK("x")' && grid[2][5] === 's:76561198000000777' && grid[2][4] === 'https://steamcommunity.com/profiles/76561198000000777',
  'formula-like nickname stored as text, vanity address stored as numeric steam id');

clearRL();
r = post({ ...base, steam: 'steamcommunity.com/profiles/76561198000000777', discord: '123456789012345678', nickname: '=HYPERLINK("x")', mmr: 4100 });
assert(r.ok && r.updated === true && grid.length === 3 && grid[2][7] === 4100, 'numeric and vanity address of one account are the same registration');
clearRL();
const callsBefore = steam.calls;
r = post({ ...base, steam: 'https://steamcommunity.com/id/MyVanity', discord: '123456789012345678', nickname: '=HYPERLINK("x")', mmr: 4100 });
assert(r.ok && steam.calls === callsBefore, 'steam lookup is cached for repeated submits');

const bad = [
  [{ steam: 'https://store.steampowered.com/app/570' }, 'steam'],
  [{ steam: 'https://steamcommunity.com/id/NoSuchName' }, 'steam'],
  [{ steam: 'https://steamcommunity.com/profiles/76561198000000404' }, 'steam'],
  [{ discord: 'a' }, 'discord'],
  [{ discord: 'has space' }, 'discord'],
  [{ mmr: '-5' }, 'mmr'], [{ mmr: '20000' }, 'mmr'], [{ mmr: '45.5' }, 'mmr'],
  [{ prefs: [1,1,2,3] }, 'prefs'], [{ prefs: [1,2,3] }, 'prefs'],
  [{ nickname: '   ' }, 'nickname'], [{ nickname: 'x'.repeat(21) }, 'nickname'],
];
bad.forEach(([patch, code]) => { clearRL(); const res = post({ ...base, steam:'https://steamcommunity.com/profiles/76561198000000001', discord:'fresh_user', nickname:'신규', ...patch }); assert(!res.ok && res.code === code, 'invalid ' + code + ' ' + JSON.stringify(patch)); });

clearRL();
r = post({ ...base, website: 'spam' }); assert(r.ok && grid.length === 3, 'honeypot pretends success, writes nothing');

r = post({ action:'adminList', key:'wrong' }); assert(!r.ok && r.code === 'auth', 'admin list needs key');
r = post({ action:'adminList', key });
assert(r.ok && r.players.length === 2 && r.players[0].prefs.join() === '2,1,3,4' && r.players[1].discord === '123456789012345678', 'admin list returns parsed rows');

r = post({ action:'adminSetStatus', key, steamKeys:['s:76561197990650432','s:76561198000000777'], status:'승인' });
assert(r.ok && r.changed === 2 && grid[1][2] === '승인' && grid[2][2] === '승인', 'bulk approve');
clearRL();
r = post({ ...base, mmr: 6400, nickname: '불멸의소환사2' });
assert(!r.ok && r.code === 'locked' && grid[1][7] === 6300 && grid[1][2] === '승인', 'approved registration cannot be edited by the player');
r = post({ ...base, mmr: 6400, nickname: '불멸의소환사2', discord: 'other_user' });
assert(!r.ok && r.code === 'conflict', 'someone else still gets the conflict message, not the lock message');
post({ action:'adminSetStatus', key, steamKey:'s:76561197990650432', status:'대기' });
clearRL();
r = post({ ...base, mmr: 6400, nickname: '불멸의소환사2' });
assert(r.ok && r.updated === true && grid[1][7] === 6400 && grid[1][2] === '대기', 'set back to waiting: the player can edit again');
post({ action:'adminSetStatus', key, steamKey:'s:76561197990650432', status:'제외' });
clearRL();
r = post({ ...base, mmr: 100, nickname: '불멸의소환사2' });
assert(!r.ok && r.code === 'locked' && grid[1][7] === 6400, 'excluded registration is locked too');
post({ action:'adminSetStatus', key, steamKey:'s:76561197990650432', status:'승인' });

r = post({ action:'adminConfig', key, open:false, season:'시즌 2' });
assert(r.ok && r.open === false && r.season === '시즌 2', 'close registration');
clearRL();
r = post({ ...base }); assert(!r.ok && r.code === 'closed', 'registration closed rejects');
r = get('status'); assert(r.ok && r.open === false && r.registered === 2 && r.version >= 2, 'public status');
assert(sheets['선수등록 (시즌 2)'] && sheets['선수등록 (시즌 2)'].grid === grid && r.season === '시즌 2' && r.returning === false && !('pastSeasons' in r),
  'renaming the season keeps the roster and renames its tab');

const records = { players:[{ id:'p1', name:'A', baseMMR:5000, mmr:5100, prefs:[1,2,3,4], wins:1, losses:0, streak:1, roleCount:[1,0,0,0,0], discord:'secret', steam:'secret' }],
  matches:[{ id:'m1', at:'2026-10-05T08:12:12.491Z', winner:'r', rule:{k:200}, rows:[{ id:'p1', name:'A', side:'r', role:1, rank:0, before:5000, delta:100, extra:'x' }] }], settings:{k:200} };
r = post({ action:'publishRecords', key:'nope', records }); assert(!r.ok, 'publish needs key');
r = post({ action:'publishRecords', key, records }); assert(r.ok && r.players === 1 && r.matches === 1, 'publish records');
r = get('records');
const txt = JSON.stringify(r.records);
assert(r.ok && !txt.includes('secret') && !txt.includes('extra') && !('settings' in r.records) && r.records.players[0].mmr === 5100, 'public records sanitized');
delete cache.records; r = get('records'); assert(r.ok && r.records.matches.length === 1, 'records read back from drive file when cache is empty');

r = post({ action:'pushRoster', key, roster:{ entries:[{ id:'<@123456789012345678>', username:'zzkim', name:'김' }, { id:'', username:'x' }] } });
assert(r.ok && r.count === 1, 'push roster keeps valid entries');
r = post({ action:'adminRoster', key }); assert(r.ok && r.roster.entries[0].id === '123456789012345678', 'admin roster');

// 리그 기록의 원본은 서버에 둔다. 번호(rev)가 맞아야만 받아서, 매니저와 봇이 서로의 변경을 덮어쓰지 않게 한다
r = post({ action:'adminLeague', key }); assert(r.ok && r.league === null && r.rev === 0 && r.leagueAt === '', 'no league yet');
r = post({ action:'adminLeagueRev', key }); assert(r.ok && r.rev === 0, 'rev starts at 0');
const league = { players: records.players, matches: records.matches, settings: { balanceTol: 500 }, junk: 'dropped' };
r = post({ action:'saveLeague', key: 'nope', league, baseRev: 0 }); assert(!r.ok && r.code === 'auth', 'saving the league needs key');
r = post({ action:'adminLeagueRev', key: 'nope' }); assert(!r.ok && r.code === 'auth', 'league rev needs key');
r = post({ action:'saveLeague', key, league, baseRev: 0 });
assert(r.ok && r.rev === 1 && r.players === 1 && r.matches === 1, 'first save becomes rev 1');
r = post({ action:'adminLeague', key: 'nope' }); assert(!r.ok && r.code === 'auth', 'league needs key');
r = post({ action:'adminLeague', key });
assert(r.ok && r.rev === 1 && r.league.players[0].discord === 'secret' && r.league.settings.balanceTol === 500 && r.league.matches[0].rule.k === 200 && !('junk' in r.league) && r.leagueAt,
  'league is kept whole (discord and settings included)');
delete cache.records;
assert(!JSON.stringify(get('records').records).includes('secret') && get('records').records.players[0].mmr === 5100, 'public records are derived from the league and stay sanitized');

const grown = { ...league, players: [{ ...records.players[0], mmr: 5200 }] };
r = post({ action:'saveLeague', key, league: grown, baseRev: 0 });
assert(!r.ok && r.code === 'conflict' && post({ action:'adminLeagueRev', key }).rev === 1 && post({ action:'adminLeague', key }).league.players[0].mmr === 5100,
  'save based on an older rev is refused and changes nothing');
r = post({ action:'saveLeague', key, league: grown, baseRev: 1 });
assert(r.ok && r.rev === 2 && get('records').records.players[0].mmr === 5200, 'save based on the current rev is accepted; ranking page follows');
r = post({ action:'saveLeague', key, league, baseRev: 0, force: true });
assert(r.ok && r.rev === 3 && post({ action:'adminLeague', key }).league.players[0].mmr === 5100, 'forced save overwrites');
r = post({ action:'saveLeague', key, league: { players: 'x' }, baseRev: 3 });
assert(!r.ok && post({ action:'adminLeagueRev', key }).rev === 3, 'broken league is refused');
r = post({ action:'publishRecords', key, records });
assert(!r.ok && r.code === 'outdated', 'old managers can no longer overwrite the ranking page once the server owns the league');

// 시트의 순위·경기 기록 탭 (보기용)
const row = (id, side, role, before, delta) => ({ id, name: id.toUpperCase(), side, role, rank: 0, before, delta });
const three = {
  players: [
    { id:'a', name:'=HYPERLINK("x")', baseMMR:3000, mmr:3120, prefs:[2,1,3,4], wins:2, losses:0, streak:2, roleCount:[0,2,0,0,0], discord:'123456789012345678', steam:'' },
    { id:'b', name:'나', baseMMR:4000, mmr:3880, prefs:[1,2,3,4], wins:0, losses:2, streak:-2, roleCount:[2,0,0,0,0], discord:'b_user', steam:'' },
    { id:'c', name:'다', baseMMR:3500, mmr:3500, prefs:[4,3,2,1], wins:0, losses:0, streak:0, roleCount:[0,0,0,0,0], discord:'', steam:'' },
    { id:'d', name:'라', baseMMR:3300, mmr:3420, prefs:[3,4,1,2], wins:2, losses:0, streak:2, roleCount:[0,0,2,0,0], discord:'', steam:'' }
  ],
  matches: [
    { id:'m2', at:'2026-10-06T13:30:00.000Z', winner:'d', rule:{k:200}, rows:[row('b', 'r', 1, 3940, -60), row('a', 'd', 2, 3060, 60), row('d', 'd', 1, 3360, 60)] },
    { id:'m1', at:'2026-10-05T15:10:00.000Z', winner:'r', rule:{k:200}, rows:[row('a', 'r', 2, 3000, 60), row('b', 'd', 1, 4000, -60)] }
  ],
  settings: {}
};
r = post({ action:'saveLeague', key, league: three, baseRev: 3 });
const rank = sheets['순위'].grid, log = sheets['경기 기록'].grid;
assert(r.ok && rank[0][0].startsWith('이 탭은') && rank[1].slice(0, 9).join() === '순위,닉네임,인하우스 MMR,시작 MMR,변동,승,패,승률,연속', 'ranking tab: notice and headers');
// 승패가 같은 두 선수는 공동 1위이고, 그 안에서는 MMR이 높은 쪽이 위에 온다 (순위 페이지와 같은 순서)
assert(rank.length === 6 && rank[2].slice(0, 9).join('|') === '1|라|3420|3300|120|2|0|100%|2연승' &&
  rank[3].slice(0, 9).join('|') === '1|=HYPERLINK("x")|3120|3000|120|2|0|100%|2연승', 'ranking tab: leaders share rank 1, formula-like name kept as text');
assert(rank[4].slice(0, 9).join('|') === '3|나|3880|4000|-120|0|2|0%|2연패' && rank[5][0] === '-' && rank[5][1] === '다' && rank[5][7] === '-',
  'ranking tab: rank after a tie skips ahead, players without games have none');
assert(rank[3].slice(9, 13).join() === '미드,캐리,오프,서폿' && rank[3].slice(13, 18).join() === '0,2,0,0,0' && rank[3][18] === '123456789012345678' && typeof rank[3][18] === 'string',
  'ranking tab: preferences, role counts, discord id kept as text');
assert(log[1].join() === '경기 시각,경기,이긴 팀,진영,자리,닉네임,결과,이전 MMR,변동,이후 MMR' && log.length === 7, 'match tab: headers and one line per player');
assert(log[2].join('|') === '2026-10-06 22:30|2|다이어|래디언트|1번 캐리|B|패|3940|-60|3880' && log[3][4] === '1번 캐리' && log[3][3] === '다이어' && log[4][4] === '2번 미드' && log[4][6] === '승',
  'match tab: newest first, radiant before dire, Korean time');
assert(log[5].slice(0, 3).join('|') === '2026-10-06 00:10|1|래디언트' && log[6][9] === 3940, 'match tab: older match below');
assert(sheets['순위'].warnOnly === true && sheets['경기 기록'].warnOnly === true, 'mirror tabs warn before manual edits');
r = post({ action:'saveLeague', key, league: { ...three, players: three.players.slice(0, 1), matches: [] }, baseRev: 4 });
assert(r.ok && sheets['순위'].grid.length === 3 && sheets['경기 기록'].grid.length === 2, 'mirror tabs are rewritten whole (old rows do not linger)');
sheets['순위'].clearContents = () => { throw new Error('시트 오류'); };
r = post({ action:'saveLeague', key, league: three, baseRev: 5 });
assert(r.ok && r.rev === 6 && post({ action:'adminLeague', key }).league.players.length === 4, 'a failing mirror tab does not fail the save');
assert(grid[0][3] === '닉네임' && grid.length >= 3, 'registration tab is untouched by the mirror tabs');

const lanes = [1, 2, 3, 4, 5].map(role => ({ role, r: 'r' + role, d: 'd' + role, extra: 'x' }));
r = post({ action:'adminLineup', key }); assert(r.ok && r.lineup === null, 'no lineup yet');
r = post({ action:'pushLineup', key: 'nope', lineup: { lanes } }); assert(!r.ok && r.code === 'auth', 'lineup needs key');
r = post({ action:'pushLineup', key, lineup: { lanes, bench: ['b1', '', 'b2'], post: 'https://discord.com/channels/1/2/3' } });
assert(r.ok && r.at, 'push lineup');
r = post({ action:'adminLineup', key });
assert(r.ok && r.lineup.lanes.length === 5 && r.lineup.lanes[2].r === 'r3' && r.lineup.lanes[4].d === 'd5' && !('extra' in r.lineup.lanes[0]) &&
  r.lineup.bench.join() === 'b1,b2' && r.lineup.post.endsWith('/3'), 'lineup read back');
[{ lanes: lanes.slice(0, 4) }, { lanes: lanes.map(l => ({ ...l, d: 'same' })) }, { lanes: lanes.slice().reverse() }, {}].forEach((bad, i) => {
  r = post({ action:'pushLineup', key, lineup: bad }); assert(!r.ok, 'bad lineup rejected #' + (i + 1));
});
assert(post({ action:'adminLineup', key }).lineup.lanes[0].r === 'r1', 'bad lineups leave the stored one alone');
r = post({ action:'pushLineup', key, lineup: null });
assert(r.ok && r.cleared && post({ action:'adminLineup', key }).lineup === null, 'lineup cleared');

r = post({ action:'unknown' }); assert(!r.ok, 'unknown action');
r = JSON.parse(env.doPost({ postData:{ contents:'not json' } }).text); assert(!r.ok, 'bad body');

// 스팀이 답하지 않을 때
post({ action:'adminConfig', key, open:true });
steam.down = true; clearSteam(); clearRL();
r = post({ ...base, steam:'https://steamcommunity.com/id/SomeName', discord:'down_user', nickname:'점검중' });
assert(!r.ok && r.code === 'steam' && grid.length === 3, 'steam not answering: vanity address is asked to retry');
r = post({ ...base, steam:'https://steamcommunity.com/profiles/76561198000000555', discord:'down_user', nickname:'점검중' });
assert(r.ok && grid.length === 4 && grid[3][5] === 's:76561198000000555', 'steam not answering: numeric address is still accepted');
steam.down = false;

// 스팀이 몇 번 거절하다가 답할 때 (실제 배포에서 자주 있다)
steam.vanity.flakyname = '76561198000000666';
clearSteam(); clearRL(); steam.flaky = 3;
let before = steam.calls;
r = post({ ...base, steam:'https://steamcommunity.com/id/FlakyName', discord:'down_user', nickname:'점검중' });
assert(!r.ok && r.code === 'conflict' && steam.calls === before + 4 && steam.flaky === 0, 'steam refusing three times: the fourth try gets the answer');
clearSteam(); clearRL(); steam.flaky = 4; before = steam.calls;
r = post({ ...base, steam:'https://steamcommunity.com/id/FlakyName', discord:'down_user', nickname:'점검중' });
assert(!r.ok && r.code === 'steam' && steam.calls === before + 4, 'steam refusing four times: gives up and asks to retry');
steam.flaky = 0;

// 예전 방식(사용자 지정 주소가 키)으로 저장된 줄
const oldRow = (nick, vanity, discord) => [new Date(), new Date(), '대기', nick, 'https://steamcommunity.com/id/' + vanity, 'id:' + vanity.toLowerCase(), discord, 3000, '캐리', '미드', '오프', '서폿'];
grid.push(oldRow('옛주소', 'OldName', 'old_user'), oldRow('사라진주소', 'Gone', 'gone_user'), oldRow('느긋한사람', 'Lazy', 'lazy_user'), oldRow('겹친사람', 'Dupe', 'dupe_user'));
Object.assign(steam.vanity, { oldname: '76561198000000888', lazy: '76561198000000999', dupe: '76561197990650432' });
clearRL(); clearSteam();
r = post({ ...base, steam:'steamcommunity.com/id/Lazy', discord:'lazy_user', nickname:'느긋한사람', mmr: 3100 });
assert(r.ok && r.updated === true && grid.length === 8 && grid[6][5] === 's:76561198000000999' && grid[6][7] === 3100, 'old vanity row is recognized and upgraded on resubmit');
env._logs.length = 0;
env.setup();
assert(grid[4][5] === 's:76561198000000888' && grid[4][4] === 'https://steamcommunity.com/profiles/76561198000000888', 'setup converts old vanity keys to numeric ids');
assert(grid[5][5] === 'id:gone' && env._logs.some(l => l.includes('찾지 못해') && l.includes('사라진주소')), 'unresolvable old key is kept and reported');
assert(env._logs.some(l => l.includes('같은 스팀 계정') && l.includes('겹친사람')), 'duplicate account after conversion is reported');
assert(props.ADMIN_KEY === key, 'running setup again keeps the admin key');

// ── 시즌별 등록 탭과 지난 시즌 선수의 간편 등록 (새로 설치한 시트에서 시작) ──
(() => {
  const S = makeEnv({ fresh: true });
  const post = body => JSON.parse(S.env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
  const status = () => JSON.parse(S.env.doGet({ parameter: {} }).text);
  const clearRL = () => Object.keys(S.cache).filter(k => k.startsWith('rl:')).forEach(k => delete S.cache[k]);
  const tabNames = () => S.tabs.map(t => t.getName()).join(' | ');
  const C = { status: 2, nick: 3, url: 4, key: 5, discord: 6, mmr: 7, p1: 8, note: 12 };
  const steamId = n => '7656119800000' + String(1000 + n);
  const url = n => 'https://steamcommunity.com/profiles/' + steamId(n);
  const reg = (n, extra = {}) => { clearRL(); return post({ action: 'register', nickname: '선수' + n, steam: url(n), discord: 'user' + n, mmr: 3000 + n * 100, prefs: [1, 2, 3, 4], ...extra }); };
  const rejoin = (steam, prefs = [4, 3, 2, 1], extra = {}) => { clearRL(); return post({ action: 'rejoin', steam, prefs, ...extra }); };
  const rowOf = (tab, n) => S.sheets[tab].grid.find(row => row[C.key] === 's:' + steamId(n));

  S.env.setup();
  const key = S.props.ADMIN_KEY;
  assert(tabNames() === '선수등록 (시즌 1)' && S.tabs[0].grid[0].join() === '등록시각,수정시각,상태,닉네임,스팀프로필,스팀키,디스코드,MMR,1지망,2지망,3지망,4지망,비고',
    'fresh install: the first season gets its own tab');
  S.steam.vanity.returner = steamId(5);
  [1, 3, 4, 6, 7, 8].forEach(n => reg(n));
  reg(2, { discord: '223456789012345678' });
  reg(5, { steam: 'https://steamcommunity.com/id/Returner' });
  post({ action: 'adminSetStatus', key, steamKeys: [1, 2, 3, 5, 6, 7, 8].map(n => 's:' + steamId(n)), status: '승인' });
  post({ action: 'adminSetStatus', key, steamKey: 's:' + steamId(4), status: '제외' });
  assert(status().registered === 8 && status().returning === false && post({ action: 'ping', key }).pastSeasons.length === 0, 'first season: nobody is a returning player yet');
  let r = rejoin(url(99));
  assert(!r.ok && r.code === 'notfound', 'quick rejoin without a past season finds nothing');
  r = rejoin(url(1));
  assert(!r.ok && r.code === 'already' && S.tabs[0].grid.length === 9, 'quick rejoin by someone already in this season is refused');

  // 새 시즌 시작
  r = post({ action: 'adminNewSeason', key: 'nope', season: '시즌 2' }); assert(!r.ok && r.code === 'auth', 'starting a season needs key');
  r = post({ action: 'adminNewSeason', key, season: '   ' }); assert(!r.ok && r.code === 'season', 'a new season needs a name');
  r = post({ action: 'adminNewSeason', key, season: ' 시즌1 ' }); assert(!r.ok && r.code === 'season' && S.tabs.length === 1, 'a new season cannot reuse a name (spaces ignored)');
  r = post({ action: 'adminNewSeason', key, season: '시즌 2' });
  assert(r.ok && r.season === '시즌 2' && r.registered === 0 && r.returning === true && r.pastSeasons.join() === '시즌 1', 'new season starts with an empty roster');
  assert(tabNames() === '선수등록 (시즌 2) | 선수등록 (시즌 1)' && S.sheets['선수등록 (시즌 1)'].grid.length === 9 && S.sheets['선수등록 (시즌 2)'].grid.length === 1
    && S.sheets['선수등록 (시즌 2)'].grid[0][C.note] === '비고', 'new season: a new tab in front, last season kept in its own tab');
  assert(post({ action: 'adminList', key }).players.length === 0 && status().season === '시즌 2' && status().returning === true, 'admin list and public status follow the new season');

  // 지난 시즌 선수의 간편 등록
  r = rejoin(url(1));
  let row = rowOf('선수등록 (시즌 2)', 1);
  assert(r.ok && r.nickname === '선수1' && r.from === '시즌 1' && !('discord' in r) && !('mmr' in r), 'quick rejoin answers with the nickname and season only');
  assert(row && row[C.status] === '대기' && row[C.nick] === '선수1' && row[C.url] === url(1) && row[C.discord] === 'user1' && row[C.mmr] === 3100
    && row.slice(C.p1, C.p1 + 4).join() === '서폿,오프,미드,캐리' && row[C.note] === '재참가 · 시즌 1', 'quick rejoin copies nickname, discord and MMR, takes the new position order');
  assert(rowOf('선수등록 (시즌 1)', 1).slice(C.p1, C.p1 + 4).join() === '캐리,미드,오프,서폿' && S.sheets['선수등록 (시즌 1)'].grid.length === 9, 'last season\'s tab is left as it was');
  r = post({ action: 'rejoin', steam: url(1), prefs: [1, 2, 3, 4] }); assert(!r.ok && r.code === 'rate', 'quick rejoin is rate limited too');
  r = rejoin(url(1)); assert(!r.ok && r.code === 'already' && r.error.includes('처음 등록해요') && S.sheets['선수등록 (시즌 2)'].grid.length === 2, 'second quick rejoin: already registered, told how to edit');
  post({ action: 'adminSetStatus', key, steamKey: 's:' + steamId(1), status: '승인' });
  r = rejoin(url(1)); assert(!r.ok && r.code === 'already' && r.error.includes('운영진에게'), 'after approval: told to ask the staff');
  assert(rowOf('선수등록 (시즌 2)', 1)[C.status] === '승인' && rowOf('선수등록 (시즌 1)', 8)[C.status] === '승인' && post({ action: 'adminList', key }).players[0].note === '재참가 · 시즌 1',
    'approval applies to this season; the admin list shows who came back');

  r = rejoin(steamId(2));                                  // 숫자만 넣어도 된다
  row = rowOf('선수등록 (시즌 2)', 2);
  assert(r.ok && row[C.discord] === '223456789012345678' && typeof row[C.discord] === 'string' && row[C.mmr] === 3200, 'numeric discord id is carried over as text');
  r = rejoin(url(4));
  assert(r.ok && rowOf('선수등록 (시즌 2)', 4)[C.status] === '대기' && rowOf('선수등록 (시즌 2)', 4)[C.note] === '재참가 · 시즌 1 (그때 제외)', 'someone excluded last season comes back as waiting, with a note for the staff');
  const calls = S.steam.calls;
  S.steam.down = true;
  r = rejoin(url(3));
  assert(r.ok && S.steam.calls === calls && rowOf('선수등록 (시즌 2)', 3), 'numeric address: quick rejoin does not need steam to answer');
  Object.keys(S.cache).filter(k => k.startsWith('steam:')).forEach(k => delete S.cache[k]);      // 지난 시즌에 조회해 둔 결과가 남아 있지 않을 때
  r = rejoin('https://steamcommunity.com/id/Returner'); assert(!r.ok && r.code === 'steam', 'custom address while steam is not answering: asked to retry');
  S.steam.down = false;
  r = rejoin('https://steamcommunity.com/id/Returner');
  assert(r.ok && r.nickname === '선수5' && rowOf('선수등록 (시즌 2)', 5)[C.url] === url(5), 'custom address is resolved to the same account');

  const count = S.sheets['선수등록 (시즌 2)'].grid.length;
  r = rejoin(url(99)); assert(!r.ok && r.code === 'notfound' && r.error.includes('처음 등록해요'), 'unknown steam profile: told to use the full form');
  r = rejoin('https://store.steampowered.com/app/570'); assert(!r.ok && r.code === 'steam', 'quick rejoin: bad steam address');
  r = rejoin(url(6), [1, 1, 2, 3]); assert(!r.ok && r.code === 'prefs', 'quick rejoin: bad position order');
  r = rejoin(url(6), [1, 2, 3, 4], { website: 'spam' }); assert(r.ok && r.nickname === '', 'quick rejoin: honeypot pretends success');
  post({ action: 'adminConfig', key, open: false });
  r = rejoin(url(6)); assert(!r.ok && r.code === 'closed', 'quick rejoin: registration closed');
  post({ action: 'adminConfig', key, open: true });
  assert(S.sheets['선수등록 (시즌 2)'].grid.length === count, 'refused quick rejoins write nothing');

  // 이번 시즌에 다른 사람이 같은 닉네임이나 디스코드를 먼저 쓴 경우
  reg(21, { nickname: '선수 6' });
  r = rejoin(url(6)); assert(!r.ok && r.code === 'conflict' && r.error.includes('닉네임'), 'quick rejoin: nickname taken by someone else this season');
  reg(22, { discord: 'user7' });
  r = rejoin(url(7)); assert(!r.ok && r.code === 'conflict' && r.error.includes('디스코드'), 'quick rejoin: discord account used by another steam profile this season');

  // 간편 등록한 뒤, 승인 전에는 모든 칸을 적는 등록으로 고칠 수 있다
  r = reg(2, { discord: 'someone_else' }); assert(!r.ok && r.code === 'conflict', 'full form with another discord cannot take over a rejoined row');
  r = reg(2, { discord: '223456789012345678', mmr: 4321, nickname: '선수2새이름' });
  row = rowOf('선수등록 (시즌 2)', 2);
  assert(r.ok && r.updated === true && row[C.mmr] === 4321 && row[C.nick] === '선수2새이름' && row[C.note] === '', 'full form updates a rejoined row and clears the note');

  // 세 번째 시즌: 가장 최근에 등록한 시즌의 정보를 가져온다
  r = post({ action: 'adminNewSeason', key, season: '시즌 3' });
  assert(r.ok && r.pastSeasons.join() === '시즌 1,시즌 2' && tabNames() === '선수등록 (시즌 3) | 선수등록 (시즌 2) | 선수등록 (시즌 1)', 'third season');
  r = rejoin(url(2));
  row = rowOf('선수등록 (시즌 3)', 2);
  assert(r.ok && r.from === '시즌 2' && r.nickname === '선수2새이름' && row[C.mmr] === 4321 && row[C.note] === '재참가 · 시즌 2 (그때 대기)', 'the latest season wins (and a never-approved row is noted)');
  r = rejoin(url(8));
  assert(r.ok && r.from === '시즌 1' && rowOf('선수등록 (시즌 3)', 8)[C.mmr] === 3800 && rowOf('선수등록 (시즌 3)', 8)[C.note] === '재참가 · 시즌 1', 'a player who skipped a season is found in the older one');
  S.tabs.splice(S.tabs.findIndex(t => t.getName() === '선수등록 (시즌 2)'), 1);       // 운영진이 지난 시즌 탭을 지웠다
  r = rejoin(url(1));
  assert(r.ok && r.from === '시즌 1' && rowOf('선수등록 (시즌 3)', 1)[C.note] === '재참가 · 시즌 1', 'a deleted season tab is skipped');

  // 시즌 이름 고치기와 탭 이름
  r = post({ action: 'adminConfig', key, season: '시즌1' }); assert(!r.ok && r.code === 'season' && status().season === '시즌 3', 'the current season cannot take a past season\'s name');
  r = post({ action: 'adminConfig', key, season: '2027 봄: 시즌/3' });
  assert(r.ok && r.season === '2027 봄: 시즌/3' && S.tabs[0].getName() === '선수등록 (2027 봄 시즌 3)' && r.registered === 3, 'renaming: characters a tab cannot hold are dropped from the tab name only');
  S.tabs.push(Object.assign(Object.create(S.tabs[0]), { getName: () => '선수등록 (시즌 4)', getSheetId: () => -1 }));   // 운영진이 손으로 만든 같은 이름의 탭
  r = post({ action: 'adminNewSeason', key, season: '시즌 4' });
  assert(r.ok && S.tabs[0].getName() === '선수등록 (시즌 4) 2' && r.registered === 0, 'tab name already taken: a number is added');
  S.tabs.splice(0, 1);                                     // 지금 시즌의 탭이 지워졌다
  r = status();
  assert(r.ok && r.registered === 0 && r.season === '시즌 4' && S.tabs[0].grid[0][C.nick] === '닉네임' && reg(30).ok && S.tabs[0].grid.length === 2, 'a deleted current tab is made again');
})();
