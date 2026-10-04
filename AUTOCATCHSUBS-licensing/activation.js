/* Public-only activation UI. Native commands enforce the actual license. */
(()=>{
  const invoke=(name,args)=>window.__TAURI_INTERNALS__.invoke(name,args);
  let overlay, busy=false, lastActive=false;
  const style=document.createElement('style');
  style.textContent=`.acs-license-shade{position:fixed;inset:0;z-index:2147483645;background:#080b12ed;display:flex;align-items:center;justify-content:center;padding:24px;font-family:inherit;color:#e5e7eb}.acs-license-card{width:370px;max-width:100%;background:#151a24;border:1px solid #303c52;border-radius:14px;padding:26px;box-shadow:0 18px 60px #0008}.acs-license-card h2{font-size:19px;margin:0 0 14px}.acs-license-card p{font-size:13px;line-height:1.6;color:#b3bece}.acs-license-card label{display:block;font-size:12px;margin:14px 0 5px}.acs-license-card input{box-sizing:border-box;width:100%;background:#0c111b;color:#fff;border:1px solid #435371;border-radius:7px;padding:11px;font:inherit}.acs-license-card button,.acs-license-manage{background:#2563eb;border:0;color:white;border-radius:7px;padding:9px 14px;cursor:pointer;font:inherit}.acs-license-card button{width:100%;margin-top:16px}.acs-license-card button:disabled{opacity:.5;cursor:wait}.acs-license-status{min-height:36px;white-space:pre-wrap}.acs-license-manage{font-size:11px;padding:5px 9px;margin-left:6px}.acs-license-card .acs-license-retry{background:transparent;color:#9cbcff;border:1px solid #3c5178;margin-top:7px}`;
  document.head.append(style);
  function manager(){
    if(document.getElementById('acs-license-manage'))return;
    const tutorial=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Tutorial');
    if(!tutorial)return;
    const button=document.createElement('button');button.id='acs-license-manage';button.className='acs-license-manage';button.textContent='Licencias';
    button.onclick=()=>invoke('autocatch_open_licenses').catch(e=>{button.title=String(e);button.textContent='Reintentar licencias';});tutorial.insertAdjacentElement('afterend',button);
  }
  function show(message){
    if(overlay)return;
    overlay=document.createElement('div');overlay.className='acs-license-shade';overlay.setAttribute('role','dialog');overlay.setAttribute('aria-modal','true');overlay.setAttribute('aria-label','Activar AUTOCATCHSUBS JR');
    overlay.innerHTML=`<form class="acs-license-card"><h2>AUTOCATCHSUBS JR</h2><p>Activa este equipo con el código que te entregó tu administrador. Después podrás trabajar sin conexión.</p><label for="acs-editor">Tu nombre</label><input id="acs-editor" maxlength="128" autocomplete="name" placeholder="Nombre del editor"><label for="acs-code">Código de activación</label><input id="acs-code" required maxlength="19" autocomplete="off" spellcheck="false" placeholder="XXXX-XXXX-XXXX-XXXX"><p>Un código queda vinculado permanentemente a una sola PC.</p><div class="acs-license-status" role="status" aria-live="polite"></div><button type="submit">Activar este equipo</button><button type="button" class="acs-license-retry">Comprobar activación guardada</button></form>`;
    overlay.querySelector('[role=status]').textContent=message||'';
    overlay.querySelector('form').onsubmit=async e=>{
      e.preventDefault();if(busy)return;busy=true;
      const button=overlay.querySelector('[type=submit]'),status=overlay.querySelector('[role=status]');button.disabled=true;button.textContent='Activando…';status.textContent='Comprobando código y equipo…';
      try{await invoke('autocatch_activate_license',{code:overlay.querySelector('#acs-code').value,profileName:overlay.querySelector('#acs-editor').value});overlay.remove();overlay=null;lastActive=true;
        if(!localStorage.getItem('autocatchsubs-jr-onboarding')){localStorage.setItem('autocatchsubs-jr-onboarding','1');setTimeout(()=>[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Tutorial')?.click(),500);}
      }catch(error){status.textContent=String(error?.message||error);button.disabled=false;button.textContent='Reintentar activación';}finally{busy=false;}
    };
    overlay.querySelector('.acs-license-retry').onclick=check;
    document.body.append(overlay);overlay.querySelector('#acs-code').focus();
  }
  function brandJR(){
    const nodes=document.createTreeWalker(document.getElementById('root')||document.body,NodeFilter.SHOW_TEXT);let node;
    while(node=nodes.nextNode())if(node.nodeValue.trim()==='AUTOCATCHSUBS')node.nodeValue=node.nodeValue.replace('AUTOCATCHSUBS','AUTOCATCHSUBS JR');
  }
  async function check(){
    if(busy)return;
    try{const state=await invoke('autocatch_license_status');if(state.admin){manager();return;}
      brandJR();if(state.active){lastActive=true;overlay?.remove();overlay=null;}else{lastActive=false;show(state.message);}
    }catch(error){if(!lastActive)show('No se pudo comprobar la activación. Pulsa Comprobar activación guardada para reintentar.');}
  }
  check();setInterval(check,5000);
})();
