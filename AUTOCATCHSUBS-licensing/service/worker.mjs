// No desktop binaries or private Admin UI are served by this Worker.
export const PRODUCT = 'AUTOCATCHSUBS';
const encoder = new TextEncoder();
const CODE = /^[A-HJ-NP-Z2-9]{4}(?:-[A-HJ-NP-Z2-9]{4}){3}$/;
const HWID = /^[a-f0-9]{64}$/;
const ID = /^ACS-\d{3}$/;
export function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k)+':'+canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
function bytes(text) { return Uint8Array.from(atob(text), c=>c.charCodeAt(0)); }
function b64(value) { return btoa(String.fromCharCode(...new Uint8Array(value))); }
function message(error, status=400) { return reply({error},status); }
function reply(body,status=200) {
  return new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
}
export async function digest(text) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(text)))].map(x=>x.toString(16).padStart(2,'0')).join('');
}
export async function sign(payload, env) {
  const key = await crypto.subtle.importKey('pkcs8',bytes(env.SIGNING_KEY_PKCS8),{name:'Ed25519'},false,['sign']);
  return {payload,signature:b64(await crypto.subtle.sign('Ed25519',key,encoder.encode(canonical(payload))))};
}
async function verify(envelope,env) {
  const key=await crypto.subtle.importKey('raw',bytes(env.PUBLIC_KEY),{name:'Ed25519'},false,['verify']);
  if(!await crypto.subtle.verify('Ed25519',key,bytes(envelope.signature),encoder.encode(canonical(envelope.payload))))throw Error('invalid');
  if(envelope.payload.product!==PRODUCT||envelope.payload.schema!==1||envelope.payload.kind!=='activation')throw Error('invalid');
  return envelope.payload;
}
async function admin(request,env) {
  const incoming=request.headers.get('Authorization')||'';
  if(!env.ADMIN_TOKEN||env.ADMIN_TOKEN.length<40||incoming.length>512)return false;
  const a=await digest(incoming),b=await digest('Bearer '+env.ADMIN_TOKEN);
  let mismatch=0;for(let i=0;i<a.length;i++)mismatch|=a.charCodeAt(i)^b.charCodeAt(i);
  return mismatch===0;
}
async function limited(request,env) {
  const now=Math.floor(Date.now()/1000),ip=request.headers.get('CF-Connecting-IP')||'local';
  const bucket=await digest(ip)+':'+Math.floor(now/60);
  const row=await env.DB.prepare('INSERT INTO attempts(bucket,count,expires) VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1 RETURNING count').bind(bucket,now+120).first();
  // Expired counters are short-lived; cleanup is best effort and carries no secrets.
  if(now%10===0)await env.DB.prepare('DELETE FROM attempts WHERE expires<?').bind(now).run();
  return row.count>30;
}
function activation(row) {
  return {schema:1,kind:'activation',product:PRODUCT,license_id:row.id,generation:row.generation,
    hwid:row.hwid,computer:row.computer,profile_name:row.profile,issued_at:row.activated_at};
}
export default {
  async fetch(request,env) {
    const path=new URL(request.url).pathname;
    if(request.method!=='POST')return message('Método no permitido',405);
    if(Number(request.headers.get('Content-Length')||0)>8192)return message('Solicitud demasiado grande',413);
    const raw=await request.text();
    if(encoder.encode(raw).length>8192)return message('Solicitud demasiado grande',413);
    let data;try{data=JSON.parse(raw);}catch{return message('Solicitud inválida');}
    if(!data||Array.isArray(data)||typeof data!=='object')return message('Solicitud inválida');
    try {
      if(path.startsWith('/admin/')) {
        if(!await admin(request,env))return message('No autorizado',401);
        if(path==='/admin/seed') {
          if(!Array.isArray(data.seats)||!data.seats.length||data.seats.length>20)return message('Máximo 20 puestos por lote');
          if(data.seats.some(x=>!ID.test(x.id)||Number(x.id.slice(4))<1||Number(x.id.slice(4))>100||!HWID.test(x.code_hash)))return message('Puesto inválido');
          // Repeating a seed after a network failure preserves the same identity.
          for(const item of data.seats) {
            const existing=await env.DB.prepare('SELECT code_hash FROM seats WHERE id=?').bind(item.id).first();
            if(existing&&existing.code_hash!==item.code_hash)return message('La identidad del código ya existe',409);
          }
          await env.DB.batch(data.seats.map(x=>env.DB.prepare('INSERT OR IGNORE INTO seats(id,code_hash) VALUES(?,?)').bind(x.id,x.code_hash)));
          return reply({ok:true});
        }
        if(path==='/admin/list')return reply({seats:(await env.DB.prepare('SELECT id,generation,state,hwid,computer,profile,alias,activated_at FROM seats ORDER BY id').all()).results});
        if(!ID.test(data.id))return message('Puesto inválido');
        if(path==='/admin/revoke') {
          const row=await env.DB.prepare('SELECT * FROM seats WHERE id=?').bind(data.id).first();
          if(!row||row.state==='FREE')return message('Puesto sin activar');
          if(row.state!=='REVOKED')await env.DB.batch([
            env.DB.prepare('INSERT OR IGNORE INTO blocks(id,generation) VALUES(?,?)').bind(row.id,row.generation),
            env.DB.prepare("UPDATE seats SET state='REVOKED' WHERE id=?").bind(row.id),
            env.DB.prepare('UPDATE metadata SET sequence=sequence+1 WHERE id=1')]);
          return reply({ok:true});
        }
        if(path==='/admin/alias') {
          if(typeof data.alias!=='string'||data.alias.length>128)return message('Alias inválido');
          await env.DB.prepare('UPDATE seats SET alias=? WHERE id=?').bind(data.alias,data.id).run();
          return reply({ok:true});
        }
        return message('Operación desconocida',404);
      }
      if(path!=='/v1/activate'&&path!=='/v1/check')return message('Operación desconocida',404);
      if(await limited(request,env))return message('Demasiados intentos; espera un minuto',429);
      if(path==='/v1/activate') {
        const code=String(data.code||'').trim().toUpperCase();
        if(!CODE.test(code)||!HWID.test(data.hwid)||data.product!==PRODUCT)return message('Datos de activación inválidos');
        const codeHash=await digest(PRODUCT+'\0'+code),issued=new Date().toISOString();
        // One atomic compare-and-set. Two devices cannot consume the same code.
        let row=await env.DB.prepare("UPDATE seats SET state='ACTIVE',hwid=?,computer=?,profile=?,activated_at=? WHERE code_hash=? AND state='FREE' RETURNING *").bind(data.hwid,String(data.computer||'').slice(0,128),String(data.profile_name||'').slice(0,128),issued,codeHash).first();
        if(!row)row=await env.DB.prepare('SELECT * FROM seats WHERE code_hash=?').bind(codeHash).first();
        if(!row||row.state!=='ACTIVE'||row.hwid!==data.hwid)return message('Código inválido, revocado o vinculado a otro equipo',409);
        return reply(await sign(activation(row),env));
      }
      let payload;try{payload=await verify(data.activation,env);}catch{return message('Licencia inválida');}
      if(payload.hwid!==data.hwid||!HWID.test(data.hwid)||!HWID.test(data.nonce))return message('Dispositivo inválido');
      const rows=await env.DB.batch([
        env.DB.prepare('SELECT state,hwid,generation FROM seats WHERE id=?').bind(payload.license_id),
        env.DB.prepare('SELECT sequence FROM metadata WHERE id=1')]);
      const row=rows[0].results[0],sequence=rows[1].results[0].sequence;
      const active=!!row&&row.state==='ACTIVE'&&row.hwid===data.hwid&&row.generation===payload.generation;
      return reply(await sign({schema:1,kind:'status',product:PRODUCT,license_id:payload.license_id,
        generation:payload.generation,hwid:data.hwid,nonce:data.nonce,active,sequence,checked_at:new Date().toISOString()},env));
    } catch {
      // Do not log activation codes, device IDs, signing keys or Admin tokens.
      return message('Servicio temporalmente no disponible; vuelve a intentar',503);
    }
  }
};
