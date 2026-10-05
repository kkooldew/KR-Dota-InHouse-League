const makeEnv = require('./gas-harness');
const { env, grid, props, cache } = makeEnv();
const post = body => JSON.parse(env.doPost({ postData: { contents: JSON.stringify(body) } }).text);
const get = action => JSON.parse(env.doGet({ parameter: action ? { action } : {} }).text);
const assert = (c, m) => { if(!c){ console.log('FAIL', m); process.exitCode = 1; } else console.log('ok  ', m); };
const clearRL = () => Object.keys(cache).filter(k => k.startsWith('rl:')).forEach(k => delete cache[k]);

env.setup();
const key = props.ADMIN_KEY;
assert(key && key.length >= 32, 'setup creates admin key');
assert(grid[0][3] === '닉네임', 'header row created');

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
assert(grid[2][3] === '=HYPERLINK("x")' && grid[2][5] === 'id:myvanity', 'formula-like nickname stored as text, vanity key lowercased');

const bad = [
  [{ steam: 'https://store.steampowered.com/app/570' }, 'steam'],
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

r = post({ action:'adminSetStatus', key, steamKeys:['s:76561197990650432','id:myvanity'], status:'승인' });
assert(r.ok && r.changed === 2 && grid[1][2] === '승인' && grid[2][2] === '승인', 'bulk approve');
clearRL();
r = post({ ...base, mmr: 6400, nickname: '불멸의소환사2' });
assert(r.ok && grid[1][2] === '승인', 'resubmit keeps approval status');

r = post({ action:'adminConfig', key, open:false, season:'시즌 2' });
assert(r.ok && r.open === false && r.season === '시즌 2', 'close registration');
clearRL();
r = post({ ...base }); assert(!r.ok && r.code === 'closed', 'registration closed rejects');
r = get('status'); assert(r.ok && r.open === false && r.registered === 2, 'public status');

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
r = post({ action:'unknown' }); assert(!r.ok, 'unknown action');
r = JSON.parse(env.doPost({ postData:{ contents:'not json' } }).text); assert(!r.ok, 'bad body');
