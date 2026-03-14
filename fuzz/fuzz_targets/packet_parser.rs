#![no_main]

use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // parse_packet must never panic on any input
    let _ = fry_tftp_server::core::protocol::packet::parse_packet(data);
});
