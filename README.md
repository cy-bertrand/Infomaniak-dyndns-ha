# Infomaniak DDNS – Custom Integration pour Home Assistant

Mise à jour automatique de votre enregistrement DNS dynamique (DDNS) Infomaniak depuis Home Assistant.

---

## Installation

### Manuelle
1. Copiez le dossier `custom_components/infomaniak_ddns/` dans `<config>/custom_components/`
2. Redémarrez Home Assistant

### Via HACS (recommandé)
1. Dans HACS, allez dans **Intégrations** → bouton **⋮** → **Dépôts personnalisés**
2. Ajoutez l'URL du dépôt, catégorie **Intégration**
3. Installez **Infomaniak DDNS**
4. Redémarrez Home Assistant

---

## Configuration

**Paramètres → Appareils et services → Ajouter une intégration → Infomaniak DDNS**

### Étape 1 — Connexion et mode IP

| Champ | Description | Défaut |
|---|---|---|
| **URL de mise à jour** | URL API DDNS Infomaniak | `https://infomaniak.com/nic/update` |
| **Nom d'hôte** | FQDN de votre DDNS (ex: `home.mondomaine.com`) | — |
| **Nom d'utilisateur** | Login DDNS (pas le login admin Infomaniak) | — |
| **Mot de passe** | Mot de passe DDNS (pas le mot de passe admin) | — |
| **Intervalle** | Fréquence de mise à jour en minutes | `5` |
| **Source IP** | Voir tableau ci-dessous | `Auto` |

### Modes de source IP

| Mode | Comportement | Quand l'utiliser |
|---|---|---|
| **Auto — IP WAN détectée par Infomaniak** | Pas de paramètre `myip` dans la requête. Infomaniak enregistre l'IP source de la requête HTTP, c'est-à-dire l'IP WAN de votre box/routeur derrière laquelle tourne HA. | **Cas standard** — HA est derrière votre box internet |
| **IP fixe — saisie manuelle** | Envoie `&myip=x.x.x.x` dans la requête. | Serveur avec IP fixe, VPN, ou IP de failover |
| **Entité HA — lire depuis un capteur** | Lit l'état d'un `entity_id` HA à chaque mise à jour et envoie cette valeur comme `myip`. Si l'entité est indisponible, repasse en auto. | Capteur IP externe (ex: `sensor.ip_wan` via l'intégration *whatismyip* ou similaire) |

### Étape 2 (si mode IP fixe)
Saisie de l'adresse IPv4 (validée au format `x.x.x.x`).

### Étape 2 (si mode entité)
Saisie de l'`entity_id` du capteur (ex: `sensor.ip_wan`). La connexion est testée en mode auto car l'entité peut ne pas encore être disponible.

---

## Entités créées

| Entité | États possibles | Description |
|---|---|---|
| `sensor.ddns_<hostname>_status` | `updated` / `unchanged` / `error` / `unknown` | Résultat de la dernière mise à jour |
| `sensor.ddns_<hostname>_ip` | Adresse IPv4 | Dernière IP enregistrée (retournée par l'API) |

### Attributs de `_status`

- `hostname` — nom d'hôte configuré
- `last_response` — réponse brute de l'API (`good 1.2.3.4`, `nochg 1.2.3.4`, etc.)
- `last_error` — message d'erreur si applicable
- `ip_source` — source IP utilisée (ex: `auto (IP WAN détectée par Infomaniak)`, `static (1.2.3.4)`, `entity sensor.ip_wan (1.2.3.4)`)
- `ip_mode` — mode configuré (`auto`, `static`, `entity`)
- `update_count` — nombre de mises à jour réussies depuis le démarrage
- `update_interval_minutes` — intervalle configuré

### Attributs de `_ip`

- `ip_source` — source de l'IP utilisée
- `ip_mode` — mode configuré

---

## Réponses API Infomaniak

| Réponse | Signification | État capteur |
|---|---|---|
| `good <ip>` | IP mise à jour avec succès | `updated` |
| `nochg <ip>` | IP inchangée, pas de mise à jour nécessaire | `unchanged` |
| `badauth` | Identifiants incorrects | `error` |
| `nohost` | Nom d'hôte inconnu | `error` |
| `notfqdn` | Nom d'hôte invalide | `error` |
| `abuse` | Trop de requêtes | `error` |
| `911` | Problème serveur Infomaniak | `error` |

---

## Exemple d'automation : alerte en cas d'erreur

```yaml
automation:
  - alias: "Alerte DDNS Infomaniak en erreur"
    trigger:
      - platform: state
        entity_id: sensor.ddns_home_mondomaine_com_status
        to: "error"
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ DDNS Infomaniak"
          message: >
            Erreur DDNS : {{ state_attr('sensor.ddns_home_mondomaine_com_status', 'last_error') }}
```

---

## Prérequis Infomaniak

1. Domaine géré chez Infomaniak
2. Manager Infomaniak → votre domaine → **DNS** → **DNS Dynamique**
3. Créer un enregistrement DDNS avec un **login/mot de passe dédié** (≠ identifiants admin)
4. Utiliser ces identifiants dans l'intégration

Documentation Infomaniak : https://www.infomaniak.com/en/support/faq/2357

