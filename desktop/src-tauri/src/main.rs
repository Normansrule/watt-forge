// Watt Forge desktop shell. REFERENCE: build with `cargo tauri build` (see desktop/README.md).
//
// Security model (docs/SECURITY_MODEL.md):
//  * the UI is the same static web app as GitHub Pages, served from the bundle (no network needed);
//  * no Tauri fs/shell/http plugins: the only native capabilities are the commands below;
//  * designs are stored only under the app-data folder, with sanitized file names and a size cap;
//  * netlists are untrusted: netlist-guard rejects .control/.include/.lib/shell etc., then ngspice
//    runs in batch mode in a fresh temp folder with a hard wall-clock limit and output cap.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::Read;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};
use tauri::Manager;

const MAX_DESIGN_BYTES: usize = 10_000;
const SIM_TIMEOUT: Duration = Duration::from_secs(60);
const MAX_OUTPUT_BYTES: usize = 1_000_000;

fn designs_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_data_dir().map_err(|e| e.to_string())?.join("designs");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

fn safe_name(name: &str) -> Result<String, String> {
    let ok = !name.is_empty()
        && name.len() <= 64
        && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == ' ');
    if ok { Ok(format!("{}.json", name.trim())) } else { Err("design names use letters, digits, space, - and _ (max 64)".into()) }
}

#[tauri::command]
fn save_design(app: tauri::AppHandle, name: String, json: String) -> Result<(), String> {
    if json.len() > MAX_DESIGN_BYTES {
        return Err("design too large".into());
    }
    serde_json::from_str::<serde_json::Value>(&json).map_err(|e| format!("not valid JSON: {e}"))?;
    let path = designs_dir(&app)?.join(safe_name(&name)?);
    std::fs::write(path, json).map_err(|e| e.to_string())
}

#[tauri::command]
fn list_designs(app: tauri::AppHandle) -> Result<Vec<String>, String> {
    let mut out = vec![];
    for entry in std::fs::read_dir(designs_dir(&app)?).map_err(|e| e.to_string())? {
        let p = entry.map_err(|e| e.to_string())?.path();
        if p.extension().map(|e| e == "json").unwrap_or(false) {
            if let Some(stem) = p.file_stem() {
                out.push(stem.to_string_lossy().into_owned());
            }
        }
    }
    out.sort();
    Ok(out)
}

#[tauri::command]
fn load_design(app: tauri::AppHandle, name: String) -> Result<String, String> {
    let path = designs_dir(&app)?.join(safe_name(&name)?);
    let text = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    if text.len() > MAX_DESIGN_BYTES {
        return Err("design too large".into());
    }
    Ok(text)
}

#[tauri::command]
fn simulate_netlist(netlist: String) -> Result<String, String> {
    netlist_guard::check(&netlist).map_err(|r| r.0)?;
    // a fresh folder per run, so two simulations started together never share files
    static RUNS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let run = RUNS.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!("wattforge-{}-{}", std::process::id(), run));
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let file = dir.join("circuit.cir");
    std::fs::write(&file, &netlist).map_err(|e| e.to_string())?;
    let mut child = Command::new("ngspice")
        .arg("-b")
        .arg(&file)
        .current_dir(&dir)
        .env_clear()
        .env("PATH", std::env::var("PATH").unwrap_or_default())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("could not start ngspice (is it installed?): {e}"))?;
    // drain stdout on a thread so a chatty simulation can't block on a full pipe
    let mut stdout = child.stdout.take().ok_or("no stdout")?;
    let reader = std::thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = (&mut stdout).take(MAX_OUTPUT_BYTES as u64).read_to_end(&mut buf);
        let _ = std::io::copy(&mut stdout, &mut std::io::sink()); // discard the rest
        String::from_utf8_lossy(&buf).into_owned()
    });
    let start = Instant::now();
    loop {
        match child.try_wait().map_err(|e| e.to_string())? {
            Some(_) => break,
            None if start.elapsed() > SIM_TIMEOUT => {
                let _ = child.kill();
                let _ = std::fs::remove_dir_all(&dir);
                return Err("simulation exceeded the 60 s limit and was stopped".into());
            }
            None => std::thread::sleep(Duration::from_millis(50)),
        }
    }
    let out = reader.join().unwrap_or_default();
    let _ = std::fs::remove_dir_all(&dir);
    Ok(out)
}

/// End-to-end self-test, used by CI: with WATTFORGE_SMOKE=1 the app runs a netlist through the real
/// page -> IPC -> guard -> ngspice path, checks the guard rejects a malicious netlist, runs one MPPT
/// benchmark in the control lab's module Web Worker, reports here, and exits with status 0 (pass) or
/// 1 (fail). Without the variable this command does nothing.
#[tauri::command]
fn smoke_report(app: tauri::AppHandle, ok: bool, detail: String) {
    if std::env::var_os("WATTFORGE_SMOKE").is_none() {
        return;
    }
    println!("WATTFORGE_SMOKE {} {}", if ok { "PASS" } else { "FAIL" }, detail.chars().take(400).collect::<String>());
    app.exit(if ok { 0 } else { 1 });
}

const SMOKE_JS: &str = r#"
(async () => {
  const t = window.__TAURI__ && window.__TAURI__.core;
  if (!t) return;
  const report = (ok, detail) => t.invoke('smoke_report', { ok, detail: String(detail) });
  try {
    const net = '* smoke\nV1 in 0 DC 12\nR1 in out 1k\nC1 out 0 1u\n.tran 1u 10m\n.meas tran vavg AVG v(out) FROM=9m TO=10m\n.end\n';
    const out = await t.invoke('simulate_netlist', { netlist: net });
    const m = /vavg\s*=\s*([-+0-9.eE]+)/.exec(out);
    let rejected = false;
    try { await t.invoke('simulate_netlist', { netlist: '* x\n.control\nshell ls\n.endc\n.end\n' }); } catch (e) { rejected = true; }
    // the control lab's benchmark worker (module worker under the app's CSP) must run too
    const worker = await new Promise((resolve) => {
      let w;
      const timer = setTimeout(() => resolve('timeout'), 60000);
      try { w = new Worker(new URL('js/workers/control-worker.js', location.href), { type: 'module' }); }
      catch (e) { clearTimeout(timer); resolve('blocked: ' + e); return; }
      w.onerror = (e) => { clearTimeout(timer); resolve('error: ' + (e.message || 'worker error')); };
      w.onmessage = (ev) => {
        if (ev.data.done) { clearTimeout(timer); resolve(ev.data.results.po.eta_mppt); }
        else if (ev.data.error) { clearTimeout(timer); resolve('error: ' + ev.data.error); }
      };
      w.postMessage({ id: 1, profile: 'steady', keys: ['po'], seeds: [7] });
    });
    const workerOk = typeof worker === 'number' && worker > 0.99;
    const ok = !!m && Math.abs(parseFloat(m[1]) - 12) < 0.05 && rejected && workerOk;
    await report(ok, `vavg=${m ? m[1] : 'missing'} guard_rejected=${rejected} worker_eta=${worker} page=${location.pathname}`);
  } catch (e) { await report(false, e); }
})();
"#;

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![save_design, list_designs, load_design, simulate_netlist, smoke_report])
        .setup(|app| {
            if std::env::var_os("WATTFORGE_SMOKE").is_some() {
                let win = app.get_webview_window("main").ok_or("no main window")?;
                let handle = win.clone();
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_secs(3)); // let the page load
                    let _ = handle.eval(SMOKE_JS);
                });
                let app_handle = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_secs(90));
                    println!("WATTFORGE_SMOKE FAIL timeout");
                    app_handle.exit(1);
                });
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Watt Forge");
}
