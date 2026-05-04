# Guide : soumettre une PR sur hacs/default

Ce fichier décrit les étapes pour inclure l'intégration dans le store HACS officiel.

## Prérequis (à vérifier avant la PR)

- [x] L'action **HACS Action** passe sans erreur (onglet Actions du repo GitHub)
- [x] L'action **Hassfest** passe sans erreur
- [x] Une **release GitHub** existe (ex: v1.1.0)
- [x] Le repo a une **description** et des **topics** GitHub :
      `home-assistant`, `hacs`, `ddns`, `infomaniak`, `homeassistant`

## Étapes

1. **Forker** https://github.com/hacs/default
2. Dans ton fork, créer une branche : `add-infomaniak-ddns`
3. Éditer le fichier `integration` (liste alphabétique) et ajouter :
   ```
   cy-bertrand/Infomaniak-dyndns-ha
   ```
   (à insérer en respectant l'ordre alphabétique, à la lettre **I**)
4. Ouvrir une Pull Request vers `hacs/default:master`
5. Remplir le template PR fourni par HACS :
   - Confirmer que tu es bien le propriétaire du repo
   - Confirmer que les actions passent
   - Confirmer qu'une release existe

## Notes importantes

- Le processus de review peut prendre plusieurs semaines
