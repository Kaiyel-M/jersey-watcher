# jersey-watcher — agent + catalogue maillots Cristiano Ronaldo

Un agent qui **surveille des boutiques**, te **notifie sur Telegram** dès qu'un maillot de Cristiano sort (tous numéros : 28, 17, 9, 7 — et il ignore le Ronaldo brésilien), et **alimente une page catalogue** classée par **année** et par **rareté**. Les maillots plus dispo passent dans un **onglet Historique** avec leur historique de prix, pour comparer dans le temps. Tourne gratuitement sur **GitHub Actions** ; la page est servie par **GitHub Pages**.

## Ce qu'il fait
- Notif Telegram : **lien direct + description + rareté + lien vers ta page**. Alertes spéciales **baisse de prix** et **bon prix** (sous la médiane des mêmes saisons déjà vues).
- Page `docs/index.html` : cartes avec **photo, club, année, dom/ext, version joueur, prix**, tri par **rareté / année / prix**, filtres club et dom/ext, et **comparaison de prix par saison**.
- Onglet **Historique** : les maillots partis, avec leur courbe de prix.
- `data.json` = ta base (tout est mémorisé, donc pas de spam et historique conservé).

## Mise en route

### 1. Bot Telegram
- @BotFather → `/newbot` → récupère le **token**. Écris à ton bot, puis ouvre `https://api.telegram.org/bot<TOKEN>/getUpdates` pour lire ton **chat_id** (ou @userinfobot).

### 2. Repo GitHub
- Crée un repo (public conseillé pour Pages gratuit), dépose ces fichiers en gardant l'arborescence (`.github/workflows/`, `docs/`).

### 3. Secrets
- Settings → Secrets and variables → Actions → New secret : `TG_TOKEN`, `TG_CHAT_ID`.

### 4. Activer la page (GitHub Pages)
- Settings → **Pages** → Source : **Deploy from a branch** → branche `main`, dossier **/docs** → Save.
- Ton adresse : `https://TON-USER.github.io/TON-REPO/`. Colle-la dans `config.json` → `page_url`.

### 5. Régler les cibles — `config.json`
- `mode: "cr7"` : rien à faire pour la détection, il attrape tout Cristiano.
- `currency` : symbole affiché. `max_price` : plafond (null = aucun).
- Vérifie qu'un shop est Shopify : ouvre `LE-SHOP/products.json` (si JSON → `shopify`, sinon → `pages`).

### 6. Lancer
- Onglet Actions → active → **Run workflow** (1er run = base, pas de spam + message d'armement).
- Ensuite : tout seul toutes les 20 min. Ouvre ta page Pages quand tu veux.

## Test local
```bash
pip install -r requirements.txt
export TG_TOKEN=... ; export TG_CHAT_ID=...
python watch.py      # génère data.json + docs/index.html ; ouvre docs/index.html
```

## Régler la rareté
Tout est dans `base_rarity()` de `watch.py` (Sporting/United 07-09 au sommet, Al-Nassr en bas) + bonus extérieur / manches longues / version joueur. Ajuste les chiffres à ta guise.

## Idées d'extensions (à la demande)
- eBay / Vinted (recherche sauvegardée native pour démarrer, API ensuite).
- Marquer sur la page ce que tu possèdes déjà (relié à ton tracker) + « candidats à l'upsell ».
- Normalisation des devises pour comparer £/$/€ à égalité.
- Digest hebdo des nouveautés et variations de prix.
