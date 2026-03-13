use egui::Ui;

pub struct HelpState {
    pub show_about: bool,
}

impl Default for HelpState {
    fn default() -> Self {
        Self::new()
    }
}

impl HelpState {
    pub fn new() -> Self {
        Self { show_about: false }
    }
}

pub fn draw(ui: &mut Ui, _help: &mut HelpState) {
    egui::ScrollArea::vertical().show(ui, |ui| {
        ui.heading("Fry TFTP Server");
        ui.add_space(4.0);
        ui.label(
            egui::RichText::new("High-performance, cross-platform TFTP server")
                .size(14.0)
                .italics(),
        );
        ui.label(format!("Version: {}", env!("CARGO_PKG_VERSION")));

        ui.add_space(12.0);
        ui.separator();
        ui.add_space(8.0);

        // ── Supported RFCs ──
        ui.heading("Supported RFCs");
        ui.add_space(4.0);

        egui::Grid::new("rfc_grid")
            .striped(true)
            .min_col_width(100.0)
            .show(ui, |ui| {
                ui.strong("RFC");
                ui.strong("Title");
                ui.strong("Description");
                ui.end_row();

                ui.label("RFC 1350");
                ui.label("TFTP Protocol (Revision 2)");
                ui.label(
                    "Base protocol: RRQ, WRQ, DATA, ACK, ERROR opcodes, octet and netascii modes",
                );
                ui.end_row();

                ui.label("RFC 2347");
                ui.label("Option Extension");
                ui.label("OACK negotiation for extended options between client and server");
                ui.end_row();

                ui.label("RFC 2348");
                ui.label("Blocksize Option");
                ui.label("Configurable block size from 8 to 65464 bytes (default 512)");
                ui.end_row();

                ui.label("RFC 2349");
                ui.label("Timeout & Transfer Size");
                ui.label("Timeout negotiation and tsize option for transfer size reporting");
                ui.end_row();

                ui.label("RFC 7440");
                ui.label("Windowsize Option");
                ui.label("Sliding window for higher throughput (up to 65535 blocks per window)");
                ui.end_row();
            });

        ui.add_space(12.0);
        ui.separator();
        ui.add_space(8.0);

        // ── Features ──
        ui.heading("Features");
        ui.add_space(4.0);

        let features = [
            "GUI mode (egui) with dashboard, file browser, transfer history, log viewer",
            "TUI mode (ratatui) for terminal-based operation",
            "Headless mode for server/daemon deployment",
            "Hot-reload configuration via file watcher and SIGHUP",
            "Access Control Lists (ACL) with whitelist/blacklist modes and CIDR support",
            "Per-IP rate limiting and session limits",
            "Memory-mapped file I/O for large file transfers",
            "Sliding window protocol for high throughput (250+ MB/s)",
            "Netascii and octet transfer modes",
            "Path traversal protection and symlink policy enforcement",
            "Circular log rotation with configurable line limits",
            "System tray integration with status indicators",
            "Windows Service, systemd, and launchd support",
            "Environment variable overrides (TFTP_SERVER_*)",
            "Export transfers as CSV/JSON",
        ];
        for feat in &features {
            ui.horizontal(|ui| {
                ui.label("  -");
                ui.label(*feat);
            });
        }
    });
}
