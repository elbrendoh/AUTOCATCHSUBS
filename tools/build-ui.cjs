// Reproduce both clients from the public baseline, readable overlays and activation UI.
const fs=require('fs'),path=require('path'),cp=require('child_process'),crypto=require('crypto');
const root=path.resolve(__dirname,'..');
cp.execFileSync(process.execPath,[path.join(root,'ui/overrides/patch_ui.cjs')],{stdio:'inherit'});
for(const edition of ['admin','jr']){
  const dist=path.join(root,'AUTOCATCHSUBS-release-source','dist-'+edition);
  fs.cpSync(path.join(root,'ui/baseline'),dist,{recursive:true});
  fs.cpSync(path.join(root,'ui/preview/assets'),path.join(dist,'assets'),{recursive:true});
  const title=edition==='jr'?'AUTOCATCHSUBS JR':'AUTOCATCHSUBS';
  const html=fs.readFileSync(path.join(root,'ui/preview/index.html'),'utf8')
    .replace('<title>AUTOCATCHSUBS</title>','<title>'+title+'</title>')
    .replace('</head>','<script defer src="/activation.js"></script></head>');
  fs.writeFileSync(path.join(dist,'index.html'),html);
  for(const name of fs.readdirSync(path.join(dist,'assets')).filter(x=>x.endsWith('.js'))){
    const file=path.join(dist,'assets',name);
    let js=fs.readFileSync(file,'utf8');
    if(edition==='jr')js=js.replaceAll('56102','56202').replaceAll('56103','56203').replaceAll('56104','56204');
    fs.writeFileSync(file,js);
    cp.execFileSync(process.execPath,['--check',file]);
  }
  fs.copyFileSync(path.join(root,'AUTOCATCHSUBS-licensing/activation.js'),path.join(dist,'activation.js'));
  console.log('Built '+title+' UI from public sources; bundle SHA256 '+crypto.createHash('sha256').update(fs.readFileSync(path.join(dist,'assets/index-BRt8Z4DF.js'))).digest('hex'));
}
