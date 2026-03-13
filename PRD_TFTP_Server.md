# PRD — TFTP Server Pro

**Версия документа:** 2.0  
**Дата:** 2026-03-12  
**Автор:** Slava / 2F-IT GmbH  
**Статус:** Review → Approved  
**Changelog v2.0:** Исправлены 14 критичных и 12 значимых пробелов по результатам gap analysis.

---

## 1. Обзор продукта

### 1.1 Назначение

TFTP Server Pro — кросс-платформенный высокопроизводительный TFTP-сервер с графическим (GUI) и консольным (TUI) интерфейсом, реализованный на Rust. Продукт ориентирован на сетевых инженеров, системных администраторов и DevOps-команды, которым необходим надёжный инструмент для PXE-загрузки, обновления прошивок сетевого оборудования (Fortinet, Palo Alto, Cisco и др.), массового деплоя образов и автоматизации сетевой инфраструктуры.

### 1.2 Проблема

Существующие TFTP-серверы (tftpd-hpa, SolarWinds TFTP, Serva) страдают от одной или нескольких проблем:

- Отсутствие GUI или убогий интерфейс без мониторинга в реальном времени
- Ограниченная производительность (stop-and-wait без sliding window)
- Отсутствие нативной кросс-платформенности (Windows-only или Linux-only)
- Нет поддержки современных RFC (2347/2348/2349/7440)
- Нет ACL / контроля доступа
- Устаревший код на C/C++ с потенциальными memory safety уязвимостями
- Нет headless-режима для серверных развёртываний

### 1.3 Решение

Единый бинарник на Rust с conditional compilation через Cargo feature flags:

- **GUI-режим** (`--gui`, default при feature `gui`) — для работы на рабочей станции инженера
- **TUI-режим** (`--tui`, требует feature `tui`) — для серверов с SSH-доступом
- **Headless-режим** (`--headless`, всегда доступен) — для демонов/сервисов (systemd, Windows Service, launchd)

**Build варианты (feature flags):**

```toml
[features]
default = ["gui", "tui"]
gui = ["dep:eframe", "dep:egui", "dep:egui_plot", "dep:rfd", "dep:tray-icon"]
tui = ["dep:ratatui", "dep:crossterm"]
```

| Команда сборки | Что включено | Для кого |
|---|---|---|
| `cargo build --release` | GUI + TUI + Headless | Рабочая станция инженера |
| `cargo build --release --no-default-features --features tui` | TUI + Headless | Сервер с SSH |
| `cargo build --release --no-default-features` | Только Headless | Docker, CI/CD, systemd |

Полная поддержка RFC 1350 + расширений (2347, 2348, 2349, 7440), IPv4/IPv6 dual-stack, sliding window для гигабитных скоростей, ACL, per-IP rate limiting, горячая перезагрузка конфига, детальный мониторинг и логирование.

### 1.4 Целевая аудитория

| Сегмент | Сценарий использования |
|---|---|
| Сетевые инженеры | Обновление firmware сетевого оборудования (FortiGate, PA, Cisco IOS) |
| Системные администраторы | PXE boot, развёртывание ОС через сеть |
| DevOps / SRE | Автоматизация провижининга в CI/CD пайплайнах (headless) |
| Embedded-разработчики | Загрузка прошивок на embedded-устройства |
| IT Security | Контролируемая среда передачи файлов с ACL и аудит-логами |

---

## 2. Цели и метрики успеха

### 2.1 Бизнес-цели

| # | Цель | Критерий выполнения |
|---|---|---|
| BG-1 | Замена проприетарных TFTP-серверов в рабочем окружении 2F-IT | Полный переход инженеров на TFTP Server Pro |
| BG-2 | Open-source продукт для community adoption | GitHub Stars > 500 за первый год |
| BG-3 | Потенциальный upsell-продукт для клиентов 2F-IT | Включение в стандартный toolkit для заказчиков |

### 2.2 Технические метрики

| Метрика | Target | Метод измерения |
|---|---|---|
| Пропускная способность (single session) | ≥ 800 Mbit/s при blksize=65464 + windowsize=64 | iperf-like benchmark на localhost |
| Пропускная способность (10 параллельных сессий) | ≥ 500 Mbit/s суммарно | Стресс-тест с 10 клиентами |
| Время отклика на RRQ | < 1 ms (cold start сессии) | Замер от получения пакета до первого DATA |
| Потребление памяти (idle) | < 20 MB (GUI), < 5 MB (headless) | RSS через `ps` / Task Manager |
| Потребление памяти (100 сессий) | < 100 MB | Стресс-тест |
| Startup time | < 500 ms до ready-to-serve | Замер от запуска до первого bound socket |
| Binary size | < 15 MB (GUI), < 5 MB (headless) | `ls -la` на stripped release build |

---

## 3. Функциональные требования

### 3.1 TFTP Protocol Engine

#### 3.1.1 Базовый протокол (RFC 1350)

**Описание:** Полная реализация TFTP v2 согласно RFC 1350 с учётом уточнений RFC 1123 §4.2.3.

**Типы пакетов:**

- **RRQ (opcode 1)** — Read Request. Клиент запрашивает файл на чтение. Сервер открывает сессию, начинает отправку DATA-пакетов. Формат: `| 01 | filename | 0 | mode | 0 |`
- **WRQ (opcode 2)** — Write Request. Клиент запрашивает запись файла на сервер. Если WRQ разрешён в конфиге, сервер отвечает ACK(0) и принимает DATA от клиента. Формат: `| 02 | filename | 0 | mode | 0 |`
- **DATA (opcode 3)** — Блок данных. Содержит 2-байтовый номер блока и payload (до blksize байт). Последний блок: payload < blksize — сигнал завершения. Формат: `| 03 | block# | data |`
- **ACK (opcode 4)** — Подтверждение приёма блока. Содержит номер подтверждённого блока. Формат: `| 04 | block# |`
- **ERROR (opcode 5)** — Сообщение об ошибке. Содержит код ошибки и текстовое описание. Формат: `| 05 | errcode | errmsg | 0 |`

**Коды ошибок:**

| Код | Значение | Когда отправляется |
|---|---|---|
| 0 | Not defined | Общая ошибка, не попадающая в другие категории |
| 1 | File not found | RRQ на несуществующий файл |
| 2 | Access violation | Файл вне root директории или ACL deny |
| 3 | Disk full | Нет места на диске при WRQ |
| 4 | Illegal TFTP operation | Неожиданный opcode в текущем состоянии сессии |
| 5 | Unknown transfer ID | Пакет от неизвестного TID (порт клиента) |
| 6 | File already exists | WRQ на существующий файл (если overwrite запрещён) |
| 7 | No such user | Не используется (зарезервировано) |
| 8 | Option rejected | OACK negotiation failure (RFC 2347) |

**Режимы передачи:**

- **octet** — бинарная передача без преобразований (основной режим для firmware/images)
- **netascii** — текстовая передача с конвертацией line endings: CR/LF ↔ native. При отправке: LF → CR+LF, bare CR → CR+NUL. При приёме: CR+LF → LF, CR+NUL → CR

**Filename Encoding:**

RFC 1350 предполагает ASCII, но современные клиенты могут слать UTF-8. Политика:

1. Принимаем UTF-8 filenames (валидируем через `std::str::from_utf8`)
2. Если не валидный UTF-8 → ERROR(0, "Invalid filename encoding")
3. Логируем оригинальные байты в hex для диагностики
4. На Windows: конвертируем `/` → `\` при resolve
5. Запрещённые символы в filename: null byte, `..`, `~`, любые control chars (0x00–0x1F)

**Логика Transfer ID (TID):**

1. Сервер слушает на well-known порту (default: 69)
2. При получении RRQ/WRQ сервер создаёт новый UDP socket на эфемерном порту — это TID сервера
3. Клиент получает ответ с нового порта, его source port — TID клиента
4. Дальнейшая сессия идёт между двумя TID (эфемерный:эфемерный)
5. Пакеты с неверным TID → ERROR(5) + игнорирование

**Block number rollover:**

Номер блока — u16 (0–65535). При файлах > 65535 * blksize байт номер блока переполняется. Реализация: после блока 65535 следующий блок имеет номер 0, счётчик rollover инкрементируется. Это прозрачно для протокола — оба конца используют u16 wrapping.

**Zero-byte файлы:** Файл 0 байт — один DATA-пакет с пустым payload: `| 03 | 0001 | (empty) |`. Session state machine ДОЛЖЕН корректно завершить сессию по получению ACK(1) на этот пакет.

**Sorcerer's Apprentice Syndrome (RFC 1123 §4.2.3.1):**

Классический баг TFTP: сеть дублирует ACK → сервер отправляет DATA дважды → каждый блок отправляется бесконтрольно. Митигация (обязательна):

```
При получении ACK(N):
  if N < current_block:
      → ИГНОРИРОВАТЬ (duplicate/late ACK)
      → НЕ отправлять DATA повторно
  if N == current_block:
      → Нормальная обработка, отправляем следующий блок
  if N > current_block:
      → Аномалия, логируем WARN, игнорируем

Ретрансмиссия DATA происходит ТОЛЬКО по timeout, НИКОГДА по дублированному ACK.
```

#### 3.1.2 Option Extension Framework (RFC 2347)

**Описание:** Механизм negotiation опций между клиентом и сервером.

**Формат опций в RRQ/WRQ:**

```
| opcode | filename | 0 | mode | 0 | opt1 | 0 | val1 | 0 | opt2 | 0 | val2 | 0 |
```

**Логика:**

1. Клиент добавляет опции в RRQ/WRQ после mode
2. Сервер парсит опции, для каждой решает: принять (возможно с другим значением) или отвергнуть
3. Сервер отправляет OACK (opcode 6) с принятыми опциями: `| 06 | opt1 | 0 | val1 | 0 | ... |`
4. Если клиент не поддерживает OACK — он игнорирует и работает по базовому RFC 1350
5. Если сервер отвергает все опции — он может ответить обычным DATA(1) / ACK(0) или ERROR(8)

**OACK Flow — различия для RRQ и WRQ (критично!):**

```
=== RRQ с опциями ===
Client → Server:  RRQ(filename, mode, options...)
Server → Client:  OACK(accepted_options...)
Client → Server:  ACK(0)                          ← подтверждение OACK
Server → Client:  DATA(1)                          ← начало передачи
Client → Server:  ACK(1)
...

=== RRQ без опций ===
Client → Server:  RRQ(filename, mode)
Server → Client:  DATA(1)                          ← сразу данные
Client → Server:  ACK(1)
...

=== WRQ с опциями ===
Client → Server:  WRQ(filename, mode, options...)
Server → Client:  OACK(accepted_options...)
Client → Server:  DATA(1)                          ← клиент начинает СРАЗУ после OACK (НЕ ACK(0)!)
Server → Client:  ACK(1)
...

=== WRQ без опций ===
Client → Server:  WRQ(filename, mode)
Server → Client:  ACK(0)                           ← готовность принимать
Client → Server:  DATA(1)
Server → Client:  ACK(1)
...
```

**Ключевое отличие:** При WRQ с опциями клиент отправляет DATA(1) сразу после OACK (не ACK(0)!). Сервер НЕ должен ждать ACK(0) — иначе deadlock.

**Поддерживаемые опции:**

| Опция | RFC | Тип | Диапазон | Default | Описание |
|---|---|---|---|---|---|
| blksize | 2348 | u16 | 8–65464 | 512 | Размер блока данных в байтах |
| timeout | 2349 | u8 | 1–255 | 3 (сек) | Таймаут ожидания ACK/DATA |
| tsize | 2349 | u64 | 0–2^64 | 0 | Размер файла (для прогресс-бара) |
| windowsize | 7440 | u16 | 1–65535 | 1 | Количество блоков в sliding window |

#### 3.1.3 Block Size (RFC 2348)

**Описание:** Позволяет увеличить размер блока данных с 512 до 65464 байт.

**Логика negotiation:**

1. Клиент предлагает blksize=X в RRQ/WRQ
2. Сервер проверяет: `max(8, min(X, server_max_blksize))` — если значение ≥ 8 и ≤ настройке сервера, принимает; иначе предлагает своё значение
3. MTU consideration: на Ethernet (1500 MTU) оптимальный blksize = 1468 (1500 - 20 IP - 8 UDP - 4 TFTP header). При jumbo frames (9000 MTU): blksize = 8948
4. Максимальное значение 65464 = 65535 - 20 (IP) - 8 (UDP) - 4 (TFTP) - 39 (IP options headroom)

**Конфигурация сервера:**

```toml
[protocol]
max_blksize = 65464    # максимально допустимый blksize
default_blksize = 512  # если клиент не запрашивает
```

#### 3.1.4 Timeout и Transfer Size (RFC 2349)

**timeout:**

1. Клиент предлагает timeout=X секунд
2. Сервер принимает если X в диапазоне [server_min_timeout, server_max_timeout]
3. Иначе сервер предлагает ближайшее допустимое значение
4. Таймаут применяется к ожиданию ACK (при отправке) и DATA (при приёме)

**tsize:**

- **При RRQ:** клиент отправляет tsize=0, сервер отвечает в OACK реальным размером файла. Клиент использует для прогресс-бара
- **При WRQ:** клиент отправляет tsize=N (размер файла, который будет загружен). Сервер проверяет N ≤ max_file_size и наличие свободного места, может отклонить

#### 3.1.5 Window Size (RFC 7440) — Sliding Window

**Описание:** Ключевая фича для высокой производительности. Вместо stop-and-wait (отправил блок → ждём ACK → отправляем следующий) сервер отправляет windowsize блоков подряд, затем ожидает ACK последнего.

**Логика отправки (RRQ, сервер отдаёт файл):**

```
Window = [base_block, base_block + windowsize - 1]
1. Отправить все блоки из текущего окна
2. Ожидать ACK:
   a. ACK(N) где N = base_block + windowsize - 1 → окно полностью подтверждено
      → сдвигаем base_block на N+1, отправляем следующее окно
   b. ACK(N) где base_block ≤ N < base_block + windowsize - 1 → частичное подтверждение
      → сдвигаем base_block на N+1, отправляем оставшиеся + новые блоки до заполнения окна
   c. ACK(N) где N < base_block → дубликат, ИГНОРИРОВАТЬ (Sorcerer's Apprentice protection)
   d. Timeout → ретрансмиссия всего текущего окна от base_block
3. Последний блок (payload < blksize) → финализация после получения финального ACK
```

**Логика приёма (WRQ, сервер принимает файл):**

```
Window = [expected_block, expected_block + windowsize - 1]
1. Принимаем блоки, записываем в буфер
2. Если получены все блоки окна → ACK(last_block), сдвигаем окно
3. Если timeout без получения всех блоков → ACK(last_received_contiguous)
   → клиент ретранслирует с last_received_contiguous + 1
4. Out-of-order блоки: буферизуем, но ACK только contiguous sequence
```

**Вычисление пропускной способности:**

```
throughput = (windowsize * blksize * 8) / RTT
Пример: windowsize=64, blksize=1468, RTT=1ms
  → 64 * 1468 * 8 / 0.001 = 751 Mbit/s
Пример: windowsize=64, blksize=65464, RTT=1ms (localhost/LAN)
  → 64 * 65464 * 8 / 0.001 ≈ 33.5 Gbit/s (ограничено NIC/bus)
```

**Конфигурация:**

```toml
[protocol]
max_windowsize = 64     # максимально допустимый windowsize
default_windowsize = 1  # если клиент не запрашивает (= stop-and-wait)
```

### 3.2 Session Manager

#### 3.2.1 Жизненный цикл сессии

```
                RRQ/WRQ received
                       │
                       ▼
              ┌────────────────┐
              │   ACL Check    │──deny──→ ERROR(2) + drop
              └───────┬────────┘
                      │ allow
                      ▼
              ┌────────────────┐
              │  Rate Limit    │──exceeded──→ DROP (silent) + log WARN
              │  (per-IP)      │
              └───────┬────────┘
                      │ ok
                      ▼
              ┌────────────────┐
              │ Session Limit  │──full──→ ERROR(0, "server busy") + drop
              │ (global+perIP) │
              └───────┬────────┘
                      │ ok
                      ▼
              ┌────────────────┐
              │ Option Negot.  │──fail──→ ERROR(8) + drop
              │ (if OACK)     │
              └───────┬────────┘
                      │ ok
                      ▼
              ┌────────────────┐
              │ File Resolve   │──not found──→ ERROR(1) + drop
              │ (path check)  │──violation──→ ERROR(2) + drop
              └───────┬────────┘
                      │ ok
                      ▼
              ┌────────────────┐
              │ Spawn Tokio    │
              │ Task + New     │
              │ UDP Socket     │
              └───────┬────────┘
                      │
                      ▼
              ┌────────────────┐
              │  TRANSFERRING  │←──timeout──→ retransmit (до max_retries)
              │  (DATA/ACK     │
              │   exchange)    │
              └───────┬────────┘
                      │
              ┌───────┴────────┐
              ▼                ▼
       ┌───────────┐   ┌────────────┐
       │ COMPLETED │   │  FAILED    │
       │ (last ACK │   │ (timeout/  │
       │  received)│   │  error/    │
       └───────────┘   │  cancel)   │
              │        └────────────┘
              ▼                │
         Log + Stats     Log + Stats
         cleanup         cleanup
```

#### 3.2.2 Структура сессии

```rust
struct Session {
    // Идентификация
    id: SessionId,                    // уникальный UUID
    client_addr: SocketAddr,          // IP:port клиента (TID)
    server_socket: UdpSocket,         // выделенный сокет для сессии
    cancel_token: CancellationToken,  // для graceful shutdown
    
    // Тип операции
    operation: Operation,             // Read | Write
    filename: PathBuf,                // запрошенный файл (resolved)
    transfer_mode: TransferMode,      // Octet | Netascii
    
    // Negotiated параметры
    blksize: u16,                     // 512–65464
    timeout: Duration,                // 1–255 сек
    windowsize: u16,                  // 1–65535
    tsize: Option<u64>,               // размер файла (если known)
    
    // Состояние передачи
    state: SessionState,              // Negotiating | Transferring | Completed | Failed | Cancelled
    current_block: u64,               // текущий блок (u64 для rollover tracking)
    bytes_transferred: u64,           // сколько передано
    retries: u32,                     // текущий retry count
    started_at: Instant,              // начало сессии
    last_activity: Instant,           // последняя активность
    
    // Window state
    window_base: u16,                 // base block в текущем окне
    window_buffer: Vec<Bytes>,        // буфер блоков для ретрансмиссии
}
```

#### 3.2.3 Управление параллельными сессиями

- Каждая сессия — отдельная tokio task (async, НЕ OS thread)
- `SessionManager` хранит `HashMap<SessionId, SessionHandle>` под `tokio::sync::RwLock`
- `SessionHandle` содержит `JoinHandle` + `CancellationToken` для graceful shutdown
- Лимит параллельных сессий: `max_sessions` (глобальный) + `per_ip_max_sessions` (per-IP). При превышении → ERROR(0) на новые запросы
- Periodic cleanup task: каждые 10 сек проверяет stale сессии (no activity > session_timeout)

#### 3.2.4 Retransmission Logic

```
attempt = 0
timeout = negotiated_timeout

loop:
    select! {
        _ = cancel_token.cancelled() => {
            // Graceful shutdown: прекращаем сессию
            log "session cancelled by server shutdown"
            break
        }
        
        result = send_and_wait(timeout) => match result {
            Ok(response) => {
                process response
                reset attempt = 0
                continue
            }
            Err(Timeout) => {
                attempt += 1
                if attempt > max_retries {
                    abort session → ERROR
                    break
                }
                if exponential_backoff_enabled {
                    timeout = min(negotiated_timeout * 2^attempt, max_timeout)
                }
                retransmit
            }
        }
    }
```

**Конфигурация:**

```toml
[session]
max_retries = 5
max_timeout = 30         # секунд, потолок для backoff
exponential_backoff = true
session_timeout = 120    # секунд без активности → kill session
```

#### 3.2.5 Graceful Shutdown Flow

```
1. Получен сигнал STOP (SIGTERM / Ctrl+C / Service Stop)
2. server_state → Stopping
3. Main socket перестаёт принимать новые RRQ/WRQ (break из main loop)
4. SessionManager.shutdown_all():
   a. Для каждой активной сессии: cancel_token.cancel()
   b. tokio::time::timeout(30 сек, join_all(session_handles))
   c. Если по истечении 30 сек остались сессии → abort (drop tasks)
5. Закрываем main socket
6. Flush логов (tracing-appender shutdown guard)
7. Exit(0)
```

### 3.3 File System Layer

#### 3.3.1 Virtual Root & Path Security

**Требования безопасности (критично):**

Сервер ДОЛЖЕН предотвращать path traversal атаки. Все запрошенные пути резолвятся относительно root директории и каноникализируются.

**Алгоритм резолва пути:**

```
input: requested_path (из RRQ/WRQ пакета)
output: resolved_path | AccessViolation

1. Validate UTF-8 encoding (reject non-UTF-8 bytes)
2. Reject null bytes, control characters (0x00-0x1F)
3. Strip leading '/' и '\' из requested_path
4. Запретить: "..", "~", абсолютные пути
5. Platform normalize: на Windows заменить '/' → '\' 
6. resolved = canonicalize(root_dir / requested_path)
7. Проверить: resolved.starts_with(canonicalize(root_dir))
   → если нет → AccessViolation (path traversal attempt!)
8. Проверить: resolved существует (для RRQ)
9. Проверить: resolved — обычный файл (не symlink за пределы root, не directory)
10. Return resolved
```

#### 3.3.2 Virtual Roots (маппинг путей)

Позволяет создать виртуальную файловую систему поверх физических директорий:

```toml
[filesystem]
root = "/srv/tftp"       # Linux default, см. §3.5.1 для platform defaults

[filesystem.virtual_roots]
"/firmware" = "/opt/firmware-repo/latest"
"/pxe"      = "/var/lib/tftpboot"
"/configs"  = "/etc/network-configs/exported"
```

**Логика:**

1. При получении RRQ("firmware/fortigate-7.4.6.out"):
   - Матчится prefix "/firmware" → базовая директория = "/opt/firmware-repo/latest"
   - resolved = "/opt/firmware-repo/latest/fortigate-7.4.6.out"
   - Security check: путь внутри разрешённой директории? ✓
2. Если файл не найден ни в одном virtual root → проверяем в основном root
3. Virtual roots имеют приоритет над основным root

#### 3.3.3 File I/O оптимизации

**Примечание:** `sendfile(2)` / `TransmitFile` работают только с TCP-сокетами и НЕСОВМЕСТИМЫ с UDP. Для TFTP над UDP применяются следующие оптимизации:

**Memory-mapped I/O (основная стратегия):**

- `mmap` файла → данные в page cache, OS управляет подкачкой
- Для каждого блока: slice в mmap-регион + формирование TFTP DATA header (4 байта) + `send_to`
- Избегаем лишний `read` syscall — данные уже в памяти через page cache
- На маленьких файлах (< 64KB): обычный `read` в pre-allocated buffer (mmap overhead не оправдан)

**Pre-allocated Buffer Pool:**

```rust
struct BufferPool {
    buffers: Vec<BytesMut>,     // pre-allocated, recycled между сессиями
    capacity: usize,            // = max_sessions
    buf_size: usize,            // = max_blksize + 4 (TFTP header)
}
```

- При создании сессии → берём буфер из пула (O(1))
- При завершении → возвращаем в пул (без аллокации)

**Read-ahead buffer (для sliding window):**

```
read_ahead_buffer: VecDeque<Bytes> с capacity = windowsize * 2
background_reader: tokio task, читает файл ahead of current window
notification: tokio::sync::Notify когда буфер опустошается ниже порога
```

**Write buffer (для WRQ):**

```
write_buffer: BTreeMap<u16, Bytes>  # block_num → data (для out-of-order)
flush_threshold: windowsize блоков  # fsync после каждого полного окна
```

**Платформо-специфичные оптимизации (future, не MVP):**

- Linux: `io_uring` для batched sendmsg с `MSG_ZEROCOPY`
- Windows: Registered I/O (RIO) через `windows-sys`
- macOS: kqueue + scattered writes

#### 3.3.4 Ограничения

```toml
[filesystem]
max_file_size = "4GB"       # максимальный размер файла для WRQ
allow_overwrite = false      # разрешить перезапись существующих файлов при WRQ
create_dirs = false          # создавать промежуточные директории при WRQ
```

### 3.4 Access Control List (ACL)

#### 3.4.1 Модель

ACL применяется **до** создания сессии, на этапе обработки RRQ/WRQ на главном сокете. Это минимизирует ресурсозатраты на отклонённые соединения.

**Типы правил:**

```toml
[acl]
mode = "whitelist"  # whitelist | blacklist | disabled

# Whitelist: только указанные адреса/сети имеют доступ
# Blacklist: все имеют доступ, кроме указанных
# Disabled: ACL отключён, все имеют доступ

[[acl.rules]]
action = "allow"         # allow | deny
source = "192.168.1.0/24"
operations = ["read"]    # read | write | all
comment = "Office LAN — read only"

[[acl.rules]]
action = "allow"
source = "10.0.0.5/32"
operations = ["all"]
comment = "Build server — full access"

[[acl.rules]]
action = "allow"
source = "fd00::/8"
operations = ["read"]
comment = "IPv6 ULA — read access"

[[acl.rules]]
action = "deny"
source = "0.0.0.0/0"
operations = ["write"]
comment = "Default deny write from everywhere"

[[acl.rules]]
action = "deny"
source = "::/0"
operations = ["write"]
comment = "Default deny write IPv6"
```

#### 3.4.2 Алгоритм матчинга

```
input: client_ip (IPv4 or IPv6), operation (read|write)

1. Если mode == disabled → ALLOW
2. Итерируем rules сверху вниз (порядок важен!)
3. Для каждого rule:
   a. client_ip matches source CIDR? (ipnet crate, поддерживает IPv4 и IPv6)
   b. operation matches rule.operations?
   c. Если оба → return rule.action (allow|deny)
4. Default policy:
   - whitelist mode: если ни одно правило не сматчилось → DENY
   - blacklist mode: если ни одно правило не сматчилось → ALLOW
```

#### 3.4.3 Горячее обновление ACL

ACL правила перезагружаются при:
- Получении сигнала reload (SIGHUP на Unix, IPC на Windows)
- Изменении файла конфига (через `notify` crate, filesystem watcher)
- Нажатии кнопки "Reload" в GUI/TUI

Текущие сессии НЕ прерываются при изменении ACL. Новые правила применяются только к новым соединениям.

### 3.5 Конфигурация

#### 3.5.1 Полная схема конфига

```toml
# =============================================================
# TFTP Server Pro — Configuration
# =============================================================

[server]
bind_address = "::"         # dual-stack: слушает IPv4 и IPv6
port = 69                   # порт (< 1024 требует root / capabilities / elevation)
# root — platform-specific default:
#   Linux:   /srv/tftp
#   macOS:   ~/Library/TFTP
#   Windows: C:\TFTP
root = "/srv/tftp"
log_level = "info"          # trace | debug | info | warn | error
# log_file — platform-specific default:
#   Linux:   /var/log/tftp-server.log
#   macOS:   ~/Library/Logs/tftp-server.log
#   Windows: %APPDATA%\tftp-server\tftp-server.log
log_file = ""               # пусто = определяется автоматически по платформе

[network]
ip_version = "dual"         # dual | v4 | v6
# dual: bind на :: с IPV6_V6ONLY=false → принимает и v4 и v6
# v4:   bind на 0.0.0.0, только IPv4
# v6:   bind на :: с IPV6_V6ONLY=true, только IPv6
recv_buffer_size = "4MB"    # SO_RCVBUF для main socket
send_buffer_size = "4MB"    # SO_SNDBUF для main socket
session_recv_buffer = "2MB" # SO_RCVBUF для session sockets
session_send_buffer = "2MB" # SO_SNDBUF для session sockets

[protocol]
allow_write = false         # разрешить WRQ
default_blksize = 512       # blksize по умолчанию
max_blksize = 65464         # максимально допустимый blksize от клиента
default_windowsize = 1      # windowsize по умолчанию
max_windowsize = 64         # максимально допустимый windowsize
default_timeout = 3         # таймаут в секундах
min_timeout = 1
max_timeout = 255

[session]
max_sessions = 100          # максимум параллельных сессий (глобально)
max_retries = 5             # максимум ретрансмиссий на блок/окно
exponential_backoff = true  # экспоненциальный backoff при retransmit
session_timeout = 120       # секунд без активности → kill
shutdown_grace_period = 30  # секунд ожидания при graceful shutdown

[security]
per_ip_max_sessions = 10            # макс параллельных сессий с одного IP
per_ip_rate_limit = 100             # макс RRQ/WRQ запросов в минуту с одного IP
rate_limit_window_seconds = 60      # окно для rate limit
rate_limit_action = "drop"          # drop | error
                                    # drop: молча игнорируем (рекомендовано для DoS protection)
                                    # error: отвечаем ERROR(0, "rate limit exceeded")

[filesystem]
max_file_size = "4GB"       # лимит размера файла для WRQ
allow_overwrite = false     # перезапись при WRQ
create_dirs = false         # создание поддиректорий при WRQ
follow_symlinks = false     # следовать за симлинками (security risk!)

[filesystem.virtual_roots]
# "/alias" = "/real/path"

[acl]
mode = "disabled"           # whitelist | blacklist | disabled

# [[acl.rules]]
# action = "allow"
# source = "192.168.0.0/16"
# operations = ["read"]
# comment = "Local network"

[gui]
theme = "dark"              # dark | light
refresh_rate_ms = 100       # частота обновления UI
graph_history_seconds = 300 # глубина истории графиков (5 мин)

[tui]
color = true                # цветной вывод
mouse = true                # поддержка мыши
refresh_rate_ms = 250       # частота обновления TUI
```

#### 3.5.2 Platform-Specific Defaults

Compile-time defaults через `#[cfg(target_os)]`:

| Параметр | Linux | macOS | Windows |
|---|---|---|---|
| root | `/srv/tftp` | `~/Library/TFTP` | `C:\TFTP` |
| log_file | `/var/log/tftp-server.log` | `~/Library/Logs/tftp-server.log` | `%APPDATA%\tftp-server\tftp-server.log` |
| config search path | `/etc/tftp-server/config.toml` → `~/.config/tftp-server/config.toml` → `./config.toml` | `~/Library/Preferences/tftp-server/config.toml` → `./config.toml` | `%APPDATA%\tftp-server\config.toml` → `.\config.toml` |

Реализация: `dirs` crate для platform-specific директорий.

#### 3.5.3 Приоритет конфигурации

```
1. CLI аргументы (наивысший приоритет)
2. Environment variables (TFTP_SERVER_PORT, TFTP_SERVER_ROOT, etc.)
3. Config file (--config /path/to/config.toml)
4. Platform-specific default config path (см. §3.5.2)
5. Compiled-in defaults (наинизший приоритет)
```

#### 3.5.4 Горячая перезагрузка

При получении сигнала перезагрузки:

1. Парсим новый конфиг
2. Валидируем (root существует, порты валидны, и т.д.)
3. Если валидация OK → атомарно подменяем `Arc<Config>` через `ArcSwap`
4. Если валидация FAIL → логируем ошибку, оставляем старый конфиг
5. Существующие сессии продолжают с параметрами, с которыми были созданы
6. Новые сессии используют новый конфиг

**Не перезагружаемые без рестарта:**
- `bind_address`, `port` и `ip_version` (сокет уже привязан)

### 3.6 Логирование и мониторинг

#### 3.6.1 Structured Logging

Используем `tracing` crate для structured logging:

```
2026-03-12T14:32:01.234Z INFO  tftp_core::session
    event="transfer_start"
    session_id="a1b2c3d4"
    client="192.168.1.10:54321"
    file="firmware.bin"
    operation="read"
    blksize=1468
    windowsize=64
    tsize=52428800

2026-03-12T14:32:15.891Z INFO  tftp_core::session
    event="transfer_complete"
    session_id="a1b2c3d4"
    client="192.168.1.10:54321"
    file="firmware.bin"
    bytes=52428800
    duration_ms=14657
    speed_mbps=28.6
    retransmits=0

2026-03-12T14:32:20.100Z WARN  tftp_core::acl
    event="access_denied"
    client="192.168.1.99:12345"
    file="secret.bin"
    reason="ACL deny: rule #3"
```

#### 3.6.2 Realtime Statistics

`AppState` хранит live-метрики, доступные GUI/TUI:

```rust
struct AppState {
    // Глобальные счётчики (lock-free)
    total_bytes_tx: AtomicU64,
    total_bytes_rx: AtomicU64,
    total_sessions: AtomicU64,
    total_errors: AtomicU64,
    
    // Bandwidth sampling (для графиков)
    bandwidth_samples: RwLock<VecDeque<BandwidthSample>>,
    // → {timestamp, tx_bytes, rx_bytes} каждые 100ms
    
    // Active sessions
    active_sessions: RwLock<HashMap<SessionId, SessionInfo>>,
    
    // Transfer history (ring buffer, последние N)
    transfer_history: RwLock<VecDeque<TransferRecord>>,
    
    // Config (hot-reloadable)
    config: ArcSwap<Config>,
    
    // Server state
    server_state: AtomicU8,  // Running | Stopping | Stopped | Error
    
    // Shutdown coordination
    shutdown_token: CancellationToken,
    
    // Per-IP rate limiter state
    rate_limiter: RwLock<HashMap<IpAddr, RateLimiterEntry>>,
}
```

#### 3.6.3 Log Output Targets

| Target | Метод | Когда |
|---|---|---|
| GUI Log Tab | `tracing` subscriber → in-memory ring buffer | GUI mode |
| TUI Log Panel | `tracing` subscriber → crossterm renderer | TUI mode |
| Stdout | `tracing-subscriber` fmt layer | Headless mode |
| File | `tracing-appender` file layer | Если log_file задан в конфиге |
| Syslog | `tracing-syslog` (опционально) | Linux daemon mode |
| Windows Event Log | `tracing` + `windows-service` integration | Windows Service mode |

### 3.7 CLI Interface

#### 3.7.1 Аргументы командной строки

```
USAGE:
    tftp-server [OPTIONS]

OPTIONS:
    --gui                    Запуск в GUI-режиме (default, requires feature "gui")
    --tui                    Запуск в TUI-режиме (requires feature "tui")
    --headless               Запуск без интерфейса (daemon)
    
    -c, --config <PATH>      Путь к конфиг-файлу
    -r, --root <PATH>        Корневая директория (override конфига)
    -p, --port <PORT>        Порт (override конфига)
    -b, --bind <ADDRESS>     Bind address (override конфига)
    
    --allow-write            Разрешить WRQ (override конфига)
    --max-sessions <N>       Max параллельных сессий
    --blksize <N>            Max blksize
    --windowsize <N>         Max windowsize
    --ip-version <VER>       dual | v4 | v6
    
    -v, --verbose            Увеличить verbosity (-vv для debug, -vvv для trace)
    -q, --quiet              Только errors
    
    --version                Версия
    -h, --help               Справка

WINDOWS-SPECIFIC:
    --install-service        Установить как Windows Service
    --uninstall-service      Удалить Windows Service
```

Используем `clap` crate с derive API для парсинга.

---

## 4. GUI — Детальная спецификация

### 4.1 Технология

- **egui** (immediate mode GUI) через **eframe** (native window wrapper)
- Рендеринг: `wgpu` backend (Vulkan / Metal / DX12 / OpenGL fallback)
- Единый бинарник, нет внешних runtime зависимостей
- **Conditional compilation:** GUI код компилируется только при `#[cfg(feature = "gui")]`

### 4.2 Главное окно

**Заголовок:** "TFTP Server Pro" + статус (Running ● / Stopped ■) + bind address + кнопка Start/Stop

**Layout:** двухпанельный — левая навигация (sidebar), правая — содержимое вкладки.

### 4.3 Вкладки

#### 4.3.1 Dashboard

**Виджеты:**

- **Status cards (3 штуки в ряд):**
  - Active Sessions: число текущих сессий + sparkline за 60 сек
  - TX Rate: текущая скорость отдачи (MB/s) + sparkline
  - RX Rate: текущая скорость приёма (MB/s) + sparkline

- **Active Transfers Table:**

| Столбец | Описание |
|---|---|
| Client IP | IP:port клиента (IPv4 или IPv6) |
| File | Имя файла |
| Direction | ↑ Upload / ↓ Download |
| Progress | Прогресс-бар (если tsize known), иначе transferred bytes |
| Speed | Текущая скорость (MB/s) |
| Duration | Время с начала |
| Blksize | Negotiated blksize |
| Window | Negotiated windowsize |

- **Bandwidth Graph:**
  - egui_plot: линейный график TX/RX за последние 5 минут
  - Масштабирование: auto-scale Y-axis
  - Tooltip с точными значениями

#### 4.3.2 Files

- **File browser:** дерево файлов root директории
- **Path display:** текущий root path
- **Actions:** Change root (file dialog via `rfd`), Drag-drop для смены root, Refresh
- **File info:** при клике на файл — размер, дата модификации, количество раз отдавался

#### 4.3.3 Transfers

- **История трансферов:** таблица с сортировкой и фильтрацией

| Столбец | Описание |
|---|---|
| Timestamp | Время начала |
| Client | IP клиента |
| File | Имя файла |
| Direction | Read / Write |
| Size | Размер переданных данных |
| Duration | Длительность |
| Speed | Средняя скорость |
| Status | Completed ✓ / Failed ✗ / In Progress ⟳ |
| Retransmits | Количество ретрансмиссий |

- **Фильтры:** по IP, по файлу, по статусу, по дате
- **Export:** CSV / JSON

#### 4.3.4 Log

- **Realtime лог** с auto-scroll (отключается при скролле вверх)
- **Color coding:** TRACE → серый, DEBUG → голубой, INFO → зелёный, WARN → жёлтый, ERROR → красный
- **Фильтры:** по уровню, по тексту (substring search)
- **Actions:** Clear, Copy, Export to file
- **Buffer:** последние 10,000 строк (настраиваемо)

#### 4.3.5 Config

- **Визуальный редактор конфига** с группами:
  - Server Settings (port, bind, root, ip_version)
  - Protocol Settings (blksize, windowsize, timeout, allow_write)
  - Session Settings (max_sessions, retries, timeouts)
  - Security Settings (per_ip_max_sessions, rate_limit)
  - Filesystem Settings (max_file_size, overwrite, symlinks)
- **Validation:** realtime валидация при вводе (подсветка ошибок)
- **Apply:** кнопка "Apply" для горячей перезагрузки
- **Reset:** кнопка "Reset to defaults"
- **Import/Export:** загрузка/сохранение TOML файла

#### 4.3.6 ACL

- **Rules table:**

| # | Action | Source CIDR | Operations | Comment | Enabled |
|---|---|---|---|---|---|
| 1 | Allow | 192.168.1.0/24 | Read | Office LAN | ✓ |
| 2 | Allow | fd00::/8 | Read | IPv6 ULA | ✓ |
| 3 | Allow | 10.0.0.5/32 | All | Build server | ✓ |
| 4 | Deny | 0.0.0.0/0 | Write | Default deny write | ✓ |
| 5 | Deny | ::/0 | Write | Default deny write v6 | ✓ |

- **Actions:** Add rule, Delete rule, Reorder (drag-drop), Toggle enable/disable
- **CIDR validator:** inline validation при вводе (IPv4 и IPv6 CIDR)
- **Mode selector:** Whitelist / Blacklist / Disabled

### 4.4 System Tray

- Реализация через **`tray-icon`** crate (egui не поддерживает tray нативно)
- `tray-icon` работает в отдельном thread, коммуникация с egui через `mpsc` channel
- Minimize to tray (опционально)
- Tray icon: зелёный = running, серый = stopped, красный = error
- Context menu: Show / Start / Stop / Quit
- Кросс-платформенный: Windows (System Tray), macOS (Menu Bar), Linux (via DBus/AppIndicator)

### 4.5 Дизайн

- **Тема:** Dark (default) / Light (toggle)
- **Цвета (dark):** фон #1a1a2e, sidebar #16213e, accent #0f3460, text #e0e0e0
- **Шрифты:** встроенный Noto Sans (для Unicode-совместимости)
- **Responsive:** корректное поведение при resize окна

---

## 5. TUI — Детальная спецификация

### 5.1 Технология

- **ratatui** (successor tui-rs) + **crossterm** backend
- Работает в любом VT100-совместимом терминале
- Поддержка 256 цветов и true color
- **Conditional compilation:** TUI код компилируется только при `#[cfg(feature = "tui")]`

### 5.2 Feature Parity с GUI

Все данные из `AppState` доступны в TUI. Вкладки аналогичны GUI:

| Клавиша | Вкладка |
|---|---|
| 1 | Dashboard |
| 2 | Files |
| 3 | Transfers |
| 4 | Log |
| 5 | Config |
| 6 | ACL |

### 5.3 Управление

| Клавиша | Действие |
|---|---|
| Tab / Shift+Tab | Переключение фокуса между панелями |
| ↑↓ / j/k | Навигация по спискам/таблицам |
| Enter | Выбор / открытие |
| q | Quit (с подтверждением) |
| s | Start/Stop сервер |
| r | Reload конфиг |
| / | Поиск/фильтр в текущей вкладке |
| ? | Справка |

### 5.4 Popup-диалоги

Для редактирования параметров в Config и ACL — модальные popup'ы поверх основного UI (аналог vim command mode).

---

## 6. Headless Mode

### 6.1 Описание

Запуск без какого-либо интерфейса. Весь вывод — в stdout/stderr и лог-файл. Предназначен для:

- systemd unit (Linux)
- launchd daemon (macOS)
- Windows Service
- Docker container
- CI/CD pipeline

### 6.2 Кросс-платформенная обработка сигналов и управление

#### 6.2.1 Unix (Linux, macOS)

| Сигнал | Действие |
|---|---|
| SIGHUP | Reload конфиг |
| SIGTERM | Graceful shutdown (ждём завершения текущих сессий до shutdown_grace_period) |
| SIGINT | Graceful shutdown (аналогично SIGTERM) |
| SIGUSR1 | Dump текущего состояния в лог |

Реализация: `tokio::signal::unix::signal(SignalKind::*)` под `#[cfg(unix)]`.

#### 6.2.2 Windows

| Событие | Действие |
|---|---|
| CTRL+C | Graceful shutdown |
| CTRL+BREAK | Immediate shutdown |
| SERVICE_CONTROL_STOP | Graceful shutdown (от services.msc / sc.exe) |
| SERVICE_CONTROL_SHUTDOWN | Graceful shutdown (при завершении Windows) |
| SERVICE_CONTROL_PARAMCHANGE | Reload конфиг |

Реализация:
- `ctrlc` crate для CTRL+C/BREAK в консольном режиме
- `windows-service` crate для Service Control Handler
- Дополнительный IPC: Named Pipe `\\.\pipe\tftp-server-control` для команд reload/status из CLI (работает и под Service, и в консоли)

#### 6.2.3 Универсальный IPC (все платформы)

Для управления headless-сервером из других процессов:

```
Unix:   unix domain socket /run/tftp-server.sock
Windows: Named Pipe \\.\pipe\tftp-server-control
```

Команды через IPC: `reload`, `stop`, `status` (JSON response).

### 6.3 systemd Unit (Linux)

```ini
[Unit]
Description=TFTP Server Pro
After=network.target

[Service]
Type=notify
ExecStart=/usr/local/bin/tftp-server --headless -c /etc/tftp-server/config.toml
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
User=tftp
Group=tftp
AmbientCapabilities=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/srv/tftp /var/log/tftp-server
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

### 6.4 Windows Service

Реализация через `windows-service` crate. Поддержка:
- `tftp-server --install-service` — регистрация в SCM
- `tftp-server --uninstall-service` — удаление из SCM
- Start/Stop через services.msc / `sc.exe start tftp-server`
- Event Log integration через `windows-service` event reporting
- UAC: для порта 69 требуется запуск от администратора. При установке как Service — Service работает под `LocalSystem` или custom service account

### 6.5 launchd Daemon (macOS)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.2f-it.tftp-server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/tftp-server</string>
        <string>--headless</string>
        <string>-c</string>
        <string>/usr/local/etc/tftp-server/config.toml</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/usr/local/var/log/tftp-server.out.log</string>
    <key>StandardErrorPath</key>
    <string>/usr/local/var/log/tftp-server.err.log</string>
</dict>
</plist>
```

Установка: `sudo cp com.2f-it.tftp-server.plist /Library/LaunchDaemons/` → `sudo launchctl load ...`

### 6.6 Docker

```dockerfile
FROM rust:1.77-slim AS builder
WORKDIR /build
COPY . .
RUN cargo build --release --no-default-features

FROM debian:bookworm-slim
COPY --from=builder /build/target/release/tftp-server /usr/local/bin/tftp-server
EXPOSE 69/udp
VOLUME /srv/tftp
# ВАЖНО: --net=host рекомендуется для TFTP (ephemeral session ports)
# Иначе нужен range: -p 69:69/udp -p 10000-60000:10000-60000/udp
ENTRYPOINT ["tftp-server", "--headless"]
```

**Docker networking note:** TFTP использует эфемерный порт для каждой сессии. `docker run -p 69:69/udp` пробросит только main socket. Session sockets (ephemeral ports) НЕ будут доступны. Решения:

- **Рекомендовано:** `docker run --net=host` (Linux only)
- **Альтернатива:** `-p 69:69/udp -p 10000-60000:10000-60000/udp` (тяжело для Docker)
- **macOS/Windows Docker:** только через host networking в VM

---

## 7. Архитектура проекта

### 7.1 Cargo Workspace

```
tftp-server/                    # workspace root
├── Cargo.toml                  # workspace + единственный binary crate
├── src/
│   ├── main.rs                 # entry point, CLI dispatch (gui/tui/headless)
│   ├── lib.rs                  # re-export core
│   ├── core/                   # protocol engine, сессии, FS, ACL, конфиг
│   │   ├── mod.rs
│   │   ├── protocol/           # packet parsing (zero-copy)
│   │   ├── session/            # SessionManager, per-client state
│   │   ├── fs/                 # FileSystem abstraction + virtual roots
│   │   ├── acl/                # IP rules, CIDR matching
│   │   ├── config/             # TOML config, validation, hot reload
│   │   ├── net/                # Network layer, socket setup, dual-stack
│   │   └── state.rs            # AppState
│   ├── gui/                    # #[cfg(feature = "gui")] egui frontend
│   │   ├── mod.rs
│   │   ├── app.rs
│   │   ├── tabs/
│   │   └── tray.rs             # tray-icon integration
│   ├── tui/                    # #[cfg(feature = "tui")] ratatui frontend
│   │   ├── mod.rs
│   │   └── app.rs
│   ├── headless/               # headless/daemon mode
│   │   └── mod.rs
│   └── platform/               # #[cfg(unix)] / #[cfg(windows)] specifics
│       ├── mod.rs
│       ├── unix.rs             # signals, socket options, privilege drop
│       └── windows.rs          # service, named pipe IPC, UAC
├── config/
│   └── default.toml
├── deploy/
│   ├── systemd/
│   │   └── tftp-server.service
│   ├── launchd/
│   │   └── com.2f-it.tftp-server.plist
│   └── docker/
│       └── Dockerfile
├── tests/
│   ├── integration/            # интеграционные тесты
│   ├── fixtures/               # тестовые файлы
│   └── test_client/            # минимальный TFTP клиент для тестов
├── benches/                    # benchmarks (criterion)
├── fuzz/                       # cargo-fuzz targets
│   └── fuzz_targets/
│       └── packet_parser.rs
├── .github/
│   └── workflows/
│       ├── ci.yml              # lint + test + clippy + audit
│       └── release.yml         # matrix build + sign + package
├── Makefile
└── rust-toolchain.toml         # MSRV pinning
```

### 7.2 Архитектура модулей

```
main.rs
  │
  ├── #[cfg(feature = "gui")]  → gui::run(AppState)
  ├── #[cfg(feature = "tui")]  → tui::run(AppState)
  └── headless::run(AppState)  → always available
  
  All modes share:
  └── core::Server::new(config) → Arc<AppState>
        ├── core::net::MainSocket      (dual-stack UDP listener)
        ├── core::session::SessionMgr  (tokio tasks)
        ├── core::protocol::*          (packet parse/serialize)
        ├── core::fs::*                (path resolve, I/O)
        ├── core::acl::*               (IP rule matching)
        └── core::config::*            (TOML, hot reload)
```

### 7.3 AppState — связующее звено

`core` экспортирует `AppState` как `Arc<AppState>`. Все фронтенды получают один и тот же `AppState` и подписываются на обновления.

Обновление данных: core engine пишет в `AppState` (через атомики и RwLock), фронтенды периодически читают (GUI каждые 100ms, TUI каждые 250ms).

### 7.4 Ключевые зависимости

```toml
[dependencies]
# === Core (always compiled) ===
tokio = { version = "1", features = ["full"] }
socket2 = "0.5"
bytes = "1"
toml = "0.8"
serde = { version = "1", features = ["derive"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
tracing-appender = "0.2"
ipnet = "2"                # IPv4 + IPv6 CIDR matching
arc-swap = "1"             # atomic config swap
notify = "6"               # filesystem watcher для hot reload
uuid = { version = "1", features = ["v4"] }
thiserror = "2"            # ergonomic error types
anyhow = "1"               # error propagation
clap = { version = "4", features = ["derive"] }
dirs = "5"                 # platform-specific dirs
tokio-util = "0.7"         # CancellationToken
ctrlc = "3"                # cross-platform Ctrl+C

# === GUI (optional) ===
eframe = { version = "0.27", optional = true }
egui = { version = "0.27", optional = true }
egui_plot = { version = "0.27", optional = true }
rfd = { version = "0.14", optional = true }     # native file dialog
tray-icon = { version = "0.14", optional = true }

# === TUI (optional) ===
ratatui = { version = "0.26", optional = true }
crossterm = { version = "0.27", optional = true }

# === Platform-specific ===
[target.'cfg(unix)'.dependencies]
nix = { version = "0.28", features = ["signal", "fs", "net", "mman"] }

[target.'cfg(windows)'.dependencies]
windows-service = "0.7"
windows-sys = { version = "0.52", features = [
    "Win32_Networking_WinSock",
    "Win32_System_Pipes",
] }

# === Dev/Test ===
[dev-dependencies]
criterion = { version = "0.5", features = ["html_reports"] }
tokio-test = "0.4"
tempfile = "3"
proptest = "1"             # property-based testing

[features]
default = ["gui", "tui"]
gui = ["dep:eframe", "dep:egui", "dep:egui_plot", "dep:rfd", "dep:tray-icon"]
tui = ["dep:ratatui", "dep:crossterm"]
```

---

## 8. Сетевой слой — детали реализации

### 8.1 Main Socket (Dual-Stack)

```rust
fn create_main_socket(config: &Config) -> Result<UdpSocket> {
    let (domain, bind_addr) = match config.network.ip_version {
        IpVersion::Dual => {
            // IPv6 socket с IPV6_V6ONLY=false → принимает и IPv4 (mapped) и IPv6
            let socket = Socket::new(Domain::IPV6, Type::DGRAM, Some(Protocol::UDP))?;
            socket.set_only_v6(false)?;  // dual-stack!
            (socket, SocketAddr::from((Ipv6Addr::UNSPECIFIED, config.server.port)))
        }
        IpVersion::V4 => {
            let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
            (socket, SocketAddr::from((Ipv4Addr::UNSPECIFIED, config.server.port)))
        }
        IpVersion::V6 => {
            let socket = Socket::new(Domain::IPV6, Type::DGRAM, Some(Protocol::UDP))?;
            socket.set_only_v6(true)?;   // IPv6 only
            (socket, SocketAddr::from((Ipv6Addr::UNSPECIFIED, config.server.port)))
        }
    };

    socket.set_reuse_address(true)?;
    socket.set_nonblocking(true)?;
    socket.set_recv_buffer_size(config.network.recv_buffer_size)?;
    socket.set_send_buffer_size(config.network.send_buffer_size)?;
    socket.bind(&SockAddr::from(bind_addr))?;

    Ok(tokio::net::UdpSocket::from_std(socket.into())?)
}
```

**Dual-stack note:** При dual-stack IPv4-клиенты приходят как `::ffff:192.168.1.10`. ACL engine маппит `::ffff:0:0/96` автоматически к IPv4 CIDR при матчинге. `ipnet` crate поддерживает это из коробки.

### 8.2 Per-Session Socket

Каждая сессия создаёт свой UDP socket на эфемерном порту:

```rust
let session_socket = Socket::new(domain, Type::DGRAM, Some(Protocol::UDP))?;
session_socket.set_nonblocking(true)?;
session_socket.set_recv_buffer_size(config.network.session_recv_buffer)?;
session_socket.set_send_buffer_size(config.network.session_send_buffer)?;
session_socket.bind(&SockAddr::from(SocketAddr::from((bind_addr, 0))))?;
// port 0 → ОС выделяет эфемерный порт

let tokio_session = tokio::net::UdpSocket::from_std(session_socket.into())?;
tokio_session.connect(client_addr).await?;
```

### 8.3 Main Loop

```rust
loop {
    tokio::select! {
        _ = shutdown_token.cancelled() => {
            tracing::info!("Server shutdown initiated");
            break;
        }
        
        result = main_socket.recv_from(&mut buf) => {
            let (len, client_addr) = result?;
            let packet = match parse_packet(&buf[..len]) {
                Ok(p) => p,
                Err(e) => {
                    tracing::warn!(client=%client_addr, error=%e, "malformed packet");
                    continue;
                }
            };

            match packet {
                Packet::Rrq { filename, mode, options } => {
                    let client_ip = client_addr.ip();
                    
                    // Rate limit check
                    if !rate_limiter.check(client_ip) {
                        tracing::warn!(client=%client_ip, "rate limit exceeded");
                        if config.security.rate_limit_action == "error" {
                            send_error(&main_socket, client_addr, 0, "Rate limit exceeded").await;
                        }
                        continue;
                    }
                    
                    // ACL check
                    if !acl.check(client_ip, Operation::Read) {
                        send_error(&main_socket, client_addr, 2, "Access denied").await;
                        continue;
                    }
                    
                    // Per-IP session limit
                    if session_mgr.count_by_ip(client_ip) >= config.security.per_ip_max_sessions {
                        send_error(&main_socket, client_addr, 0, "Too many sessions").await;
                        continue;
                    }
                    
                    // Global session limit
                    if session_mgr.count() >= config.session.max_sessions {
                        send_error(&main_socket, client_addr, 0, "Server busy").await;
                        continue;
                    }
                    
                    session_mgr.spawn_read_session(client_addr, filename, mode, options).await;
                }
                
                Packet::Wrq { filename, mode, options } => {
                    if !config.protocol.allow_write {
                        send_error(&main_socket, client_addr, 2, "Write not allowed").await;
                        continue;
                    }
                    // ... аналогичные проверки (rate limit, ACL, session limits) ...
                    session_mgr.spawn_write_session(client_addr, filename, mode, options).await;
                }
                
                _ => {
                    send_error(&main_socket, client_addr, 4, "Illegal operation").await;
                }
            }
        }
    }
}

// Graceful shutdown
session_mgr.shutdown_all(config.session.shutdown_grace_period).await;
```

### 8.4 Resource Limits Check at Startup

```rust
fn check_system_limits(config: &Config) {
    #[cfg(unix)]
    {
        let (soft, hard) = nix::sys::resource::getrlimit(Resource::RLIMIT_NOFILE).unwrap();
        let needed = (config.session.max_sessions as u64) * 2 + 32; // sessions + overhead
        if soft < needed {
            tracing::warn!(
                "File descriptor limit ({soft}) may be insufficient for {max} sessions. \
                 Recommend: ulimit -n {needed}",
                max = config.session.max_sessions
            );
        }
    }
}
```

---

## 9. Packet Format — бинарная спецификация

### 9.1 Общий формат

Все пакеты начинаются с 2-байтового opcode (big-endian):

```
Offset  Size    Field
0       2       opcode (u16 BE)
2       var     payload (зависит от opcode)
```

### 9.2 RRQ / WRQ (opcode 1, 2)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Opcode (1/2)          |    Filename (variable)  | 0 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Mode ("octet"/"netascii")                            | 0 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Option Name (optional)                               | 0 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Option Value (optional)                              | 0 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

Строки null-terminated. Опции идут парами (name, value) после mode.

### 9.3 DATA (opcode 3)

```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Opcode (3)            |         Block #               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Data (0 to blksize octets)                                 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- Block# starts at 1
- Последний DATA: len(data) < blksize
- Zero-byte файл: один DATA пакет с data length = 0

### 9.4 ACK (opcode 4)

```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Opcode (4)            |         Block #               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

4 байта. ACK(0) = подтверждение WRQ (без опций) или подтверждение OACK (при RRQ с опциями).

### 9.5 ERROR (opcode 5)

```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Opcode (5)            |         ErrorCode             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    ErrMsg (variable)                                    | 0 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### 9.6 OACK (opcode 6)

```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Opcode (6)            |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+                               +
|    Option Name                                          | 0 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Option Value                                         | 0 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

Повторяется для каждой принятой опции.

### 9.7 Zero-Copy Parsing

Парсинг пакетов через `bytes::Bytes` — zero-copy slicing:

```rust
struct ParsedPacket<'a> {
    opcode: u16,
    payload: PacketPayload<'a>,
}

enum PacketPayload<'a> {
    Rrq { filename: &'a str, mode: &'a str, options: Vec<(&'a str, &'a str)> },
    Wrq { filename: &'a str, mode: &'a str, options: Vec<(&'a str, &'a str)> },
    Data { block: u16, data: &'a [u8] },
    Ack { block: u16 },
    Error { code: u16, message: &'a str },
    Oack { options: Vec<(&'a str, &'a str)> },
}
```

---

## 10. Error Handling Strategy

### 10.1 Error Categories

| Категория | Примеры | Действие |
|---|---|---|
| Protocol Error | Malformed packet, wrong opcode | ERROR packet → клиенту, log WARN |
| File Error | Not found, permission denied, disk full | ERROR packet → клиенту, log ERROR |
| Network Error | Send failed, socket error | Retry if transient, abort if persistent |
| Session Error | Timeout, max retries exceeded | Abort session, log WARN |
| Config Error | Invalid TOML, bad path | Reject reload, log ERROR, keep old config |
| System Error | Out of memory, fd limit | Log FATAL, graceful degradation |

### 10.2 Error Types

```rust
#[derive(Debug, thiserror::Error)]
pub enum TftpError {
    #[error("Protocol error: {0}")]
    Protocol(ProtocolError),
    
    #[error("File error: {0}")]
    File(#[from] std::io::Error),
    
    #[error("ACL denied: {client} → {reason}")]
    AclDenied { client: IpAddr, reason: String },
    
    #[error("Session limit reached: {current}/{max}")]
    SessionLimit { current: usize, max: usize },
    
    #[error("Rate limit exceeded: {client}")]
    RateLimited { client: IpAddr },
    
    #[error("Config error: {0}")]
    Config(String),
    
    #[error("Path traversal attempt: {0}")]
    PathTraversal(String),
}

#[derive(Debug, thiserror::Error)]
pub enum ProtocolError {
    #[error("Malformed packet: {0}")]
    Malformed(String),
    
    #[error("Unknown opcode: {0}")]
    UnknownOpcode(u16),
    
    #[error("Option negotiation failed: {0}")]
    OptionNegotiation(String),
    
    #[error("Unexpected packet in state {state}: got {opcode}")]
    UnexpectedPacket { state: String, opcode: u16 },
    
    #[error("Invalid filename encoding")]
    InvalidFilename,
}
```

---

## 11. Security Model

### 11.1 Threat Model

| Угроза | Митигация |
|---|---|
| Path traversal (../../etc/passwd) | Canonicalize + prefix check (§3.3.1) |
| Symlink escape | `follow_symlinks = false` по умолчанию |
| DoS через массовые сессии | `max_sessions` + `per_ip_max_sessions` + `per_ip_rate_limit` (§3.5.1) |
| Buffer overflow | Rust memory safety (compile-time) |
| Unauthorized write | `allow_write = false` по умолчанию + ACL |
| Man-in-the-middle | N/A (TFTP is inherently insecure by design — документируем) |
| Resource exhaustion (fd) | fd limit check at startup (§8.4), session timeouts, file size limits |
| Malformed packet crash | Defensive parsing, fuzz-tested (§12.4), all errors handled |
| UDP amplification | Limit response size, verify source (connected session sockets) |
| Sorcerer's Apprentice | Duplicate ACK protection (§3.1.1) |
| Filename injection | UTF-8 validation, forbidden chars, path canonicalization (§3.3.1) |

### 11.2 Hardening Defaults

- WRQ **отключён** по умолчанию
- ACL **disabled** по умолчанию (open), но документация рекомендует включить
- `follow_symlinks = false`
- `allow_overwrite = false`
- `create_dirs = false`
- Per-IP rate limiting **включён** (100 req/min default)
- Bind на `::` (dual-stack, все интерфейсы) — документируем рекомендацию bind на конкретный интерфейс
- Запуск под непривилегированным пользователем + `CAP_NET_BIND_SERVICE` (Linux)

### 11.3 Privilege Separation

Порт 69 < 1024, требует elevated privileges:

- **Linux:** `setcap cap_net_bind_service=+ep /usr/local/bin/tftp-server` или systemd `AmbientCapabilities`
- **Windows:** запуск от администратора (GUI), или как Windows Service (automatic elevation). Application manifest: `requireAdministrator` для GUI executable
- **macOS:** `sudo` для bind, затем drop privileges. Или launchd (запускается от root, drop-to-user)

### 11.4 TFTP Security Disclaimer

TFTP (RFC 1350) — протокол без аутентификации и шифрования by design. Данные передаются в открытом виде. Этот сервер НЕ предназначен для передачи конфиденциальных данных через ненадёжные сети. Рекомендуется использовать в изолированных сетях (management VLAN, out-of-band network).

---

## 12. Тестирование

### 12.1 Unit Tests

| Модуль | Что тестируем |
|---|---|
| protocol/ | Parsing всех типов пакетов (valid + malformed), serialization round-trip, Sorcerer's Apprentice protection |
| session/ | State machine transitions (все 4 OACK flow), timeout logic, retransmit logic, cancellation |
| fs/ | Path resolution, traversal prevention, virtual roots, zero-byte files, UTF-8 filenames |
| acl/ | Rule matching, CIDR parsing (IPv4 + IPv6), whitelist/blacklist modes, IPv4-mapped IPv6 |
| config/ | TOML parsing, platform defaults, validation, merge priority |
| net/ | Dual-stack socket creation, IPv4-mapped address handling |

### 12.2 Integration Tests

| Тест | Описание |
|---|---|
| Basic RRQ | Клиент запрашивает файл, получает все блоки, сверяет checksum |
| Basic WRQ | Клиент отправляет файл, сервер сохраняет, сверяем |
| Zero-byte file | RRQ на пустой файл → один DATA с empty payload → ACK → complete |
| OACK RRQ flow | RRQ с опциями → OACK → ACK(0) → DATA(1) |
| OACK WRQ flow | WRQ с опциями → OACK → DATA(1) (НЕ ACK(0)!) |
| Sliding window | Transfer с windowsize > 1, проверка throughput и корректности |
| Block rollover | Файл > 32MB при blksize=512, проверка rollover |
| ACL deny | Запрос от заблокированного IP → ERROR(2) |
| ACL IPv6 | IPv6 клиент с IPv6 CIDR rule → корректный матчинг |
| Path traversal | RRQ("../../etc/passwd") → ERROR(2) |
| Rate limit | 101 запрос за 60 сек → drop/error на 101-м |
| Per-IP session limit | 11 сессий с одного IP → ERROR на 11-й |
| Concurrent sessions | 50 параллельных трансферов, все завершаются корректно |
| Large file | Transfer файла 1GB+ с sliding window |
| Netascii | Line ending conversion round-trip |
| Config reload | Изменение конфига на лету, проверка новых параметров |
| Timeout / retransmit | Симуляция packet loss, проверка retransmit |
| Graceful shutdown | SIGTERM во время активных трансферов → текущие завершаются, новые отвергаются |
| Duplicate ACK | Симуляция Sorcerer's Apprentice → дубликат DATA не отправляется |

### 12.3 Benchmarks

С использованием `criterion` crate:

| Benchmark | Что измеряем |
|---|---|
| packet_parse | Парсинг 1M пакетов разных типов |
| packet_serialize | Сериализация 1M пакетов |
| throughput_localhost | Максимальный throughput на localhost |
| session_creation | Время создания 10,000 сессий |
| acl_matching | Matching 100 rules против 1M IP адресов (IPv4 + IPv6) |
| path_resolution | Резолв 100K путей |

### 12.4 Fuzz Testing

С использованием `cargo-fuzz` + `libfuzzer`:

```rust
// fuzz/fuzz_targets/packet_parser.rs
fuzz_target!(|data: &[u8]| {
    let _ = parse_packet(data);  // не должен паникать ни на каком input
});
```

Дополнительно: `proptest` для property-based testing:
- Roundtrip: `serialize(parse(data)) == data` для валидных пакетов
- Invariant: `parse(random_bytes)` никогда не паникует

### 12.5 Тестовый клиент

Минимальный TFTP-клиент на Rust в `tests/test_client/`:
- RRQ/WRQ с опциями (все 4 flow из §3.1.2)
- Configurable blksize, windowsize
- IPv4 и IPv6 поддержка
- Packet loss simulation (drop N% пакетов)
- Duplicate ACK simulation (Sorcerer's Apprentice test)
- Concurrent mode (N параллельных клиентов)

---

## 13. Build & Release Pipeline

### 13.1 CI (GitHub Actions)

**ci.yml:**

```yaml
on: [push, pull_request]
jobs:
  lint:
    - cargo fmt --check
    - cargo clippy -- -D warnings
    - cargo audit                    # CVE check зависимостей
  test:
    matrix: [ubuntu-latest, windows-latest, macos-latest]
    steps:
      - cargo test --workspace
      - cargo test --workspace --no-default-features           # headless only
      - cargo test --workspace --no-default-features --features tui  # tui only
  coverage:
    - cargo tarpaulin --out xml      # threshold ≥ 80%
  bench:
    - cargo bench --workspace        # only on main
  fuzz:
    - cargo fuzz run packet_parser -- -max_total_time=60  # only on main
```

**MSRV:** Зафиксирован в `rust-toolchain.toml` и `Cargo.toml` (`rust-version = "1.75"`).

### 13.2 Release Build

**release.yml (on tag push):**

Matrix build для всех target platforms:

| Platform | Target | Runner | Notes |
|---|---|---|---|
| Windows x64 | x86_64-pc-windows-msvc | windows-latest | Native, code signed |
| Windows x86 | i686-pc-windows-msvc | windows-latest | Native, code signed |
| Linux x64 (glibc) | x86_64-unknown-linux-gnu | ubuntu-latest | Native |
| Linux x64 (musl) | x86_64-unknown-linux-musl | ubuntu-latest | Fully static binary |
| Linux ARM64 (glibc) | aarch64-unknown-linux-gnu | ubuntu-latest | via `cross` |
| Linux ARM64 (musl) | aarch64-unknown-linux-musl | ubuntu-latest | via `cross`, static |
| macOS Intel | x86_64-apple-darwin | macos-13 | Native, signed + notarized |
| macOS ARM | aarch64-apple-darwin | macos-14 | Native (M1), signed + notarized |

**Headless-only builds** (additional matrix): all targets above с `--no-default-features` → binary без GUI/TUI зависимостей.

### 13.3 Code Signing

| Platform | Метод | CI Secret |
|---|---|---|
| Windows | Authenticode (`signtool.exe`) | `WINDOWS_CERT_PFX` + `WINDOWS_CERT_PASSWORD` |
| macOS | Apple Developer ID (`codesign` + `notarytool`) | `APPLE_CERT_P12` + `APPLE_ID` + `APPLE_TEAM_ID` |
| Linux | GPG detached signature (.sig) | `GPG_PRIVATE_KEY` |

### 13.4 Packaging

| Platform | Format | Инструмент |
|---|---|---|
| Windows | MSI installer | `cargo-wix` (firewall rule, PATH, Service registration) |
| macOS | DMG + Homebrew formula | `create-dmg` + formula в tap repo |
| Debian/Ubuntu | .deb | `cargo-deb` |
| RHEL/Fedora | .rpm | `cargo-generate-rpm` |
| Arch | AUR PKGBUILD | Manual |
| Docker | Container image | Dockerfile (§6.6) → Docker Hub / GHCR |
| All | .zip / .tar.gz | Raw binary archives |

### 13.5 Versioning

Semantic Versioning (semver): `MAJOR.MINOR.PATCH`

- MAJOR: breaking changes в конфиге / API core
- MINOR: новая функциональность
- PATCH: bugfixes

Начальная версия: `0.1.0` (pre-release)

---

## 14. Этапы разработки (Roadmap)

### Phase 1 — Core Engine (MVP)

**Цель:** рабочий TFTP-сервер в headless-режиме с базовым протоколом + dual-stack.

| # | Задача | Приоритет |
|---|---|---|
| 1.1 | Project structure + Cargo.toml с feature flags | P0 |
| 1.2 | Platform module (`platform/unix.rs`, `platform/windows.rs`) | P0 |
| 1.3 | Packet parser/serializer (RFC 1350) + Sorcerer's Apprentice protection | P0 |
| 1.4 | Main socket listener (dual-stack IPv4/IPv6) + session spawning | P0 |
| 1.5 | RRQ handler (basic, stop-and-wait) + OACK flow (RRQ + WRQ) | P0 |
| 1.6 | File system abstraction + path security + filename encoding | P0 |
| 1.7 | TOML конфиг + platform defaults + CLI args (clap) | P0 |
| 1.8 | Structured logging (tracing) + platform log targets | P0 |
| 1.9 | Graceful shutdown (CancellationToken) + signal handling (Unix + Windows) | P0 |
| 1.10 | Unit tests + fuzz target для parser | P0 |
| 1.11 | Integration test с basic RRQ (IPv4 + IPv6) | P0 |
| 1.12 | Resource limits check at startup (fd, ulimit) | P1 |

**Deliverable:** `cargo run -- --headless -r ./testfiles` → клиент может скачать файл по IPv4 и IPv6.

### Phase 2 — Full Protocol

**Цель:** полная реализация всех RFC, включая sliding window.

| # | Задача | Приоритет |
|---|---|---|
| 2.1 | OACK / Option Extension (RFC 2347) — все 4 flow | P0 |
| 2.2 | blksize negotiation (RFC 2348) | P0 |
| 2.3 | timeout + tsize (RFC 2349) | P0 |
| 2.4 | windowsize / Sliding Window (RFC 7440) | P0 |
| 2.5 | WRQ handler (write support) | P1 |
| 2.6 | Netascii mode | P1 |
| 2.7 | Block number rollover | P1 |
| 2.8 | Retransmission + exponential backoff | P0 |
| 2.9 | ACL engine (whitelist/blacklist, CIDR, IPv4+IPv6) | P1 |
| 2.10 | Per-IP rate limiting + per-IP session limit | P0 |
| 2.11 | Virtual roots | P2 |
| 2.12 | Hot config reload (signals + file watcher + IPC) | P1 |
| 2.13 | Zero-byte file handling | P1 |
| 2.14 | Benchmarks (criterion) | P1 |

**Deliverable:** headless-сервер, проходящий все integration tests включая sliding window + dual-stack.

### Phase 3 — GUI

**Цель:** полнофункциональный графический интерфейс.

| # | Задача | Приоритет |
|---|---|---|
| 3.1 | eframe app skeleton + AppState integration | P0 |
| 3.2 | Dashboard (status cards + active transfers table) | P0 |
| 3.3 | Bandwidth graph (egui_plot) | P1 |
| 3.4 | Files tab (file browser) | P1 |
| 3.5 | Transfers tab (history + filters) | P1 |
| 3.6 | Log tab (realtime, color-coded, filter) | P0 |
| 3.7 | Config tab (visual editor + apply) | P1 |
| 3.8 | ACL tab (rules table + editor, IPv6 support) | P1 |
| 3.9 | Dark/Light theme | P2 |
| 3.10 | System tray (tray-icon crate) | P2 |

**Deliverable:** GUI-приложение с полным мониторингом и управлением.

### Phase 4 — TUI

**Цель:** консольный интерфейс для серверов.

| # | Задача | Приоритет |
|---|---|---|
| 4.1 | ratatui app skeleton + AppState | P0 |
| 4.2 | Dashboard + Transfers | P0 |
| 4.3 | Log panel | P0 |
| 4.4 | Config / ACL editing popups | P1 |
| 4.5 | Mouse support | P2 |

### Phase 5 — Polish & Release

| # | Задача | Приоритет |
|---|---|---|
| 5.1 | GitHub Actions CI/CD (lint, test, coverage, fuzz, audit) | P0 |
| 5.2 | Cross-compile pipeline (all targets + musl static) | P0 |
| 5.3 | Code signing (Windows Authenticode + macOS Notarization) | P1 |
| 5.4 | Native installers (MSI, DMG, .deb, .rpm) | P1 |
| 5.5 | systemd unit + launchd plist + Windows Service installer | P1 |
| 5.6 | Docker image (with networking documentation) | P2 |
| 5.7 | README + documentation + firewall instructions | P0 |
| 5.8 | Security audit (fuzzing extended, clippy strict, `cargo audit`) | P1 |
| 5.9 | Performance optimization pass (mmap, buffer pool) | P1 |
| 5.10 | v0.1.0 release | P0 |

---

## 15. Open Questions / Future Scope

| # | Вопрос | Статус |
|---|---|---|
| OQ-1 | MTFTP (multicast TFTP, RFC 2090)? | Deferred (v0.3) |
| OQ-2 | Plugin system для custom hooks (pre-transfer, post-transfer)? | Under discussion |
| OQ-3 | REST API для удалённого мониторинга/управления? | Deferred (v0.3) |
| OQ-4 | Prometheus metrics endpoint (headless)? | Deferred (v0.2) |
| OQ-5 | Auto-update mechanism? | Under discussion |
| OQ-6 | TFTP Proxy mode (relay)? | Under discussion |
| OQ-7 | PXE-specific optimizations (boot menu, chainloading)? | Under discussion |
| OQ-8 | Encryption wrapper (DTLS over TFTP)? | Research needed |
| OQ-9 | Persistent transfer history (SQLite/redb)? | Deferred (v0.2) |
| OQ-10 | Configurable ephemeral port range? | Deferred (v0.2) |
| OQ-11 | io_uring (Linux) / RIO (Windows) для I/O batching? | Research needed |

---

## 16. Glossary

| Термин | Определение |
|---|---|
| **TFTP** | Trivial File Transfer Protocol — простой протокол передачи файлов поверх UDP |
| **RRQ** | Read Request — запрос на чтение файла |
| **WRQ** | Write Request — запрос на запись файла |
| **OACK** | Option Acknowledgment — подтверждение опций |
| **TID** | Transfer ID — UDP порт, идентифицирующий сторону в сессии |
| **blksize** | Block Size — размер блока данных в байтах |
| **windowsize** | Window Size — количество блоков в sliding window |
| **tsize** | Transfer Size — размер файла в байтах |
| **ACL** | Access Control List — список правил контроля доступа |
| **CIDR** | Classless Inter-Domain Routing — нотация для IP-сетей (напр. 192.168.1.0/24) |
| **PXE** | Preboot Execution Environment — загрузка ОС по сети |
| **dual-stack** | Одновременная поддержка IPv4 и IPv6 на одном сокете |
| **sliding window** | Протокольный механизм отправки нескольких пакетов без ожидания ACK |
| **Sorcerer's Apprentice** | Баг TFTP: дублированный ACK вызывает бесконтрольное удвоение DATA |
| **egui** | Immediate mode GUI библиотека для Rust |
| **ratatui** | TUI (Terminal UI) библиотека для Rust |
| **tokio** | Асинхронный runtime для Rust |
| **CancellationToken** | Механизм кооперативной отмены async tasks в tokio |
| **MSRV** | Minimum Supported Rust Version — минимальная версия компилятора |

---

*— End of PRD v2.0 —*
