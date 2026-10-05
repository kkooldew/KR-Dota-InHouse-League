/* 리그 사이트 공용 스크립트: 설정 기본값, 머리·꼬리, 서버 요청 */
(function(){
  const L = window.LEAGUE = Object.assign({
    title: '도타 2 인하우스 리그', apiUrl: '', discordInvite: '', prizeNote: '', refreshSeconds: 120
  }, window.LEAGUE || {});
  L.apiUrl = String(L.apiUrl || '').trim();

  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const PREF_LABEL = ['', '캐리', '미드', '오프', '서폿'];   // 지망 번호 1~4. 서폿은 4번과 5번을 함께 뜻한다

  const NOT_JSON = '서버 응답을 읽지 못했습니다. Apps Script 웹 앱을 "모든 사용자"가 쓸 수 있게 배포했는지 확인해 주세요.';

  async function call(url, init){
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 20000);
    let res;
    try{
      res = await fetch(url, Object.assign({signal: ctrl.signal, cache: 'no-store'}, init));
    }catch(err){
      throw new Error(err.name === 'AbortError' ? '서버가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.' : '서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.');
    }finally{
      clearTimeout(timer);
    }
    let j;
    try{ j = await res.json(); }catch(err){ throw new Error(NOT_JSON); }
    if(!j || !j.ok){
      const e = new Error((j && j.error) || '서버에서 요청을 처리하지 못했습니다.');
      e.code = j && j.code;
      throw e;
    }
    return j;
  }

  const api = {
    ready: /^https:\/\/script\.google(usercontent)?\.com\//.test(L.apiUrl),
    get(action){
      return call(L.apiUrl + (L.apiUrl.includes('?') ? '&' : '?') + 'action=' + encodeURIComponent(action) + '&v=' + Date.now());
    },
    // text/plain으로 보내야 브라우저가 미리 묻는 요청 없이 바로 보낸다 (Apps Script는 그 요청을 받지 못한다)
    post(body){
      return call(L.apiUrl, {method: 'POST', headers: {'Content-Type': 'text/plain;charset=utf-8'}, body: JSON.stringify(body)});
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
  function toast(msg){
    let t = document.getElementById('toast');
    if(!t){
      t = document.createElement('div');
      t.id = 'toast'; t.className = 'toast'; t.setAttribute('role', 'status'); t.setAttribute('aria-live', 'polite');
      document.body.appendChild(t);
    }
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
  }

  window.Site = {L, esc, api, mountChrome, setSeason, toast, PREF_LABEL};
})();
