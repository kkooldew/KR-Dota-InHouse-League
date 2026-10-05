const fs = require('fs'), vm = require('vm');
const code = fs.readFileSync(require('path').join(__dirname, '..', 'apps-script', 'Code.gs'), 'utf8');

function makeEnv(){
  const grid = []; // rows of cells (raw)
  const fmtText = v => (typeof v === 'string' && v.startsWith("'")) ? v.slice(1) : v;
  const coerce = v => {               // Sheets: numeric-looking strings become numbers unless prefixed with '
    if (typeof v === 'string' && v.startsWith("'")) return v.slice(1);
    if (typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v)) return Number(v);
    return v;
  };
  const display = v => v instanceof Date ? v.toISOString().slice(0,19).replace('T',' ') : (v === '' || v == null ? '' : String(v));
  const sheet = {
    getName: () => '선수등록',
    getLastRow: () => grid.length,
    getMaxRows: () => 1000,
    setFrozenRows(){},
    appendRow(line){ grid.push(line.map(coerce)); },
    getRange(r, c, nr = 1, nc = 1){
      return {
        setValues(vals){ vals.forEach((row, i) => { while(grid.length < r + i) grid.push([]); row.forEach((v, j) => { grid[r-1+i][c-1+j] = coerce(v); }); }); return this; },
        setValue(v){ while(grid.length < r) grid.push([]); grid[r-1][c-1] = coerce(v); return this; },
        getValues(){ const out=[]; for(let i=0;i<nr;i++){ const row=[]; for(let j=0;j<nc;j++) row.push(grid[r-1+i]?.[c-1+j] ?? ''); out.push(row);} return out; },
        getDisplayValues(){ return this.getValues().map(row => row.map(display)); },
        setNumberFormat(){ return this; }, setFontWeight(){ return this; }
      };
    }
  };
  const props = {}, cache = {}, files = {};
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
    SpreadsheetApp: { getActiveSpreadsheet: () => ({ getSheetByName: () => sheet, insertSheet: () => sheet }) },
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => (k in props ? props[k] : null), setProperty: (k, v) => { props[k] = String(v); } }) },
    CacheService: { getScriptCache: () => ({ get: k => cache[k] ?? null, put: (k, v) => { cache[k] = v; } }) },
    LockService: { getScriptLock: () => ({ tryLock: () => true, releaseLock(){} }) },
    ContentService: { MimeType: { JSON: 'json' }, createTextOutput: t => ({ text: t, setMimeType(){ return this; } }) },
    Utilities: { getUuid: () => require('crypto').randomUUID(), sleep(){} },
    DriveApp: {
      createFile: (name, content) => { const id = 'f' + Object.keys(files).length; files[id] = content; return { getId: () => id, setContent: c => { files[id] = c; }, getBlob: () => ({ getDataAsString: () => files[id] }) }; },
      getFileById: id => { if(!(id in files)) throw new Error('nf'); return { getId: () => id, setContent: c => { files[id] = c; }, getBlob: () => ({ getDataAsString: () => files[id] }) }; }
    },
    Logger: { log: (...a) => env._logs.push(a.join(' ')) }, _logs: [],
    console
  };
  vm.createContext(env);
  vm.runInContext(code, env);
  return { env, grid, props, cache, files, steam };
}
module.exports = makeEnv;
