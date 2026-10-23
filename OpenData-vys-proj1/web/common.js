/* Společné pomůcky pro obě stránky */
const D = window.DATA;

function chybaDat() {
  document.querySelector("main").innerHTML =
    '<div class="error"><h2>Chybí data</h2><p>Soubor <code>web/data.js</code> nebyl nalezen. ' +
    'Vložte stažená CSV do složky <code>data/</code> a spusťte <code>python3 prepare_data.py</code>. ' +
    'Postup je v souboru README.md.</p></div>';
}

const fmt = (n, d = 1) => (n == null || isNaN(n)) ? "–" :
  n.toLocaleString("cs-CZ", { minimumFractionDigits: d, maximumFractionDigits: d });

const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

const prumer = (a) => a.length ? a.reduce((s, x) => s + x, 0) / a.length : NaN;

function dozitiHodnota(o, pohlavi) {
  if (pohlavi === "muzi") return o.muzi;
  if (pohlavi === "zeny") return o.zeny;
  return (o.muzi + o.zeny) / 2;
}

/* Kultura: když máme počty obyvatel, počítáme na 10 000 obyvatel, jinak absolutní počet */
const kulturaHodnota = (o) => (D.meta.maPrepocet && o.na10k != null) ? o.na10k : o.kultura;
const kulturaJednotka = () => D.meta.maPrepocet ? "kulturních míst na 10 000 obyvatel" : "kulturních míst (počet)";

function pearson(xs, ys) {
  const n = xs.length, mx = prumer(xs), my = prumer(ys);
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) {
    sxy += (xs[i] - mx) * (ys[i] - my);
    sxx += (xs[i] - mx) ** 2;
    syy += (ys[i] - my) ** 2;
  }
  return sxy / Math.sqrt(sxx * syy);
}

function regrese(xs, ys) {
  const mx = prumer(xs), my = prumer(ys);
  let sxy = 0, sxx = 0;
  for (let i = 0; i < xs.length; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; }
  const b = sxy / sxx;
  return { a: my - b * mx, b };
}

function popisR(r) {
  const s = Math.abs(r);
  const sila = s < 0.1 ? "téměř žádná" : s < 0.3 ? "slabá" : s < 0.5 ? "střední" : s < 0.7 ? "silná" : "velmi silná";
  const smer = s < 0.1 ? "" : (r > 0 ? " kladná" : " záporná");
  return sila + smer;
}

/* Rozdělí okresy podle kultury do 4 stejně velkých skupin (od nejméně po nejvíc) */
function kvartily(okresy) {
  const s = [...okresy].sort((a, b) => kulturaHodnota(a) - kulturaHodnota(b));
  const n = s.length, skupiny = [[], [], [], []];
  s.forEach((o, i) => skupiny[Math.min(3, Math.floor(i * 4 / n))].push(o));
  return skupiny;
}

function chartDefaults() {
  Chart.defaults.font.family = '"Atkinson Hyperlegible","Segoe UI",system-ui,sans-serif';
  Chart.defaults.font.size = 13;
  Chart.defaults.color = css("--muted");
  Chart.defaults.borderColor = css("--line");
}

function navigace(aktualni) {
  document.getElementById("nav").innerHTML =
    '<strong>Kultura a délka života v okresech ČR</strong><nav>' +
    `<a href="index.html" ${aktualni === "index" ? 'aria-current="page"' : ""}>Přehled</a>` +
    `<a href="pomery.html" ${aktualni === "pomery" ? 'aria-current="page"' : ""}>Poměry</a></nav>`;
}
