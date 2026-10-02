//! netlist-guard: reject SPICE netlists that could escape the simulator sandbox.
//!
//! ngspice's `.control` blocks can run `shell` commands and write files, and `.include`/`.lib`
//! can read arbitrary paths. The desktop app treats every imported netlist as untrusted and
//! runs this check first. Rules mirror `watt_forge/spice.py::check_netlist` (same test cases).

pub const MAX_BYTES: usize = 256 * 1024;
pub const MAX_LINES: usize = 20_000;
pub const MAX_TRAN_POINTS: f64 = 5_000_000.0;

const ALLOWED_ELEMENTS: &str = "RCLVISDEGFHBKXMQJ";
const ALLOWED_DOT: &[&str] = &[
    ".model", ".tran", ".ic", ".param", ".meas", ".measure", ".option", ".options", ".end", ".title",
    ".subckt", ".ends", ".global", ".temp", ".op", ".dc", ".ac", ".save", ".func", ".nodeset",
];
const FORBIDDEN_DOT: &[&str] = &[".control", ".endc", ".include", ".inc", ".lib", ".endl", ".exec", ".csparam"];
const FORBIDDEN_WORDS: &[&str] = &[
    "shell", "system", "exec", "wrdata", "write", "wrs2p", "load", "source", "cd", "setcs", "codemodel", "pre_osdi", "osdi",
];

#[derive(Debug, PartialEq)]
pub struct Rejected(pub String);

fn has_word(line: &str, word: &str) -> bool {
    let bytes = line.as_bytes();
    let w = word.as_bytes();
    let mut i = 0;
    while let Some(pos) = line[i..].find(word) {
        let s = i + pos;
        let e = s + w.len();
        let before = s == 0 || !(bytes[s - 1].is_ascii_alphanumeric() || bytes[s - 1] == b'_');
        let after = e >= bytes.len() || !(bytes[e].is_ascii_alphanumeric() || bytes[e] == b'_');
        if before && after {
            return true;
        }
        i = s + 1;
    }
    false
}

/// Parse a SPICE number with an engineering suffix ("10u", "1meg", "2.5n").
pub fn parse_number(tok: &str) -> Option<f64> {
    let t = tok.trim().to_ascii_lowercase();
    let end = t
        .char_indices()
        .find(|(_, c)| !(c.is_ascii_digit() || *c == '.' || *c == '+' || *c == '-' || *c == 'e'))
        .map(|(i, _)| i)
        .unwrap_or(t.len());
    // "e" could also start a suffix-less exponent; try the longest numeric prefix that parses
    let (mut num, mut rest) = (&t[..end], &t[end..]);
    while !num.is_empty() && num.parse::<f64>().is_err() {
        let cut = num.len() - 1;
        rest = &t[cut..];
        num = &t[..cut];
    }
    let base: f64 = num.parse().ok()?;
    let mult = if rest.starts_with("meg") {
        1e6
    } else {
        match rest.chars().next() {
            Some('t') => 1e12,
            Some('g') => 1e9,
            Some('k') => 1e3,
            Some('m') => 1e-3,
            Some('u') => 1e-6,
            Some('n') => 1e-9,
            Some('p') => 1e-12,
            Some('f') => 1e-15,
            _ => 1.0,
        }
    };
    Some(base * mult)
}

pub fn check(text: &str) -> Result<(), Rejected> {
    if text.len() > MAX_BYTES {
        return Err(Rejected("netlist too large".into()));
    }
    if text.contains('\0') {
        return Err(Rejected("binary content".into()));
    }
    let lines: Vec<&str> = text.lines().collect();
    if lines.len() > MAX_LINES {
        return Err(Rejected("too many lines".into()));
    }
    for (idx, raw) in lines.iter().enumerate().skip(1) {
        let n = idx + 1;
        let line = raw.trim();
        if line.is_empty() || line.starts_with('*') || line.starts_with(';') {
            continue;
        }
        let cont = line.starts_with('+');
        let body = if cont { &line[1..] } else { line };
        let low = body.to_ascii_lowercase();
        for w in FORBIDDEN_WORDS {
            if has_word(&low, w) {
                return Err(Rejected(format!("line {n}: forbidden command")));
            }
        }
        if low.starts_with('.') {
            let word = low.split_whitespace().next().unwrap_or("");
            if FORBIDDEN_DOT.contains(&word) {
                return Err(Rejected(format!("line {n}: {word} is not allowed")));
            }
            if !ALLOWED_DOT.contains(&word) {
                return Err(Rejected(format!("line {n}: unknown dot command {word}")));
            }
            if word == ".tran" {
                let toks: Vec<&str> = low.split_whitespace().collect();
                let step = toks.get(1).and_then(|t| parse_number(t));
                let stop = toks.get(2).and_then(|t| parse_number(t));
                match (step, stop) {
                    (Some(a), Some(b)) if a > 0.0 && b / a <= MAX_TRAN_POINTS => {}
                    (Some(_), Some(_)) => return Err(Rejected(format!("line {n}: .tran asks for too many points"))),
                    _ => return Err(Rejected(format!("line {n}: malformed .tran"))),
                }
            }
            continue;
        }
        if cont {
            continue;
        }
        let first = body.chars().next().unwrap().to_ascii_uppercase();
        if !ALLOWED_ELEMENTS.contains(first) {
            return Err(Rejected(format!("line {n}: element type {first} not allowed")));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    const GOOD: &str = "* good\nV1 in 0 DC 12\nR1 in out 1k\nC1 out 0 1u\n.tran 1u 1m\n.meas tran vavg AVG v(out)\n.end\n";

    #[test]
    fn accepts_plain() {
        assert_eq!(check(GOOD), Ok(()));
    }

    #[test]
    fn rejects_malicious() {
        let bad = [
            GOOD.replace(".end", ".control\nshell rm -rf ~\n.endc\n.end"),
            GOOD.replace(".end", ".include /etc/passwd\n.end"),
            GOOD.replace(".end", ".lib /tmp/x.lib tt\n.end"),
            GOOD.replace(".tran 1u 1m", ".tran 1p 10"),
            GOOD.replace("R1 in out 1k", "Z1 in out 1k"),
            GOOD.replace(".end", ".exec shell ls\n.end"),
            GOOD.replace(".end", ".option\n+ shell=1\n.end"),
            format!("*x\n{}", "R1 a b 1\n".repeat(30_000)),
        ];
        for b in bad.iter() {
            assert!(check(b).is_err(), "accepted: {}", &b[..b.len().min(60)]);
        }
    }

    #[test]
    fn numbers() {
        let near = |a: Option<f64>, b: f64| (a.unwrap() - b).abs() <= 1e-12 * b.abs();
        assert!(near(parse_number("10u"), 10e-6));
        assert!(near(parse_number("1meg"), 1e6));
        assert!(near(parse_number("2.5e-3"), 2.5e-3));
        assert!((parse_number("1m").unwrap() - 1e-3).abs() < 1e-18);
    }
    /// tests/fixtures/guard_cases.txt is shared with the Python and JavaScript guards.
    #[test]
    fn shared_cases() {
        let text = include_str!("../../../tests/fixtures/guard_cases.txt");
        let mut cases: Vec<(String, bool, String)> = vec![];
        for line in text.split_inclusive('\n') {
            if let Some(rest) = line.strip_prefix("===") {
                let mut it = rest.split_whitespace();
                let ok = it.next() == Some("ok");
                let name = it.next().unwrap_or("").to_string();
                cases.push((name, ok, String::new()));
            } else if let Some(c) = cases.last_mut() {
                c.2.push_str(line);
            }
        }
        assert!(cases.len() >= 15);
        for (name, ok, net) in &cases {
            assert_eq!(check(net).is_ok(), *ok, "case {name}");
        }
    }
}
