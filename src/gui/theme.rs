use egui::{Color32, Visuals};

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Theme {
    Dark,
    Light,
}

impl Theme {
    pub fn apply(&self, ctx: &egui::Context) {
        match self {
            Theme::Dark => {
                let mut visuals = Visuals::dark();
                visuals.panel_fill = Color32::from_rgb(0x1a, 0x1a, 0x2e);
                visuals.window_fill = Color32::from_rgb(0x1a, 0x1a, 0x2e);
                visuals.extreme_bg_color = Color32::from_rgb(0x10, 0x10, 0x20);
                ctx.set_visuals(visuals);
            }
            Theme::Light => {
                ctx.set_visuals(Visuals::light());
            }
        }
    }

    pub fn sidebar_bg(&self) -> Color32 {
        match self {
            Theme::Dark => Color32::from_rgb(0x16, 0x21, 0x3e),
            Theme::Light => Color32::from_rgb(0xf0, 0xf0, 0xf5),
        }
    }

    pub fn accent(&self) -> Color32 {
        match self {
            Theme::Dark => Color32::from_rgb(0x0f, 0x34, 0x60),
            Theme::Light => Color32::from_rgb(0x19, 0x76, 0xd2),
        }
    }

    pub fn status_running(&self) -> Color32 {
        Color32::from_rgb(0x4c, 0xaf, 0x50)
    }

    pub fn status_stopped(&self) -> Color32 {
        Color32::from_rgb(0x9e, 0x9e, 0x9e)
    }

    pub fn status_error(&self) -> Color32 {
        Color32::from_rgb(0xf4, 0x43, 0x36)
    }

    pub fn log_color(&self, level: &tracing::Level) -> Color32 {
        match *level {
            tracing::Level::TRACE => Color32::from_rgb(0x90, 0x90, 0x90),
            tracing::Level::DEBUG => Color32::from_rgb(0x00, 0xbc, 0xd4),
            tracing::Level::INFO => Color32::from_rgb(0x4c, 0xaf, 0x50),
            tracing::Level::WARN => Color32::from_rgb(0xff, 0xc1, 0x07),
            tracing::Level::ERROR => Color32::from_rgb(0xf4, 0x43, 0x36),
        }
    }
}
