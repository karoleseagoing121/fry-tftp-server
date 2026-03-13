pub mod acl_tab;
pub mod config_tab;
pub mod dashboard;
pub mod files;
pub mod help_tab;
pub mod log_tab;
pub mod transfers;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Tab {
    Dashboard,
    Files,
    Transfers,
    Log,
    Config,
    Acl,
    Help,
}

impl Tab {
    /// Main tabs (shown at top of sidebar).
    pub const MAIN: &'static [Tab] = &[
        Tab::Dashboard,
        Tab::Files,
        Tab::Transfers,
        Tab::Log,
        Tab::Config,
        Tab::Acl,
    ];

    pub fn label(&self) -> &str {
        match self {
            Tab::Dashboard => "Dashboard",
            Tab::Files => "Files",
            Tab::Transfers => "Transfers",
            Tab::Log => "Log",
            Tab::Config => "Config",
            Tab::Acl => "ACL",
            Tab::Help => "Help",
        }
    }

    pub fn i18n_key(&self) -> &str {
        match self {
            Tab::Dashboard => "tab_dashboard",
            Tab::Files => "tab_files",
            Tab::Transfers => "tab_transfers",
            Tab::Log => "tab_log",
            Tab::Config => "tab_config",
            Tab::Acl => "tab_acl",
            Tab::Help => "tab_help",
        }
    }

    pub fn icon(&self) -> &str {
        match self {
            Tab::Dashboard => "\u{1F4CA}",
            Tab::Files => "\u{1F4C1}",
            Tab::Transfers => "\u{1F504}",
            Tab::Log => "\u{1F4DD}",
            Tab::Config => "\u{2699}",
            Tab::Acl => "\u{1F6E1}",
            Tab::Help => "\u{2753}",
        }
    }
}
