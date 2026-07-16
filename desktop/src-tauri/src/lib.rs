// Donald OS desktop shell. A thin native wrapper: it opens a window onto the
// Donald web shell (served by the backend at /app), adds the auto-updater, and
// lets the shell open external links in the system browser (the OAuth flow).

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .run(tauri::generate_context!())
        .expect("error while running Donald OS");
}
