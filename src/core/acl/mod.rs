use crate::core::config::AclConfig;
use ipnet::IpNet;
use std::net::IpAddr;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Operation {
    Read,
    Write,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AclAction {
    Allow,
    Deny,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AclMode {
    Whitelist,
    Blacklist,
    Disabled,
}

#[derive(Debug, Clone)]
pub struct AclRule {
    pub action: AclAction,
    pub source: IpNet,
    pub operations: Vec<Operation>,
}

#[derive(Debug, Clone)]
pub struct AclEngine {
    mode: AclMode,
    rules: Vec<AclRule>,
}

impl AclEngine {
    pub fn new(config: &AclConfig) -> Self {
        let mode = match config.mode.as_str() {
            "whitelist" => AclMode::Whitelist,
            "blacklist" => AclMode::Blacklist,
            _ => AclMode::Disabled,
        };

        let rules = config
            .rules
            .iter()
            .filter_map(|r| {
                let action = match r.action.as_str() {
                    "allow" => AclAction::Allow,
                    "deny" => AclAction::Deny,
                    _ => return None,
                };

                let source: IpNet = r.source.parse().ok()?;

                let operations: Vec<Operation> = r
                    .operations
                    .iter()
                    .flat_map(|op| match op.as_str() {
                        "read" => vec![Operation::Read],
                        "write" => vec![Operation::Write],
                        "all" => vec![Operation::Read, Operation::Write],
                        _ => vec![],
                    })
                    .collect();

                Some(AclRule {
                    action,
                    source,
                    operations,
                })
            })
            .collect();

        Self { mode, rules }
    }

    /// Check if a client IP is allowed to perform an operation
    pub fn check(&self, client_ip: IpAddr, operation: Operation) -> bool {
        if self.mode == AclMode::Disabled {
            return true;
        }

        // Normalize IPv4-mapped IPv6 to IPv4 for matching
        let normalized_ip = normalize_ip(client_ip);

        for rule in &self.rules {
            if rule.source.contains(&normalized_ip) && rule.operations.contains(&operation) {
                return rule.action == AclAction::Allow;
            }
        }

        // Default policy
        match self.mode {
            AclMode::Whitelist => false, // not matched = deny
            AclMode::Blacklist => true,  // not matched = allow
            AclMode::Disabled => true,
        }
    }

    pub fn reload(&mut self, config: &AclConfig) {
        *self = Self::new(config);
    }
}

/// Normalize IPv4-mapped IPv6 addresses (::ffff:x.x.x.x) to plain IPv4
fn normalize_ip(ip: IpAddr) -> IpAddr {
    match ip {
        IpAddr::V6(v6) => {
            if let Some(v4) = v6.to_ipv4_mapped() {
                IpAddr::V4(v4)
            } else {
                IpAddr::V6(v6)
            }
        }
        v4 => v4,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::config::{AclConfig, AclRuleConfig};

    fn make_config(mode: &str, rules: Vec<AclRuleConfig>) -> AclConfig {
        AclConfig {
            mode: mode.to_string(),
            rules,
        }
    }

    fn rule(action: &str, source: &str, ops: &[&str]) -> AclRuleConfig {
        AclRuleConfig {
            action: action.to_string(),
            source: source.to_string(),
            operations: ops.iter().map(|s| s.to_string()).collect(),
            comment: String::new(),
        }
    }

    #[test]
    fn test_disabled_allows_all() {
        let acl = AclEngine::new(&make_config("disabled", vec![]));
        let ip: IpAddr = "192.168.1.10".parse().unwrap();
        assert!(acl.check(ip, Operation::Read));
        assert!(acl.check(ip, Operation::Write));
    }

    #[test]
    fn test_whitelist_denies_unmatched() {
        let acl = AclEngine::new(&make_config(
            "whitelist",
            vec![rule("allow", "10.0.0.0/8", &["read"])],
        ));
        let ip: IpAddr = "192.168.1.10".parse().unwrap();
        assert!(!acl.check(ip, Operation::Read));
    }

    #[test]
    fn test_whitelist_allows_matched() {
        let acl = AclEngine::new(&make_config(
            "whitelist",
            vec![rule("allow", "192.168.1.0/24", &["read"])],
        ));
        let ip: IpAddr = "192.168.1.10".parse().unwrap();
        assert!(acl.check(ip, Operation::Read));
        assert!(!acl.check(ip, Operation::Write)); // write not in rule
    }

    #[test]
    fn test_blacklist_denies_matched() {
        let acl = AclEngine::new(&make_config(
            "blacklist",
            vec![rule("deny", "192.168.1.0/24", &["write"])],
        ));
        let ip: IpAddr = "192.168.1.10".parse().unwrap();
        assert!(acl.check(ip, Operation::Read)); // not in deny rule
        assert!(!acl.check(ip, Operation::Write)); // in deny rule
    }

    #[test]
    fn test_blacklist_allows_unmatched() {
        let acl = AclEngine::new(&make_config(
            "blacklist",
            vec![rule("deny", "10.0.0.0/8", &["all"])],
        ));
        let ip: IpAddr = "192.168.1.10".parse().unwrap();
        assert!(acl.check(ip, Operation::Read));
        assert!(acl.check(ip, Operation::Write));
    }

    #[test]
    fn test_rule_order_matters() {
        let acl = AclEngine::new(&make_config(
            "whitelist",
            vec![
                rule("allow", "192.168.1.0/24", &["read"]),
                rule("deny", "192.168.1.10/32", &["read"]),
            ],
        ));
        // First matching rule wins: /24 matches before /32
        let ip: IpAddr = "192.168.1.10".parse().unwrap();
        assert!(acl.check(ip, Operation::Read));
    }

    #[test]
    fn test_ipv6() {
        let acl = AclEngine::new(&make_config(
            "whitelist",
            vec![rule("allow", "fd00::/8", &["read"])],
        ));
        let ip: IpAddr = "fd00::1".parse().unwrap();
        assert!(acl.check(ip, Operation::Read));
    }
}
