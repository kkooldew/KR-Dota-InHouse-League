const fs = require('fs'), vm = require('vm');
const code = fs.readFileSync(require('path').join(__dirname, '..', 'apps-script', 'Code.gs'), 'utf8');

// opt.fresh: 탭이 하나도 없는 새 시트로 시작한다. 주지 않으면 버전 5까지의 시트처럼 '선수등록' 탭이 하나 있다
function makeEnv(opt = {}){
  const coerce = v => {               // Sheets: numeric-looking strings become numbers unless prefixed with '
    if (typeof v === 'string' && v.startsWith("'")) return v.slice(1);
    if (typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v)) return Number(v);
    return v;
  };
  const display = v => v instanceof Date ? v.toISOString().slice(0,19).replace('T',' ') : (v === '' || v == null ? '' : String(v));
  const tabs = [];                     // 탭을 왼쪽부터 순서대로
  let nextId = 0;
  // 시트 탭 하나. grid 는 줄마다 칸 값(raw)이다
  const makeSheet = name => {
    const grid = [], id = nextId;
    nextId += 101;
    let maxRows = 1000;
    const sheet = {
      grid, warnOnly: false,
      getName: () => name,
      setName(n){ if (tabs.some(t => t !== sheet && t.getName() === n)) throw new Error('A sheet with the name "' + n + '" already exists.'); name = n; return sheet; },
      getSheetId: () => id,
      getLastRow: () => grid.length,
      getMaxRows: () => maxRows,
      getMaxColumns: () => 26,
      insertRowsAfter(after, n){ maxRows += n; },
      insertColumnsAfter(){},
      setFrozenRows(){},
      clearContents(){ grid.length = 0; },
      protect(){ return { setWarningOnly(v){ sheet.warnOnly = v; return this; } }; },
      appendRow(line){ grid.push(line.map(coerce)); },
      getRange(r, c, nr = 1, nc = 1){
        if(r + nr - 1 > maxRows) throw new Error('The coordinates of the range are outside the dimensions of the sheet.');
        return {
          setValues(vals){ vals.forEach((row, i) => { while(grid.length < r + i) grid.push([]); row.forEach((v, j) => { grid[r-1+i][c-1+j] = coerce(v); }); }); return this; },
          setValue(v){ while(grid.length < r) grid.push([]); grid[r-1][c-1] = coerce(v); return this; },
          getValues(){ const out=[]; for(let i=0;i<nr;i++){ const row=[]; for(let j=0;j<nc;j++) row.push(grid[r-1+i]?.[c-1+j] ?? ''); out.push(row);} return out; },
          getDisplayValues(){ return this.getValues().map(row => row.map(display)); },
          getValue(){ return this.getValues()[0][0]; },
          getDisplayValue(){ return this.getDisplayValues()[0][0]; },
          setNumberFormat(){ return this; }, setFontWeight(){ return this; }
        };
      }
    };
    return sheet;
  };
  const byName = n => tabs.find(t => t.getName() === n) || null;
  const insertSheet = (name, index) => {
    if (byName(name)) throw new Error('A sheet with the name "' + name + '" already exists.');
    const sheet = makeSheet(name);
    tabs.splice(typeof index === 'number' ? index : tabs.length, 0, sheet);
    return sheet;
  };
  if (!opt.fresh) insertSheet('선수등록');
  const grid = opt.fresh ? null : tabs[0].grid;
  // sheets['탭 이름'] 으로 지금 그 이름을 가진 탭을 본다 (탭 이름이 바뀌면 따라간다)
  const sheets = new Proxy({}, {
    get: (_, n) => byName(n) || undefined,
    has: (_, n) => !!byName(n),
    ownKeys: () => tabs.map(t => t.getName()),
    getOwnPropertyDescriptor: (_, n) => byName(n) ? { enumerable: true, configurable: true, value: byName(n) } : undefined
  });
  const props = {}, cache = {}, files = {};
  // 가짜 드라이브 파일. trashed 는 휴지통에 들어간 파일의 id (지워지지는 않아서 그대로 읽고 쓸 수 있다)
  const fileNames = {}, trashed = new Set();
  const driveFile = id => ({
    getId: () => id, getName: () => fileNames[id] || '', setContent: c => { files[id] = c; }, getBlob: () => ({ getDataAsString: () => files[id] }),
    isTrashed: () => trashed.has(id), setTrashed(v){ if (v) trashed.add(id); else trashed.delete(id); return this; }
  });
  // 가짜 스팀: vanity 는 사용자 지정 주소 → 고유 번호, missing 은 없는 번호, down 이면 답하지 않는다, flaky 는 그 횟수만큼만 거절한다
  const steam = { vanity: {}, missing: new Set(), down: false, flaky: 0, calls: 0 };
  const env = {
    UrlFetchApp: { fetch: url => {
      steam.calls++;
      if (steam.down) throw new Error('timeout');
      if (steam.flaky > 0) { steam.flaky--; return { getResponseCode: () => 429, getContentText: () => 'Too Many Requests' }; }
      const m = url.match(/^https:\/\/steamcommunity\.com\/(profiles|id)\/([^/]+)\/\?xml=1$/);
      const id = !m ? '' : m[1] === 'profiles' ? (steam.missing.has(m[2]) ? '' : m[2]) : (steam.vanity[m[2].toLowerCase()] || '');
      const body = id ? '<profile><steamID64>' + id + '</steamID64></profile>'
        : '<response><error><![CDATA[The specified profile could not be found.]]></error></response>';
      return { getResponseCode: () => 200, getContentText: () => body };
    } },
    SpreadsheetApp: { getActiveSpreadsheet: () => ({ getSheetByName: byName, getSheets: () => tabs.slice(), insertSheet }) },
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => (k in props ? props[k] : null), setProperty: (k, v) => { props[k] = String(v); },
      deleteProperty: k => { delete props[k]; } }) },
    CacheService: { getScriptCache: () => ({ get: k => cache[k] ?? null, put: (k, v) => { cache[k] = v; } }) },
    LockService: { getScriptLock: () => ({ tryLock: () => true, releaseLock(){} }) },
    ContentService: { MimeType: { JSON: 'json' }, createTextOutput: t => ({ text: t, setMimeType(){ return this; } }) },
    Utilities: {
      getUuid: () => require('crypto').randomUUID(), sleep(){},
      // 실제 Apps Script 처럼 부호 있는 바이트(-128~127) 배열을 돌려준다
      DigestAlgorithm: { SHA_256: 'sha256' }, Charset: { UTF_8: 'utf8' },
      computeDigest: (alg, value, charset) => Array.from(require('crypto').createHash(alg).update(String(value), charset || 'latin1').digest()).map(b => (b > 127 ? b - 256 : b)),
      // 'yyyy-MM-dd HH:mm' 만 흉내 낸다 (한국 시간)
      formatDate: (d, tz, fmt) => new Date(d.getTime() + 9 * 3600e3).toISOString().slice(0, 16).replace('T', ' ')
    },
    DriveApp: {
      createFile: (name, content) => { const id = 'f' + Object.keys(files).length; files[id] = content; fileNames[id] = name; return driveFile(id); },
      getFileById: id => { if(!(id in files)) throw new Error('nf'); return driveFile(id); }
    },
    Logger: { log: (...a) => env._logs.push(a.join(' ')) }, _logs: [],
    console
  };
  vm.createContext(env);
  vm.runInContext(code, env);
  // tabs: 탭 목록(왼쪽부터). 탭을 지우는 시험은 이 배열에서 빼면 된다
  return { env, grid, props, cache, files, trashed, steam, sheets, tabs };
}
module.exports = makeEnv;
