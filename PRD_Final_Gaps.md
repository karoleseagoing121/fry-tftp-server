# PRD — Исправление финальных находок аудита

**Версия:** 1.0
**Дата:** 2026-03-13
**Контекст:** Аудит PRD_TFTP_Server.md v2.0 vs реализация выявил 10 оставшихся пробелов (без учёта §13 Build & Release Pipeline).
**Общий прогресс до начала работ:** 87% (114/131 требований)

---

## 1. Сводка находок

| # | Секция PRD | Находка | Приоритет | Трудоёмкость |
|---|---|---|---|---|
| 1 | §3.3.3 | Memory-mapped I/O для больших файлов | P2 | 3h |
| 2 | §3.3.3 | Pre-allocated Buffer Pool | P2 | 2h |
| 3 | §3.3.3 | Read-ahead buffer (фоновый reader для sliding window) | P2 | 3h |
| 4 | §6.2.3 | IPC: Unix domain socket + Windows Named Pipe | P2 | 5h |
| 5 | §7.1 | Директория tests/fixtures/ с тестовыми файлами | P2 | 0.5h |
| 6 | §7.1 | Makefile с основными командами | P2 | 1h |
| 7 | §12.2 | Integration test: config hot-reload | P2 | 2h |
| 8 | §12.2 | Integration test: timeout / retransmit simulation | P2 | 2h |
| 9 | §12.2 | Integration test: block number rollover (>32MB) | P2 | 1.5h |
| 10 | §12.5 | Rust test client модуль (tests/test_client/) | P2 | 3h |

**Итого:** ~23 часа

---

## 2. Фазы реализации

### Фаза 1 — I/O оптимизации (§3.3.3) — ~8h

#### 2.1.1 Memory-Mapped I/O (mmap)

**Ссылка на PRD:** §3.3.3 «Memory-mapped I/O (основная стратегия)»

**Текущее состояние:** Файлы читаются через `tokio::fs::read()` целиком в память. Для файлов >64KB это неоптимально — лишний syscall + полное копирование в userspace.

**Требования:**

1. Добавить зависимость `memmap2 = "0.9"` в `Cargo.toml`
2. В `src/core/fs/mod.rs` создать функцию:
   ```rust
   pub fn open_file_mapped(path: &Path) -> io::Result<FileHandle>
   ```
3. `FileHandle` — enum:
   - `Mapped(memmap2::Mmap)` — для файлов ≥ 64KB
   - `Buffered(Vec<u8>)` — для файлов < 64KB (mmap overhead не оправдан)
   - `Empty` — для zero-byte файлов
4. Порог переключения: константа `MMAP_THRESHOLD = 65536`
5. `FileHandle` реализует метод `fn slice(&self, offset: u64, len: usize) -> &[u8]` для zero-copy доступа к блокам данных
6. В `src/core/session/mod.rs` заменить `tokio::fs::read()` на `open_file_mapped()` в `spawn_read_session()`
7. Mmap создавать с `MmapOptions::new().map(&file)?` (read-only mapping)
8. На Windows: `memmap2` использует `CreateFileMapping` + `MapViewOfFile` — кросс-платформенно

**Критерии приёмки:**
- [ ] RRQ файлов ≥ 64KB использует mmap
- [ ] RRQ файлов < 64KB использует обычный read
- [ ] Zero-byte файлы работают корректно
- [ ] Все существующие тесты (64 Rust + 29 Python) проходят
- [ ] Benchmark `throughput_bench` показывает ≥ прежний результат

---

#### 2.1.2 Pre-allocated Buffer Pool

**Ссылка на PRD:** §3.3.3 «Pre-allocated Buffer Pool»

**Текущее состояние:** Каждая сессия аллоцирует свой буфер для формирования DATA-пакетов. При большом количестве параллельных сессий это создаёт нагрузку на аллокатор.

**Требования:**

1. Создать `src/core/buffer_pool.rs`:
   ```rust
   pub struct BufferPool {
       pool: crossbeam_queue::ArrayQueue<BytesMut>,
       buf_size: usize,
   }

   impl BufferPool {
       pub fn new(capacity: usize, buf_size: usize) -> Self;
       pub fn acquire(&self) -> BytesMut;   // берёт из пула или аллоцирует новый
       pub fn release(&self, buf: BytesMut); // возвращает в пул (если не переполнен)
   }
   ```
2. `buf_size` = `max_blksize + 4` (TFTP header)
3. `capacity` = `config.session.max_sessions`
4. Добавить `BufferPool` в `AppState` (инициализировать при запуске сервера)
5. В `spawn_read_session()` и `spawn_write_session()` — `state.buffer_pool.acquire()` при старте, `release()` при завершении
6. Зависимость: `crossbeam-queue = "0.3"` (lock-free queue) или использовать `tokio::sync::Semaphore` + `Vec<Mutex<Option<BytesMut>>>`
7. Альтернатива без внешней зависимости: `std::sync::Mutex<Vec<BytesMut>>` — достаточно для lock contention при ~100 сессиях

**Критерии приёмки:**
- [ ] Буферы переиспользуются между сессиями (проверить через лог или метрику `pool_hits`/`pool_misses`)
- [ ] Нет утечек буферов (проверить после серии тестов: pool size ≤ capacity)
- [ ] Все тесты проходят

---

#### 2.1.3 Read-Ahead Buffer

**Ссылка на PRD:** §3.3.3 «Read-ahead buffer (для sliding window)»

**Текущее состояние:** При sliding window (windowsize > 1) блоки читаются синхронно перед отправкой. Для NVMe/SSD это незаметно, но для HDD/сетевых FS может быть bottleneck.

**Требования:**

1. В `src/core/session/mod.rs` добавить структуру:
   ```rust
   struct ReadAheadBuffer {
       queue: VecDeque<Bytes>,      // готовые блоки
       capacity: usize,              // = windowsize * 2
       notify: tokio::sync::Notify,  // оповещение reader
       done: AtomicBool,             // EOF reached
   }
   ```
2. При RRQ с `windowsize > 1`: запускать фоновую tokio task, которая:
   - Читает блоки из `FileHandle` ahead of current position
   - Складывает в `ReadAheadBuffer.queue`
   - При `queue.len() >= capacity`: `notify.notified().await` (ждёт потребителя)
3. Основная task берёт блоки из `queue` вместо прямого чтения
4. При `windowsize == 1` (stop-and-wait): read-ahead НЕ используется (overhead не оправдан)
5. При завершении/отмене сессии: фоновая task отменяется через `CancellationToken`

**Критерии приёмки:**
- [ ] При windowsize > 1 используется read-ahead
- [ ] При windowsize == 1 read-ahead не запускается
- [ ] Все тесты проходят (особенно sliding window тесты)
- [ ] Нет data race / deadlock (проверить через `cargo test` + MIRI если возможно)

---

### Фаза 2 — IPC Management (§6.2.3) — ~5h

#### 2.2.1 Универсальный IPC

**Ссылка на PRD:** §6.2.3 «Универсальный IPC (все платформы)»

**Текущее состояние:** Управление headless-сервером возможно только через сигналы (SIGHUP, SIGTERM) и Windows Service control. Нет способа отправить команду `reload` или `status` из другого процесса.

**Требования:**

1. Создать `src/core/ipc.rs`:
   ```rust
   pub async fn spawn_ipc_listener(state: Arc<AppState>) -> Result<()>
   ```

2. **Unix (`#[cfg(unix)]`):**
   - Путь: `/run/tftp-server.sock` (или `$XDG_RUNTIME_DIR/tftp-server.sock`)
   - Использовать `tokio::net::UnixListener`
   - При shutdown: удалять socket файл

3. **Windows (`#[cfg(windows)]`):**
   - Путь: `\\.\pipe\tftp-server-control`
   - Использовать `tokio::net::windows::named_pipe::ServerOptions`
   - Pipe security: только текущий пользователь + Administrators

4. **Протокол (текстовый, line-based):**
   ```
   Команды (клиент → сервер):
     reload    → перечитать конфиг (эквивалент SIGHUP)
     stop      → graceful shutdown
     status    → вернуть JSON со статусом

   Ответы (сервер → клиент):
     {"ok": true, "message": "config reloaded"}
     {"ok": true, "status": "running", "sessions": 5, "uptime_secs": 3600, ...}
     {"ok": false, "error": "config validation failed: ..."}
   ```

5. **Статус JSON:**
   ```json
   {
     "status": "running",
     "uptime_secs": 3600,
     "active_sessions": 5,
     "total_sessions": 1234,
     "total_bytes_tx": 52428800,
     "total_bytes_rx": 10485760,
     "total_errors": 2,
     "config_path": "/etc/tftp-server/config.toml",
     "bind_address": "[::]:69"
   }
   ```

6. В `src/main.rs` при headless-режиме: вызвать `ipc::spawn_ipc_listener(state.clone())` после запуска сервера

7. Команда `reload` через IPC должна вызывать тот же путь, что и SIGHUP: перечитать конфиг → валидация → ArcSwap

**Критерии приёмки:**
- [ ] На Unix: `echo "status" | socat - UNIX-CONNECT:/run/tftp-server.sock` возвращает JSON
- [ ] На Windows: `echo status > \\.\pipe\tftp-server-control` возвращает JSON
- [ ] `reload` через IPC перезагружает конфиг
- [ ] `stop` через IPC инициирует graceful shutdown
- [ ] IPC listener корректно завершается при shutdown сервера
- [ ] Socket/pipe удаляется при завершении

---

### Фаза 3 — Структура проекта (§7.1) — ~1.5h

#### 2.3.1 tests/fixtures/

**Ссылка на PRD:** §7.1 структура — `tests/fixtures/ # тестовые файлы`

**Текущее состояние:** Тестовые файлы создаются ad-hoc в `test_root/` или через `tempdir()` в Rust-тестах. Нет единой директории с fixture-файлами.

**Требования:**

1. Создать `tests/fixtures/` со следующими файлами:
   ```
   tests/fixtures/
   ├── small.txt          # 180 байт, текстовый (для базовых RRQ тестов)
   ├── oneblock.bin       # ровно 512 байт (edge case: один полный блок)
   ├── medium.bin          # 10 KB, бинарный
   ├── large.bin           # 1 MB, бинарный (для throughput тестов)
   ├── netascii.txt       # текст с mixed line endings для netascii тестов
   ├── switch.cfg         # конфиг-подобный файл (реалистичный сценарий)
   ├── zero.bin           # 0 байт (zero-byte edge case)
   └── README.md          # описание каждого файла
   ```
2. Бинарные файлы: генерировать через скрипт `tests/generate_fixtures.py` (чтобы не хранить blob в git)
3. Добавить `.gitignore` в `tests/fixtures/` для `*.bin` (генерируются скриптом)
4. В Rust integration тестах: использовать `env!("CARGO_MANIFEST_DIR")` + `/tests/fixtures/` для пути к fixtures

**Критерии приёмки:**
- [ ] Директория `tests/fixtures/` существует с перечисленными файлами
- [ ] Скрипт `tests/generate_fixtures.py` генерирует бинарные fixtures
- [ ] README.md описывает формат и назначение каждого файла

---

#### 2.3.2 Makefile

**Ссылка на PRD:** §7.1 структура — `Makefile`

**Текущее состояние:** Нет Makefile. Для сборки/тестирования нужно помнить отдельные `cargo` команды.

**Требования:**

1. Создать `Makefile` в корне проекта с целями:
   ```makefile
   .PHONY: build build-headless test test-headless lint fmt check bench fuzz clean fixtures run run-headless

   build:                 # cargo build --release
   build-headless:        # cargo build --release --no-default-features
   test:                  # cargo test --workspace
   test-headless:         # cargo test --workspace --no-default-features
   lint:                  # cargo clippy -- -D warnings
   fmt:                   # cargo fmt --check
   check:                 # fmt + lint + test (полная проверка)
   bench:                 # cargo bench --workspace
   fuzz:                  # cargo fuzz run packet_parser -- -max_total_time=60
   clean:                 # cargo clean
   fixtures:              # python tests/generate_fixtures.py
   run:                   # cargo run --release
   run-headless:          # cargo run --release -- --headless
   integration:           # запуск Python integration тестов
   docker:                # docker build -t tftp-server -f deploy/docker/Dockerfile .
   ```
2. Цель `check` должна выполнять: `fmt` → `lint` → `test` (последовательно)
3. Цель `integration` должна: собрать release → запустить сервер → запустить Python тесты → остановить сервер

**Критерии приёмки:**
- [ ] `make check` проходит на чистом клоне
- [ ] `make bench` запускает criterion benchmarks
- [ ] `make integration` прогоняет полную Python test suite

---

### Фаза 4 — Integration Tests (§12.2) — ~5.5h

#### 2.4.1 Config Hot-Reload Test

**Ссылка на PRD:** §12.2 «Config reload — Изменение конфига на лету, проверка новых параметров»

**Текущее состояние:** Hot-reload реализован (notify + ArcSwap), но нет integration теста, подтверждающего, что изменение файла конфига применяется к новым сессиям.

**Требования:**

Добавить тест в `tests/integration/basic_rrq.rs`:

```rust
#[tokio::test]
async fn test_config_hot_reload()
```

1. Создать tempdir с конфигом (`max_blksize = 1024`)
2. Запустить сервер с этим конфигом
3. Отправить RRQ с `blksize=2048` → сервер должен OACK с `blksize=1024` (clamp)
4. Изменить файл конфига: `max_blksize = 4096`
5. Подождать ≤ 2 сек (notify debounce)
6. Отправить RRQ с `blksize=2048` → сервер должен OACK с `blksize=2048` (теперь разрешено)
7. Assert: два разных negotiated blksize подтверждают hot-reload

**Критерии приёмки:**
- [ ] Тест проходит стабильно (≤ 2 сек на reload detection)
- [ ] Тест не flaky (использовать retry loop для ожидания reload)

---

#### 2.4.2 Timeout / Retransmit Simulation Test

**Ссылка на PRD:** §12.2 «Timeout / retransmit — Симуляция packet loss, проверка retransmit»

**Текущее состояние:** Retransmission реализована в session loop, но нет теста, подтверждающего, что сервер ретранслирует DATA после timeout.

**Требования:**

Добавить тест в `tests/integration/basic_rrq.rs`:

```rust
#[tokio::test]
async fn test_retransmit_on_timeout()
```

1. Запустить mini_server с файлом (несколько блоков)
2. Отправить RRQ с `timeout=1` (1 секунда)
3. Получить DATA(1) — НЕ отправлять ACK
4. Подождать >1 сек
5. Получить повторный DATA(1) — подтвердить ретрансмиссию
6. Теперь отправить ACK(1) → получить DATA(2) → нормальное завершение
7. Assert: получено 2 копии DATA(1)

**Критерии приёмки:**
- [ ] Тест подтверждает ретрансмиссию после timeout
- [ ] Тест подтверждает нормальное продолжение после запоздалого ACK
- [ ] Тест завершается за < 10 сек

---

#### 2.4.3 Block Number Rollover Test

**Ссылка на PRD:** §12.2 «Block rollover — Файл > 32MB при blksize=512, проверка rollover»

**Текущее состояние:** Rollover реализован (`u16` wrapping в session), но нет теста для файла, требующего >65535 блоков.

**Требования:**

Добавить тест в `tests/integration/basic_rrq.rs`:

```rust
#[tokio::test]
async fn test_block_number_rollover()
```

1. Создать файл размером `65536 * 512 + 512 = 33,554,944 байт` (~32 MB + 1 блок) в tempdir
2. Заполнить детерминистичным паттерном (XOR pattern для верификации)
3. Запустить mini_server
4. Отправить RRQ с `blksize=512` (default)
5. Получить все 65537 DATA-блоков
6. Проверить: блок 65535 имеет `block# = 65535`, блок 65536 имеет `block# = 0` (rollover), блок 65537 имеет `block# = 1`
7. Собрать payload, сравнить MD5 с оригиналом

**Примечание:** Тест тяжёлый (~32 MB), пометить `#[ignore]` для обычного `cargo test`, запускать через `cargo test -- --ignored` или `make test-heavy`.

**Критерии приёмки:**
- [ ] Тест подтверждает корректный rollover block# 65535 → 0
- [ ] MD5 payload совпадает с оригиналом
- [ ] Тест помечен `#[ignore]` чтобы не замедлять обычный CI

---

### Фаза 5 — Rust Test Client (§12.5) — ~3h

#### 2.5.1 Модуль test_client

**Ссылка на PRD:** §12.5 «Минимальный TFTP-клиент на Rust в tests/test_client/»

**Текущее состояние:** Integration тесты используют raw UDP socket + ручную сборку/парсинг пакетов. Код дублируется между тестами. Нет переиспользуемого test client.

**Требования:**

1. Создать `tests/test_client/mod.rs` (или `tests/common/tftp_client.rs`):
   ```rust
   pub struct TftpTestClient {
       socket: UdpSocket,
       server_addr: SocketAddr,
       blksize: u16,
       windowsize: u16,
       timeout: Duration,
   }

   impl TftpTestClient {
       pub async fn new(server_addr: SocketAddr) -> Self;

       // High-level operations
       pub async fn get(&self, filename: &str) -> Result<Vec<u8>>;
       pub async fn get_with_options(&self, filename: &str, opts: &TftpOptions) -> Result<Vec<u8>>;
       pub async fn put(&self, filename: &str, data: &[u8]) -> Result<()>;
       pub async fn put_with_options(&self, filename: &str, data: &[u8], opts: &TftpOptions) -> Result<()>;

       // Low-level operations (для специфичных тестов)
       pub async fn send_rrq(&self, filename: &str, options: &[TftpOption]) -> Result<()>;
       pub async fn send_wrq(&self, filename: &str, options: &[TftpOption]) -> Result<()>;
       pub async fn send_ack(&self, block: u16) -> Result<()>;
       pub async fn send_data(&self, block: u16, data: &[u8]) -> Result<()>;
       pub async fn recv_packet(&self, timeout: Duration) -> Result<Packet>;

       // Simulation helpers (для тестирования edge cases)
       pub async fn send_duplicate_ack(&self, block: u16, count: usize) -> Result<()>;
       pub async fn recv_packet_drop(&self, drop_rate: f64) -> Result<Option<Packet>>;
   }

   pub struct TftpOptions {
       pub blksize: Option<u16>,
       pub windowsize: Option<u16>,
       pub timeout: Option<u8>,
       pub tsize: Option<u64>,
   }
   ```

2. `get()` — полный flow: RRQ → (OACK → ACK(0))? → DATA/ACK loop → return payload
3. `put()` — полный flow: WRQ → (OACK)? → DATA/ACK loop → complete
4. Реиспользовать `parse_packet()` и `Packet::serialize()` из `src/core/protocol/packet.rs`
5. `recv_packet()` с configurable timeout (default 5 сек)

3. Рефакторинг существующих тестов в `basic_rrq.rs`:
   - Заменить raw socket + ручной парсинг на `TftpTestClient`
   - Сохранить все существующие test scenarios
   - Добавить 3 новых теста (из Фазы 4) используя test client

**Критерии приёмки:**
- [ ] `TftpTestClient` покрывает RRQ, WRQ, OACK flow (все 4 варианта)
- [ ] Все существующие тесты переписаны на test client (без потери покрытия)
- [ ] Low-level API позволяет тестировать edge cases (duplicate ACK, dropped packets)
- [ ] `cargo test` — все тесты проходят

---

## 3. Порядок выполнения

```
Фаза 5 (test_client)     ← начать с этого: инфраструктура для остальных тестов
  ↓
Фаза 4 (integration tests) ← используя test_client
  ↓
Фаза 3 (fixtures + Makefile) ← структура проекта
  ↓
Фаза 1 (I/O оптимизации)  ← самая объёмная, но изолированная от остальных
  ↓
Фаза 2 (IPC)              ← последняя, наименее критичная
```

**Рекомендация:** Фазы 3-5 можно делать параллельно, так как они затрагивают разные файлы.

---

## 4. Верификация

После завершения всех фаз:

1. `cargo build --release` — clean build, 0 warnings
2. `cargo clippy -- -D warnings` — 0 warnings
3. `cargo test --workspace` — все тесты pass
4. `cargo test --workspace -- --ignored` — heavy тесты pass (rollover)
5. `cargo bench` — benchmarks compile & run
6. `python tests/tftp_integration.py` — 29/29 ✅
7. `make check` — полная проверка через Makefile

---

## 5. Ожидаемый результат после реализации

| Секция PRD | До | После |
|---|---|---|
| §3.3 File System | 69% (5/8) | **100%** (8/8) |
| §6 Headless | 91% (10/11) | **100%** (11/11) |
| §7 Архитектура | 50% (3/6) | **100%** (6/6) |
| §12 Тестирование | 67% (8/12) | **100%** (12/12) |
| **ИТОГО (без §13)** | **90%** (108/117) | **100%** (117/117) |

*— End of PRD —*
