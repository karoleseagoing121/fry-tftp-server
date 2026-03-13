pub mod acl_tab;
pub mod config_tab;
pub mod dashboard;
pub mod files;
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
}

impl Tab {
    pub const ALL: &'static [Tab] = &[
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
        }
    }
}
