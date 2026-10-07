/* 리그 사이트 공용 스크립트: 설정 기본값, 머리·꼬리, 서버 요청 */
(function(){
  const L = window.LEAGUE = Object.assign({
    title: '도타 2 인하우스 리그', apiUrl: '', discordInvite: '', refreshSeconds: 120
  }, window.LEAGUE || {});
  L.apiUrl = String(L.apiUrl || '').trim();

  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const PREF_LABEL = ['', '캐리', '미드', '오프', '서폿'];   // 지망 번호 1~4. 서폿은 4번과 5번을 함께 뜻한다

  const NOT_JSON = '서버 응답을 읽지 못했습니다. Apps Script 웹 앱을 "모든 사용자"가 쓸 수 있게 배포했는지 확인해 주세요.';
  // 구글 서버는 가끔 요청을 처리하고도 그 답을 전해 주지 못한다(2026-10-08에 실제 서버에서 마흔 번에 네 번꼴로 봤다):
  //  - 답 대신 "페이지를 찾을 수 없음" 화면이 온다
  //  - 답을 찾지 못해 웹 앱 주소로 되돌려 보내고, 브라우저가 그것을 따라가 요청과 상관없는 공개 상태(ok: true)를 받는다
  // 둘 다 "답을 받지 못했다"로 본다. 요청이 서버에서 처리됐는지는 알 수 없다(code 가 없는 오류로 낸다).
  const LOST = '서버의 답을 받지 못했습니다. 잠시 후 다시 시도해 주세요.';
  // 공개 상태(doGet 의 답)의 모양: version 은 있는데 운영진에게만 주는 registered 가 없다. POST 의 답은 이런 모양일 수 없다
  const strayStatus = j => !!j && j.ok === true && 'version' in j && !('registered' in j);

  // wait: 답을 기다리는 시간(ms). 새 시즌 시작처럼 서버가 여러 일을 한꺼번에 하는 요청은 더 길게 준다
  async function call(url, init, wait){
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), wait || 20000);
    let res;
    try{
      res = await fetch(url, Object.assign({signal: ctrl.signal, cache: 'no-store'}, init));
    }catch(err){
      throw new Error(err.name === 'AbortError' ? '서버가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.' : '서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.');
    }finally{
      clearTimeout(timer);
    }
    let j;
    // 구글 로그인 화면으로 넘어갔으면 배포 설정 문제고, 그 밖의 읽지 못한 답은 구글 쪽의 일시적인 문제다
    try{ j = await res.json(); }catch(err){ throw new Error(/accounts\.google\.com/.test(res.url || '') ? NOT_JSON : LOST); }
    if(!j || !j.ok){
      const e = new Error((j && j.error) || '서버에서 요청을 처리하지 못했습니다.');
      e.code = j && j.code;
      throw e;
    }
    return j;
  }

  const api = {
    ready: /^https:\/\/script\.google(usercontent)?\.com\//.test(L.apiUrl),
    // 읽기는 다시 보내도 되므로, 답을 받지 못했으면 한 번 더 물어본다
    async get(action){
      const url = () => L.apiUrl + (L.apiUrl.includes('?') ? '&' : '?') + 'action=' + encodeURIComponent(action) + '&v=' + Date.now();
      const once = async () => {
        const j = await call(url());
        if(action === 'records' && !(j.records && Array.isArray(j.records.players))) throw new Error(LOST);   // 기록 대신 상태가 온 경우
        return j;
      };
      try{ return await once(); }
      catch(err){ if(err.code || err.message !== LOST) throw err; return once(); }
    },
    // text/plain으로 보내야 브라우저가 미리 묻는 요청 없이 바로 보낸다 (Apps Script는 그 요청을 받지 못한다)
    async post(body, wait){
      const j = await call(L.apiUrl, {method: 'POST', headers: {'Content-Type': 'text/plain;charset=utf-8'}, body: JSON.stringify(body)}, wait);
      if(strayStatus(j)) throw new Error(LOST);
      return j;
    }
  };

  function mountChrome(active, season){
    const head = document.getElementById('site-head');
    if(head){
      head.className = 'site-head';
      head.innerHTML =
        '<div class="wrap">' +
          '<a class="brand" href="index.html"><b>' + esc(L.title) + '</b><span class="season" id="seasonTag" hidden></span></a>' +
          '<nav class="site-nav" aria-label="사이트">' +
            '<a href="index.html"' + (active === 'register' ? ' aria-current="page"' : '') + '>선수 등록</a>' +
            '<a href="ranking.html"' + (active === 'ranking' ? ' aria-current="page"' : '') + '>순위와 경기 기록</a>' +
          '</nav>' +
        '</div>';
    }
    const foot = document.getElementById('site-foot');
    if(foot){
      foot.className = 'site-foot';
      foot.innerHTML = '<div class="wrap"><span>' + esc(L.title) + '</span>' +
        '<span>' + (L.discordInvite ? '<a href="' + esc(L.discordInvite) + '" target="_blank" rel="noopener">디스코드</a> &nbsp; ' : '') +
        '<a href="admin.html">운영진</a></span></div>';
    }
    if(season) setSeason(season);
  }
  function setSeason(season){
    const tag = document.getElementById('seasonTag');
    if(!tag) return;
    tag.textContent = season || '';
    tag.hidden = !season;
  }

  let toastTimer;
  // ms: 보여 주는 시간. 읽을 내용이 긴 알림은 더 길게 준다
  function toast(msg, ms){
    let t = document.getElementById('toast');
    if(!t){
      t = document.createElement('div');
      t.id = 'toast'; t.className = 'toast'; t.setAttribute('role', 'status'); t.setAttribute('aria-live', 'polite');
      document.body.appendChild(t);
    }
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, ms || 3200);
  }

  window.Site = {L, esc, api, mountChrome, setSeason, toast, PREF_LABEL};
})();
