# Infomaniak DDNS – Custom Integration pour Home Assistant

Cette intégration permet de mettre à jour automatiquement votre enregistrement DNS dynamique (DDNS) chez Infomaniak directement depuis Home Assistant.

---

## Installation

### Via HACS (recommandé)
1. Dans HACS, allez dans **Intégrations** → bouton **⋮** → **Dépôts personnalisés**
2. Ajoutez l'URL du dépôt, catégorie **Intégration**
3. Installez **Infomaniak DDNS**
4. Redémarrez Home Assistant

### Manuelle
1. Copiez le dossier `custom_components/infomaniak_ddns/` dans votre dossier `<config>/custom_components/`
2. Redémarrez Home Assistant

---

## Configuration

1. Allez dans **Paramètres** → **Appareils et services** → **Ajouter une intégration**
2. Recherchez **Infomaniak DDNS**
3. Remplissez les champs :

| Champ | Description | Défaut |
|---|---|---|
| **URL de mise à jour** | URL de l'API DDNS Infomaniak | `https://infomaniak.com/nic/update` |
| **Nom d'hôte DDNS** | Votre FQDN DDNS (ex: `home.mondomaine.com`) | — |
| **Nom d'utilisateur** | Login DDNS Infomaniak (**pas** votre login admin) | — |
| **Mot de passe** | Mot de passe DDNS (**pas** votre mot de passe admin) | — |
| **Intervalle (min)** | Fréquence de mise à jour en minutes | `5` |

> ⚠️ Utilisez le **login/mot de passe DDNS spécifique** créé dans le gestionnaire Infomaniak, et non vos identifiants de compte principal.

---

## Entités créées

| Entité | Description |
|---|---|
| `sensor.ddns_<hostname>_status` | Statut de la dernière mise à jour (`updated`, `unchanged`, `error`) |
| `sensor.ddns_<hostname>_ip` | Dernière adresse IP enregistrée |

### Attributs du capteur de statut

- `hostname` : Le nom d'hôte configuré
- `last_response` : Réponse brute de l'API (`good 1.2.3.4`, `nochg 1.2.3.4`, etc.)
- `last_error` : Message d'erreur si applicable
- `update_count` : Nombre de mises à jour réussies depuis le démarrage
- `update_url` : URL de l'API utilisée
- `update_interval_minutes` : Intervalle configuré

---

## Réponses API Infomaniak

| Réponse | Signification |
|---|---|
| `good <ip>` | IP mise à jour avec succès |
| `nochg <ip>` | IP inchangée, pas de mise à jour nécessaire |
| `badauth` | Identifiants incorrects |
| `nohost` | Nom d'hôte inconnu |
| `notfqdn` | Nom d'hôte invalide |
| `abuse` | Trop de requêtes |
| `911` | Problème côté serveur Infomaniak |

---

## Automation exemple : forcer une mise à jour

```yaml
automation:
  - alias: "Force DDNS update on IP change"
    trigger:
      - platform: state
        entity_id: sensor.external_ip  # votre capteur IP externe
    action:
      - service: homeassistant.reload_config_entry
        target:
          entity_id: sensor.ddns_home_mondomaine_com_status
```

---

## Prérequis Infomaniak

1. Avoir un domaine géré chez Infomaniak
2. Dans le **Manager Infomaniak** → votre domaine → **DNS** → **DNS Dynamique**
3. Créer un enregistrement DDNS avec un login/mot de passe dédié
4. Utiliser ces identifiants dans l'intégration (pas vos identifiants admin)

Documentation officielle : https://www.infomaniak.com/en/support/faq/2357

