//! Public-only license guard for the next compiled AUTOCATCHSUBS binary.
//! No Admin bypass, runtime key selector, private key or plaintext activation code.
use base64::{engine::general_purpose::STANDARD, Engine as _};
use ed25519_dalek::{Signature, VerifyingKey};
use once_cell::sync::OnceCell;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, io::Write, path::PathBuf, process::{Command, Stdio}, time::{Duration, Instant}};

const PRODUCT: &str = "AUTOCATCHSUBS";
// Both values are pinned at release build time; missing configuration fails closed.
const PUBLIC_KEY: Option<&str> = option_env!("AUTOCATCHSUBS_LICENSE_PUBLIC_KEY");
const ENDPOINT: Option<&str> = option_env!("AUTOCATCHSUBS_LICENSE_ENDPOINT");
static HWID: OnceCell<Result<String, String>> = OnceCell::new();

fn state() -> Result<PathBuf,String> {
    let root=std::env::var_os("LOCALAPPDATA").ok_or("No se encontró el perfil local de Windows")?;
    Ok(PathBuf::from(root).join("AUTOCATCHSUBS-License"))
}

fn canonical(value: &Value) -> Result<Vec<u8>,String> {
    fn sorted(value:&Value)->Value {
        match value {
            Value::Object(map)=>Value::Object(map.iter().map(|(k,v)|(k.clone(),sorted(v))).collect::<BTreeMap<_,_>>().into_iter().collect()),
            Value::Array(items)=>Value::Array(items.iter().map(sorted).collect()),
            _=>value.clone()
        }
    }
    serde_json::to_vec(&sorted(value)).map_err(|_|"Formato de licencia inválido".into())
}

fn verify(envelope:&Value,kind:&str)->Result<Value,String> {
    let error="Licencia inválida, de otro producto o firma alterada";
    let key=STANDARD.decode(PUBLIC_KEY.ok_or("Licencias aún no configuradas en esta compilación")?).map_err(|_|error)?;
    let key:[u8;32]=key.try_into().map_err(|_|error)?;
    let key=VerifyingKey::from_bytes(&key).map_err(|_|error)?;
    let signature=STANDARD.decode(envelope["signature"].as_str().ok_or(error)?).map_err(|_|error)?;
    let signature=Signature::from_slice(&signature).map_err(|_|error)?;
    let payload=&envelope["payload"];
    key.verify_strict(&canonical(payload)?,&signature).map_err(|_|error)?;
    if payload["product"]!=PRODUCT||payload["schema"]!=1||payload["kind"]!=kind||payload["generation"].as_u64().unwrap_or(0)==0 {
        return Err(error.into())
    }
    Ok(payload.clone())
}

fn read(name:&str)->Result<Value,String> {
    let bytes=fs::read(state()?.join(name)).map_err(|_|"Activa AUTOCATCHSUBS antes de iniciar este trabajo")?;
    if bytes.len()>262144 {return Err("Estado de licencia demasiado grande".into())}
    serde_json::from_slice(&bytes).map_err(|_|"Estado de licencia dañado".into())
}

fn write(name:&str,value:&Value)->Result<(),String> {
    let dir=state()?;fs::create_dir_all(&dir).map_err(|_|"No se pudo guardar la activación")?;
    let mut temporary=tempfile::NamedTempFile::new_in(&dir).map_err(|_|"No se pudo guardar la activación")?;
    temporary.write_all(&serde_json::to_vec(value).map_err(|_|"Formato inválido")?).map_err(|_|"No se pudo guardar la activación")?;
    temporary.as_file().sync_all().map_err(|_|"No se pudo guardar la activación")?;
    temporary.persist(dir.join(name)).map_err(|_|"No se pudo guardar la activación")?;
    Ok(())
}

fn hex(bytes:&[u8])->String {bytes.iter().map(|x|format!("{x:02x}")).collect()}

fn hardware()->Result<String,String> {
    HWID.get_or_init(||{
        if !cfg!(windows) {return Err("La activación requiere Windows".into())}
        let script=r#"
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$acsCpu=@(Get-CimInstance Win32_Processor | ForEach-Object {$_.ProcessorId} | Sort-Object)
$acsPartition=Get-Partition -DriveLetter $env:SystemDrive.Substring(0,1)
$acsDisk=$acsPartition | Get-Disk
$acsInstallation=(Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid).MachineGuid
@{cpu=($acsCpu -join '|');disk=$acsDisk.SerialNumber;windows_install=$acsInstallation} | ConvertTo-Json -Compress
"#;
        let mut command=Command::new("powershell.exe");
        command.args(["-NoProfile","-NonInteractive","-Command",script]).stdout(Stdio::piped()).stderr(Stdio::null());
        #[cfg(windows)] {use std::os::windows::process::CommandExt;command.creation_flags(0x08000000);}
        let mut child=command.spawn().map_err(|_|"No se pudo leer el identificador del equipo")?;
        let started=Instant::now();
        loop {
            match child.try_wait() {
                Ok(Some(_))=>break,
                Ok(None) if started.elapsed()<Duration::from_secs(30)=>std::thread::sleep(Duration::from_millis(50)),
                _=>{let _=child.kill();let _=child.wait();return Err("Windows no respondió al leer el equipo".into())}
            }
        }
        let output=child.wait_with_output().map_err(|_|"No se pudo leer el identificador del equipo")?;
        if !output.status.success(){return Err("Windows no permitió leer el identificador del equipo".into())}
        let parts:Value=serde_json::from_slice(&output.stdout).map_err(|_|"Identificador de equipo inválido")?;
        let mut normalized=BTreeMap::new();
        for key in ["cpu","disk","windows_install"] {
            let value=parts[key].as_str().unwrap_or("").trim().to_uppercase();
            if value.is_empty(){return Err("Falta CPU, disco de Windows o identidad de instalación".into())}
            normalized.insert(key,value);
        }
        let mut digest=Sha256::new();digest.update(b"AUTOCATCH-HWID-v1\0");
        digest.update(serde_json::to_vec(&normalized).map_err(|_|"Identificador inválido")?);
        Ok(hex(&digest.finalize()))
    }).clone()
}

pub fn require_active()->Result<Value,String> {
    if cfg!(feature="acs-admin") {return Ok(json!({"license_id":"ADMIN","edition":"Admin"}))}
    let payload=verify(&read("activation.json")?,"activation")?;
    let hwid=hardware()?;
    if payload["hwid"]!=hwid {return Err("Licencia vinculada a otro equipo o instalación de Windows".into())}
    let status_path=state()?.join("verified-status.json");
    if status_path.exists() {
        let saved=read("verified-status.json")?;
        for proof in saved["blocked"].as_array().ok_or("Estado de bloqueos inválido")? {
            let blocked=verify(proof,"status")?;
            if blocked["hwid"]==hwid&&blocked["license_id"]==payload["license_id"]&&blocked["generation"]==payload["generation"]&&blocked["active"]==false {
                return Err("Licencia revocada; solicita otra activación".into())
            }
        }
    }
    Ok(payload)
}

pub fn protected_bridge(func:&str)->bool {
    matches!(func,"ExportAudio"|"AddSubtitles"|"GeneratePreview"|"StartPresetEdit"|"CapturePresetSettings")
}

#[tauri::command]
pub async fn autocatch_license_status()->Value {
    // Reading hardware is blocking; keep it off the GUI/event thread.
    tauri::async_runtime::spawn_blocking(||match require_active() {
        Ok(payload)=>json!({"active":true,"product":PRODUCT,"admin":cfg!(feature="acs-admin"),"license_id":payload["license_id"]}),
        Err(error)=>json!({"active":false,"product":PRODUCT,"message":error})
    }).await.unwrap_or_else(|_|json!({"active":false,"message":"No se pudo comprobar la licencia"}))
}

#[tauri::command]
pub async fn autocatch_open_licenses()->Result<(),String> {
    if !cfg!(feature="acs-admin") {return Err("Operación disponible solo en Admin".into())}
    let exe=std::env::current_exe().map_err(|_|"No se encontró la instalación")?;
    let mut command=Command::new(exe.with_file_name("AUTOCATCHSUBSBackend.exe"));
    command.args(["--licenses","--owner-pid",&std::process::id().to_string()]);
    #[cfg(windows)] {use std::os::windows::process::CommandExt;command.creation_flags(0x08000000);}
    command.spawn().map_err(|_|"No se pudo abrir Gestión de licencias")?;
    Ok(())
}

/// Native online reconciliation. Transport failures never invalidate a valid offline seat.
pub async fn sync_online()->Result<bool,String> {
    if cfg!(feature="acs-admin") {return Ok(true)}
    let active=tauri::async_runtime::spawn_blocking(require_active).await.map_err(|_|"Licencia no disponible")??;
    let hwid=active["hwid"].as_str().ok_or("Identidad inválida")?;
    let mut nonce_bytes=[0u8;32];
    getrandom::getrandom(&mut nonce_bytes).map_err(|_|"Windows no pudo generar la consulta")?;
    let nonce=hex(&nonce_bytes);
    let endpoint=ENDPOINT.ok_or("Servicio no configurado")?;
    let client=reqwest::Client::builder().user_agent("AUTOCATCHSUBS-JR/3.8.10").redirect(reqwest::redirect::Policy::none()).timeout(Duration::from_secs(8)).build().map_err(|_|"Sin conexión")?;
    let response=client.post(format!("{}/v1/check",endpoint.trim_end_matches('/'))).json(&json!({"activation":read("activation.json")?,"hwid":hwid,"nonce":nonce})).send().await.map_err(|_|"Sin conexión")?;
    if !response.status().is_success(){return Err("Servicio no disponible".into())}
    let bytes=response.bytes().await.map_err(|_|"Respuesta incompleta")?;
    if bytes.len()>32768{return Err("Respuesta inválida".into())}
    let proof:Value=serde_json::from_slice(&bytes).map_err(|_|"Respuesta inválida")?;
    let payload=verify(&proof,"status")?;
    if payload["hwid"]!=hwid||payload["nonce"]!=nonce||payload["license_id"]!=active["license_id"]||payload["generation"]!=active["generation"]||!payload["active"].is_boolean(){return Err("Respuesta no corresponde a la consulta".into())}
    let sequence=payload["sequence"].as_u64().ok_or("Secuencia inválida")?;
    let mut saved=if state()?.join("verified-status.json").exists(){read("verified-status.json")?}else{json!({"sequence":0,"blocked":[]})};
    if sequence<saved["sequence"].as_u64().ok_or("Estado inválido")? {return Err("Respuesta anterior".into())}
    saved["sequence"]=json!(sequence);
    if payload["active"]==false {
        saved["blocked"].as_array_mut().ok_or("Estado inválido")?.push(proof);
    }
    write("verified-status.json",&saved)?;
    Ok(payload["active"]==true)
}

#[tauri::command]
pub async fn autocatch_activate_license(code:String,profile_name:String)->Result<Value,String> {
    let code=code.trim().to_uppercase();
    let alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    if code.len()!=19||!code.split('-').all(|part|part.len()==4&&part.chars().all(|c|alphabet.contains(c))) {
        return Err("Usa un código XXXX-XXXX-XXXX-XXXX".into())
    }
    let hwid=tauri::async_runtime::spawn_blocking(hardware).await.map_err(|_|"No se pudo leer el equipo")??;
    let endpoint=ENDPOINT.ok_or("Servicio de activación aún no configurado")?;
    let url=reqwest::Url::parse(endpoint).map_err(|_|"Servicio de activación inválido")?;
    if url.scheme()!="https"||url.host_str().is_none()||!url.username().is_empty()||url.password().is_some()||url.query().is_some()||url.fragment().is_some() {
        return Err("La activación requiere un servicio HTTPS".into())
    }
    let client=reqwest::Client::builder().user_agent("AUTOCATCHSUBS-JR/3.8.10").redirect(reqwest::redirect::Policy::none()).timeout(Duration::from_secs(8)).build().map_err(|_|"Servicio no disponible")?;
    let response=client.post(format!("{}/v1/activate",endpoint.trim_end_matches('/'))).json(&json!({
        "product":PRODUCT,"code":code,"hwid":hwid,"computer":std::env::var("COMPUTERNAME").unwrap_or_default(),"profile_name":profile_name.chars().take(128).collect::<String>()
    })).send().await.map_err(|_|"No se pudo conectar. Reintenta con el mismo código")?;
    if !response.status().is_success(){return Err("Código inválido, ya usado en otro equipo o servicio no disponible".into())}
    let bytes=response.bytes().await.map_err(|_|"Respuesta incompleta. Reintenta con el mismo código")?;
    if bytes.len()>32768 {return Err("Respuesta de activación inválida".into())}
    let envelope:Value=serde_json::from_slice(&bytes).map_err(|_|"Respuesta de activación inválida")?;
    let payload=verify(&envelope,"activation")?;
    if payload["hwid"]!=hwid{return Err("La activación no corresponde a este equipo".into())}
    // Do not overwrite a previously blocked copy of this same activation.
    if state()?.join("verified-status.json").exists() {
        let saved=read("verified-status.json")?;
        for proof in saved["blocked"].as_array().ok_or("Estado de bloqueos inválido")? {
            let blocked=verify(proof,"status")?;
            if blocked["hwid"]==hwid&&blocked["license_id"]==payload["license_id"]&&blocked["generation"]==payload["generation"]&&blocked["active"]==false {
                return Err("Licencia revocada".into())
            }
        }
    }
    write("activation.json",&envelope)?;
    Ok(json!({"active":true,"license_id":payload["license_id"]}))
}
