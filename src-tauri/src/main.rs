use std::env;
use std::io;
use std::net::{Ipv4Addr, SocketAddrV4, TcpListener, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use tauri::menu::{AboutMetadata, Menu, MenuItemKind, PredefinedMenuItem};
use tauri::{AppHandle, Runtime, WebviewUrl, WebviewWindowBuilder};

const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_READY_TIMEOUT: Duration = Duration::from_secs(30);

fn display_version(revision: Option<&str>) -> String {
    match revision.map(str::trim).filter(|value| !value.is_empty()) {
        Some(revision) => format!("{} ({revision})", env!("CARGO_PKG_VERSION")),
        None => env!("CARGO_PKG_VERSION").to_string(),
    }
}

fn runtime_display_version() -> String {
    let revision = env::var("MATHPUB_BUILD_REVISION").ok();
    display_version(revision.as_deref())
}

fn about_metadata<R: Runtime>(app: &AppHandle<R>) -> AboutMetadata<'static> {
    AboutMetadata {
        name: Some(app.package_info().name.clone()),
        version: Some(runtime_display_version()),
        copyright: app.config().bundle.copyright.clone(),
        authors: app
            .config()
            .bundle
            .publisher
            .clone()
            .map(|publisher| vec![publisher]),
        ..Default::default()
    }
}

fn app_menu<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<Menu<R>> {
    let menu = Menu::default(app)?;
    let submenu_name = if cfg!(target_os = "macos") {
        app.package_info().name.as_str()
    } else {
        "Help"
    };
    let about_submenu = menu
        .items()?
        .into_iter()
        .find_map(|item| match item {
            MenuItemKind::Submenu(submenu)
                if submenu.text().is_ok_and(|text| text == submenu_name) =>
            {
                Some(submenu)
            }
            _ => None,
        })
        .ok_or_else(|| io::Error::other("Tauri default About submenu was not found"))?;
    let default_about = about_submenu
        .remove_at(0)?
        .ok_or_else(|| io::Error::other("Tauri default About item was not found"))?;
    if !matches!(default_about, MenuItemKind::Predefined(_)) {
        return Err(io::Error::other("Tauri default About item has an unexpected type").into());
    }
    let about = PredefinedMenuItem::about(app, None, Some(about_metadata(app)))?;
    about_submenu.insert(&about, 0)?;
    Ok(menu)
}

fn reserve_port() -> io::Result<u16> {
    let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0))?;
    Ok(listener.local_addr()?.port())
}

fn backend_command(port: u16) -> Command {
    let program = env::var_os("MATHPUB_GUI_BACKEND").unwrap_or_else(|| "mathpub".into());
    let mut command = Command::new(program);
    command
        .arg("workspace")
        .arg("--host")
        .arg(BACKEND_HOST)
        .arg("--port")
        .arg(port.to_string())
        .arg("--no-browser")
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());
    command
}

fn wait_for_backend(port: u16, child: &mut Child) -> io::Result<()> {
    let address = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let started = Instant::now();
    loop {
        if TcpStream::connect_timeout(&address.into(), Duration::from_millis(100)).is_ok() {
            return Ok(());
        }
        if let Some(status) = child.try_wait()? {
            return Err(io::Error::other(format!(
                "mathpub workspace backend exited before startup: {status}"
            )));
        }
        if started.elapsed() >= BACKEND_READY_TIMEOUT {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "timed out waiting for mathpub workspace backend",
            ));
        }
        thread::sleep(Duration::from_millis(50));
    }
}

fn stop_backend(backend: &Arc<Mutex<Option<Child>>>) {
    let Ok(mut guard) = backend.lock() else {
        return;
    };
    let Some(mut child) = guard.take() else {
        return;
    };
    let _ = child.kill();
    let _ = child.wait();
}

fn main() {
    let port = reserve_port().expect("failed to reserve a localhost port");
    let mut child = backend_command(port)
        .spawn()
        .expect("failed to launch the mathpub workspace backend");
    if let Err(error) = wait_for_backend(port, &mut child) {
        let _ = child.kill();
        let _ = child.wait();
        panic!("{error}");
    }

    let backend = Arc::new(Mutex::new(Some(child)));
    let backend_for_exit = Arc::clone(&backend);
    let workspace_url: tauri::Url = format!("http://{BACKEND_HOST}:{port}/")
        .parse()
        .expect("workspace URL should be valid");

    let app = tauri::Builder::default()
        .menu(app_menu)
        .setup(move |app| {
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(workspace_url))
                .title("MathPub Interactive Workspace")
                .inner_size(1280.0, 720.0)
                .min_inner_size(960.0, 600.0)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build the mathpub desktop application");

    app.run(move |_app_handle, event| {
        if matches!(
            event,
            tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
        ) {
            stop_backend(&backend_for_exit);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reserves_an_ephemeral_local_port() {
        assert_ne!(reserve_port().unwrap(), 0);
    }

    #[test]
    fn display_version_includes_build_revision() {
        assert_eq!(display_version(Some("970c980")), "0.1.0 (970c980)");
        assert_eq!(
            display_version(Some(" 970c980-dirty ")),
            "0.1.0 (970c980-dirty)"
        );
        assert_eq!(display_version(None), "0.1.0");
        assert_eq!(display_version(Some("  ")), "0.1.0");
    }

    #[test]
    fn backend_command_uses_workspace_without_browser() {
        let command = backend_command(43210);
        let args: Vec<_> = command
            .get_args()
            .map(|arg| arg.to_string_lossy())
            .collect();
        assert_eq!(
            args,
            [
                "workspace",
                "--host",
                "127.0.0.1",
                "--port",
                "43210",
                "--no-browser"
            ]
        );
    }
}
