const fs=require('fs'),path=require('path');
const original=path.resolve(__dirname,'../baseline');
let js=fs.readFileSync(path.join(original,'assets/index-BRt8Z4DF.js'),'utf8');
const changes=[];
function exact(old,value,count=1){const actual=js.split(old).length-1;if(actual!==count)throw Error(`Unsupported bundle: ${old.slice(0,80)} expected ${count}, got ${actual}`);js=js.split(old).join(value);changes.push({match:old,count});}
exact('const t=Ee(i=>i.preferredEditorIntegration),n=Ee(i=>i.updateSetting),r=re.useCallback(i=>{n("preferredEditorIntegration",i)},[n]);',
      'const t="davinci",n=Ee(i=>i.updateSetting),r=re.useCallback(()=>{n("preferredEditorIntegration","davinci")},[n]);');
exact('m={davinci:{productName:e("titlebar.resolve.productName"),', 'm={davinci:{productName:"AUTOCATCHSUBS",');
exact('className:`truncate min-w-0 ${y.connected?"":"text-gray-600 dark:text-gray-400"}`,children:v',
      'title:"DaVinci Resolve · "+v,className:`truncate min-w-0 ${y.connected?"":"text-gray-600 dark:text-gray-400"}`,children:"AUTOCATCHSUBS"');
exact('Object.keys(m).map(b=>{const S=m[b];', '["davinci"].map(b=>{const S=m[b];');
exact('children:[f.jsxs(hr,{children:[f.jsx(pr,{asChild:!0,children:f.jsx(Se,{type:"button",variant:"ghost",size:"icon-sm",className:"rounded-sm",onClick:()=>y(!0),children:f.jsx(W6,{})})})',
      'children:[f.jsx(ACSTutorial,{openStyle:y,styleOpen:m}),f.jsxs(hr,{children:[f.jsx(pr,{asChild:!0,children:f.jsx(Se,{type:"button",variant:"ghost",size:"icon-sm",className:"rounded-sm","data-acs-tour":"styles",onClick:()=>y(!0),children:f.jsx(W6,{})})})');
exact('"aria-label":p("titlebar.subtitleHistory.title","History"),children:f.jsx(H6,{})',
      '"aria-label":p("titlebar.subtitleHistory.title","History"),"data-acs-tour":"history",children:f.jsx(H6,{})');
exact('children:f.jsxs(qi,{className:"max-w-xl",children:[f.jsx(zo,{children:f.jsx(Io,{children:c("actionBar.subtitleStyle","Caption Style")})})',
      'children:f.jsxs(qi,{className:"max-w-xl","data-acs-tour":"style-dialog",children:[f.jsx(zo,{children:f.jsx(Io,{children:c("actionBar.subtitleStyle","Caption Style")})})');
exact('children:f.jsxs(Se,{onClick:R,size:"lg",variant:"default",disabled:Et',
      'children:f.jsxs(Se,{"data-acs-tour":"generate",onClick:R,size:"lg",variant:"default",disabled:Et');
exact('return e?f.jsxs("div",{className:Z,children:[f.jsxs("div",{className:"flex shrink-0 items-center justify-between px-3 pt-2"',
      'return e?f.jsxs("div",{className:Z,"data-acs-tour":"subtitle-preview",children:[f.jsxs("div",{className:"flex shrink-0 items-center justify-between px-3 pt-2"');
exact('className:"shrink-0 p-3 flex justify-end gap-2 border-t shadow-2xl",children:f.jsx(TC,',
      'className:"shrink-0 p-3 flex justify-end gap-2 border-t shadow-2xl","data-acs-tour":"insert",children:f.jsx(TC,');
// The upstream footer disappears when polling temporarily loses the timeline.
// Keep the original action visible and disabled until fresh timeline data returns.
exact('Nn&&F.length>0&&f.jsx(Bee,', 'F.length>0&&f.jsx(Bee,');
exact('variant:"secondary",size:"default",disabled:d,className:"w-full",onMouseEnter:',
      'variant:"secondary",size:"default",disabled:d||!e?.timelineId,title:e?.timelineId?undefined:"Abre una timeline en Resolve. Se reintentará la conexión automáticamente.",className:"w-full",onMouseEnter:');
exact('_=window.setInterval(()=>{j()},6e4);', '_=window.setInterval(()=>{j()},1e4);');
exact('},[o,h]);l.useEffect(()=>{let N=!1;if(t!=="davinci")',
      '},[o,h]);l.useEffect(()=>{const acsUpdate=items=>{s(items);p(!0);d(!1);i(info=>({...info,templates:items}))};ACS_TEMPLATE_LISTENERS.add(acsUpdate);return()=>ACS_TEMPLATE_LISTENERS.delete(acsUpdate)},[]);l.useEffect(()=>{s([]);p(!1);d(!1)},[r.projectName]);l.useEffect(()=>{let N=!1;if(t!=="davinci")');
exact('No editor connected. Connect to DaVinci Resolve, Adobe Premiere Pro, or After Effects to customise templates.',
      'Abre DaVinci Resolve y ejecuta Workspace → Scripts → Utility → AUTOCATCHSUBS.');
exact('const{t:j}=tt(),{selectedIntegration:q}=_s();if(l.useEffect',
      'const{t:j}=tt(),{selectedIntegration:q}=_s();const[acsQuery,acsSetQuery]=l.useState("");const acsFavorites=useACSFavorites();const acsStyles=useACSStyles(i),acsTemplates=acsStyles.items;const acsNormalize=x=>String(x??"").normalize("NFD").replace(/\\p{M}/gu,"").toLocaleLowerCase();const acsMatches=x=>acsNormalize(x).includes(acsNormalize(acsQuery.trim()));if(l.useEffect');
exact('className:"grid gap-2 sm:grid-cols-[minmax(240px,460px)_auto] sm:items-center",children:[',
      'className:"acs-style-heading",children:[',1);
exact('children:j("addToTimeline.mode.animated")})]})}),(e==="animated"||O)',
      'children:j("addToTimeline.mode.animated")})]})}),f.jsx("input",{type:"search",className:"acs-style-search",value:acsQuery,onChange:acsEvent=>acsSetQuery(acsEvent.target.value),placeholder:"Buscar Text+…","aria-label":"Buscar estilos Text+ por nombre"}),f.jsx(ACSRefreshStyles,{}),(e==="animated"||O)');
exact('i.filter(_=>_.value!==Fc)', 'acsFavoritesFirst(acsTemplates.filter(_=>_.value!==Fc&&acsMatches(_.label)),acsFavorites,x=>"text:"+x.value)',2);
exact('.map(_=>f.jsxs("button",{type:"button",onClick:()=>r(_.value),className:fe("flex min-h-[56px] w-full items-center justify-between rounded-md border px-4 py-3 text-left text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",n===_.value?"border-slate-950 bg-slate-950 text-white shadow-sm":"border-border bg-background text-foreground hover:bg-muted/50"),children:[f.jsx("span",{children:_.label}),n===_.value&&f.jsx(ur,{className:"size-4 shrink-0"})]},_.value))',
      '.map(_=>f.jsx(ACSStyleRow,{item:_,selected:n===_.value,onSelect:()=>r(_.value),favorites:acsFavorites},_.value))');
// The original animated picker is also used by Add to Timeline. Keep its cards,
// menus and selection handlers; insert only the star and stable favorite order.
exact('previewLoadingId:d}){const{t:h}=tt(),[p,m]=l.useState(null);',
      'previewLoadingId:d}){const acsFavorites=useACSFavorites();const{t:h}=tt(),[p,m]=l.useState(null);');
exact('children:e.map(b=>f.jsx(rQ,{preset:b,selected:t===b.id',
      'children:acsFavoritesFirst(e,acsFavorites,x=>"preset:"+x.id).map(b=>f.jsx(rQ,{preset:b,selected:t===b.id');
exact('onRequestDelete:h}){const{t:p}=tt();return f.jsxs("div",{role:"button",tabIndex:0,"aria-label":e.name',
      'onRequestDelete:h}){const acsFavorites=useACSFavorites();const{t:p}=tt();return f.jsxs("div",{role:"button",tabIndex:0,"aria-label":e.name');
exact('className:"ml-auto flex shrink-0 items-center gap-1",children:[i&&f.jsxs(Se,',
      'className:"ml-auto flex shrink-0 items-center gap-1",children:[f.jsx(ACSFavoriteButton,{favoriteKey:"preset:"+e.id,label:e.name,favorites:acsFavorites}),i&&f.jsxs(Se,');
exact('presets:p,selectedPresetId:d,onSelect:h,onRequestEdit:v,onDelete:T,onExportJson:N,onDuplicate:M',
      'presets:p.filter(acsPreset=>acsMatches(acsPreset.name)),selectedPresetId:d,onSelect:h,onRequestEdit:v,onDelete:T,onExportJson:N,onDuplicate:M');
exact('children:"No regular templates found."', 'children:acsQuery ? "No hay Text+ con ese nombre." : acsStyles.pending ? "Buscando Text+ en segundo plano…" : "No hay plantillas Text+ verificadas en el Media Pool."');
exact('className:fe(e!=="animated"&&"hidden sm:flex sm:invisible sm:pointer-events-none")})]}),f.jsx(Es,{value:"regular"',
      'className:fe(e!=="animated"&&"hidden sm:flex sm:invisible sm:pointer-events-none")})]}),f.jsx(ACSStyleProgress,{progress:acsStyles.progress,pending:acsStyles.pending}),f.jsx(Es,{value:"regular"');
exact('const{t:p}=tt(),{subtitles:m,updateSubtitles:y,speakers:v,updateSpeakers:b}=Ns(),[S,E]',
      'const{t:p}=tt(),{subtitles:m,updateSubtitles:y,speakers:v,updateSpeakers:b,currentSubtitleDocumentFilename:acsFilename}=Ns(),acsLatest=l.useRef(null);acsLatest.current={rows:m,filename:acsFilename};const[S,E]');
exact('f.jsxs(jee,{className:"mt-4",children:[', 'f.jsxs(jee,{className:"mt-4 acs-word-actions",children:[');
exact('children:"Move last word to next subtitle while preserving word timing"})})]})]}):null',
      'children:"Move last word to next subtitle while preserving word timing"})})]}),f.jsx(Se,{type:"button",variant:"outline",className:"text-xs h-8 acs-delete",title:"Eliminar esta fila de la transcripción",onMouseDown:acsEvent=>acsEvent.preventDefault(),onClick:acsEvent=>{acsEvent.stopPropagation();acsDeleteSubtitle({rows:m,index:Q,update:y,select:X,draft:T,original:P,speaker:j,latest:acsLatest,filename:acsFilename})},children:"ELIMINAR"})]}):null');
exact('R&&f.jsx(Hee,{}),F&&f.jsx(_ce,{}),V&&f.jsx(tre,{})]})})}',
      'R&&f.jsx(Hee,{}),F&&f.jsx(_ce,{}),V&&f.jsx(tre,{})]}),f.jsx(ACSConsole,{})]})})}');
exact('return f.jsx(J2,{children:f.jsxs("div",{className:"flex flex-col h-screen overflow-hidden bg-background relative",children:[',
      'return f.jsx(J2,{children:f.jsxs("div",{className:"acs-window-shell",children:[f.jsxs("div",{className:"flex flex-col h-screen overflow-hidden bg-background relative acs-main-content",children:[');
// Hoisted functions can use original minified bindings without private Fiber or
// DOM mutation hooks. The new controls participate in normal React updates.
js=js.replace('gR.createRoot(document.getElementById("root"))',
    'const ACS_TOAST=Jt;\n'+fs.readFileSync(path.join(__dirname,'workflow-ui.js.part'),'utf8')+'\n'+fs.readFileSync(path.join(__dirname,'tutorial-ui.js.part'),'utf8')+'\ngR.createRoot(document.getElementById("root"))');
if(!js.includes('function ACSConsole()'))throw Error('UI component insertion failed');
let css=fs.readFileSync(path.join(original,'assets/index-BHLyMCPU.css'),'utf8')+'\n'+fs.readFileSync(path.join(__dirname,'workflow-ui.css.part'),'utf8')+'\n'+fs.readFileSync(path.join(__dirname,'tutorial-ui.css.part'),'utf8');
let html=fs.readFileSync(path.join(original,'index.html'),'utf8').replace('<title>Tauri + React + Typescript</title>','<title>AUTOCATCHSUBS</title>');
const out=path.resolve(__dirname,'../preview');fs.mkdirSync(path.join(out,'assets'),{recursive:true});
fs.writeFileSync(path.join(out,'assets/index-BRt8Z4DF.js'),js);fs.writeFileSync(path.join(out,'assets/index-BHLyMCPU.css'),css);fs.writeFileSync(path.join(out,'index.html'),html);

console.log('Readable AUTOCATCHSUBS UI overrides built in ui/preview');
