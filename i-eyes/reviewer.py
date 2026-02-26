"""
I-Eyes AI Code Reviewer
Analyses diffs and produces structured review comments.
"""

import json
import logging
from dataclasses import dataclass, field

import requests

from config import Config

logger = logging.getLogger("i-eyes.reviewer")

SYSTEM_PROMPT = """Tu es I-Eyes, un expert en revue de code embarqué (C, C++, Rust, Python, etc.).
Tu reçois le diff d'une Merge Request GitLab. Ta mission :

1. Analyser chaque fichier modifié.
2. Identifier : bugs, vulnérabilités, problèmes de performance, violations de style, 
   code mort, complexité excessive, problèmes spécifiques à l'embarqué (mémoire, concurrence, timing).
3. Produire des remarques constructives et précises.

Réponds UNIQUEMENT en JSON valide avec cette structure :
{
  "summary": "Résumé global de la MR en 2-3 phrases",
  "severity": "ok | info | warning | critical",
  "comments": [
    {
      "file": "chemin/du/fichier.c",
      "line": 42,
      "severity": "info | warning | critical",
      "message": "Description du problème et suggestion de correction"
    }
  ]
}

Règles :
- Si le code est bon, "comments" peut être vide et severity = "ok".
- "line" fait référence au numéro de ligne DANS LE NOUVEAU FICHIER (new_line du diff).
- Sois précis, concis et constructif. Pas de flatteries inutiles.
- Pour du code embarqué, porte une attention particulière à :
  * Gestion mémoire (malloc/free, buffer overflow, stack usage)
  * Concurrence (race conditions, mutexes, ISR safety)
  * Types et overflow (int8/uint16, signedness)
  * Volatile / registres hardware
  * Consommation énergétique
"""


@dataclass
class ReviewComment:
    file: str
    line: int
    severity: str
    message: str


@dataclass
class ReviewResult:
    summary: str
    severity: str
    comments: list[ReviewComment] = field(default_factory=list)
    raw_response: str = ""


class AIReviewer:
    def __init__(self):
        self.api_url = Config.AI_API_URL.rstrip("/")
        self.api_key = Config.AI_API_KEY
        self.model = Config.AI_MODEL

    def _build_diff_prompt(self, diffs: list[dict], mr_title: str, mr_description: str) -> str:
        parts = [f"# MR: {mr_title}\n"]
        if mr_description:
            parts.append(f"## Description\n{mr_description}\n")
        parts.append("## Changements\n")

        total_chars = 0
        for d in diffs:
            diff_text = d.get("diff", "")
            if total_chars + len(diff_text) > Config.MAX_DIFF_SIZE:
                parts.append(f"\n### {d.get('new_path', '?')} (tronqué — diff trop volumineux)\n")
                break
            parts.append(f"\n### {d.get('new_path', '?')}\n```diff\n{diff_text}\n```\n")
            total_chars += len(diff_text)

        return "\n".join(parts)

    def review(self, diffs: list[dict], mr_title: str, mr_description: str = "") -> ReviewResult:
        prompt = self._build_diff_prompt(diffs, mr_title, mr_description)
        logger.info("Sending review request to AI (%d chars of diff)", len(prompt))

        try:
            resp = requests.post(
                f"{self.api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 4096,
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # Parse JSON from response (handle markdown code blocks)
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]
                clean = clean.rsplit("```", 1)[0]

            result = json.loads(clean)
            comments = [
                ReviewComment(
                    file=c["file"],
                    line=c["line"],
                    severity=c.get("severity", "info"),
                    message=c["message"],
                )
                for c in result.get("comments", [])
            ]
            return ReviewResult(
                summary=result.get("summary", ""),
                severity=result.get("severity", "info"),
                comments=comments,
                raw_response=content,
            )

        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            logger.error("AI review failed: %s", e)
            return ReviewResult(
                summary=f"⚠️ I-Eyes n'a pas pu analyser cette MR : {e}",
                severity="warning",
                comments=[],
                raw_response=str(e),
            )
