# À faire (pour Claude Code)

Déployer cet agent pour qu'il tourne tout seul et publie la page catalogue.

1. **Tester en local d'abord** : `pip install -r requirements.txt` puis `python watch.py`
   → doit générer `data.json` + `docs/index.html`. Ouvrir la page pour vérifier qu'elle contient des maillots.
   → au passage, vérifier dans le journal quelles boutiques de `config.json` répondent bien
     (une boutique non-Shopify échoue proprement : la retirer ou la signaler).

2. **Bot Telegram** : m'aider à créer le bot via @BotFather, récupérer TOKEN + CHAT_ID.

3. **GitHub** : créer un repo (public), y pousser tous ces fichiers (garder `.github/` et `docs/`).

4. **Secrets** : ajouter `TG_TOKEN` et `TG_CHAT_ID` dans Settings → Secrets and variables → Actions.

5. **GitHub Pages** : Settings → Pages → branche `main`, dossier `/docs`.
   → récupérer l'URL et la mettre dans `config.json` → champ `page_url`.

6. **Lancer** : onglet Actions → Run workflow. Le 1er run indexe sans spammer et envoie
   un message "agent armé" sur Telegram. Ensuite : toutes les 20 min, automatiquement.

## Ce que fait l'agent
- Scanne 8 boutiques Shopify, détecte les maillots de **Cristiano Ronaldo** (tous numéros : 28, 17, 9, 7)
  et **exclut le Ronaldo brésilien** (R9).
- Notifie sur Telegram : lien direct + description + rareté + lien vers la page.
- Alimente `docs/index.html` : catalogue trié par **rareté (S/A/B/C)** ou **année**, filtres club /
  domicile-extérieur / **version joueur vs supporter**, comparaison de prix par saison.
- Les maillots plus dispo basculent dans l'onglet **Historique** avec leur historique de prix.
- `data.json` = mémoire persistante (jamais écrasée, elle s'enrichit).
