use std::sync::Arc;

use egui::Ui;

use crate::core::i18n::I18n;
use crate::core::state::*;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum SortColumn {
    Client,
    File,
    Direction,
    Size,
    Duration,
    Speed,
    Status,
    Retransmits,
}

pub struct TransfersState {
    pub filter_ip: String,
    pub filter_filename: String,
    pub filter_status: String,
    pub sort_column: SortColumn,
    pub sort_ascending: bool,
    pub show_clear_popup: bool,
}

impl Default for TransfersState {
    fn default() -> Self {
        Self::new()
    }
}

impl TransfersState {
    pub fn new() -> Self {
        Self {
            filter_ip: String::new(),
            filter_filename: String::new(),
            filter_status: "all".to_string(),
            sort_column: SortColumn::Duration,
            sort_ascending: false,
            show_clear_popup: false,
        }
    }
}

fn format_bytes(bytes: u64) -> String {
    if bytes >= 1_000_000_000 {
        format!("{:.1} GB", bytes as f64 / 1_000_000_000.0)
    } else if bytes >= 1_000_000 {
        format!("{:.1} MB", bytes as f64 / 1_000_000.0)
    } else if bytes >= 1_000 {
        format!("{:.1} KB", bytes as f64 / 1_000.0)
    } else {
        format!("{} B", bytes)
    }
}

fn export_json(records: &[&TransferRecord]) {
    if let Some(path) = rfd::FileDialog::new()
        .set_title("Export transfers as JSON")
        .add_filter("JSON", &["json"])
        .set_file_name("transfers.json")
        .save_file()
    {
        let entries: Vec<serde_json::Value> = records
            .iter()
            .map(|r| {
                serde_json::json!({
                    "client": r.client_addr.to_string(),
                    "file": r.filename,
                    "direction": match r.direction {
                        Direction::Read => "Download",
                        Direction::Write => "Upload",
                    },
                    "bytes": r.bytes_transferred,
                    "duration_ms": r.duration_ms,
                    "speed_mbps": r.speed_mbps,
                    "status": match r.status {
                        SessionStatus::Completed => "Completed",
                        SessionStatus::Failed => "Failed",
                        SessionStatus::Cancelled => "Cancelled",
                        _ => "Unknown",
                    },
                    "retransmits": r.retransmits,
                    "elapsed_secs": r.timestamp.elapsed().as_secs(),
                })
            })
            .collect();
        match serde_json::to_string_pretty(&entries) {
            Ok(json) => {
                if let Err(e) = std::fs::write(&path, json) {
                    tracing::error!(error=%e, "failed to export JSON");
                }
            }
            Err(e) => {
                tracing::error!(error=%e, "failed to serialize JSON");
            }
        }
    }
}

fn export_csv(records: &[&TransferRecord]) {
    if let Some(path) = rfd::FileDialog::new()
        .set_title("Export transfers as CSV")
        .add_filter("CSV", &["csv"])
        .set_file_name("transfers.csv")
        .save_file()
    {
        let mut csv =
            String::from("Client,File,Direction,Bytes,Duration_ms,Speed_Mbps,Status,Retransmits\n");
        for r in records {
            let dir = match r.direction {
                Direction::Read => "Download",
                Direction::Write => "Upload",
            };
            let status = match r.status {
                SessionStatus::Completed => "Completed",
                SessionStatus::Failed => "Failed",
                SessionStatus::Cancelled => "Cancelled",
                _ => "Unknown",
            };
            csv.push_str(&format!(
                "{},{},{},{},{},{:.2},{},{}\n",
                r.client_addr,
                r.filename,
                dir,
                r.bytes_transferred,
                r.duration_ms,
                r.speed_mbps,
                status,
                r.retransmits
            ));
        }
        if let Err(e) = std::fs::write(&path, csv) {
            tracing::error!(error=%e, "failed to export CSV");
        }
    }
}

pub fn draw(
    ui: &mut Ui,
    history: &[TransferRecord],
    transfers: &mut TransfersState,
    state: &Arc<AppState>,
    i18n: &I18n,
) {
    ui.heading(i18n.t("transfer_history"));

    // Filters + Export
    ui.horizontal(|ui| {
        ui.label("IP:");
        ui.add(egui::TextEdit::singleline(&mut transfers.filter_ip).desired_width(120.0));
        ui.label(i18n.t("file"));
        ui.add(egui::TextEdit::singleline(&mut transfers.filter_filename).desired_width(120.0));
        ui.label(i18n.t("status_label"));
        egui::ComboBox::from_id_salt("status_filter")
            .selected_text(&transfers.filter_status)
            .show_ui(ui, |ui| {
                ui.selectable_value(
                    &mut transfers.filter_status,
                    "all".to_string(),
                    i18n.t("all"),
                );
                ui.selectable_value(
                    &mut transfers.filter_status,
                    "completed".to_string(),
                    i18n.t("completed"),
                );
                ui.selectable_value(
                    &mut transfers.filter_status,
                    "failed".to_string(),
                    i18n.t("failed"),
                );
            });

        if ui.button(i18n.t("clear")).clicked() {
            transfers.show_clear_popup = true;
        }
    });

    // Clear confirmation popup
    if transfers.show_clear_popup {
        egui::Window::new(i18n.t("clear"))
            .collapsible(false)
            .resizable(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ui.ctx(), |ui| {
                ui.label("Clear transfer history?");
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    if ui.button("GUI only").clicked() {
                        if let Ok(mut h) = state.transfer_history.try_write() {
                            h.clear();
                        }
                        transfers.show_clear_popup = false;
                    }
                    if ui.button("GUI + File").clicked() {
                        if let Ok(mut h) = state.transfer_history.try_write() {
                            h.clear();
                        }
                        let config = state.config();
                        if !config.server.transfer_log.is_empty() {
                            let _ = std::fs::write(&config.server.transfer_log, "");
                        }
                        transfers.show_clear_popup = false;
                    }
                    if ui.button(i18n.t("close")).clicked() {
                        transfers.show_clear_popup = false;
                    }
                });
            });
    }

    ui.separator();

    let mut filtered: Vec<&TransferRecord> = history
        .iter()
        .filter(|r| {
            if !transfers.filter_ip.is_empty()
                && !r
                    .client_addr
                    .ip()
                    .to_string()
                    .contains(&transfers.filter_ip)
            {
                return false;
            }
            if !transfers.filter_filename.is_empty()
                && !r.filename.contains(&transfers.filter_filename)
            {
                return false;
            }
            match transfers.filter_status.as_str() {
                "completed" => r.status == SessionStatus::Completed,
                "failed" => r.status == SessionStatus::Failed,
                _ => true,
            }
        })
        .collect();

    // Sort
    let asc = transfers.sort_ascending;
    match transfers.sort_column {
        SortColumn::Client => filtered.sort_by(|a, b| {
            let c = a.client_addr.to_string().cmp(&b.client_addr.to_string());
            if asc {
                c
            } else {
                c.reverse()
            }
        }),
        SortColumn::File => filtered.sort_by(|a, b| {
            let c = a.filename.cmp(&b.filename);
            if asc {
                c
            } else {
                c.reverse()
            }
        }),
        SortColumn::Direction => filtered.sort_by(|a, b| {
            let c = (a.direction as u8).cmp(&(b.direction as u8));
            if asc {
                c
            } else {
                c.reverse()
            }
        }),
        SortColumn::Size => filtered.sort_by(|a, b| {
            let c = a.bytes_transferred.cmp(&b.bytes_transferred);
            if asc {
                c
            } else {
                c.reverse()
            }
        }),
        SortColumn::Duration => filtered.sort_by(|a, b| {
            let c = a.duration_ms.cmp(&b.duration_ms);
            if asc {
                c
            } else {
                c.reverse()
            }
        }),
        SortColumn::Speed => filtered.sort_by(|a, b| {
            let c = a
                .speed_mbps
                .partial_cmp(&b.speed_mbps)
                .unwrap_or(std::cmp::Ordering::Equal);
            if asc {
                c
            } else {
                c.reverse()
            }
        }),
        SortColumn::Status => filtered.sort_by(|a, b| {
            let c = (a.status as u8).cmp(&(b.status as u8));
            if asc {
                c
            } else {
                c.reverse()
            }
        }),
        SortColumn::Retransmits => filtered.sort_by(|a, b| {
            let c = a.retransmits.cmp(&b.retransmits);
            if asc {
                c
            } else {
                c.reverse()
            }
        }),
    }

    ui.horizontal(|ui| {
        ui.label(format!("{} records", filtered.len()));
        if ui.button(i18n.t("export_csv")).clicked() {
            export_csv(&filtered);
        }
        if ui.button(i18n.t("export_json")).clicked() {
            export_json(&filtered);
        }
    });

    let w = ui.available_width();
    let cw = [
        w * 0.18,
        w * 0.20,
        w * 0.07,
        w * 0.12,
        w * 0.10,
        w * 0.11,
        w * 0.10,
        w * 0.12,
    ];
    let h = 20.0;

    egui::Grid::new("transfers_grid")
        .num_columns(8)
        .striped(true)
        .spacing([0.0, 4.0])
        .show(ui, |ui| {
            let cols = [
                (i18n.t("client"), SortColumn::Client),
                (i18n.t("file"), SortColumn::File),
                (i18n.t("direction"), SortColumn::Direction),
                (i18n.t("size"), SortColumn::Size),
                (i18n.t("duration"), SortColumn::Duration),
                (i18n.t("speed"), SortColumn::Speed),
                (i18n.t("status_label"), SortColumn::Status),
                (i18n.t("retransmits"), SortColumn::Retransmits),
            ];
            for (idx, (label, col)) in cols.iter().enumerate() {
                let arrow = if transfers.sort_column == *col {
                    if transfers.sort_ascending {
                        " [A]"
                    } else {
                        " [D]"
                    }
                } else {
                    ""
                };
                let text = format!("{}{}", label, arrow);
                let response = ui.add_sized(
                    [cw[idx], h],
                    egui::Label::new(egui::RichText::new(text).strong())
                        .sense(egui::Sense::click()),
                );
                if response.clicked() {
                    if transfers.sort_column == *col {
                        transfers.sort_ascending = !transfers.sort_ascending;
                    } else {
                        transfers.sort_column = *col;
                        transfers.sort_ascending = true;
                    }
                }
            }
            ui.end_row();

            for record in &filtered {
                ui.add_sized([cw[0], h], egui::Label::new(record.client_addr.to_string()));
                ui.add_sized([cw[1], h], egui::Label::new(&record.filename));
                ui.add_sized(
                    [cw[2], h],
                    egui::Label::new(match record.direction {
                        Direction::Read => i18n.t("download"),
                        Direction::Write => i18n.t("upload"),
                    }),
                );
                ui.add_sized(
                    [cw[3], h],
                    egui::Label::new(format_bytes(record.bytes_transferred)),
                );
                ui.add_sized(
                    [cw[4], h],
                    egui::Label::new(format!("{}ms", record.duration_ms)),
                );
                ui.add_sized(
                    [cw[5], h],
                    egui::Label::new(format!("{:.2} Mbps", record.speed_mbps)),
                );
                ui.add_sized(
                    [cw[6], h],
                    egui::Label::new(match record.status {
                        SessionStatus::Completed => i18n.t("ok"),
                        SessionStatus::Failed => i18n.t("fail"),
                        SessionStatus::Cancelled => i18n.t("cancelled"),
                        _ => "?",
                    }),
                );
                ui.add_sized([cw[7], h], egui::Label::new(record.retransmits.to_string()));
                ui.end_row();
            }
        });
}
