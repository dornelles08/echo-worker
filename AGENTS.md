# echo-worker — Guia para agentes

Worker assíncrono do Echo: consome filas BullMQ da `echo-api`, transcreve áudios/vídeos e
gera resumos com LLM. Python 3.13+, uv, ruff, pytest.

- Transcrição: faster-whisper local, OpenAI Whisper ou stub fake.
- Resumo: OpenAI chat completions ou stub fake.
- Persistência: PostgreSQL (schema/migrations pertencem à API).
- Storage: MinIO/S3.
- Filas: pacote `bullmq` para Python, interoperável com BullMQ do Node.

## Arquitetura

```
src/echo_worker/
  config.py        # carregamento/validação do ambiente (Settings dataclass)
  db.py            # acesso Postgres (psycopg pool) + débito de minutos
  storage.py       # download de mídia (S3/MinIO/URL/local)
  models.py        # dataclasses de domínio (MediaRecord, Segment, ...)
  worker.py        # runtime BullMQ (duas filas, WorkerRuntime)
  main.py          # entrypoint + shutdown gracioso (sinais)
  logging.py       # setup de logging
  jobs/            # processors de transcrição e resumo
  providers/       # faster-whisper, OpenAI, stubs + factory
```

Fluxo de boot: `main.main()` → `load_settings()` → `WorkerRuntime` → `build_workers()` →
`run()` (asyncio.gather dos dois workers).

### Padrões obrigatórios

- **Nunca roda migrations nem cria mídias/usuários**: apenas lê/atualiza linhas criadas pela API.
- **Providers via Protocol** (`providers/base.py`): `Transcriber` e `Summarizer`. Seleção em
  `providers/factory.py` a partir de `Settings` (`whisper_mode`, `summary_mode`).
- **Jobs são callables** aceitando `(job, token)` e delegando para `process(data)` síncrono via
  `asyncio.to_thread`. Retornam dict com status.
- **Idempotência**: transcrição verifica `TRANSCRIBED_STATUSES` e pula (mas ainda tenta debitar);
  débito verifica `usage_debited_at` (FOR UPDATE) e não debita duas vezes.
- **Status transitions** via `Database.mark_*`.
- **Erros de job** são logados e status marcado como failed; exceção re-raised para BullMQ
  (retry/backoff do BullMQ).

### Filas e payloads

| Fila (default) | Job | Payload | Resultado |
| --- | --- | --- | --- |
| `media_transcription_queue` | `TranscriptionJob` | `{ mediaId, url, storageKey }` | transcreve, salva segmentos, debita minutos |
| `media_summary_queue` | `SummaryJob` | `{ mediaId, prompt }` | gera resumo com prompt final já composto pela API |

Nomes configuráveis via `TRANSCRIPTION_QUEUE`/`SUMMARY_QUEUE`.

### Status de mídia

Mesmos status do API. Worker transita:
- transcrição: `mark_processing_transcription` → `mark_transcribed` (ou `mark_failed_transcription`);
  se já transcrito, pula processamento mas tenta debitar.
- resumo: `mark_processing_summary` → `append_summary`/summarized (ou `mark_failed_summary`);
  se sem transcrição, `reset_to_pending_transcription`.

### Débito de minutos (idempotente)

`Database.debit_usage(media_id)`:
- `SELECT ... FOR UPDATE` na mídia; se `usage_debited_at` não nulo, retorna None.
- `minutes = ceil(duration/60)`; `UPDATE usage_counters SET minutes_used += minutes`.
- Se `rowcount == 0` (sem contador), levanta `UsageCounterMissingError`.
- Marca `usage_debited_at = now()`.

A API marca `usageDebitedAt` no create-media (upload já debitou), evitando dupla contagem.

### Storage

- `Storage.download(media, destination)` prefere `storage_key` (bucket) → URL http(s) → path local.
- `_download_from_bucket` valida tamanho > 0.
- `build_destination(directory, media)` monta nome `media-{id}{suffix}`.

### Providers

- `faster_whisper`: modelo carregado lazily (evita download no boot/testes); device/compute_type
  detectados automaticamente (CUDA→float16, senão CPU→int8).
- `openai`: httpx com timeouts (transcrição 600s, resumo 300s); `response_format=verbose_json`.
- `fake`: determinístico para dev/testes; rejeitado em produção.
- `normalize_language`: BCP-47 → código primário (pt-BR → pt).

### Configuração

- `Settings` dataclass frozen; `load_settings()` valida env e modos.
- `WORKER_ENV=production` rejeita `fake`.
- OpenAI key obrigatória quando modo openai.
- CUDA detectado via torch ou nvidia-smi.

### Banco (psycopg)

- Pool `ConnectionPool` (min 1, max configurável, default 5).
- `row_factory=dict_row`; queries parametrizadas.
- JSONB para segments via `psycopg.types.json.Jsonb`.
- Sem ORM: SQL cru. Ao mudar schema na API, atualizar `db.py` manualmente.

### Testes

- pytest + pytest-asyncio (`asyncio_mode=auto`).
- Testes em `tests/`: `test_config`, `test_language`, `test_storage`, `test_transcription_job`,
  `test_summary_job`.
- Helpers em `tests/helpers.py`: fakes de DB, storage, transcriber, summarizer, job.
- Padrão: injetar fakes no job e chamar `process(data)` (síncrono) ou `__call__` (async).
- `pythonpath = ["src", "tests"]`.

Comandos:
```bash
uv sync
uv run echo-worker
WHISPER_MODE=fake SUMMARY_MODE=fake uv run echo-worker
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

### Lint/format

- ruff: line-length 100, target py313, regras E/F/W/I/B/UP, isort known-first-party `echo_worker`.
- pre-commit: ruff-check --fix, ruff-format, pytest.

### Onde procurar

| Tarefa | Arquivo(s) |
| --- | --- |
| Novo job | `jobs/<nome>.py` + registro em `worker.py` + fila/env |
| Novo provider/transcriber | `providers/<nome>.py` + factory.py |
| Mudança de acesso a DB | `db.py` (SQL cru) |
| Mudança de storage/download | `storage.py` |
| Novo campo de domínio | `models.py` + `db.py` (to_media/select) |
| Config/env | `config.py` + `.env.example` |
| Entry/boot | `main.py`, `worker.py` |

### Não fazer

- Não rodar migrations ou criar tabelas.
- Não criar mídias/usuários.
- Não parsear templates de prompt (API compõe o prompt final).
- Não usar `fake` em produção.
- Não assumir que presigned URL ainda é válida (usar storage_key).

### Particularidades

- Python 3.13+ (`.python-version` 3.13; README menciona 3.14+).
- Build system hatchling; pacote `src/echo_worker`.
- Concurrency por fila (`WORKER_CONCURRENCY`, default 2).
- Shutdown gracioso via SIGINT/SIGTERM com timeout 30s.
- Modelos faster-whisper baixados no primeiro uso; monte volume de cache em prod.
- Testes de job usam fakes, não tocam em Postgres/Redis/S3.
