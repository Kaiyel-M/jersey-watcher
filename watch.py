#!/usr/bin/env python3
"""
jersey-watcher v2 — agent + catalogue des maillots de Cristiano Ronaldo.

- Surveille des boutiques, détecte tout maillot de Cristiano (tous numéros),
  ignore le Ronaldo brésilien.
- Notifie sur Telegram (lien direct + description + lien vers ta page).
- Alimente une PAGE catalogue (docs/index.html) : classée par année / rareté,
  domicile/extérieur, photo, prix, description.
- Les maillots plus dispo passent dans l'onglet HISTORIQUE, avec leur historique
  de prix, pour comparer dans le temps.
Tourne gratuitement sur GitHub Actions ; la page est servie par GitHub Pages.
"""

import os, re, sys, json, time, html, hashlib, datetime
import requests

# Console Windows en cp1252 : éviter un crash sur les emoji des messages.
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass

CONFIG_PATH = "config.json"
DATA_PATH   = "data.json"        # base de tous les maillots (actifs + historiques)
SITE_PATH   = "docs/index.html"  # page servie par GitHub Pages
UA = {"User-Agent": "Mozilla/5.0 (compatible; jersey-watcher/2.0)"}
# UA "navigateur" pour les pages non-Shopify (certains WAF refusent les bots).
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
              "Accept-Language": "en-US,en;q=0.9"}
TIMEOUT = 20
MAX_PAGES = 15


# ---------- utils ----------
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def today(): return datetime.date.today().isoformat()


# ---------- détection Cristiano vs Ronaldo brésilien ----------
CR7_CLUBS = ["sporting", "manchester united", "man utd", "man united",
             "juventus", "juve", "al-nassr", "al nassr", "alnassr", "nassr", "portugal"]
R9_MARKERS = ["brazil", "brasil", "barcelona", "barça", "barca", "internazionale",
              "inter milan", "psv", "corinthians", "nazario", "nazário",
              "fenomeno", "fenômeno", " r9 "]
CR7_REAL_SEASONS = [str(y) for y in range(2009, 2019)] + \
    [f"{a:02d}-{a+1:02d}" for a in range(9, 18)] + [f"{a:02d}/{a+1:02d}" for a in range(9, 18)]

def is_cr7_shirt(title):
    t = " " + title.lower() + " "
    if "cristiano" in t: return True
    if "ronaldo" not in t: return False
    if any(m in t for m in R9_MARKERS): return False
    if any(c in t for c in CR7_CLUBS): return True
    if "real madrid" in t or "real " in t:
        return any(s in t for s in CR7_REAL_SEASONS)
    return False

def match_keywords(title, groups):
    t = title.lower()
    return any(all(k.lower() in t for k in g) for g in groups)

def title_matches(title, src):
    return is_cr7_shirt(title) if src.get("mode") == "cr7" else match_keywords(title, src.get("keywords", []))


# ---------- parsing : club, année, dom/ext, manches, version ----------
def club_of(t):
    t = t.lower()
    if "sporting" in t: return "Sporting CP"
    if "man" in t and ("united" in t or "utd" in t): return "Manchester United"
    if "real madrid" in t or ("real" in t and "madrid" in t): return "Real Madrid"
    if "juve" in t: return "Juventus"
    if "nassr" in t: return "Al-Nassr"
    if "portugal" in t: return "Portugal"
    return "?"

def year_of(t):
    m = re.search(r"(19|20)\d{2}", t)
    if m: return int(m.group(0))
    m = re.search(r"\b(\d{2})[-/](\d{2})\b", t)   # 02-03 -> 2002
    if m:
        yy = int(m.group(1)); return 2000 + yy if yy < 50 else 1900 + yy
    return None

def homeaway_of(t):
    t = t.lower()
    if any(w in t for w in ["third", "3rd", "3e"]): return "Third"
    if any(w in t for w in ["away", "exterieur", "extérieur", "visiteur"]): return "Extérieur"
    if any(w in t for w in ["home", "domicile", " local"]): return "Domicile"
    return "?"

def sleeve_of(t):
    t = t.lower()
    if any(w in t for w in ["long sleeve", "long-sleeve", "manches longues", " l/s", " ls "]): return "Manches longues"
    return ""

def version_of(t):
    t = t.lower()
    if any(w in t for w in ["player issue", "player version", "player edition", "match issue", "match version",
                            "match worn", "matchworn", "on-field", "on field", "formotion", "adizero", "techfit",
                            "heat.rdy", "vaporknit", "vapor", "dri-fit adv", "authentic", "match prepared", "player spec"]):
        return "Version joueur"
    return "Rétail"


# ---------- rareté (heuristique ajustable) ----------
def base_rarity(club, year):
    if club == "Sporting CP": return 95
    if club == "Manchester United":
        if year in (2007, 2008): return 90
        if year and year <= 2009: return 80
        return 56                       # 2e passage 2021-2023
    if club == "Real Madrid":
        if year == 2009: return 86      # 1re saison, n°9
        if year in (2013, 2017): return 78
        if year and year <= 2013: return 72
        return 68
    if club == "Juventus": return 63
    if club == "Al-Nassr": return 45
    if club == "Portugal":
        if year == 2016: return 88      # Euro gagné
        if year in (2004, 2006): return 80
        if year == 2026: return 74      # 1er Puma, sans doute son dernier tournoi
        if year and year <= 2014: return 66
        return 58
    return 50

def rarity(club, year, ha, sleeve, version):
    s = base_rarity(club, year)
    if ha == "Extérieur": s += 6
    if ha == "Third": s += 8
    if sleeve: s += 5
    if version == "Version joueur": s += 10
    s = max(1, min(100, s))
    tier = "S" if s >= 88 else "A" if s >= 76 else "B" if s >= 60 else "C"
    return s, tier

ERA_NOTE = {
    ("Sporting CP", 2002): "Sa vraie 1re saison pro — le n°28, le plus rare.",
    ("Sporting CP", 2003): "Le maillot de l'amical qui a convaincu Ferguson.",
    ("Manchester United", 2007): "Saison du 1er Ballon d'Or et du doublé PL/C1.",
    ("Manchester United", 2008): "Saison de la C1 et du Mondial des clubs.",
    ("Real Madrid", 2009): "Sa 1re saison au Real — le rare n°9.",
    ("Real Madrid", 2013): "La Décima.",
    ("Real Madrid", 2017): "Dernière saison, 3e C1 d'affilée.",
    ("Portugal", 2004): "Débuts en tournoi, n°17.",
    ("Portugal", 2016): "Le maillot du sacre à l'Euro — le Graal.",
    ("Portugal", 2026): "1er maillot Puma en Mondial, sans doute son dernier tournoi.",
}
def describe(club, year, ha, sleeve, version):
    bits = [b for b in [club, str(year) if year else "", ha if ha != "?" else "", sleeve, version if version != "Rétail" else ""] if b]
    head = " · ".join(bits)
    note = ERA_NOTE.get((club, year), "")
    return f"{head}. {note}".strip()


# ---------- Telegram ----------
def notify(text):
    tok, chat = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not tok or not chat:
        print("!! TG_TOKEN/TG_CHAT_ID manquants :\n" + text + "\n"); return
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": text, "parse_mode": "HTML"}, timeout=TIMEOUT)
        if r.status_code != 200: print("!! Telegram", r.status_code, r.text[:200])
    except Exception as e: print("!! Telegram", e)

def alert_new(it, page_url, kind="NOUVEAU"):
    price = f"{it['price']:.0f} {it['currency']}" if it.get("price") else "prix ?"
    tag = "💸 BAISSE DE PRIX" if kind == "DROP" else ("🟢 BON PRIX" if it.get("good_deal") else "👕 NOUVEAU")
    star = "★" * {"S": 4, "A": 3, "B": 2, "C": 1}.get(it.get("tier", "C"), 1)
    msg = (f"{tag} — {price}  [{star} rareté {it.get('tier','?')}]\n"
           f"<b>{html.escape(it['title'])}</b>\n{html.escape(it.get('desc',''))}\n"
           f"🔗 Annonce : {it['url']}")
    if page_url: msg += f"\n📚 Ton catalogue : {page_url}"
    notify(msg)


# ---------- récup Shopify ----------
def fetch_shopify(base, coll):
    out, page = [], 1
    while page <= MAX_PAGES:
        url = (f"{base}/collections/{coll}/products.json?limit=250&page={page}" if coll
               else f"{base}/products.json?limit=250&page={page}")
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        if r.status_code != 200: raise RuntimeError(f"HTTP {r.status_code}")
        batch = r.json().get("products", [])
        if not batch: break
        out += batch; page += 1
    return out

def scan_shopify(src):
    """Retourne {id: item_dict} des maillots Cristiano trouvés sur ce shop."""
    base = src["base"].rstrip("/"); cur = src.get("currency", "")
    items = {}
    try:
        products = fetch_shopify(base, src.get("collection"))
    except Exception as e:
        print(f"   {src['name']}: {e} (bascule en 'pages' si besoin)"); return None
    for p in products:
        title = p.get("title", "")
        if not title_matches(title, src): continue
        prices, avail = [], False
        for v in p.get("variants", []):
            try: prices.append(float(v.get("price")))
            except (TypeError, ValueError): pass
            if v.get("available"): avail = True
        price = min(prices) if prices else None
        cap = src.get("max_price")
        if cap is not None and price is not None and price > cap: continue
        img = ""
        imgs = p.get("images") or []
        if imgs: img = imgs[0].get("src", "")
        elif p.get("featured_image"): img = p["featured_image"]
        yr = year_of(title); club = club_of(title); ha = homeaway_of(title)
        sl = sleeve_of(title)
        body = re.sub("<[^>]+>", " ", p.get("body_html") or "")
        tags = " ".join(p.get("tags")) if isinstance(p.get("tags"), list) else (p.get("tags") or "")
        ver = version_of(f"{title} {body} {tags}")
        sc, tier = rarity(club, yr, ha, sl, ver)
        iid = f"{src['name']}:{p.get('id')}"
        items[iid] = {
            "id": iid, "source": src["name"], "title": title,
            "url": f"{base}/products/{p.get('handle')}", "image": img,
            "price": price, "currency": cur, "available": avail,
            "club": club, "year": yr, "home_away": ha, "sleeve": sl, "version": ver,
            "rarity": sc, "tier": tier, "desc": describe(club, yr, ha, sl, ver),
        }
    return items


# ---------- surveillance de pages (sites non-Shopify) ----------
# Liens à ignorer (navigation, réseaux sociaux) et liens "produit" à conserver.
SKIP_HREF = ("/cart", "/account", "/login", "/register", "/policies", "/blogs",
             "/pages/", "javascript:", "mailto:", "tel:", "facebook.com",
             "instagram.com", "twitter.com", "x.com", "tiktok.com", "youtube.com",
             "/wishlist", "/compare", "/checkout", "/contact", "/faq")
KEEP_HREF = ("/product", "/products/", "/item", "/buy", "/shop/", "-shirt",
             "ronaldo", ".html", "/lot", "/itm/", "/dp/", "/p/")

def page_signature(html_text, url):
    """Empreinte 'liste de produits' d'une page : ensemble trié des liens produits.
    Un nouvel article -> nouveau lien -> empreinte différente. Repli sur le texte."""
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    keep = []
    for h in re.findall(r'href=["\']([^"\'>]+)', html_text):
        hl = h.lower()
        if any(s in hl for s in SKIP_HREF): continue
        if not (h.startswith("/") or host in hl): continue
        if any(k in hl for k in KEEP_HREF):
            keep.append(h.split("?")[0].split("#")[0])
    keep = sorted(set(keep))
    if len(keep) >= 3:
        return hashlib.sha1("\n".join(keep).encode("utf-8", "ignore")).hexdigest(), len(keep)
    # repli : empreinte du texte visible normalisé (scripts/styles retirés)
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_text, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip().lower()
    return hashlib.sha1(txt.encode("utf-8", "ignore")).hexdigest(), 0

def fetch_page_sig(url):
    r = requests.get(url, headers=BROWSER_UA, timeout=TIMEOUT)
    if r.status_code != 200: raise RuntimeError(f"HTTP {r.status_code}")
    return page_signature(r.text, url)

def alert_page(name, url, page_url):
    msg = (f"🔔 <b>{html.escape(name)}</b> — la page a changé\n"
           f"Probable nouvel arrivage CR7 à vérifier.\n🔗 {url}")
    if page_url: msg += f"\n📚 {page_url}"
    notify(msg)


# ---------- page HTML ----------
PAGE = r"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Catalogue maillots CR7</title>
<style>
:root{--bg:#0c0e12;--panel:#161b24;--line:#2a323f;--ink:#eef1f6;--muted:#9aa3b2;--gold:#e6bd50}
*{box-sizing:border-box;margin:0}body{background:var(--bg);color:var(--ink);font-family:Inter,system-ui,Arial,sans-serif;padding:0 0 60px}
.wrap{max-width:1000px;margin:0 auto;padding:0 16px}
h1{font-size:26px;padding:28px 0 4px}.sub{color:var(--muted);font-size:13px;margin-bottom:18px}
.tabs{display:flex;gap:8px;margin-bottom:12px}
.tabs button,.ctrl{background:var(--panel);border:1px solid var(--line);color:var(--muted);border-radius:99px;padding:8px 14px;font-size:13px;cursor:pointer}
.tabs button.on{background:var(--gold);color:#12140f;border-color:var(--gold);font-weight:600}
.ctrls{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
.ctrl{-webkit-appearance:none}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}
.card img{width:100%;height:190px;object-fit:cover;background:#0f1318}
.noimg{width:100%;height:190px;display:flex;align-items:center;justify-content:center;color:#3b4451;font-size:13px}
.body{padding:12px 13px;display:flex;flex-direction:column;gap:7px;flex:1}
.top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tier{font-weight:700;font-size:12px;border-radius:6px;padding:1px 7px}
.tS{background:#e6bd50;color:#12140f}.tA{background:#c7923b;color:#12140f}.tB{background:#3b4658;color:#dfe4ec}.tC{background:#2a323f;color:#9aa3b2}
.chip{font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:6px;padding:1px 7px}
.club{font-weight:600;font-size:15px;line-height:1.2}.desc{font-size:12px;color:var(--muted);flex:1}
.price{font-size:17px;font-weight:700}.cmp{font-size:11px;color:var(--muted)}
.src{font-size:11px;color:#6b7382}
.links{display:flex;gap:8px;margin-top:4px}
a.btn{flex:1;text-align:center;text-decoration:none;font-size:12.5px;padding:8px;border-radius:8px;background:var(--gold);color:#12140f;font-weight:600}
.hist{font-size:11px;color:var(--muted);border-top:1px solid var(--line);padding-top:6px;margin-top:2px}
.empty{color:#6b7382;text-align:center;padding:40px 0}
.section{margin-bottom:20px;border:1px solid var(--line);border-left:4px solid var(--acc,var(--line));border-radius:14px;overflow:hidden}
.shead{display:flex;align-items:center;gap:11px;padding:13px 16px;border-bottom:1px solid var(--line)}
.sdot{width:12px;height:12px;border-radius:99px;flex:0 0 auto}
.stitle{font-weight:700;font-size:16px;letter-spacing:.02em}
.ssub{color:var(--muted);font-size:12.5px}
.scount{margin-left:auto;color:var(--muted);font-size:12.5px;font-weight:600}
.sbody{padding:14px 16px}
</style></head><body><div class="wrap">
<h1>Catalogue maillots <span style="color:var(--gold)">CR7</span></h1>
<div class="sub" id="sub"></div>
<div class="tabs">
  <button id="tab-active" class="on" onclick="setTab('active')">En vente</button>
  <button id="tab-gone" onclick="setTab('gone')">Historique (prix)</button>
</div>
<div class="ctrls">
  <select class="ctrl" id="sort" onchange="render()">
    <option value="rarity">Trier : rareté</option>
    <option value="year">Trier : année</option>
    <option value="price">Trier : prix</option>
  </select>
  <select class="ctrl" id="club" onchange="render()"><option value="">Tous les clubs</option></select>
  <select class="ctrl" id="ha" onchange="render()">
    <option value="">Dom + Ext</option><option>Domicile</option><option>Extérieur</option><option>Third</option>
  </select>
  <select class="ctrl" id="ver" onchange="render()">
    <option value="">Toutes versions</option><option value="Version joueur">Version joueur</option><option value="Rétail">Supporter</option>
  </select>
</div>
<div id="content"></div>
</div>
<script>
const DATA = __DATA__;
let TAB='active';
const items=Object.values(DATA.items||{});
const clubs=[...new Set(items.map(i=>i.club).filter(c=>c&&c!=='?'))].sort();
const csel=document.getElementById('club');
clubs.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c;csel.appendChild(o)});
function groupKey(i){return i.club+'|'+i.year+'|'+i.home_away}
function setTab(t){TAB=t;document.getElementById('tab-active').classList.toggle('on',t==='active');
  document.getElementById('tab-gone').classList.toggle('on',t==='gone');render()}
function fnum(n){return n==null?'?':Number(n).toLocaleString('fr-FR')}
const TIER_META={S:{t:'Mythiques',c:'#e6bd50',bg:'rgba(230,189,80,.10)'},A:{t:'Rares',c:'#c7923b',bg:'rgba(199,146,59,.10)'},B:{t:'Recherchés',c:'#5b6b86',bg:'rgba(91,107,134,.13)'},C:{t:'Courants',c:'#3a4453',bg:'rgba(58,68,83,.16)'}};
function cardHTML(i,g){
  const g2=g[groupKey(i)]||[]; const cmp=g2.length>1?`<div class="cmp">${g2.length} offres même saison : ${fnum(Math.min(...g2))}–${fnum(Math.max(...g2))} ${i.currency||''}</div>`:'';
  const img=i.image?`<img src="${i.image}" loading="lazy" alt="">`:`<div class="noimg">pas de photo</div>`;
  const hist=(TAB==='gone'&&i.history)?`<div class="hist">Historique prix : ${i.history.map(h=>`${fnum(h.price)}${i.currency||''} (${h.date})`).join(' → ')}<br>Vu pour la dernière fois : ${i.last_seen||'?'}</div>`:'';
  const price=i.price?`${fnum(i.price)} ${i.currency||''}`:'prix ?';
  const deal=i.good_deal?`<span class="chip" style="color:#7bd88f;border-color:#2e5a3a">bon prix</span>`:'';
  return `<div class="card">${img}<div class="body">
    <div class="top"><span class="tier t${i.tier}">${i.tier} · ${i.rarity}</span>
      ${i.home_away&&i.home_away!=='?'?`<span class="chip">${i.home_away}</span>`:''}
      ${i.sleeve?`<span class="chip">${i.sleeve}</span>`:''}
      ${i.version==='Version joueur'?`<span class="chip">Version joueur</span>`:''}${deal}</div>
    <div class="club">${i.club} ${i.year||''}</div>
    <div class="desc">${i.desc||i.title}</div>
    <div class="price">${price}</div>${cmp}
    <div class="src">${i.source}</div>
    <div class="links"><a class="btn" href="${i.url}" target="_blank" rel="noopener">Voir l'annonce</a></div>
    ${hist}</div></div>`;
}
function sectionHTML(sec,g){
  const cards=`<div class="grid">${sec.items.map(i=>cardHTML(i,g)).join('')}</div>`;
  if(sec.title==null) return cards;
  const acc=sec.color||'#5b6b86', bg=sec.bg||'rgba(120,132,150,.10)';
  return `<div class="section" style="--acc:${acc}">
    <div class="shead" style="background:${bg}"><span class="sdot" style="background:${acc}"></span><span class="stitle">${sec.title}</span>${sec.sub?`<span class="ssub">${sec.sub}</span>`:''}<span class="scount">${sec.items.length} maillot${sec.items.length>1?'s':''}</span></div>
    <div class="sbody">${cards}</div></div>`;
}
function render(){
  const sort=document.getElementById('sort').value, fc=document.getElementById('club').value, fh=document.getElementById('ha').value, fv=document.getElementById('ver').value;
  let list=items.filter(i=> TAB==='active'? i.available!==false : i.available===false);
  if(fc)list=list.filter(i=>i.club===fc); if(fh)list=list.filter(i=>i.home_away===fh); if(fv)list=list.filter(i=>i.version===fv);
  const g={}; items.filter(i=>i.available!==false&&i.price).forEach(i=>{(g[groupKey(i)]=g[groupKey(i)]||[]).push(i.price)});
  const act=items.filter(i=>i.available!==false).length, gone=items.filter(i=>i.available===false).length;
  document.getElementById('sub').textContent=`${act} en vente · ${gone} archivés · mis à jour ${DATA.updated||''}`;
  const box=document.getElementById('content');
  if(!list.length){box.innerHTML='<div class="empty">Rien ici pour le moment. Le catalogue se remplira au fil des trouvailles.</div>';return}
  let sections;
  if(sort==='rarity'){
    sections=['S','A','B','C'].map(t=>({title:'Rareté '+t,sub:TIER_META[t].t,color:TIER_META[t].c,bg:TIER_META[t].bg,
      items:list.filter(i=>i.tier===t).sort((a,b)=>b.rarity-a.rarity)})).filter(s=>s.items.length);
  }else if(sort==='year'){
    const ys=[...new Set(list.map(i=>i.year).filter(Boolean))].sort((a,b)=>a-b);
    sections=ys.map(y=>({title:String(y),color:'#6b7688',bg:'rgba(120,132,150,.10)',items:list.filter(i=>i.year===y).sort((a,b)=>b.rarity-a.rarity)}));
    const nay=list.filter(i=>!i.year); if(nay.length)sections.push({title:'Année inconnue',color:'#6b7688',bg:'rgba(120,132,150,.10)',items:nay});
  }else{
    sections=[{title:null,items:list.slice().sort((a,b)=>(a.price||1e9)-(b.price||1e9))}];
  }
  box.innerHTML=sections.map(s=>sectionHTML(s,g)).join('');
}
render();
</script></body></html>"""

def build_site(data, page_url):
    dataj = json.dumps(data, ensure_ascii=False)
    out = PAGE.replace("__DATA__", dataj)
    d = os.path.dirname(SITE_PATH)
    if d: os.makedirs(d, exist_ok=True)
    with open(SITE_PATH, "w", encoding="utf-8") as f: f.write(out)


# ---------- main ----------
def main():
    cfg = load_json(CONFIG_PATH, {})
    page_url = cfg.get("page_url", "")
    data = load_json(DATA_PATH, {"items": {}})
    db = data["items"]
    first_run = not db

    seen_now, alerts = set(), []
    for src in cfg.get("shopify", []):
        print(f">> {src['name']}")
        found = scan_shopify(src)
        if found is None:  # échec réseau : on ne touche pas au statut de ce shop
            for iid, it in db.items():
                if it["source"] == src["name"]: seen_now.add(iid)
            continue
        for iid, it in found.items():
            seen_now.add(iid)
            old = db.get(iid)
            if not old:
                it["first_seen"] = today(); it["last_seen"] = today()
                it["history"] = [{"date": today(), "price": it["price"]}]
                # bon prix ? (sous la médiane des mêmes saisons déjà connues)
                same = [o["price"] for o in db.values() if o.get("price") and o.get("club")==it["club"] and o.get("year")==it["year"]]
                if it["price"] and same:
                    same.sort(); med = same[len(same)//2]
                    it["good_deal"] = it["price"] < med*0.9
                db[iid] = it
                if not first_run: alerts.append((it, "NEW"))
            else:
                old["last_seen"] = today(); old["available"] = it["available"]
                for k in ("price","image","desc","rarity","tier","home_away","year","club"): old[k] = it[k]
                last = old["history"][-1]["price"] if old.get("history") else None
                if it["price"] is not None and it["price"] != last:
                    old.setdefault("history", []).append({"date": today(), "price": it["price"]})
                    if last is not None and it["price"] < last and not first_run:
                        alerts.append((old, "DROP"))

    # réconciliation : maillots connus mais absents ce run -> plus dispo (historique)
    for iid, it in db.items():
        if iid not in seen_now and it.get("available") is not False:
            it["available"] = False; it["last_seen"] = it.get("last_seen", today())

    # surveillance des pages non-Shopify (alerte au changement de contenu)
    pstate = data.setdefault("pages_state", {})
    page_alerts = []
    for pg in cfg.get("pages", []):
        name, url = pg.get("name"), pg.get("url")
        if not url: continue
        print(f">> [page] {name}")
        try:
            sig, count = fetch_page_sig(url)
        except Exception as e:
            print(f"   {name}: {e} (page ignorée ce run)"); continue
        st = pstate.get(name)
        if not st:  # 1re observation -> on mémorise la base, pas d'alerte
            pstate[name] = {"sig": sig, "count": count, "url": url,
                            "first_seen": today(), "last_change": today(), "last_checked": today()}
        else:
            st["last_checked"] = today(); st["url"] = url
            if sig != st.get("sig"):
                st["sig"] = sig; st["count"] = count; st["last_change"] = today()
                if not first_run: page_alerts.append((name, url))

    data["updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    save_json(DATA_PATH, data)
    build_site(data, page_url)

    for it, kind in alerts:
        alert_new(it, page_url, kind)
        print(f"   {kind}:", it["title"])

    for name, url in page_alerts:
        alert_page(name, url, page_url)
        print("   PAGE CHANGÉE:", name)

    if first_run:
        notify(f"🟢 Catalogue CR7 armé. J'ai indexé {len(db)} maillot(s) et je surveille "
               f"{len(pstate)} page(s) partenaire(s). Je te préviens dès qu'il y a du nouveau."
               + (f"\n📚 {page_url}" if page_url else ""))
    print(f"Terminé. {len(db)} au catalogue, {len(pstate)} page(s) suivie(s), "
          f"{len(alerts)+len(page_alerts)} alerte(s).")


if __name__ == "__main__":
    main()
