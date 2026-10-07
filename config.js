/* 리그 사이트 설정. 여기 적는 값은 누구나 볼 수 있으니 운영진 키 같은 비밀 값은 넣지 마세요. */
window.LEAGUE = {
  title: '도타 2 인하우스 리그',

  // 구글 Apps Script 웹 앱 주소. 배포한 뒤 받은 https://script.google.com/macros/s/…/exec 주소를 넣으세요.
  // 비워 두면 등록 페이지는 닫혀 있고, 순위 페이지는 같은 폴더의 records.json을 읽습니다.
  apiUrl: 'https://script.google.com/macros/s/AKfycbyoBYQAyMa_fnnOBx0kv4c6wluJ7sLnan4YkATY_sbwAzAovdumIi-e34mhRRqmBJuB/exec',

  // 등록을 마친 사람에게 보여 줄 디스코드 초대 링크
  discordInvite: 'https://discord.gg/CHmUMHweRq',

  // 순위 페이지가 새 기록을 확인하는 간격(초)
  refreshSeconds: 120
};
