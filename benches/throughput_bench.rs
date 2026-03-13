use criterion::{black_box, criterion_group, criterion_main, Criterion};
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;

fn bench_acl_matching(c: &mut Criterion) {
    use fry_tftp_server::core::acl::{AclEngine, Operation};
    use fry_tftp_server::core::config::{AclConfig, AclRuleConfig};

    let rules: Vec<AclRuleConfig> = (0..50)
        .map(|i| AclRuleConfig {
            action: if i % 2 == 0 {
                "allow".to_string()
            } else {
                "deny".to_string()
            },
            source: format!("10.{}.0.0/16", i),
            operations: vec!["read".to_string()],
            comment: format!("Rule {}", i),
        })
        .collect();

    let config = AclConfig {
        mode: "whitelist".to_string(),
        rules,
    };
    let acl = AclEngine::new(&config);

    // IP that matches the last rule
    let ip: IpAddr = "10.49.1.1".parse().unwrap();

    c.bench_function("acl_match_50_rules", |b| {
        b.iter(|| {
            let _ = black_box(acl.check(black_box(ip), black_box(Operation::Read)));
        })
    });

    // IP that matches no rule (worst case — scans all)
    let no_match_ip: IpAddr = "192.168.1.1".parse().unwrap();

    c.bench_function("acl_no_match_50_rules", |b| {
        b.iter(|| {
            let _ = black_box(acl.check(black_box(no_match_ip), black_box(Operation::Read)));
        })
    });
}

fn bench_path_resolution(c: &mut Criterion) {
    use fry_tftp_server::core::fs;

    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));

    c.bench_function("resolve_path_valid", |b| {
        b.iter(|| {
            let _ = black_box(fs::resolve_path(
                black_box(&root),
                black_box("Cargo.toml"),
                black_box(true),
                black_box(false),
            ));
        })
    });

    c.bench_function("resolve_path_traversal_reject", |b| {
        b.iter(|| {
            let _ = black_box(fs::resolve_path(
                black_box(&root),
                black_box("../../etc/passwd"),
                black_box(true),
                black_box(false),
            ));
        })
    });
}

fn bench_session_info_creation(c: &mut Criterion) {
    use fry_tftp_server::core::state::{Direction, SessionInfo, SessionStatus};

    let addr = SocketAddr::new(IpAddr::V4(Ipv4Addr::new(192, 168, 1, 10)), 54321);

    c.bench_function("session_info_create", |b| {
        b.iter(|| {
            let _ = black_box(SessionInfo {
                id: uuid::Uuid::new_v4(),
                client_addr: addr,
                filename: "firmware.bin".to_string(),
                direction: Direction::Read,
                status: SessionStatus::Transferring,
                blksize: 1468,
                windowsize: 64,
                tsize: Some(52428800),
                bytes_transferred: 0,
                started_at: std::time::Instant::now(),
                last_activity: std::time::Instant::now(),
                retransmits: 0,
            });
        })
    });
}

criterion_group!(
    benches,
    bench_acl_matching,
    bench_path_resolution,
    bench_session_info_creation,
);
criterion_main!(benches);
