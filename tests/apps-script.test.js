const makeEnv = require('./gas-harness');
const { env, grid, props, cache, steam, sheets, trashed } = makeEnv();
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
assert(sheets['선수등록 (시즌 1)'] && sheets['선수등록 (시즌 1)'].grid === grid && !('선수등록' in sheets) && grid[0][12] === '비고' && grid[0][13] === '최고MMR',
  'upgrade: the old registration tab becomes the current season tab');

const base = { action:'register', nickname:'불멸의소환사', steam:'steamcommunity.com/profiles/76561197990650432/', discord:'@ZZKim', mmr:'6100', prefs:[2,1,3,4] };
let r = post(base);
assert(r.ok && r.updated === false, 'new registration');
assert(grid[1][5] === 's:76561197990650432' && grid[1][6] === 'zzkim' && grid[1][2] === '대기', 'row stored with normalized keys');
assert(grid[1][8] === '미드' && grid[1][11] === '서폿', 'prefs stored as labels');
assert(r.returning === false && r.mmr === 6100 && grid[1][13] === '' && grid[1][12] === '', 'a page without the peak MMR field still registers (peak left blank)');

r = post(base); assert(!r.ok && r.code === 'rate', 'rate limit blocks immediate resubmit');
clearRL();
r = post({ ...base, mmr: 6300, peak: '7100', nickname: '불멸의소환사2' });
assert(r.ok && r.updated === true && grid[1][7] === 6300 && grid[1][3] === '불멸의소환사2' && grid.length === 2, 'same steam+discord updates row');
assert(grid[1][13] === 7100 && r.mmr === 6300, 'peak MMR is stored');
clearRL();
r = post({ ...base, mmr: 6300, nickname: '불멸의소환사2' });
assert(r.ok && grid[1][13] === 7100, 'resubmitting without a peak keeps the stored one');

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
  [{ peak: '6000' }, 'peak'], [{ peak: '20000' }, 'peak'], [{ peak: '6500.5' }, 'peak'], [{ peak: 'abc' }, 'peak'],
  [{ prefs: [1,1,2,3] }, 'prefs'], [{ prefs: [1,2,3] }, 'prefs'],
  [{ nickname: '   ' }, 'nickname'], [{ nickname: 'x'.repeat(21) }, 'nickname'],
];
bad.forEach(([patch, code]) => { clearRL(); const res = post({ ...base, steam:'https://steamcommunity.com/profiles/76561198000000001', discord:'fresh_user', nickname:'신규', ...patch }); assert(!res.ok && res.code === code, 'invalid ' + code + ' ' + JSON.stringify(patch)); });

// 예전 방식의 디스코드(이름#1234)는 받지 않는다. 이름 부분에 아무 글자나 넣을 수 있어서, 운영진 화면이나 디스코드 메시지로 흘러가면 위험했다
['oldname#1234', '"><svg/onload=alert(1)>#1234', 'x@everyone#0001', '`x`**y**#9999'].forEach(d => {
  clearRL();
  const res = post({ ...base, steam:'https://steamcommunity.com/profiles/76561198000000001', discord: d, nickname:'신규' });
  assert(!res.ok && res.code === 'discord' && /이름#1234 모양은 이제 쓰이지 않습니다/.test(res.error) && grid.length === 3, 'legacy discord tag is refused: ' + d);
});
r = JSON.parse(env.doPost({ postData: { contents: ' '.repeat(9200000) } }).text);
assert(!r.ok && /너무 큽니다/.test(r.error), 'an oversized request is refused before it is parsed');

clearRL();
r = post({ ...base, website: 'spam' }); assert(r.ok && grid.length === 3, 'honeypot pretends success, writes nothing');

r = post({ action:'adminList', key:'wrong' }); assert(!r.ok && r.code === 'auth', 'admin list needs key');
r = post({ action:'adminList', key });
assert(r.ok && r.players.length === 2 && r.players[0].prefs.join() === '2,1,3,4' && r.players[1].discord === '123456789012345678', 'admin list returns parsed rows');
assert(r.players[0].peak === 7100 && r.players[1].peak === null && r.players[0].note === '', 'admin list carries the peak MMR (blank when not given)');

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
r = get('status'); assert(r.ok && r.open === false && r.version >= 7 && r.season === '시즌 2', 'public status');
assert(!('registered' in r) && !('pastSeasons' in r) && Object.keys(r).sort().join() === 'ok,open,recordsAt,season,version', 'public status does not tell how many registered');
r = post({ action:'ping', key });
assert(sheets['선수등록 (시즌 2)'] && sheets['선수등록 (시즌 2)'].grid === grid && r.season === '시즌 2' && r.registered === 2 && r.pastSeasons.length === 0,
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

// 운영자가 드라이브를 정리하다 기록 파일을 휴지통에 버렸어도, 쓰는 파일이면 도로 꺼낸다 (그대로 두면 30일 뒤에 기록이 통째로 사라진다)
trashed.add(props.LEAGUE_FILE_ID); trashed.add(props.RECORDS_FILE_ID);
r = post({ action:'adminLeague', key });
assert(r.ok && r.league.players[0].mmr === 5200 && !trashed.has(props.LEAGUE_FILE_ID), 'a league file found in the trash is taken back out when read');
delete cache.records;
assert(get('records').records.players[0].mmr === 5200 && !trashed.has(props.RECORDS_FILE_ID), 'the public records file too');
// 모양이 깨진 항목이 섞여 있어도 공개 기록을 만들다 멈추지 않는다
const cleaned = env.sanitizeRecords_({ players: [null, 'x', records.players[0]], matches: [{ id:'m', at:'', winner:'r', rows:[null, records.matches[0].rows[0]] }] });
assert(cleaned.players.length === 1 && cleaned.players[0].name === 'A' && cleaned.matches[0].rows.length === 1, 'broken entries are dropped from the public records instead of failing');
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

// ── 시즌: 시즌별 등록 탭, 리그 기록 보관, 지난 시즌 선수의 인하우스 MMR 이어받기 (새로 설치한 시트에서 시작) ──
(() => {
  const S = makeEnv({ fresh: true });
  const post = body => JSON.parse(S.env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
  const status = () => JSON.parse(S.env.doGet({ parameter: {} }).text);
  const records = () => { delete S.cache.records; return JSON.parse(S.env.doGet({ parameter: { action: 'records' } }).text).records; };
  const clearRL = () => Object.keys(S.cache).filter(k => k.startsWith('rl:')).forEach(k => delete S.cache[k]);
  const tabNames = () => S.tabs.map(t => t.getName()).join(' | ');
  const seasons = () => JSON.parse(S.props.SEASONS);
  const C = { status: 2, nick: 3, url: 4, key: 5, discord: 6, mmr: 7, p1: 8, note: 12, peak: 13 };
  const steamId = n => '7656119800000' + String(1000 + n);
  const url = n => 'https://steamcommunity.com/profiles/' + steamId(n);
  const reg = (n, extra = {}) => { clearRL(); return post({ action: 'register', nickname: '선수' + n, steam: url(n), discord: 'user' + n, mmr: 3000 + n * 100, peak: 5000 + n * 100, prefs: [1, 2, 3, 4], ...extra }); };
  const rowOf = (tab, n) => S.sheets[tab].grid.find(row => row[C.key] === 's:' + steamId(n));
  // 리그 매니저가 올리는 리그 기록의 선수 한 명
  const member = (n, mmr, extra = {}) => ({ id: 'p' + n, name: '선수' + n, baseMMR: 3000 + n * 100, mmr, prefs: [1, 2, 3, 4], wins: 1, losses: 0, streak: 1,
    roleCount: [1, 0, 0, 0, 0], discord: 'user' + n, steam: url(n), ...extra });
  const game = (id, ids) => ({ id, at: '2026-10-07T12:00:00.000Z', winner: 'r', rule: { k: 200 },
    rows: ids.map((pid, i) => ({ id: 'p' + pid, name: '선수' + pid, side: i < 5 ? 'r' : 'd', role: (i % 5) + 1, rank: 0, before: 3000, delta: i < 5 ? 20 : -20 })) });

  S.env.setup();
  const key = S.props.ADMIN_KEY;
  const ping = () => post({ action: 'ping', key });
  assert(tabNames() === '선수등록 (시즌 1)' && S.tabs[0].grid[0].join() === '등록시각,수정시각,상태,닉네임,스팀프로필,스팀키,디스코드,MMR,1지망,2지망,3지망,4지망,비고,최고MMR',
    'fresh install: the first season gets its own tab');
  S.steam.vanity.returner = steamId(5);
  [1, 3, 4, 6, 7, 8, 9, 10].forEach(n => reg(n));
  reg(2, { discord: '223456789012345678' });
  reg(5, { steam: 'https://steamcommunity.com/id/Returner' });
  post({ action: 'adminSetStatus', key, steamKeys: [1, 2, 3, 5, 6, 7, 8, 10].map(n => 's:' + steamId(n)), status: '승인' });
  post({ action: 'adminSetStatus', key, steamKey: 's:' + steamId(4), status: '제외' });              // 9번은 대기로 남는다
  let r = ping();
  assert(r.registered === 10 && r.pastSeasons.length === 0 && !('registered' in status()), 'first season: head count goes to the staff only');
  assert(rowOf('선수등록 (시즌 1)', 1)[C.peak] === 5100 && rowOf('선수등록 (시즌 1)', 1)[C.note] === '' && reg(11, { peak: undefined }).returning === false, 'first season: everyone is new');

  // 시즌 1의 리그 기록. 인하우스 MMR은 등록한 MMR과 달라져 있다
  const settings = { k: 200, balanceTol: 0, roleWeights: [1.3, 1.3, 1.2, 1, 1] };
  const league1 = { settings, matches: [game('m1', [1, 2, 3, 5, 6, 8, 10, 91, 92, 93])], players: [
    member(1, 3350), member(2, 2990, { discord: '223456789012345678' }), member(3, 3301),
    member(5, 3777, { steam: '' }),                                     // 스팀이 적혀 있지 않아 디스코드로 찾는 선수
    member(6, 3666, { steam: '', discord: '' }),                        // 둘 다 없어 그 시즌에 등록한 닉네임으로 찾는 선수
    member(8, 4100.6, { discord: '@User8' }),                           // 소수와 @, 대문자가 섞인 예전 기록
    member(10, 3999, { name: '프리시즌이름', prefs: [3, 5, 4, 1, 2], steam: 'https://steamcommunity.com/id/custom', discord: 'USER10' })   // 예전 형식(5지망)
  ] };
  r = post({ action: 'saveLeague', key, league: league1, baseRev: 0 });
  assert(r.ok && r.rev === 1 && records().players.length === 7 && S.sheets['순위'].grid.length === 9, 'season 1 league saved; ranking tab written');
  post({ action: 'pushRoster', key, roster: { entries: [{ id: '123456789012345678', username: 'user1', name: '선수1' }] } });
  post({ action: 'pushLineup', key, lineup: { lanes: [1, 2, 3, 4, 5].map(role => ({ role, r: 'r' + role, d: 'd' + role })) } });

  // 새 시즌 시작
  r = post({ action: 'adminNewSeason', key: 'nope', season: '시즌 2' }); assert(!r.ok && r.code === 'auth', 'starting a season needs key');
  r = post({ action: 'adminNewSeason', key, season: '   ' }); assert(!r.ok && r.code === 'season', 'a new season needs a name');
  // 되돌릴 수 없는 일이라 확인 문구("시즌 변경")를 함께 보낸 요청만 받는다
  const newSeason = (season, word = '시즌 변경') => post({ action: 'adminNewSeason', key, season, confirm: word });
  r = post({ action: 'adminNewSeason', key, season: '시즌 2' });
  assert(!r.ok && r.code === 'confirm' && r.error.includes('시즌 변경') && S.tabs.length === 3 && status().season === '시즌 1', 'starting a season without the confirmation phrase is refused');
  assert(['시즌변경', ' 시즌 변경', '시즌 변경!', 'yes', true].every(word => newSeason('시즌 2', word).code === 'confirm') && S.tabs.length === 3 && post({ action: 'adminLeague', key }).rev === 1,
    'a wrong confirmation phrase changes nothing');
  r = newSeason(' 시즌1 '); assert(!r.ok && r.code === 'season' && S.tabs.length === 3, 'a new season cannot reuse a name (spaces ignored)');
  r = post({ action: 'adminList', key });
  assert(r.seasonNo === 0 && r.current === 0 && r.season === '시즌 1' && r.players.length === 11, 'the admin list tells which season it is (by number)');
  r = newSeason('시즌 2');
  assert(r.ok && r.season === '시즌 2' && r.registered === 0 && r.pastSeasons.join() === '시즌 1', 'new season starts with an empty roster');
  // 끝난 시즌의 명단은 시즌 번호로 다시 볼 수 있다 (봇이 지난 시즌 선수에게서 역할을 거둘 때 쓴다)
  r = post({ action: 'adminList', key });
  assert(r.seasonNo === 1 && r.current === 1 && r.season === '시즌 2' && r.players.length === 0, 'the season number goes up with a new season');
  r = post({ action: 'adminList', key, seasonNo: 0 });
  assert(r.ok && r.season === '시즌 1' && r.seasonNo === 0 && r.current === 1 && r.players.length === 11 && r.players.filter(p => p.status === '승인').length === 8
    && r.players.some(p => p.discord === '223456789012345678'), 'a past season\'s roster can be read by its number');
  assert([5, -1, 1.5, 'x'].every(no => post({ action: 'adminList', key, seasonNo: no }).code === 'season') && post({ action: 'adminList', key: 'nope', seasonNo: 0 }).code === 'auth',
    'unknown season numbers are refused; the key is still needed');
  assert(S.tabs[0].getName() === '선수등록 (시즌 2)' && S.sheets['선수등록 (시즌 1)'].grid.length === 12 && S.sheets['선수등록 (시즌 2)'].grid.length === 1
    && S.sheets['선수등록 (시즌 2)'].grid[0][C.peak] === '최고MMR', 'new season: a new tab in front, last season kept in its own tab');
  assert(post({ action: 'adminList', key }).players.length === 0 && status().season === '시즌 2', 'admin list and public status follow the new season');
  // 리그 기록: 끝난 시즌은 보관하고, 새 시즌은 빈 기록에서 시작한다
  let got = post({ action: 'adminLeague', key });
  assert(got.rev === 2 && got.league.players.length === 0 && got.league.matches.length === 0 && JSON.stringify(got.league.settings) === JSON.stringify(settings),
    'new season: the league starts empty, settings kept, rev bumped so the manager pulls it');
  assert(records().players.length === 0 && records().matches.length === 0, 'new season: the public ranking is empty');
  const kept = JSON.parse(S.files[seasons()[0].league]);
  assert(seasons()[0].endedAt && kept.players.length === 7 && kept.players[0].mmr === 3350 && kept.matches.length === 1 && !('league' in seasons()[1]) && !('leaguePending' in seasons()[1]),
    'new season: the ended season\'s league is kept whole in its own drive file');
  assert(S.sheets['순위 (시즌 1)'].grid.length === 9 && S.sheets['순위 (시즌 1)'].grid[0][0].startsWith('끝난 시즌(시즌 1)') && S.sheets['경기 기록 (시즌 1)'].grid.length === 12
    && S.sheets['순위'].grid.length === 2 && S.sheets['경기 기록'].grid.length === 2, 'new season: ranking and match tabs of the ended season are kept under its name');
  assert(post({ action: 'adminRoster', key }).roster === null && post({ action: 'adminLineup', key }).lineup === null, 'new season: the bot\'s roster and lineup of the old season are dropped');

  // 지난 시즌에 승인됐던 선수가 같은 스팀·디스코드로 다시 등록: 인하우스 MMR을 이어받는다
  r = reg(1, { nickname: '새이름1', mmr: 5000, peak: 6200, prefs: [4, 3, 2, 1] });
  let row = rowOf('선수등록 (시즌 2)', 1);
  assert(r.ok && r.updated === false && r.returning === true && r.from === '시즌 1' && r.inhouse === true && r.mmr === 3350, 'returning player is told the inherited in-house MMR');
  assert(row[C.status] === '대기' && row[C.mmr] === 3350 && row[C.nick] === '새이름1' && row.slice(C.p1, C.p1 + 4).join() === '서폿,오프,미드,캐리' && row[C.peak] === 6200
    && row[C.discord] === 'user1' && row[C.note] === '재참가 · 시즌 1 · 인하우스 MMR 이어받음',
    'returning player: MMR is last season\'s final in-house MMR (not the typed one); name, positions and peak are the new ones');
  assert(rowOf('선수등록 (시즌 1)', 1)[C.mmr] === 3100 && rowOf('선수등록 (시즌 1)', 1)[C.nick] === '선수1', 'last season\'s tab is left as it was');
  r = reg(1, { nickname: '새이름1b', mmr: 7000, peak: 7100, prefs: [2, 1, 3, 4] });
  row = rowOf('선수등록 (시즌 2)', 1);
  assert(r.ok && r.updated === true && r.returning === true && r.mmr === 3350 && row[C.mmr] === 3350 && row[C.nick] === '새이름1b' && row[C.peak] === 7100
    && row[C.p1] === '미드' && row[C.note] === '재참가 · 시즌 1 · 인하우스 MMR 이어받음' && S.sheets['선수등록 (시즌 2)'].grid.length === 2,
    'returning player editing before approval: the inherited MMR stays, the rest follows the form');
  r = reg(2, { discord: '223456789012345678', mmr: 9000, peak: 9000 });
  row = rowOf('선수등록 (시즌 2)', 2);
  assert(r.returning && r.mmr === 2990 && row[C.mmr] === 2990 && row[C.discord] === '223456789012345678' && typeof row[C.discord] === 'string', 'returning player whose MMR went down inherits that too');
  r = reg(5, { steam: 'https://steamcommunity.com/id/Returner' });
  assert(r.returning && r.mmr === 3777 && rowOf('선수등록 (시즌 2)', 5)[C.mmr] === 3777, 'league entry without a steam address is found by discord');
  r = reg(6, { nickname: '여섯번째' });
  assert(r.returning && r.mmr === 3666 && rowOf('선수등록 (시즌 2)', 6)[C.note] === '재참가 · 시즌 1 · 인하우스 MMR 이어받음', 'league entry with neither is found by last season\'s nickname');
  r = reg(8);
  assert(r.returning && r.mmr === 4101, 'in-house MMR is rounded; @ and capitals in the league\'s discord do not matter');
  r = reg(10);
  assert(r.returning && r.mmr === 3999, 'an older-format league entry (5 preferences, custom steam address) still gives its final MMR');
  r = reg(7);
  assert(r.returning && r.mmr === 3700 && r.inhouse === false && r.from === '시즌 1' && rowOf('선수등록 (시즌 2)', 7)[C.note] === '재참가 · 시즌 1 · 그때 등록한 MMR 이어받음',
    'approved but never in the league: the MMR registered back then is carried');

  // 지난 시즌에 승인되지 않았던 사람과 처음 온 사람은 적어 낸 현재 MMR로 시작한다
  r = reg(4, { mmr: 4444, peak: 4444 });
  assert(r.ok && r.returning === false && r.mmr === 4444 && rowOf('선수등록 (시즌 2)', 4)[C.mmr] === 4444 && rowOf('선수등록 (시즌 2)', 4)[C.note] === '시즌 1에도 등록함 (그때 제외)',
    'excluded last season: treated as new, with a note for the staff');
  r = reg(9);
  assert(r.returning === false && rowOf('선수등록 (시즌 2)', 9)[C.note] === '시즌 1에도 등록함 (그때 대기)', 'never approved last season: treated as new, noted');
  r = reg(20);
  assert(r.returning === false && r.from === '' && r.mmr === 5000 && rowOf('선수등록 (시즌 2)', 20)[C.note] === '' && rowOf('선수등록 (시즌 2)', 20)[C.peak] === 7000, 'first-time player: nothing inherited');

  // 스팀과 디스코드 가운데 한쪽만 지난 시즌의 승인 기록과 같으면 다시 확인하게 한다
  const count = S.sheets['선수등록 (시즌 2)'].grid.length;
  r = reg(3, { discord: 'user3_typo' });
  assert(!r.ok && r.code === 'conflict' && r.error.includes('디스코드 사용자명을 다시 확인') && !r.error.includes('user3'), 'same steam, other discord than last season: asked to check (old account not revealed)');
  r = reg(30, { discord: 'user3' });
  assert(!r.ok && r.code === 'conflict' && r.error.includes('스팀 프로필 주소를 다시 확인'), 'same discord, other steam than last season: asked to check');
  r = reg(31, { discord: 'user11' });
  assert(r.ok && r.returning === false && rowOf('선수등록 (시즌 2)', 31)[C.note] === '', 'a discord that was never approved does not block anyone');
  assert(S.sheets['선수등록 (시즌 2)'].grid.length === count + 1, 'refused registrations write nothing');
  r = reg(3);
  assert(r.returning && r.mmr === 3301, 'with both matching the same player is recognized');
  r = post({ action: 'rejoin', steam: url(3), prefs: [1, 2, 3, 4] }); assert(!r.ok && /알 수 없는 요청/.test(r.error), 'the separate quick re-registration is gone');

  // 이번 시즌 안의 규칙은 그대로다
  post({ action: 'adminSetStatus', key, steamKey: 's:' + steamId(1), status: '승인' });
  r = reg(1, { nickname: '또바꿈' }); assert(!r.ok && r.code === 'locked' && rowOf('선수등록 (시즌 2)', 1)[C.nick] === '새이름1b', 'approved again this season: locked');
  assert(rowOf('선수등록 (시즌 1)', 4)[C.status] === '제외' && post({ action: 'adminList', key }).players.filter(p => p.note.startsWith('재참가')).length === 8, 'approval applies to this season only; the admin list shows who came back');

  // 세 번째 시즌: 가장 최근에 뛴 시즌의 인하우스 MMR을 이어받는다
  post({ action: 'adminSetStatus', key, steamKeys: [2, 5, 6, 7, 8, 10].map(n => 's:' + steamId(n)), status: '승인' });       // 3번은 시즌 2에서 대기로 남는다
  r = post({ action: 'saveLeague', key, league: { settings, matches: [], players: [member(1, 3500), member(7, 3650)] }, baseRev: 2 });
  assert(r.ok && r.rev === 3, 'season 2 league saved');
  r = newSeason('시즌 3');
  assert(r.ok && r.pastSeasons.join() === '시즌 1,시즌 2' && tabNames().startsWith('선수등록 (시즌 3) | 선수등록 (시즌 2) | 선수등록 (시즌 1)')
    && S.sheets['순위 (시즌 2)'] && S.sheets['순위 (시즌 1)'] && post({ action: 'adminLeague', key }).rev === 4, 'third season');
  r = reg(1);
  assert(r.returning && r.from === '시즌 2' && r.mmr === 3500 && rowOf('선수등록 (시즌 3)', 1)[C.note] === '재참가 · 시즌 2 · 인하우스 MMR 이어받음', 'the latest season\'s in-house MMR wins');
  r = reg(2, { discord: '223456789012345678' });
  assert(r.returning && r.from === '시즌 1' && r.mmr === 2990 && rowOf('선수등록 (시즌 3)', 2)[C.note] === '재참가 · 시즌 2 · 시즌 1 인하우스 MMR 이어받음',
    'approved last season but did not play: the in-house MMR of the season before is carried, and the note says which');
  r = reg(3);
  assert(r.returning && r.from === '시즌 1' && r.mmr === 3301, 'left waiting last season: recognized by the season before, where approved');
  r = reg(4, { mmr: 4000 });
  assert(r.returning === false && rowOf('선수등록 (시즌 3)', 4)[C.note] === '시즌 2에도 등록함 (그때 대기)', 'never approved in any season: still new');
  S.trashed.add(seasons()[0].league); S.trashed.add(seasons()[1].league);  // 운영자가 지난 시즌의 보관 파일을 휴지통에 버렸다
  r = reg(8);
  assert(r.returning && !S.trashed.has(seasons()[1].league), 'an archived league found in the trash is taken back out when a returning player needs it');
  delete S.files[seasons()[1].league];                                  // 시즌 2의 보관 파일이 지워졌다
  r = reg(7);
  assert(r.returning && r.from === '시즌 2' && r.mmr === 3700, 'a lost archive falls back to an older one, then to the registered MMR');
  S.tabs.splice(S.tabs.findIndex(t => t.getName() === '선수등록 (시즌 2)'), 1);     // 운영진이 지난 시즌의 등록 탭을 지웠다
  r = reg(5, { steam: 'https://steamcommunity.com/id/Returner' });
  assert(r.returning && r.from === '시즌 1' && r.mmr === 3777, 'a deleted season tab is skipped');
  r = post({ action: 'adminList', key, seasonNo: 1 });
  assert(r.ok && r.season === '시즌 2' && r.players.length === 0, 'a deleted season tab reads as an empty roster');

  // 새 시즌을 시작하다 리그 기록을 비우지 못한 경우(구글 드라이브가 잠깐 답하지 않을 때): 시즌은 바뀌고, 다음 요청에서 이어서 비운다
  post({ action: 'saveLeague', key, league: { settings, matches: [], players: [member(1, 3600)] }, baseRev: 4 });
  const getFile = S.env.DriveApp.getFileById;
  S.env.DriveApp.getFileById = id => Object.assign(getFile(id), { setContent() { throw new Error('드라이브 오류'); } });
  r = newSeason('시즌 4');
  assert(r.ok && r.season === '시즌 4' && seasons()[3].leaguePending === true && post({ action: 'adminLeague', key }).league.players.length === 1 && seasons()[2].league,
    'drive failing during the reset: the season still starts and the ended league is already archived');
  S.env.DriveApp.getFileById = getFile;
  status();
  got = post({ action: 'adminLeague', key });
  assert(!('leaguePending' in seasons()[3]) && got.league.players.length === 0 && got.rev === 6 && S.sheets['순위 (시즌 3)'], 'the next request finishes the reset');
  r = reg(1);
  assert(r.returning && r.from === '시즌 3' && r.mmr === 3600, 'and the archive made before the failure is used');

  // 시즌 이름 고치기와 탭 이름
  r = post({ action: 'adminConfig', key, season: '시즌1' }); assert(!r.ok && r.code === 'season' && status().season === '시즌 4', 'the current season cannot take a past season\'s name');
  r = post({ action: 'adminConfig', key, season: '2027 봄: 시즌/4' });
  assert(r.ok && r.season === '2027 봄: 시즌/4' && S.tabs[0].getName() === '선수등록 (2027 봄 시즌 4)' && r.registered === 1, 'renaming: characters a tab cannot hold are dropped from the tab name only');
  assert(post({ action: 'adminList', key }).seasonNo === 3, 'renaming the season does not change its number (so the bot does not take it for a new season)');
  S.tabs.push(Object.assign(Object.create(S.tabs[0]), { getName: () => '선수등록 (시즌 5)', getSheetId: () => -1 }));   // 운영진이 손으로 만든 같은 이름의 탭
  r = newSeason('시즌 5');
  assert(r.ok && S.tabs[0].getName() === '선수등록 (시즌 5) 2' && r.registered === 0 && S.sheets['순위 (2027 봄 시즌 4)'], 'tab name already taken: a number is added');
  S.tabs.splice(0, 1);                                     // 지금 시즌의 탭이 지워졌다
  r = ping();
  assert(r.ok && r.registered === 0 && r.season === '시즌 5' && S.tabs[0].grid[0][C.nick] === '닉네임' && reg(40).ok && S.tabs[0].grid.length === 2, 'a deleted current tab is made again');
  r = post({ action: 'adminList', key });
  assert(r.seasonNo === 4 && r.players.length === 1, 'and the season keeps its number');

  // 칸이 늘어난 버전으로 올렸을 때: 이미 있는 시즌 탭들에 새 머리글을 채운다
  const season1 = S.sheets['선수등록 (시즌 1)'].grid;
  delete S.props.LAYOUT; season1[0][C.peak] = ''; season1[0][C.note] = ''; S.tabs[0].grid[0][C.peak] = '';
  status();
  assert(S.props.LAYOUT && season1[0][C.peak] === '최고MMR' && season1[0][C.note] === '비고' && S.tabs[0].grid[0][C.peak] === '최고MMR' && season1[1][C.nick] === '선수1',
    'upgrade: missing headers are filled in on every season tab, rows untouched');
})();

// 리그 기록이 한 번도 올라오지 않은 채 시즌을 바꾸면 보관할 것도 비울 것도 없다
(() => {
  const S = makeEnv({ fresh: true });
  const post = body => JSON.parse(S.env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
  S.env.setup();
  const key = S.props.ADMIN_KEY;
  const r = post({ action: 'adminNewSeason', key, season: '시즌 2', confirm: '시즌 변경' });
  const list = JSON.parse(S.props.SEASONS);
  assert(r.ok && !('league' in list[0]) && list[0].endedAt && !('leaguePending' in list[1]) && post({ action: 'adminLeague', key }).rev === 0 && !S.sheets['순위'],
    'starting a season before any league record exists changes the registration tab only');
})();
