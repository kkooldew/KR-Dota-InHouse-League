/**
 * 봇의 팀 편성과 경기 결과 정산 (Node)
 *
 * 리그 매니저 파일에서 @engine 구역(팀 편성, 정산 로직)을 그대로 읽어 실행한다.
 * 로직을 여기로 옮겨 적지 않는 것은, 매니저와 봇이 서로 다른 팀을 짜거나 다르게 정산하는 일을 막기 위해서다.
 * 봇(bot.py)이 모집을 마감할 때, 그리고 /승리·/승리취소 때 이 파일을 실행한다.
 *
 * 입력 (표준 입력, JSON). league 는 서버의 리그 기록 {players, matches, settings}, now 는 지금 시각(ms, 비우면 실행 시각)
 *   팀 편성 (mode 없음)
 *     participants: 참가자의 선수 id
 *     busy:         결과를 아직 기록하지 않은 오늘 경기에 뛴 선수 id (오늘 뛴 사람으로 친다)
 *   경기 결과 기록 (mode: 'result')
 *     lanes:  [{r: 선수 id, d: 선수 id}] 1번부터 5번 자리 순서
 *     winner: 'r' 또는 'd'
 *   마지막 경기 되돌리기 (mode: 'undo')
 *     matchId: 되돌릴 경기 id (그 경기가 마지막 경기일 때만 되돌린다)
 * 출력 (표준 출력, JSON)
 *   팀 편성: {ok:true, lanes:[{role, r:{id,name,mmr,rank,win,lose}, d:{…}}], bench:[{id,name}], stats:{…}}
 *     rank는 그 자리가 선수의 몇 지망인지(0부터), win·lose는 이 편성 그대로 이기거나 졌을 때의 MMR 변동
 *     stats는 매니저의 보드에 보이는 값: sR·sD 팀 평균(자리 배율과 지망 반영), rawR·rawD 그대로 낸 평균, diff 팀 평균 차이, lead 앞선 팀('r'|'d'|''),
 *       sides 라인 합 [{lane, r, d, rRoles, dRoles}], chanceR 래디언트 기대 승률(%), below·firsts 3지망 이하·1지망 인원
 *   결과·되돌리기: {ok:true, league: 바뀐 리그 기록, match:{id,at,winner}, changes:[{id,name,side,role,before,delta,after}]}
 *   실패: {ok:false, error}
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

// 매니저의 기록을 그대로 올려놓고, mode 에 따라 매니저의 함수를 부른다
const DRIVER = `
var lanes = null;
(() => {
  state = { players: INPUT.league.players || [], matches: INPUT.league.matches || [],
            settings: Object.assign(defaultSettings(), INPUT.league.settings || {}) };
  // 정산한 뒤 서버에 되돌려 줄 기록. 설정은 받은 그대로 둔다(기본값을 섞어 넣지 않는다)
  const league = () => ({ players: state.players, matches: state.matches, settings: INPUT.league.settings || {} });
  const change = r => ({ id: r.id, name: r.name, side: r.side, role: r.role, before: r.before, delta: r.delta, after: r.before + r.delta });

  // 경기 결과 기록: 매니저의 승리 버튼과 같은 applyResult
  if (INPUT.mode === 'result') {
    if (INPUT.winner !== 'r' && INPUT.winner !== 'd') return { ok: false, error: '이긴 팀이 잘못됐습니다' };
    lanes = (INPUT.lanes || []).map((l, i) => ({ role: i + 1, r: l.r, d: l.d }));
    const ids = lanes.flatMap(l => [l.r, l.d]);
    if (lanes.length !== 5 || new Set(ids).size !== 10) return { ok: false, error: '팀 편성이 열 명이 아닙니다' };
    const gone = ids.filter(id => !byId(id));
    if (gone.length) return { ok: false, error: '팀에 있던 선수 ' + gone.length + '명이 지금 선수단에 없습니다. 매니저에서 기록해 주세요' };
    const match = applyResult(INPUT.winner === 'r', new Date(INPUT.now || Date.now()));
    return { ok: true, league: league(), match: { id: match.id, at: match.at, winner: match.winner }, changes: match.rows.map(change) };
  }

  // 마지막 경기 되돌리기: 매니저의 "마지막 경기 되돌리기"와 같은 dropLatest. matchId 를 주면 그 경기가 마지막일 때만 되돌린다
  if (INPUT.mode === 'undo') {
    const last = state.matches[0];
    if (!last) return { ok: false, error: '되돌릴 경기가 없습니다' };
    if (INPUT.matchId && last.id !== INPUT.matchId) return { ok: false, error: '그 뒤에 다른 경기가 기록돼 있어 되돌리지 않았습니다. 매니저에서 지워 주세요' };
    dropLatest();
    return { ok: true, league: league(), match: { id: last.id, at: last.at, winner: last.winner }, changes: last.rows.map(change) };
  }

  // 팀 편성: 매니저의 "팀 짜기" 버튼과 같은 순서. 출전 10명 고르기 → 가장 좋은 편성 → 진영 정하기
  const want = new Set(INPUT.participants || []);
  const pool = state.players.filter(p => want.has(p.id));              // 매니저처럼 선수단 순서로 늘어놓는다
  if (pool.length < 10) return { ok: false, error: '참가자 가운데 선수단에 있는 사람이 ' + pool.length + '명이라 팀을 짤 수 없습니다' };
  const today = playedToday(INPUT.now || Date.now());
  (INPUT.busy || []).forEach(id => today.add(id));
  const ten = chooseTen(pool, today);
  lanes = candToLanes(bestMatch(ten), ten);
  const st = laneStats();
  // 이기면·지면 받을 점수 미리 보기. 매니저의 보드(renderBoard)와 같은 계산이라, 이 편성 그대로 기록하면 정산 결과와 같다
  const rule = ruleOf();
  const ifR = computeDeltas(st.R, st.D, true, st.roles, rule, st.ranksR, st.ranksD);      // 래디언트가 이길 때
  const ifD = computeDeltas(st.R, st.D, false, st.roles, rule, st.ranksR, st.ranksD);     // 다이어가 이길 때
  const seat = (p, rank, win, lose) => ({ id: p.id, name: p.name, mmr: p.mmr, rank, win, lose: Math.max(-p.mmr, lose) });   // MMR은 0 아래로 내려가지 않는다
  const meet = (lane, side) => MATCHUPS.filter(m => m.lane === lane).map(m => m[side]);   // 그 라인에 서는 자리 번호
  const playing = new Set(ten.map(p => p.id));
  return {
    ok: true,
    lanes: lanes.map((l, i) => ({ role: l.role,
      r: seat(st.R[i], st.ranksR[i], ifR.r[i], ifD.r[i]), d: seat(st.D[i], st.ranksD[i], ifD.d[i], ifR.d[i]) })),
    bench: pool.filter(p => !playing.has(p.id)).map(p => ({ id: p.id, name: p.name })),
    stats: { sR: Math.round(st.sR), sD: Math.round(st.sD), rawR: Math.round(st.rawR), rawD: Math.round(st.rawD),
             // 차이는 화면에 보이는 두 평균(반올림한 값)을 뺀 것으로 한다. 반올림 전의 차이를 쓰면 "5230 대 5352, 차이 121"처럼 1이 어긋나 보인다
             diff: Math.abs(Math.round(st.sR) - Math.round(st.sD)), lead: st.sR > st.sD ? 'r' : st.sD > st.sR ? 'd' : '',
             sides: st.sides.map(s => ({ lane: s.lane, r: s.r, d: s.d, rRoles: meet(s.lane, 'r'), dRoles: meet(s.lane, 'd') })),
             chanceR: Math.round(ifR.eR * 100), below: st.below, firsts: st.firsts }
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
