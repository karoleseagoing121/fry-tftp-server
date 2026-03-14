use arc_swap::ArcSwap;
use std::collections::HashMap;
use std::net::{IpAddr, SocketAddr};
use std::sync::atomic::{AtomicU64, AtomicU8, Ordering};
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::core::buffer_pool::BufferPool;
use crate::core::config::{CliOverrides, Config};

/// Server running state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum ServerState {
    Starting = 0,
    Running = 1,
    Stopping = 2,
    Stopped = 3,
    Error = 4,
}

impl ServerState {
    pub fn from_u8(v: u8) -> Self {
        match v {
            0 => Self::Starting,
            1 => Self::Running,
            2 => Self::Stopping,
            3 => Self::Stopped,
            4 => Self::Error,
            _ => Self::Error,
        }
    }
}

/// Transfer direction
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction {
    Read,
    Write,
}

/// Session status
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SessionStatus {
    Negotiating,
    Transferring,
    Completed,
    Failed,
    Cancelled,
}

/// Information about an active session (read-only snapshot for UI)
#[derive(Debug, Clone)]
pub struct SessionInfo {
    pub id: Uuid,
    pub client_addr: SocketAddr,
    pub filename: String,
    pub direction: Direction,
    pub status: SessionStatus,
    pub blksize: u16,
    pub windowsize: u16,
    pub tsize: Option<u64>,
    pub bytes_transferred: u64,
    pub started_at: Instant,
    pub last_activity: Instant,
    pub retransmits: u32,
}

/// Transfer history record
#[derive(Debug, Clone)]
pub struct TransferRecord {
    pub id: Uuid,
    pub client_addr: SocketAddr,
    pub filename: String,
    pub direction: Direction,
    pub bytes_transferred: u64,
    pub duration_ms: u64,
    pub speed_mbps: f64,
    pub status: SessionStatus,
    pub retransmits: u32,
    pub timestamp: Instant,
}

/// Rate limiter entry per IP
#[derive(Debug, Clone)]
pub struct RateLimiterEntry {
    pub count: u32,
    pub window_start: Instant,
}

/// Bandwidth sample snapshot
#[derive(Debug, Clone, Copy, Default)]
pub struct BandwidthSample {
    pub tx_bps: f64,
    pub rx_bps: f64,
}

/// Central application state shared across all modes (GUI/TUI/Headless)
pub struct AppState {
    // Global counters (lock-free)
    pub total_bytes_tx: AtomicU64,
    pub total_bytes_rx: AtomicU64,
    pub total_sessions: AtomicU64,
    pub total_errors: AtomicU64,

    // Active sessions
    pub active_sessions: RwLock<HashMap<Uuid, SessionInfo>>,

    // Transfer history (last N)
    pub transfer_history: RwLock<Vec<TransferRecord>>,

    // Config (hot-reloadable)
    pub config: ArcSwap<Config>,

    // Server state
    pub server_state: AtomicU8,

    // Shutdown coordination (swappable for restart)
    pub shutdown_token: ArcSwap<CancellationToken>,

    // Per-IP rate limiter state
    pub rate_limiter: RwLock<HashMap<IpAddr, RateLimiterEntry>>,

    // Bandwidth sampling (shared across all modes)
    pub bandwidth: arc_swap::ArcSwap<BandwidthSample>,
    bandwidth_prev_tx: AtomicU64,
    bandwidth_prev_rx: AtomicU64,

    // Pre-allocated buffer pool for session packet buffers
    pub buffer_pool: BufferPool,

    // CLI overrides preserved across config reloads
    pub cli_overrides: CliOverrides,
}

impl AppState {
    pub fn new(config: Config, cli_overrides: CliOverrides) -> Arc<Self> {
        let buffer_pool = BufferPool::new(
            config.session.max_sessions,
            config.protocol.max_blksize as usize + 4,
        );
        Arc::new(Self {
            total_bytes_tx: AtomicU64::new(0),
            total_bytes_rx: AtomicU64::new(0),
            total_sessions: AtomicU64::new(0),
            total_errors: AtomicU64::new(0),
            active_sessions: RwLock::new(HashMap::new()),
            transfer_history: RwLock::new(Vec::new()),
            config: ArcSwap::new(Arc::new(config)),
            server_state: AtomicU8::new(ServerState::Starting as u8),
            shutdown_token: ArcSwap::new(Arc::new(CancellationToken::new())),
            rate_limiter: RwLock::new(HashMap::new()),
            bandwidth: arc_swap::ArcSwap::new(Arc::new(BandwidthSample::default())),
            bandwidth_prev_tx: AtomicU64::new(0),
            bandwidth_prev_rx: AtomicU64::new(0),
            buffer_pool,
            cli_overrides,
        })
    }

    /// Sample current bandwidth (call once per second from a periodic task)
    pub fn sample_bandwidth(&self) {
        let tx = self.total_bytes_tx.load(Ordering::Relaxed);
        let rx = self.total_bytes_rx.load(Ordering::Relaxed);
        let prev_tx = self.bandwidth_prev_tx.swap(tx, Ordering::Relaxed);
        let prev_rx = self.bandwidth_prev_rx.swap(rx, Ordering::Relaxed);
        let sample = BandwidthSample {
            tx_bps: tx.saturating_sub(prev_tx) as f64,
            rx_bps: rx.saturating_sub(prev_rx) as f64,
        };
        self.bandwidth.store(Arc::new(sample));
    }

    /// Get latest bandwidth sample
    pub fn get_bandwidth(&self) -> Arc<BandwidthSample> {
        self.bandwidth.load_full()
    }

    pub fn get_server_state(&self) -> ServerState {
        ServerState::from_u8(self.server_state.load(Ordering::Relaxed))
    }

    pub fn set_server_state(&self, state: ServerState) {
        self.server_state.store(state as u8, Ordering::Relaxed);
    }

    pub fn config(&self) -> Arc<Config> {
        self.config.load_full()
    }

    /// Reload config from disk, preserving CLI overrides.
    pub fn reload_config(&self) -> anyhow::Result<()> {
        let ovr = &self.cli_overrides;
        let mut new_config = Config::load(ovr.config_path.as_deref())?;
        new_config.apply_overrides(
            ovr.port,
            ovr.bind.clone(),
            ovr.root.clone(),
            ovr.allow_write,
            ovr.max_sessions,
            ovr.blksize,
            ovr.windowsize,
            ovr.ip_version.clone(),
            ovr.log_level.clone(),
        );
        // Update buffer pool if max_blksize changed
        let new_buf_size = new_config.protocol.max_blksize as usize + 4;
        if self.buffer_pool.buf_size() != new_buf_size {
            self.buffer_pool.update_buf_size(new_buf_size);
        }

        self.config.store(Arc::new(new_config));
        Ok(())
    }

    /// Get a clone of the current shutdown token
    pub fn get_shutdown_token(&self) -> Arc<CancellationToken> {
        self.shutdown_token.load_full()
    }

    /// Cancel the current shutdown token (stop the server)
    pub fn cancel_shutdown(&self) {
        self.shutdown_token.load().cancel();
    }

    /// Reset state for server restart: new shutdown token, clear stats, reload config.
    pub async fn reset_for_restart(&self, new_config: Config) {
        // Reset counters
        self.total_bytes_tx.store(0, Ordering::Relaxed);
        self.total_bytes_rx.store(0, Ordering::Relaxed);
        self.total_sessions.store(0, Ordering::Relaxed);
        self.total_errors.store(0, Ordering::Relaxed);
        self.bandwidth_prev_tx.store(0, Ordering::Relaxed);
        self.bandwidth_prev_rx.store(0, Ordering::Relaxed);
        self.bandwidth.store(Arc::new(BandwidthSample::default()));

        // Clear sessions and history
        self.active_sessions.write().await.clear();
        self.transfer_history.write().await.clear();
        self.rate_limiter.write().await.clear();

        // Store new config
        self.config.store(Arc::new(new_config));

        // Replace shutdown token with a fresh one
        self.shutdown_token
            .store(Arc::new(CancellationToken::new()));

        // Set state to Starting
        self.set_server_state(ServerState::Starting);
    }

    /// Check rate limit for an IP. Returns true if allowed.
    pub async fn check_rate_limit(&self, ip: IpAddr) -> bool {
        let config = self.config();
        let window = std::time::Duration::from_secs(config.security.rate_limit_window_seconds);
        let limit = config.security.per_ip_rate_limit;
        let now = Instant::now();

        let mut rate_map = self.rate_limiter.write().await;
        let entry = rate_map.entry(ip).or_insert(RateLimiterEntry {
            count: 0,
            window_start: now,
        });

        if now.duration_since(entry.window_start) >= window {
            // Reset window
            entry.count = 1;
            entry.window_start = now;
            true
        } else if entry.count < limit {
            entry.count += 1;
            true
        } else {
            false
        }
    }

    /// Remove rate limiter entries that have been idle for longer than 2x the window.
    pub async fn cleanup_stale_rate_limits(&self) {
        let config = self.config();
        let window = std::time::Duration::from_secs(config.security.rate_limit_window_seconds);
        let expiry = window.saturating_mul(2);
        let now = Instant::now();

        let mut rate_map = self.rate_limiter.write().await;
        rate_map.retain(|_ip, entry| now.duration_since(entry.window_start) < expiry);
    }

    /// Count active sessions for an IP
    pub async fn count_sessions_by_ip(&self, ip: IpAddr) -> usize {
        let sessions = self.active_sessions.read().await;
        sessions
            .values()
            .filter(|s| s.client_addr.ip() == ip)
            .count()
    }

    /// Count total active sessions
    pub async fn count_sessions(&self) -> usize {
        self.active_sessions.read().await.len()
    }

    /// Register a new active session
    pub async fn register_session(&self, info: SessionInfo) {
        self.total_sessions.fetch_add(1, Ordering::Relaxed);
        self.active_sessions.write().await.insert(info.id, info);
    }

    /// Update session info
    pub async fn update_session(&self, id: Uuid, bytes: u64, status: SessionStatus) {
        let mut sessions = self.active_sessions.write().await;
        if let Some(session) = sessions.get_mut(&id) {
            session.bytes_transferred = bytes;
            session.status = status;
            session.last_activity = Instant::now();
        }
    }

    /// Clean up sessions that have been inactive longer than timeout_secs.
    pub async fn cleanup_stale_sessions(&self, timeout_secs: u64) -> usize {
        let now = Instant::now();
        let timeout = std::time::Duration::from_secs(timeout_secs);
        let mut stale_ids = Vec::new();

        {
            let sessions = self.active_sessions.read().await;
            for (id, info) in sessions.iter() {
                if now.duration_since(info.last_activity) > timeout {
                    stale_ids.push(*id);
                }
            }
        }

        let count = stale_ids.len();
        for id in stale_ids {
            tracing::warn!(session_id=%id, "cleaning up stale session (timeout)");
            self.complete_session(id, SessionStatus::Failed).await;
            self.total_errors
                .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        }
        count
    }

    /// Complete a session and move to history
    pub async fn complete_session(&self, id: Uuid, status: SessionStatus) {
        let mut sessions = self.active_sessions.write().await;
        if let Some(session) = sessions.remove(&id) {
            let duration = session.started_at.elapsed();
            let duration_ms = duration.as_millis() as u64;
            let speed_mbps = if duration_ms > 0 {
                (session.bytes_transferred as f64 * 8.0) / (duration_ms as f64 * 1000.0)
            } else {
                0.0
            };

            let record = TransferRecord {
                id: session.id,
                client_addr: session.client_addr,
                filename: session.filename,
                direction: session.direction,
                bytes_transferred: session.bytes_transferred,
                duration_ms,
                speed_mbps,
                status,
                retransmits: session.retransmits,
                timestamp: Instant::now(),
            };

            // Write to transfer log file (JSON Lines)
            let config = self.config();
            if !config.server.transfer_log.is_empty() {
                let line = serde_json::json!({
                    "ts": chrono_now(),
                    "client": record.client_addr.to_string(),
                    "file": &record.filename,
                    "dir": match record.direction { Direction::Read => "DL", Direction::Write => "UL" },
                    "bytes": record.bytes_transferred,
                    "ms": record.duration_ms,
                    "mbps": format!("{:.1}", record.speed_mbps),
                    "status": match record.status {
                        SessionStatus::Completed => "OK",
                        SessionStatus::Failed => "FAIL",
                        SessionStatus::Cancelled => "CANCEL",
                        _ => "?",
                    },
                    "retx": record.retransmits,
                });
                if let Ok(json) = serde_json::to_string(&line) {
                    use std::io::Write;
                    let path = std::path::Path::new(&config.server.transfer_log);
                    if let Some(parent) = path.parent() {
                        let _ = std::fs::create_dir_all(parent);
                    }
                    if let Ok(mut f) = std::fs::OpenOptions::new()
                        .create(true)
                        .append(true)
                        .open(path)
                    {
                        let _ = writeln!(f, "{}", json);
                    }
                }
            }

            drop(sessions);
            let mut history = self.transfer_history.write().await;
            history.push(record);
            // Keep last 1000 records
            if history.len() > 1000 {
                let excess = history.len() - 1000;
                history.drain(0..excess);
            }
        }
    }

    /// Load transfer history from jsonl file at startup
    pub fn load_transfer_history(&self) {
        let config = self.config();
        let path = &config.server.transfer_log;
        if path.is_empty() {
            return;
        }
        let content = match std::fs::read_to_string(path) {
            Ok(c) => c,
            Err(_) => return,
        };
        let mut records = Vec::new();
        for line in content.lines().rev().take(1000) {
            if let Ok(val) = serde_json::from_str::<serde_json::Value>(line) {
                let record = TransferRecord {
                    id: Uuid::new_v4(),
                    client_addr: val["client"]
                        .as_str()
                        .unwrap_or("?")
                        .parse()
                        .unwrap_or_else(|_| "0.0.0.0:0".parse().unwrap()),
                    filename: val["file"].as_str().unwrap_or("?").to_string(),
                    direction: if val["dir"].as_str() == Some("UL") {
                        Direction::Write
                    } else {
                        Direction::Read
                    },
                    bytes_transferred: val["bytes"].as_u64().unwrap_or(0),
                    duration_ms: val["ms"].as_u64().unwrap_or(0),
                    speed_mbps: val["mbps"]
                        .as_str()
                        .and_then(|s| s.parse().ok())
                        .unwrap_or(0.0),
                    status: match val["status"].as_str() {
                        Some("OK") => SessionStatus::Completed,
                        Some("FAIL") => SessionStatus::Failed,
                        Some("CANCEL") => SessionStatus::Cancelled,
                        _ => SessionStatus::Failed,
                    },
                    retransmits: val["retx"].as_u64().unwrap_or(0) as u32,
                    timestamp: Instant::now(),
                };
                records.push(record);
            }
        }
        records.reverse();
        if let Ok(mut history) = self.transfer_history.try_write() {
            *history = records;
        }
    }
}

fn chrono_now() -> String {
    let dur = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    let secs = dur.as_secs();
    let h = (secs % 86400) / 3600;
    let m = (secs % 3600) / 60;
    let s = secs % 60;
    format!(
        "{}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        1970 + secs / 31557600,            // approximate year
        ((secs % 31557600) / 2629800) + 1, // approximate month
        ((secs % 2629800) / 86400) + 1,    // approximate day
        h,
        m,
        s
    )
}
