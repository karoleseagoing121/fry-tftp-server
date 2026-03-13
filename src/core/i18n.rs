//! Internationalization (i18n) module.
//!
//! Provides a simple key-value translation system with embedded language packs.
//! Supports runtime language switching via config.

use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Lang {
    En,
    Ru,
}

impl Lang {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "ru" | "russian" => Lang::Ru,
            _ => Lang::En,
        }
    }

    pub fn code(&self) -> &'static str {
        match self {
            Lang::En => "en",
            Lang::Ru => "ru",
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            Lang::En => "English",
            Lang::Ru => "Русский",
        }
    }

    pub const ALL: &'static [Lang] = &[Lang::En, Lang::Ru];
}

pub struct I18n {
    lang: Lang,
    strings: HashMap<&'static str, &'static str>,
}

impl I18n {
    pub fn new(lang: Lang) -> Self {
        let strings = match lang {
            Lang::En => en(),
            Lang::Ru => ru(),
        };
        Self { lang, strings }
    }

    pub fn lang(&self) -> Lang {
        self.lang
    }

    pub fn set_lang(&mut self, lang: Lang) {
        self.lang = lang;
        self.strings = match lang {
            Lang::En => en(),
            Lang::Ru => ru(),
        };
    }

    /// Get translated string. Falls back to key if not found.
    pub fn t<'a>(&'a self, key: &'a str) -> &'a str {
        self.strings.get(key).copied().unwrap_or(key)
    }
}

fn en() -> HashMap<&'static str, &'static str> {
    let mut m = HashMap::new();

    // Header
    m.insert("status", "Status:");
    m.insert("listening", "Listening:");
    m.insert("running", "Running");
    m.insert("starting", "Starting...");
    m.insert("stopping", "Stopping...");
    m.insert("stopped", "Stopped");
    m.insert("error", "Error");
    m.insert("start_server", "Start Server");
    m.insert("stop_server", "Stop Server");
    m.insert("light_mode", "Light Mode");
    m.insert("dark_mode", "Dark Mode");
    m.insert("about", "About");
    m.insert("close", "Close");

    // Tabs
    m.insert("tab_dashboard", "Dashboard");
    m.insert("tab_files", "Files");
    m.insert("tab_transfers", "Transfers");
    m.insert("tab_log", "Log");
    m.insert("tab_config", "Config");
    m.insert("tab_acl", "ACL");
    m.insert("tab_help", "Help");

    // Status bar
    m.insert("sessions", "Sessions");
    m.insert("total", "Total");
    m.insert("errors", "Errors");

    // Dashboard
    m.insert("active_sessions", "Active Sessions");
    m.insert("tx_rate", "TX Rate");
    m.insert("rx_rate", "RX Rate");
    m.insert("active_transfers", "Active Transfers");
    m.insert("no_active_transfers", "No active transfers");
    m.insert("client", "Client");
    m.insert("file", "File");
    m.insert("direction", "Dir");
    m.insert("progress", "Progress");
    m.insert("speed", "Speed");
    m.insert("duration", "Duration");
    m.insert("blksize", "Blksize");
    m.insert("window", "Window");
    m.insert("download", "Download");
    m.insert("upload", "Upload");
    m.insert("bandwidth", "Bandwidth");
    m.insert("tx_mbps", "TX (MB/s)");
    m.insert("rx_mbps", "RX (MB/s)");

    // Files
    m.insert("refresh", "Refresh");
    m.insert("change_root", "Change Root...");
    m.insert("up", "Up");
    m.insert("name", "Name");
    m.insert("size", "Size");
    m.insert("type", "Type");
    m.insert("directory", "Directory");

    // Transfers
    m.insert("transfer_history", "Transfer History");
    m.insert("export_csv", "Export CSV");
    m.insert("export_json", "Export JSON");
    m.insert("status_label", "Status:");
    m.insert("all", "All");
    m.insert("completed", "Completed");
    m.insert("failed", "Failed");
    m.insert("cancelled", "Cancelled");
    m.insert("retransmits", "Retransmits");
    m.insert("ok", "OK");
    m.insert("fail", "FAIL");

    // Log
    m.insert("level", "Level:");
    m.insert("filter", "Filter:");
    m.insert("auto_scroll", "Auto-scroll");
    m.insert("clear", "Clear");
    m.insert("copy_all", "Copy All");
    m.insert("export", "Export");

    // Config
    m.insert("configuration", "Configuration");
    m.insert("server", "Server");
    m.insert(
        "port_restart_note",
        "* Port, Bind Address and IP Version require restart to take effect",
    );
    m.insert("port", "Port *:");
    m.insert("bind_address", "Bind Address *:");
    m.insert("root_directory", "Root Directory:");
    m.insert("browse", "Browse...");
    m.insert("ip_version", "IP Version *:");
    m.insert("dual_stack", "Dual Stack");
    m.insert("ipv4_only", "IPv4 Only");
    m.insert("ipv6_only", "IPv6 Only");
    m.insert("log_level", "Log Level:");
    m.insert("max_log_lines", "Max Log Lines:");
    m.insert("unlimited", "0 = unlimited");
    m.insert("protocol", "Protocol");
    m.insert("allow_write", "Allow Write:");
    m.insert("default_blksize", "Default Blksize:");
    m.insert("max_blksize", "Max Blksize:");
    m.insert("default_windowsize", "Default Windowsize:");
    m.insert("max_windowsize", "Max Windowsize:");
    m.insert("default_timeout", "Default Timeout:");
    m.insert("session", "Session");
    m.insert("max_sessions", "Max Sessions:");
    m.insert("max_retries", "Max Retries:");
    m.insert("session_timeout", "Session Timeout (s):");
    m.insert("exponential_backoff", "Exponential Backoff:");
    m.insert("security", "Security");
    m.insert("per_ip_max_sessions", "Per-IP Max Sessions:");
    m.insert("per_ip_rate_limit", "Per-IP Rate Limit:");
    m.insert("rate_limit_window", "Rate Limit Window (s):");
    m.insert("dashboard_section", "Dashboard");
    m.insert("show_bandwidth_chart", "Show Bandwidth Chart:");
    m.insert("filesystem", "Filesystem");
    m.insert("max_file_size", "Max File Size:");
    m.insert("allow_overwrite", "Allow Overwrite:");
    m.insert("create_directories", "Create Directories:");
    m.insert("follow_symlinks", "Follow Symlinks:");
    m.insert("apply", "Apply");
    m.insert(
        "restart_note",
        " (Port/Bind/IP changes require server restart)",
    );
    m.insert("reset_current", "Reset to Current");
    m.insert("reset_defaults", "Reset to Defaults");
    m.insert("import_toml", "Import TOML...");
    m.insert("export_toml", "Export TOML...");
    m.insert("language", "Language");
    m.insert("language_label", "Interface Language:");

    // ACL
    m.insert("access_control_list", "Access Control List");
    m.insert("mode", "Mode:");
    m.insert("disabled", "Disabled");
    m.insert("whitelist", "Whitelist");
    m.insert("blacklist", "Blacklist");
    m.insert("no_acl_rules", "No ACL rules configured");
    m.insert("acl_recommendation", "It is recommended to add ACL rules if the server is exposed to the network. Use whitelist mode to allow only trusted IP ranges, or blacklist mode to block specific addresses.");
    m.insert("action", "Action");
    m.insert("source_cidr", "Source (CIDR)");
    m.insert("operations", "Operations");
    m.insert("comment", "Comment");
    m.insert("allow", "Allow");
    m.insert("deny", "Deny");
    m.insert("add_rule", "Add Rule");
    m.insert("add", "Add:");
    m.insert("invalid_cidr", "Invalid CIDR notation");
    m.insert("reset", "Reset");

    // Help
    m.insert("help_title", "Fry TFTP Server");
    m.insert(
        "help_subtitle",
        "High-performance, cross-platform TFTP server",
    );
    m.insert("supported_rfcs", "Supported RFCs");
    m.insert("features", "Features");

    // About
    m.insert("about_title", "Fry TFTP Server");
    m.insert("version", "Version:");
    m.insert("author", "Author:");
    m.insert("author_name", "Viacheslav Gordeev");
    m.insert("email", "Email:");
    m.insert("source", "Source:");
    m.insert("license", "License:");
    m.insert("built_with", "Built with Rust, egui, tokio, ratatui");

    m
}

fn ru() -> HashMap<&'static str, &'static str> {
    let mut m = HashMap::new();

    // Header
    m.insert("status", "Статус:");
    m.insert("listening", "Слушает:");
    m.insert("running", "Работает");
    m.insert("starting", "Запуск...");
    m.insert("stopping", "Остановка...");
    m.insert("stopped", "Остановлен");
    m.insert("error", "Ошибка");
    m.insert("start_server", "Запустить");
    m.insert("stop_server", "Остановить");
    m.insert("light_mode", "Светлая тема");
    m.insert("dark_mode", "Тёмная тема");
    m.insert("about", "О программе");
    m.insert("close", "Закрыть");

    // Tabs
    m.insert("tab_dashboard", "Обзор");
    m.insert("tab_files", "Файлы");
    m.insert("tab_transfers", "Передачи");
    m.insert("tab_log", "Журнал");
    m.insert("tab_config", "Настройки");
    m.insert("tab_acl", "ACL");
    m.insert("tab_help", "Справка");

    // Status bar
    m.insert("sessions", "Сессии");
    m.insert("total", "Всего");
    m.insert("errors", "Ошибки");

    // Dashboard
    m.insert("active_sessions", "Активные сессии");
    m.insert("tx_rate", "Скорость TX");
    m.insert("rx_rate", "Скорость RX");
    m.insert("active_transfers", "Активные передачи");
    m.insert("no_active_transfers", "Нет активных передач");
    m.insert("client", "Клиент");
    m.insert("file", "Файл");
    m.insert("direction", "Напр.");
    m.insert("progress", "Прогресс");
    m.insert("speed", "Скорость");
    m.insert("duration", "Время");
    m.insert("blksize", "Блок");
    m.insert("window", "Окно");
    m.insert("download", "Скачивание");
    m.insert("upload", "Загрузка");
    m.insert("bandwidth", "Пропускная способность");
    m.insert("tx_mbps", "TX (МБ/с)");
    m.insert("rx_mbps", "RX (МБ/с)");

    // Files
    m.insert("refresh", "Обновить");
    m.insert("change_root", "Сменить папку...");
    m.insert("up", "Вверх");
    m.insert("name", "Имя");
    m.insert("size", "Размер");
    m.insert("type", "Тип");
    m.insert("directory", "Папка");

    // Transfers
    m.insert("transfer_history", "История передач");
    m.insert("export_csv", "Экспорт CSV");
    m.insert("export_json", "Экспорт JSON");
    m.insert("status_label", "Статус:");
    m.insert("all", "Все");
    m.insert("completed", "Завершено");
    m.insert("failed", "Ошибка");
    m.insert("cancelled", "Отменено");
    m.insert("retransmits", "Повторы");
    m.insert("ok", "ОК");
    m.insert("fail", "ОШИБ");

    // Log
    m.insert("level", "Уровень:");
    m.insert("filter", "Фильтр:");
    m.insert("auto_scroll", "Авто-прокрутка");
    m.insert("clear", "Очистить");
    m.insert("copy_all", "Копировать");
    m.insert("export", "Экспорт");

    // Config
    m.insert("configuration", "Конфигурация");
    m.insert("server", "Сервер");
    m.insert(
        "port_restart_note",
        "* Порт, адрес и IP-версия требуют перезапуска",
    );
    m.insert("port", "Порт *:");
    m.insert("bind_address", "Адрес *:");
    m.insert("root_directory", "Корневая папка:");
    m.insert("browse", "Обзор...");
    m.insert("ip_version", "IP версия *:");
    m.insert("dual_stack", "Двойной стек");
    m.insert("ipv4_only", "Только IPv4");
    m.insert("ipv6_only", "Только IPv6");
    m.insert("log_level", "Уровень логов:");
    m.insert("max_log_lines", "Макс. строк лога:");
    m.insert("unlimited", "0 = без ограничений");
    m.insert("protocol", "Протокол");
    m.insert("allow_write", "Разрешить запись:");
    m.insert("default_blksize", "Блок по умолч.:");
    m.insert("max_blksize", "Макс. блок:");
    m.insert("default_windowsize", "Окно по умолч.:");
    m.insert("max_windowsize", "Макс. окно:");
    m.insert("default_timeout", "Таймаут по умолч.:");
    m.insert("session", "Сессия");
    m.insert("max_sessions", "Макс. сессий:");
    m.insert("max_retries", "Макс. повторов:");
    m.insert("session_timeout", "Таймаут сессии (с):");
    m.insert("exponential_backoff", "Экспон. откат:");
    m.insert("security", "Безопасность");
    m.insert("per_ip_max_sessions", "Сессий на IP:");
    m.insert("per_ip_rate_limit", "Лимит запросов/IP:");
    m.insert("rate_limit_window", "Окно лимита (с):");
    m.insert("dashboard_section", "Обзор");
    m.insert("show_bandwidth_chart", "Показывать график:");
    m.insert("filesystem", "Файловая система");
    m.insert("max_file_size", "Макс. размер файла:");
    m.insert("allow_overwrite", "Перезапись файлов:");
    m.insert("create_directories", "Создавать папки:");
    m.insert("follow_symlinks", "Следовать ссылкам:");
    m.insert("apply", "Применить");
    m.insert("restart_note", " (Порт/Адрес/IP требуют перезапуска)");
    m.insert("reset_current", "Сбросить к текущим");
    m.insert("reset_defaults", "По умолчанию");
    m.insert("import_toml", "Импорт TOML...");
    m.insert("export_toml", "Экспорт TOML...");
    m.insert("language", "Язык");
    m.insert("language_label", "Язык интерфейса:");

    // ACL
    m.insert("access_control_list", "Список доступа");
    m.insert("mode", "Режим:");
    m.insert("disabled", "Выключен");
    m.insert("whitelist", "Белый список");
    m.insert("blacklist", "Чёрный список");
    m.insert("no_acl_rules", "Правила ACL не настроены");
    m.insert("acl_recommendation", "Рекомендуется добавить правила ACL если сервер доступен из сети. Используйте белый список для доверенных IP или чёрный список для блокировки.");
    m.insert("action", "Действие");
    m.insert("source_cidr", "Источник (CIDR)");
    m.insert("operations", "Операции");
    m.insert("comment", "Комментарий");
    m.insert("allow", "Разрешить");
    m.insert("deny", "Запретить");
    m.insert("add_rule", "Добавить");
    m.insert("add", "Добавить:");
    m.insert("invalid_cidr", "Неверный CIDR формат");
    m.insert("reset", "Сбросить");

    // Help
    m.insert("help_title", "Fry TFTP Server");
    m.insert(
        "help_subtitle",
        "Высокопроизводительный кроссплатформенный TFTP сервер",
    );
    m.insert("supported_rfcs", "Поддерживаемые RFC");
    m.insert("features", "Возможности");

    // About
    m.insert("about_title", "Fry TFTP Server");
    m.insert("version", "Версия:");
    m.insert("author", "Автор:");
    m.insert("author_name", "Вячеслав Гордеев");
    m.insert("email", "Почта:");
    m.insert("source", "Исходный код:");
    m.insert("license", "Лицензия:");
    m.insert("built_with", "Создано на Rust, egui, tokio, ratatui");

    m
}
