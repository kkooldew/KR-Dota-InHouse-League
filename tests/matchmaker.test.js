// 봇의 자동 팀 편성 테스트: 매니저 파일의 @engine 구역을 그대로 읽어 팀을 짜는지 확인한다.
//   node tests/matchmaker.test.js
const { makeMatch, loadEngine } = require('../bot/matchmaker');
const assert = (c, m) => { if(!c){ console.log('FAIL', m); process.exitCode = 1; } else console.log('ok  ', m); };

const KST = (y, mo, d, h, mi) => Date.UTC(y, mo - 1, d, h - 9, mi);
const NOW = KST(2026, 10, 7, 21, 0);                      // 10월 7일 오후 9시
const player = (n, mmr, prefs, games = 0) => ({ id: 'p' + n, name: '선수' + n, baseMMR: mmr, mmr, prefs,
  wins: Math.ceil(games / 2), losses: Math.floor(games / 2), streak: 0, roleCount: [0, 0, 0, 0, 0], discord: 'user' + n, steam: '' });
// 1지망이 캐리 2, 미드 2, 오프 2, 서폿 4로 딱 맞는 열 명
const FIRSTS = [1, 1, 2, 2, 3, 3, 4, 4, 4, 4];
const rest = f => [1, 2, 3, 4].filter(x => x !== f);
const ten = () => FIRSTS.map((f, i) => player(i + 1, 3000 + i * 150, [f, ...rest(f)]));
const match = (at, ids) => ({ id: 'm' + at, at: new Date(at).toISOString(), winner: 'r',
  rows: ids.map((id, i) => ({ id, name: id, side: i < 5 ? 'r' : 'd', role: (i % 5) + 1, rank: 0, before: 3000, delta: 0 })) });
const run = (players, opt = {}) => makeMatch({ league: { players, matches: opt.matches || [], settings: opt.settings || {} },
  participants: opt.participants || players.map(p => p.id), busy: opt.busy || [], now: NOW });
const playing = r => r.lanes.flatMap(l => [l.r.id, l.d.id]);
const benched = r => r.bench.map(p => p.id).sort().join();

const engine = loadEngine();
assert(['function bestMatch', 'function chooseTen', 'function candToLanes', 'function playedToday', 'const DEFAULT_SETTINGS', 'const gamesOf']
  .every(s => engine.includes(s)), '매니저 파일에서 팀 편성 로직을 읽는다');
assert(!/document\.|\$\(|localStorage/.test(engine), '읽어 온 로직에 화면을 건드리는 코드가 없다');

let r = run(ten());
assert(r.ok && r.lanes.length === 5 && r.lanes.map(l => l.role).join() === '1,2,3,4,5', '열 명이면 다섯 자리씩 두 팀');
assert(new Set(playing(r)).size === 10 && r.bench.length === 0, '열 명 모두 한 번씩 들어간다');
assert(r.stats.firsts === 10 && r.stats.below === 0 && r.lanes.every(l => l.r.rank === 0 && l.d.rank === 0), '모두 1지망 자리를 받을 수 있으면 그렇게 짠다');
assert(JSON.stringify(run(ten())) === JSON.stringify(r), '같은 입력이면 같은 편성');
assert(Math.abs(r.stats.rawR - r.stats.rawD) < 400, '두 팀 평균이 크게 벌어지지 않는다: ' + r.stats.rawR + ' 대 ' + r.stats.rawD);

r = run(ten().slice(0, 9));
assert(!r.ok && /9명/.test(r.error), '아홉 명이면 짜지 않는다');
r = run(ten(), { participants: ['p1', 'p2', 'nobody'] });
assert(!r.ok && /2명/.test(r.error), '선수단에 없는 참가자는 세지 않는다');

// 열두 명: 오늘 뛴 사람이 가장 뒤로 밀린다 (총 판수가 더 적어도)
const twelve = () => [...ten(), player(11, 3600, [1, 2, 3, 4]), player(12, 3700, [2, 1, 3, 4])].map(p => Object.assign(p, { wins: 5, losses: 5 }));
let ps = twelve();
ps[0].wins = 0; ps[0].losses = 1;                         // p1: 총 1판뿐이지만 오늘 뛰었다
ps[1].wins = 1; ps[1].losses = 1;                         // p2: 총 2판, 오늘 뛰었다
r = run(ps, { matches: [match(KST(2026, 10, 7, 20, 0), ['p1', 'p2'])] });
assert(r.ok && benched(r) === 'p1,p2', '오늘 뛴 두 명이 쉰다: ' + benched(r));

// 오늘 뛴 사람이 없으면 예전처럼 총 판수가 적은 사람부터
ps = twelve();
ps[10].wins = 9; ps[10].losses = 9; ps[11].wins = 8; ps[11].losses = 8;
r = run(ps);
assert(r.ok && benched(r) === 'p11,p12', '오늘 뛴 사람이 없으면 총 판수가 많은 두 명이 쉰다: ' + benched(r));

// 하루는 오전 6시에 바뀐다
ps = twelve();
r = run(ps, { matches: [match(KST(2026, 10, 7, 5, 30), ['p3', 'p4']), match(KST(2026, 10, 7, 6, 30), ['p5', 'p6'])] });
assert(r.ok && benched(r) === 'p5,p6', '오전 6시 전의 경기는 어제로 친다: ' + benched(r));

// 봇이 넘기는 busy(결과를 아직 기록하지 않은 오늘 경기)도 오늘 뛴 것으로 친다
ps = twelve();
r = run(ps, { busy: ['p7', 'p8'] });
assert(r.ok && benched(r) === 'p7,p8', '아직 기록하지 않은 오늘 경기에 뛴 사람도 쉰다: ' + benched(r));

// 오늘 뛴 사람이 세 명인데 두 자리만 빼면 될 때: 그 셋 가운데 총 판수가 적은 사람이 뛴다
ps = twelve();
ps[6].wins = 1; ps[6].losses = 0;                         // p7: 오늘 뛰었고 총 1판
r = run(ps, { busy: ['p7', 'p8', 'p9'] });
assert(r.ok && benched(r) === 'p8,p9', '오늘 뛴 사람끼리는 총 판수가 적은 사람이 먼저: ' + benched(r));

// 순번이 같아 다 넣을 수 없으면 균형으로 고른다 (누가 빠지든 열 명이 들어가고 두 명이 쉰다)
r = run(twelve());
assert(r.ok && r.bench.length === 2 && new Set(playing(r)).size === 10, '순번이 모두 같으면 균형이 맞는 열 명을 고른다');
