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

// 리그 기록이 아직 없을 때. 예전 방식의 공개 기록 올리기(매니저가 공개할 칸만 골라 올림)는 이때만 받는다
const records = { players:[{ id:'p1', name:'A', baseMMR:5000, mmr:5100, prefs:[1,2,3,4], wins:1, losses:0, streak:1, roleCount:[1,0,0,0,0], discord:'secret', steam:'secret' }],
  matches:[{ id:'m1', at:'2026-10-05T08:12:12.491Z', winner:'r', rule:{k:200}, rows:[{ id:'p1', name:'A', side:'r', role:1, rank:0, before:5000, delta:100, extra:'x' }] }], settings:{k:200} };
r = post({ action:'publishRecords', key:'nope', records }); assert(!r.ok, 'publish needs key');
r = post({ action:'publishRecords', key, records }); assert(r.ok && r.players === 1 && r.matches === 1, 'publish records');
r = get('records');
const txt = JSON.stringify(r.records);
assert(r.ok && !txt.includes('secret') && !txt.includes('extra') && !('settings' in r.records) && r.records.players[0].mmr === 5100, 'public records sanitized');
delete cache.records; r = get('records'); assert(r.ok && r.records.matches.length === 1, 'records read back from drive file when cache is empty');
r = post({ action:'adminLeague', key }); assert(r.ok && r.league === null && r.rev === 0 && r.leagueAt === '', 'no league yet');
r = post({ action:'adminLeagueRev', key }); assert(r.ok && r.rev === 0, 'rev starts at 0');
const rev = () => post({ action:'adminLeagueRev', key }).rev;

r = post({ action:'adminSetStatus', key, steamKeys:['s:76561197990650432','s:76561198000000777'], status:'승인' });
assert(r.ok && r.changed === 2 && grid[1][2] === '승인' && grid[2][2] === '승인', 'bulk approve');
// 승인한 선수는 선수단(리그 기록)에 바로 들어간다. 리그 기록이 없었으면 이때 생긴다
assert(r.league && r.league.ok && r.league.added.join('|') === '불멸의소환사2|=HYPERLINK("x")' && r.league.players === 2 && r.league.rev === 1 && rev() === 1,
  'approving puts the players straight into the league (the league is created if there was none)');
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

r = post({ action:'pushRoster', key, roster:{ entries:[{ id:'<@123456789012345678>', username:'zzkim', name:'김' }, { id:'', username:'x' }] } });
assert(r.ok && r.count === 1, 'push roster keeps valid entries');
r = post({ action:'adminRoster', key }); assert(r.ok && r.roster.entries[0].id === '123456789012345678', 'admin roster');

// 리그 기록의 원본은 서버에 둔다. 번호(rev)가 맞아야만 받아서, 매니저와 봇이 서로의 변경을 덮어쓰지 않게 한다
const at = rev();                                        // 위에서 승인한 선수가 선수단에 들어가면서 번호가 이미 올라가 있다
assert(at >= 1, 'the league already has a rev from the approvals above');
const league = { players: records.players, matches: records.matches, settings: { balanceTol: 500 }, junk: 'dropped' };
r = post({ action:'saveLeague', key: 'nope', league, baseRev: at }); assert(!r.ok && r.code === 'auth', 'saving the league needs key');
r = post({ action:'adminLeagueRev', key: 'nope' }); assert(!r.ok && r.code === 'auth', 'league rev needs key');
r = post({ action:'saveLeague', key, league, baseRev: at });
assert(r.ok && r.rev === at + 1 && r.players === 1 && r.matches === 1, 'a save based on the current rev is accepted and bumps it');
r = post({ action:'adminLeague', key: 'nope' }); assert(!r.ok && r.code === 'auth', 'league needs key');
r = post({ action:'adminLeague', key });
assert(r.ok && r.rev === at + 1 && r.league.players[0].discord === 'secret' && r.league.settings.balanceTol === 500 && r.league.matches[0].rule.k === 200 && !('junk' in r.league) && r.leagueAt,
  'league is kept whole (discord and settings included)');
delete cache.records;
assert(!JSON.stringify(get('records').records).includes('secret') && get('records').records.players[0].mmr === 5100, 'public records are derived from the league and stay sanitized');

const grown = { ...league, players: [{ ...records.players[0], mmr: 5200 }] };
r = post({ action:'saveLeague', key, league: grown, baseRev: at });
assert(!r.ok && r.code === 'conflict' && rev() === at + 1 && post({ action:'adminLeague', key }).league.players[0].mmr === 5100,
  'save based on an older rev is refused and changes nothing');
r = post({ action:'saveLeague', key, league: grown, baseRev: at + 1 });
assert(r.ok && r.rev === at + 2 && get('records').records.players[0].mmr === 5200, 'save based on the current rev is accepted; ranking page follows');

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
assert(r.ok && r.rev === at + 3 && post({ action:'adminLeague', key }).league.players[0].mmr === 5100, 'forced save overwrites');
r = post({ action:'saveLeague', key, league: { players: 'x' }, baseRev: at + 3 });
assert(!r.ok && rev() === at + 3, 'broken league is refused');
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
r = post({ action:'saveLeague', key, league: three, baseRev: at + 3 });
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
r = post({ action:'saveLeague', key, league: { ...three, players: three.players.slice(0, 1), matches: [] }, baseRev: at + 4 });
assert(r.ok && sheets['순위'].grid.length === 3 && sheets['경기 기록'].grid.length === 2, 'mirror tabs are rewritten whole (old rows do not linger)');
sheets['순위'].clearContents = () => { throw new Error('시트 오류'); };
r = post({ action:'saveLeague', key, league: three, baseRev: at + 5 });
assert(r.ok && r.rev === at + 6 && post({ action:'adminLeague', key }).league.players.length === 4, 'a failing mirror tab does not fail the save');
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
  assert(tabNames() === '선수등록 (시즌 1)' && S.tabs[0].grid[0].join() === '등록시각,수정시각,상태,닉네임,스팀프로필,스팀키,디스코드,MMR,1지망,2지망,3지망,4지망,비고,최고MMR,처리자,처리시각',
    'fresh install: the first season gets its own tab');
  S.steam.vanity.returner = steamId(5);
  [1, 3, 4, 6, 7, 8, 9, 10].forEach(n => reg(n));
  reg(2, { discord: '223456789012345678' });
  reg(5, { steam: 'https://steamcommunity.com/id/Returner' });
  const rev = () => post({ action: 'adminLeagueRev', key }).rev;
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
  // 승인한 여덟 명은 이미 선수단에 들어가 있다(번호 1). 여기서는 매니저가 한 시즌을 치른 기록을 올린 것으로 친다: 7번은 그 기록에 없다
  assert(rev() === 1 && post({ action: 'adminLeague', key }).league.players.length === 8, 'season 1: the approved players are in the league before any manager touches it');
  r = post({ action: 'saveLeague', key, league: league1, baseRev: 1 });
  assert(r.ok && r.rev === 2 && records().players.length === 7 && S.sheets['순위'].grid.length === 9, 'season 1 league saved; ranking tab written');
  post({ action: 'pushRoster', key, roster: { entries: [{ id: '123456789012345678', username: 'user1', name: '선수1' }] } });
  post({ action: 'pushLineup', key, lineup: { lanes: [1, 2, 3, 4, 5].map(role => ({ role, r: 'r' + role, d: 'd' + role })) } });

  // 새 시즌 시작
  r = post({ action: 'adminNewSeason', key: 'nope', season: '시즌 2' }); assert(!r.ok && r.code === 'auth', 'starting a season needs key');
  r = post({ action: 'adminNewSeason', key, season: '   ' }); assert(!r.ok && r.code === 'season', 'a new season needs a name');
  // 되돌릴 수 없는 일이라 확인 문구("시즌 변경")를 함께 보낸 요청만 받는다
  const newSeason = (season, word = '시즌 변경') => post({ action: 'adminNewSeason', key, season, confirm: word });
  r = post({ action: 'adminNewSeason', key, season: '시즌 2' });
  assert(!r.ok && r.code === 'confirm' && r.error.includes('시즌 변경') && S.tabs.length === 4 && status().season === '시즌 1', 'starting a season without the confirmation phrase is refused');
  assert(['시즌변경', ' 시즌 변경', '시즌 변경!', 'yes', true].every(word => newSeason('시즌 2', word).code === 'confirm') && S.tabs.length === 4 && post({ action: 'adminLeague', key }).rev === 2,
    'a wrong confirmation phrase changes nothing');
  r = newSeason(' 시즌1 '); assert(!r.ok && r.code === 'season' && S.tabs.length === 4, 'a new season cannot reuse a name (spaces ignored)');
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
  assert(got.rev === 3 && got.league.players.length === 0 && got.league.matches.length === 0 && JSON.stringify(got.league.settings) === JSON.stringify(settings),
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
  r = post({ action: 'adminSetStatus', key, steamKey: 's:' + steamId(1), status: '승인' });
  // 새 시즌에 승인한 재참가 선수는 이어받은 인하우스 MMR로 새 시즌의 선수단에 들어간다 (시즌 1을 3350으로 마친 선수)
  got = post({ action: 'adminLeague', key });
  assert(r.league.ok && r.league.added.join() === '새이름1b' && got.rev === 4 && got.league.players.length === 1 && got.league.players[0].mmr === 3350 && got.league.players[0].baseMMR === 3350
    && got.league.players[0].wins === 0 && got.league.players[0].prefs.join() === '2,1,3,4' && got.league.players[0].discord === 'user1' && JSON.stringify(got.league.settings) === JSON.stringify(settings),
    'new season: an approved returning player enters the new league with the carried in-house MMR and a clean record');
  r = reg(1, { nickname: '또바꿈' }); assert(!r.ok && r.code === 'locked' && rowOf('선수등록 (시즌 2)', 1)[C.nick] === '새이름1b', 'approved again this season: locked');
  assert(rowOf('선수등록 (시즌 1)', 4)[C.status] === '제외' && post({ action: 'adminList', key }).players.filter(p => p.note.startsWith('재참가')).length === 8, 'approval applies to this season only; the admin list shows who came back');

  // 세 번째 시즌: 가장 최근에 뛴 시즌의 인하우스 MMR을 이어받는다
  post({ action: 'adminSetStatus', key, steamKeys: [2, 5, 6, 7, 8, 10].map(n => 's:' + steamId(n)), status: '승인' });       // 3번은 시즌 2에서 대기로 남는다
  assert(rev() === 5 && post({ action: 'adminLeague', key }).league.players.length === 7, 'season 2: the rest of the approved players join the league');
  r = post({ action: 'saveLeague', key, league: { settings, matches: [], players: [member(1, 3500), member(7, 3650)] }, baseRev: 5 });
  assert(r.ok && r.rev === 6, 'season 2 league saved');
  r = newSeason('시즌 3');
  assert(r.ok && r.pastSeasons.join() === '시즌 1,시즌 2' && tabNames().startsWith('선수등록 (시즌 3) | 선수등록 (시즌 2) | 선수등록 (시즌 1)')
    && S.sheets['순위 (시즌 2)'] && S.sheets['순위 (시즌 1)'] && post({ action: 'adminLeague', key }).rev === 7, 'third season');
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
  post({ action: 'saveLeague', key, league: { settings, matches: [], players: [member(1, 3600)] }, baseRev: 7 });
  const getFile = S.env.DriveApp.getFileById;
  S.env.DriveApp.getFileById = id => Object.assign(getFile(id), { setContent() { throw new Error('드라이브 오류'); } });
  r = newSeason('시즌 4');
  assert(r.ok && r.season === '시즌 4' && seasons()[3].leaguePending === true && post({ action: 'adminLeague', key }).league.players.length === 1 && seasons()[2].league,
    'drive failing during the reset: the season still starts and the ended league is already archived');
  S.env.DriveApp.getFileById = getFile;
  status();
  got = post({ action: 'adminLeague', key });
  assert(!('leaguePending' in seasons()[3]) && got.league.players.length === 0 && got.rev === 9 && S.sheets['순위 (시즌 3)'], 'the next request finishes the reset');
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

// 등록이 가득 찼을 때(3000줄): 새 등록은 받지 않지만, 이미 등록한 사람은 승인 전이면 계속 고칠 수 있다
(() => {
  const S = makeEnv({ fresh: true });
  S.env.setup();
  const post = body => JSON.parse(S.env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
  const form = { action: 'register', nickname: '먼저온선수', steam: 'https://steamcommunity.com/profiles/76561198000000001', discord: 'early_bird', mmr: 3000, prefs: [1, 2, 3, 4] };
  assert(post(form).ok, 'full sheet: someone registered before it filled up');
  const grid = S.tabs[0].grid;
  S.tabs[0].insertRowsAfter(1000, 2500);                   // 가짜 시트는 1000줄로 시작한다. 실제 시트는 줄을 더하면 저절로 늘어난다
  for (let i = grid.length; i <= 3000; i++)
    grid.push(['', '', '대기', '채움' + i, '', 's:76561199' + String(i).padStart(8, '0'), 'filler' + i, 1000, '캐리', '미드', '오프', '서폿', '', '']);
  Object.keys(S.cache).filter(k => k.startsWith('rl:')).forEach(k => delete S.cache[k]);
  let r = post({ ...form, nickname: '늦게온선수', steam: 'https://steamcommunity.com/profiles/76561198000000002', discord: 'late_bird' });
  assert(!r.ok && /가득 찼습니다/.test(r.error) && grid.length === 3001, 'full sheet: a new registration is refused');
  r = post({ ...form, mmr: 3200 });
  assert(r.ok && r.updated === true && grid[1][7] === 3200, 'full sheet: an existing registration can still be edited');
})();

// 리그 기록이 한 번도 올라오지 않은 채 시즌을 바꾸면 보관할 것도 비울 것도 없다
(() => {
  const S = makeEnv({ fresh: true });
  const post = body => JSON.parse(S.env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
  S.env.setup();
  const key = S.props.ADMIN_KEY;
  let r = post({ action: 'adminNewSeason', key, season: '시즌 2', confirm: '시즌 변경' });
  const list = JSON.parse(S.props.SEASONS);
  assert(r.ok && !('league' in list[0]) && list[0].endedAt && !('leaguePending' in list[1]) && post({ action: 'adminLeague', key }).rev === 0 && !S.sheets['순위'],
    'starting a season before any league record exists changes the registration tab only');
  r = post({ action: 'saveLeague', key, league: { players: [], matches: [], settings: {} }, baseRev: 0 });
  assert(r.ok && r.rev === 1 && post({ action: 'adminLeague', key }).league.players.length === 0, 'first save becomes rev 1');
})();

// ── 승인한 선수는 선수단(리그 기록)에 바로 들어간다 (버전 10) ──
// 전에는 운영진이 명단 파일을 받아 리그 매니저에 불러와야 했고, 그 일을 빠뜨리면 봇이 팀을 짜지 못했다
(() => {
  const fs = require('fs'), path = require('path'), vm = require('vm');
  const S = makeEnv({ fresh: true });
  const post = body => JSON.parse(S.env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
  const clearRL = () => Object.keys(S.cache).filter(k => k.startsWith('rl:')).forEach(k => delete S.cache[k]);
  S.env.setup();
  const key = S.props.ADMIN_KEY;
  const steamId = n => '7656119800000' + String(2000 + n);
  const url = n => 'https://steamcommunity.com/profiles/' + steamId(n);
  const prefsOf = n => [[1, 2, 3, 4], [2, 3, 1, 4], [3, 1, 4, 2], [4, 3, 2, 1]][n % 4];
  const reg = (n, extra = {}) => { clearRL(); return post({ action: 'register', nickname: '선수' + n, steam: url(n), discord: 'user' + n, mmr: 3000 + n * 100, prefs: prefsOf(n), ...extra }); };
  const set = (ns, status) => post({ action: 'adminSetStatus', key, steamKeys: [].concat(ns).map(n => 's:' + steamId(n)), status });
  const sync = () => post({ action: 'adminSyncPlayers', key });
  const got = () => post({ action: 'adminLeague', key });
  const rev = () => post({ action: 'adminLeagueRev', key }).rev;
  const who = name => got().league.players.find(p => p.name === name);
  const names = () => got().league.players.map(p => p.name).join();
  const overwrite = change => { const lg = got().league; change(lg); return post({ action: 'saveLeague', key, league: lg, baseRev: 0, force: true }); };   // 매니저가 기록을 올린 것으로 친다
  const manual = (id, name, discord) => ({ id, name, baseMMR: 2000, mmr: 2000, prefs: [1, 2, 3, 4], wins: 0, losses: 0, streak: 0, roleCount: [0, 0, 0, 0, 0], discord, steam: '' });   // 매니저에서 손으로 넣은 선수
  const C = { status: 2, nick: 3, key: 5, p1: 8 };
  const rowOf = n => S.tabs[0].grid.find(row => row[C.key] === 's:' + steamId(n));

  for (let n = 1; n <= 12; n++) reg(n);
  let r = set(12, '제외');
  assert(r.ok && r.changed === 1 && !('league' in r) && rev() === 0 && got().league === null, 'link: excluding someone who was never approved does not touch the league');
  r = post({ action: 'adminSetStatus', key, steamKey: 's:76561190000000000', status: '승인' });
  assert(r.ok && r.changed === 0 && !('league' in r) && rev() === 0, 'link: an unknown player changes nothing');

  // 리그 기록이 아직 없으면 이때 생긴다. 넣는 선수의 모양은 매니저가 만드는 선수(newPlayer)와 같다
  r = set(1, '승인');
  let p = who('선수1'), g = got();
  assert(r.ok && r.changed === 1 && r.league.ok && r.league.added.join() === '선수1' && r.league.players === 1 && r.league.rev === 1 && rev() === 1, 'link: approving creates the league and puts the player in');
  assert(Object.keys(p).join() === 'id,name,baseMMR,mmr,prefs,wins,losses,streak,roleCount,discord,steam' && /^ps[0-9a-z]+$/.test(p.id) && !p.id.includes(steamId(1).slice(4)),
    'link: the player has the same fields as one made by the manager, and an id that does not give away the steam account');
  assert(p.baseMMR === 3100 && p.mmr === 3100 && p.prefs.join() === prefsOf(1).join() && p.wins === 0 && p.losses === 0 && p.streak === 0 && p.roleCount.join() === '0,0,0,0,0'
    && p.discord === 'user1' && p.steam === url(1), 'link: MMR, preferences, discord and steam come from the registration; the record starts clean');
  assert(g.league.matches.length === 0 && JSON.stringify(g.league.settings) === '{}' && g.leagueAt, 'link: a league made this way has no matches and leaves the settings to the manager and the bot (defaults)');
  delete S.cache.records;
  const pub = JSON.parse(S.env.doGet({ parameter: { action: 'records' } }).text).records, pubText = JSON.stringify(pub);
  assert(pub.players.length === 1 && pub.players[0].name === '선수1' && pub.players[0].mmr === 3100 && !pubText.includes('user1') && !pubText.includes(steamId(1)) && !pubText.includes('steam'),
    'link: the ranking page gets the player without discord or steam');
  assert(S.sheets['순위'].grid.length === 3 && S.sheets['순위'].grid[2][1] === '선수1' && S.sheets['순위'].grid[2][0] === '-', 'link: the ranking tab of the sheet is written too');

  r = set(1, '승인');
  assert(r.ok && r.changed === 1 && !('league' in r) && rev() === 1, 'link: approving an already approved player again does nothing');
  r = set([2, 3, 4, 5, 6, 7, 8, 9, 10], '승인');
  g = got();
  assert(r.changed === 9 && r.league.added.length === 9 && r.league.players === 10 && rev() === 2 && new Set(g.league.players.map(x => x.id)).size === 10
    && names() === [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => '선수' + n).join(), 'link: approving many at once writes the league once, each with its own id');

  // 이렇게 들어간 선수로 봇이 팀을 짤 수 있고(실제 matchmaker.js 와 매니저 파일), 매니저의 검사(backupProblem)도 이 기록을 받는다
  const { makeMatch, loadEngine } = require('../bot/matchmaker.js');
  const made = makeMatch({ league: g.league, participants: g.league.players.map(x => x.id), busy: [], now: Date.parse('2026-10-08T12:00:00Z') });
  assert(made.ok && made.lanes.length === 5 && new Set(made.lanes.flatMap(l => [l.r.id, l.d.id])).size === 10 && made.bench.length === 0, 'link: the bot can form teams from players the server put in, with no manager involved');
  const html = fs.readFileSync(path.join(__dirname, '..', 'manager', 'InhouseLeagueManager_v0_18.html'), 'utf8');
  const src = html.match(/const SAFE_ID = [\s\S]*?\nfunction backupProblem\(o\)\{[\s\S]*?\n\}\n/);
  const ctx = vm.createContext({ console, performance: require('perf_hooks').performance });
  vm.runInContext(loadEngine() + '\n' + (src ? src[0] : ''), ctx);
  const problem = src ? vm.runInContext('backupProblem', ctx) : () => 'no check';
  assert(problem(g.league) === null && problem({ players: [{ id: 'bad id!', name: 'x', mmr: 1 }] }) !== null, 'link: the manager\'s own check (backupProblem) accepts the league the server made');

  // 승인을 풀면: 아직 경기를 치르지 않은 선수는 선수단에서도 빠진다
  r = set(2, '대기');
  assert(r.league.ok && r.league.removed.join() === '선수2' && r.league.kept.length === 0 && r.league.players === 9 && !who('선수2') && rev() === 3, 'link: un-approving a player who has not played takes them out of the league');
  reg(2, { nickname: '둘째', mmr: 4444, prefs: [4, 1, 2, 3] });
  r = set(2, '승인');
  p = who('둘째');
  assert(r.league.added.join() === '둘째' && p.mmr === 4444 && p.baseMMR === 4444 && p.prefs.join() === '4,1,2,3' && p.discord === 'user2' && r.league.players === 10,
    'link: set back to waiting, corrected by the player, approved again: joins with the corrected registration');

  // 경기를 치른 선수는 승인을 풀어도 선수단에 남는다 (전적과 경기 기록이 이어지게)
  overwrite(lg => {
    lg.players.forEach((x, i) => Object.assign(x, i < 5 ? { wins: 1, streak: 1, mmr: x.mmr + 20 } : { losses: 1, streak: -1, mmr: x.mmr - 20 }));
    lg.matches = [{ id: 'm1', at: '2026-10-08T12:00:00.000Z', winner: 'r', rule: { k: 200, spreadRatio: 1.5, roleWeights: [1.2, 1.25, 1.2, 0.675, 0.675] },
      rows: lg.players.map((x, i) => ({ id: x.id, name: x.name, side: i < 5 ? 'r' : 'd', role: (i % 5) + 1, rank: 0, before: x.baseMMR, delta: i < 5 ? 20 : -20 })) }];
  });
  let at = rev();
  const oldId = who('선수1').id;
  r = set(1, '제외');
  assert(r.changed === 1 && r.league.ok && r.league.kept.join() === '선수1' && r.league.removed.length === 0 && who('선수1').wins === 1 && rev() === at,
    'link: excluding a player who has played keeps them in the league (and writes nothing)');
  // 대기로 돌려 본인이 고치게 한 뒤 다시 승인: 닉네임·등록 MMR·지망은 새 값으로, 인하우스 MMR과 전적은 그대로
  r = set(1, '대기');
  assert(!('league' in r), 'link: excluded to waiting is not an approval change');
  reg(1, { nickname: '첫째', mmr: 9000, prefs: [3, 4, 1, 2] });
  r = set(1, '승인');
  p = who('첫째');
  assert(r.league.updated.join() === '첫째' && r.league.added.length === 0 && p.id === oldId && p.baseMMR === 9000 && p.mmr === 3120 && p.wins === 1 && p.prefs.join() === '3,4,1,2'
    && got().league.players.length === 10 && rev() === at + 1, 'link: approving a player already in the league updates name, registered MMR and preferences; in-house MMR and record stay');

  // 같은 선수인지: 디스코드 → 스팀 → 닉네임 (매니저의 명단 불러오기와 같은 순서)
  overwrite(lg => { lg.players.find(x => x.name === '선수3').discord = 'typo_user'; });
  r = set(3, '대기');
  assert(r.league.kept.join() === '선수3', 'link: found by steam when the discord differs (kept, has games)');
  r = set(3, '승인');
  assert(r.league.updated.join() === '선수3' && who('선수3').discord === 'user3' && got().league.players.length === 10, 'link: same steam, other discord: the same player, discord corrected, no duplicate');
  overwrite(lg => { lg.players.push(manual('pmanual11', '선수11', '')); });
  r = set(11, '승인');
  p = who('선수11');
  assert(r.league.updated.join() === '선수11' && p.id === 'pmanual11' && p.discord === 'user11' && p.steam === url(11) && p.baseMMR === 4100 && p.mmr === 4100 && got().league.players.length === 11,
    'link: a player typed into the manager by hand (no discord, no steam) is matched by name and completed');
  r = set(11, '대기');
  assert(r.league.removed.join() === '선수11' && got().league.players.length === 10, 'link: and taken out again when un-approved without games');
  overwrite(lg => { lg.players.push(manual('pmanual12', '선수12', 'someone_else')); });
  r = set(12, '승인');
  assert(r.league.added.join() === '선수12 (2)' && who('선수12').discord === 'someone_else' && who('선수12 (2)').discord === 'user12' && got().league.players.length === 12,
    'link: same name but another discord is another person: added under a numbered name');
  r = set(12, '제외');
  assert(r.league.removed.join() === '선수12 (2)' && who('선수12').id === 'pmanual12' && got().league.players.length === 11, 'link: un-approving removes only the player with that discord, not the namesake');

  // 빠진 선수 채우기: 매니저가 예전 기록으로 서버를 덮어써서 승인한 선수가 빠졌어도, 다음에 누군가를 승인할 때 함께 들어간다.
  // 이미 있는 선수는 건드리지 않는다(매니저에서 고친 지망이나 MMR을 덮어쓰지 않는다)
  overwrite(lg => {
    lg.players = lg.players.filter(x => x.name !== '둘째');
    Object.assign(lg.players.find(x => x.name === '선수4'), { prefs: [4, 3, 2, 1], baseMMR: 1234 });
  });
  r = set(11, '승인');
  p = who('선수4');
  assert(r.league.added.join() === '선수11' && r.league.filled.join() === '둘째' && r.league.updated.length === 0 && r.league.players === 12 && who('둘째').wins === 0 && who('둘째').mmr === 4444
    && p.prefs.join() === '4,3,2,1' && p.baseMMR === 1234 && p.wins === 1, 'link: an approved player missing from the league is put back; players already there are left alone');

  // 운영진 페이지의 "선수단 다시 맞추기"
  r = post({ action: 'adminSyncPlayers', key: 'nope' }); assert(!r.ok && r.code === 'auth', 'link: syncing needs key');
  at = rev();
  r = sync();
  assert(r.ok && r.league.ok && r.league.added.length === 0 && r.league.filled.length === 0 && r.league.removed.length === 0 && r.league.players === 12 && rev() === at,
    'link: syncing when nothing is missing writes nothing');
  overwrite(lg => { lg.players = lg.players.filter(x => x.name !== '선수11'); });
  r = sync();
  assert(r.league.ok && r.league.filled.join() === '선수11' && r.league.added.length === 0 && r.league.players === 12 && rev() === at + 2, 'link: syncing puts every approved player who is missing into the league');
  // 봇은 팀을 짜기 직전에 sync 를 붙여 리그 기록을 받는다
  overwrite(lg => { lg.players = lg.players.filter(x => x.name !== '선수11'); });
  at = rev();
  r = post({ action: 'adminLeague', key });
  assert(r.league.players.length === 11 && r.rev === at, 'link: reading the league does not change it');
  r = post({ action: 'adminLeague', key, sync: true });
  assert(r.ok && r.league.players.length === 12 && r.league.players.some(x => x.name === '선수11') && r.rev === at + 1, 'link: reading with sync fills in missing approved players first (the bot does this before forming teams)');

  // 드라이브가 답하지 않을 때: 승인은 그대로 되고, 리그 기록은 건드리지 않는다. 없는 줄 알고 새로 쓰면 선수와 경기가 통째로 사라진다
  const getFile = S.env.DriveApp.getFileById;
  const fileId = S.props.LEAGUE_FILE_ID;
  let kept = S.files[fileId];
  reg(13); reg(14); reg(15); reg(16);
  at = rev();
  S.env.DriveApp.getFileById = () => { throw new Error('Service error: Drive'); };
  r = set(13, '승인');
  assert(r.ok && r.changed === 1 && rowOf(13)[C.status] === '승인' && r.league.ok === false && r.league.error && rev() === at && S.props.LEAGUE_FILE_ID === fileId && S.files[fileId] === kept,
    'link: drive not answering: the approval stands and the league is neither changed nor replaced by an empty one');
  S.env.DriveApp.getFileById = getFile;
  r = sync();
  assert(r.league.ok && r.league.filled.join() === '선수13' && r.league.players === 13 && got().league.matches.length === 1, 'link: the next sync puts that player in');
  kept = S.files[fileId];
  S.files[fileId] = '{broken';
  r = set(14, '승인');
  assert(r.changed === 1 && r.league.ok === false && S.files[fileId] === '{broken', 'link: a league file that cannot be read is not overwritten');
  S.files[fileId] = kept;
  r = sync();
  assert(r.league.ok && r.league.filled.join() === '선수14', 'link: once it reads again the player goes in');

  // 시트에서 값이 지워지거나 이상해진 줄
  rowOf(15)[C.nick] = '';
  r = set(15, '승인');
  assert(r.changed === 1 && r.league.ok && r.league.skipped.length === 1 && r.league.added.length === 0 && r.league.players === 14, 'link: a row whose nickname was erased is skipped (the manager refuses nameless players)');
  ['', '2.5', '서폿', '서폿'].forEach((v, i) => { rowOf(16)[C.p1 + i] = v; });
  r = set(16, '승인');
  assert(r.league.added.join() === '선수16' && who('선수16').prefs.join() === '4,1,2,3' && problem(got().league) === null, 'link: unreadable preferences are filled in so the manager still accepts the league');

  // 새 시즌을 시작하다 리그 기록을 비우지 못한 동안에는 넣지 않고 기다렸다가, 비운 뒤에 넣는다 (지난 시즌의 기록에 섞이지 않게)
  S.env.DriveApp.getFileById = id => Object.assign(getFile(id), { setContent() { throw new Error('드라이브 오류'); } });
  r = post({ action: 'adminNewSeason', key, season: '시즌 2', confirm: '시즌 변경' });
  assert(r.ok && JSON.parse(S.props.SEASONS)[1].leaguePending === true, 'link: (setup) the season started but the league could not be reset yet');
  reg(21);
  at = rev();
  r = set(21, '승인');
  assert(r.changed === 1 && r.league.ok === false && r.league.code === 'pending' && rev() === at && JSON.parse(S.files[fileId]).players.length === 15,
    'link: while the reset is pending the approval stands but last season\'s league is left alone');
  S.env.DriveApp.getFileById = getFile;
  post({ action: 'ping', key });
  g = got();
  assert(!('leaguePending' in JSON.parse(S.props.SEASONS)[1]) && g.league.players.length === 1 && g.league.players[0].name === '선수21' && g.league.matches.length === 0 && g.rev === at + 2,
    'link: when the reset finishes, the players approved meanwhile are put into the new league');
})();

// ── 리그 관리자마다 키를 따로 준다 (버전 11. 그때는 '운영진'이라고 불렀다). 리그 관리자 추가·끊기와 새 시즌 시작은 주인 키만, 누가 승인·제외했는지는 시트에 남긴다 ──
(() => {
  const crypto = require('crypto');
  const S = makeEnv({ fresh: true });
  const post = body => JSON.parse(S.env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
  const status = () => JSON.parse(S.env.doGet({ parameter: {} }).text);
  const clearRL = () => Object.keys(S.cache).filter(k => k.startsWith('rl:')).forEach(k => delete S.cache[k]);
  S.env.setup();
  const owner = S.props.ADMIN_KEY;
  const steamId = n => '7656119800000' + String(5000 + n);
  const reg = (n, extra = {}) => { clearRL(); return post({ action: 'register', nickname: '선수' + n, steam: 'https://steamcommunity.com/profiles/' + steamId(n), discord: 'user' + n, mmr: 3000 + n * 100, prefs: [1, 2, 3, 4], ...extra }); };
  const set = (key, ns, st) => post({ action: 'adminSetStatus', key, steamKeys: [].concat(ns).map(n => 's:' + steamId(n)), status: st });
  const C = { status: 2, nick: 3, key: 5, by: 14, byAt: 15 };
  const rowOf = n => S.tabs.find(t => t.getName().startsWith('선수등록')).grid.find(row => row[C.key] === 's:' + steamId(n));
  const log = () => (S.sheets['운영 기록'] ? S.sheets['운영 기록'].grid : []);
  const isDate = v => Object.prototype.toString.call(v) === '[object Date]';   // 서버 쪽에서 만든 Date 는 이 파일의 Date 와 틀이 달라 instanceof 로는 못 가린다
  const lastLog = () => log()[log().length - 1].slice(1).join('|');           // 시각을 뺀 나머지: 시즌|운영진|한 일|대상|내용
  for (let n = 1; n <= 6; n++) reg(n);

  let r = post({ action: 'ping', key: owner });
  assert(r.ok && r.role === 'owner' && r.name === '주인' && r.version >= 11, 'staff: the owner key is told it is the owner');
  r = post({ action: 'adminStaff', key: owner });
  assert(r.ok && r.staff.length === 0, 'staff: nobody but the owner at first');
  assert(post({ action: 'adminStaff', key: 'nope' }).code === 'auth' && post({ action: 'adminStaffAdd', key: 'nope', name: 'x' }).code === 'auth', 'staff: managing staff needs a key');

  // 운영진 추가: 키는 이때 한 번만 돌려주고, 서버에는 지문만 남는다
  r = post({ action: 'adminStaffAdd', key: owner, name: '  짱고  ' });
  const k1 = r.key, id1 = r.staff[0].id;
  assert(r.ok && /^[0-9a-f]{64}$/.test(k1) && k1 !== owner && r.name === '짱고' && r.staff.length === 1 && r.staff[0].name === '짱고' && r.staff[0].createdAt && r.staff[0].lastDay === ''
    && !('hash' in r.staff[0]) && !('key' in r.staff[0]), 'staff: adding returns that person\'s own key once');
  assert(!S.props.STAFF.includes(k1) && JSON.parse(S.props.STAFF)[0].hash === crypto.createHash('sha256').update(k1).digest('hex') && !JSON.stringify(S.props).replace(S.props.ADMIN_KEY, '').includes(k1),
    'staff: the server keeps only a fingerprint (SHA-256) of the key');
  assert(lastLog() === '시즌 1|주인|리그 관리자 추가|짱고|' && log()[0].join() === '시각,시즌,리그 관리자,한 일,대상,내용' && isDate(log()[1][0]), 'staff: adding is written to the log tab');
  // 버전 12까지 만들어진 탭의 머리글(운영진)은 다음에 기록을 남길 때 새 이름으로 고친다
  log()[0][2] = '운영진';
  r = post({ action: 'adminStaffAdd', key: owner, name: '머리글' });
  assert(r.ok && log()[0].join() === '시각,시즌,리그 관리자,한 일,대상,내용' && lastLog() === '시즌 1|주인|리그 관리자 추가|머리글|', 'staff: an old log tab gets the new column name');
  assert(post({ action: 'adminStaffRemove', key: owner, id: r.staff[r.staff.length - 1].id }).staff.length === 1, 'staff: (the extra one is removed again)');
  assert(!JSON.stringify(post({ action: 'adminStaff', key: owner })).includes(k1), 'staff: the key cannot be read back later');

  // 그 키로 할 수 있는 일: 등록 명단, 승인, 등록 열고 닫기, 리그 기록 (매니저도 이 키로 쓴다)
  r = post({ action: 'ping', key: k1 });
  assert(r.ok && r.role === 'staff' && r.name === '짱고' && r.registered === 6, 'staff: a staff key gets in, and is told who it is');
  assert(post({ action: 'adminList', key: k1 }).players.length === 6 && post({ action: 'adminLeagueRev', key: k1 }).ok && post({ action: 'adminRoster', key: k1 }).ok
    && post({ action: 'adminSyncPlayers', key: k1 }).ok, 'staff: reads and syncs work with a staff key');
  r = set(k1, 1, '승인');
  assert(r.ok && r.changed === 1 && r.by === '짱고' && r.league.ok && rowOf(1)[C.status] === '승인' && rowOf(1)[C.by] === '짱고' && isDate(rowOf(1)[C.byAt]),
    'staff: approving writes who did it and when on that row');
  assert(lastLog() === '시즌 1|짱고|승인|선수1|대기 → 승인', 'staff: and one line in the log tab');
  r = post({ action: 'adminList', key: owner });
  const one = r.players.find(p => p.nickname === '선수1'), two = r.players.find(p => p.nickname === '선수2');
  assert(one.by === '짱고' && !isNaN(Date.parse(one.byAt)) && two.by === '' && two.byAt === '', 'staff: the admin list carries who handled each registration');
  r = post({ action: 'saveLeague', key: k1, league: post({ action: 'adminLeague', key: k1 }).league, baseRev: post({ action: 'adminLeagueRev', key: k1 }).rev });
  assert(r.ok, 'staff: the league can be saved with a staff key (the manager uses it)');

  // 주인 키로만 하는 일
  let before = JSON.stringify([S.props.SEASONS, S.props.STAFF, S.tabs.length]);
  r = post({ action: 'adminNewSeason', key: k1, season: '시즌 2', confirm: '시즌 변경' });
  assert(!r.ok && r.code === 'owner' && /주인 키/.test(r.error) && status().season === '시즌 1', 'staff: a staff key cannot start a new season');
  assert(post({ action: 'adminStaff', key: k1 }).code === 'owner' && post({ action: 'adminStaffAdd', key: k1, name: '몰래' }).code === 'owner'
    && post({ action: 'adminStaffRemove', key: k1, id: id1 }).code === 'owner' && JSON.stringify([S.props.SEASONS, S.props.STAFF, S.tabs.length]) === before,
    'staff: a staff key cannot list, add or remove staff (nothing changes)');

  // 이름
  assert([' 짱 고 ', '짱고', '주인', '', '   ', 'x'.repeat(21)].every(name => post({ action: 'adminStaffAdd', key: owner, name }).code === 'name') && JSON.parse(S.props.STAFF).length === 1,
    'staff: a name must be given, short, and not already taken (spaces ignored; the owner\'s name too)');
  r = post({ action: 'adminStaffAdd', key: owner, name: '=1+1<b>' });
  const k2 = r.key, id2 = r.staff[1].id;
  assert(r.ok && r.name === '=1+1b' && r.staff.length === 2 && id2 !== id1 && k2 !== k1, 'staff: a second person gets a different key (angle brackets dropped from the name)');
  set(k2, 2, '제외');
  assert(rowOf(2)[C.by] === '=1+1b' && lastLog() === '시즌 1|=1+1b|제외|선수2|대기 → 제외', 'staff: a formula-like name is stored as text on the row and in the log');

  // 누가 바꿨는지: 상태가 실제로 바뀔 때만 적는다
  const at1 = rowOf(1)[C.byAt], lines = log().length;
  r = set(owner, 1, '승인');
  assert(r.changed === 1 && rowOf(1)[C.by] === '짱고' && rowOf(1)[C.byAt] === at1 && log().length === lines, 'staff: setting the same status again keeps the first handler and logs nothing');
  r = set(owner, [1, 3, 4], '승인');
  assert(r.changed === 3 && r.by === '주인' && rowOf(3)[C.by] === '주인' && rowOf(4)[C.by] === '주인' && rowOf(1)[C.by] === '짱고' && log().length === lines + 2
    && log().slice(-2).map(x => x.slice(2).join('|')).join(' / ') === '주인|승인|선수3|대기 → 승인 / 주인|승인|선수4|대기 → 승인', 'staff: a bulk change logs one line per player actually changed');
  set(k1, 3, '대기');
  assert(rowOf(3)[C.by] === '짱고' && lastLog() === '시즌 1|짱고|대기|선수3|승인 → 대기', 'staff: undoing an approval is logged with who did it');
  r = reg(3, { nickname: '셋째' });
  assert(r.ok && r.updated === true && rowOf(3)[C.nick] === '셋째' && rowOf(3)[C.by] === '짱고' && isDate(rowOf(3)[C.byAt]), 'staff: the player editing afterwards keeps the handler on the row');

  // 등록 열고 닫기, 시즌 이름, 서버 기록 덮어쓰기도 남긴다
  post({ action: 'adminConfig', key: k1, open: false });
  assert(lastLog() === '시즌 1|짱고|등록 닫기||', 'staff: closing registration is logged');
  const n1 = log().length;
  post({ action: 'adminConfig', key: k1, open: false });
  post({ action: 'adminConfig', key: k1, season: '시즌 1' });
  assert(log().length === n1, 'staff: settings that did not change are not logged');
  post({ action: 'adminConfig', key: owner, open: true, season: '가을 시즌' });
  assert(log().slice(-2).map(x => x.slice(1).join('|')).join(' / ') === '시즌 1|주인|등록 열기|| / 가을 시즌|주인|시즌 이름 고침|가을 시즌|시즌 1 → 가을 시즌', 'staff: opening and renaming are logged');
  const lg = post({ action: 'adminLeague', key: owner });
  post({ action: 'saveLeague', key: k1, league: lg.league, baseRev: lg.rev });
  const n2 = log().length;
  r = post({ action: 'saveLeague', key: k1, league: lg.league, baseRev: 0, force: true });
  assert(r.ok && log().length === n2 + 1 && /^가을 시즌\|짱고\|리그 기록 덮어쓰기\|\|선수 \d+명, 경기 0판으로 덮어씀$/.test(lastLog()), 'staff: overwriting a newer league on purpose is logged (ordinary saves are not)');

  // 마지막으로 쓴 날
  r = post({ action: 'adminStaff', key: owner });
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  assert(r.staff[0].lastDay === today && r.staff[1].lastDay === today, 'staff: the owner sees the day each key was last used');

  // 기록을 남기지 못해도 하던 일은 끝낸다
  const logTab = S.sheets['운영 기록'], getRange = logTab.getRange;
  logTab.getRange = () => { throw new Error('시트 오류'); };
  r = set(k1, 5, '승인');
  assert(r.ok && r.changed === 1 && rowOf(5)[C.status] === '승인' && rowOf(5)[C.by] === '짱고', 'staff: a failing log tab does not fail the approval');
  logTab.getRange = getRange;

  // 새 시즌: 주인 키로 시작하고, 운영진의 키는 시즌이 바뀌어도 그대로다
  r = post({ action: 'adminNewSeason', key: owner, season: '겨울 시즌', confirm: '시즌 변경' });
  assert(r.ok && r.season === '겨울 시즌' && r.role === 'owner' && log().some(x => x.slice(1).join('|') === '겨울 시즌|주인|새 시즌 시작|겨울 시즌|가을 시즌 → 겨울 시즌'), 'staff: the owner starts a season, and it is logged');
  assert(post({ action: 'ping', key: k1 }).name === '짱고' && S.tabs.filter(t => t.getName() === '운영 기록').length === 1, 'staff: staff keys and the log tab carry over to the new season');

  // 끊기: 그 키는 바로 쓸 수 없다
  assert(post({ action: 'adminStaffRemove', key: owner, id: 'nope' }).code === 'staff', 'staff: removing someone unknown is refused');
  r = post({ action: 'adminStaffRemove', key: owner, id: id1 });
  assert(r.ok && r.staff.length === 1 && r.staff[0].id === id2 && !('STAFF_SEEN_' + id1 in S.props) && lastLog() === '겨울 시즌|주인|리그 관리자 끊기|짱고|', 'staff: removing is logged and forgets that key');
  assert(post({ action: 'ping', key: k1 }).code === 'auth' && post({ action: 'adminList', key: k1 }).code === 'auth' && post({ action: 'saveLeague', key: k1, league: lg.league, baseRev: 0, force: true }).code === 'auth'
    && post({ action: 'ping', key: k2 }).ok, 'staff: a removed key stops working at once; the others keep working');
  r = post({ action: 'adminStaffAdd', key: owner, name: '짱고' });
  assert(r.ok && r.key !== k1 && post({ action: 'ping', key: k1 }).code === 'auth' && post({ action: 'ping', key: r.key }).name === '짱고', 'staff: adding the same person again gives a new key; the old one stays dead');

  // 틀린 키, 깨진 목록
  assert(['', 'short', k2.slice(0, 63), k2 + '0', k2.toUpperCase(), 'x'.repeat(5000), null, 12345, {}].every(key => post({ action: 'ping', key }).code === 'auth'), 'staff: near-miss, empty, huge or non-text keys are refused');
  const keep = S.props.STAFF;
  S.props.STAFF = '{broken';
  assert(post({ action: 'ping', key: k2 }).code === 'auth' && post({ action: 'ping', key: owner }).ok && post({ action: 'adminStaff', key: owner }).staff.length === 0, 'staff: a broken staff list locks staff out but never the owner');
  S.props.STAFF = keep;
  const pub = status();
  assert(!('role' in pub) && !('name' in pub) && !JSON.stringify(pub).includes('짱고'), 'staff: the public status says nothing about staff');
  for (let n = 0; JSON.parse(S.props.STAFF).length < 30; n++) post({ action: 'adminStaffAdd', key: owner, name: '운영진' + n });
  r = post({ action: 'adminStaffAdd', key: owner, name: '서른한번째' });
  assert(!r.ok && r.code === 'name' && JSON.parse(S.props.STAFF).length === 30 && S.props.STAFF.length < 9000, 'staff: at most thirty, and the list fits in one script property');
})();

// ── 지난 시즌에 다른 선수가 쓰던 닉네임은 그 선수만 다시 쓸 수 있다 (버전 12) ──
(() => {
  const S = makeEnv({ fresh: true });
  const post = body => JSON.parse(S.env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
  const clearRL = () => Object.keys(S.cache).filter(k => k.startsWith('rl:')).forEach(k => delete S.cache[k]);
  S.env.setup();
  const key = S.props.ADMIN_KEY;
  const steamId = n => '7656119800000' + String(8000 + n);
  const reg = (n, nickname, extra = {}) => { clearRL(); return post({ action: 'register', nickname, steam: 'https://steamcommunity.com/profiles/' + steamId(n), discord: 'nick' + n, mmr: 3000 + n, prefs: [1, 2, 3, 4], ...extra }); };
  const set = (ns, status) => post({ action: 'adminSetStatus', key, steamKeys: [].concat(ns).map(n => 's:' + steamId(n)), status });
  const season = name => post({ action: 'adminNewSeason', key, season: name, confirm: '시즌 변경' });
  const tab = name => S.sheets['선수등록 (' + name + ')'].grid;
  const C = { status: 2, nick: 3, key: 5 };
  const rowIn = (name, n) => tab(name).find(row => row[C.key] === 's:' + steamId(n));

  // 시즌 1: 꿀듀(1번)와 ZzangGo(2번)는 승인, 3번은 대기로 남고, 4번은 제외
  reg(1, '꿀듀'); reg(2, 'ZzangGo'); reg(3, '대기맨'); reg(4, '제외맨');
  set([1, 2], '승인'); set(4, '제외');
  season('시즌 2');

  let r = reg(5, '꿀듀');
  assert(!r.ok && r.code === 'nickname' && /지난 시즌에 다른 선수가 쓰던 닉네임/.test(r.error) && tab('시즌 2').length === 1, 'nick: a name an approved player used last season is refused to someone else (nothing written)');
  assert([' 꿀 듀 ', 'zzanggo', 'ZZANG GO', 'Zzang Go'].every(name => reg(5, name).code === 'nickname') && tab('시즌 2').length === 1, 'nick: spaces and capitals do not get around it');
  r = reg(5, '대기맨');
  assert(r.ok && rowIn('시즌 2', 5)[C.nick] === '대기맨', 'nick: a name that was only registered, never approved, is free (otherwise anyone could squat names)');
  r = reg(6, '제외맨');
  assert(r.ok, 'nick: an excluded registration does not hold its name either');

  // 원래 주인은 그대로 쓴다. 다른 닉네임으로 돌아와도 예전 닉네임은 그 사람의 것으로 남는다
  let reads = 0;
  const past1 = S.sheets['선수등록 (시즌 1)'], getRange = past1.getRange;
  past1.getRange = (...a) => { reads++; return getRange.apply(past1, a); };
  r = reg(1, '꿀듀');
  past1.getRange = getRange;
  assert(r.ok && r.returning === true && rowIn('시즌 2', 1)[C.nick] === '꿀듀' && reads === 1, 'nick: the original owner takes the name back (and last season\'s tab is read once for both checks)');
  r = reg(2, '짱고2');
  assert(r.ok && r.returning === true && reg(7, 'ZzangGo').code === 'nickname', 'nick: an owner who came back under a new name still holds the old one');
  r = reg(1, '꿀듀', { mmr: 4444 });
  assert(r.ok && r.updated === true, 'nick: editing other fields while keeping one\'s name is not asked again');
  r = reg(1, 'zzanggo');
  assert(!r.ok && r.code === 'nickname' && rowIn('시즌 2', 1)[C.nick] === '꿀듀', 'nick: an owner cannot switch to someone else\'s old name');
  r = reg(2, '꿀듀');
  assert(!r.ok && r.code === 'nickname' && /이미 쓰고 있는/.test(r.error), 'nick: a name taken this season gets the this-season message');
  // 스팀은 같은데 디스코드를 다르게 적은 원래 주인: 닉네임이 아니라 디스코드를 다시 확인하라는 안내가 나와야 한다
  set(6, '승인');                                       // 시즌 2에서는 6번(제외맨)만 승인된다. 2번(짱고2)은 대기로 남는다
  season('시즌 3');
  r = reg(2, 'ZzangGo', { discord: 'nick2_typo' });
  assert(!r.ok && r.code === 'conflict' && /디스코드 사용자명을 다시 확인/.test(r.error), 'nick: the owner with a mistyped discord is told to check the discord, not that the name is taken');

  // 시즌이 여러 번 지나도 묶여 있다. 시즌 2에서 승인된 닉네임도 묶인다
  assert(reg(8, '꿀듀').code === 'nickname' && reg(8, 'ZzangGo').code === 'nickname' && reg(8, '제외맨').code === 'nickname' && reg(8, '짱고2').ok,
    'nick: names stay held across several seasons (season 1 and season 2 alike); a name never approved (짱고2) is free');
  // 떠난 선수의 닉네임을 풀어 주려면 운영자가 그 시즌 탭의 닉네임 칸을 고친다
  rowIn('시즌 1', 2)[C.nick] = 'ZzangGo (떠남)';
  r = reg(9, 'ZzangGo');
  assert(r.ok, 'nick: the staff can release a name by editing it in the old season\'s tab');
  // 이 기능이 생기기 전에 서로 다른 시즌에 두 사람이 같은 닉네임으로 승인된 적이 있으면, 둘 다 쓸 수 있다(먼저 등록한 쪽이 갖는다)
  rowIn('시즌 2', 5)[C.nick] = '꿀듀'; rowIn('시즌 2', 5)[C.status] = '승인';
  r = reg(5, '꿀듀');
  assert(r.ok && reg(1, '꿀듀').code === 'nickname', 'nick: with two past owners either may use it; the first to register this season keeps it');
  // 지난 시즌의 탭이 지워졌으면 그 시즌의 닉네임은 더 묶이지 않는다
  S.tabs.splice(S.tabs.findIndex(t => t.getName() === '선수등록 (시즌 2)'), 1);
  S.tabs.splice(S.tabs.findIndex(t => t.getName() === '선수등록 (시즌 1)'), 1);
  r = reg(10, 'zzanggo (떠남)');
  assert(r.ok, 'nick: a deleted season tab holds nothing');
})();

// 새 시즌을 시작하려는 순간 드라이브가 답하지 않으면: 기록이 없는 것으로 치고 넘어가지 않고, 아무것도 바꾸지 않은 채 멈춘다
(() => {
  const S = makeEnv({ fresh: true });
  const post = body => JSON.parse(S.env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
  S.env.setup();
  const key = S.props.ADMIN_KEY;
  const league = { players: [{ id: 'p1', name: '가', baseMMR: 3000, mmr: 3100, prefs: [1, 2, 3, 4], wins: 1, losses: 0, streak: 1, roleCount: [1, 0, 0, 0, 0], discord: 'ga', steam: '' }],
    matches: [], settings: { k: 150, balanceTol: 300 } };
  post({ action: 'saveLeague', key, league, baseRev: 0 });
  const getFile = S.env.DriveApp.getFileById, before = JSON.stringify([S.props.SEASONS, S.tabs.map(t => t.getName()), S.props.LEAGUE_REV, S.files[S.props.LEAGUE_FILE_ID]]);
  // 드라이브가 한두 번 답하지 않아도 다시 읽어서 기록을 돌려준다 ("기록이 없다"로 답하면 매니저가 뒤처진 기록으로 서버를 덮어쓸 수 있다)
  let flaky = 2;
  S.env.DriveApp.getFileById = id => { if (flaky-- > 0) throw new Error('Service error: Drive'); return getFile(id); };
  const g = post({ action: 'adminLeague', key });
  assert(g.ok && g.league && g.league.players.length === 1 && g.rev === 1 && flaky < 0, 'drive failing twice: the league is read on the third try instead of being reported as missing');
  // 공개 기록 파일을 읽지 못하면 빈 파일을 새로 만들지 않고, 리그 기록에서 다시 걸러 낸다 (순위 페이지가 텅 비지 않게)
  const recId = S.props.RECORDS_FILE_ID, fileCount = Object.keys(S.files).length;
  const records = () => { delete S.cache.records; return JSON.parse(S.env.doGet({ parameter: { action: 'records' } }).text); };
  S.env.DriveApp.getFileById = id => { if (id === recId) throw new Error('Service error: Drive'); return getFile(id); };
  let pub = records();
  assert(pub.ok && pub.records.players.length === 1 && pub.records.players[0].mmr === 3100 && !('discord' in pub.records.players[0]) && pub.records.publishedAt
    && S.props.RECORDS_FILE_ID === recId && Object.keys(S.files).length === fileCount, 'public records file unreadable: served from the league (sanitized) instead of an empty new file');
  S.env.DriveApp.getFileById = () => { throw new Error('Service error: Drive'); };
  pub = records();
  assert(!pub.ok && !('records' in pub) && S.props.RECORDS_FILE_ID === recId && Object.keys(S.files).length === fileCount && !('records' in S.cache),
    'nothing readable at all: an error (the ranking page keeps what it had), still no empty file and nothing cached');
  let r = post({ action: 'adminNewSeason', key, season: '시즌 2', confirm: '시즌 변경' });
  assert(!r.ok && r.code === 'league' && /읽지 못해/.test(r.error) && JSON.stringify([S.props.SEASONS, S.tabs.map(t => t.getName()), S.props.LEAGUE_REV, S.files[S.props.LEAGUE_FILE_ID]]) === before,
    'new season while drive cannot be read: refused, and nothing has changed (the old season is not carried into the new one unarchived)');
  S.env.DriveApp.getFileById = getFile;
  r = post({ action: 'adminNewSeason', key, season: '시즌 2', confirm: '시즌 변경' });
  let list = JSON.parse(S.props.SEASONS), got = post({ action: 'adminLeague', key });
  assert(r.ok && r.season === '시즌 2' && JSON.parse(S.files[list[0].league]).players[0].mmr === 3100 && got.league.players.length === 0 && got.league.settings.k === 150,
    'new season once drive answers again: archived and reset as usual');
  // 비우는 일이 미뤄진 동안 지금 파일을 읽지 못해도, 설정은 보관해 둔 사본에서 이어받는다 (기본값으로 돌아가지 않는다)
  post({ action: 'saveLeague', key, league, baseRev: got.rev });
  S.env.DriveApp.getFileById = id => Object.assign(getFile(id), { setContent() { throw new Error('드라이브 오류'); } });
  r = post({ action: 'adminNewSeason', key, season: '시즌 3', confirm: '시즌 변경' });
  list = JSON.parse(S.props.SEASONS);
  const liveId = S.props.LEAGUE_FILE_ID;
  S.env.DriveApp.getFileById = id => { if (id === liveId) throw new Error('Service error: Drive'); return getFile(id); };
  post({ action: 'ping', key });
  got = JSON.parse(S.files[S.props.LEAGUE_FILE_ID]);
  assert(r.ok && list[2].leaguePending === true && !('leaguePending' in JSON.parse(S.props.SEASONS)[2]) && got.players.length === 0 && got.settings.k === 150 && got.settings.balanceTol === 300,
    'reset finished later while the live file cannot be read: the settings still come from the archived copy');
})();

// 버전 10으로 올린 뒤 첫 요청: 그때까지 승인돼 있던 선수를 선수단에 넣는다 (한 번만)
(() => {
  const S = makeEnv({ fresh: true });
  const post = body => JSON.parse(S.env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
  const status = () => JSON.parse(S.env.doGet({ parameter: {} }).text);
  S.env.setup();
  const key = S.props.ADMIN_KEY;
  [1, 2, 3].forEach(n => {
    Object.keys(S.cache).filter(k => k.startsWith('rl:')).forEach(k => delete S.cache[k]);
    post({ action: 'register', nickname: '옛선수' + n, steam: 'https://steamcommunity.com/profiles/7656119800000300' + n, discord: 'old' + n, mmr: 4000 + n, prefs: [1, 2, 3, 4] });
  });
  // 버전 9까지의 서버가 남긴 모양: 승인은 돼 있지만 선수단에는 들어간 적이 없다
  S.tabs[0].grid[1][2] = '승인'; S.tabs[0].grid[2][2] = '승인';
  delete S.props.LINKED;
  assert(post({ action: 'adminLeagueRev', key: 'nope' }).code === 'auth' && S.props.LINKED === '1', 'upgrade: the first request after the upgrade links the players (whatever the request is)');
  let g = post({ action: 'adminLeague', key });
  assert(g.rev === 1 && g.league.players.map(p => p.name).join() === '옛선수1,옛선수2' && g.league.players[1].mmr === 4002, 'upgrade: players approved before the upgrade are in the league');
  post({ action: 'saveLeague', key, league: { players: [g.league.players[0]], matches: [], settings: {} }, baseRev: 1 });
  status();
  g = post({ action: 'adminLeague', key });
  assert(g.rev === 2 && g.league.players.length === 1, 'upgrade: this happens once; later requests do not rewrite the league by themselves');
})();
