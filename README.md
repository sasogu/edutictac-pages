# EduTicTac Pages

Allotjament de llocs estàtics a partir de repositoris públics de Forgejo
(`git.edutictac.es`), equivalent funcional a GitHub Pages però adreçat per
**ruta** en compte de per subdomini wildcard:

```
https://pages.edutictac.es/<owner>/<repo>/<ruta>
```

## Com publicar un lloc

1. Crea (o reutilitza) un repositori **públic** a `git.edutictac.es`.
2. Puja un `index.html` a l'arrel d'una branca `pages`, `main` o `master`
   (en aquest ordre de prioritat).
3. Visita `https://pages.edutictac.es/<owner>/<repo>/`.

Qualsevol fitxer estàtic (CSS, JS, imatges...) es serveix igual, mantenint
la mateixa ruta que té al repositori.

## Principis

- **Sense credencials de Forgejo**: el servei només reenvia el que Forgejo
  ja exposa anònimament (`raw/branch/...`). Per disseny, mai pot servir
  contingut d'un repositori privat.
- **Sense estat propi**: no hi ha base de dades. El contingut sempre viu al
  repositori Forgejo; ací només es fa de memòria cau de lectura.
- **404 net** si cap de les branques candidates té el fitxer demanat.
- Protecció davant de *path traversal* i límit de mida de fitxer servit.

## Execució local

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8006
```

Tests:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Configuració

Totes les opcions es passen per variable d'entorn; no calen fitxers `.env`
al repositori.

| Variable | Per defecte | Descripció |
| --- | --- | --- |
| `PAGES_GITEA_ROOT` | `https://git.edutictac.es` | Arrel de la instància Forgejo |
| `PAGES_BRANCH_CANDIDATES` | `pages,main,master` | Ordre de branques a provar |
| `PAGES_CACHE_TTL_SECONDS` | `60` | TTL de la memòria cau de contingut |
| `PAGES_BRANCH_CACHE_TTL_SECONDS` | `300` | TTL de la memòria cau de resolució de branca |
| `PAGES_CACHE_MAX_ENTRIES` | `500` | Nombre màxim d'entrades en cau |
| `PAGES_MAX_FILE_BYTES` | `20971520` (20 MB) | Mida màxima de fitxer servit |
| `PAGES_REQUEST_TIMEOUT_SECONDS` | `5` | Timeout de les peticions a Forgejo |

## Desplegament

Servei FastAPI sense estat, pensat per executar-se darrere d'un proxy
invers (nginx) amb TLS i `limit_req` per limitar la freqüència de
peticions. No requereix cap base de dades ni volum persistent.

## Llicència

MIT.
