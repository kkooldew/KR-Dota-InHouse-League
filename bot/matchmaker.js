/**
 * 봇의 자동 팀 편성 (Node)
 *
 * 리그 매니저 파일에서 @engine 구역(팀 편성 로직)을 그대로 읽어 실행한다.
 * 로직을 여기로 옮겨 적지 않는 것은, 매니저와 봇이 서로 다른 팀을 짜는 일을 막기 위해서다.
 * 봇(bot.py)이 모집을 마감할 때 이 파일을 실행한다.
 *
 * 입력 (표준 입력, JSON)
 *   league:       매니저가 서버에 올려 둔 기록 {players, matches, settings}
 *   participants: 참가자의 선수 id
 *   busy:         결과를 아직 기록하지 않은 오늘 경기에 뛴 선수 id (오늘 뛴 사람으로 친다)
 *   now:          지금 시각(ms). 비우면 실행 시각
 * 출력 (표준 출력, JSON)
 *   {ok:true, lanes:[{role, r:{id,name,mmr,rank}, d:{…}}], bench:[{id,name}], stats:{…}} 또는 {ok:false, error}
 *   rank는 그 자리가 선수의 몇 지망인지(0부터)
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { performance } = require('perf_hooks');

const MANAGER = path.join(__dirname, '..', 'manager', 'InhouseLeagueManager_v0_18.html');

function loadEngine(file = MANAGER) {
  const html = fs.readFileSync(file, 'utf8');
  const blocks = [];
  const re = /\/\* @engine:start[\s\S]*?\*\/([\s\S]*?)\/\* @engine:end \*\//g;
  for (let m; (m = re.exec(html)); ) blocks.push(m[1]);
  if (blocks.length < 3) throw new Error('매니저 파일에서 팀 편성 로직(@engine 구역)을 찾지 못했습니다: ' + file);
  return blocks.join('\n');
}

// 매니저의 "팀 짜기" 버튼과 같은 순서: 출전 10명 고르기 → 가장 좋은 편성 → 진영 정하기
const DRIVER = `
var lanes = null;
(() => {
  state = { players: INPUT.league.players || [], matches: INPUT.league.matches || [],
            settings: Object.assign(defaultSettings(), INPUT.league.settings || {}) };
  const want = new Set(INPUT.participants || []);
  const pool = state.players.filter(p => want.has(p.id));              // 매니저처럼 선수단 순서로 늘어놓는다
  if (pool.length < 10) return { ok: false, error: '참가자 가운데 선수단에 있는 사람이 ' + pool.length + '명이라 팀을 짤 수 없습니다' };
  const today = playedToday(INPUT.now || Date.now());
  (INPUT.busy || []).forEach(id => today.add(id));
  const ten = chooseTen(pool, today);
  lanes = candToLanes(bestMatch(ten), ten);
  const st = laneStats();
  const seat = (p, rank) => ({ id: p.id, name: p.name, mmr: p.mmr, rank });
  const playing = new Set(ten.map(p => p.id));
  return {
    ok: true,
    lanes: lanes.map((l, i) => ({ role: l.role, r: seat(st.R[i], st.ranksR[i]), d: seat(st.D[i], st.ranksD[i]) })),
    bench: pool.filter(p => !playing.has(p.id)).map(p => ({ id: p.id, name: p.name })),
    stats: { sR: Math.round(st.sR), sD: Math.round(st.sD), rawR: Math.round(st.rawR), rawD: Math.round(st.rawD),
             diff: Math.round(st.diff), below: st.below, firsts: st.firsts }
  };
})()`;

function makeMatch(input, file = MANAGER) {
  const ctx = vm.createContext({ console, performance, INPUT: input });
  vm.runInContext(loadEngine(file), ctx, { filename: 'engine' });
  return vm.runInContext(DRIVER, ctx, { filename: 'driver' });
}

module.exports = { makeMatch, loadEngine, MANAGER };

if (require.main === module) {
  let text = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', c => { text += c; });
  process.stdin.on('end', () => {
    let out;
    try { out = makeMatch(JSON.parse(text), process.argv[2] || MANAGER); }
    catch (err) { out = { ok: false, error: String((err && err.message) || err) }; }
    process.stdout.write(JSON.stringify(out));
  });
}
