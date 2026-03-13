#![no_main]

use libfuzzer_sys::fuzz_target;
use std::path::PathBuf;

fuzz_target!(|data: &[u8]| {
    // resolve_path must never panic on any input
    if let Ok(s) = std::str::from_utf8(data) {
        let root = PathBuf::from(if cfg!(windows) {
            "C:\\TFTP"
        } else {
            "/tmp/fuzz-root"
        });
        let _ = fry_tftp_server::core::fs::resolve_path(&root, s, false, false);
    }
});
