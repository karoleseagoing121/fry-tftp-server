#[cfg(feature = "tui")]
pub mod app;

#[cfg(feature = "tui")]
pub async fn run(
    state: std::sync::Arc<crate::core::state::AppState>,
    log_buffer: crate::core::log_buffer::LogBuffer,
) -> anyhow::Result<()> {
    use std::io;
    use std::time::Duration;

    use crossterm::event::{self, DisableMouseCapture, EnableMouseCapture, Event};
    use crossterm::execute;
    use crossterm::terminal::{
        disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
    };
    use ratatui::backend::CrosstermBackend;
    use ratatui::Terminal;

    use crate::platform;

    // Register signal handlers
    platform::register_signals(state.get_shutdown_token(), Some(state.clone())).await;

    // Spawn the TFTP server in background
    let server_state = state.clone();
    tokio::spawn(async move {
        if let Err(e) = crate::core::run_server(server_state).await {
            tracing::error!(error = %e, "server error");
        }
    });

    let app_state_for_close = state.clone();

    // Run TUI event loop (blocking)
    let result = tokio::task::block_in_place(|| -> anyhow::Result<()> {
        // Setup terminal
        enable_raw_mode()?;
        let mut stdout = io::stdout();
        execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
        let backend = CrosstermBackend::new(stdout);
        let mut terminal = Terminal::new(backend)?;

        let mut tui_app = app::TuiApp::new(state, log_buffer);

        // Event loop
        loop {
            terminal.draw(|f| tui_app.render(f))?;

            if event::poll(Duration::from_millis(250))? {
                match event::read()? {
                    Event::Key(key) => {
                        if tui_app.handle_key(key) {
                            break;
                        }
                    }
                    Event::Mouse(mouse) => {
                        tui_app.handle_mouse(mouse);
                    }
                    _ => {}
                }
            }

            if tui_app.should_quit {
                break;
            }
        }

        // Restore terminal
        disable_raw_mode()?;
        execute!(
            terminal.backend_mut(),
            LeaveAlternateScreen,
            DisableMouseCapture
        )?;
        terminal.show_cursor()?;
        Ok(())
    });

    app_state_for_close.cancel_shutdown();
    result
}
