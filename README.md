# echo-worker

Worker assíncrono do Echo. Consome as filas BullMQ produzidas pela `echo-api`,
transcreve áudios/vídeos e gera resumos usando LLM.

- **Transcrição**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) local ou API OpenAI.
- **Resumo**: API OpenAI (ou stub determinístico em desenvolvimento).
- **Persistência**: PostgreSQL (schema e migrations pertencem à `echo-api`).
- **Armazenamento**: MinIO/S3.
- **Filas**: pacote oficial [bullmq](https://pypi.org/project/bullmq/) para Python, interoperável com o BullMQ do Node.

## Filas

| Fila | Payload | Resultado |
| --- | --- | --- |
| `media_transcription_queue` | `{ mediaId, url, storageKey }` | transcreve, salva segmentos e debita minutos |
| `media_summary_queue` | `{ mediaId, prompt }` | gera resumo com o prompt final já composto pela API |

O worker nunca roda migrations nem cria mídias: ele apenas lê e atualiza linhas
criadas pela `echo-api`.

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL, Redis e MinIO acessíveis

## Configuração

```bash
cp .env.example .env
```

Variáveis principais:

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `DATABASE_URL` | — | connection string do PostgreSQL |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | `localhost` / `6379` / `0` | conexão Redis |
| `REDIS_PASSWORD` | — | senha do Redis (opcional) |
| `WORKER_CONCURRENCY` | `2` | jobs simultâneos por fila |
| `WHISPER_MODE` | `local` | `local`, `openai` ou `fake` |
| `SUMMARY_MODE` | `openai` | `openai` ou `fake` |
| `OPENAI_API_KEY` | — | obrigatória quando o modo é `openai` |
| `STORAGE_*` | MinIO local | endpoint, credenciais e bucket |
| `TEMP_DIR` | `/tmp/echo-worker` | diretório de download temporário |

`fake` é rejeitado quando `WORKER_ENV=production`.

## Uso

```bash
uv sync
uv run echo-worker
# ou
uv run python -m echo_worker.main
```

### Desenvolvimento sem modelos

```bash
WHISPER_MODE=fake SUMMARY_MODE=fake uv run echo-worker
```

## Testes e lint

```bash
uv run ruff check .
uv run pytest
```

## Docker

```bash
docker build -t echo-worker .
docker run --env-file .env echo-worker
```

O primeiro uso de `WHISPER_MODE=local` baixa os pesos do modelo para o cache do
faster-whisper. Em produção, monte um volume de cache para evitar downloads
repetidos.

## Estrutura

```
src/echo_worker/
  config.py        # carregamento e validação do ambiente
  db.py            # acesso ao PostgreSQL e débito de minutos
  storage.py       # download de mídia (S3/MinIO/URL)
  models.py        # dataclasses de domínio
  worker.py        # runtime BullMQ (duas filas)
  main.py          # entrypoint e shutdown gracioso
  jobs/            # processors de transcrição e resumo
  providers/       # faster-whisper, OpenAI e stubs
```
