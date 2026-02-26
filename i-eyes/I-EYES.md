# I-Eyes 💀 — AI Code Review pour GitLab

> Revue de code automatique par IA, déclenchée sur chaque Merge Request.

---

## 🎯 Fonctionnement

```
GitLab MR → Webhook → I-Eyes → AI Review → Commentaires sur la MR
```

1. Un développeur ouvre/met à jour une **Merge Request** sur GitLab.
2. GitLab envoie un **webhook** à I-Eyes.
3. I-Eyes récupère les **diffs** de la MR via l'API GitLab.
4. Les changements sont envoyés à un **modèle IA** (OpenAI, Anthropic, ou tout API compatible).
5. L'IA analyse le code et retourne des remarques structurées.
6. I-Eyes **poste les commentaires** directement sur la MR :
   - Un **résumé global** en commentaire général.
   - Des **remarques inline** sur les lignes concernées.
   - Un **label** de sévérité (`i-eyes:warning` / `i-eyes:critical`) si nécessaire.

---

## 📁 Structure du projet

```
i-eyes/
├── config.py              # Configuration (variables d'environnement)
├── gitlab_client.py       # Client API GitLab (diffs, commentaires, labels)
├── reviewer.py            # Moteur de revue IA (prompt + parsing)
├── webhook_server.py      # Serveur Flask (réception webhooks)
├── requirements.txt       # Dépendances Python
├── Dockerfile             # Image Docker
├── docker-compose.yml     # Déploiement Docker Compose
├── .env.example           # Template des variables d'environnement
└── I-EYES.md              # Cette documentation
```

---

## ⚡ Installation rapide

### Prérequis

- Python 3.11+ (ou Docker)
- Un **Personal Access Token** GitLab avec les scopes : `api`, `read_repository`
- Une **clé API** pour le modèle IA (OpenAI, Anthropic, etc.)

### 1. Cloner et configurer

```bash
git clone <repo_url>
cd i-eyes
cp .env.example .env
# Éditer .env avec vos valeurs
```

### 2. Lancer

**Avec Docker (recommandé) :**

```bash
docker compose up -d
```

**Sans Docker :**

```bash
pip install -r requirements.txt
python webhook_server.py
```

Le serveur écoute sur `http://0.0.0.0:8000`.

### 3. Configurer le webhook GitLab

1. Dans votre projet GitLab : **Settings → Webhooks**
2. URL : `http://<votre-serveur>:8000/webhook`
3. Secret Token : la valeur de `GITLAB_WEBHOOK_SECRET` dans votre `.env`
4. Trigger : cocher **Merge request events**
5. Enregistrer

---

## ⚙️ Configuration

| Variable | Description | Défaut |
|---|---|---|
| `GITLAB_URL` | URL de votre instance GitLab | `https://gitlab.com` |
| `GITLAB_TOKEN` | Personal Access Token GitLab | *requis* |
| `GITLAB_WEBHOOK_SECRET` | Secret du webhook (optionnel mais recommandé) | `` |
| `AI_API_URL` | URL de l'API IA (compatible OpenAI) | `https://api.openai.com/v1` |
| `AI_API_KEY` | Clé API du fournisseur IA | *requis* |
| `AI_MODEL` | Modèle à utiliser | `gpt-4o` |
| `IEYES_HOST` | Adresse d'écoute | `0.0.0.0` |
| `IEYES_PORT` | Port d'écoute | `8000` |
| `MAX_DIFF_SIZE` | Taille max du diff envoyé à l'IA (caractères) | `50000` |
| `REVIEW_LANGUAGE` | Langue des commentaires (`fr` / `en`) | `fr` |

### Fournisseurs IA compatibles

Tout fournisseur exposant une API compatible OpenAI `/v1/chat/completions` :

| Fournisseur | `AI_API_URL` | `AI_MODEL` |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Anthropic (via proxy) | `https://api.anthropic.com/v1` | `claude-sonnet-4-20250514` |
| Azure OpenAI | `https://<endpoint>.openai.azure.com` | `gpt-4o` |
| Ollama (local) | `http://localhost:11434/v1` | `llama3` |
| LM Studio (local) | `http://localhost:1234/v1` | `local-model` |

---

## 🔍 Ce que I-Eyes analyse

### Général
- Bugs logiques, erreurs de syntaxe
- Code mort, duplication
- Complexité excessive
- Violations de conventions de nommage

### Spécifique embarqué (C/C++/Rust)
- 🧠 **Mémoire** : malloc/free, buffer overflow, stack usage, fuites
- ⚡ **Concurrence** : race conditions, mutex manquants, ISR safety
- 🔢 **Types** : overflow int8/uint16, signedness, casts implicites
- 📡 **Hardware** : volatile manquant, accès registres, DMA
- 🔋 **Énergie** : boucles actives, sleep modes, peripherals non désactivés

---

## 📝 Exemple de sortie

### Commentaire résumé sur la MR :

> ## ⚠️ I-Eyes Code Review
>
> **Verdict global : WARNING**
>
> Cette MR ajoute un handler d'interruption pour le capteur de température.
> Le code fonctionne mais présente un risque de race condition sur la variable
> partagée `temp_buffer` et un buffer overflow potentiel dans `parse_sensor_data()`.
>
> **3 remarque(s) détaillée(s) ci-dessous.**

### Commentaire inline sur une ligne :

> ⚠️ **I-Eyes** [WARNING]
>
> `temp_buffer` est accédé depuis l'ISR et le thread principal sans protection.
> Utilisez `volatile` et un mutex, ou un buffer atomique lock-free.

---

## 🏥 Endpoints

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/health` | Healthcheck (retourne `{"status": "ok"}`) |
| `POST` | `/webhook` | Réception des webhooks GitLab |

---

## 🚀 Production

### Derrière un reverse proxy (Nginx)

```nginx
server {
    listen 443 ssl;
    server_name i-eyes.votre-domaine.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### Sécurité

- **Toujours** configurer `GITLAB_WEBHOOK_SECRET` en production.
- Utiliser HTTPS (via reverse proxy).
- Limiter l'accès réseau au serveur I-Eyes (firewall).
- Stocker les secrets dans un vault ou des variables CI/CD, pas en clair.

---

## 🛠️ Développement

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer en mode dev
python webhook_server.py

# Tester le healthcheck
curl http://localhost:8000/health
```

### Tester manuellement avec un payload webhook

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Gitlab-Event: Merge Request Hook" \
  -H "X-Gitlab-Token: your-secret" \
  -d @test_payload.json
```

---

*Développé par Vendredi 💀 pour votre client.*
