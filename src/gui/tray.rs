use tray_icon::menu::{Menu, MenuEvent, MenuItem};
use tray_icon::{Icon, TrayIcon, TrayIconBuilder};

pub struct TrayState {
    pub tray_icon: TrayIcon,
    pub show_id: tray_icon::menu::MenuId,
    pub stop_id: tray_icon::menu::MenuId,
    pub quit_id: tray_icon::menu::MenuId,
}

fn create_icon(r: u8, g: u8, b: u8) -> Icon {
    let size = 16u32;
    let mut rgba = Vec::with_capacity((size * size * 4) as usize);
    for y in 0..size {
        for x in 0..size {
            // Simple circle
            let dx = x as f32 - 7.5;
            let dy = y as f32 - 7.5;
            let dist = (dx * dx + dy * dy).sqrt();
            if dist < 7.0 {
                rgba.extend_from_slice(&[r, g, b, 255]);
            } else if dist < 8.0 {
                // Anti-alias edge
                let alpha = ((8.0 - dist) * 255.0) as u8;
                rgba.extend_from_slice(&[r, g, b, alpha]);
            } else {
                rgba.extend_from_slice(&[0, 0, 0, 0]);
            }
        }
    }
    Icon::from_rgba(rgba, size, size).expect("failed to create tray icon")
}

pub fn create_tray() -> anyhow::Result<TrayState> {
    let menu = Menu::new();

    let show_item = MenuItem::new("Show", true, None);
    let stop_item = MenuItem::new("Stop Server", true, None);
    let quit_item = MenuItem::new("Quit", true, None);

    let show_id = show_item.id().clone();
    let stop_id = stop_item.id().clone();
    let quit_id = quit_item.id().clone();

    menu.append(&show_item)?;
    menu.append(&stop_item)?;
    menu.append(&quit_item)?;

    let icon = create_icon(0x4c, 0xaf, 0x50); // green = running

    let tray_icon = TrayIconBuilder::new()
        .with_menu(Box::new(menu))
        .with_tooltip("Fry TFTP Server - Running")
        .with_icon(icon)
        .build()?;

    Ok(TrayState {
        tray_icon,
        show_id,
        stop_id,
        quit_id,
    })
}

/// Tray visual state: Running (green), Stopped (grey), Error (red)
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum TrayVisualState {
    Running,
    Stopped,
    Error,
}

pub fn update_tray_icon(tray: &TrayState, visual: TrayVisualState) {
    let (r, g, b, tooltip) = match visual {
        TrayVisualState::Running => (0x4c, 0xaf, 0x50, "Fry TFTP Server - Running"),
        TrayVisualState::Stopped => (0x9e, 0x9e, 0x9e, "Fry TFTP Server - Stopped"),
        TrayVisualState::Error => (0xf4, 0x43, 0x36, "Fry TFTP Server - Error"),
    };
    let icon = create_icon(r, g, b);
    let _ = tray.tray_icon.set_icon(Some(icon));
    let _ = tray.tray_icon.set_tooltip(Some(tooltip));
}

/// Poll for menu events, returns action if any
pub enum TrayAction {
    Show,
    Stop,
    Quit,
}

pub fn poll_tray_events(tray: &TrayState) -> Option<TrayAction> {
    if let Ok(event) = MenuEvent::receiver().try_recv() {
        if event.id == tray.show_id {
            return Some(TrayAction::Show);
        } else if event.id == tray.stop_id {
            return Some(TrayAction::Stop);
        } else if event.id == tray.quit_id {
            return Some(TrayAction::Quit);
        }
    }
    None
}
